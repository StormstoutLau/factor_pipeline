# -*- coding: utf-8 -*-
"""GR-2 数据契约 (v3.6.0).

字段级新鲜度 / PIT / 覆盖率 / 值域 / 日历校验；默认 ``strict=False``
只返回报告，不抛错。本模块**不 import** ``governance``（DESIGN D1）；
异常基类为模块内局部 ``DataContractError``。

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §5；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.2。
"""
import hashlib
import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

POLICY_VERSION = "1.0.0"

# known_gap 码名集中映射（DESIGN §5.7.4 词汇表；复审 R3 / 修复包 F3；DR-F3）：
# 码名约束集中在数据处，新增 known_gap 字段只需加一行映射；
# 未命中回退 "<name>_missing"（兜底语义不变）
GAP_CODE_BY_FIELD: Dict[str, str] = {
    "barra": "barra_stale",
    "industry": "industry_stale",
}


# ============================================================
# 异常
# ============================================================

class DataContractError(Exception):
    """strict 模式下存在 block 级失败。"""

    def __init__(self, report: "ContractReport"):
        super().__init__("数据契约未通过: %d 个阻断项" % len(report.blocking()))
        self.report = report


# ============================================================
# 数据模型
# ============================================================

@dataclass(frozen=True)
class FieldSpec:
    name: str
    file: Optional[str] = None
    reader: str = "pickle"
    max_lag: Optional[int] = 0
    required: bool = True
    min_coverage: float = 0.95
    max_nan_rate: float = 0.50
    value_range: Optional[Tuple[float, float]] = None
    description: str = ""
    semantic_type: str = "price"
    unit: Optional[str] = None
    pit_required: bool = False
    pit_date_field: Optional[str] = None
    missing_semantics: str = "warn"      # warn | known_gap | block
    universe_bias_applicable: bool = False
    expected_missing_tail: int = 0
    column: Optional[str] = None         # 派生需求 DR-11：list_date_df['list_date']


@dataclass(frozen=True)
class FieldSnapshot:
    name: str
    last_any_date: Optional[str]
    last_full_date: Optional[str]
    coverage_last: float
    nan_rate: float
    n_rows: int
    n_cols: int
    file: Optional[str]
    file_fingerprint: str
    fingerprint_mode: str
    content_digest: str


@dataclass(frozen=True)
class KnownGap:
    code: str
    field: str
    start: Optional[str]
    end: Optional[str]
    impact: str
    mitigation: str


@dataclass(frozen=True)
class DataSnapshot:
    as_of: str
    sample_end: str
    fields: Dict[str, FieldSnapshot]
    universe_version: Optional[str]
    universe_bias: str = "unknown"
    calendar_hash: Optional[str] = None

    def stable_hash(self) -> str:
        """稳定子集 hash：排除 as_of（F-A）；含 content_digest。"""
        body = {
            "sample_end": self.sample_end,
            "universe_version": self.universe_version,
            "universe_bias": self.universe_bias,
            "calendar_hash": self.calendar_hash,
            "fields": {
                name: {
                    "last_any_date": snap.last_any_date,
                    "last_full_date": snap.last_full_date,
                    "coverage_last": snap.coverage_last,
                    "nan_rate": snap.nan_rate,
                    "n_rows": snap.n_rows,
                    "n_cols": snap.n_cols,
                    "content_digest": snap.content_digest,
                }
                for name, snap in self.fields.items()
            },
        }
        return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()

    def to_record_fields(self) -> Dict[str, Any]:
        return {
            "data_snapshot": {
                "as_of": self.as_of,
                "sample_end": self.sample_end,
                "universe_version": self.universe_version,
                "universe_bias": self.universe_bias,
                "calendar_hash": self.calendar_hash,
                "fields": {
                    name: asdict(snap) for name, snap in self.fields.items()
                },
            },
            "data_snapshot_hash": self.stable_hash(),
            "universe_version": self.universe_version,
        }


