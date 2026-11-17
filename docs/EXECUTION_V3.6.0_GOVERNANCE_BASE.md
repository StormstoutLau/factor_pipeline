# EXECUTION v3.6.0 治理底座 — P0 四件套 (GR-1 ~ GR-4)

> **版本**: v1.0 (2026-11-17) — 步骤 5 实施文档；步骤 6 review 见 §9
> **上游设计**: [DESIGN_GOVERNANCE_BASE.md](private/DESIGN_GOVERNANCE_BASE.md) v1.2（本地，gitignored）
> **上游调研**: [RESEARCH_GOVERNANCE_BASE.md](research/RESEARCH_GOVERNANCE_BASE.md) v1.1
> **上游方案**: [多因子治理路线图 §4-§6](analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) / [PROJECT_STATUS P1-A](PROJECT_STATUS.md)
> **目标版本**: 3.6.0（`pyproject.toml` 3.5.3 → 3.6.0；缓存代际 `v2.3.0-cache` 不变）
> **批次档位**: **T1 完整管线**（Layer-1：`backtest/` + `scripts/` + `tests/`；命中"契约/真值源变更"强制升级条款）
> **新增依赖**: 零（仅用已声明的 numpy/pandas/scipy/pydantic/duckdb）
> **关联 ADR**: ADR-050 ~ ADR-054

---

## §0 摘要、档位与工件状态

### 0.1 交付内容

四个平级模块 + 两处既有代码最小改动 + 一个对拍脚本 + 四个测试文件：

| 工件 | 类型 | 状态（步骤 5 时点） |
|------|------|-------------------|
| `backtest/governance.py` | 新增 | 待实施（E1） |
| `backtest/data_contract.py` | 新增 | 待实施（E2） |
| `backtest/golden_master.py` | 新增 | 待实施（E3） |
| `backtest/multiple_testing_ledger.py` | 新增 | 待实施（E4） |
| `backtest/multiple_testing.py` | 改动（可选参数） | 待实施（E4） |
| `pipelines_v2.py` | 改动（hook） | 待实施（E6） |
| `benchmarks/stata_econ_crosscheck.py` | 新增 | 待实施（E5） |
| `tests/test_backtest/test_{governance,data_contract,golden_master,multiple_testing_ledger}.py` | 新增 | 待实施（E1-E4） |
| `tests/golden/govbase_v1_synth/` | 新增 fixture | 待实施（E3） |
| `scripts/spec_runner_adapter.py` | 新增（流程工具） | **已完成**（附带回退点：删除文件即可） |

### 0.2 档位判定（SPEC_PROCESS v1.7.2 §批次档位）

| 判据 | 读数 | 结论 |
|------|------|------|
| 改动路径 ∩ `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` | 非空（`backtest/` 虽不在列，但属运行时模块） | Layer-1 |
| 强制升级条款：契约 / 真值源 / 门禁变更 | 命中（新增 `GovernanceRecord` 契约、golden 基线、台账口径） | **T1** |
| 裁剪理由 | 无（T1 不允许裁剪四文档） | —— |

> 工件命名沿用本仓映射（SPEC_PROCESS §自包含口径允许环境态替换）：
> RESEARCH=`docs/research/`、DESIGN=`docs/private/`、IMPLEMENTATION=`docs/EXECUTION_*.md`、
> CHECKLIST/CONSISTENCY=`docs/audit/`。设计文档不入库的证据降级见 DESIGN §19.4。

### 0.3 与路线图/SOP 的映射

| 路线图项 | 本批工件 | 门禁 |
|---------|---------|------|
| GR-1 治理记录 | `governance.py` | G0/G1 的载体；S0-S6 记录 |
| GR-2 数据契约 | `data_contract.py` | G0：mv 5 日缺口拦截 |
| GR-3 Golden master | `golden_master.py` + fixtures | G4：默认路径零变更 |
| GR-4 多重检验台账 | `multiple_testing_ledger.py` | G2：family 预注册 + 校正 |

---

## §1 任务分解（E0-E8）

> 一份文档含 ≥3 个独立能力 → 按 SPEC_PROCESS Step 5 要求做任务拆解。每个 E 任务有独立验收命令与回退点。

| E | 任务 | 输入 | 产出 | 依赖 | 验收命令 | 回退点 |
|---|------|------|------|------|---------|--------|
| E0 | 版本与基线冻结 | — | 基线门禁事件流 + 版本字面量清单 | — | `adapter.py gate unit-tests` | 无代码变更 |
| E1 | GR-1 记录与存储 | DESIGN §4 | `governance.py` + T1-T10 | — | `pytest tests/test_backtest/test_governance.py -q` | 删除模块；无调用点 |
| E2 | GR-2 数据契约 | DESIGN §5 | `data_contract.py` + T11-T15 | — | `pytest ... test_data_contract.py -q` | 删除模块；不进入管线默认路径 |
| E3 | GR-3 Golden master | DESIGN §6 | `golden_master.py` + fixture + T16-T20 | E1（hash） | `pytest ... test_golden_master.py -q` | 删除模块与 `tests/golden/` |
| E4 | GR-4 台账 + 检验注入 | DESIGN §7 | `multiple_testing_ledger.py` + `multiple_testing.py` 可选参数 + T21-T30 | E1 | `pytest ... test_multiple_testing_ledger.py -q` | 删除台账；`bootstrap_indices` 默认 None 即原路径 |
| E5 | Stata 对拍脚本 | DESIGN §8 | `benchmarks/stata_econ_crosscheck.py` | E4 | `python benchmarks/stata_econ_crosscheck.py --case all` | 删除脚本；Stata 缺失时 SKIP |
| E6 | 管线 hook | DESIGN §4.5 | `pipelines_v2.py` 增 2 个方法 + 1 调用点 | E1 | T31/T32 + 全量回归 | 删除方法/调用点（默认 None） |
| E7 | 研究脚本适配 | DESIGN §10.4 | 容量/多头端研究入口前置契约（可选） | E2 | 研究脚本 dry-run | 不接线即回退 |
| E8 | 文档闭环 | 全部 | ADR-050~054 / CHANGELOG / PROJECT_STATUS / ARCHITECTURE / 版本号 | E1-E6 | `pytest tests/test_fix3_version_unification.py` | 文档回滚 |

**实施顺序**：E1 → E2 ∥ E3 → E4 → E5 → E6 → E7 → E8。
**禁止**：先做 E6（管线 hook）再补 E1——hook 依赖记录契约稳定。

---

## §2 接口签名与回退点

> 签名即实现契约；Step 6 逐条核"可实现性"，Step 9 按此写测试。Python 3.9 语法（禁用 `X | Y`）。

### 2.1 `backtest/governance.py`（E1）

```python
SCHEMA_VERSION = "1.0.0"

ID_FIELDS: Tuple[str, ...] = (
    "batch_id", "parent_id", "experiment_id", "factor_id", "variant_id",
    "stage", "status", "mode", "arm",
    "pipeline_version", "config_hash", "construction_code_hash", "gate_policy_version",
    "data_snapshot_hash", "universe_version", "sample_window", "split_id", "holdout_locked_at",
    "benchmark_id", "return_convention", "tradable_convention", "cost_model", "sign_convention",
    "seed",
)
HASH_EXCLUDED: FrozenSet[str] = frozenset({
    "record_id", "schema_version", "timestamp", "reviewer",
    "evidence_uri", "env_fingerprint", "notes",
})

class Stage(str, Enum): ...          # S0..S6 / final / portfolio / recheck
class Mode(str, Enum): ...           # research / production
class RecordStatus(str, Enum): ...   # active / retired / superseded
class Arm(str, Enum): ...            # static / dynamic / mixed

class GateResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    passed: bool
    reasons: List[str]
    action: Literal["block", "downgrade", "allow"]
    evidence_refs: List[str]
    evaluated_by: Literal["human", "script", "ledger"]

class GovernanceRecord(BaseModel):
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
    sample_window: Dict[str, str]          # {"start": ISO, "end": ISO}
    split_id: Optional[str] = None
    holdout_locked_at: Optional[str] = None
    # —— 口径（5）——
    benchmark_id: str
    return_convention: str
    tradable_convention: Dict[str, Any]
    cost_model: Dict[str, Any]
    sign_convention: str
    # —— 结果（条件必填，见 §2.1.1）——
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
    def build(cls, **fields: Any) -> "GovernanceRecord": ...
    @model_validator(mode="after")
    def _validate_stage_requirements(self) -> "GovernanceRecord": ...

def canonical_json(obj: Any) -> str: ...
def compute_record_id(fields: Mapping[str, Any]) -> str: ...
def compute_payload_hash(payload: Mapping[str, Any]) -> str: ...
def env_fingerprint() -> Dict[str, Any]: ...
def code_commit(repo_root: Optional[str] = None) -> Optional[str]: ...

class GovernanceStore:
    def __init__(self, db_path: str = "factor_db.duckdb",
                 table: str = "governance_record",
                 backend: str = "duckdb",          # duckdb | jsonl
                 enable: bool = True,
                 on_conflict: str = "error",       # error | keep_first
                 lock_path: Optional[str] = None) -> None: ...
    def append(self, record: GovernanceRecord) -> bool: ...
    def append_many(self, records: Iterable[GovernanceRecord]) -> int: ...
    def get(self, record_id: str) -> Optional[Union[GovernanceRecord, Dict[str, Any]]]: ...
    def query(self, **filters: Any) -> pd.DataFrame: ...
    def query_records(self, **filters: Any) -> List[Union[GovernanceRecord, Dict[str, Any]]]: ...
    def latest(self, factor_id: str, stage: Optional[Stage] = None) -> Optional[Union[GovernanceRecord, Dict[str, Any]]]: ...
    def ancestors(self, record_id: str, *, max_depth: int = 64) -> List[AncestorEntry]: ...
    def close(self) -> None: ...

@dataclass(frozen=True)
class AncestorEntry:
    record_id: str
    record: Optional[GovernanceRecord]
    broken_link: bool = False
    reason: str = ""          # "" | "missing" | "schema_mismatch"
```

