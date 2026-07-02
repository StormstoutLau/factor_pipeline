# -*- coding: utf-8 -*-
"""Fix Factor_DB internal absolute imports (from query.X → from Factor_DB.query.X)

P1.2: 配合 Factor_DB pip install -e ., 将其内部子包的绝对导入改为
包名限定导入, 避免依赖 sys.path 注入.
"""
import re
import os

PKG = "Factor_DB"
ROOT = r"f:\Coding\Factor_DB"

# 子包列表 (匹配 absolute imports)
SUBPKGS = ["query", "loaders", "adapters", "analytics", "utils", "osint", "benchmarks", "core"]

# 构造正则: ^(\s*)from <subpkg>.(\S+) import  ->  ^\1from Factor_DB.<subpkg>.\2 import
patterns = []
for sub in SUBPKGS:
    # 不匹配已经是 Factor_DB.sub 的
    pat = re.compile(rf'^(\s*)from {sub}\.(\S+) import', re.MULTILINE)
    repl = rf'\1from {PKG}.{sub}.\2 import'
    patterns.append((pat, repl))
    # import sub.X
    pat2 = re.compile(rf'^(\s*)import {sub}\.', re.MULTILINE)
    repl2 = rf'\1import {PKG}.{sub}.'
    patterns.append((pat2, repl2))

# 跳过 tests/, scripts/, docs/, README, .md
SKIP_DIRS = {"tests", "scripts", "docs", ".git", "__pycache__", ".pytest_cache", "factor_db.egg-info"}

total_files = 0
total_replacements = 0
file_details = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # 跳过指定目录
    rel = os.path.relpath(dirpath, ROOT)
    parts = rel.split(os.sep) if rel != "." else []
    if any(p in SKIP_DIRS for p in parts):
        continue
    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        if fname in ("__init__.py",):
            # __init__.py 通常用相对导入, 不修改
            continue
        fpath = os.path.join(dirpath, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        new_content = content
        file_count = 0
        for pat, repl in patterns:
            new_content, n = pat.subn(repl, new_content)
            file_count += n

        if file_count > 0:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            rel_path = os.path.relpath(fpath, ROOT)
            total_files += 1
            total_replacements += file_count
            file_details.append((rel_path, file_count))
            print(f"  Fixed: {rel_path}  ({file_count} replacements)")

print(f"\nTotal: {total_files} files, {total_replacements} replacements")
