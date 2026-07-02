# -*- coding: utf-8 -*-
"""
因子数据缺失插补系统
Factor Missing Data Imputation System
"""

__version__ = "2.0.0"
__author__ = "Factor Missing Team"
__description__ = "专业级因子数据缺失插补系统 - 优化版"


# 版本信息
def get_version():
    """获取版本信息"""
    return __version__


def get_info():
    """获取系统信息"""
    return {
        "version": __version__,
        "author": __author__,
        "description": __description__,
    }


__all__ = ["get_version", "get_info"]
