import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path
import websockets
from typing import Optional, Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)

async def get_main_module():
    """获取 main 模块"""
    try:
        return sys.modules['__main__']
    except KeyError:
        # 如果找不到 main 模块，尝试手动导入
        spec = importlib.util.spec_from_file_location(
            "main",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
        )
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        return main

async def get_db_ops():
    """获取 main.py 中的 db_ops 实例"""
    main = await get_main_module()
    if main.db_ops is None:
        main.db_ops = await main.init_db_ops()
    return main.db_ops

class UFBClient:
    def __init__(self, config_dir: str = "./ufb/config"):
        # 获取当前文件所在目录（ufb目录）
        current_file_dir = Path(__file__).parent
        # 获取项目根目录（当前文件的上级目录）
        project_root = current_file_dir.parent
        
        self.server_url: Optional[str] = None
        self.token: Optional[str] = None
        
        # 使用项目根目录作为基准
        self.config_dir = (project_root / config_dir).resolve()
        # logger.info(f"配置目录: {self.config_dir}")
        
        self.config_path = self.config_dir / "config.json"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.on_config_update_callbacks: list[Callable[[Dict[str, Any]], None]] = []
        self.reconnect_task = None  # 用于存储重连任务
        
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

    async def ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """加载本地配置"""
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                logger.error("配置文件损坏")
                return {}
        return {}

    async def save_config(self, config: Dict[str, Any], to_client: bool = False):
        """保存配置到本地"""
        logger.info(f"保存配置到本地: {self.config_path.absolute()}")
        self.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        if to_client:
            db_ops = await get_db_ops()
            await db_ops.sync_from_json(config)
    

    def merge_configs(self, local_config: Dict[str, Any], cloud_config: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并本地和云端配置
        策略：
        1. 如果本地配置为空，使用云端配置
        2. 如果是字典类型，递归合并
        3. 如果是列表类型，合并列表（去重）
        4. 如果是其他类型，使用云端的值覆盖本地值
        """
        # 如果本地配置为空，直接使用云端配置
        if not local_config:
            return cloud_config.copy()
        
        # 如果云端配置为空，使用本地配置
        if not cloud_config:
            return local_config.copy()

        # 开始递归合并
        merged = local_config.copy()
        
        for key, cloud_value in cloud_config.items():
            # 如果是字典类型，递归合并
            if isinstance(cloud_value, dict):
                if key not in merged:
                    merged[key] = {}
                if isinstance(merged[key], dict):
                    merged[key] = self.merge_configs(merged[key], cloud_value)
                else:
                    # 如果本地值不是字典类型，但云端是字典类型，使用云端的值
                    merged[key] = cloud_value.copy()
            # 如果是列表类型，合并列表
            elif isinstance(cloud_value, list):
                if key not in merged or not isinstance(merged[key], list):
                    merged[key] = cloud_value.copy()
                else:
                    # 合并列表，去重
                    merged_list = merged[key].copy()
                    for item in cloud_value:
                        if item not in merged_list:
                            merged_list.append(item)
                    merged[key] = merged_list
            else:
                # 非字典和列表类型，使用云端的值
                merged[key] = cloud_value

        return merged

    def on_config_update(self, callback: Callable[[Dict[str, Any]], None]):
        """注册配置更新回调"""
        self.on_config_update_callbacks.append(callback)

    def notify_config_update(self, config: Dict[str, Any]):
        """通知所有监听器配置已更新"""
        for callback in self.on_config_update_callbacks:
            try:
                callback(config)
            except Exception as e:
                logger.error(f"配置更新回调执行失败: {e}")

    async def handle_config_conflict(self, conflict_data: Dict[str, Any], local_config: Dict[str, Any]) -> Dict[str, Any]:
        """处理配置冲突
        返回最终使用的配置
        """
        logger.info(f"配置冲突: \n云端时间: {conflict_data['cloudTime']}\n本地时间: {conflict_data['localTime']}")
        
        # 总是选择使用云端配置
        await self.websocket.send(json.dumps({
            "type": "resolveConflict",
            "choice": "useCloud"
        }))
        
        # 等待服务器响应
        cloud_config = json.loads(await self.websocket.recv())
        logger.info(f"收到云端配置: {json.dumps(cloud_config, ensure_ascii=False, indent=2)}")
        
        # 合并云端和本地配置
        merged_config = self.merge_configs(local_config, cloud_config)
        logger.info(f"合并后的配置: {json.dumps(merged_config, ensure_ascii=False, indent=2)}")
        
        return merged_config

    async def connect(self, server_url: str, token: str):
        """建立WebSocket连接"""
        if self.is_connected:
            await self.close()

        self.server_url = server_url
        self.token = token

        try:
            self.websocket = await websockets.connect(f"{server_url}/ws/config/{token}")
            self.is_connected = True
            logger.info("WebSocket连接已建立")
            
            # 连接成功后取消重连任务
            if self.reconnect_task:
                self.reconnect_task.cancel()
                self.reconnect_task = None
                
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            # 启动重连
            await self.start_reconnect()
            raise

    async def reconnect(self):
        """重连逻辑"""
        while True:
            try:
                if not self.is_connected and self.server_url and self.token:
                    logger.info("尝试重新连接...")
                    self.websocket = await websockets.connect(f"{self.server_url}/ws/config/{self.token}")
                    self.is_connected = True
                    logger.info("重连成功")
                    
                    # 重新启动消息处理
                    asyncio.create_task(self._handle_messages())
                    
                    # 重新发送配置更新
                    local_config = self.load_config()
                    await self.websocket.send(json.dumps({
                        "type": "update",
                        **local_config
                    }))
                    
                    # 重连成功后退出循环
                    break
            except Exception as e:
                logger.error(f"重连失败: {e}")
                await asyncio.sleep(10)  # 等待10秒后重试

    async def start_reconnect(self):
        """启动重连任务"""
        if not self.reconnect_task or self.reconnect_task.done():
            self.reconnect_task = asyncio.create_task(self.reconnect())

    async def start(self, server_url: Optional[str] = None, token: Optional[str] = None):
        """启动客户端"""
        logger.info("启动客户端")
        await self.ensure_config_dir()
        
        if server_url and token:
            await self.connect(server_url, token)
        elif self.server_url and self.token:
            await self.connect(self.server_url, self.token)
        else:
            logger.info("等待连接参数...")
            return

        # 检查本地配置
        local_config = self.load_config()
        current_timestamp = int(time.time() * 1000)

        # 确保配置结构完整
        if not local_config:
            local_config = {
                "globalConfig": {
                    "SYNC_CONFIG": {
                        "lastSyncTime": current_timestamp
                    }
                }
            }
        else:
            if "globalConfig" not in local_config:
                local_config["globalConfig"] = {}
            if "SYNC_CONFIG" not in local_config["globalConfig"]:
                local_config["globalConfig"]["SYNC_CONFIG"] = {}
            if "lastSyncTime" not in local_config["globalConfig"]["SYNC_CONFIG"]:
                local_config["globalConfig"]["SYNC_CONFIG"]["lastSyncTime"] = current_timestamp

        # 检查是否为首次同步（配置文件不存在或为空）
        if not self.config_path.exists() or not local_config:
            # 发送首次同步请求
            await self.websocket.send(json.dumps({
                "type": "firstSync",
                **local_config
            }))
        else:
            # 非首次同步，直接检查配置是否需要更新
            await self.websocket.send(json.dumps({
                "type": "update",
                **local_config
            }))

        # 创建后台任务处理消息
        asyncio.create_task(self._handle_messages())

    async def _handle_messages(self):
        """在后台处理WebSocket消息"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    logger.info(f"收到服务器消息")

                    msg_type = data.get("type")
                    if msg_type == "firstSync":
                        if data.get("message") == "firstSync_success":
                            logger.info("首次同步成功")
                            await self.save_config(data)
                            self.notify_config_update(data)

                    elif msg_type == "update":
                        if data:
                            if data.get('additional_info') != "to_server" or data.get('additional_info') is None:
                                await self.save_config(data, to_client=True)
                            else:
                                await self.save_config(data)
                            self.notify_config_update(data)
                            
                            if data.get("message") == "config_updated":
                                logger.info("配置已更新")

                    elif msg_type == "configConflict":
                        # 获取时间戳
                        cloud_time = data.get("cloudTime")
                        local_time = data.get("localTime")
                        newer_config = data.get("newerConfig")
                        
                        logger.info(f"配置冲突:\n云端时间: {cloud_time}\n本地时间: {local_time}\n较新配置: {newer_config}")
                        
                        # 加载本地配置
                        local_config = self.load_config()
                        
                        # 总是使用云端配置
                        await self.websocket.send(json.dumps({
                            "type": "resolveConflict",
                            "choice": "useCloud"
                        }))
                        
                        # 等待服务器响应
                        response = json.loads(await self.websocket.recv())
                        # 合并配置
                        merged_config = self.merge_configs(local_config, response)
                        await self.save_config(merged_config)
                        self.notify_config_update(merged_config)

                    elif msg_type == "delete":
                        if data.get("success"):
                            logger.info("配置删除成功")
                        else:
                            logger.error(f"配置删除失败: {data.get('message', '')}")

                except json.JSONDecodeError:
                    logger.error("收到无效的JSON消息")
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")

        except websockets.ConnectionClosed:
            logger.info("WebSocket连接已关闭")
            self.is_connected = False
            # 启动重连
            await self.start_reconnect()
        except Exception as e:
            logger.error(f"WebSocket错误: {e}")
            self.is_connected = False
            # 启动重连
            await self.start_reconnect()

    async def close(self):
        """关闭客户端"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
            logger.info("WebSocket连接已关闭")
            # 取消重连任务
            if self.reconnect_task:
                self.reconnect_task.cancel()
                self.reconnect_task = None
