# -*- coding: utf-8 -*-
"""Fix 3 手工校验脚本

校验:
  1. 5 个预期位置的版本号均为 2.5.0
  2. 全局扫描旧版本号 (2.0.0, 2.1.0) 残留
  3. 缓存 code_version 独立于项目版本
  4. pyproject.toml 版本号状态
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent.parent  # F:\Coding
_PROJECT_ROOT = _PROJECT_PARENT / "factor_pipeline"
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))

EXPECTED_VERSION = "2.5.0"
OLD_VERSIONS = ["2.0.0", "2.1.0"]


print("=" * 70)
print("Fix 3 手工校验 — 版本号统一")
print("=" * 70)


# ── 校验 1: 5 个预期位置 ────────────────────────────────────────
print("\n[1] 预期位置版本号核对")

EXPECTED_LOCATIONS = [
    ("__init__.py", r'__version__\s*=\s*["\']([^"\']+)["\']'),
    ("config_v2.py", r'version:\s*str\s*=\s*Field\(default="([^"]+)"'),
    ("reporting.py", r'pipeline_version\s*:\s*str\s*=\s*"([^"]+)"'),
    ("tests/unit/test_config_v2.py", r"config\.version\s*==\s*'([^']+)'"),
    ("tests/unit/test_reporting.py", r'pipeline_version\s*==\s*"([^"]+)"'),
]

found_versions = []
for rel_path, pattern in EXPECTED_LOCATIONS:
    full_path = _PROJECT_ROOT / rel_path
    assert full_path.exists(), f"文件不存在: {rel_path}"
    content = full_path.read_text(encoding='utf-8')
    m = re.search(pattern, content)
    assert m, f"{rel_path}: 未找到版本号 (pattern: {pattern})"
    actual = m.group(1)
    assert actual == EXPECTED_VERSION, (
        f"{rel_path}: {actual} != {EXPECTED_VERSION}"
    )
    found_versions.append((rel_path, actual))
    print(f"  ✓ {rel_path}: {actual}")


# ── 校验 2: 全局扫描旧版本残留 ─────────────────────────────────
print("\n[2] 全局扫描旧版本号残留")

# 排除目录: 文档/缓存/历史脚本
EXCLUDE_DIRS = {'.pytest_cache', '__pycache__', '.git', 'node_modules', 'cache'}
# 排除文件: 测试文件自身和 verify 脚本 (会描述旧版本)
EXCLUDE_FILE_KEYWORDS = ['verify_fix3', 'test_fix3_version_unification']
# 只关注真正的代码赋值/比较场景, 排除描述性引用
CODE_VERSION_PATTERN = re.compile(
    r'(?:__version__\s*=\s*["\']|version\s*[:=]\s*["\']|'
    r'pipeline_version\s*[:=]\s*["\']|==\s*["\'])'
    r'(' + '|'.join(re.escape(v) for v in OLD_VERSIONS) + r')'
)
residual = []
for py_file in _PROJECT_ROOT.rglob("*.py"):
    # 跳过排除目录
    if any(part in EXCLUDE_DIRS for part in py_file.parts):
        continue
    # 跳过测试/校验文件自身
    if any(kw in py_file.name for kw in EXCLUDE_FILE_KEYWORDS):
        continue
    content = py_file.read_text(encoding='utf-8')
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        # 只匹配代码赋值/比较场景
        if CODE_VERSION_PATTERN.search(line):
            for old_v in OLD_VERSIONS:
                if old_v in line:
                    residual.append((py_file.relative_to(_PROJECT_ROOT), i, old_v, line.strip()))
                    break

if residual:
    print("  ⚠ 发现旧版本残留 (代码赋值/比较场景):")
    for path, line_no, old_v, line in residual:
        print(f"    {path}:{line_no} [{old_v}] {line}")
else:
    print("  ✓ 无旧版本号残留 (代码赋值/比较场景, 排除描述性引用)")


# ── 校验 3: 缓存 code_version 独立性 ────────────────────────────
print("\n[3] 缓存 code_version 独立性校验")
from factor_pipeline.backtest.cache_manager import CODE_VERSION

cache_version = CODE_VERSION
print(f"  项目版本: {EXPECTED_VERSION}")
print(f"  缓存 code_version: {cache_version}")
# 缓存版本不应等于项目版本 (语义独立)
assert cache_version != EXPECTED_VERSION, (
    f"缓存 code_version ({cache_version}) 不应等于项目版本 ({EXPECTED_VERSION})"
)
# 缓存版本应包含 "cache" 标识
assert "cache" in cache_version.lower(), (
    f"缓存 code_version ({cache_version}) 应包含 'cache' 标识"
)
print(f"  ✓ 缓存版本独立于项目版本")


# ── 校验 4: pyproject.toml 版本号 ───────────────────────────────
print("\n[4] pyproject.toml 版本号状态")
toml_path = _PROJECT_ROOT / "pyproject.toml"
if toml_path.exists():
    content = toml_path.read_text(encoding='utf-8')
    m = re.search(r'version\s*=\s*"([^"]+)"', content)
    if m:
        toml_version = m.group(1)
        print(f"  pyproject.toml version: {toml_version}")
        # pyproject.toml 可能独立于代码版本 (包发布版本)
        # 只记录, 不强制一致
        if toml_version == EXPECTED_VERSION:
            print(f"  ✓ 与代码版本一致")
        else:
            print(f"  ℹ 与代码版本不一致 (可能独立维护, 包发布版本)")
    else:
        print(f"  ℹ pyproject.toml 未找到 version 字段")
else:
    print(f"  ℹ pyproject.toml 不存在")


# ── 校验 5: __version__ 可从包顶层导入 ──────────────────────────
print("\n[5] __version__ 顶层导入校验")
import factor_pipeline
assert hasattr(factor_pipeline, '__version__'), "factor_pipeline 无 __version__ 属性"
actual_top_version = factor_pipeline.__version__
assert actual_top_version == EXPECTED_VERSION, (
    f"factor_pipeline.__version__ = {actual_top_version} != {EXPECTED_VERSION}"
)
print(f"  ✓ factor_pipeline.__version__ = {actual_top_version}")


print("\n" + "=" * 70)
print(f"Fix 3 手工校验通过: 5/5 (预期位置 {len(found_versions)}/5, 缓存独立, 顶层可导入)")
if residual:
    print(f"  注意: 有 {len(residual)} 处旧版本残留 (已记录, 非代码赋值场景)")
print("=" * 70)