@dataclass(frozen=True)
class CheckResult:
    check: str
    passed: bool
    severity: str                 # block | warn | info
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContractReport:
    passed: bool
    checks: List[CheckResult]
    snapshot: DataSnapshot
    policy_version: str
    known_gaps: Tuple[KnownGap, ...] = ()
    calendar_source: str = "injected"

    def blocking(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "block"]

    def warnings(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "warn"]

    def to_markdown(self) -> str:
        lines = [
            "# 数据契约报告",
            "",
            "- 结论: **%s**" % ("PASS" if self.passed else "FAIL"),
            "- 样本末: %s" % self.snapshot.sample_end,
            "- 策略版本: %s" % self.policy_version,
            "- 日历来源: %s" % self.calendar_source,
            "",
            "| 检查 | 字段 | 结果 | 严重度 | 说明 |",
            "|------|------|------|--------|------|",
        ]
        for check in self.checks:
            lines.append(
                "| %s | %s | %s | %s | %s |" % (
                    check.check,
                    check.details.get("field", "-"),
                    "PASS" if check.passed else "FAIL",
                    check.severity,
                    check.message.replace("|", "/"),
                )
            )
        if self.known_gaps:
            lines.extend(["", "## 已知缺口"])
            for gap in self.known_gaps:
                lines.append("- `%s` (%s): %s" % (gap.code, gap.field, gap.impact))
        return "\n".join(lines)

    def to_record_fields(self) -> Dict[str, Any]:
        payload = self.snapshot.to_record_fields()
        payload.update({
            "contract_passed": self.passed,
            "contract_policy_version": self.policy_version,
            "known_gaps": [asdict(gap) for gap in self.known_gaps],
            "calendar_source": self.calendar_source,
        })
        return payload


class FieldReader(Protocol):
    def read(self, root: Path, spec: FieldSpec) -> pd.DataFrame:
        ...


# ============================================================
# 默认字段（匹配实际数据布局）
# ============================================================

def default_fields() -> Tuple[FieldSpec, ...]:
    return (
        FieldSpec("price", "stock_close.pkl", max_lag=0,
                  semantic_type="price", unit="元"),
        FieldSpec("adj", "stock_adj.pkl", max_lag=0,
                  semantic_type="adj_factor"),
        FieldSpec("amount", "stock_amount.pkl", max_lag=0,
                  semantic_type="amount", unit="千元"),
        FieldSpec("mv", "market_value.csv", reader="csv", max_lag=1,
                  semantic_type="mv", unit="元"),
        FieldSpec("list_date", "list_date_df.pkl", reader="pickle_series",
                  max_lag=None, column="list_date",
                  semantic_type="reference_date"),
        FieldSpec("volume", "stock_volume.pkl", max_lag=0, required=False,
                  semantic_type="volume", unit="股"),
        FieldSpec("open", "stock_open.pkl", max_lag=0, required=False),
        FieldSpec("high", "stock_high.pkl", max_lag=0, required=False),
        FieldSpec("low", "stock_low.pkl", max_lag=0, required=False),
        FieldSpec("suspend", "stock_suspend.pkl", max_lag=1, required=False,
                  semantic_type="status_flag"),
        FieldSpec("name", "stock_name.pkl", max_lag=None, required=False,
                  semantic_type="status_flag"),
        FieldSpec("return", "stock_return.pkl", max_lag=1, required=False,
                  semantic_type="return", unit="%", expected_missing_tail=1),
        FieldSpec("calendar", "all_dates.pkl", max_lag=None, required=False,
                  semantic_type="reference_date"),
        FieldSpec("barra", "market_data/barra_df_tl.pkl", max_lag=None,
                  required=False, missing_semantics="known_gap"),
        FieldSpec("industry", None, reader="industry", max_lag=None,
                  required=False, missing_semantics="known_gap"),
    )


# ============================================================
# 工具
# ============================================================

def _canonical_json(obj: Any) -> str:
    return json.dumps(
        _jsonable(obj), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    )


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.generic,)):
        return _jsonable(obj.item())
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    return obj


