# -*- coding: utf-8 -*-
"""Check Factor_Trading_v3.0 setup readiness"""
import os

root = r'f:\Coding\Factor_Trading_v3.0'
init_path = os.path.join(root, '__init__.py')
print(f'Top __init__.py: {os.path.exists(init_path)}')

with open(os.path.join(root, 'pyproject.toml')) as f:
    pp = f.read()
print(f'Has packages.find: {"packages.find" in pp}')
print(f'Has package-dir: {"package-dir" in pp}')

# Check core/__init__.py
core_init = os.path.join(root, 'core', '__init__.py')
print(f'core/__init__.py: {os.path.exists(core_init)}')
if os.path.exists(core_init):
    with open(core_init) as f:
        ci = f.read()
    print(f'core/__init__.py size: {len(ci)} chars')
    print(f'core/__init__.py first 500 chars:')
    print(ci[:500])
