# -*- coding: utf-8 -*-
"""v3.8.1 校准配置（frozen + config_hash）。

设计依据：DESIGN §14；实施依据：EXECUTION §2.1。
v3.8.1：删 ``tau_max_minutes``，新增 ``minute_start/minute_end``
（分钟层窗口）与 ``lambda_min_days/adv_window_days``（λ 反解口径），
字段数 16 -> 19。
"""
import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = ["CalibrationConfig"]


@dataclass(frozen=True)
class CalibrationConfig(object):
    """校准全参数；构建后用 ``dataclasses.replace`` 生成变体。"""

    data_root: str = r"E:\Ashare_data"
    minute_root: Optional[str] = r"E:\Level 1 Data"
    sample_start: str = "2020-01-31"
    sample_end: str = "2026-01-31"
    minute_start: str = "2020-01-31"       # v3.8.1：分钟层起点
    minute_end: str = "2023-03-31"         # v3.8.1：分钟层终点（实际数据止 2023-03-30）
    participation_grid: Tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05)
    sigma_clip: Tuple[float, float] = (0.005, 0.20)
    bvc_sigma_bars: int = 20
    block_size_mode: str = "auto"          # auto | sqrt | iid（v3.8.1 仅 auto 可用）
    windows: Tuple[int, ...] = (24, 36, 48, 60)
    kappa: float = 1.5
    p_cap: float = 0.10
    d_max: int = 5
    default_horizon: int = 20
    lambda_min_days: int = 10              # v3.8.1：每股×月最小有效日数
    adv_window_days: int = 21              # v3.8.1：ADV 均值窗（与脚本 rolling(21) 对齐）
    lambda_p_threshold: float = 0.05
    seed: int = 20261118

    def config_hash(self) -> str:
        """sha256(canonical_json(asdict(self)))；排序键、无时间戳。"""
        payload = json.dumps(
            dataclasses.asdict(self), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
