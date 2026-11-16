# -*- coding: utf-8 -*-
"""旧版 pandas pickle 兼容转换 — E:\\Ashare_data 预构造因子解锁.

背景: `UTR_turnover.pkl` / `construction_factors/*.pkl` 由更高版本 pandas 写出,
其 `StringDtype` 以 3 个位置参数构造 (`('pyarrow', nan)`), 而本机 pandas 2.2.3
的签名为 `StringDtype(storage=None, na_value=NA)` → `pd.read_pickle` 抛
`TypeError: StringDtype.__init__() takes from 1 to 2 positional arguments but 3 were given`.
文件未损坏, 仅为反序列化兼容问题.

做法: 自定义 `Unpickler.find_class` 把 `StringDtype` 替换为 shim, shim 读取
storage 参数后返回本机 `pd.StringDtype`, 其余类照常解析; 转换结果写 parquet
(不依赖 numpy/pandas 版本), 原文件不改动.

用法:
    python scripts/convert_legacy_pickles.py
    python scripts/convert_legacy_pickles.py --force --format pickle
"""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

SRC_ROOT = r"E:\Ashare_data"
DST_ROOT = r"E:\Ashare_data\_converted"
TARGETS = [
    ('price_volume_factors', 'UTR_turnover.pkl'),
    ('price_volume_factors', 'UTR_turnover_new.pkl'),
    ('construction_factors', 'current_ratio.pkl'),
    ('construction_factors', 'debt_ratio.pkl'),
    ('construction_factors', 'LT_debt_ratio.pkl'),
    ('construction_factors', 'ocf_yoy_processed.pkl'),
]


class _StringDtypeShim:
    """接收旧版 pickle 的 3 参数构造, 交给当前 pandas 的 StringDtype."""

    def __new__(cls, *args, **kwargs):
        storage = next(
            (a for a in args if isinstance(a, str) and a in ('python', 'pyarrow')),
            None,
        )
        return pd.StringDtype(storage=storage)


class _CompatUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if name == 'StringDtype':
            return _StringDtypeShim
        return super().find_class(module, name)


def load_legacy(path):
    with open(path, 'rb') as f:
        return _CompatUnpickler(f).load()


def describe(df, path):
    dup = int(df.columns.duplicated().sum())
    return {
        'source': str(path),
        'shape': list(df.shape),
        'index_start': str(df.index[0])[:10],
        'index_end': str(df.index[-1])[:10],
        'nan_ratio': round(float(df.isna().to_numpy().mean()), 6),
        'duplicate_columns': dup,
        'nonnull_columns': int((df.notna().sum() > 0).sum()),
    }


def write_frame(df, dst, fmt, force):
    if dst.exists() and not force:
        return 'skipped'
    dst.parent.mkdir(parents=True, exist_ok=True)
    if df.columns.duplicated().any():
        seen = {}
        cols = []
        for c in df.columns:
            seen[c] = seen.get(c, 0) + 1
            cols.append(c if seen[c] == 1 else f'{c}__dup{seen[c]}')
        df = df.copy()
        df.columns = cols
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    if fmt == 'parquet':
        df.to_parquet(dst, engine='pyarrow')
    else:
        df.to_pickle(dst)
    return 'written'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src-root', default=SRC_ROOT)
    ap.add_argument('--dst-root', default=DST_ROOT)
    ap.add_argument('--format', choices=['parquet', 'pickle'], default='parquet')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    src_root = Path(args.src_root)
    dst_root = Path(args.dst_root)
    ext = '.parquet' if args.format == 'parquet' else '.pkl'
    manifest = []

    for sub, name in TARGETS:
        src = src_root / sub / name
        if not src.exists():
            print('MISS %s' % src)
            continue
        df = load_legacy(src)
        info = describe(df, src)
        dst = dst_root / sub / (Path(name).stem + ext)
        status = write_frame(df, dst, args.format, args.force)
        info['target'] = str(dst)
        info['status'] = status
        manifest.append(info)
        print('%-22s %-8s %-12s %s -> %s'
              % (name, status, str(info['shape']), info['index_start'],
                 info['index_end']))

    out = dst_root / 'manifest.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print('\nmanifest -> %s' % out)

    # 冒烟回读 (仅 parquet 抽查首尾)
    if args.format == 'parquet':
        for info in manifest:
            back = pd.read_parquet(info['target'])
            assert list(back.shape) == info['shape'], info['target']
            assert np.isclose(float(back.isna().to_numpy().mean()),
                              info['nan_ratio'], atol=1e-6), info['target']
        print('smoke check: %d/%d OK' % (len(manifest), len(manifest)))


if __name__ == '__main__':
    main()
