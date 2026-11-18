# -*- coding: utf-8 -*-
"""GR-4 多重检验台账 (v3.6.0).

family/variant 预注册 + 全部 trial 入账 + 三分母 + FDR/FWER 双轨校正。
计算核复用 ``backtest.multiple_testing``；本模块**不 import** ``governance``
（DESIGN D1），异常基类为模块内局部定义。

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §7；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.4。
"""
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
)

import numpy as np
import pandas as pd

from .multiple_testing import (
    HansenSPA,
    WhiteRealityCheck,
    apply_bh_fdr,
    apply_bonferroni,
    apply_by_fdr,
)

logger = logging.getLogger(__name__)

POLICY_VERSION = "1.0.0"

# v3.7.0 E5: family stage 约束（stage 不进入指纹，只做一致性校验）
_FAMILY_STAGES = ("factor", "portfolio")
_PORTFOLIO_TRIAL_STAGES = ("S4", "portfolio")


# ============================================================
# 异常（模块内局部定义）
# ============================================================

class PreregistrationError(Exception):
    """family/variant 未预注册，或预注册时序被违反。"""


class TrackMismatchError(Exception):
    """校正轨（FDR/FWER）与方法不匹配。"""


class FamilyConflictError(Exception):
    """同 family 注册冲突 / 多 primary trial / 同 attempt 不同 p。"""


# ============================================================
# 枚举与数据模型
# ============================================================

class CorrectionTrack(str, Enum):
    FDR = "fdr"
    FWER = "fwer"


class CorrectionMethod(str, Enum):
    BH = "benjamini_hochberg"
    BY = "benjamini_yekutieli"
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    ROMANO_WOLF = "romano_wolf"
    WHITE_RC = "white_rc"
    HANSEN_SPA = "hansen_spa"


FDR_METHODS = (CorrectionMethod.BH, CorrectionMethod.BY)
FWER_METHODS = (
    CorrectionMethod.BONFERRONI,
    CorrectionMethod.HOLM,
    CorrectionMethod.ROMANO_WOLF,
    CorrectionMethod.WHITE_RC,
    CorrectionMethod.HANSEN_SPA,
)
JOINT_METHODS = (CorrectionMethod.WHITE_RC, CorrectionMethod.HANSEN_SPA)


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    factor_id: str
    description: str
    spec_hash: str
    kind: str = "confirmatory"          # confirmatory | exploratory


@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    experiment_id: str
    batch_id: str
    description: str
    registered_by: str
    correction_track: CorrectionTrack
    alpha: float = 0.05
    lead_variant_id: str = ""
    n_trials_expected: Optional[int] = None
    holdout_id: Optional[str] = None
    policy_version: str = POLICY_VERSION
    variants: Tuple[VariantSpec, ...] = ()
    stage: str = "factor"               # factor | portfolio（不进入指纹）
    registered_at: Optional[str] = None

    def fingerprint(self) -> str:
        body = {
            "family_id": self.family_id,
            "experiment_id": self.experiment_id,
            "batch_id": self.batch_id,
            "description": self.description,
            "registered_by": self.registered_by,
            "correction_track": self.correction_track.value,
            "alpha": self.alpha,
            "lead_variant_id": self.lead_variant_id,
            "n_trials_expected": self.n_trials_expected,
            "holdout_id": self.holdout_id,
            "policy_version": self.policy_version,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "factor_id": v.factor_id,
                    "spec_hash": v.spec_hash,
                    "kind": v.kind,
                }
                for v in self.variants
            ],
        }
        return _sha256(_canonical_json(body))


@dataclass(frozen=True)
class TrialRecord:
    family_id: str
    variant_id: str
    attempt_id: str
    factor_id: str
    stage: str
    metric_name: str
    metric_value: float
    p_value: Optional[float]
    spec_hash: str
    run_id: Optional[str] = None
    record_id: Optional[str] = None
    executed: bool = True
    primary: bool = False
    note: str = ""
    alternative: str = "two-sided"
    backfilled: bool = False
    created_at: Optional[str] = None