def _stable_scalar(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _stable_scalar(value.item())
    if isinstance(value, float) and math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return value


def _content_digest(frame: pd.DataFrame) -> str:
    """确定性内容摘要：列名 + shape + 每列首/中/尾各 8 行 + NaN 计数。"""
    digest = hashlib.sha256()
    digest.update(_canonical_json({
        "columns": [str(c) for c in frame.columns],
        "shape": [int(frame.shape[0]), int(frame.shape[1])],
    }).encode("utf-8"))
    n_rows = len(frame)
    positions = set(range(min(8, n_rows)))
    if n_rows:
        middle = n_rows // 2
        positions.update(range(max(0, middle - 4), min(n_rows, middle + 4)))
        positions.update(range(max(0, n_rows - 8), n_rows))
    for column in frame.columns:
        series = frame[column]
        for pos in sorted(positions):
            digest.update(_canonical_json([
                str(column), int(pos), _stable_scalar(series.iloc[pos])
            ]).encode("utf-8"))
    digest.update(_canonical_json({
        "nan": int(frame.isna().sum().sum())
    }).encode("utf-8"))
    return digest.hexdigest()


def _meta_fingerprint(path: Path) -> str:
    stat = path.stat()
    body = "%d|%d" % (stat.st_size, stat.st_mtime_ns)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _head_digest(path: Path, size: int = 65536) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read(size)).hexdigest()


def _calendar_hash(calendar: pd.DatetimeIndex) -> str:
    body = "\n".join(d.strftime("%Y-%m-%d") for d in calendar)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _resolve_calendar(
    root: Path, sample_end: pd.Timestamp,
    trading_calendar: Optional[Any],
) -> Tuple[pd.DatetimeIndex, str, bool]:
    """返回 (calendar, source, fallback_used)。"""
    if trading_calendar is not None:
        calendar = pd.DatetimeIndex(pd.to_datetime(trading_calendar))
        calendar = calendar.normalize().drop_duplicates().sort_values()
        return calendar, "injected", False

    calendar_path = root / "all_dates.pkl"
    if calendar_path.exists():
        obj = pd.read_pickle(calendar_path)
        if isinstance(obj, pd.DataFrame):
            index = pd.DatetimeIndex(obj.index)
        else:
            index = pd.DatetimeIndex(pd.to_datetime(obj))
        return (
            index.normalize().drop_duplicates().sort_values(),
            "field:all_dates",
            False,
        )

    fallback = pd.bdate_range(end=sample_end, periods=1300)
    return fallback, "bdate_fallback", True


def _effective_end(calendar: pd.DatetimeIndex,
                   sample_end: pd.Timestamp) -> Optional[pd.Timestamp]:
    candidates = calendar[calendar <= sample_end]
    if len(candidates) == 0:
        return None
    return candidates.max()


def _trading_day_lag(last_full: pd.Timestamp, effective: pd.Timestamp,
                     calendar: pd.DatetimeIndex) -> int:
    after = calendar[(calendar > last_full) & (calendar <= effective)]
    return int(len(after))


def _as_frame(obj: Any, spec: FieldSpec) -> pd.DataFrame:
    if isinstance(obj, pd.Series):
        return obj.to_frame(name=spec.column or spec.name)
    if isinstance(obj, pd.DataFrame):
        if spec.reader == "pickle_series":
            if spec.column and spec.column in obj.columns:
                return obj[[spec.column]]
            if len(obj.columns) == 1:
                return obj
            raise ValueError(
                "pickle_series 需要 column 或单列 DataFrame: %s" % spec.name
            )
        return obj
    raise TypeError("reader 返回类型不支持: %s" % type(obj).__name__)


