# -*- coding: utf-8 -*-
"""GR-1 治理记录与存储 (v3.6.0).

单一真相源：所有治理结论落 ``GovernanceRecord``，报告只引用 ``record_id``。
本模块与 ``data_contract`` / ``golden_master`` / ``multiple_testing_ledger``
**互不 import**（DESIGN D1）；DuckDB 为 lazy import，JSONL backend 在无
duckdb 环境下必须可用。

设计依据：``docs/private/DESIGN_GOVERNANCE_BASE.md`` §4；
实施依据：``docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md`` §2.1。
"""
import hashlib
import json
import logging
import math
import os
import platform
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
GATE_NAMES = ("G0", "G1", "G2", "G3", "G3.5", "G4", "G5")

# 口径枚举（DESIGN §5.7.2）；qfq 禁止进入 production / golden（G4）
PRICE_CONVENTIONS: Tuple[str, ...] = (
    "hfq", "raw+adj_factor", "qfq", "total_return",
)
ST_SOURCES: Tuple[str, ...] = ("name_proxy", "official_flag")
SUSPEND_SOURCES: Tuple[str, ...] = (
    "event_rebuild", "amount_proxy", "daily_flag",
)
TRADABLE_SOURCE_DEFAULTS: Dict[str, str] = {
    "st_source": "name_proxy",
    "suspend_source": "event_rebuild",
}

# 参与 record_id 的输入身份字段（结果字段不参与）
ID_FIELDS: Tuple[str, ...] = (
    "batch_id", "parent_id", "experiment_id", "factor_id", "variant_id",
    "stage", "status", "mode", "arm",
    "pipeline_version", "config_hash", "construction_code_hash",
    "gate_policy_version",
    "data_snapshot_hash", "universe_version", "sample_window", "split_id",
    "holdout_locked_at",
    "benchmark_id", "price_convention", "return_convention",
    "tradable_convention", "cost_model",
    "sign_convention",
    "seed",
)

# 参与 record_id 且带模型默认值的字段：build() 必须在算 id 前注入默认，
# 否则「省略」与「显式传默认值」两条语义等价的输入会得到不同 record_id
# （复审 R1 / 修复包 F1；DR-F1）
ID_DEFAULTS: Dict[str, Any] = {
    "price_convention": "hfq",
    "gate_policy_version": "1.0.0",
}

# payload_hash 排除的易变/运维字段
HASH_EXCLUDED: FrozenSet[str] = frozenset({
    "record_id", "schema_version", "timestamp", "reviewer",
    "evidence_uri", "env_fingerprint", "notes",
})


# ============================================================
# 异常（模块内局部定义，不跨模块 import）
# ============================================================

class GovernanceError(Exception):
    """治理模块基础异常。"""


class ReproducibilityConflictError(GovernanceError):
    """同一 record_id 对应不同 payload —— 结果不可复现。"""


# ============================================================
# 枚举
# ============================================================

class Stage(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    FINAL = "final"
    PORTFOLIO = "portfolio"
    RECHECK = "recheck"


class Mode(str, Enum):
    RESEARCH = "research"
    PRODUCTION = "production"


class RecordStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class Arm(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    MIXED = "mixed"


class GateResultPayload(BaseModel):
    """门禁结论来源披露（B29）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    reasons: List[str]
    action: Literal["block", "downgrade", "allow"]
    evidence_refs: List[str]
    evaluated_by: Literal["human", "script", "ledger"]


# ============================================================
# 时间 / JSON 归一化
# ============================================================

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_time(value: Any) -> Optional[str]:
    """统一为带时区 UTC ISO 8601；无法解析时原样返回。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return datetime(
            value.year, value.month, value.day, tzinfo=timezone.utc
        ).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return text
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return value


def _jsonable(obj: Any) -> Any:
    """把 Enum / Mapping / 序列 / 时间 / NaN 归一为可稳定序列化对象。"""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Mapping):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, (datetime, date)):
        return _normalize_time(obj)
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            return _jsonable(obj.item())
        except (ValueError, TypeError):
            return obj
    return obj


