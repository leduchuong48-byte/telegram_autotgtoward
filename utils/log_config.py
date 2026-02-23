import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

def setup_logging():
    """
    配置日志系统，同时输出到控制台与日志文件。
    """
    # 加载环境变量
    load_dotenv()
    
    # 创建根日志记录器
    root_logger = logging.getLogger()
    
    # 设置日志级别 - 默认使用INFO级别
    root_logger.setLevel(logging.INFO)
    
    log_path = os.getenv("LOG_FILE_PATH") or os.getenv("LOG_FILE") or "./logs/telegram_forwarder.log"
    log_path = os.path.abspath(log_path)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    has_stream = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    has_file = any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == log_path
        for handler in root_logger.handlers
    )

    if not has_stream:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if not has_file:
        max_bytes = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024))
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", 3))
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 返回配置的日志记录器
    return root_logger 
