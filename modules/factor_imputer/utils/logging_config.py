# -*- coding: utf-8 -*-
"""
日志配置模块
提供统一的日志系统
"""

import logging
import sys
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str = "INFO", log_file: Optional[str] = None, logger_name: str = "factor_imputer"
) -> logging.Logger:
    """
    设置日志系统

    Parameters:
    -----------
    level : str
        日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    log_file : Optional[str]
        日志文件路径
    logger_name : str
        日志器名称

    Returns:
    --------
    logger : logging.Logger
        配置好的日志器
    """
    # 解析日志级别
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level = level_map.get(level.upper(), logging.INFO)

    # 创建日志器
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # 避免重复添加处理器
    if logger.handlers:
        logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "factor_imputer") -> logging.Logger:
    """
    获取日志器

    Parameters:
    -----------
    name : str
        日志器名称

    Returns:
    --------
    logger : logging.Logger
        日志器实例
    """
    return logging.getLogger(name)
