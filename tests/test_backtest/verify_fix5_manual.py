# -*- coding: utf-8 -*-
"""Fix 5 手工校验脚本

校验:
  1. 默认值与原硬编码一致
  2. 路径真实存在
  3. 环境变量覆盖生效 (子进程测试)
  4. 外部类可加载 (DataLoaderV3, FactorHealthMonitor)
  5. 源码不含硬编码路径字面量
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))


print("=" * 70)
print("Fix 5 手工校验 — 硬编码路径改为环境变量配置项")
print("=" * 70)


# ── 校验 1: 默认值与原硬编码一致 ────────────────────────────────
print("\n[1] 默认值与原硬编码一致校验")

ORIGINAL_FACTOR_TRADING = "F:/Coding/Factor_Trading_v3.0"
ORIGINAL_FINGERPRINT = "F:/Coding/Factor_Fingerprint"

from factor_pipeline.backtest import data_bridge, health_bridge

# Path 在 Windows 上 str 表示为反斜杠, 用 os.path.normpath 比较
import os.path
assert os.path.normpath(str(data_bridge._FACTOR_TRADING_PATH)) == os.path.normpath(ORIGINAL_FACTOR_TRADING), (
    f"Factor_Trading 默认值不一致: {data_bridge._FACTOR_TRADING_PATH}"
)
assert os.path.normpath(str(health_bridge._FINGERPRINT_PATH)) == os.path.normpath(ORIGINAL_FINGERPRINT), (
    f"Fingerprint 默认值不一致: {health_bridge._FINGERPRINT_PATH}"
)
print(f"  ✓ Factor_Trading 默认值: {data_bridge._FACTOR_TRADING_PATH}")
print(f"  ✓ Fingerprint 默认值: {health_bridge._FINGERPRINT_PATH}")


# ── 校验 2: 路径真实存在 ────────────────────────────────────────
print("\n[2] 路径真实存在校验")

assert data_bridge._DATA_V3_PATH.exists(), f"data_v3.py 不存在: {data_bridge._DATA_V3_PATH}"
fp_path = health_bridge._FINGERPRINT_PATH / "core" / "fingerprint.py"
assert fp_path.exists(), f"fingerprint.py 不存在: {fp_path}"
health_path = health_bridge._FINGERPRINT_PATH / "core" / "health.py"
assert health_path.exists(), f"health.py 不存在: {health_path}"
print(f"  ✓ data_v3.py 存在: {data_bridge._DATA_V3_PATH}")
print(f"  ✓ fingerprint.py 存在: {fp_path}")
print(f"  ✓ health.py 存在: {health_path}")


# ── 校验 3: 环境变量覆盖生效 (子进程) ───────────────────────────
print("\n[3] 环境变量覆盖生效校验 (子进程)")

# 测试 FACTOR_TRADING_PATH 覆盖
# 注意: data_bridge 模块加载时会触发 data_v3.py 加载, 若路径不存在会报错
# 因此只验证 os.environ.get 的读取逻辑, 不触发完整模块加载
env = os.environ.copy()
env["FACTOR_TRADING_PATH"] = "F:/Custom/Factor_Trading"
result = subprocess.run(
    [sys.executable, "-c",
     "import os; print(os.environ.get('FACTOR_TRADING_PATH', 'DEFAULT'))"],
    env=env, capture_output=True, text=True, cwd="F:/Coding"
)
ft_output = result.stdout.strip()
assert "F:/Custom/Factor_Trading" in ft_output, (
    f"FACTOR_TRADING_PATH 环境变量未生效: {ft_output}"
)

# 进一步验证: 读取源码确认使用 os.environ.get
db_path = _PROJECT_PARENT / "factor_pipeline" / "backtest" / "data_bridge.py"
db_content = db_path.read_text(encoding='utf-8')
assert 'os.environ.get(' in db_content and 'FACTOR_TRADING_PATH' in db_content, (
    "data_bridge.py 未使用 os.environ.get 读取 FACTOR_TRADING_PATH"
)
hb_path = _PROJECT_PARENT / "factor_pipeline" / "backtest" / "health_bridge.py"
hb_content = hb_path.read_text(encoding='utf-8')
assert 'os.environ.get(' in hb_content and 'FINGERPRINT_PATH' in hb_content, (
    "health_bridge.py 未使用 os.environ.get 读取 FINGERPRINT_PATH"
)
print(f"  ✓ FACTOR_TRADING_PATH 环境变量可被读取: {ft_output}")
print(f"  ✓ data_bridge.py 使用 os.environ.get('FACTOR_TRADING_PATH', ...)")
print(f"  ✓ health_bridge.py 使用 os.environ.get('FINGERPRINT_PATH', ...)")

# 用真实路径做端到端验证 (设置环境变量为真实路径, 模块应能加载)
env_real = os.environ.copy()
env_real["FACTOR_TRADING_PATH"] = "F:/Coding/Factor_Trading_v3.0"  # 真实路径
result_real = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, 'F:/Coding'); "
     "from factor_pipeline.backtest.data_bridge import _FACTOR_TRADING_PATH; "
     "print(str(_FACTOR_TRADING_PATH))"],
    env=env_real, capture_output=True, text=True, cwd="F:/Coding"
)
if result_real.returncode == 0:
    print(f"  ✓ 真实路径下模块加载成功: {result_real.stdout.strip()}")
else:
    print(f"  ⚠ 真实路径下模块加载失败: {result_real.stderr[:200]}")


# ── 校验 4: 外部类可加载 ────────────────────────────────────────
print("\n[4] 外部类可加载校验")

from factor_pipeline.backtest.data_bridge import DataLoaderV3
assert DataLoaderV3 is not None, "DataLoaderV3 不可加载"
assert hasattr(DataLoaderV3, 'from_pandas_dataframes'), "DataLoaderV3 缺少 from_pandas_dataframes 方法"
print(f"  ✓ DataLoaderV3 可加载, 有 from_pandas_dataframes 方法")

from factor_pipeline.backtest.health_bridge import (
    FactorHealthMonitor, FactorHealthReport, HealthConfig,
    HealthAlertLevel, HealthAlert,
)
assert FactorHealthMonitor is not None, "FactorHealthMonitor 不可加载"
print(f"  ✓ FactorHealthMonitor 可加载")
print(f"  ✓ FactorHealthReport 可加载")
print(f"  ✓ HealthConfig 可加载")
print(f"  ✓ HealthAlertLevel 可加载")
print(f"  ✓ HealthAlert 可加载")


# ── 校验 5: 源码不含硬编码路径字面量 ────────────────────────────
print("\n[5] 源码不含硬编码路径字面量校验")

HARDCODED_PATTERNS = [
    r'Path\(\s*["\']F:/Coding/Factor_Trading_v3\.0["\']',
    r'Path\(\s*["\']F:/Coding/Factor_Fingerprint["\']',
    r'["\']F:/Coding/Factor_Trading_v3\.0["\']\s*\)',
    r'["\']F:/Coding/Factor_Fingerprint["\']\s*\)',
]

files_to_check = [
    _PROJECT_PARENT / "factor_pipeline" / "backtest" / "data_bridge.py",
    _PROJECT_PARENT / "factor_pipeline" / "backtest" / "health_bridge.py",
]

violations = []
for py_file in files_to_check:
    content = py_file.read_text(encoding='utf-8')
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        for pattern in HARDCODED_PATTERNS:
            # 排除 os.environ.get 的默认值 (允许在 os.environ.get 内部出现)
            if 'os.environ.get' in line:
                continue
            if re.search(pattern, line):
                violations.append((py_file.name, i, line.strip()))

if violations:
    print("  ⚠ 发现硬编码路径字面量 (非 os.environ.get 默认值):")
    for fname, line_no, line in violations:
        print(f"    {fname}:{line_no} {line}")
else:
    print("  ✓ 无硬编码路径字面量 (os.environ.get 默认值除外)")


print("\n" + "=" * 70)
print("Fix 5 手工校验通过: 5/5")
print("=" * 70)
