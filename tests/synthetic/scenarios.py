# -*- coding: utf-8 -*-
"""v3.9.0 内置合成场景（DESIGN §4.3）。"""
from .panel import PanelSpec

__all__ = ["SCENARIOS"]

SCENARIOS = {
    "clean": PanelSpec(),
    "limit_heavy": PanelSpec(limit_up_ratio=0.08, limit_down_ratio=0.08),
    "suspend_gap": PanelSpec(suspend_ratio=0.10, suspend_len=5),
    "st_mixed": PanelSpec(st_ratio=0.10),
    "stale_factor": PanelSpec(loaded_lag_days=5, factor_missing=0.05),
    "adj_jump": PanelSpec(adj_jump_days=(40, 41)),
}
