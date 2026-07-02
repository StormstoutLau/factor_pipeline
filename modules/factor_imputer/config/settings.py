# -*- coding: utf-8 -*-
"""
配置管理模块
提供统一的配置管理
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DataConfig:
    """数据配置"""

    base_path: Path = Path("E:/Ashare_data/")
    stock_names_file: str = "stock_names.pkl"
    market_cap_file: str = "market_cap_df.pkl"
    suspend_data_file: str = "stock_suspend_df.pkl"
    industry_file: str = "stock_sw_industry.pkl"
    index_constituents_file: str = "index_constituents.pkl"
    list_date_file: str = "list_date_df.pkl"

    @property
    def stock_names_path(self) -> Path:
        return self.base_path / self.stock_names_file

    @property
    def market_cap_path(self) -> Path:
        return self.base_path / self.market_cap_file

    @property
    def suspend_data_path(self) -> Path:
        return self.base_path / self.suspend_data_file

    @property
    def industry_path(self) -> Path:
        return self.base_path / self.industry_file

    @property
    def index_constituents_path(self) -> Path:
        return self.base_path / self.index_constituents_file

    @property
    def list_date_path(self) -> Path:
        return self.base_path / self.list_date_file


@dataclass(frozen=True)
class ImputationConfig:
    """插补配置"""

    window_size: int = 20
    min_samples: int = 5
    max_missing_rate: float = 0.3
    cross_sectional_method: str = "cross_sectional_median"
    time_series_method: str = "rolling_ffill"
    model_method: str = "rolling_rf"
    n_estimators: int = 50
    max_depth: int = 5
    random_state: Optional[int] = None

    def validate(self) -> None:
        """验证配置有效性"""
        if self.window_size < self.min_samples:
            raise ValueError(f"window_size ({self.window_size}) must be >= min_samples ({self.min_samples})")
        if not 0 <= self.max_missing_rate <= 1:
            raise ValueError(f"max_missing_rate ({self.max_missing_rate}) must be in [0, 1]")
        if self.window_size < 1:
            raise ValueError(f"window_size ({self.window_size}) must be >= 1")
        if self.min_samples < 1:
            raise ValueError(f"min_samples ({self.min_samples}) must be >= 1")
        if self.n_estimators < 1:
            raise ValueError(f"n_estimators ({self.n_estimators}) must be >= 1")
        if self.max_depth < 1:
            raise ValueError(f"max_depth ({self.max_depth}) must be >= 1")


@dataclass(frozen=True)
class PerformanceConfig:
    """性能配置"""

    parallel_workers: int = 4
    chunk_size: int = 1000
    use_numba: bool = False
    cache_enabled: bool = True
    cache_size: int = 1000


@dataclass(frozen=True)
class MonitoringConfig:
    """监控配置"""

    enabled: bool = True
    metrics_port: int = 9090
    log_level: str = "INFO"


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self._configs: Dict[str, Any] = {}
        self._load_defaults()

    def _load_defaults(self):
        """加载默认配置"""
        self._configs["data"] = DataConfig()
        self._configs["imputation"] = ImputationConfig()
        self._configs["performance"] = PerformanceConfig()
        self._configs["monitoring"] = MonitoringConfig()

    def get(self, name: str) -> Any:
        """获取配置"""
        return self._configs.get(name)

    def set(self, name: str, config: Any) -> None:
        """设置配置"""
        self._configs[name] = config

    def validate_all(self) -> None:
        """验证所有配置"""
        for name, config in self._configs.items():
            if hasattr(config, "validate"):
                try:
                    config.validate()
                except ValueError as e:
                    raise ValueError(f"配置 '{name}' 验证失败: {e}")


# 全局配置实例
_config_manager = ConfigManager()


def get_config(name: str = "imputation") -> Any:
    """获取全局配置"""
    return _config_manager.get(name)


def set_config(name: str, config: Any) -> None:
    """设置全局配置"""
    _config_manager.set(name, config)
