# -*- coding: utf-8 -*-
"""样本外协议：purged K 折、组合 purged K 折与 holdout 登记（v3.7.0 E1）。

设计依据：``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §4；
实施依据：``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §2.1。

本模块为显式调用：不被 ``backtest/__init__.py`` 导入，也未实例化时
不产生任何文件或行为。
"""
import hashlib
import itertools
import json
import math
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np


class HoldoutRegistryError(RuntimeError):
    """holdout 登记不可用 / 记录缺失 / 时序违规。"""


class HoldoutReuseError(HoldoutRegistryError):
    """holdout 窗口被其他批次占用，或本批次改动了窗口。"""


# ============================================================
# 内部辅助
# ============================================================

def _segments(idx: np.ndarray) -> List[Tuple[int, int]]:
    """把有序索引切成连续段 ``[(a, b), ...]``（含端点）。"""
    if len(idx) == 0:
        return []
    segments: List[Tuple[int, int]] = []
    start = prev = int(idx[0])
    for value in idx[1:]:
        cur = int(value)
        if cur == prev + 1:
            prev = cur
            continue
        segments.append((start, prev))
        start = prev = cur
    segments.append((start, prev))
    return segments


def _excluded_mask(
    test_idx: np.ndarray,
    purge: int,
    embargo: int,
    label_horizon: int,
    n_samples: int,
) -> np.ndarray:
    """训练集需剔除的 purge/embargo 掩码（逐连续测试段生成）。"""
    mask = np.zeros(n_samples, dtype=bool)
    # 标签重叠至少剔除 a-1（label_horizon>=1，保守口径）；purge 为额外下限
    back = max(purge, label_horizon)
    for a, b in _segments(test_idx):
        lo = max(0, a - back)
        hi = min(n_samples - 1, b + embargo)
        if lo <= hi:
            mask[lo:hi + 1] = True
    return mask


def _train_mask(
    test_idx: np.ndarray,
    purge: int,
    embargo: int,
    label_horizon: int,
    n_samples: int,
) -> np.ndarray:
    keep = np.ones(n_samples, dtype=bool)
    keep[test_idx] = False
    keep &= ~_excluded_mask(
        test_idx, purge, embargo, label_horizon, n_samples)
    return keep


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# PurgedKFold
# ============================================================