def _read_frame(root: Path, spec: FieldSpec,
                readers: Optional[Mapping[str, Any]]) -> pd.DataFrame:
    path = root / spec.file  # type: ignore[operator]
    custom = (readers or {}).get(spec.reader)
    if custom is not None:
        if hasattr(custom, "read"):
            return _as_frame(custom.read(root, spec), spec)
        return _as_frame(custom(root, spec), spec)

    if spec.reader == "csv":
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    elif spec.reader in ("pickle", "pickle_series"):
        frame = pd.read_pickle(path)
    elif spec.reader == "derived":
        raise ValueError("derived reader 必须注入: %s" % spec.name)
    else:
        raise ValueError("未知 reader: %s" % spec.reader)
    return _as_frame(frame, spec)


def _empty_snapshot(spec: FieldSpec) -> FieldSnapshot:
    return FieldSnapshot(
        name=spec.name, last_any_date=None, last_full_date=None,
        coverage_last=0.0, nan_rate=1.0, n_rows=0, n_cols=0,
        file=spec.file, file_fingerprint="", fingerprint_mode="meta",
        content_digest="",
    )


def _make_snapshot(spec: FieldSpec, frame: pd.DataFrame, path: Path,
                   effective: Optional[pd.Timestamp]) -> FieldSnapshot:
    index = frame.index
    n_rows, n_cols = frame.shape
    coverage = frame.notna().sum(axis=1) / max(n_cols, 1)

    core = frame
    if spec.expected_missing_tail and n_rows > spec.expected_missing_tail:
        core = frame.iloc[:-spec.expected_missing_tail]
        core_coverage = coverage.iloc[:-spec.expected_missing_tail]
    else:
        core_coverage = coverage

    full_mask = core_coverage >= spec.min_coverage
    last_full = None
    if len(core_coverage) and bool(full_mask.any()):
        last_full = core_coverage.index[full_mask][-1]

    last_any = None
    if len(index):
        any_mask = core.notna().any(axis=1)
        if bool(any_mask.any()):
            last_any = core.index[any_mask][-1]

    coverage_last = 0.0
    if effective is not None and len(index):
        upto = index[index <= effective]
        if len(upto):
            coverage_last = float(coverage.loc[upto[-1]])

    nan_rate = float(frame.isna().to_numpy().mean()) if n_rows else 1.0
    return FieldSnapshot(
        name=spec.name,
        last_any_date=_iso(last_any),
        last_full_date=_iso(last_full),
        coverage_last=coverage_last,
        nan_rate=nan_rate,
        n_rows=int(n_rows),
        n_cols=int(n_cols),
        file=spec.file,
        file_fingerprint=_meta_fingerprint(path),
        fingerprint_mode="meta",
        content_digest=_content_digest(frame),
    )


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


# ============================================================
# 检查
# ============================================================

def _schema_checks(spec: FieldSpec, frame: pd.DataFrame) -> List[CheckResult]:
    problems = []
    if not isinstance(frame.index, pd.DatetimeIndex):
        problems.append("index 非 DatetimeIndex")
    else:
        if not frame.index.is_monotonic_increasing:
            problems.append("index 非单调递增")
        if frame.index.has_duplicates:
            problems.append("index 存在重复")
    if len(set(map(str, frame.columns))) != len(frame.columns):
        problems.append("列名重复")
    numeric_types = {"price", "adj_factor", "volume", "amount", "mv", "return"}
    if spec.semantic_type in numeric_types:
        non_numeric = [
            str(c) for c in frame.columns
            if not pd.api.types.is_numeric_dtype(frame[c])
        ]
        if non_numeric:
            problems.append("非数值列: %s" % non_numeric[:5])
    if spec.semantic_type in numeric_types:
        values = frame.to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(values).any():
            problems.append("存在 inf")
    passed = not problems
    return [CheckResult(
        "schema", passed, "block" if spec.required else "warn",
        "%s: %s" % (spec.name, "OK" if passed else "; ".join(problems)),
        {"field": spec.name, "problems": problems},
    )]


