import traceback
import aiohttp
import os
import asyncio
from telethon.tl import types

from handlers.button.button_helpers import create_media_size_buttons,create_media_settings_buttons,create_media_types_buttons,create_media_extensions_buttons, create_push_config_details_buttons
from models.models import ForwardRule, MediaTypes, MediaExtensions, RuleSync, Keyword, ReplaceRule, PushConfig
from enums.enums import AddMode
import logging
from utils.common import get_media_settings_text, get_db_ops
from models.models import get_session
from models.db_operations import DBOperations
from handlers.button.button_helpers import create_push_settings_buttons
from telethon import Button
from sqlalchemy import inspect
from utils.constants import RSS_HOST, RSS_PORT,RULES_PER_PAGE,PUSH_SETTINGS_TEXT
from utils.common import check_and_clean_chats, is_admin
from utils.auto_delete import reply_and_delete, send_message_and_delete, respond_and_delete
from managers.state_manager import state_manager

logger = logging.getLogger(__name__)



async def callback_push_settings(event, rule_id, session, message, data):
    await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id=rule_id), link_preview=False)
    return

async def callback_toggle_enable_push(event, rule_id, session, message, data):
    """处理切换推送启用状态的回调"""
    try:
        # 获取规则
        rule = session.query(ForwardRule).get(int(rule_id))
        
        rule.enable_push = not rule.enable_push
        
        # 检查是否启用了同步功能
        if rule.enable_sync:
            logger.info(f"规则 {rule.id} 启用了同步功能，正在同步推送状态到关联规则")
            # 获取需要同步的规则列表
            sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            
            # 为每个同步规则应用相同的设置
            for sync_rule in sync_rules:
                sync_rule_id = sync_rule.sync_rule_id
                logger.info(f"正在同步推送状态到规则 {sync_rule_id}")
                
                # 获取同步目标规则
                target_rule = session.query(ForwardRule).get(sync_rule_id)
                if not target_rule:
                    logger.warning(f"同步目标规则 {sync_rule_id} 不存在，跳过")
                    continue
                
                try:
                    # 更新同步目标规则的推送状态
                    target_rule.enable_push = rule.enable_push
                    logger.info(f"同步规则 {sync_rule_id} 的推送状态已更新为 {rule.enable_push}")
                except Exception as e:
                    logger.error(f"同步推送状态到规则 {sync_rule_id} 时出错: {str(e)}")
                    continue
        
        session.commit()

        await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id), link_preview=False)

        status = "启用" if rule.enable_push else "禁用"
        await event.answer(f'已{status}推送功能')
        
    except Exception as e:
        session.rollback()
        logger.error(f"切换推送状态时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer('处理请求时出错，请检查日志')



async def callback_add_push_channel(event, rule_id, session, message, data):
    """处理添加推送配置的回调"""
    try:
        # 获取规则
        rule = session.query(ForwardRule).get(int(rule_id))
        if not rule:
            await event.answer('规则不存在')
            return
            
        # 检查是否频道消息
        if isinstance(event.chat, types.Channel):
            # 检查是否是管理员
            if not await is_admin(event):
                await event.answer('只有管理员可以修改设置')
                return
            user_id = os.getenv('USER_ID')
        else:
            user_id = event.sender_id

        # 设置用户状态
        chat_id = abs(event.chat_id)
        state = f"add_push_channel:{rule_id}"
        
        logger.info(f"准备设置状态 - user_id: {user_id}, chat_id: {chat_id}, state: {state}")
        state_manager.set_state(user_id, chat_id, state, message, state_type="push")
        
        # 启动超时取消任务
        asyncio.create_task(cancel_state_after_timeout(user_id, chat_id))
        
        await message.edit(
            f"请发送推送配置\n"
            f"5分钟内未设置将自动取消",
            buttons=[[Button.inline("取消", f"cancel_add_push_channel:{rule_id}")]]
        )
        
    except Exception as e:
        session.rollback()
        logger.error(f"添加推送配置时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer('处理请求时出错，请检查日志')

async def callback_cancel_add_push_channel(event, rule_id, session, message, data):
    """取消添加推送配置"""
    try:
        rule_id = data.split(':')[1]
        rule = session.query(ForwardRule).get(int(rule_id))
        if not rule:
            await event.answer('规则不存在')
            return
            
        # 清除状态
        if isinstance(event.chat, types.Channel):
            user_id = os.getenv('USER_ID')
        else:
            user_id = event.sender_id
            
        chat_id = abs(event.chat_id)
        state_manager.clear_state(user_id, chat_id)

        await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id), link_preview=False)
        await event.answer("已取消添加推送配置")
        
    except Exception as e:
        logger.error(f"取消添加推送配置时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer('处理请求时出错，请检查日志')

async def cancel_state_after_timeout(user_id: int, chat_id: int, timeout_minutes: int = 5):
    """在指定时间后自动取消状态"""
    await asyncio.sleep(timeout_minutes * 60)
    current_state, _, _ = state_manager.get_state(user_id, chat_id)
    if current_state:  # 只有当状态还存在时才清除
        logger.info(f"状态超时自动取消 - user_id: {user_id}, chat_id: {chat_id}")
        state_manager.clear_state(user_id, chat_id)

async def callback_toggle_push_config(event, config_id, session, message, data):
    """处理点击推送配置的回调"""
    try:

        config = session.query(PushConfig).get(int(config_id))
        if not config:
            await event.answer("推送配置不存在")
            return

        await event.edit(
            f"推送配置: `{config.push_channel}`\n",
            buttons=await create_push_config_details_buttons(config.id)
        )
        
    except Exception as e:
        logger.error(f"显示推送配置详情时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer("处理请求时出错，请检查日志")

async def callback_toggle_push_config_status(event, config_id, session, message, data):
    """处理切换推送配置状态的回调"""
    try:
        config = session.query(PushConfig).get(int(config_id))
        if not config:
            await event.answer("推送配置不存在")
            return
        
        rule_id = config.rule_id
        push_channel = config.push_channel
        
        config.enable_push_channel = not config.enable_push_channel
        
        # 获取规则对象
        rule = session.query(ForwardRule).get(int(rule_id))
        
        # 检查是否启用了同步功能
        if rule and rule.enable_sync:
            logger.info(f"规则 {rule.id} 启用了同步功能，正在同步推送配置状态到关联规则")
            
            # 获取需要同步的规则列表
            sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            
            # 为每个同步规则更新相同推送频道的状态
            for sync_rule in sync_rules:
                sync_rule_id = sync_rule.sync_rule_id
                logger.info(f"正在同步规则 {sync_rule_id} 的推送频道 {push_channel} 状态")
                
                # 查找目标规则的相同推送频道配置
                target_config = session.query(PushConfig).filter_by(
                    rule_id=sync_rule_id, 
                    push_channel=push_channel
                ).first()
                
                if not target_config:
                    logger.warning(f"同步目标规则 {sync_rule_id} 不存在推送频道 {push_channel}，跳过")
                    continue
                
                try:
                    # 更新目标规则推送配置的状态
                    target_config.enable_push_channel = config.enable_push_channel
                    logger.info(f"已更新规则 {sync_rule_id} 的推送频道 {push_channel} 状态为 {config.enable_push_channel}")
                except Exception as e:
                    logger.error(f"更新规则 {sync_rule_id} 的推送配置状态时出错: {str(e)}")
                    continue
        
        session.commit()

        await event.edit(
            f"推送配置: `{config.push_channel}`\n",
            buttons=await create_push_config_details_buttons(config.id)
        )
        
        status = "启用" if config.enable_push_channel else "禁用"
        await event.answer(f"已{status}推送配置")
        
    except Exception as e:
        session.rollback()
        logger.error(f"切换推送配置状态时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer("处理请求时出错，请检查日志")

async def callback_delete_push_config(event, config_id, session, message, data):
    """处理删除推送配置的回调"""
    try:
        config = session.query(PushConfig).get(int(config_id))
        if not config:
            await event.answer("推送配置不存在")
            return
        
        rule_id = config.rule_id
        push_channel = config.push_channel
        
        # 获取规则对象
        rule = session.query(ForwardRule).get(int(rule_id))
        
        # 检查是否启用了同步功能
        if rule and rule.enable_sync:
            logger.info(f"规则 {rule.id} 启用了同步功能，正在同步删除推送配置到关联规则")
            
            # 获取需要同步的规则列表
            sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            
            # 为每个同步规则删除相同的推送配置
            for sync_rule in sync_rules:
                sync_rule_id = sync_rule.sync_rule_id
                logger.info(f"正在同步删除规则 {sync_rule_id} 的推送频道 {push_channel}")
                
                # 查找目标规则的相同推送频道配置
                target_config = session.query(PushConfig).filter_by(
                    rule_id=sync_rule_id, 
                    push_channel=push_channel
                ).first()
                
                if not target_config:
                    logger.warning(f"同步目标规则 {sync_rule_id} 不存在推送频道 {push_channel}，跳过")
                    continue
                
                try:
                    # 删除目标规则的推送配置
                    session.delete(target_config)
                    logger.info(f"已删除规则 {sync_rule_id} 的推送频道 {push_channel}")
                except Exception as e:
                    logger.error(f"删除规则 {sync_rule_id} 的推送配置时出错: {str(e)}")
                    continue
        
        # 删除配置
        session.delete(config)
        session.commit()
        
        await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id), link_preview=False)
        await event.answer("已删除推送配置")
        
    except Exception as e:
        session.rollback()
        logger.error(f"删除推送配置时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer("处理请求时出错，请检查日志")

async def callback_push_page(event, rule_id_data, session, message, data):
    """处理推送设置页面翻页的回调"""
    try:
        # 解析数据
        parts = rule_id_data.split(":")
        if len(parts) != 2:
            await event.answer("数据格式错误")
            return
            
        rule_id = int(parts[0])
        page = int(parts[1])

        await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id, page), link_preview=False)
        await event.answer(f"第 {page+1} 页")
        
    except Exception as e:
        logger.error(f"处理推送设置翻页时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer("处理请求时出错，请检查日志")

async def callback_toggle_enable_only_push(event, rule_id, session, message, data):
    """处理切换只转发到推送配置的回调"""
    try:
        rule = session.query(ForwardRule).get(int(rule_id))
       
        rule.enable_only_push = not rule.enable_only_push
        
        # 检查是否启用了同步功能
        if rule.enable_sync:
            logger.info(f"规则 {rule.id} 启用了同步功能，正在同步'只转发到推送配置'设置到关联规则")
            # 获取需要同步的规则列表
            sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            
            # 为每个同步规则应用相同的设置
            for sync_rule in sync_rules:
                sync_rule_id = sync_rule.sync_rule_id
                logger.info(f"正在同步'只转发到推送配置'设置到规则 {sync_rule_id}")
                
                # 获取同步目标规则
                target_rule = session.query(ForwardRule).get(sync_rule_id)
                if not target_rule:
                    logger.warning(f"同步目标规则 {sync_rule_id} 不存在，跳过")
                    continue
                
                try:
                    # 更新同步目标规则的设置
                    target_rule.enable_only_push = rule.enable_only_push
                    logger.info(f"同步规则 {sync_rule_id} 的'只转发到推送配置'设置已更新为 {rule.enable_only_push}")
                except Exception as e:
                    logger.error(f"同步'只转发到推送配置'设置到规则 {sync_rule_id} 时出错: {str(e)}")
                    continue
        
        session.commit()
        
        await event.edit(PUSH_SETTINGS_TEXT, buttons=await create_push_settings_buttons(rule_id), link_preview=False)

        status = "启用" if rule.enable_only_push else "禁用"
        await event.answer(f'已{status}只转发到推送配置')
        
    except Exception as e:
        session.rollback()
        logger.error(f"切换只转发到推送配置状态时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer('处理请求时出错，请检查日志')

async def callback_toggle_media_send_mode(event, config_id, session, message, data):
    """处理切换媒体发送方式的回调"""
    try:
        config = session.query(PushConfig).get(int(config_id))
        if not config:
            await event.answer("推送配置不存在")
            return
            
        rule_id = config.rule_id
        
        # 切换媒体发送模式
        if config.media_send_mode == "Single":
            config.media_send_mode = "Multiple"
            new_mode = "全部"
        else:
            config.media_send_mode = "Single"
            new_mode = "单个"
            
        session.commit()
        
        # 检查是否启用了同步功能
        rule = session.query(ForwardRule).get(int(rule_id))
        if rule and rule.enable_sync:
            logger.info(f"规则 {rule.id} 启用了同步功能，正在同步媒体发送方式到关联规则的推送配置")
            # 获取需要同步的规则列表
            sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            
            # 获取当前推送配置的推送频道
            push_channel = config.push_channel
            
            # 为每个同步规则查找相同推送频道的配置并应用相同设置
            for sync_rule in sync_rules:
                sync_rule_id = sync_rule.sync_rule_id
                logger.info(f"正在同步媒体发送方式到规则 {sync_rule_id} 的相同推送频道")
                
                # 查找目标规则下的相同推送频道配置
                target_config = session.query(PushConfig).filter_by(rule_id=sync_rule_id, push_channel=push_channel).first()
                if not target_config:
                    logger.warning(f"同步目标规则 {sync_rule_id} 不存在相同推送频道 {push_channel}，跳过")
                    continue
                
                try:
                    # 更新同步目标配置的媒体发送方式
                    target_config.media_send_mode = config.media_send_mode
                    logger.info(f"同步规则 {sync_rule_id} 的推送频道 {push_channel} 的媒体发送方式已更新为 {config.media_send_mode}")
                except Exception as e:
                    logger.error(f"同步媒体发送方式到规则 {sync_rule_id} 时出错: {str(e)}")
                    continue
                    
            session.commit()
        
        # 更新界面
        await event.edit(
            f"推送配置: `{config.push_channel}`\n",
            buttons=await create_push_config_details_buttons(config.id)
        )
        
        await event.answer(f"已设置媒体发送方式为: {new_mode}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"切换媒体发送方式时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await event.answer("处理请求时出错，请检查日志")