**实现要点（必须照做，防止 Step 10 判忠实度偏离）**：

1. `build()` **先归一化时间**（全部转 UTC ISO 8601，带时区）→ 补默认值 → 计算 `record_id` → **一次构造**；
   `model_validator(mode="after")` 只读校验，不赋值（frozen 语义）。
2. `compute_record_id` 取 `ID_FIELDS` 子集；缺失键按 `None` 参与（`canonical_json` 用 `sort_keys=True`）。
3. `compute_payload_hash` 排除 `HASH_EXCLUDED`；`timestamp` 为 `None` 时先补 UTC now 再哈希（排除集已含它，不影响）。
4. 存储层写入前 `record.model_copy(deep=True)`；DuckDB 批量只走 `INSERT INTO ... SELECT * FROM df`。
5. DuckDB **lazy import**；`backend='jsonl'` 在无 duckdb 环境可用；`lock_path` 用 `msvcrt.locking`（Windows）/`fcntl`（POSIX）。
   跨平台等待语义存在差异：Windows `LK_LOCK` 重试约 10 s 后抛 `OSError`，POSIX `flock` 阻塞至获得；
   仅影响 JSONL fallback 的极端跨进程竞争（进程内另有线程锁），由异构复审 F1 披露（§9.8）。
6. `_parse_legacy` 三分支：当前版本严格校验；更旧补默认 + `extra="allow"` + `legacy=True`；更新版本原样 dict + warning。
   因此 `get/latest/query_records` 返回 `Union[GovernanceRecord, Dict]`（DR-16）；`ancestors` 遇非当前 schema 记录
   追加 `broken_link=True` 条目（`reason="schema_mismatch"`）后停止回溯。

#### 2.1.1 stage 条件校验（实现即设计 §4.2 表）

| 条件 | 必填 | 失败 |
|------|------|------|
| S0 | `test_family`、`holdout_locked_at`、全部口径、`construction_code_hash` | `ValidationError` |
| S1 | `data_snapshot` 非空、`data_snapshot_hash`、`gate_status['G0']` | 同上 |
| S2 | `config_hash`、`arm`、`pipeline_version`、`gate_status['G1']` | 同上 |
| S3/final/portfolio | `effect_metric`∈{lambda_mean,ic_mean,sharpe}、`effect_size`、`ci`(low≤high)、`n_trials≥1`、`n_testable≥0`、`n_hypotheses≥0`、`test_family`、`correction_method`、p/q/adjusted_p 至少一个 | 同上 |
| S4 | `capacity_estimate` 非空、`gate_status['G3.5']` | 同上 |
| S5/S6 + production | G0/G1/G2/G3/G3.5/G4/G5 全 passed、`reviewer` | 同上 |
| S5/S6 + research | **直接拒绝** | 同上 |
| production | 上述 S5 条件 + `status='active'` | 同上 |
| portfolio/recheck 或 retired | `parent_id` 非空 | 同上 |

**回退点**：删除 `governance.py`；无任何既有模块 import 它（D1），故零波及。

### 2.2 `backtest/data_contract.py`（E2）

```python
@dataclass(frozen=True)
class FieldSpec:
    name: str
    file: Optional[str] = None
    reader: str = "pickle"                 # pickle | csv | pickle_series | derived
    max_lag: Optional[int] = 0             # None = 静态参考，跳过 freshness
    required: bool = True
    min_coverage: float = 0.95
    max_nan_rate: float = 0.50
    value_range: Optional[Tuple[float, float]] = None
    description: str = ""
    # §5.7 语义扩展
    semantic_type: str = "price"
    unit: Optional[str] = None
    pit_required: bool = False
    pit_date_field: Optional[str] = None
    missing_semantics: str = "warn"        # warn | known_gap | block
    universe_bias_applicable: bool = False
    expected_missing_tail: int = 0         # forward return 结构性末行缺失
    column: Optional[str] = None           # DR-11: list_date_df['list_date']

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
    fingerprint_mode: str                  # meta | content
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
    universe_bias: str = "unknown"         # point_in_time | current_snapshot_backfilled | unknown
    calendar_hash: Optional[str] = None
    def stable_hash(self) -> str: ...
    def to_record_fields(self) -> Dict[str, Any]: ...

@dataclass(frozen=True)
class CheckResult:
    check: str
    passed: bool
    severity: str                          # block | warn | info
    message: str
    details: Dict[str, Any]

@dataclass(frozen=True)
class ContractReport:
    passed: bool
    checks: List[CheckResult]
    snapshot: DataSnapshot
    policy_version: str
    known_gaps: Tuple[KnownGap, ...] = ()
    calendar_source: str = "injected"      # injected | bdate_fallback
    def blocking(self) -> List[CheckResult]: ...
    def warnings(self) -> List[CheckResult]: ...
    def to_markdown(self) -> str: ...
    def to_record_fields(self) -> Dict[str, Any]: ...

class FieldReader(Protocol):
    def read(self, root: Path, spec: FieldSpec) -> pd.DataFrame: ...

class ContractCache:
    def __init__(self, path: Optional[str] = None): ...
    def get(self, key: str) -> Optional[FieldSnapshot]: ...
    def put(self, key: str, snapshot: FieldSnapshot) -> None: ...

def build_snapshot(root, sample_end, fields=None, *, trading_calendar=None,
                   universe=None, list_date=None, readers=None) -> DataSnapshot: ...
def check_data_contract(root, sample_end, fields=None, *, strict=False,
                        trading_calendar=None, universe=None, list_date=None,
                        cache=None, readers=None) -> ContractReport: ...
class DataContractError(Exception):
    def __init__(self, report: ContractReport): ...
```

**实现要点**：

1. `content_digest`：列名 + shape + 每列首/中/尾各 8 行 + 全表 NaN 计数 → canonical JSON → SHA256；
   `content_hash_full=True` 时用全表字节 hash。**不含 mtime**。
2. `last_full_date` 用"覆盖率 ≥ `min_coverage`"的最后交易日；`expected_missing_tail` **不剥离原始快照**，
   而是从 `lag` 中扣除（`lag = max(0, raw_lag - expected_missing_tail)`），`raw_lag` 保留在 `details`。
3. freshness：`lag = count(calendar[last_full_date < c <= effective_end])`；`effective_end` 取 `calendar <= sample_end` 的最大值。
4. 日历缺省 → `pd.bdate_range` 兜底 + `calendar_source='bdate_fallback'` + warn（偏差方向：只多不少）。
5. `check` 名称固定：`schema / freshness / coverage / value_sanity / pit / universe / calendar / consistency / adj_alignment / adj_monotonic`。
6. **异常基类局部定义**（`DataContractError(Exception)`），不 import `governance`——这是对 DESIGN §10.3 的一处实施级修正（见 §9.6 F1）。
7. **缓存 key 扩展（DR-12）**：除 `(field, file, size, mtime_ns, head_digest)` 外追加 `sample_end + calendar_hash`——
   `coverage_last`/`last_full_date` 依赖样本末与日历，只按文件元数据缓存会在换样本末时误命中。
8. **缓存命中的已知限制（DR-13）**：命中路径不保留完整 frame，跨字段 `adj_alignment`/`adj_monotonic`
   只在本次实际读取了 `adj + price` 时执行；命中缓存的报告不含该两项。`FieldSnapshot` 未加 `index_digest`，
   待 T41/E3 评估是否补（不影响 T11-T15）。

**回退点**：删除模块；契约不在管线默认路径调用，删除后无运行时影响。

### 2.3 `backtest/golden_master.py`（E3）

```python
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

@dataclass
class GoldenReport:
    baseline_id: str
    verdict: str                           # PASS | PASS_WITH_ENV_DIFF | FAIL
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

class GoldenMaster:
    def __init__(self, root: Union[str, Path] = "tests/golden"): ...
    def capture(self, baseline_id: str,
                outputs: Mapping[str, pd.DataFrame],
                manifest: Mapping[str, Any],
                *, force: bool = False,
                reason: str = "",
                reviewer: str = "") -> Path: ...
    def load(self, baseline_id: str) -> Tuple[GoldenManifest, pd.DataFrame]: ...
    def compare(self, baseline_id: str,
                outputs: Mapping[str, pd.DataFrame],
                *, rtol: Optional[float] = None,
                atol: Optional[float] = None) -> GoldenReport: ...
    def verify(self, baseline_id: str,
               runner: Callable[[], Mapping[str, pd.DataFrame]]) -> GoldenReport: ...
```