def canonical_json(obj: Any) -> str:
    """稳定 JSON：键排序 + 紧凑分隔符；Enum 取 value，NaN → None。

    快路径（性能包 O1）：``model_dump(mode="json")`` 产物已是 JSON-native，
    直接 dumps 可省去 Python 层递归 ``_jsonable``（10k 记录约 0.6s）；
    非 native 值触发 TypeError、NaN 触发 ValueError 时回退原路径，语义不变。
    """
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return json.dumps(
            _jsonable(obj),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )


def _as_mapping(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def compute_record_id(fields: Mapping[str, Any]) -> str:
    """record_id = 输入身份字段的 SHA256（结果字段不参与）。"""
    payload = {key: _jsonable(fields.get(key)) for key in ID_FIELDS}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_payload_hash(payload: Mapping[str, Any]) -> str:
    """payload_hash = 全 payload 排除易变/运维字段后的 SHA256。"""
    # 性能包 O1：payload 来自 model_dump(mode="json") 时为 JSON-native，
    # 不再逐字段走 _jsonable（10k 记录约 0.4s）；非 native / NaN 由
    # canonical_json 回退路径按原语义归一。
    body = {
        str(key): value
        for key, value in payload.items()
        if key not in HASH_EXCLUDED
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _compute_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """数据快照稳定子集 hash：排除 as_of 与 file_fingerprint（F-A）。"""
    if not snapshot:
        return ""
    stable: Dict[str, Any] = {}
    for key, value in snapshot.items():
        if key == "as_of":
            continue
        if key == "fields" and isinstance(value, Mapping):
            stable[key] = {
                name: {
                    k: v for k, v in field.items()
                    if k != "file_fingerprint"
                }
                for name, field in value.items()
            }
        else:
            stable[key] = value
    return hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()


def env_fingerprint() -> Dict[str, Any]:
    """运行环境指纹：版本 + BLAS + 线程环境变量（不引入 threadpoolctl）。"""
    info: Dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
    }
    try:
        import numpy as np

        info["numpy"] = np.__version__
        config = getattr(getattr(np, "__config__", None), "CONFIG", None)
        blas = "unknown"
        if isinstance(config, Mapping):
            try:
                blas = (
                    config.get("Build Dependencies", {})
                    .get("blas", {})
                    .get("name", "unknown")
                )
            except AttributeError:
                blas = "unknown"
        info["blas"] = blas
    except ImportError:
        info["numpy"] = "missing"
        info["blas"] = "unknown"
    try:
        import pandas as pd

        info["pandas"] = pd.__version__
    except ImportError:
        info["pandas"] = "missing"
    try:
        import scipy

        info["scipy"] = scipy.__version__
    except ImportError:
        info["scipy"] = "missing"
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                 "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        info["threads_%s" % name] = os.environ.get(name, "unset")
    return info


def code_commit(repo_root: Optional[str] = None) -> Optional[str]:
    """当前 git commit；失败返回 None（不阻断治理记录）。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


# ============================================================
# GovernanceRecord
# ============================================================

class GovernanceRecord(BaseModel):
    """不可变治理记录（D3）。

    身份字段决定 ``record_id``；结果字段不参与。``build()`` 负责补全
    时间/环境/快照 hash 并计算 id；``model_validator`` 只读校验。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # —— 身份（7）——
    record_id: str
    schema_version: str = SCHEMA_VERSION
    batch_id: str
    parent_id: Optional[str] = None
    experiment_id: str
    factor_id: str
    variant_id: Optional[str] = None

    # —— 阶段（4）——
    stage: Stage
    status: RecordStatus = RecordStatus.ACTIVE
    mode: Mode = Mode.RESEARCH
    arm: Optional[Arm] = None

    # —— 处理（5）——
    pipeline_version: str
    config_hash: str
    construction_code_hash: str
    construction_version_known: bool = True
    gate_policy_version: str = "1.0.0"

    # —— 数据（6）——
    data_snapshot: Dict[str, Any]
    data_snapshot_hash: str
    universe_version: Optional[str] = None
    sample_window: Dict[str, str]
    split_id: Optional[str] = None
    holdout_locked_at: Optional[str] = None

    # —— 口径（6）——
    benchmark_id: str
    price_convention: str = "hfq"
    return_convention: str
    tradable_convention: Dict[str, Any]
    cost_model: Dict[str, Any]
    sign_convention: str

    # —— 结果（条件必填）——
    seed: Optional[int] = None
    tau: Optional[float] = None
    health_score: Optional[float] = None
    premium_health: Optional[float] = None
    diagnosis: Optional[Dict[str, Any]] = None
    p_value: Optional[float] = None
    q_value: Optional[float] = None
    adjusted_p: Optional[float] = None
    n_trials: Optional[int] = None
    n_testable: Optional[int] = None
    n_hypotheses: Optional[int] = None
    test_family: Optional[str] = None
    correction_method: Optional[str] = None
    effect_metric: Optional[str] = None
    effect_size: Optional[float] = None
    ci: Optional[Tuple[float, float]] = None
    dsr: Optional[float] = None
    pbo: Optional[float] = None
    oos_metric: Optional[Dict[str, Any]] = None
    capacity_estimate: Optional[Dict[str, Any]] = None
    gate_status: Dict[str, GateResultPayload] = Field(default_factory=dict)
    drift_alerts: List[Dict[str, Any]] = Field(default_factory=list)

    # —— 运维（5）——
    reviewer: Optional[str] = None
    timestamp: Optional[str] = None
    evidence_uri: Optional[str] = None
    env_fingerprint: Optional[Dict[str, Any]] = None
    notes: str = ""

    @classmethod
    def build(cls, **fields: Any) -> "GovernanceRecord":
        """补默认值 → 计算 record_id → 一次构造（frozen 语义）。"""
        data = dict(fields)
        data.pop("record_id", None)

        data["timestamp"] = _normalize_time(data.get("timestamp")) or _utc_now()
        if data.get("holdout_locked_at") is not None:
            data["holdout_locked_at"] = _normalize_time(
                data["holdout_locked_at"]
            )
        for key in ("tradable_convention", "cost_model"):
            if key in data:
                data[key] = _as_mapping(data[key])
        # 代理口径必须写入 record（DESIGN §5.7.2 H1）：缺省补默认，显式值保留
        tradable = data.get("tradable_convention")
        if isinstance(tradable, Mapping):
            data["tradable_convention"] = {
                **TRADABLE_SOURCE_DEFAULTS, **dict(tradable)
            }
        if isinstance(data.get("sample_window"), Mapping):
            data["sample_window"] = {
                str(k): (v if isinstance(v, str) else _normalize_time(v))
                for k, v in data["sample_window"].items()
            }
        if not data.get("data_snapshot_hash"):
            data["data_snapshot_hash"] = _compute_snapshot_hash(
                data.get("data_snapshot") or {}
            )
        if data.get("env_fingerprint") is None:
            data["env_fingerprint"] = env_fingerprint()
        # ID 默认值注入（DR-F1）：在计算 record_id 之前，保证省略 == 显式默认
        for _key, _default in ID_DEFAULTS.items():
            data.setdefault(_key, _default)
        data["record_id"] = compute_record_id(data)
        return cls(**data)

    @model_validator(mode="after")
    def _validate_stage_requirements(self) -> "GovernanceRecord":
        # gate_status 键约束（B29）
        unknown = set(self.gate_status) - set(GATE_NAMES)
        if unknown:
            raise ValueError("未知 gate_status 键: %s" % sorted(unknown))

        # 标量合法区间
        for name in ("p_value", "q_value", "adjusted_p"):
            value = getattr(self, name)
            if value is not None and not (0.0 <= value <= 1.0):
                raise ValueError("%s 必须在 [0, 1]" % name)

        # 价格复权口径（DESIGN §5.7.2 H3）：qfq 破坏可复现性
        if self.price_convention not in PRICE_CONVENTIONS:
            raise ValueError("price_convention 非法: %r" % self.price_convention)
        # golden 场景 = G4 存在且通过（DR-F2）：G4 失败的留档记录不是基线，
        # 允许其携带 qfq 记录失败证据；G4 通过则拒绝 qfq（防回归）
        _g4 = self.gate_status.get("G4")
        golden = bool(_g4 is not None and getattr(_g4, "passed", False))
        if self.price_convention == "qfq" and (
            self.mode == Mode.PRODUCTION or golden
        ):
            raise ValueError(
                "price_convention='qfq' 禁止用于 production/golden（防回归）")

        # ST/停牌代理口径必须写入且枚举合法（H1）
        missing_sources = [
            k for k in TRADABLE_SOURCE_DEFAULTS
            if not self.tradable_convention.get(k)
        ]
        if missing_sources:
            raise ValueError(
                "tradable_convention 缺少代理口径: %s" % missing_sources)
        if self.tradable_convention["st_source"] not in ST_SOURCES:
            raise ValueError(
                "st_source 非法: %r" % self.tradable_convention["st_source"])
        if self.tradable_convention["suspend_source"] not in SUSPEND_SOURCES:
            raise ValueError(
                "suspend_source 非法: %r"
                % self.tradable_convention["suspend_source"])
        if self.ci is not None and self.ci[0] > self.ci[1]:
            raise ValueError("ci 需满足 low <= high")
        counters = (self.n_trials, self.n_testable, self.n_hypotheses)
        if all(v is not None for v in counters):
            if not (counters[0] >= counters[1] >= counters[2]):
                raise ValueError("需满足 n_trials >= n_testable >= n_hypotheses")

        stage = self.stage
        if stage == Stage.S0:
            self._require(
                ["test_family", "holdout_locked_at", "construction_code_hash"],
                "S0",
            )
        elif stage == Stage.S1:
            self._require(["data_snapshot", "data_snapshot_hash"], "S1")
            self._require_gate("G0", "S1")
        elif stage == Stage.S2:
            self._require(["config_hash", "arm", "pipeline_version"], "S2")
            self._require_gate("G1", "S2")
        elif stage in (Stage.S3, Stage.FINAL, Stage.PORTFOLIO):
            self._require(
                ["test_family", "correction_method", "effect_metric",
                 "effect_size", "ci"],
                stage.value,
            )
            if self.effect_metric not in ("lambda_mean", "ic_mean", "sharpe"):
                raise ValueError("effect_metric 非法: %r" % self.effect_metric)
            if not self.n_trials or self.n_trials < 1:
                raise ValueError("S3 及以后要求 n_trials >= 1")
            if all(v is None for v in (self.p_value, self.q_value,
                                       self.adjusted_p)):
                raise ValueError("S3 及以后要求 p_value/q_value/adjusted_p 之一")
        elif stage == Stage.S4:
            self._require(["capacity_estimate"], "S4")
            self._require_gate("G3.5", "S4")

        if stage in (Stage.S5, Stage.S6):
            if self.mode == Mode.RESEARCH:
                raise ValueError("研究记录不得使用 S5/S6（研究止于 S4）")
            self._require_production_gates()

        if self.mode == Mode.PRODUCTION:
            if stage not in (Stage.S5, Stage.S6):
                raise ValueError("production 记录必须处于 S5/S6")
            if self.status != RecordStatus.ACTIVE:
                raise ValueError("production 记录 status 必须为 active")
            self._require_production_gates()

        if stage in (Stage.PORTFOLIO, Stage.RECHECK) or \
                self.status == RecordStatus.RETIRED:
            if not self.parent_id:
                raise ValueError("portfolio/recheck/retired 必须提供 parent_id")
        return self

    def _require(self, names: List[str], stage: str) -> None:
        missing = [n for n in names if getattr(self, n, None) in (None, "", {}, [])]
        if missing:
            raise ValueError("%s 缺少必填字段: %s" % (stage, missing))

    def _require_gate(self, name: str, stage: str) -> None:
        if name not in self.gate_status:
            raise ValueError("%s 缺少 gate_status[%s]" % (stage, name))

    def _require_production_gates(self) -> None:
        missing = [g for g in GATE_NAMES if g not in self.gate_status]
        if missing:
            raise ValueError("production 缺少门禁: %s" % missing)
        failed = [
            g for g in GATE_NAMES if not self.gate_status[g].passed
        ]
        if failed:
            raise ValueError("production 门禁未通过: %s" % failed)
        if not self.reviewer:
            raise ValueError("production 必须提供 reviewer")


# ============================================================
# 存储
# ============================================================

_LOCKS_GUARD = threading.Lock()
_FILE_LOCKS: Dict[str, threading.Lock] = {}


def _thread_lock(path: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(path, threading.Lock())


@contextmanager
def _file_lock(lock_path: Optional[str]):
    """进程内 + 跨进程文件锁（Windows msvcrt / POSIX fcntl）。"""
    if not lock_path:
        yield
        return
    parent = os.path.dirname(os.path.abspath(lock_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _thread_lock(os.path.abspath(lock_path)):
        handle = open(lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


_TABLE_COLUMNS = (
    "record_id", "schema_version", "factor_id", "batch_id",
    "experiment_id", "stage", "mode", "status",
)


@dataclass(frozen=True)
class AncestorEntry:
    """`ancestors()` 单条结果：``record is None`` 表示断链（DESIGN §4.4）。

    对标 ``git rev-list --missing=print``：遍历不中断，缺失节点以显式标记
    返回，而不是静默截断或整条抛错。
    """

    record_id: str
    record: Optional[GovernanceRecord]
    broken_link: bool = False
    reason: str = ""          # "" | "missing" | "schema_mismatch"


class _LegacyGovernanceRecord(GovernanceRecord):
    """更旧 schema 的宽松副本：补默认值 + extra=allow + ``legacy=True``。"""

    model_config = ConfigDict(frozen=True, extra="allow")

    legacy: bool = True


def _schema_tuple(version: Any) -> Tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).split("."))
    except (TypeError, ValueError):
        return ()


class GovernanceStore:
    """append-only 治理记录存储（DuckDB 主 / JSONL fallback）。"""

    def __init__(
        self,
        db_path: str = "factor_db.duckdb",
        table: str = "governance_record",
        backend: str = "duckdb",
        enable: bool = True,
        on_conflict: str = "error",
        lock_path: Optional[str] = None,
    ):
        if backend not in ("duckdb", "jsonl"):
            raise ValueError("backend 必须是 duckdb/jsonl")
        if on_conflict not in ("error", "keep_first"):
            raise ValueError("on_conflict 必须是 error/keep_first")
        if not table.replace("_", "").isalnum():
            raise ValueError("非法表名: %r" % table)
        self.db_path = db_path
        self.table = table
        self.backend = backend
        self.enable = enable
        self.on_conflict = on_conflict
        self.lock_path = lock_path
        self._conn = None
        if enable and backend == "duckdb":
            self._connect()

    # —— DuckDB ——
    def _connect(self):
        if self._conn is not None:
            return self._conn
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - 环境分支
            raise GovernanceError(
                "duckdb 不可用；请改用 backend='jsonl'"
            ) from exc
        self._conn = duckdb.connect(self.db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS {table} (
                record_id       VARCHAR PRIMARY KEY,
                schema_version  VARCHAR NOT NULL,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                factor_id       VARCHAR,
                batch_id        VARCHAR,
                experiment_id   VARCHAR,
                stage           VARCHAR,
                mode            VARCHAR,
                status          VARCHAR,
                payload         JSON NOT NULL,
                payload_hash    VARCHAR NOT NULL
            )
            """.format(table=self.table)
        )
        return self._conn

    def _existing_hash(self, record_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT payload_hash FROM {t} WHERE record_id = ?".format(
                t=self.table
            ),
            [record_id],
        ).fetchone()
        return None if row is None else row[0]

    def _decide(self, record_id: str, payload_hash: str) -> bool:
        """返回 True 表示需要插入；False 表示幂等/保留首条。"""
        existing = self._existing_hash(record_id)
        if existing is None:
            return True
        if existing == payload_hash:
            return False
        if self.on_conflict == "keep_first":
            logger.warning(
                "record_id %s 已存在且 payload 不同，keep_first 保留首条",
                record_id,
            )
            return False
        raise ReproducibilityConflictError(
            "record_id %s 对应不同 payload（结果不可复现）" % record_id
        )

    def _insert_one(self, record: GovernanceRecord, payload_hash: str) -> None:
        payload = canonical_json(record.model_dump(mode="json"))
        self._conn.execute(
            """
            INSERT INTO {t}
                (record_id, schema_version, factor_id, batch_id,
                 experiment_id, stage, mode, status, payload, payload_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON), ?)
            """.format(t=self.table),
            [
                record.record_id, record.schema_version, record.factor_id,
                record.batch_id, record.experiment_id, record.stage.value,
                record.mode.value, record.status.value, payload, payload_hash,
            ],
        )

    # —— JSONL ——
    def _jsonl_rows(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.db_path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(self.db_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("跳过无法解析的 JSONL 行: %r", line[:80])
        return rows

    def _jsonl_append(self, record: GovernanceRecord, payload_hash: str) -> bool:
        with _file_lock(self.lock_path):
            for row in self._jsonl_rows():
                if row.get("record_id") != record.record_id:
                    continue
                existing = compute_payload_hash(row)
                if existing == payload_hash:
                    return False
                if self.on_conflict == "keep_first":
                    logger.warning(
                        "record_id %s 已存在且 payload 不同，keep_first 保留首条",
                        record.record_id,
                    )
                    return False
                raise ReproducibilityConflictError(
                    "record_id %s 对应不同 payload（结果不可复现）"
                    % record.record_id
                )
            payload = record.model_dump(mode="json")
            with open(self.db_path, "a", encoding="utf-8") as handle:
                handle.write(canonical_json(payload) + "\n")
        return True

    # —— 公共 API ——
    def append(self, record: GovernanceRecord) -> bool:
        if not self.enable:
            return False
        payload = record.model_dump(mode="json")
        payload_hash = compute_payload_hash(payload)
        if self.backend == "jsonl":
            return self._jsonl_append(record, payload_hash)
        self._connect()
        if not self._decide(record.record_id, payload_hash):
            return False
        self._insert_one(record, payload_hash)
        return True

    def append_many(self, records: Iterable[GovernanceRecord]) -> int:
        if not self.enable:
            return 0
        unique: Dict[str, GovernanceRecord] = {}
        for record in records:
            unique.setdefault(record.record_id, record)
        if not unique:
            return 0
        if self.backend == "jsonl":
            inserted = 0
            for record in unique.values():
                if self.append(record):
                    inserted += 1
            return inserted

        self._connect()
        # 每条记录只 dump/序列化一次（性能包 O1）
        rows: List[Dict[str, Any]] = []
        for record in unique.values():
            payload = record.model_dump(mode="json")
            rows.append({
                "record_id": record.record_id,
                "schema_version": record.schema_version,
                "factor_id": record.factor_id,
                "batch_id": record.batch_id,
                "experiment_id": record.experiment_id,
                "stage": record.stage.value,
                "mode": record.mode.value,
                "status": record.status.value,
                "payload": canonical_json(payload),
                "payload_hash": compute_payload_hash(payload),
            })

        # 批量存在性检查：一次 JOIN，替代逐条 _decide 查询
        existing = self._existing_hashes([row["record_id"] for row in rows])
        pending: List[Dict[str, Any]] = []
        for row in rows:
            record_id = row["record_id"]
            if record_id not in existing:
                pending.append(row)
                continue
            if existing[record_id] == row["payload_hash"]:
                continue
            if self.on_conflict == "keep_first":
                logger.warning(
                    "record_id %s 已存在且 payload 不同，keep_first 保留首条",
                    record_id,
                )
                continue
            raise ReproducibilityConflictError(
                "record_id %s 对应不同 payload（结果不可复现）" % record_id
            )
        if not pending:
            return 0

        frame = pd.DataFrame(pending)
        self._conn.register("_gr_batch", frame)
        try:
            self._conn.execute(
                """
                INSERT INTO {t}
                    (record_id, schema_version, factor_id, batch_id,
                     experiment_id, stage, mode, status, payload, payload_hash)
                SELECT record_id, schema_version, factor_id, batch_id,
                       experiment_id, stage, mode, status,
                       CAST(payload AS JSON), payload_hash
                FROM _gr_batch
                """.format(t=self.table)
            )
        finally:
            self._conn.unregister("_gr_batch")
        return len(pending)

    def _existing_hashes(self, record_ids: Sequence[str]) -> Dict[str, str]:
        """批量取已存在记录的 payload_hash（一次注册 + JOIN）。"""
        if not record_ids:
            return {}
        probe = pd.DataFrame({"record_id": list(record_ids)})
        self._conn.register("_gr_probe", probe)
        try:
            rows = self._conn.execute(
                """
                SELECT p.record_id, t.payload_hash
                FROM _gr_probe p
                JOIN {t} t ON t.record_id = p.record_id
                """.format(t=self.table)
            ).fetchall()
        finally:
            self._conn.unregister("_gr_probe")
        return {row[0]: row[1] for row in rows}

    def get(
        self, record_id: str,
    ) -> Optional[Union[GovernanceRecord, Dict[str, Any]]]:
        if not self.enable:
            return None
        payload: Optional[Dict[str, Any]] = None
        if self.backend == "jsonl":
            for row in self._jsonl_rows():
                if row.get("record_id") == record_id:
                    payload = row
                    break
        else:
            self._connect()
            row = self._conn.execute(
                "SELECT payload FROM {t} WHERE record_id = ?".format(
                    t=self.table
                ),
                [record_id],
            ).fetchone()
            if row is not None:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
        return None if payload is None else self._parse_payload(payload)

    def query(self, **filters: Any) -> pd.DataFrame:
        if not self.enable:
            return pd.DataFrame()
        allowed = {
            "record_id", "schema_version", "factor_id", "batch_id",
            "experiment_id", "stage", "mode", "status",
        }
        unknown = set(filters) - allowed
        if unknown:
            raise ValueError("不支持过滤字段: %s" % sorted(unknown))
        normalized = {
            k: (v.value if isinstance(v, Enum) else v)
            for k, v in filters.items()
        }

        if self.backend == "jsonl":
            rows = []
            for payload in self._jsonl_rows():
                if all(payload.get(k) == v for k, v in normalized.items()):
                    rows.append({
                        "record_id": payload.get("record_id"),
                        "schema_version": payload.get("schema_version"),
                        "factor_id": payload.get("factor_id"),
                        "batch_id": payload.get("batch_id"),
                        "experiment_id": payload.get("experiment_id"),
                        "stage": payload.get("stage"),
                        "mode": payload.get("mode"),
                        "status": payload.get("status"),
                        "payload": canonical_json(payload),
                        "payload_hash": compute_payload_hash(payload),
                        "created_at": None,
                    })
            return pd.DataFrame(rows)

        self._connect()
        where, params = self._where(normalized)
        sql = "SELECT * FROM {t}{where} ORDER BY created_at".format(
            t=self.table, where=where
        )
        return self._conn.execute(sql, params).df()

    def query_records(
        self, **filters: Any,
    ) -> List[Union[GovernanceRecord, Dict[str, Any]]]:
        frame = self.query(**filters)
        records: List[Union[GovernanceRecord, Dict[str, Any]]] = []
        for payload in frame.get("payload", []):
            if isinstance(payload, str):
                payload = json.loads(payload)
            if payload:
                records.append(self._parse_payload(payload))
        return records

    def latest(
        self, factor_id: str, stage: Optional[Stage] = None
    ) -> Optional[Union[GovernanceRecord, Dict[str, Any]]]:
        if not self.enable:
            return None
        if self.backend == "jsonl":
            candidates = [
                p for p in self._jsonl_rows()
                if p.get("factor_id") == factor_id
                and (stage is None or p.get("stage") == stage.value)
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda p: p.get("timestamp") or "")
            return self._parse_payload(candidates[-1])

        self._connect()
        clauses = ["factor_id = ?"]
        params: List[Any] = [factor_id]
        if stage is not None:
            clauses.append("stage = ?")
            params.append(stage.value)
        row = self._conn.execute(
            """
            SELECT payload FROM {t}
            WHERE {where}
            ORDER BY json_extract_string(payload, '$.timestamp') DESC,
                     created_at DESC
            LIMIT 1
            """.format(t=self.table, where=" AND ".join(clauses)),
            params,
        ).fetchone()
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return self._parse_payload(payload)

    def ancestors(
        self, record_id: str, *, max_depth: int = 64
    ) -> List[AncestorEntry]:
        """沿 parent_id 回溯；断链以条目标注，循环/超深抛错。

        返回 ``AncestorEntry`` 列表（DESIGN §4.4 F-F）：
        - 正常节点：``record`` 非空、``broken_link=False``；
        - 断链（记录不存在）或遇到更新 schema 的 dict：追加
          ``record=None``、``broken_link=True`` 的终止条目，``reason`` 分别为
          ``missing`` / ``schema_mismatch``。
        """
        out: List[AncestorEntry] = []
        seen = set()
        cursor: Optional[str] = record_id
        for _ in range(max_depth):
            if not cursor:
                return out
            if cursor in seen:
                raise GovernanceError("parent cycle detected at %s" % cursor)
            seen.add(cursor)
            record = self.get(cursor)
            if record is None:
                logger.warning("ancestors 断链: %s 不存在", cursor)
                out.append(AncestorEntry(
                    record_id=cursor, record=None,
                    broken_link=True, reason="missing",
                ))
                return out
            if not isinstance(record, GovernanceRecord):
                logger.warning(
                    "ancestors 遇到非当前 schema 记录，停止回溯: %s", cursor)
                out.append(AncestorEntry(
                    record_id=cursor, record=None,
                    broken_link=True, reason="schema_mismatch",
                ))
                return out
            out.append(AncestorEntry(
                record_id=cursor, record=record, broken_link=False,
            ))
            cursor = record.parent_id
        raise GovernanceError("ancestors 超过 max_depth=%d" % max_depth)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # —— 内部 ——
    @staticmethod
    def _where(normalized: Mapping[str, Any]) -> Tuple[str, List[Any]]:
        if not normalized:
            return "", []
        clauses = []
        params: List[Any] = []
        for key, value in normalized.items():
            clauses.append("%s = ?" % key)
            params.append(value)
        return " WHERE " + " AND ".join(clauses), params

    @staticmethod
    def _parse_payload(
        payload: Mapping[str, Any],
    ) -> Union[GovernanceRecord, Dict[str, Any]]:
        schema = payload.get("schema_version", SCHEMA_VERSION)
        if schema == SCHEMA_VERSION:
            return GovernanceRecord.model_validate(dict(payload))
        current = _schema_tuple(SCHEMA_VERSION)
        theirs = _schema_tuple(schema)
        if theirs and theirs < current:
            # 更旧 schema：补默认值 + extra=allow + legacy=True
            logger.warning(
                "记录 schema_version=%s 旧于当前 %s，按 legacy 兼容模式解析",
                schema, SCHEMA_VERSION,
            )
            return _LegacyGovernanceRecord.model_validate(dict(payload))
        # 更新 schema（来自未来）：原样 dict 返回，禁止静默丢弃
        logger.warning(
            "记录 schema_version=%s 新于当前 %s，按原样 dict 返回",
            schema, SCHEMA_VERSION,
        )
        return dict(payload)
