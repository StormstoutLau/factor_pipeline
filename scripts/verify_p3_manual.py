# -*- coding: utf-8 -*-
"""P3 手工校验脚本 — adapters 重构验证

校验:
  1. NeutralizerAdapter REQUIRED 缺失抛 AdapterImportError
  2. NeutralizerAdapter 正常构造 (factor_neutralizer 已 pip install)
  3. GarchWhiteningAdapter 使用模块级 _arch_model, _get_arch_model_class 已删除
  4. adapters.py 死代码清理 (sm is None / neutralizer_class is None / 'external' 标记)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent  # F:\Coding
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

print("=" * 70)
print("P3 手工校验 — adapters 重构")
print("=" * 70)

# ── 校验 1: NeutralizerAdapter REQUIRED 缺失抛 AdapterImportError ────
print("\n[1] NeutralizerAdapter REQUIRED 缺失抛 AdapterImportError")
from factor_pipeline.adapters import NeutralizerAdapter
from factor_pipeline.exceptions import AdapterImportError

try:
    adapter = NeutralizerAdapter(
        module_path='../NonExistent/Module',
        import_path='does.not.exist',
        class_name='NonExistentClass'
    )
    print("  FAIL: 未抛 AdapterImportError")
    sys.exit(1)
except AdapterImportError as e:
    print(f"  PASS: 抛 AdapterImportError, module_path={e.module_path}")

# ── 校验 2: NeutralizerAdapter 正常构造 ────────────────────────────
print("\n[2] NeutralizerAdapter 正常构造 (factor_neutralizer 已内化)")
adapter = NeutralizerAdapter()
assert adapter.is_fallback_mode == False, "is_fallback_mode 应为 False"
assert adapter._neutralizer_class is not None, "_neutralizer_class 不应为 None"
print(f"  is_fallback_mode = {adapter.is_fallback_mode}")
print(f"  _neutralizer_class = {adapter._neutralizer_class.__name__}")
print("  PASS")

# ── 校验 3: GarchWhiteningAdapter 模块级 _arch_model ────────────────
print("\n[3] GarchWhiteningAdapter 模块级 _arch_model 使用")
from factor_pipeline.adapters import GarchWhiteningAdapter
import factor_pipeline.adapters as adapters_mod

print(f"  HAS_ARCH = {adapters_mod.HAS_ARCH}")
print(f"  _arch_model is None = {adapters_mod._arch_model is None}")
adapter_g = GarchWhiteningAdapter(p=1, q=1)
print(f"  _has_arch = {adapter_g._has_arch}")
print(f"  is_fallback_mode = {adapter_g.is_fallback_mode}")
assert not hasattr(adapter_g, '_get_arch_model_class'), "_get_arch_model_class 方法应已删除"
print("  PASS: _get_arch_model_class 已删除, 使用模块级 _arch_model")

# ── 校验 4: adapters.py 死代码清理 ─────────────────────────────────
print("\n[4] adapters.py 死代码清理检查")
src_path = Path(__file__).resolve().parent.parent / "adapters.py"
src = src_path.read_text(encoding='utf-8')

# sm is None 死代码 (statsmodels 是 REQUIRED)
sm_dead = re.findall(r'if sm is None:', src)
assert len(sm_dead) == 0, f"sm is None 死代码残留: {len(sm_dead)} 处"
print("  PASS: sm is None 死代码已清理")

# _get_arch_model_class 已删除
assert '_get_arch_model_class' not in src, "_get_arch_model_class 残留"
print("  PASS: _get_arch_model_class 已删除")

# neutralizer_class is None 死代码
assert 'neutralizer_class is None' not in src, "neutralizer_class is None 死代码残留"
print("  PASS: neutralizer_class is None 死代码已清理")

# _neutralizer = 'external' 字符串标记
assert "_neutralizer = 'external'" not in src, "_neutralizer = 'external' 字符串标记残留"
print("  PASS: _neutralizer = 'external' 字符串标记已删除")

# ── 校验 5: NeutralizerAdapter is_fallback_mode 永远 False ──────────
print("\n[5] NeutralizerAdapter is_fallback_mode 永远为 False")
adapter_n = NeutralizerAdapter()
assert adapter_n.is_fallback_mode == False
# 模拟 fit 后也应为 False
import pandas as pd
import numpy as np
np.random.seed(42)
fake_data = pd.DataFrame(np.random.randn(20, 3), columns=['A', 'B', 'C'])
adapter_n.fit(fake_data)
assert adapter_n.is_fallback_mode == False, "fit 后 is_fallback_mode 仍应为 False"
print("  PASS: 构造和 fit 后 is_fallback_mode 均为 False")

print("\n" + "=" * 70)
print("P3 手工校验全部通过 (5/5)")
print("=" * 70)