**实现要点**：

1. long format 键 `(date, factor_id, stock)`；outer join 统计 missing/extra。
2. `np.isclose(..., rtol=1e-10, atol=1e-12, equal_nan=True)`；双方 NaN 相等、单方 NaN = mismatch。
3. **NaN 率守卫**：按 factor，`actual_nan_rate - baseline_nan_rate > 0.01` → 强制 FAIL。
4. 读写 parquet 用 DuckDB `COPY ... (FORMAT PARQUET)` / `read_parquet`；不 import pyarrow。
5. `capture` 默认拒绝覆盖；`force=True` 必须给 `reason` + `reviewer`，写入 manifest。
6. 环境指纹不匹配但数值在容差内 → `PASS_WITH_ENV_DIFF`。
7. **manifest 审计字段（DR-14）**：`reason`/`reviewer` 仅 `force=True` 时写入；
   `factor_ids`/`periods`/`n_stocks` 由 `outputs` 计算，不接受调用方覆盖；`load` 过滤未知键以兼容未来 schema。
8. **提交式 fixture**：`tests/golden/govbase_v1_synth/` 需真实管线输出，E3 只验证机制
   （T16-T20 用 `tmp_path` 临时基线）；提交式基线在 E6（管线 hook 可用后）采集。

**回退点**：删除模块与 `tests/golden/`；无运行时调用。

### 2.4 `backtest/multiple_testing_ledger.py`（E4）

```python
class CorrectionTrack(str, Enum): FDR = "fdr"; FWER = "fwer"
class CorrectionMethod(str, Enum):
    BH = "benjamini_hochberg"; BY = "benjamini_yekutieli"
    BONFERRONI = "bonferroni"; HOLM = "holm"
    ROMANO_WOLF = "romano_wolf"; WHITE_RC = "white_rc"; HANSEN_SPA = "hansen_spa"

@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    factor_id: str
    description: str
    spec_hash: str
    kind: str = "confirmatory"             # confirmatory | exploratory

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
    policy_version: str = "1.0.0"
    variants: Tuple[VariantSpec, ...] = ()
    registered_at: Optional[str] = None
    def fingerprint(self) -> str: ...

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
    alternative: str = "two-sided"        # two-sided | greater | less
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
    evidence_uri: Optional[str]
    def to_markdown(self) -> str: ...
    def to_record_fields(self, extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]: ...

class MultipleTestingLedger:
    def __init__(self, db_path: str = "factor_db.duckdb",
                 table_prefix: str = "mt_", enable: bool = True,
                 strict_preregistration: bool = True): ...
    def register_family(self, spec: FamilySpec) -> str: ...
    def record_trial(self, trial: TrialRecord, *, backfill: bool = False,
                     exploratory: bool = False) -> str: ...
    def record_trials(self, trials: Iterable[TrialRecord], *, backfill: bool = False,
                      exploratory: bool = False) -> int: ...
    def apply(self, family_id: str,
              method: Optional[CorrectionMethod] = None,
              *, alpha: Optional[float] = None,
              bootstrap_p_values: Optional[np.ndarray] = None,
              returns_matrix: Optional[np.ndarray] = None,
              benchmark_index: int = 0,
              bootstrap_indices: Optional[np.ndarray] = None,
              allow_alpha_override: bool = False) -> FamilyResult: ...
    def query_trials(self, family_id: str) -> pd.DataFrame: ...
    def report(self, family_id: str) -> FamilyResult: ...
    def close(self) -> None: ...

class PreregistrationError(Exception): ...
class TrackMismatchError(Exception): ...
class FamilyConflictError(Exception): ...
```

**实现要点**：

1. family/variant 注册后不可追加；`registered_at` 由 ledger 用 `dataclasses.replace` 写入 UTC now。
2. `record_trial(exploratory=True)`：未预注册 variant 允许，但 `kind='exploratory'`；已 confirmatory 的 variant 不得降级。
3. `backfill=True`：必须显式 `created_at`，trial 标 `backfilled=True`，不进 confirmatory 主分析。
4. `n_trials`（全部行）、`n_testable`（有限 p）、`n_hypotheses`（有限 primary p 的 confirmatory variant 数）。
5. 拒绝规则统一从 q/p_adj 以 `<= alpha` 重算；不修改原 `apply_*` 函数。
6. `result_id = SHA256(family_fingerprint|method|alpha|sorted(confirmatory & not backfilled entry_ids)|policy_version)`；exploratory 聚合另加 `|scope=exploratory`。
7. `entry_id = SHA256(family_id|variant_id|attempt_id)`。
8. bootstrap 协议：重抽单元 = 差分收益矩阵；stationary bootstrap；块大小用全 K 列一阶自相关中位数；五元组存 `mt_trial.payload.bootstrap_protocol`。
9. RW 快速核只在 `k=1` 启用，`k>1` 回退原实现；与原实现 `atol=1e-15` 等价性测试。

**回退点**：删除台账模块；`multiple_testing.py` 新增参数默认 `None`，原路径逐值不变（可用 T45 签名测试 + 原测试全绿证明）。

### 2.5 `backtest/multiple_testing.py` 改动（E4）

```python
# WhiteRealityCheck.test / HansenSPA.test 追加可选参数（位置参数不变）
def test(self, returns_matrix, benchmark_index=0, alpha=0.05,
         bootstrap_indices: Optional[np.ndarray] = None) -> Dict[str, Any]: ...
```

- 提供 `bootstrap_indices`（形状 `(B, T)`）→ 用 `indices[b]` 取行；
- `None` → 沿用原 RNG 路径，逐值不变；
- 注入路径的 `individual_p_values` 是**联合重抽样**下的边际 p（同一索引矩阵），与 `None` 路径的逐列独立 block bootstrap 分布口径不同；仅作对照，不改变 `rc_p_value`/SPA 主 p 值口径（异构复审 F2）；
- 分块：`chunk = max(1, 256 * 1024**2 // (T * K * 8))`；
- 不改变 `HansenSPA` 现有统计量口径（F-G 双口径对拍在 E5 处理）。

**回退点**：删除参数与分支（或显式传 `None`），原实现不变。

### 2.6 `pipelines_v2.py` 改动（E6）

```python
class FactorProcessingPipelineV2:
    def set_governance_hook(
        self, hook: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None: ...

    def _config_hash(self) -> str: ...
```

- `__init__` 增 `self._governance_hook = None`；
- `fit()` 每因子路由记录写完后：`if self._governance_hook is not None: self._governance_hook({...})`；
- 事件字段固定：`event/factor_id/stage/arm/pipeline_version/config_hash/routing/sample_window/env_fingerprint`；
- hook 异常**不吞**；
- **不 import** `backtest.governance`。

**回退点**：删除 `set_governance_hook`/`_config_hash`/调用点；`_governance_hook` 默认 None → 零行为变更。

### 2.7 `benchmarks/stata_econ_crosscheck.py`（E5）

```bash
python benchmarks/stata_econ_crosscheck.py \
  --case {all|bh|by|bonferroni|holm|romano_wolf|white_rc|hansen_spa|hac|dsr|pbo} \
  [--stata "C:\Program Files\Stata18\StataMP-64.exe"] \
  [--skip-stata] [--mc] [--B 500] [--seed 12345] [--out out/stata_econ_crosscheck.json]
```

- 退出码：PASS=0；FAIL=1；Stata 缺失/`--skip-stata`=0（SKIP）；
- 输出 JSON + stdout Markdown 表；fixture hash 入 JSON；
- Hansen 双口径：仓库口径（未 studentized）1e-10 对拍 + 原文口径差异披露。

**实现要点（E5 实施级）**：

1. `import delimited` 默认把数值列存为 **float**（单精度），1e-10 对拍会假 FAIL；
   必须 `stringcols(_all)` 导入后 `destring _all, replace`（double）。
2. bootstrap 索引 fixture 为 0-based；Mata 侧 `IDX = trunc(IDX) :+ 1`。
3. Mata `sort()` 需两参数：`sort(v, 1)`。
4. `out_white.csv` / `out_hansen.csv` 无表头，读取用 `header=None`。
5. HAC 复用 `scripts/verify_hac_stata.py`；其 L3 为已知约定差（SE²×n vs Ω），
   JSON 记 `convention_diff=true`，verdict 标 `PASS（既有脚本；L3 约定差）` 而非纯 PASS。

**回退点**：删除脚本；不影响运行时与 pytest 主路径。

### 2.8 `scripts/contract_gate.py` + 研究入口接线（E7）

```python
# scripts/contract_gate.py
def market_fields() -> Tuple[FieldSpec, ...]: ...
def load_list_date(data_root) -> Optional[pd.Series]: ...
class _PanelPickleReader:                      # pkl 面板字符串日期 → DatetimeIndex
    def read(self, root, spec) -> pd.DataFrame: ...
def run_contract_gate(data_root, *, sample_end=None, prefix="research",
                      json_path=None, markdown_path=None) -> ContractReport: ...
```

