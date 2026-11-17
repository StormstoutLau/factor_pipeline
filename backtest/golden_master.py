# -*- coding: utf-8 -*-
"""GR-3 Golden master (v3.6.0).

long-format parquet + JSON manifest；同环境 ``rtol=1e-10/atol=1e-12``，
跨环境禁止 bitwise 断言。本模块**不 import** ``governance``（DESIGN D1）；
DuckDB 为 lazy import（读写 parquet 不引入 pyarrow）。

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §6；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.3。
"""
import hashlib
import json
import logging
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
DEFAULT_RTOL = 1e-10
DEFAULT_ATOL = 1e-12
KEY_COLUMNS = ("date", "factor_id", "stock")


# ============================================================
# 数据模型
# ============================================================

@dataclass(frozen=True)
class GoldenManifest:
    baseline_id: str
    schema_version: str
    created_at: str
    code_commit: Optional[str]
    pipeline_version: str
    config_hash: Optional[str]
    data_snapshot_hash: Optional[str]
    universe_version: Optional[str]
    factor_ids: Tuple[str, ...]
    periods: Tuple[str, ...]
    n_stocks: int
    tolerance: Dict[str, float]
    env_fingerprint: Dict[str, Any]
    generator: str
    files: Dict[str, str]
    reason: Optional[str] = None
    reviewer: Optional[str] = None


@dataclass
class GoldenReport:
    baseline_id: str
    verdict: str                       # PASS | PASS_WITH_ENV_DIFF | FAIL
    n_common: int
    n_missing: int
    n_extra: int
    n_mismatch: int
    max_abs_diff: float
    max_rel_diff: float
    n_both_nan: int
    n_actual_nan: int
    n_baseline_nan: int
    per_factor: Dict[str, Dict[str, float]]
    env_match: bool
    nan_rate_guard_triggered: bool

    def to_markdown(self) -> str:
        lines = [
            "# Golden master 比较报告",
            "",
            "- baseline: `%s`" % self.baseline_id,
            "- 结论: **%s**" % self.verdict,
            "- 共同键: %d；缺失: %d；多出: %d；不一致: %d" % (
                self.n_common, self.n_missing, self.n_extra, self.n_mismatch
            ),
            "- max_abs_diff: %.3e；max_rel_diff: %.3e" % (
                self.max_abs_diff, self.max_rel_diff
            ),
            "- NaN: both=%d / actual=%d / baseline=%d" % (
                self.n_both_nan, self.n_actual_nan, self.n_baseline_nan
            ),
            "- 环境一致: %s；NaN 率守卫: %s" % (
                self.env_match, self.nan_rate_guard_triggered
            ),
        ]
        return "\n".join(lines)


# ============================================================
# 工具
# ============================================================

def _env_fingerprint() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "platform": platform.platform(),
    }