@dataclass
class FamilyResult:
    family_id: str
    method: CorrectionMethod
    track: CorrectionTrack
    alpha: float
    n_trials: int
    n_testable: int
    n_hypotheses: int
    adjusted: Dict[str, float]
    rejected: Dict[str, bool]
    joint_p: Optional[float]
    rejected_any: Optional[bool]
    sensitivity: Dict[str, Any]
    evidence_uri: Optional[str] = None
    lead_variant_id: Optional[str] = None

    def to_markdown(self) -> str:
        lines = [
            "# 多重检验台账 — %s" % self.family_id,
            "",
            "- 方法: `%s`（%s 轨）" % (
                self.method.value, self.track.value
            ),
            "- alpha: %s" % self.alpha,
            "- 分母: n_trials=%d / n_testable=%d / n_hypotheses=%d" % (
                self.n_trials, self.n_testable, self.n_hypotheses
            ),
        ]
        if self.joint_p is not None:
            lines.append(
                "- 联合检验 p=%.6g（joint test, not per-hypothesis）"
                % self.joint_p
            )
        else:
            for variant_id in sorted(self.adjusted):
                lines.append(
                    "- %s: adjusted=%.6g, rejected=%s" % (
                        variant_id, self.adjusted[variant_id],
                        self.rejected[variant_id],
                    )
                )
        return "\n".join(lines)

    def to_record_fields(
        self, extra: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        payload = {
            "n_trials": self.n_trials,
            "n_testable": self.n_testable,
            "n_hypotheses": self.n_hypotheses,
            "test_family": self.family_id,
            "correction_method": self.method.value,
            "p_value": None,
            "q_value": None,
            "adjusted_p": None,
        }
        if self.joint_p is not None:
            payload["adjusted_p"] = self.joint_p
        elif self.adjusted:
            lead = self.lead_variant_id
            if lead not in self.adjusted:
                lead = sorted(self.adjusted)[0]
            value = self.adjusted[lead]
            if self.track == CorrectionTrack.FDR:
                payload["q_value"] = value
            else:
                payload["adjusted_p"] = value
        if extra:
            payload.update(dict(extra))
        return payload


# ============================================================
# 工具
# ============================================================

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _holm_adjusted(p_values: Sequence[float]) -> List[float]:
    """Holm step-down 校正 p 值：max_{j<=i} min(1, (m-j+1)p_(j))。"""
    m = len(p_values)
    if m == 0:
        return []
    order = np.argsort(np.asarray(p_values, dtype=float), kind="stable")
    sorted_p = np.asarray(p_values, dtype=float)[order]
    adjusted_sorted = np.empty(m)
    running = 0.0
    for i in range(m):
        value = min(1.0, (m - i) * float(sorted_p[i]))
        running = max(running, value)
        adjusted_sorted[i] = running
    adjusted = np.empty(m)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist()


def _romano_wolf_fast(
    p_values: Sequence[float],
    bootstrap_p_values: np.ndarray,
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """RW k=1 快速核：k=1 时第 k 小恒为每行最小值，避免逐 j 排序。"""
    p_arr = np.asarray(p_values, dtype=float)
    boot = np.asarray(bootstrap_p_values, dtype=float)
    if boot.ndim != 2:
        raise ValueError("bootstrap_p_values 必须是 2D (B, m)")
    if boot.shape[1] != len(p_arr):
        raise ValueError("bootstrap_p_values 列数 ≠ len(p_values)")
    m = len(p_arr)
    B = boot.shape[0]
    if m == 0:
        return [], []
    order = np.argsort(p_arr, kind="stable")
    sorted_p = p_arr[order]
    sorted_min = np.sort(boot.min(axis=1))
    adjusted_sorted = np.searchsorted(sorted_min, sorted_p, side="right") / B
    adjusted_sorted = np.maximum.accumulate(adjusted_sorted)
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)
    rejected_sorted = np.zeros(m, dtype=bool)
    for j in range(m):
        if adjusted_sorted[j] <= alpha:
            rejected_sorted[j] = True
        else:
            break
    adjusted = np.empty(m)
    adjusted[order] = adjusted_sorted
    rejected = np.zeros(m, dtype=bool)
    rejected[order] = rejected_sorted
    return adjusted.tolist(), rejected.tolist()


def _family_payload(spec: FamilySpec) -> Dict[str, Any]:
    payload = asdict(spec)
    payload["correction_track"] = spec.correction_track.value
    payload["variants"] = [asdict(v) for v in spec.variants]
    return payload


# ============================================================
# 台账
# ============================================================

class MultipleTestingLedger:
    """append-only 多重检验台账（DuckDB）。"""

    def __init__(
        self,
        db_path: str = "factor_db.duckdb",
        table_prefix: str = "mt_",
        enable: bool = True,
        strict_preregistration: bool = True,
        holdout_checker: Optional[Callable[[str, str], None]] = None,
    ):
        if not table_prefix.replace("_", "").isalnum():
            raise ValueError("非法 table_prefix: %r" % table_prefix)
        self.db_path = db_path
        self.prefix = table_prefix
        self.enable = enable
        self.strict_preregistration = strict_preregistration
        self.holdout_checker = holdout_checker
        self._conn = None
        if enable:
            self._connect()

    # —— 存储 ——
    def _table(self, name: str) -> str:
        return self.prefix + name

    def _connect(self):
        if self._conn is not None:
            return self._conn
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("duckdb 不可用，台账无法启用") from exc
        self._conn = duckdb.connect(self.db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS {family} (
                family_id VARCHAR PRIMARY KEY,
                fingerprint VARCHAR NOT NULL,
                payload JSON NOT NULL,
                registered_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {variant} (
                family_id VARCHAR,
                variant_id VARCHAR,
                spec_hash VARCHAR NOT NULL,
                payload JSON NOT NULL,
                PRIMARY KEY (family_id, variant_id)
            );
            CREATE TABLE IF NOT EXISTS {trial} (
                entry_id VARCHAR PRIMARY KEY,
                family_id VARCHAR,
                variant_id VARCHAR,
                attempt_id VARCHAR,
                p_value DOUBLE,
                payload JSON NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {result} (
                result_id VARCHAR PRIMARY KEY,
                family_id VARCHAR,
                method VARCHAR,
                alpha DOUBLE,
                payload JSON NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
            """.format(
                family=self._table("family"),
                variant=self._table("variant"),
                trial=self._table("trial"),
                result=self._table("result"),
            )
        )
        return self._conn

    def _load_family(self, family_id: str) -> FamilySpec:
        if not self.enable:
            raise PreregistrationError("台账未启用")
        self._connect()
        row = self._conn.execute(
            "SELECT payload FROM {t} WHERE family_id = ?".format(
                t=self._table("family")
            ),
            [family_id],
        ).fetchone()
        if row is None:
            raise PreregistrationError("family 未注册: %s" % family_id)
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        data["variants"] = tuple(VariantSpec(**v) for v in data["variants"])
        data["correction_track"] = CorrectionTrack(data["correction_track"])
        return FamilySpec(**data)

    def _load_trials(self, family_id: str) -> List[TrialRecord]:
        self._connect()
        rows = self._conn.execute(
            "SELECT payload FROM {t} WHERE family_id = ?".format(
                t=self._table("trial")
            ),
            [family_id],
        ).fetchall()
        trials = []
        for (payload,) in rows:
            data = json.loads(payload) if isinstance(payload, str) else payload
            trials.append(TrialRecord(**data))
        return trials

    # —— 公共 API ——
    def register_family(self, spec: FamilySpec) -> str:
        if not self.enable:
            return ""
        if not spec.variants:
            raise FamilyConflictError("family 必须至少有一个 variant")
        if spec.stage not in _FAMILY_STAGES:
            raise FamilyConflictError(
                "非法 family stage: %s" % spec.stage)
        if spec.holdout_id and self.holdout_checker is not None:
            self.holdout_checker(spec.holdout_id, spec.batch_id)
        ids = [v.variant_id for v in spec.variants]
        if len(ids) != len(set(ids)):
            raise FamilyConflictError("variant_id 重复")
        for variant in spec.variants:
            if variant.kind not in ("confirmatory", "exploratory"):
                raise FamilyConflictError("非法 variant kind: %s" % variant.kind)
        if not spec.lead_variant_id:
            spec = replace(spec, lead_variant_id=spec.variants[0].variant_id)
        if spec.lead_variant_id not in ids:
            raise FamilyConflictError("lead_variant_id 不在 variants 中")

        self._connect()
        fingerprint = spec.fingerprint()
        row = self._conn.execute(
            "SELECT fingerprint FROM {t} WHERE family_id = ?".format(
                t=self._table("family")
            ),
            [spec.family_id],
        ).fetchone()
        if row is not None:
            if row[0] == fingerprint:
                return spec.family_id
            raise FamilyConflictError("family 已存在且指纹不同: %s" % spec.family_id)

        stored = replace(spec, registered_at=_utc_now())
        self._conn.execute(
            "INSERT INTO {t} VALUES (?, ?, CAST(? AS JSON), ?)".format(
                t=self._table("family")
            ),
            [stored.family_id, fingerprint,
             json.dumps(_family_payload(stored), ensure_ascii=False),
             _parse_time(stored.registered_at)],
        )
        for variant in stored.variants:
            self._conn.execute(
                "INSERT INTO {t} VALUES (?, ?, ?, CAST(? AS JSON))".format(
                    t=self._table("variant")
                ),
                [stored.family_id, variant.variant_id, variant.spec_hash,
                 json.dumps(asdict(variant), ensure_ascii=False)],
            )
        return stored.family_id

    def record_trial(
        self, trial: TrialRecord, *, backfill: bool = False,
        exploratory: bool = False,
    ) -> str:
        if not self.enable:
            return ""
        family = self._load_family(trial.family_id)
        if family.stage == "portfolio":
            if trial.stage not in _PORTFOLIO_TRIAL_STAGES:
                raise FamilyConflictError(
                    "portfolio family 不接受 stage=%s 的 trial"
                    % trial.stage)
        elif trial.stage in _PORTFOLIO_TRIAL_STAGES:
            raise FamilyConflictError(
                "factor family 不接受 stage=%s 的 trial" % trial.stage)
        variants = {v.variant_id: v for v in family.variants}
        variant = variants.get(trial.variant_id)

        if variant is not None:
            if exploratory and variant.kind == "confirmatory":
                raise PreregistrationError(
                    "confirmatory variant 不得以 exploratory=True 记录"
                )
        else:
            if not exploratory:
                raise PreregistrationError(
                    "variant 未预注册: %s" % trial.variant_id
                )
            self._connect()
            self._conn.execute(
                "INSERT INTO {t} VALUES (?, ?, ?, CAST(? AS JSON))".format(
                    t=self._table("variant")
                ),
                [family.family_id, trial.variant_id, trial.spec_hash,
                 json.dumps({
                     "variant_id": trial.variant_id,
                     "factor_id": trial.factor_id,
                     "description": "exploratory (auto)",
                     "spec_hash": trial.spec_hash,
                     "kind": "exploratory",
                 }, ensure_ascii=False)],
            )

        if backfill:
            if not trial.created_at:
                raise PreregistrationError(
                    "backfill=True 必须显式提供 created_at"
                )
            created = _parse_time(trial.created_at)
        else:
            created = _parse_time(trial.created_at) if trial.created_at else None
            if created is None:
                created = _parse_time(_utc_now())
            registered = _parse_time(family.registered_at)
            if registered is not None and created < registered:
                raise PreregistrationError(
                    "trial.created_at 早于 family.registered_at"
                )

        stored = replace(
            trial,
            created_at=created.isoformat() if created else None,
            backfilled=bool(backfill or trial.backfilled),
        )
        entry_id = _sha256("|".join([
            stored.family_id, stored.variant_id, stored.attempt_id,
        ]))
        row = self._conn.execute(
            "SELECT p_value FROM {t} WHERE entry_id = ?".format(
                t=self._table("trial")
            ),
            [entry_id],
        ).fetchone()
        if row is not None:
            same = (row[0] is None and stored.p_value is None) or (
                row[0] is not None and stored.p_value is not None
                and abs(float(row[0]) - float(stored.p_value)) <= 1e-15
            )
            if same:
                return entry_id
            raise FamilyConflictError(
                "同 attempt_id 对应不同 p_value: %s" % entry_id
            )

        self._conn.execute(
            "INSERT INTO {t} VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), ?)".format(
                t=self._table("trial")
            ),
            [entry_id, stored.family_id, stored.variant_id,
             stored.attempt_id, stored.p_value,
             json.dumps(asdict(stored), ensure_ascii=False),
             _parse_time(stored.created_at)],
        )
        return entry_id

    def record_trials(
        self, trials: Iterable[TrialRecord], *, backfill: bool = False,
        exploratory: bool = False,
    ) -> int:
        count = 0
        for trial in trials:
            self.record_trial(
                trial, backfill=backfill, exploratory=exploratory
            )
            count += 1
        return count

    def apply(
        self,
        family_id: str,
        method: Optional[CorrectionMethod] = None,
        *,
        alpha: Optional[float] = None,
        bootstrap_p_values: Optional[np.ndarray] = None,
        returns_matrix: Optional[np.ndarray] = None,
        benchmark_index: int = 0,
        bootstrap_indices: Optional[np.ndarray] = None,
        allow_alpha_override: bool = False,
    ) -> FamilyResult:
        if not self.enable:
            return self._empty_result(family_id, method, alpha)

        family = self._load_family(family_id)
        if method is None:
            method = (CorrectionMethod.BH
                      if family.correction_track == CorrectionTrack.FDR
                      else CorrectionMethod.BONFERRONI)
        if family.correction_track == CorrectionTrack.FDR:
            if method not in FDR_METHODS:
                raise TrackMismatchError(
                    "FDR 轨不允许方法 %s" % method.value
                )
        else:
            if method not in FWER_METHODS:
                raise TrackMismatchError(
                    "FWER 轨不允许方法 %s" % method.value
                )

        alpha_used = family.alpha if alpha is None else float(alpha)
        if alpha is not None and abs(alpha - family.alpha) > 1e-15 \
                and not allow_alpha_override:
            raise FamilyConflictError(
                "alpha 已预注册为 %s，覆盖需 allow_alpha_override=True"
                % family.alpha
            )

        trials = self._load_trials(family_id)
        variants = {v.variant_id: v for v in family.variants}
        n_trials = len(trials)
        n_testable = sum(1 for t in trials if t.p_value is not None)

        grouped: Dict[str, List[TrialRecord]] = {}
        for trial in trials:
            if trial.backfilled:
                continue
            variant = variants.get(trial.variant_id)
            if variant is None or variant.kind != "confirmatory":
                continue
            grouped.setdefault(trial.variant_id, []).append(trial)

        primaries: List[TrialRecord] = []
        for variant_id in sorted(grouped):
            rows = grouped[variant_id]
            declared = [r for r in rows if r.primary]
            if len(declared) > 1:
                raise FamilyConflictError(
                    "variant %s 存在多个 primary trial" % variant_id
                )
            chosen = declared[0] if declared else sorted(
                rows, key=lambda r: (r.created_at or "", r.attempt_id)
            )[0]
            if chosen.p_value is not None:
                primaries.append(chosen)

        n_hypotheses = len(primaries)
        p_list = [float(t.p_value) for t in primaries]
        variant_order = [t.variant_id for t in primaries]

        adjusted: Dict[str, float] = {}
        rejected: Dict[str, bool] = {}
        joint_p: Optional[float] = None
        rejected_any: Optional[bool] = None

        if method in (CorrectionMethod.BH, CorrectionMethod.BY,
                      CorrectionMethod.BONFERRONI):
            func = {
                CorrectionMethod.BH: apply_bh_fdr,
                CorrectionMethod.BY: apply_by_fdr,
                CorrectionMethod.BONFERRONI: apply_bonferroni,
            }[method]
            values, _ = func(p_list, alpha_used)
            adjusted = dict(zip(variant_order, values))
            rejected = {
                key: bool(value <= alpha_used)
                for key, value in adjusted.items()
            }
            rejected_any = any(rejected.values()) if rejected else False
        elif method == CorrectionMethod.HOLM:
            values = _holm_adjusted(p_list)
            adjusted = dict(zip(variant_order, values))
            rejected = {
                key: bool(value <= alpha_used)
                for key, value in adjusted.items()
            }
            rejected_any = any(rejected.values()) if rejected else False
        elif method == CorrectionMethod.ROMANO_WOLF:
            if bootstrap_p_values is None:
                raise ValueError("ROMANO_WOLF 需要 bootstrap_p_values")
            boot = np.asarray(bootstrap_p_values, dtype=float)
            if boot.ndim != 2 or boot.shape[1] != len(p_list):
                raise ValueError("bootstrap_p_values 形状必须为 (B, m)")
            values, flags = _romano_wolf_fast(p_list, boot, alpha_used)
            adjusted = dict(zip(variant_order, values))
            rejected = dict(zip(variant_order, flags))
            rejected_any = any(rejected.values()) if rejected else False
        else:
            if returns_matrix is None:
                raise ValueError("%s 需要 returns_matrix" % method.value)
            if bootstrap_indices is not None:
                n_bootstrap = int(np.asarray(bootstrap_indices).shape[0])
            elif bootstrap_p_values is not None:
                n_bootstrap = int(np.asarray(bootstrap_p_values).shape[0])
            else:
                n_bootstrap = 1000
            tester = (WhiteRealityCheck(n_bootstrap=n_bootstrap)
                      if method == CorrectionMethod.WHITE_RC
                      else HansenSPA(n_bootstrap=n_bootstrap))
            result = tester.test(
                returns_matrix, benchmark_index=benchmark_index,
                alpha=alpha_used, bootstrap_indices=bootstrap_indices,
            )
            joint_p = float(
                result["rc_p_value"] if method == CorrectionMethod.WHITE_RC
                else result["spa_p_value"]
            )
            rejected = {vid: bool(joint_p <= alpha_used)
                        for vid in variant_order}
            rejected_any = bool(joint_p <= alpha_used)

        sensitivity: Dict[str, Any] = {
            "n_trials": n_trials,
            "n_testable": n_testable,
        }
        if method in (CorrectionMethod.BH, CorrectionMethod.BY,
                      CorrectionMethod.BONFERRONI, CorrectionMethod.HOLM):
            p_sensitivity = [
                float(t.p_value) if t.p_value is not None else 1.0
                for t in trials
            ]
            if method == CorrectionMethod.BH:
                sens_values, _ = apply_bh_fdr(p_sensitivity, alpha_used)
            elif method == CorrectionMethod.BY:
                sens_values, _ = apply_by_fdr(p_sensitivity, alpha_used)
            elif method == CorrectionMethod.BONFERRONI:
                sens_values, _ = apply_bonferroni(p_sensitivity, alpha_used)
            else:
                sens_values = _holm_adjusted(p_sensitivity)
            sensitivity["min_adjusted"] = (
                float(min(sens_values)) if sens_values else None
            )
            sensitivity["n_rejected"] = int(
                sum(1 for v in sens_values if v <= alpha_used)
            )
        else:
            sensitivity["joint_p"] = joint_p

        result = FamilyResult(
            family_id=family.family_id,
            method=method,
            track=family.correction_track,
            alpha=alpha_used,
            n_trials=n_trials,
            n_testable=n_testable,
            n_hypotheses=n_hypotheses,
            adjusted=adjusted,
            rejected=rejected,
            joint_p=joint_p,
            rejected_any=rejected_any,
            sensitivity=sensitivity,
            lead_variant_id=family.lead_variant_id,
        )
        self._persist_result(family, result)
        return result

    def query_trials(self, family_id: str) -> pd.DataFrame:
        if not self.enable:
            return pd.DataFrame()
        self._connect()
        return self._conn.execute(
            """
            SELECT entry_id, family_id, variant_id, attempt_id,
                   p_value, created_at
            FROM {t}
            WHERE family_id = ?
            ORDER BY created_at, entry_id
            """.format(t=self._table("trial")),
            [family_id],
        ).df()

    def report(self, family_id: str) -> FamilyResult:
        return self.apply(family_id)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # —— 内部 ——
    def _persist_result(self, family: FamilySpec,
                        result: FamilyResult) -> None:
        confirmatory_ids = sorted(
            _sha256("|".join([t.family_id, t.variant_id, t.attempt_id]))
            for t in self._load_trials(family.family_id)
            if not t.backfilled
            and any(v.variant_id == t.variant_id
                    and v.kind == "confirmatory"
                    for v in family.variants)
        )
        result_id = _sha256("|".join([
            family.fingerprint(), result.method.value, repr(result.alpha),
            ",".join(confirmatory_ids), family.policy_version,
        ]))
        row = self._conn.execute(
            "SELECT result_id FROM {t} WHERE result_id = ?".format(
                t=self._table("result")
            ),
            [result_id],
        ).fetchone()
        if row is not None:
            return
        payload = {
            "family_id": result.family_id,
            "method": result.method.value,
            "track": result.track.value,
            "alpha": result.alpha,
            "n_trials": result.n_trials,
            "n_testable": result.n_testable,
            "n_hypotheses": result.n_hypotheses,
            "adjusted": result.adjusted,
            "rejected": result.rejected,
            "joint_p": result.joint_p,
            "rejected_any": result.rejected_any,
            "sensitivity": result.sensitivity,
            "evidence_uri": result.evidence_uri,
            "policy_version": family.policy_version,
        }
        self._conn.execute(
            "INSERT INTO {t} VALUES (?, ?, ?, ?, CAST(? AS JSON), ?)".format(
                t=self._table("result")
            ),
            [result_id, result.family_id, result.method.value,
             result.alpha, json.dumps(payload, ensure_ascii=False),
             _parse_time(_utc_now())],
        )

    def _empty_result(
        self, family_id: str, method: Optional[CorrectionMethod],
        alpha: Optional[float],
    ) -> FamilyResult:
        method = method or CorrectionMethod.BH
        return FamilyResult(
            family_id=family_id, method=method,
            track=(CorrectionTrack.FDR if method in FDR_METHODS
                   else CorrectionTrack.FWER),
            alpha=0.05 if alpha is None else float(alpha),
            n_trials=0, n_testable=0, n_hypotheses=0,
            adjusted={}, rejected={}, joint_p=None, rejected_any=None,
            sensitivity={}, lead_variant_id=None,
        )