接线（两个脚本，新增且默认关闭）：

```bash
python scripts/verify_capacity_impact.py    [--contract|--contract-only] \
       [--contract-sample-end YYYY-MM-DD] [--contract-json PATH]
python scripts/verify_long_side_research.py [--contract|--contract-only] \
       [--contract-sample-end YYYY-MM-DD] [--contract-json PATH]
```

- `--contract`：加载面板前运行 GR-2 契约；未通过 → 退出码 2，不继续研究；
- `--contract-only`：只跑契约并退出（dry-run）；未通过 → 退出码 2；
- 报告落盘 `out/<prefix>_contract.json` + `.md`（默认 `capacity_impact` / `long_side_research`）；
- 真实目录适配：原始字段在 `<data_root>/market_data/`；`list_date` 经参数注入，`calendar` 注入交易日历，
  `barra`（dict-Series）按 known_gap 跳过；pkl 面板索引统一转 `DatetimeIndex`。

**回退点**：删除 `contract_gate.py` 与两处 `--contract*` 分支；默认路径零变更。

---

## §3 工程细节

### 3.1 版本锚点（5 处，机械同步）

| 文件 | 行 | 现值 | 目标 |
|------|----|------|------|
| `pyproject.toml` | L7 | `3.5.3` | `3.6.0` |
| `__init__.py` | L58 | `__version__ = "3.5.3"` | `3.6.0` |
| `config_v2.py` | L371 | `default="3.5.3"` | `3.6.0` |
| `reporting.py` | L40 | `pipeline_version = "3.5.3"` | `3.6.0` |
| `tests/test_fix3_version_unification.py` | L34 | `EXPECTED_VERSION = "3.5.3"` | `3.6.0` |

> 版本号变更**不**改变缓存代际 `v2.3.0-cache`（默认路径无算法变更）。

### 3.2 依赖与版本（2026-11-17 本机读数，py312）

| 依赖 | 声明下限 | 本机实测 | 用途 | 新增？ |
|------|---------|---------|------|--------|
| Python | `>=3.9` | 3.12.10 | 运行时 | 否 |
| pydantic | `>=2.0.0` | 2.13.4 | GovernanceRecord | 否 |
| duckdb | `>=0.10.0` | 1.5.3 | 记录/台账/golden parquet | 否 |
| numpy | `>=1.22.0` | 2.4.6 | 向量化校正/浮点比较 | 否 |
| pandas | `>=2.0.0` | 2.2.3 | 宽表/长表 | 否 |
| scipy | `>=1.7.0` | —（已声明） | 分布函数（DSR，P1） | 否 |
| pytest | `>=7.0.0` | 9.0.3（py312） | 测试 | 否 |
| Stata | 18 MP | `C:\Program Files\Stata18\StataMP-64.exe` | 对拍（可选） | 否 |

### 3.3 Python 3.9 兼容

- 注解只用 `Optional / Union / List / Dict / Tuple / Mapping / Sequence / Iterable / Callable`；
- 不用 `X | Y`、`list[str]`、`match`；
- `typing.Protocol` 用于 `FieldReader`（3.8+）；
- `functools.cached_property` 3.8+ 可用；
- `zoneinfo` 不用（3.9 可用但 Windows 需 tzdata；统一用 `datetime.timezone.utc`）。

### 3.4 序列化与哈希

| 对象 | 规则 |
|------|------|
| `canonical_json` | `sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str` |
| 时间 | 全部 UTC ISO 8601 带时区（`+00:00`）；禁止 naive/本地时间混用 |
| 浮点 | 入 hash 前 `float()` 归一；NaN → `None`（避免 `NaN != NaN` 破坏幂等） |
| dict 字段 | 存储前 deep copy；调用方不得原地修改 |
| `record_id` | `ID_FIELDS` 子集 → SHA256 |
| `payload_hash` | 全 payload 排除 `HASH_EXCLUDED` → SHA256 |
| `data_snapshot_hash` | 稳定子集（含 `content_digest`，排除 `as_of`/`file_fingerprint`）→ SHA256 |

### 3.5 错误类型（实施级修正：模块内局部定义，不跨模块 import）

| 模块 | 异常 | 基类 |
|------|------|------|
| governance | `GovernanceError` / `ReproducibilityConflictError` / `GovernanceValidationError` | `Exception` |
| data_contract | `DataContractError(report)` | `Exception` |
| golden_master | `GoldenMismatchError(report)` | `Exception` |
| ledger | `PreregistrationError` / `TrackMismatchError` / `FamilyConflictError` | `Exception` |

> 设计 §10.3 把后三者写成 `GovernanceError` 子类，与 D1「四模块互不 import」冲突；
> 实施采用局部基类，**保留错误语义但不建立跨模块依赖**。见 §9.6 F1。

### 3.6 并发与锁

- DuckDB 默认单写者；
- JSONL backend 提供 `lock_path`：Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`；
- 无 `lock_path` 时文档化"仅单写者"；不承诺天然并发安全。

### 3.7 文件布局（净新增）

```
backtest/governance.py
backtest/data_contract.py
backtest/golden_master.py
backtest/multiple_testing_ledger.py
benchmarks/stata_econ_crosscheck.py
tests/test_backtest/test_governance.py
tests/test_backtest/test_data_contract.py
tests/test_backtest/test_golden_master.py
tests/test_backtest/test_multiple_testing_ledger.py
tests/golden/govbase_v1_synth/{manifest.json,values.parquet}
tests/golden/govbase_v1_synth/make_baseline.py
scripts/spec_runner_adapter.py（已完成）
```

---

## §4 低效操作排除表

> Step 5 硬约束：本表非空。每行给"低效形态 → 替代 → 量化依据/预算"。

| # | 低效形态 | 风险位置 | 替代实现 | 量化依据 / 预算 |
|---|---------|---------|---------|----------------|
| 1 | DuckDB `executemany` 批量写 | 记录/台账批量入账 | DataFrame + `INSERT INTO ... SELECT * FROM df` | 10k 行 17.540s → 0.009s（P1，约 1950×） |
| 2 | 因子循环内重复读盘 | 契约快照 | 会话级 `build_snapshot` 一次 + `ContractCache` | 宽表扫描 0.084s/字段组；冷启动 <10s |
| 3 | 逐假设 Python 循环做 BH/BY | 台账校正 | NumPy `argsort` + 累积 min | 10 万假设 0.0041s（预算 <0.05s） |
| 4 | Romano-Wolf 对每个 j 重复排序 | FWER 轨 | `k=1` 快速核：`sorted_boot[:,0]` + `searchsorted` | m=1000,B=1000 预算 <0.5s |
| 5 | 一次性构造 `(B,T,K)` bootstrap 张量 | White/SPA | 分块：`chunk = 256MB // (T*K*8)` | T=1000,K=100,B=1000 <10s、<1GB |
| 6 | 宽表↔长表反复转换 | golden 比较 | 一次 long 化 + outer join | 24×300×4 <0.1s |
| 7 | 每次运行重新生成 `experiment_id` | 研究脚本 | 配置预生成并持久化，幂等重跑复用 | 防台账分母碎片化（B42） |
| 8 | 逐行 `DataFrame.apply` 做内容哈希 | `content_digest` | 列名 + shape + 首/中/尾采样 + NaN 计数 | O(n) 读已发生；增量成本可忽略 |
| 9 | 全表 deep copy | 记录写入 | 仅 store 边界 `model_copy(deep=True)` | 10k 记录 hash+JSON 0.049s（P6） |
| 10 | 契约按因子重复校验 | G0 | 契约在研究会话级跑一次，结果入 record | 禁止因子级重复扫描（设计 §5.6） |
| 11 | `np.sort` 全矩阵做 RW 等价性核对 | 测试 | 仅测试内小样本（B=200,m=20） | 测试预算 <1s |
| 12 | 对 p 值序列做 bootstrap | 台账 | 重抽差分收益矩阵（§7.4.1 协议） | 统计正确性（非性能）；禁止 p 值重抽 |

---

## §5 TDD 用例与红→绿计划（F5）

### 5.1 用例映射（DESIGN §12 + 本批补充）