def _env_match(manifest: GoldenManifest) -> bool:
    local = _env_fingerprint()
    recorded = manifest.env_fingerprint or {}
    keys = [k for k in ("python", "numpy", "pandas") if k in recorded]
    if not keys:
        return False
    return all(recorded.get(k) == local.get(k) for k in keys)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _to_long(outputs: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    parts: List[pd.DataFrame] = []
    for factor_id, frame in outputs.items():
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("outputs[%r] 必须是 DataFrame" % factor_id)
        data = frame.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        data = data.reset_index()
        date_col = data.columns[0]
        data = data.rename(columns={date_col: "date"})
        long = data.melt(
            id_vars=["date"], var_name="stock", value_name="value"
        )
        long["factor_id"] = str(factor_id)
        long["stock"] = long["stock"].astype(str)
        long["value"] = pd.to_numeric(long["value"], errors="coerce")
        parts.append(long[["date", "factor_id", "stock", "value"]])
    if not parts:
        return pd.DataFrame(columns=list(KEY_COLUMNS) + ["value"])
    merged = pd.concat(parts, ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"]).astype("datetime64[ns]")
    return merged


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    import duckdb

    conn = duckdb.connect()
    try:
        conn.register("_gm_df", frame)
        target = str(path).replace("'", "''")
        conn.execute(
            "COPY (SELECT * FROM _gm_df) TO '%s' (FORMAT PARQUET)" % target
        )
    finally:
        conn.close()


def _read_parquet(path: Path) -> pd.DataFrame:
    import duckdb

    conn = duckdb.connect()
    try:
        target = str(path).replace("'", "''")
        frame = conn.execute(
            "SELECT * FROM read_parquet('%s')" % target
        ).df()
    finally:
        conn.close()
    frame["date"] = pd.to_datetime(frame["date"]).astype("datetime64[ns]")
    frame["factor_id"] = frame["factor_id"].astype(str)
    frame["stock"] = frame["stock"].astype(str)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


# ============================================================
# GoldenMaster
# ============================================================

class GoldenMaster:
    """数值回归基线：capture / load / compare / verify。"""

    def __init__(self, root: Union[str, Path] = "tests/golden"):
        self.root = Path(root)

    def capture(
        self,
        baseline_id: str,
        outputs: Mapping[str, pd.DataFrame],
        manifest: Mapping[str, Any],
        *,
        force: bool = False,
        reason: str = "",
        reviewer: str = "",
    ) -> Path:
        target = self.root / baseline_id
        parquet_path = target / "values.parquet"
        manifest_path = target / "manifest.json"
        exists = parquet_path.exists() or manifest_path.exists()

        if exists:
            if not force:
                raise FileExistsError(
                    "基线已存在: %s（force=True 才允许覆盖）" % target
                )
            if not reason.strip() or not reviewer.strip():
                raise ValueError("force 覆盖必须提供 reason 与 reviewer")

        long = _to_long(outputs)
        if long.empty:
            raise ValueError("outputs 为空，拒绝采集空基线")

        target.mkdir(parents=True, exist_ok=True)
        _write_parquet(long, parquet_path)

        payload = dict(manifest or {})
        tolerance = dict(payload.get("tolerance") or {
            "rtol": DEFAULT_RTOL, "atol": DEFAULT_ATOL,
        })
        record = GoldenManifest(
            baseline_id=baseline_id,
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
            created_at=str(payload.get("created_at")
                           or pd.Timestamp.now(tz="UTC").isoformat()),
            code_commit=payload.get("code_commit"),
            pipeline_version=str(payload.get("pipeline_version", "unknown")),
            config_hash=payload.get("config_hash"),
            data_snapshot_hash=payload.get("data_snapshot_hash"),
            universe_version=payload.get("universe_version"),
            factor_ids=tuple(sorted(str(k) for k in outputs)),
            periods=tuple(
                sorted(long["date"].dt.strftime("%Y-%m-%d").unique().tolist())
            ),
            n_stocks=int(long["stock"].nunique()),
            tolerance=tolerance,
            env_fingerprint=dict(
                payload.get("env_fingerprint") or _env_fingerprint()
            ),
            generator=str(payload.get("generator", "unknown")),
            files={"values.parquet": _sha256_file(parquet_path)},
            reason=(reason or None),
            reviewer=(reviewer or None),
        )
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(asdict(record), handle, ensure_ascii=False, indent=2,
                      default=str)
        return parquet_path

    def load(
        self, baseline_id: str
    ) -> Tuple[GoldenManifest, pd.DataFrame]:
        target = self.root / baseline_id
        manifest_path = target / "manifest.json"
        parquet_path = target / "values.parquet"
        if not manifest_path.exists() or not parquet_path.exists():
            raise FileNotFoundError("基线不存在: %s" % target)
        with open(manifest_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["factor_ids"] = tuple(payload.get("factor_ids") or ())
        payload["periods"] = tuple(payload.get("periods") or ())
        known = set(GoldenManifest.__dataclass_fields__)
        payload = {k: v for k, v in payload.items() if k in known}
        manifest = GoldenManifest(**payload)
        return manifest, _read_parquet(parquet_path)

    def compare(
        self,
        baseline_id: str,
        outputs: Mapping[str, pd.DataFrame],
        *,
        rtol: Optional[float] = None,
        atol: Optional[float] = None,
    ) -> GoldenReport:
        manifest, baseline = self.load(baseline_id)
        actual = _to_long(outputs)
        rtol = float(manifest.tolerance.get("rtol", DEFAULT_RTOL)
                     if rtol is None else rtol)
        atol = float(manifest.tolerance.get("atol", DEFAULT_ATOL)
                     if atol is None else atol)

        merged = baseline.merge(
            actual, on=list(KEY_COLUMNS), how="outer",
            suffixes=("_baseline", "_actual"), indicator=True,
        )
        n_missing = int((merged["_merge"] == "left_only").sum())
        n_extra = int((merged["_merge"] == "right_only").sum())
        both = merged[merged["_merge"] == "both"].copy()

        expected = both["value_baseline"].to_numpy(dtype=float)
        observed = both["value_actual"].to_numpy(dtype=float)
        close = np.isclose(observed, expected, rtol=rtol, atol=atol,
                           equal_nan=True)
        n_mismatch = int((~close).sum())

        n_both_nan = int(
            (both["value_baseline"].isna() & both["value_actual"].isna()).sum()
        )
        n_actual_nan = int(both["value_actual"].isna().sum())
        n_baseline_nan = int(both["value_baseline"].isna().sum())

        finite = np.isfinite(expected) & np.isfinite(observed)
        if finite.any():
            diff = np.abs(observed[finite] - expected[finite])
            max_abs = float(diff.max())
            denom = np.maximum(np.abs(expected[finite]), 1e-300)
            max_rel = float((diff / denom).max())
        else:
            max_abs = 0.0
            max_rel = 0.0

        factors = sorted(set(baseline["factor_id"]) | set(actual["factor_id"]))
        per_factor: Dict[str, Dict[str, float]] = {}
        guard = False
        for factor in factors:
            sub = both[both["factor_id"] == factor]
            if len(sub) == 0:
                per_factor[factor] = {
                    "n_mismatch": 0.0, "max_abs_diff": 0.0,
                    "actual_nan_rate": 0.0, "baseline_nan_rate": 0.0,
                }
                continue
            exp = sub["value_baseline"].to_numpy(dtype=float)
            obs = sub["value_actual"].to_numpy(dtype=float)
            ok = np.isclose(obs, exp, rtol=rtol, atol=atol, equal_nan=True)
            finite_sub = np.isfinite(exp) & np.isfinite(obs)
            per_factor[factor] = {
                "n_mismatch": float(int((~ok).sum())),
                "max_abs_diff": float(
                    np.abs(obs[finite_sub] - exp[finite_sub]).max()
                ) if finite_sub.any() else 0.0,
                "actual_nan_rate": float(np.isnan(obs).mean()),
                "baseline_nan_rate": float(np.isnan(exp).mean()),
            }
            if (per_factor[factor]["actual_nan_rate"]
                    - per_factor[factor]["baseline_nan_rate"]) > 0.01:
                guard = True

        env_match = _env_match(manifest)
        if n_mismatch or n_missing or n_extra or guard:
            verdict = "FAIL"
        elif not env_match:
            verdict = "PASS_WITH_ENV_DIFF"
        else:
            verdict = "PASS"

        return GoldenReport(
            baseline_id=baseline_id,
            verdict=verdict,
            n_common=int(len(both)),
            n_missing=n_missing,
            n_extra=n_extra,
            n_mismatch=n_mismatch,
            max_abs_diff=max_abs,
            max_rel_diff=max_rel,
            n_both_nan=n_both_nan,
            n_actual_nan=n_actual_nan,
            n_baseline_nan=n_baseline_nan,
            per_factor=per_factor,
            env_match=env_match,
            nan_rate_guard_triggered=guard,
        )

    def verify(
        self,
        baseline_id: str,
        runner,
        *,
        rtol: Optional[float] = None,
        atol: Optional[float] = None,
    ) -> GoldenReport:
        outputs = runner()
        return self.compare(
            baseline_id, outputs, rtol=rtol, atol=atol
        )
