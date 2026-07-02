"""
Factor Neutralizer - 因子中性化处理工具

用于对量化因子进行行业中性化、市值中性化等处理。
"""

__version__ = "2.1.0"
__author__ = "StormstoutLau"

from .core.FactorNeutralizer import FactorNeutralizer

__all__ = ["FactorNeutralizer"]