| 组 | 用例 | 断言 | 反例/边界 |
|----|------|------|----------|
| GR-1 | T1 record_id 确定性 | 同输入 1000 次同 id | 改任一身份字段 → id 变（T2） |
| | T2 身份敏感性 | 逐字段改 | `status` 变更 → 新 id |
| | T3 易变字段不影响 | timestamp/reviewer/env 改 → id 同 | 结果字段改 → id 同、payload_hash 变 |
| | T4 stage 必填 | S3 缺 effect/ci → ValidationError | S0 缺 holdout → 同 |
| | T5 production 门禁 | 缺 G4/G5 → ValidationError | research+S5 → 拒绝 |
| | T6 roundtrip | dump→JSON→validate 相等 | NaN/None 边界 |
| | T7 幂等 | 两次写 → 1 行 | 同 id 同 payload |
| | T8 冲突 | 同 id 不同 payload → 冲突异常 | `keep_first` 保留首条 |
| | T9 query/latest | 过滤正确 | 空结果 |
| | T10 JSONL fallback | 与 DuckDB 语义一致 | 无 duckdb 环境（monkeypatch import） |
| GR-2 | T11 mv 缺口拦截 | 2026-01-23 vs 2026-01-30 → block | 合成 5 日缺口 |
| | T12 正常数据 | passed=True，0 block | 单股停牌不误判 |
| | T13 PIT 违规 | 上市日前有值 → block | list_date 缺失 → warn |
| | T14 可选缺失 | volume/suspend 缺 → warn | required=False |
| | T15 缓存命中 | 第二次不读盘（reader 计数） | mtime 变但内容同 → 同 digest |
| GR-3 | T16 完全相同 | PASS，max_abs=0 | —— |
| | T17 容差边界 | 1e-11 PASS；1e-8 FAIL | rtol/atol 双边界 |
| | T18 参数变更 | percentile 2/98 → FAIL | —— |
| | T19 缺/多股 | missing/extra 计数正确 | —— |
| | T20 capture 不覆盖 | 已存在 → 拒绝 | force 需 reason+reviewer |
| GR-4 | T21 未预注册拒绝 | family/variant 不存在 → 异常 | exploratory 允许 |
| | T22 时序 | created_at < registered_at → 拒绝 | 时区一致 |
| | T23/T24 BH/BY 参考 | q/掩码 ≤1e-12 | 并列 p |
| | T25 `<= α` 边界 | q==α 判显著 | 原函数严格 `<` 不参与 |
| | T26 RW 参考 | p_adj ≤1e-10 | 注入同一 t* 矩阵 |
| | T27 RW 快速核 | 与原实现 ≤1e-15 | k=1/k>1 |
| | T28 White/SPA joint | p ≤1e-10；lc≥consistent≥uc | 同索引矩阵 |
| | T29 三分母 | 含失败/重复/exploratory | n_trials≥n_testable≥n_hypotheses |
| | T30 轨不匹配 | FDR+Bonferroni → 异常 | FWER+BH → 异常 |
| hook | T31 未设 hook | 输出与基线 1e-10 一致 | 全量回归 |
| | T32 事件字段 | 每因子一条 dict | 字段缺失 → 测试失败 |

### 5.2 本批补充用例（实施级，覆盖 DESIGN §18 修正）

| # | 用例 | 覆盖 |
|---|------|------|
| T33 | 模块隔离：AST 扫描四模块 import，断言互不 import | D1 |
| T34 | 旧 schema 读取：更旧/更新两分支不丢记录 | B6 |
| T35 | `content_digest` 对 mtime 不变、对内容敏感 | F-A |
| T36 | cache key 含头部 64KB 摘要，copy2 恢复不命中陈旧快照 | B12 |
| T37 | `expected_missing_tail=1` 时末行缺失不算 freshness 缺口 | B13 |
| T38 | NaN 率守卫：actual 比 baseline 多 2% → FAIL | B16 |
| T39 | backfill trial 不进 confirmatory 主分析 | F-D |
| T40 | exploratory trial 不改变 `result_id` | F-E |
| T41 | ancestors 循环 → 异常；断链 → `broken_link`（`AncestorEntry`） | F-F |
| T42 | `gate_status` 未知键 → 拒绝 | B29 |
| T43 | 时间字段均为带时区 UTC ISO | B5 |
| T44 | jsonl `lock_path` 获取/释放；并发线程无交错 | F-H |
| T45 | `Inspect.signature` 断言 `bootstrap_indices` 默认 None | 零变更 |
| T46 | `env_fingerprint()` 含 python/numpy/pandas/BLAS/线程且可序列化 | B7 |

### 5.3 红→绿记录形态（F5，Step 9 执行时填写）

```text
[红] 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_governance.py -q --tb=short
     退出码: 2
     关键失败行: E   ModuleNotFoundError: No module named 'factor_pipeline.backtest.governance'
     摘要: 1 error during collection in 0.44s
     时间: 2026-11-17（步骤 9 E1，实现前）

[绿] 命令: 同上（含批量写入烟测 T7b）
     退出码: 0
     用例计数: 11 passed in 0.46s
     门禁读数: tests-e1 pass（11 passed, 0.44s）；tests-fast pass（58 passed, 14.40s）
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17T21:47+08:00

[红] E2 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_data_contract.py -q --tb=short
     退出码: 2
     关键失败行: E   ModuleNotFoundError: No module named 'factor_pipeline.backtest.data_contract'
     摘要: 1 error during collection in 0.52s
     时间: 2026-11-17（步骤 9 E2，实现前）

[绿] E2 命令: 同上
     退出码: 0
     用例计数: 5 passed in 0.17s
     门禁读数: tests-e2 pass（5 passed, 0.14s）；tests-e1 pass（11 passed）；tests-fast pass（58 passed, 13.58s）
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17（步骤 9 E2 完成后）

[红] E3 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_golden_master.py -q --tb=short
     退出码: 2
     关键失败行: E   ModuleNotFoundError: No module named 'factor_pipeline.backtest.golden_master'
     摘要: 1 error during collection in 0.56s
     时间: 2026-11-17（步骤 9 E3，实现前）

[绿] E3 命令: 同上
     退出码: 0
     用例计数: 5 passed in 0.38s
     门禁读数: tests-e3 pass（5 passed, 0.39s）；E1-E3 联合 21 passed/0.95s；tests-fast pass（58 passed, 14.10s）
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17（步骤 9 E3 完成后）

[红] E4 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_multiple_testing_ledger.py -q --tb=short
     退出码: 2
     关键失败行: E   ModuleNotFoundError: No module named 'factor_pipeline.backtest.multiple_testing_ledger'
     摘要: 1 error during collection in 0.47s
     时间: 2026-11-17（步骤 9 E4，实现前）

[绿] E4 命令: 同上
     退出码: 0
     用例计数: 10 passed in 0.55s
     门禁读数: tests-e4 pass（10 passed, 0.55s）；tests-fast pass（58 passed, 13.62s）；
               E1-E4 + multiple_testing 联合 82 passed / 14.73s
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17T22:45+08:00

[红] E5 补充用例命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_pipelines_hook.py tests/test_backtest/test_govbase_supplement.py -q --tb=short
     退出码: 1
     关键失败行:
       E   AttributeError: 'FactorProcessingPipelineV2' object has no attribute 'set_governance_hook'（T31/T32，3 处）
       E   assert getattr(got_old, "legacy", False) is True → False（T34）
     摘要: 4 failed, 2 passed in 2.61s
     说明: T33/T35 为既有实现的表征测试（先绿）；RULE-1 如实登记，不冒充红。
     时间: 2026-11-17（步骤 9 E5/E6 补充，实现前）

[绿] E5 补充用例命令: 同上
     退出码: 0
     用例计数: 6 passed in 0.93s
     门禁读数: tests-e5 pass（6 passed, 0.96s）；tests-e1 pass（11 passed, 0.43s）；
               tests-e4 pass（10 passed, 0.60s）；tests-fast pass（58 passed, 14.01s）；
               tests/test_pipelines_v2.py 13 passed / 5.69s
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17T23:33+08:00

[E5 对拍] 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" benchmarks/stata_econ_crosscheck.py --case all
     退出码: 0
     Stata: 18.0（C:\Program Files\Stata18\StataMP-64.exe）；fixture_hash=4ae7fa24a32694b0…
     读数: bh 3.331e-16；by 0；bonferroni 1.110e-16；holm 1.110e-16；
           romano_wolf 0；white_rc 0.56=0.56；hansen_spa [0.498, 0.56, 0.0] 全等；
           hac PASS（既有脚本；L3 约定差）；dsr/pbo SKIP（P1 未实装）
     Hansen 双口径: studentized 0.548 vs 仓库口径 0.498（差 0.05，仅披露不判定）
     SKIP 路径: --skip-stata 退出码 0；--case bh 仅输出 bh 行
     门禁: stata-e5 pass
     时间: 2026-11-17T23:34+08:00

[红] E6 补充用例（T36-T40 首轮）命令:
     "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest
     tests/test_backtest/test_pipelines_hook.py tests/test_backtest/test_govbase_supplement.py
     tests/test_backtest/test_multiple_testing_ledger.py -q --tb=short
     退出码: 1
     关键失败行:
       E   FileNotFoundError: tests/golden/govbase_v1_synth（T31 golden 基线缺失）
       E   AttributeError: 'CheckResult' object has no attribute 'name'（T37 测试缺陷，已改为 c.check）
     摘要: 2 failed, 20 passed in 2.21s
     说明: T36/T38/T39/T40 为既有实现的表征测试（先绿）；RULE-1 如实登记，不冒充红。
     时间: 2026-11-17（步骤 9 E6，T36-T40 实现前）

[红] T37 语义红（临时回退 `expected_missing_tail` 扣减、仅保留原 lag 判定后重跑）
     命令: 同上，仅 tests/test_backtest/test_govbase_supplement.py::test_t37_expected_missing_tail_not_freshness_gap
     退出码: 1
     关键失败行: E   AssertionError: assert False is True
                E   +  where False = CheckResult(check='freshness', passed=False, ...,
                   details={'field': 'fwd_return', 'lag': 1, 'max_lag': 0}).passed
     摘要: 1 failed in 0.49s
     时间: 2026-11-17（步骤 9 E6，T37 实现前）

[绿] E6 补充用例命令: 同首轮（三个测试文件）
     退出码: 0
     用例计数: 22 passed in 1.81s
     门禁读数: tests-e5 pass（10 passed, 1.25s）；tests-e4 pass（12 passed, 0.72s）；
               tests-fast pass（58 passed, 31.29s）；unit-tests pass
               （1907 passed / 7 skipped / 13 subtests passed / 1526.02s / 0:25:26，
                基线 1864 passed / 7 skipped；+43 = 本批 E1-E6 新增用例）
     其他: tests/golden/govbase_v1_synth 基线由 make_baseline.py 生成
           （36 月 × 20 股 × 2 因子，seed=20261117；rtol=1e-10/atol=1e-12）
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-17（步骤 9 E6 完成后；unit-tests 2026-11-18T00:13+08:00 收尾）

[红] T41-T45 命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_govbase_supplement.py -q --tb=short
     退出码: 1
     关键失败行: E   AttributeError: 'GovernanceRecord' object has no attribute 'broken_link'
                （ancestors 仍返回 List[GovernanceRecord]，无结构化断链标记）
     摘要: 1 failed, 10 passed in 1.18s
     说明: T42-T45 为既有实现的表征测试（先绿）；RULE-1 如实登记。
     时间: 2026-11-18（步骤 9 E7/T41-T45，T41 实现前）

[绿] T41-T45 命令: 同上
     退出码: 0
     用例计数: 11 passed in 0.75s
     联合: tests/test_backtest/test_governance.py + 本文件 22 passed in 1.05s
     门禁读数: tests-e5 pass（15 passed, 1.35s）；tests-e4 pass（12 passed, 0.66s）；
               tests-fast pass（58 passed, 13.74s）；治理联合 121 passed / 39.05s
     实现: AncestorEntry(record_id, record, broken_link, reason)；
           断链 reason=missing、非当前 schema reason=schema_mismatch；循环仍抛 GovernanceError
     session: factorpipe-govbase-step9-20261117
     时间: 2026-11-18（步骤 9 E7/T41-T45 完成后）

[红] E7 接线前命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" scripts/verify_capacity_impact.py --contract-only
     退出码: 2
     关键失败行: verify_capacity_impact.py: error: unrecognized arguments: --contract-only
     时间: 2026-11-18（E7 接线前）

[绿] E7 用例命令: "C:\Users\Peng\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_backtest/test_contract_gate.py -q --tb=short
     退出码: 0
     用例计数: 2 passed in 0.18s
     覆盖: market_fields 目录适配（含 list_date/calendar/barra 排除）+ 报告落盘 + 样本末推导
     时间: 2026-11-18（E7 接线后）

[E7 dry-run] 命令: 两个脚本各跑 `--contract-only`（E:\Ashare_data）
     退出码: 2（契约 FAIL，属**预期拦截**）
     读数: BLOCK freshness mv: lag=5, max_lag=1 (last_full=2026-01-23, end=2026-01-30)
           WARN freshness/coverage suspend（稀疏标志、无满覆盖日）
           WARN consistency return 越界 [-1, 10]；WARN adj_alignment 缺 81 日
           INFO schema industry 已知缺口
     产物: out/capacity_impact_contract.{json,md}、out/long_side_research_contract.{json,md}
     说明: 命中 DESIGN §5.2「当前 mv 5 日缺口必须被拦截」；默认路径（不带 --contract*）零变更。
     时间: 2026-11-18

[绿] E7 全量回归命令: python scripts/spec_runner_adapter.py gate unit-tests --session factorpipe-govbase-step9-20261117
     退出码: 0
     读数: 1914 passed, 7 skipped, 167 warnings, 13 subtests passed in 1406.66s (0:23:26)
     零变更: 基线 1864 passed / 7 skipped；+50 = 本批 E1-E7 新增用例
             （E6 收尾 1907 → E7 +7：T41-T45 5 + test_contract_gate 2）；0 失败 0 新增 skip
     session: factorpipe-govbase-step9-20261117（seq 25）
     时间: 2026-11-18T01:10:40+08:00
```

