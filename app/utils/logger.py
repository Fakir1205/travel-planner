"""
日志标准化模块
使用loguru提供增强日志
"""
import sys
from loguru import logger
from app.config import settings
def setup_logger():
    """配置logger"""
    # 先移除基础log
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        level="DEBUG" if settings.debug else "INFO"
    )
    logger.add(
        "logs/app.log",
        rotation="500 MB",
        retention="5 days",
        compression="zip",
        serialize=True,
        level="INFO"
    )
    logger.add(
        "logs/error.log",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        level="ERROR",
        backtrace=True,
        diagnose=True,
    )
    logger.info("日志配置成功")
    return logger
app_logger = setup_logger()