def _value_checks(spec: FieldSpec, frame: pd.DataFrame) -> List[CheckResult]:
    numeric_types = {"price", "adj_factor", "volume", "amount", "mv", "return"}
    if spec.value_range is None and spec.semantic_type not in numeric_types:
        return []
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    finite = values[np.isfinite(values)]
    problems = []
    if spec.value_range is not None and finite.size:
        low, high = spec.value_range
        if finite.min() < low or finite.max() > high:
            problems.append("越界 [%s, %s]" % (low, high))
    elif spec.semantic_type in ("price", "adj_factor", "mv"):
        if finite.size and finite.min() <= 0:
            problems.append("存在 <= 0 的值")
    elif spec.semantic_type in ("amount", "volume"):
        if finite.size and finite.min() < 0:
            problems.append("存在负值")
    if not problems:
        return []
    return [CheckResult(
        "value_sanity", False, "block", "%s: %s" % (spec.name, "; ".join(problems)),
        {"field": spec.name, "problems": problems},
    )]


def _freshness_check(spec: FieldSpec, snap: FieldSnapshot,
                     effective: Optional[pd.Timestamp],
                     calendar: pd.DatetimeIndex) -> Optional[CheckResult]:
    if spec.max_lag is None:
        return None
    if effective is None or snap.last_full_date is None:
        return CheckResult(
            "freshness", False, "block" if spec.required else "warn",
            "%s: 无可用满覆盖日" % spec.name, {"field": spec.name},
        )
    last_full = pd.Timestamp(snap.last_full_date)
    raw_lag = _trading_day_lag(last_full, effective, calendar)
    # B13：forward return 末行结构性缺失；effective_end 不变，仅从 lag 中扣除
    expected_tail = max(0, int(spec.expected_missing_tail or 0))
    lag = max(0, raw_lag - expected_tail)
    passed = lag <= spec.max_lag
    detail = "lag=%d, max_lag=%d (last_full=%s, end=%s)" % (
        lag, spec.max_lag, last_full.date(), effective.date(),
    )
    if expected_tail:
        detail += ", raw_lag=%d, expected_missing_tail=%d" % (
            raw_lag, expected_tail,
        )
    return CheckResult(
        "freshness", passed, "block" if spec.required else "warn",
        "%s: %s" % (spec.name, detail),
        {"field": spec.name, "lag": lag, "raw_lag": raw_lag,
         "expected_missing_tail": expected_tail,
         "max_lag": spec.max_lag},
    )


def _coverage_check(spec: FieldSpec, snap: FieldSnapshot) -> CheckResult:
    problems = []
    if snap.coverage_last < spec.min_coverage:
        problems.append(
            "coverage_last=%.4f < %.4f" % (snap.coverage_last, spec.min_coverage)
        )
    if snap.nan_rate > spec.max_nan_rate:
        problems.append("nan_rate=%.4f > %.4f" % (snap.nan_rate, spec.max_nan_rate))
    return CheckResult(
        "coverage", not problems,
        "block" if spec.required else "warn",
        "%s: %s" % (spec.name, "OK" if not problems else "; ".join(problems)),
        {"field": spec.name, "problems": problems},
    )


def _pit_checks(spec: FieldSpec, frame: pd.DataFrame,
                list_date: Optional[pd.Series]) -> List[CheckResult]:
    if not spec.pit_required:
        return []
    if list_date is None:
        return [CheckResult(
            "pit", False, "warn",
            "%s: list_date 未提供，PIT 无法校验" % spec.name,
            {"field": spec.name, "pit_status": "unavailable"},
        )]
    valid = frame.notna()
    violations = []
    for column in frame.columns:
        if column not in list_date.index:
            continue
        first = valid[column]
        if not first.any():
            continue
        first_date = first[first].index.min()
        listing = pd.Timestamp(list_date.loc[column])
        if pd.isna(listing):
            continue
        if first_date < listing:
            violations.append(str(column))
    if not violations:
        return [CheckResult(
            "pit", True, "block", "%s: PIT OK" % spec.name,
            {"field": spec.name},
        )]
    return [CheckResult(
        "pit", False, "block",
        "%s: %d 只股票在上市日前有值" % (spec.name, len(violations)),
        {"field": spec.name, "violations": violations[:20]},
    )]