> 只有绿、无红 = 未按 TDD 执行，该行不得标 ✅（SPEC_PROCESS F5）。

### 5.4 Fixture 清单

| Fixture | 内容 | 用途 |
|---------|------|------|
| `synth_panel_36m_200s` | 36 月 × 200 股 × 4 因子合成面板 | golden / 契约正常路径 |
| `mv_gap_panel` | close 到 01-30、mv 到 01-23 | T11 |
| `pit_violation_panel` | 上市日前有值 | T13 |
| `p_registry` | m=20/200/2000 的 p 向量（固定 seed） | BH/BY/Holm/Bonferroni |
| `bootstrap_t_matrix` | B=500 的 t* 矩阵 + 索引 | RW 对拍 |
| `excess_matrix` | T=240,K=10 差分收益 | White/SPA |
| `legacy_record_payload` | v0.9 旧 schema JSON | T34 |
| `govbase_v1_synth`（提交式） | `tests/golden/govbase_v1_synth/`（values.parquet + manifest.json；36 月 × 20 股 × 2 因子，seed=20261117） | T31 零变更回归 |

---

## §6 性能验证

| 环节 | 预算 | 验证方法 | 失败处置 |
|------|------|---------|---------|
| 契约冷启动 | <10s | `time.perf_counter` 包 `check_data_contract`（7 字段） | 查 IO/重复扫描 |
| 契约缓存命中 | <0.1s | 第二次调用计时 | 查 cache key |
| 记录写入 10k | <0.1s | `append_many` 计时 | 查是否误用 executemany |
| BH 10 万假设 | <0.05s | 合成 p 向量计时 | 查是否 Python 循环 |
| RW m=1000,B=1000 | <0.5s | 合成 t* 矩阵计时 | 查是否逐 j 排序 |
| White/SPA T=1000,K=100,B=1000 | <10s / <1GB | 内存峰值用 `tracemalloc` | 调 chunk |
| golden 比较 24×300×4 | <0.1s | 计时 | 查重复转换 |
| 全量测试 | 不劣化 >20% | 基线（见 §0 E0）vs 实施后 | 定位慢测试 |

> 性能读数记入 `out/govbase_perf.json`（不入库），作为 E2 证据；预算超限 → P2 问题，不阻断功能验收，但须登记。

---

## §7 验收命令与证据出口

### 7.1 门禁命令（Spec_Runner，v1.11.0）

```bash
# 接入自检（已完成，session = factorpipe-probe-20261117）
python scripts/spec_runner_adapter.py probe

# 基线（本批 E0，2026-11-17）：tests-fast pass；unit-tests pass
#   unit-tests 读数 = 1864 passed, 7 skipped, 13 subtests passed, 1516.82s（25:16）
#   7 skipped 为仓库既有 skip；本批新增测试不得新增 skip（RULE-3）
python scripts/spec_runner_adapter.py gate tests-fast --session factorpipe-govbase-step5-20261117
python scripts/spec_runner_adapter.py gate unit-tests --session factorpipe-govbase-step5-20261117

# 实施后（E1-E6，同一 session 追加）
python scripts/spec_runner_adapter.py gate tests-e5 --session factorpipe-govbase-step9-YYYYMMDD
python scripts/spec_runner_adapter.py gate stata-e5 --session factorpipe-govbase-step9-YYYYMMDD
python scripts/spec_runner_adapter.py gate unit-tests --session factorpipe-govbase-step9-YYYYMMDD
```

- session 落 `F:\Spec_Workflow\tools\spec_runner\sessions\factorpipe-*.jsonl`；
- `replay` 校验 seq 单调 + 行可解析；
- `gate` 的 verdict = exit code 机械映射，无 LLM 判断。

### 7.2 证据等级映射（Step 10 用）

| 验收项 | 证据 | 等级 |
|--------|------|------|
| 全量/定向测试 | runner gate 事件流 + pytest 退出码 | E1 |
| 版本一致性 | `test_fix3_version_unification` 通过 + grep 5 处 | E1 |
| 模块隔离 | AST 测试 + `git diff --stat` | E1 |
| 性能预算 | `out/govbase_perf.json` + 计时脚本 | E2 |
| Stata 对拍 | `out/stata_econ_crosscheck.json` + Stata 版本 | E2（场景自选，附命令） |
| 设计条文落地 | 行号对照（`Lxxx@commit`） | E3 |
| 盲区扫描 | 本 doc §9 + DESIGN §19 | E4（发现 N 项语气） |

### 7.3 不达标处置

- P1（阻断验收）：任一 block 级测试失败、record_id 不确定、默认路径 golden 出现差异 → 修复后重跑；
- P2（应修）：性能超预算、文档不一致、Stata SKIP 无记录 → 登记并修复；
- P3（提示）：注释/命名/可读性。

---

## §8 回滚与风险

