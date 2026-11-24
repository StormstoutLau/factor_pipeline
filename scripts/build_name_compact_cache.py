# -*- coding: utf-8 -*-
"""P-023 离线迁移：stock_name.pkl → stock_name_compact.npz。

幂等（mtime/size 匹配即 up-to-date）、原子（临时文件 + os.replace）、
可回退（删除 npz 即回 pkl；本脚本从不修改 pkl）。

用法：
    python scripts/build_name_compact_cache.py --data-root E:\\Ashare_data
    python scripts/build_name_compact_cache.py --data-root E:\\Ashare_data \
        --dry-run
"""
import argparse
import json
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_PARENT = os.path.dirname(_ROOT)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from backtest.tradability_loader import (  # noqa: E402
    NAME_COMPACT_NAME, build_name_compact_payload, load_name_compact,
    write_name_compact)

__all__ = ["migrate", "main"]


def migrate(data_root, panel_dir="market_data", out=None, force=False,
            dry_run=False):
    """执行迁移并返回统计 dict（status: up-to-date/dry-run/written）。"""
    src = os.path.join(data_root, panel_dir, "stock_name.pkl")
    if not os.path.exists(src):
        raise FileNotFoundError("缺少源面板: %s" % src)
    dst = out or os.path.join(data_root, panel_dir, NAME_COMPACT_NAME)
    if os.path.exists(dst) and not force:
        rec = load_name_compact(dst, src)
        if rec is not None:
            return {
                "status": "up-to-date",
                "path": dst,
                "bytes": int(os.path.getsize(dst)),
                "shape": [int(len(rec.index)), int(len(rec.columns))],
                "uniques": int(len(rec.aux[0])),
            }
    frame = pd.read_pickle(src)
    if dry_run:
        payload = build_name_compact_payload(frame)
        return {
            "status": "dry-run",
            "path": dst,
            "shape": [int(frame.shape[0]), int(frame.shape[1])],
            "uniques": int(len(payload["uniques"])),
        }
    stats = write_name_compact(dst, frame, src)
    stats["status"] = "written"
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="P-023 离线 name 紧凑缓存迁移（幂等/原子/可回退）")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--panel-dir", default="market_data")
    parser.add_argument("--out", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = migrate(args.data_root, panel_dir=args.panel_dir,
                         out=args.out, force=args.force,
                         dry_run=args.dry_run)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)},
                         ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