def _universe_check(frame: pd.DataFrame,
                    universe: Optional[Sequence[str]]) -> Optional[CheckResult]:
    if universe is None:
        return None
    missing = sorted(set(universe) - set(map(str, frame.columns)))
    return CheckResult(
        "universe", not missing, "block",
        "universe: %s" % ("OK" if not missing else "缺 %d 只" % len(missing)),
        {"missing": missing[:20]},
    )


def _calendar_check(calendar: pd.DatetimeIndex,
                    effective: Optional[pd.Timestamp]) -> CheckResult:
    problems = []
    if len(calendar) == 0:
        problems.append("日历为空")
    if not calendar.is_monotonic_increasing:
        problems.append("日历非单调")
    if calendar.has_duplicates:
        problems.append("日历重复")
    if effective is None:
        problems.append("sample_end 之前无交易日")
    return CheckResult(
        "calendar", not problems, "block",
        "calendar: %s" % ("OK" if not problems else "; ".join(problems)),
        {"problems": problems},
    )


_RETURN_CONSISTENCY_BOUNDS = {
    "decimal": (-1.0, 10.0),
    "%": (-100.0, 1000.0),
}


def _consistency_check(spec: FieldSpec, frame: pd.DataFrame) -> List[CheckResult]:
    if spec.semantic_type != "return":
        return []
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    finite = values[np.isfinite(values)]
    unit = spec.unit or "decimal"
    low, high = _RETURN_CONSISTENCY_BOUNDS.get(
        unit, _RETURN_CONSISTENCY_BOUNDS["decimal"]
    )
    details = {"field": spec.name, "unit": unit, "bounds": [low, high]}
    if finite.size and (finite.min() < low or finite.max() > high):
        return [CheckResult(
            "consistency", False, "warn",
            "%s: return 越界 [%s, %s]" % (spec.name, low, high),
            details,
        )]
    return [CheckResult(
        "consistency", True, "warn", "%s: return OK" % spec.name,
        details,
    )]


def _adj_alignment_check(adj: Optional[pd.DataFrame],
                         price: Optional[pd.DataFrame]) -> Optional[CheckResult]:
    if adj is None or price is None:
        return None
    missing = price.index.difference(adj.index)
    extra = adj.index.difference(price.index)
    passed = len(missing) == 0 and len(extra) == 0
    return CheckResult(
        "adj_alignment", passed, "warn",
        "adj/price 索引: %s（缺 %d 日，多 %d 日）" % (
            "对齐" if passed else "不对齐", len(missing), len(extra)
        ),
        {
            "missing_days": int(len(missing)),
            "extra_days": int(len(extra)),
            "first_missing": _iso(missing.min()) if len(missing) else None,
        },
    )


def _adj_monotonic_check(adj: pd.DataFrame) -> CheckResult:
    significant = 0
    total = 0
    for column in adj.columns:
        series = adj[column].dropna()
        if len(series) < 2:
            continue
        ratio = series.pct_change().dropna()
        total += 1
        if (ratio < -0.001).any():
            significant += 1
    return CheckResult(
        "adj_monotonic", True, "info",
        "adj 单调披露: %d/%d 列存在 >0.1%% 回落" % (significant, total),
        {"significant_columns": significant, "n_columns": total},
    )


# ============================================================
# 缓存
# ============================================================