### 8.1 回滚点汇总

| 层 | 回滚动作 | 影响 |
|----|---------|------|
| 模块 | 删除 4 个新文件 | 无调用方（D1），零波及 |
| 既有代码 | 删除 `bootstrap_indices` 分支 / 删除 hook 方法 | 默认 None，行为回到 3.5.3 |
| 版本 | 5 处字面量回退 3.5.3 | 版本测试恢复 |
| 数据 | `tests/golden/` 删除 | 仅测试失败，无运行时影响 |
| 流程 | 删除 `scripts/spec_runner_adapter.py` | 仅失去门禁入口 |

### 8.2 风险（承接 DESIGN §14，新增本批项）

| # | 风险 | 处置 |
|---|------|------|
| R1 | 三分母被误读 | `to_markdown` 固定解释 + T29 |
| R2 | 同输入不同结果 | `payload_hash` 冲突显式抛错 |
| R3 | 数据布局变化 | `FieldReader` 注入；默认映射集中一处 |
| R4 | 并发写 | 单写者默认；JSONL 用 `lock_path` |
| R5 | Hansen 未 studentize | P0 双口径对拍；P1 决策 D-1 |
| R6 | bootstrap 来源不可信 | 索引 SHA256 + seed 存证 |
| R7-R12 | 见 DESIGN §14 | 同设计 |
| **R13** | **设计文档不入库，E3 行号证据不可绑 commit** | 本文档复述关键签名（可入库副本）；DESIGN §19.4 登记 |
| **R14** | **模块异常基类与 DESIGN §10.3 不一致** | 采用局部基类，§9.6 F1 登记；不改设计意图 |
| **R15** | **全量测试基线耗时未知/波动** | E0 读数 = 1864 passed / 7 skipped / 1516.82s（2026-11-17，`factorpipe-govbase-step5-20261117`）；实施后用同一命令对比，>20% 劣化须定位 |

---

## §9 步骤 6 review 记录（实施文档幻觉消除）

> **性质**：`自查·并发`（RULE-1 初始）→ **`已复核·独立 pass`**（正文完稿后另起一遍；仍为同基座，见 §9.7）。
> RULE-4 单视角声明适用（同一 agent、同一基座）；RULE-5 异构审查未满足。
> **方法**：逐条回源（签名/版本/行号/依赖/性能数字/低效排除），不复述设计结论。

### 9.1 版本存在性核验

| 依赖 | 核验方式 | 读数 | 状态 |
|------|---------|------|------|
| Python 3.9 下限 | 语法扫描（注解/内置泛型） | 全文未用 PEP 604 联合类型、未用内置泛型下标 | ✅ |
| pydantic >=2.0.0 | `python -c import pydantic`（py312） | 2.13.4 | ✅ |
| duckdb >=0.10.0 | 同上 | 1.5.3 | ✅ |
| numpy >=1.22.0 | 同上 | 2.4.6 | ✅ |
| pandas >=2.0.0 | 同上 | 2.2.3 | ✅ |
| pytest >=7.0.0 | 同上 | 9.0.3 | ✅ |
| Stata 18 MP | 路径存在性 | `C:\Program Files\Stata18\StataMP-64.exe` | ✅（可选） |

> 均为**已安装版本**（可直接 import），满足"版本可查到"；未新增依赖，故无 PyPI 新包核验项。

### 9.2 签名可实现性

| 接口 | 核对点 | 结论 |
|------|--------|------|
| `GovernanceRecord.build()` | frozen + 一次构造；`model_validator` 只读 | 可实现 |
| `compute_record_id` | 仅用 `ID_FIELDS`；`canonical_json` 稳定 | 可实现 |
| `GovernanceStore.append_many` | DataFrame 列与表列对齐；`INSERT...SELECT` | 可实现 |
| `_parse_legacy` | pydantic `model_validate` + `extra='allow'` 需 `model_config` 副本 | **需实现细节**：用 `create_model` 或宽松副本；已在 §2.1 注 |
| `check_data_contract` | `Protocol` + 默认 readers | 可实现 |
| `DataSnapshot.stable_hash` | 排序后 canonical JSON | 可实现 |
| `GoldenMaster.capture` | DuckDB `COPY` 写 parquet；无 pyarrow | 可实现（duckdb 1.5.3 支持） |
| `MultipleTestingLedger.apply` | 复用 `apply_*`；RW 快速核 | 可实现 |
| `HansenSPA.test(bootstrap_indices=...)` | 追加 kwarg；位置参数不变 | 可实现 |
| `pipelines_v2.set_governance_hook` | 纯赋值；fit 一处条件调用 | 可实现 |
| `benchmarks` CLI | argparse；subprocess `/e do` | 可实现（已有 `verify_hac_stata.py` 先例） |

### 9.3 stdlib API 下限

| API | 最低版本 | 用途 | 结论 |
|-----|---------|------|------|
| `dataclasses.dataclass(frozen=True)` | 3.7 | 值对象 | ✅ |
| `dataclasses.replace` | 3.7 | registered_at 持久化副本 | ✅ |
| `typing.Protocol` | 3.8 | FieldReader | ✅ |
| `typing.Literal` | 3.8 | GateResultPayload | ✅ |
| `functools.cached_property` | 3.8 | config_hash 缓存 | ✅ |
| `msvcrt.locking` | Windows | JSONL 锁 | ✅（仅 Windows 分支） |
| `hashlib.sha256` | 全版本 | 全部 id/hash | ✅ |
| `zoneinfo` | **未使用** | —— | 避免 tzdata 依赖 |

### 9.4 无虚构库/函数

- 全文只引用 numpy/pandas/scipy/pydantic/duckdb 与 stdlib；
- 未引用 pandas 2.x 已移除 API（`append`/`iteritems`）；
- DuckDB 只用 `executemany` 之外的能力（`execute`/`COPY`/`read_parquet`），未用 `MERGE`；
- Stata 只用内置 `import delimited / sort / mata / regress / newey / mtest`，未假设 SSC 包存在。

### 9.5 低效排除核对

| 检查 | 结果 |
|------|------|
| 是否存在 `executemany` 批量写 | 否（§4 #1 明确禁止） |
| 是否存在因子循环内 IO | 否（契约会话级一次，§4 #2/#10） |
| 是否存在逐假设 Python 循环 | 否（§4 #3） |
| 是否存在逐 j 重复排序 | 否（§4 #4） |
| 是否存在无界内存 bootstrap | 否（§4 #5 分块） |
| 是否每次运行重新生成 experiment_id | 否（§4 #7） |

### 9.6 发现与修正

| # | 严重度 | 发现 | 修正 |
|---|--------|------|------|
| F1 | MAJOR | DESIGN §10.3 让 `DataContractError/PreregistrationError/TrackMismatchError/GoldenMismatchError` 继承 `GovernanceError`，与 D1「四模块互不 import」直接冲突；按设计写会形成 `data_contract → governance` 等反向依赖 | 实施改为**模块内局部异常基类**（§3.5），保留错误语义；设计意图（错误分类）不变，依赖图不破 |
| F2 | MAJOR | `_parse_legacy` 若直接 `GovernanceRecord.model_validate` 旧 payload，`extra='forbid'` 会拒绝新增/缺失字段，与"不丢历史"承诺冲突 | 明确用宽松副本（`create_model` 或 `model_construct` + 补默认）解析；T34 覆盖更旧/更新两分支 |
| F3 | MINOR | `payload_hash` 若在 `timestamp` 补全前计算，同输入两次运行 hash 不同（timestamp 已排除，但 payload 内容含 timestamp 值） | 明确：`timestamp` 先补 UTC now，再计算 payload；因 `timestamp` 在排除集，值无关，但 dict 形状须稳定 |
| F4 | MINOR | `expected_missing_tail` 与 `max_lag` 交互未写清：剥离末行后 `sample_end` 是否同步回退 | 明确：`effective_end` 与 `last_full_date` **均不变**（保持原始快照可追溯），仅在 freshness 判定时从 `lag` 扣减 `expected_missing_tail`；`raw_lag` 写入 `details`；T37 固定该语义 |
| F5 | MINOR | `GoldenMaster.capture` 的 manifest 未定义必填键，`force` 审计会漏 | 明确必填：`baseline_id/created_at/pipeline_version/factor_ids/periods/n_tolerances/files`；`force` 时追加 `reason/reviewer` |
| F6 | MINOR | DESIGN §5.1 写 `ContractReport.known_gaps: Tuple[str, ...]`，§5.7.4 又写「升级为结构化 `KnownGap`」——同一字段两处类型不一致 | 实施取**较新的 §5.7.4**（`Tuple[KnownGap, ...]`）；§5.1 视为被 §5.7.4 取代，Step 8 一致性 review 须显式登记该替换 |
| F7 | MINOR | DESIGN §5.1 `DataSnapshot` 字段顺序为 `universe_version`（无默认）→ `universe_bias`（有默认）→ `calendar_hash`（无默认），违反 dataclass「有默认字段必须在后」规则，按原文写会在 import 时 `TypeError` | 实施给 `calendar_hash` 补 `= None` 默认（语义不变：None = 未提供日历）；字段顺序保持 |

