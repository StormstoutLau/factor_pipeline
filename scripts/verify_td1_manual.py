# -*- coding: utf-8 -*-
"""TD-1 手工校验脚本 — Factor_Trading_v3.0 子包化 + data_bridge.py importlib 清理

校验:
  1. Factor_Trading_v3_0 包可从任意目录导入
  2. DataLoaderV3 正确解析为 Factor_Trading_v3_0.core.data_v3.DataLoaderV3
  3. data_bridge.py 无 importlib.util.spec_from_file_location 残留
  4. data_bridge.py 无 _FACTOR_TRADING_PATH / _DATA_V3_PATH / _data_v3_module 残留
  5. data_bridge.py 源码含 from Factor_Trading_v3_0.core.data_v3 import
  6. DataBridge 功能正常 (端到端)
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

print("=" * 70)
print("TD-1 手工校验 — Factor_Trading_v3.0 子包化 + data_bridge.py 清理")
print("=" * 70)

# ── 校验 1: Factor_Trading_v3_0 包可导入 ────────────────────────────
print("\n[1] Factor_Trading_v3_0 包可从任意目录导入")
import Factor_Trading_v3_0
print(f"  __file__: {Factor_Trading_v3_0.__file__}")
print(f"  __version__: {Factor_Trading_v3_0.__version__}")
assert Factor_Trading_v3_0.__version__ == "3.0.0"
print("  PASS")

# ── 校验 2: DataLoaderV3 正确解析 ──────────────────────────────────
print("\n[2] DataLoaderV3 正确解析为 Factor_Trading_v3_0.core.data_v3.DataLoaderV3")
from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3
assert DataLoaderV3.__module__ == "Factor_Trading_v3_0.core.data_v3"
assert DataLoaderV3.__name__ == "DataLoaderV3"
print(f"  module: {DataLoaderV3.__module__}")
print(f"  name: {DataLoaderV3.__name__}")
print("  PASS")

# ── 校验 3: data_bridge.py 无 importlib hack 残留 ──────────────────
print("\n[3] data_bridge.py 无 importlib hack 残留")
from factor_pipeline.backtest import data_bridge

src = inspect.getsource(data_bridge)
assert "spec_from_file_location" not in src, "data_bridge.py 仍有 spec_from_file_location"
assert "module_from_spec" not in src, "data_bridge.py 仍有 module_from_spec"
print("  PASS: 无 spec_from_file_location / module_from_spec")

# ── 校验 4: data_bridge.py 无旧常量残留 ────────────────────────────
print("\n[4] data_bridge.py 无 _FACTOR_TRADING_PATH / _DATA_V3_PATH / _data_v3_module 残留")
assert not hasattr(data_bridge, '_FACTOR_TRADING_PATH'), "仍有 _FACTOR_TRADING_PATH"
assert not hasattr(data_bridge, '_DATA_V3_PATH'), "仍有 _DATA_V3_PATH"
assert not hasattr(data_bridge, '_data_v3_module'), "仍有 _data_v3_module"
assert not hasattr(data_bridge, '_spec'), "仍有 _spec"
print("  PASS: 4 个旧常量均已删除")

# ── 校验 5: data_bridge.py 源码含直接导入 ──────────────────────────
print("\n[5] data_bridge.py 源码含 from Factor_Trading_v3_0.core.data_v3 import")
assert "from Factor_Trading_v3_0.core.data_v3 import" in src, "源码缺少直接导入"
print("  PASS: 含直接导入语句")

# ── 校验 6: DataBridge 功能正常 (端到端) ────────────────────────────
print("\n[6] DataBridge 功能正常 (端到端)")
import numpy as np
import pandas as pd

np.random.seed(42)
n_stocks, n_dates = 10, 30
stocks = [f"S{i:03d}" for i in range(n_stocks)]
dates = pd.date_range("2024-01-01", periods=n_dates, freq="D")

# 构造因子数据 (n_stocks, n_dates)
factor_data = {
    "f1": pd.DataFrame(np.random.randn(n_stocks, n_dates), index=stocks, columns=dates),
}
price_data = pd.DataFrame(
    100 + np.cumsum(np.random.randn(n_stocks, n_dates) * 0.5, axis=1),
    index=stocks, columns=dates,
)

bridge = data_bridge.DataBridge()
dl = bridge.create_dataloader(factor_data, price_data)

assert dl.n_dates == n_dates, f"n_dates 不匹配: {dl.n_dates} != {n_dates}"
assert dl.n_stocks == n_stocks, f"n_stocks 不匹配: {dl.n_stocks} != {n_stocks}"
assert "f1" in dl.factor_data, "因子 f1 未加载"
assert dl.factor_data["f1"].shape == (n_dates, n_stocks), \
    f"因子 shape 错误: {dl.factor_data['f1'].shape} != ({n_dates}, {n_stocks})"
assert "close" in dl.price_data, "close 未加载"
assert dl.price_data["close"].shape == (n_dates, n_stocks)

print(f"  n_dates: {dl.n_dates}")
print(f"  n_stocks: {dl.n_stocks}")
print(f"  factor_data['f1'].shape: {dl.factor_data['f1'].shape}")
print(f"  price_data['close'].shape: {dl.price_data['close'].shape}")
print("  PASS: DataBridge 端到端功能正常")

print("\n" + "=" * 70)
print("TD-1 手工校验全部通过 (6/6)")
print("=" * 70)