class ContractCache:
    """按 (field, file, size, mtime_ns, head_digest, calendar_hash, sample_end) 缓存。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._store: Dict[str, Dict[str, Any]] = {}
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    self._store = json.load(handle)
            except (OSError, json.JSONDecodeError):
                logger.warning("契约缓存无法读取，忽略: %s", path)
                self._store = {}

    def get(self, key: str) -> Optional[FieldSnapshot]:
        entry = self.get_entry(key)
        return None if entry is None else entry[0]

    def put(self, key: str, snapshot: FieldSnapshot) -> None:
        self._store[key] = {"snapshot": asdict(snapshot), "checks": []}
        self._flush()

    def get_entry(
        self, key: str
    ) -> Optional[Tuple[FieldSnapshot, List[CheckResult]]]:
        raw = self._store.get(key)
        if raw is None:
            return None
        snapshot = FieldSnapshot(**raw["snapshot"])
        checks = [CheckResult(**item) for item in raw.get("checks", [])]
        return snapshot, checks

    def put_entry(self, key: str, snapshot: FieldSnapshot,
                  checks: List[CheckResult]) -> None:
        self._store[key] = {
            "snapshot": asdict(snapshot),
            "checks": [asdict(c) for c in checks],
        }
        self._flush()

    def _flush(self) -> None:
        if not self.path:
            return
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._store, handle, ensure_ascii=False)


def _cache_key(spec: FieldSpec, path: Path, sample_end: str,
               calendar_hash: str) -> str:
    stat = path.stat()
    body = "|".join([
        spec.name, spec.file or "", spec.reader,
        str(stat.st_size), str(stat.st_mtime_ns),
        _head_digest(path), sample_end, calendar_hash,
    ])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ============================================================
# 公共 API
# ============================================================

def _collect(
    root: Union[str, Path],
    sample_end: Union[str, pd.Timestamp],
    fields: Optional[Sequence[FieldSpec]] = None,
    *,
    trading_calendar: Optional[Any] = None,
    universe: Optional[Sequence[str]] = None,
    list_date: Optional[pd.Series] = None,
    cache: Optional[ContractCache] = None,
    readers: Optional[Mapping[str, Any]] = None,
) -> Tuple[DataSnapshot, List[CheckResult], Tuple[KnownGap, ...], str]:
    root_path = Path(root)
    sample_ts = pd.Timestamp(sample_end)
    specs = tuple(fields) if fields is not None else default_fields()

    calendar, calendar_source, fallback = _resolve_calendar(
        root_path, sample_ts, trading_calendar
    )
    effective = _effective_end(calendar, sample_ts)
    cal_hash = _calendar_hash(calendar)

    snapshots: Dict[str, FieldSnapshot] = {}
    frames: Dict[str, pd.DataFrame] = {}
    checks: List[CheckResult] = []
    gaps: List[KnownGap] = []

    global_checks: List[CheckResult] = [_calendar_check(calendar, effective)]
    if fallback:
        global_checks.append(CheckResult(
            "calendar", False, "warn",
            "交易日历使用 bdate 兜底；节假日会计入 lag（偏差方向：只多不少）",
            {"calendar_source": calendar_source},
        ))

    for spec in specs:
        path = root_path / spec.file if spec.file else None
        exists = bool(path and path.exists())
        if not exists:
            snapshots[spec.name] = _empty_snapshot(spec)
            if spec.missing_semantics == "known_gap":
                code = GAP_CODE_BY_FIELD.get(
                    spec.name, "%s_missing" % spec.name)
                gaps.append(KnownGap(
                    code=code, field=spec.name,
                    start=None, end=None,
                    impact="字段不可用，相关研究须披露",
                    mitigation="专项 B：外部数据采购/换源",
                ))
                checks.append(CheckResult(
                    "schema", False, "info",
                    "%s: 文件不存在（已知缺口）" % spec.name,
                    {"field": spec.name},
                ))
            else:
                checks.append(CheckResult(
                    "schema", False,
                    "block" if spec.required else "warn",
                    "%s: 文件不存在 (%s)" % (spec.name, spec.file),
                    {"field": spec.name},
                ))
            continue

        key = _cache_key(spec, path, str(sample_ts), cal_hash)
        cached = cache.get_entry(key) if cache is not None else None
        if cached is not None:
            snapshot, cached_checks = cached
            snapshots[spec.name] = snapshot
            checks.extend(cached_checks)
            continue

        try:
            frame = _read_frame(root_path, spec, readers)
        except Exception as exc:  # 读取失败按 schema 处理
            snapshots[spec.name] = _empty_snapshot(spec)
            checks.append(CheckResult(
                "schema", False,
                "block" if spec.required else "warn",
                "%s: 读取失败 (%s)" % (spec.name, exc),
                {"field": spec.name},
            ))
            continue

        frames[spec.name] = frame
        snapshot = _make_snapshot(spec, frame, path, effective)
        snapshots[spec.name] = snapshot

        field_checks: List[CheckResult] = []
        field_checks.extend(_schema_checks(spec, frame))
        field_checks.extend(_value_checks(spec, frame))
        field_checks.extend(_consistency_check(spec, frame))
        freshness = _freshness_check(spec, snapshot, effective, calendar)
        if freshness is not None:
            field_checks.append(freshness)
        field_checks.append(_coverage_check(spec, snapshot))
        field_checks.extend(_pit_checks(spec, frame, list_date))
        if spec.name == "price":
            universe_result = _universe_check(frame, universe)
            if universe_result is not None:
                field_checks.append(universe_result)
        checks.extend(field_checks)
        if cache is not None:
            cache.put_entry(key, snapshot, field_checks)

    checks.extend(global_checks)

    # 注：cache 命中路径不保留 frame；跨字段 adj_alignment 仅在本次实际读取
    # 了 adj + price 时执行（首跑），命中缓存的报告不含该检查。
    alignment = _adj_alignment_check(frames.get("adj"), frames.get("price"))
    if alignment is not None:
        checks.append(alignment)
    if "adj" in frames:
        checks.append(_adj_monotonic_check(frames["adj"]))

    snapshot = DataSnapshot(
        as_of=pd.Timestamp.now(tz="UTC").isoformat(),
        sample_end=str(sample_ts.date()),
        fields=snapshots,
        universe_version=None,
        universe_bias="unknown",
        calendar_hash=cal_hash,
    )
    return snapshot, checks, tuple(gaps), calendar_source


def build_snapshot(
    root: Union[str, Path],
    sample_end: Union[str, pd.Timestamp],
    fields: Optional[Sequence[FieldSpec]] = None,
    *,
    trading_calendar: Optional[Any] = None,
    universe: Optional[Sequence[str]] = None,
    list_date: Optional[pd.Series] = None,
    readers: Optional[Mapping[str, Any]] = None,
) -> DataSnapshot:
    snapshot, _checks, _gaps, _source = _collect(
        root, sample_end, fields,
        trading_calendar=trading_calendar, universe=universe,
        list_date=list_date, cache=None, readers=readers,
    )
    return snapshot


CONTRACT_MODES = ("research", "production")


def check_data_contract(
    root: Union[str, Path],
    sample_end: Union[str, pd.Timestamp],
    fields: Optional[Sequence[FieldSpec]] = None,
    *,
    strict: bool = False,
    mode: str = "research",
    trading_calendar: Optional[Any] = None,
    universe: Optional[Sequence[str]] = None,
    list_date: Optional[pd.Series] = None,
    cache: Optional[ContractCache] = None,
    readers: Optional[Mapping[str, Any]] = None,
) -> ContractReport:
    if mode not in CONTRACT_MODES:
        raise ValueError(
            "mode 非法: %r（可选: %s）" % (mode, "/".join(CONTRACT_MODES))
        )
    snapshot, checks, gaps, source = _collect(
        root, sample_end, fields,
        trading_calendar=trading_calendar, universe=universe,
        list_date=list_date, cache=cache, readers=readers,
    )
    if mode == "production":
        # DESIGN §5.3：adj_alignment 在 production 由 warn 升级为 block
        checks = [
            replace(check, severity="block")
            if (check.check == "adj_alignment"
                and not check.passed and check.severity == "warn")
            else check
            for check in checks
        ]
    passed = not any(
        (not check.passed and check.severity == "block") for check in checks
    )
    report = ContractReport(
        passed=passed,
        checks=checks,
        snapshot=snapshot,
        policy_version=POLICY_VERSION,
        known_gaps=gaps,
        calendar_source=source,
    )
    if strict and not passed:
        raise DataContractError(report)
    return report