### 9.7 复核结论

**独立 pass**（2026-11-17，正文完稿后另起一遍）：机械核对读数 = DESIGN §10.1 公共符号 **32/32** 在本文出现、
DESIGN §12 测试项 **32/32** 在本文映射、三文档代码围栏全配对、表格列数 0 处失配；
另逐条复核版本锚点（5 处）与依赖读数（6 项）。本 pass 新发现 F6/F7 两处（类型不一致 / dataclass 默认值顺序）。

**PASS_WITH_FIXES**：2 处 MAJOR（跨模块异常继承、旧 schema 宽松解析）+ 5 处 MINOR 已在本文修正；
其余签名、版本、stdlib 下限、低效排除均可回源。本文可作为步骤 7 checklist 的基线。

> 独立性声明：本条为**自查（单视角，同基座）**；RULE-5 异构审查由 §9.8 补齐（reviewer =
> GLM-5.3-Flash，异构家族）。本小节自身仍不得在步骤 10 审计中升级为 E1/E2 证据；
> §9.8 的 E2 证据仅限其列出的探针读数。

### 9.8 异构复审（步骤 9 后，RULE-5）

> 基座：reviewer = GLM-5.3-Flash，implementer = DeepSeek-V4.1-Flash（异构模型家族）；
> 权限：reviewer 只标记、**未改写实现**（RULE-5 单向权限）。
> 探针脚本：[probe_review_govbase.py](../out/probe_review_govbase.py)（可重放）；
> 读数留档：[review_govbase_results.txt](../out/review_govbase_results.txt)。

| # | 探针（视角） | 读数 | 判定 |
|---|------------|------|------|
| P1 | record_id 独立重算（可复现性） | 独立 canonical+SHA256 逐位一致；100 次同输入 1 值；3 身份字段→4 id；`notes` 不变 id、`p_value` 变 payload_hash | 加固 |
| P2 | BH/BY 独立实现（统计口径） | BH m=7/50/500、BY m=7/50 全部 `max abs(dq)=0`，掩码一致 | 加固 |
| P3 | JSONL 4 线程并发 append（健壮性） | 40 行、可解析、id 唯一、0 线程异常、lock 文件在 | 加固 |
| P4 | ancestors 三态（实施忠实度） | 正常链 broken=False；断链 `reason=missing`；未来 schema `reason=schema_mismatch` | 加固 |
| P5 | White RC 注入对账（统计口径） | 同 idx 两次 `rc_p` 确定（0.66）；注入/None 均可运行、字段齐全 | 加固 |
| P6 | CHECKLIST 汇总对账（结论效度） | §3.5 实为 16 行（T31-T46），与 §10 括号 16 一致 | 确认 |
| P7 | 零变更算式（结论效度） | 1864+43=1907；1907+7=1914 | 确认 |
| P8 | 模块隔离 + hook 零变更面（静态 E3） | 四模块互不 import；`_governance_hook` 6 处引用均 None 守卫 | 加固 |

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| F1 | MINOR/披露 | `_file_lock` 跨平台等待语义不一致：Windows `LK_LOCK` 重试约 10 s 后抛 `OSError`，POSIX `flock` 阻塞至获得 | §2.1 要点 5 已注；不阻断，跨进程超时策略留后续批次 |
| F2 | MINOR/披露 | 注入路径 `individual_p_values` 为联合重抽样边际 p，与 `None` 路径逐列独立 bootstrap 口径不同 | §2.5 已注；仅作对照，不改主 p 值口径 |
| F3 | 探针勘误 | 复审员 BY 独立公式首版误写为除以 H_m（标准 BY 应乘 C(m)），修正后 0 差 | 无需处置（实现为标准 BY） |

**结论**：PASS_WITH_NOTES — 0 推翻 / 0 重大 / 0 中等；2 项 MINOR 披露已入正文。
取证分级：P1-P5/P8 = E2（探针可重放）；P6/P7 = E3（文档文本核对）；gate 读数 = E1（runner seq 25）。
E5 级推测证据未使用；发现数按实测登记（3 项，含 1 项复审员自误）。

---

## §10 设计 ↔ 实施映射（步骤 6 对齐自检）

| DESIGN 条目 | 实施落点 | 状态 |
|------------|---------|------|
| §4 GR-1 数据模型/条件校验/确定性 id/存储 | §2.1 + §2.1.1 + §3.4 | ✅ |
| §4.5 管线接入 | §2.6 | ✅ |
| §5 GR-2 数据模型/默认字段/检查/新鲜度/性能/词汇表 | §2.2 + §3.4 | ✅ |
| §6 GR-3 基线/比较/采集纪律/性能 | §2.3 + §5.4 + §6 | ✅ |
| §7 GR-4 台账/预注册/三分母/校正/接口/存储/性能 | §2.4 + §2.5 + §4 + §6 | ✅ |
| §8 Stata 对拍 | §2.7 + §6 | ✅ |
| §9 性能预算 | §4 + §6 | ✅ |
| §10 接口汇总/错误类型 | §2 + §3.5（F1 修正） | ✅ |
| §11 零变更承诺 | §1 回退点 + §5 T31/T45 | ✅ |
| §12 测试设计 | §5.1 + §5.2 | ✅ |
| §13 实施顺序 | §1 E0-E8 | ✅ |
| §14 风险 | §8.2 | ✅ |
| §18 第三轮修正（F-A~F-H/B*） | §2.1 注 + §5.2 T33-T46 | ✅ |
| §19 替代方案/边界/版本化 | §9 + §8.1 + §8.2 R13 | ✅ |

---

## §11 F1-F5 取证字段（本步骤适用项）

| 字段 | 出具 |
|------|------|
| F1 来源日期 | 本批所有内部事实读取日 = 2026-11-17；外部文献日期见 RESEARCH §2 表 |
| F2 来源版本 | 代码 = `factor_pipeline 3.5.3` + 行号；依赖 = §3.2 实测版本；设计 = v1.2；调研 = v1.1 |
| F3 降级链 | `F:\Spec_Runner`（v1.0.0，P-019 后冻结）→ `F:\Spec_Workflow\tools\spec_runner\spec_runner.py`（v1.11.0）→ 命令面与事件流 schema 一致；无其他降级 |
| F4 引用验证表 | 本步骤无新增外部引用；沿用 RESEARCH §9.2 的 5/5 命中读数 |
| F5 先失败记录 | **本步骤 N/A**（Step 5 只写文档）；Step 9 实施时按 §5.3 两读数块出具 |

---

## §12 未决项登记（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|------|---------|---------|---------|
| D-1 Hansen 是否按原文 studentize | 与 Stata 原文口径对拍 DIFF 时有消费方影响评估 | P1；本批 E5 产出双口径差异 | 不修复，先双口径披露 | E2（E5：studentized 0.548 vs 仓库 0.498，差 0.05） |
| D-2 RW 快速核是否下沉 `multiple_testing.py` | T27 等价性 + 性能读数达标 | 步骤 9 E4 完成时 | 仅台账内使用 | E1（T27 通过，≤1e-15） |
| D-3 golden 是否纳入 record_id 向量基线 | 基线机制能覆盖治理件自身 | 步骤 9 E3 完成时 | 纳入，作为第二基线 | E4（倾向） |
| D-4 `ancestors()` 断链是否结构化标注 `broken_link` | T41 验收前决定签名形态 | 步骤 9 E6 完成后（2026-11-18 裁定） | **已解决**：采用 `AncestorEntry`（决策锚点：git `rev-list --missing=print` 缺失对象以 `?` 标记不中断；GraphQL 部分成功 data+errors） | E1（T41 红→绿；全仓无调用点） |
| D-5 `default_fields()` 与真实目录布局不一致 | 直接对 `E:\Ashare_data` 调用默认字段时 | 步骤 9 E7 实施时（2026-11-18） | E7 组合层适配（排除 `list_date`/`calendar`/`barra`、字符串日期索引归一化）；核心 `default_fields()` 的修正留后续批次 | E2（dry-run BLOCK mv 被正确拦截；其余字段通过适配读取） |
| U1 RW/White/SPA 真实 A 股 size/power | 1000 reps 拒绝率 ∈ [0.03,0.07] | 步骤 9 后 | 未知 | E5（待核） |
| U2 PBO S 选择 | 预注册 + 敏感性 | P1 | S=10，12/16 敏感性 | E5（待核） |
| U3 DSR 有效 N | N 敏感性报告 | P1 | 未知 | E5（待核） |
| U4 Stata SSC 第二参照 | `rwolf2/multproc` 可用时 | 可选安装 | 不阻塞 | E5（待核） |

---

## §13 下一步

1. 步骤 7：`docs/audit/CHECKLIST_V3.6.0_GOVERNANCE_BASE.md`（每项 DoR/DoD）；
2. 步骤 8：四文档一致性 review（机械读数 + 双向引用 + 断言延续）；
3. 步骤 9：TDD 实施（E1 → E2 ∥ E3 → E4 → E5 → E6），红→绿两读数入档；
4. 步骤 10：ADD 四阶段审计 + 取证矩阵 E1-E5。