class PurgedKFold:
    """purged K 折（López de Prado）。

    测试折为连续块；训练集剔除测试折、purge 区（标签重叠）与
    embargo 区（测试段之后的 ``embargo`` 期）。
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge: int = 1,
        embargo: int = 1,
        label_horizon: int = 1,
    ) -> None:
        if n_splits < 2:
            raise ValueError("n_splits 必须 >= 2")
        if purge < 0:
            raise ValueError("purge 必须 >= 0")
        if embargo < 0:
            raise ValueError("embargo 必须 >= 0")
        if label_horizon < 1:
            raise ValueError("label_horizon 必须 >= 1")
        self.n_splits = int(n_splits)
        self.purge = int(purge)
        self.embargo = int(embargo)
        self.label_horizon = int(label_horizon)

    @property
    def split_id(self) -> str:
        return "pkf_n%d_p%d_e%d_h%d" % (
            self.n_splits, self.purge, self.embargo, self.label_horizon)

    def _validate_n(self, n_samples: int) -> None:
        minimum = self.n_splits + self.purge + self.embargo + self.label_horizon
        if n_samples < minimum:
            raise ValueError(
                "n_samples=%d 小于最小要求 %d" % (n_samples, minimum))

    def split_groups(self, n_samples: int) -> List[np.ndarray]:
        self._validate_n(n_samples)
        groups = np.array_split(
            np.arange(n_samples, dtype=np.int64), self.n_splits)
        return [np.asarray(g, dtype=np.int64) for g in groups]

    def split(
        self, n_samples: int,
    ) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        for test in self.split_groups(n_samples):
            keep = _train_mask(
                test, self.purge, self.embargo,
                self.label_horizon, n_samples)
            yield np.flatnonzero(keep).astype(np.int64), test


# ============================================================
# CombinatorialPurgedKFold
# ============================================================

class CombinatorialPurgedKFold:
    """组合 purged K 折（CSCV 的路径生成器）。"""

    def __init__(
        self,
        n_groups: int = 6,
        n_test_groups: int = 2,
        purge: int = 1,
        embargo: int = 1,
        label_horizon: int = 1,
    ) -> None:
        if n_groups < 2:
            raise ValueError("n_groups 必须 >= 2")
        if not (1 <= n_test_groups < n_groups):
            raise ValueError("n_test_groups 必须满足 1 <= k < n_groups")
        if purge < 0:
            raise ValueError("purge 必须 >= 0")
        if embargo < 0:
            raise ValueError("embargo 必须 >= 0")
        if label_horizon < 1:
            raise ValueError("label_horizon 必须 >= 1")
        self.n_groups = int(n_groups)
        self.n_test_groups = int(n_test_groups)
        self.purge = int(purge)
        self.embargo = int(embargo)
        self.label_horizon = int(label_horizon)

    @property
    def n_paths(self) -> int:
        return math.comb(self.n_groups, self.n_test_groups)

    @property
    def split_id(self) -> str:
        return "cpcv_n%d_k%d_p%d_e%d_h%d" % (
            self.n_groups, self.n_test_groups,
            self.purge, self.embargo, self.label_horizon)

    def split_groups(self, n_samples: int) -> List[np.ndarray]:
        if n_samples < self.n_groups:
            raise ValueError(
                "n_samples=%d 小于 n_groups=%d"
                % (n_samples, self.n_groups))
        groups = np.array_split(
            np.arange(n_samples, dtype=np.int64), self.n_groups)
        return [np.asarray(g, dtype=np.int64) for g in groups]

    def split(
        self, n_samples: int,
    ) -> Iterator[Tuple[np.ndarray, np.ndarray, int]]:
        groups = self.split_groups(n_samples)
        for path_id, combo in enumerate(itertools.combinations(
                range(self.n_groups), self.n_test_groups)):
            test = np.sort(np.concatenate([groups[i] for i in combo]))
            test = np.asarray(test, dtype=np.int64)
            keep = _train_mask(
                test, self.purge, self.embargo,
                self.label_horizon, n_samples)
            yield np.flatnonzero(keep).astype(np.int64), test, path_id


# ============================================================
# HoldoutRegistry
# ============================================================

_CHECK_KEYS = (
    "holdout_id", "start", "end", "universe_version", "batch_id",
    "locked_at", "price_convention", "return_convention", "note",
)


class HoldoutRegistry:
    """holdout 窗口登记（DuckDB，append-only）。"""

    def __init__(
        self,
        db_path: str = "holdout_db.duckdb",
        table_prefix: str = "cv_",
        enable: bool = True,
    ) -> None:
        if not table_prefix.replace("_", "").isalnum():
            raise ValueError("非法 table_prefix: %r" % table_prefix)
        self.db_path = db_path
        self.prefix = table_prefix
        self.enable = enable
        self._conn = None

    # —— 内部 ——
    def _table(self) -> str:
        return self.prefix + "holdout"

    def _connect(self):
        if not self.enable:
            raise HoldoutRegistryError("holdout registry 未启用")
        if self._conn is not None:
            return self._conn
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise HoldoutRegistryError("duckdb 不可用") from exc
        self._conn = duckdb.connect(self.db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS {t} (
                holdout_id VARCHAR PRIMARY KEY,
                start_date VARCHAR NOT NULL,
                end_date VARCHAR NOT NULL,
                universe_version VARCHAR,
                batch_id VARCHAR NOT NULL,
                locked_at VARCHAR NOT NULL,
                payload JSON NOT NULL
            )
            """.format(t=self._table())
        )
        return self._conn

    def _rows(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT holdout_id, start_date, end_date, universe_version, "
            "batch_id, locked_at, payload FROM {t}".format(t=self._table())
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = row[6]
            if isinstance(payload, str):
                payload = json.loads(payload)
            payload = payload or {}
            out.append({
                "holdout_id": row[0],
                "start": row[1],
                "end": row[2],
                "universe_version": row[3],
                "batch_id": row[4],
                "locked_at": row[5],
                "price_convention": payload.get("price_convention"),
                "return_convention": payload.get("return_convention"),
                "note": payload.get("note", ""),
            })
        return out

    # —— 公共 API ——
    def lock(
        self,
        start: str,
        end: str,
        universe_version: str,
        batch_id: str,
        *,
        price_convention: str = "hfq",
        return_convention: str = "monthly_next",
        locked_at: Optional[str] = None,
        note: str = "",
    ) -> str:
        if not self.enable:
            raise HoldoutRegistryError("holdout registry 未启用")
        try:
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ValueError("start/end 必须为 YYYY-MM-DD") from exc
        if start > end:
            raise ValueError("start 必须 <= end")

        body = {
            "start": start,
            "end": end,
            "universe_version": universe_version,
            "price_convention": price_convention,
            "return_convention": return_convention,
        }
        holdout_id = hashlib.sha256(
            _canonical_json(body).encode("utf-8")).hexdigest()

        existing_rows = self._rows()
        for row in existing_rows:
            if row["holdout_id"] == holdout_id:
                if row["batch_id"] == batch_id:
                    return holdout_id
                raise HoldoutReuseError(
                    "holdout 窗口已被 batch %s 锁定" % row["batch_id"])
            overlap = not (row["end"] < start or row["start"] > end)
            if not overlap:
                continue
            if row["batch_id"] == batch_id:
                if row["start"] == start and row["end"] == end:
                    # 同一时间窗的其它 universe / 口径：允许
                    continue
                raise HoldoutReuseError(
                    "同 batch 改动 holdout 窗口: %s..%s"
                    % (row["start"], row["end"]))
            raise HoldoutReuseError(
                "holdout 窗口与 batch %s 重叠: %s..%s"
                % (row["batch_id"], row["start"], row["end"]))

        payload = {
            "price_convention": price_convention,
            "return_convention": return_convention,
            "note": note,
        }
        conn = self._connect()
        conn.execute(
            "INSERT INTO {t} VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON))"
            .format(t=self._table()),
            [holdout_id, start, end, universe_version, batch_id,
             locked_at or _utc_now(),
             json.dumps(payload, ensure_ascii=False)],
        )
        return holdout_id

    def check(self, holdout_id: str) -> Optional[Dict[str, Any]]:
        if not self.enable:
            raise HoldoutRegistryError("holdout registry 未启用")
        for row in self._rows():
            if row["holdout_id"] == holdout_id:
                return {key: row.get(key) for key in _CHECK_KEYS}
        return None

    def assert_locked_before(self, holdout_id: str, run_at: str) -> None:
        record = self.check(holdout_id)
        if record is None:
            raise HoldoutRegistryError("holdout 记录不存在: %s" % holdout_id)
        if _parse_dt(run_at) < _parse_dt(record["locked_at"]):
            raise HoldoutRegistryError(
                "run_at 早于 holdout 锁定时间（回顾性，不得声称样本外）")

    def dev_mask(
        self,
        dates: Sequence[str],
        holdout_id: Optional[str],
        purge: int = 1,
    ) -> np.ndarray:
        if not self.enable:
            raise HoldoutRegistryError("holdout registry 未启用")
        values = [str(d) for d in dates]
        for prev, cur in zip(values, values[1:]):
            if cur < prev:
                raise ValueError("dates 必须按升序排列")
        mask = np.ones(len(values), dtype=bool)
        if holdout_id is None:
            return mask
        record = self.check(holdout_id)
        if record is None:
            raise HoldoutRegistryError(
                "holdout 记录不存在: %s" % holdout_id)
        start = record["start"]
        dev = np.array([d < start for d in values], dtype=bool)
        if purge > 0 and dev.any():
            dev_idx = np.flatnonzero(dev)
            dev[dev_idx[-purge:]] = False
        mask &= dev
        return mask

    def list_locks(self) -> List[Dict[str, Any]]:
        if not self.enable:
            raise HoldoutRegistryError("holdout registry 未启用")
        return [{key: row.get(key) for key in _CHECK_KEYS}
                for row in self._rows()]


def require_locked(
    registry: HoldoutRegistry,
) -> Callable[[str, str], None]:
    """生成 ledger 可用的 holdout 校验回调（依赖注入）。"""
    def _check(holdout_id: str, batch_id: str) -> None:
        record = registry.check(holdout_id)
        if record is None or record["batch_id"] != batch_id:
            raise HoldoutReuseError(
                "holdout 未由本 batch 锁定: %s" % holdout_id)
    return _check
