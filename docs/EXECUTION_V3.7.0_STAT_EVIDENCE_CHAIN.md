# EXECUTION v3.7.0 统计证据链 — P1 六项 (SE-1 ~ SE-6)

> **版本**: v1.2 (2026-11-18；v1.0 = 步骤 5 初稿；v1.1 = 步骤 6 独立复审 F1-F7 修正，见 §10；v1.2 = 步骤 8 一致性对齐：设计引用升 v1.2、流程状态回填，F1-F7 见 [CONSISTENCY_REVIEW](audit/CONSISTENCY_REVIEW_V3.7.0_STAT_EVIDENCE_CHAIN.md))
> **上游设计**: [DESIGN_STAT_EVIDENCE_CHAIN.md](private/DESIGN_STAT_EVIDENCE_CHAIN.md) v1.2（本地，gitignored；步骤 4 复审见其 §21；步骤 6 补口见其 §14.7/§22；步骤 8 对齐见其 §23）
> **上游调研**: [RESEARCH_STAT_EVIDENCE_CHAIN.md](research/RESEARCH_STAT_EVIDENCE_CHAIN.md) v1.2（含 §12 独立复审与 §13 边界 purge 回填）
> **上游方案**: [多因子治理路线图 §5 P1](analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md#L203-L220) / [§6 G2](analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md#L275-L288)
> **目标版本**: 3.7.0（`pyproject.toml` 3.6.0 → 3.7.0；缓存代际 `v2.3.0-cache` **不变**）
> **批次档位**: **大任务 / T1**（3 个新模块 + 3 处契约扩展 + 4 个新 ADR → 全 10 步，不裁剪步骤 7-8）
> **新增依赖**: 零（仅用已声明的 numpy / scipy / pandas / duckdb / pydantic）
> **关联 ADR**: ADR-055 ~ ADR-058（ADR-055 起未占用）
> **说明**: 本文件只做实施规划；代码在步骤 9 按 §1 顺序落地。所有「待实测」读数在步骤 9 回填。

---

## §0 摘要、档位与工件状态

### 0.1 交付内容

| 工件 | 类型 | 内容 | 阶段 | 状态（步骤 9 实施后） |
|------|------|------|------|-------------------|
| `backtest/cross_validation.py` | 新增 | `PurgedKFold`、`CombinatorialPurgedKFold`、`HoldoutRegistry`、`require_locked`、两个异常 | E1 | 已完成 |
| `backtest/overfitting.py` | 新增 | `deflated_sharpe_ratio`、`probability_of_backtest_overfitting`、`sharpe_ratio`、`trim_to_divisible` | E2 | 已完成 |
| `backtest/effect_size.py` | 新增 | `newey_west_se`、`mean_ci`、`sharpe_ci`、`stationary_bootstrap_indices`、`effect_summary` | E3 | 已完成 |
| `backtest/specification_logger/spec_log.py` | 扩展 | schema v2 字段、`content_hash`、`get_specification_matrix` | E4 | 已完成 |
| `backtest/specification_logger/spec_curve.py` | 扩展 | 模块级 `joint_inference` | E4 | 已完成 |
| `backtest/specification_logger/pre_registration.py` | 扩展 | `content_hash`、`verify_compliance` 可选参数 | E4 | 已完成 |
| `backtest/specification_logger/__init__.py` | 扩展 | 导出 `joint_inference` | E4 | 已完成 |
| `backtest/multiple_testing_ledger.py` | 扩展 | `FamilySpec.stage`、`holdout_checker`、stage 校验 | E5 | 已完成 |
| `backtest/governance.py` | 扩展 | `dsr/pbo` 范围、`oos_metric` 结构、`G2Policy`、`evaluate_g2` | E6 | 已完成 |
| `benchmarks/stata_econ_crosscheck.py` | 微调 | `P1_CASES` detail 改 N/A | E7 | 已完成 |
| `scripts/verify_stat_evidence.py` | 新增 | MC 校准 + 泄漏探针 + smoke | E7 | 已完成 |
| `tests/test_backtest/test_cross_validation.py` | 新增 | T01-T14b（16 项） | E1 | 已完成 |
| `tests/test_backtest/test_overfitting.py` | 新增 | T15-T26b（13 项） | E2 | 已完成 |
| `tests/test_backtest/test_effect_size.py` | 新增 | T27-T33b + T32b（9 项） | E3 | 已完成 |
| `tests/test_backtest/test_spec_curve_v2.py` | 新增 | T34-T40c（9 项） | E4 | 已完成 |
| `tests/test_backtest/test_g2_gate.py` | 新增 | T41-T46 + T41b/T45b（8 项） | E5/E6 | 已完成 |
| `tests/test_backtest/test_specification_logger.py` | 扩展 | v2 兼容用例（T35 就地） | E4 | 已完成 |
| `tests/test_backtest/test_multiple_testing_ledger.py` | 扩展 | stage / holdout 回调 | E5 | 已完成 |
| `docs/DECISIONS.md` | 扩展 | ADR-055 ~ ADR-058 | E8 | 已完成 |
| `docs/CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `README.md` | 扩展 | v3.7.0 登记 | E8 | 已完成 |

### 0.2 档位判定（SPEC_PROCESS v1.7.2 §批次档位 / WORKFLOW_METHODOLOGY §13.8）

| 判据 | 读数 | 结论 |
|------|------|------|
| 任务规模 | 3 个新模块 + 3 个既有模块契约扩展 + 4 个新 ADR（跨模块、兼容性风险） | **大任务** |
| 改动路径 ∩ `{scripts/, tests/, benchmarks/}` | 非空 | Layer-1 |
| 强制升级条款：契约 / 真值源 / 门禁变更 | 命中（spec JSONL schema v2、ledger family 指纹、`GovernanceRecord` 校验、G2 门禁） | **T1** |
| 流程裁剪 | 无；步骤 7 checklist + 步骤 8 一致性 review 必须产出 | 全 10 步 |

> 工件命名沿用本仓映射：RESEARCH=`docs/research/`、DESIGN=`docs/private/`、
> IMPLEMENTATION=`docs/EXECUTION_*.md`、CHECKLIST/CONSISTENCY=`docs/audit/`。

### 0.3 与路线图 P1 六项的映射

| 路线图项 | 设计落点 | 本批工件 | 验收测试 |
|---------|---------|---------|---------|
| P1-① 样本外协议 + holdout 锁 | 设计 §4 | `cross_validation.py` | T01-T14b |
| P1-② DSR + PBO | 设计 §5 / §6 | `overfitting.py` | T15-T26 |
| P1-③ L2 多重检验升级（FDR/FWER 分轨） | 设计 §9 / §10 | `multiple_testing_ledger.py` + `governance.py` | T41-T46 |
| P1-④ 规格曲线 + 联合推断 | 设计 §7 | `specification_logger/*` | T34-T40b |
| P1-⑤ 效应量 + CI 强制 | 设计 §8 | `effect_size.py` | T27-T33 |
| P1-⑥ 组合层不跳过校正 | 设计 §9 | ledger `stage` + `evaluate_g2` | T46 / T41 |
| G2 门禁（§6） | 设计 §10 | `G2Policy` / `evaluate_g2` | T41-T45b |

### 0.4 设计决策 D1-D14 的实施落点

| 决策 | 实施落点 | 验收 |
|------|---------|------|
| D1 CPCV 主协议 / purge 1 / holdout 12 月 / 2024-12 边界 purge | `cross_validation.py` 默认参数 + `HoldoutRegistry.dev_mask(purge=1)` | T02/T03/T13 |
| D2 `HoldoutRegistry`（DuckDB `cv_holdout`）+ 重叠拒绝 | `cross_validation.py` `HoldoutRegistry` | T09-T12b/T14b |
| D3 DSR 逐期 SR / N=ledger / V=1/(T−1) | `overfitting.deflated_sharpe_ratio` | T15-T20 |
| D4 PBO CSCV 严格整除 / S=8 主 | `overfitting.probability_of_backtest_overfitting` + `trim_to_divisible` | T21-T26 |
| D5 spec schema v2 + 旧 5 键不变 | `spec_log.py` | T34/T35 |
| D6 联合推断 null-imposed bootstrap | `spec_curve.joint_inference` | T36-T40 |
| D7 效应量三口径 + CI 同口径 | `effect_size.py` | T27-T33 |
| D8 `FamilySpec.stage` + `holdout_checker` | `multiple_testing_ledger.py` | T46 / 扩展用例 |
| D9 `GovernanceRecord` 校验 + `evaluate_g2` | `governance.py` | T41-T45b |
| D10 模块边界（不互相 import） | 见 §2 各模块 import 清单 | 代码评审 + 导入图检查 |
| D11 默认零变更 | 不改 `backtest/__init__.py`；新参数全可选 | §5.2 golden master |
| D12 Python 3.9 / pydantic v2 / DuckDB JSON / 无新依赖 | 全模块 | §5.2 py3.9 AST 扫描 |
| D13 样本映射 58 / 56 / 54 | 常量与默认参数 | T13 + §6 实测 |
| D14 回顾性不可追认 | `assert_locked_before` + 脚本/报告模板文案 | T14b |

### 0.5 步骤 5 实施澄清（对设计的 3 处补口，不改设计语义）

| # | 问题 | 定案 | 理由 |
|---|------|------|------|
| C1 | 设计 §8.2 与 §11.1 对 `sharpe_ratio` 归属不一致（§8 示例写在 `effect_size`，§11.1 列在 `overfitting`） | **唯一公共实现放 `overfitting.sharpe_ratio`**；`effect_size.sharpe_ci` 内部用私有 `_sharpe_per_period`（同公式 `ddof=1`），不 import `overfitting`（守 D10）；新增 **T32b** 跨模块数值一致性断言（测试层可同时 import） | 避免两个公共同名符号漂移，同时不破坏模块边界 |
| C2 | 设计 §10.2 要求「方法名常量与 `CorrectionMethod` 一致」但未编号测试 | 新增 **T41b**：`governance` 的 FDR/FWER 常量集合与 `multiple_testing_ledger.CorrectionMethod` 逐字一致 | 该断言明确写在设计 §10.2，补编号以免漏测 |
| C3 | 设计 §10.3 的 `GovernanceRecord` 结构校验未编号测试 | 新增 **T45b**：`dsr/pbo` 越界或 NaN、`oos_metric` 缺键/类型错 → `ValueError` | 同 C2 |

> 新增 3 个测试后总数 **52**（原 49）。测试编号沿用 `b` 后缀惯例（对齐 T12b/T14b/T40b）。
> 上述补口列入步骤 6 review 的核对清单（§9）。

---

## §1 任务分解（E0-E8）

| E | 任务 | 输入 | 产出 | 依赖 | 验收命令 | 回退点 |
|---|------|------|------|------|---------|--------|
| E0 | 基线冻结 | 当前 3.6.0 工作区 | 基线读数（全量 pytest / golden master / 版本一致性） | — | §5.1 | 无代码变更 |
| E1 | 样本外协议 | 设计 §4 | `cross_validation.py` + `test_cross_validation.py` | — | `python -m pytest tests/test_backtest/test_cross_validation.py -q` | 删除模块与测试；无调用点 |
| E2 | DSR / PBO | 设计 §5 / §6 | `overfitting.py` + `test_overfitting.py` | — | `python -m pytest tests/test_backtest/test_overfitting.py -q` | 删除模块与测试 |
| E3 | 效应量 / CI | 设计 §8 | `effect_size.py` + `test_effect_size.py` | — | `python -m pytest tests/test_backtest/test_effect_size.py -q` | 删除模块与测试 |
| E4 | 规格曲线 v2 | 设计 §7 | `specification_logger/*` 四处改动 + `test_spec_curve_v2.py` + 旧测试扩展 | E3（CI 口径参考，不 import） | `python -m pytest tests/test_backtest/test_spec_curve_v2.py tests/test_backtest/test_specification_logger.py -q` | 新参数全可选：不传即旧记录格式 |
| E5 | 台账 stage / holdout 回调 | 设计 §9 | `multiple_testing_ledger.py` + `test_g2_gate.py` 的 T46 | E1 | `python -m pytest tests/test_backtest/test_multiple_testing_ledger.py tests/test_backtest/test_g2_gate.py -q` | `holdout_checker=None` + `stage` 默认值 → 旧行为 |
| E6 | G2 门禁 | 设计 §10 | `governance.py` 扩展 + `test_g2_gate.py` | E2/E3/E5 | `python -m pytest tests/test_backtest/test_g2_gate.py tests/test_backtest/test_governance.py -q` | 删除 `evaluate_g2`/`G2Policy`；校验只在字段提供时生效 |
| E7 | 独立验证脚本 | 设计 §14.6 | `scripts/verify_stat_evidence.py` + Stata detail 文案 | E1-E6 | `python scripts/verify_stat_evidence.py --section all --n-sim 200` | 删除脚本；Stata 对拍仍 SKIP 退出码 0 |
| E8 | 文档闭环 | 全部 | ADR-055~058 / CHANGELOG / PROJECT_STATUS / README / 版本 3.7.0 | E1-E7 | `python -m pytest tests/test_fix3_version_unification.py -q` | 文档与版本号回滚 |

**实施顺序**：E0 → E1 ∥ E2 ∥ E3 → E4 → E5 → E6 → E7 → E8。
**禁止**：
1. 先做 E6（`evaluate_g2`）再补 E2/E3——评估器依赖 DSR/效应量返回键稳定；
2. 在 E4 中修改 `get_specification_curve` 的 5 键返回——只用新增方法；
3. 任何阶段改 `backtest/__init__.py`（D11）。

**每阶段纪律**：先写测试（红）→ 实现（绿）→ 本文件 §5.3 回填读数 → 再进入下一阶段。阶段之间不并行改同一文件。

---

## §2 接口签名与回退点

> 签名即实现契约；步骤 6 逐条核「可实现性」，步骤 9 按此写测试。
> 全部使用 Python 3.9 语法：`Optional[...]` / `List[...]` / `Dict[...]` / `Tuple[...]`，**禁止** `X | Y`。

### 2.1 `backtest/cross_validation.py`（E1）

```python
class HoldoutRegistryError(RuntimeError): ...
class HoldoutReuseError(HoldoutRegistryError): ...

class PurgedKFold:
    def __init__(self, n_splits: int = 5, purge: int = 1,
                 embargo: int = 1, label_horizon: int = 1) -> None: ...
    @property
    def split_id(self) -> str: ...            # "pkf_n5_p1_e1_h1"
    def split_groups(self, n_samples: int) -> List[np.ndarray]: ...
    def split(self, n_samples: int) -> Iterator[Tuple[np.ndarray, np.ndarray]]: ...

class CombinatorialPurgedKFold:
    def __init__(self, n_groups: int = 6, n_test_groups: int = 2,
                 purge: int = 1, embargo: int = 1,
                 label_horizon: int = 1) -> None: ...
    @property
    def n_paths(self) -> int: ...             # math.comb(N, k)
    @property
    def split_id(self) -> str: ...            # "cpcv_n6_k2_p1_e1_h1"
    def split_groups(self, n_samples: int) -> List[np.ndarray]: ...
    def split(self, n_samples: int
              ) -> Iterator[Tuple[np.ndarray, np.ndarray, int]]: ...

class HoldoutRegistry:
    def __init__(self, db_path: str = "holdout_db.duckdb",
                 table_prefix: str = "cv_", enable: bool = True) -> None: ...
    def lock(self, start: str, end: str, universe_version: str,
             batch_id: str, *, price_convention: str = "hfq",
             return_convention: str = "monthly_next",
             locked_at: Optional[str] = None, note: str = "") -> str: ...
    def check(self, holdout_id: str) -> Optional[Dict[str, Any]]: ...
    def assert_locked_before(self, holdout_id: str, run_at: str) -> None: ...
    def dev_mask(self, dates: Sequence[str], holdout_id: Optional[str],
                 purge: int = 1) -> np.ndarray: ...
    def list_locks(self) -> List[Dict[str, Any]]: ...

def require_locked(registry: HoldoutRegistry) -> Callable[[str, str], None]: ...
```

**实现要点**

| 项 | 规则 |
|----|------|
| 内部辅助 | `_segments(idx)` 切连续段；`_excluded_mask(test_idx, purge, embargo, label_horizon)` 逐段生成 purge/embargo 掩码（CPCV 不连续测试块必须逐段，禁止 `min/max` 一把梭） |
| 折界 | `np.array_split(np.arange(T), n_splits)`；余数分到前面的折；确定性 |
| purge 口径 | 训练样本 `t` 满足 `t + label_horizon >= a` 且 `t <= b` 剔除（保守口径，多剔 `a−1`，设计 §4.1/F5） |
| embargo | `[b+1, b+embargo]` 剔除；`b` 为测试段终点 |
| 校验 | `n_splits>=2`、`purge>=0`、`embargo>=0`、`label_horizon>=1`、`T >= n_splits+purge+embargo+label_horizon`；CPCV 另加 `n_groups>=2`、`1<=k<N`、`T>=N`；失败 `ValueError` |
| holdout 存储 | DuckDB；`CREATE TABLE IF NOT EXISTS {prefix}holdout (...)`；只用 `CREATE/INSERT/SELECT` |
| `holdout_id` | `SHA256(canonical_json({start,end,universe_version,price_convention,return_convention}))`（完整 64 位） |
| `check` 返回 | 9 键 Dict：`holdout_id/start/end/universe_version/batch_id/locked_at/price_convention/return_convention/note`（表列 6 字段 + payload 展开 3；步骤 6 定案，T09 断言键集合） |
| 拒绝规则 | 设计 §4.4 规则 1-8 全量实现；`enable=False` 所有方法抛 `HoldoutRegistryError` |
| `dev_mask` | 只保留 `date < start`，再剔除起点前 `purge` 个标签；`date >= start` 全 False；`dates` 非升序 → `ValueError`；`holdout_id=None` → 全 True（未锁定批次的回顾性研究路径，`full_retrospective` 披露责任在调用方——设计 §4.4 样本映射，属 D14 机制）；`holdout_id` 非 None 且不存在 → `HoldoutRegistryError`（设计 §4.4 规则 7） |
| `assert_locked_before` | `run_at < locked_at` → `HoldoutRegistryError`（F3）；`>=` 通过；记录不存在亦抛错 |
| import | 标准库（`json/hashlib/itertools/math/datetime/typing`）+ `numpy` + `duckdb`；均为顶层 import（本模块不被 `backtest/__init__.py` 导入，默认路径不会触发加载） | 

**回退点**：删除文件即完全回退（无任何既有模块 import 它）。

### 2.2 `backtest/overfitting.py`（E2）

```python
def sharpe_ratio(returns: Sequence[float], *,
                 periods_per_year: int = 12) -> Dict[str, Any]: ...
def deflated_sharpe_ratio(returns: Sequence[float], n_trials: int, *,
                          sr_variance: Optional[float] = None,
                          trial_sharpes: Optional[Sequence[float]] = None,
                          periods_per_year: int = 12) -> Dict[str, Any]: ...
def trim_to_divisible(n_samples: int, n_blocks: int,
                      keep: str = "recent") -> slice: ...
def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray, n_blocks: int, *,
    metric: str = "sharpe", return_logits: bool = False) -> Dict[str, Any]: ...
```

**返回键（DSR）**：`dsr`、`sr_per_period`、`sr_annualized`、`sr0`、`T`、`n_trials`、`skew`、`kurtosis`、`sr_variance`、`variance_source`、`reason`。

**返回键（PBO）**：`pbo`、`n_splits`、`n_blocks`、`n_strategies`、`n_periods`、`metric`、`tie_policy`、可选 `logits`。

| 项 | 规则 |
|----|------|
| DSR 口径 | 逐期 SR = `mean/std(ddof=1)`；`γ3 = scipy.stats.skew(bias=False)`；`γ4 = kurtosis(fisher=False, bias=False)`；`γ=0.5772156649`；公式见设计 §5.1（**分母不可省**，F0） |
| DSR 校验 | `T>=3`、`n_trials>=2`、全有限、`std>0`；`sr_variance`/`trial_sharpes` 二选一（都传 → `ValueError`；长度必须 == `n_trials`）；`sr_variance<=0` → `ValueError` |
| DSR 退化 | `denom<=0` 或非有限 → `dsr=nan, reason="denominator_non_positive"`（不抛）；`reason` 另有 `"ok"` / `"zero_variance"` |
| PBO 切分 | `S` 偶数且 `>=2`；`T % S == 0` 否则 `ValueError` 并提示 `trim_to_divisible`；连续块 |
| PBO 选优 | IS 按 `metric` 取最大，并列取**最小列索引**；OOS 相对秩 `rank = 1 + #{<} + 0.5·(#{==}−1)`，`ω=rank/(N+1)`，`λ=log(ω/(1−ω))` |
| PBO 校验 | `N>=2`、矩阵全有限、每块每列 `std>0`（否则 `ValueError`）；`metric ∈ {"sharpe","mean"}` |
| `trim_to_divisible` | `keep="recent"` → `slice(T−T%S, T)`；`keep="earliest"` → `slice(0, T−T%S)`；`n_blocks` 非法 → `ValueError` |
| import | `numpy` / `scipy.stats` / `math`；**不 import** `effect_size` / `cross_validation` / `governance` |

**回退点**：删除文件即回退。

### 2.3 `backtest/effect_size.py`（E3）

```python
def newey_west_se(values: Sequence[float],
                  max_lag: Optional[int] = None) -> Dict[str, Any]: ...
def mean_ci(values: Sequence[float], *, alpha: float = 0.05,
            max_lag: Optional[int] = None) -> Dict[str, Any]: ...
def stationary_bootstrap_indices(n: int, n_bootstrap: int = 1000,
                                 block_size: Optional[int] = None,
                                 seed: int = 0) -> np.ndarray: ...
def sharpe_ci(returns: Sequence[float], *, alpha: float = 0.05,
              n_bootstrap: int = 1000, block_size: Optional[int] = None,
              seed: int = 0,
              periods_per_year: int = 12) -> Dict[str, Any]: ...
def effect_summary(metric: str, values: Sequence[float], *,
                   alpha: float = 0.05, periods_per_year: int = 12,
                   n_bootstrap: int = 1000, block_size: Optional[int] = None,
                   seed: int = 0,
                   max_lag: Optional[int] = None) -> Dict[str, Any]: ...
```

| 项 | 规则 |
|----|------|
| NW 默认 lag | `max(1, floor(4·(T/100)^(2/9)))`（与 `PremiumEstimator` 一致） |
| NW 核 | Bartlett：`Ω = γ0 + 2Σ_{j=1..L}(1−j/(L+1))γ_j`；`SE = sqrt(Ω/T)` |
| `mean_ci` | 返回 `mean/se/ci_low/ci_high/lag/method="newey_west"/n_periods`；CI 用 **t 分位**（`df=T−1`），不用 1.96 |
| bootstrap | Politis-Romano 环形 stationary bootstrap；期望块长 `ceil(sqrt(T))`；返回 `(B,T)` int64 |
| `sharpe_ci` | 每次重抽样计算年化 SR，取 `alpha/2` / `1−alpha/2` 分位；`se=std(bootstrap, ddof=1)`；返回含 `sharpe/sharpe_per_period/ci_low/ci_high/se/n_bootstrap/block_size/seed/method` |
| 私有 Sharpe | `_sharpe_per_period(returns)`：`mean/std(ddof=1)`；与 `overfitting.sharpe_ratio` 同公式（C1），由 T32b 断言一致 |
| `effect_summary` | `lambda_mean`/`ic_mean` → `mean_ci`；`sharpe` → `sharpe_ci`；其它 → `ValueError` |
| 校验 | `T>=3`、全有限、`alpha ∈ (0,1)`、`n_bootstrap>=100`、`block_size>=1`；零方差 → `ValueError` |
| import | `numpy` / `scipy.stats` / `math`；**不 import** `overfitting` |

**回退点**：删除文件即回退。

### 2.4 `backtest/specification_logger/`（E4）

```python
# spec_log.py
def log_run(self, config, result, run_type="exploratory",
            factor_name=None, *,
            spec_id=None, values=None, value_type=None,
            parent_run_id=None, spec=None) -> str: ...
def get_specification_matrix(self, factor_name=None, value_type="returns",
                             strict=True) -> Dict[str, Any]: ...

# spec_curve.py（模块级）
def joint_inference(values: np.ndarray, *, effect: str = "mean",
                    direction: str = "two-sided", n_bootstrap: int = 1000,
                    block_size: Optional[int] = None,
                    resampling: str = "stationary", alpha: float = 0.05,
                    seed: int = 0) -> Dict[str, Any]: ...

# pre_registration.py
def commit(self, spec, researcher="anonymous", description="") -> str: ...
def verify_compliance(self, actual_config, committed_hash, *,
                      strict_extra=False, run_at=None,
                      constraints=None) -> Dict[str, Any]: ...

# __init__.py
__all__ = [..., "joint_inference"]
```

| 项 | 规则 |
|----|------|
| `log_run` 旧调用 | `record` 字段集合与旧版**完全一致**（`timestamp/run_type/factor_name/config/result/commit_hash`）；不写 `schema_version` |
| `log_run` 新调用 | 任一 v2 参数非 None → 写 `schema_version="2"` + `spec_id/values/value_type/content_hash/parent_run_id/spec`；`values` 转 float 并拒绝 NaN/inf；`value_type ∈ {"returns","ic"}` 必填 |
| `content_hash` | `SHA256(canonical_json({run_type,factor_name,config,result,spec_id,values,value_type,parent_run_id,spec}))`；**排除** `timestamp/commit_hash/content_hash` |
| 返回 | 仍为 8 位 `commit_hash`（旧契约，测试 `test_log_run_returns_hash` 保持） |
| `get_specification_matrix` | 只取 `schema_version=="2"` 且 `value_type` 匹配的记录；返回 `spec_ids/values(T×M)/records/n_periods/n_specs/value_type/truncated`；`strict=True` 长度不一致/缺 values → `ValueError`（带行号与 spec_id）；`strict=False` 取最短并 `truncated=True`；无匹配 → `np.empty((0,0))` |
| `joint_inference` 算法 | 设计 §7.4：零假设强加 `centered=values−mean(values)`；同一 `idx` 用于所有规格；零分布标准化 `z`；三统计量（median / share_significant / aggregated_z）；`p=(1+#{≥})/(B+1)` |
| `joint_inference` 返回 | `statistics`（3 项，各含 `name/estimate/null_lower/null_upper/p_value/n_specs`）+ `n_bootstrap/block_size/resampling/effect/direction/alpha/seed/n_periods/n_specs/method="null_imposed_bootstrap"` |
| `joint_inference` 校验 | 2D、`T>=3`、`M>=1`、全有限、零方差列 → `ValueError`；**bootstrap 样本内**出现零方差列 → `ValueError`（提示换 seed，设计 §7.4）；「所有列同量纲（同为收益或同为 IC）」为文档级约束写入 docstring；枚举合法；`n_bootstrap>=100` |
| `PreRegistration.commit` | 保留 `timestamp` + 8 位 `commit_hash`；新增 `content_hash`（SHA256，**timestamp 不参与**）与 `hash_algo="sha256"` |
| `verify_compliance` | 先 `content_hash` 精确匹配 → 回退 `commit_hash`；新增 `strict_extra/run_at/constraints`；返回旧 4 键不变 + `matched_by` + `committed_at` |
| import | `spec_curve.joint_inference` 只依赖 `numpy/scipy`；**不 import** `effect_size`（stationary/iid 索引生成内联，见下方定案 (a)） |

> **E4 内部实现选择（步骤 6 定案：方案 (a)）**：
> `spec_curve.joint_inference` 内部直接实现 stationary/iid 索引生成（约 10 行，`numpy.random.default_rng`）；禁止 `from ..effect_size import ...`（D10）。

**回退点**：四处均为可选参数/新增 API；不传新参数时记录与旧版逐字节一致，可单独回滚任一文件。

### 2.5 `backtest/multiple_testing_ledger.py`（E5）

```python
@dataclass(frozen=True)
class FamilySpec:
    ...
    stage: str = "factor"          # 新增；"factor" | "portfolio"；不进入 fingerprint

class MultipleTestingLedger:
    def __init__(self, ..., holdout_checker=None): ...   # 新增可选回调
```

| 项 | 规则 |
|----|------|
| `stage` 兼容 | `fingerprint()` **不包含** stage（设计 §9.1/D8）；`_family_payload` 用 `asdict` 自动带 stage；旧 payload 缺该键 → dataclass 默认 `"factor"` 生效（`_load_family` 无需改） |
| `register_family` 校验 | `stage ∈ {"factor","portfolio"}`，否则 `FamilyConflictError`；stage 不可变更（family_id 已存在且指纹相同 → 幂等；指纹不同 → 既有逻辑报错） |
| `record_trial` 校验 | `family.stage=="portfolio"` → `trial.stage ∈ {"S4","portfolio"}`；`family.stage=="factor"` → **拒绝** `"S4"` 与 `"portfolio"`（F2）；旧 family + `stage="S3"` 不报错 |
| `holdout_checker` | `register_family` 中若 `spec.holdout_id` 非空且回调非 None → `holdout_checker(spec.holdout_id, spec.batch_id)`；回调抛异常 → 注册失败（异常原样上抛）；默认 None 零变更 |
| import | 不 import `cross_validation`（依赖注入） |

**回退点**：`stage` 默认值 + `holdout_checker=None` → 旧行为逐位一致。

### 2.6 `backtest/governance.py`（E6）

```python
_FDR_METHODS = frozenset({"benjamini_hochberg", "benjamini_yekutieli"})
_FWER_METHODS = frozenset({"bonferroni", "holm", "romano_wolf",
                           "white_rc", "hansen_spa"})

@dataclass(frozen=True)
class G2Policy:
    alpha: float = 0.05
    dsr_threshold: float = 0.95
    pbo_threshold: float = 0.10
    require_dsr: bool = True
    require_pbo: bool = False
    require_oos: bool = True
    require_effect: bool = True

def evaluate_g2(record: GovernanceRecord,
                policy: Optional[G2Policy] = None) -> GateResultPayload: ...
```

| 项 | 规则 |
|----|------|
| 记录校验扩展 | `dsr`/`pbo` 非 None 时必须有限且在 `[0,1]`；`oos_metric` 非 None 时必须含 `metric(str)/value(有限 float)/n_periods(int>=1)/same_sign(bool)`；均在 `_validate_stage_requirements` 内追加（`governance.py` L457-L492 区间） |
| `evaluate_g2` 顺序 | 设计 §10.2 的 9 步；`stage ∈ {S3, FINAL, PORTFOLIO}` |
| 轨道 | `correction_method ∈ _FDR_METHODS` → 用 `q_value`；`∈ _FWER_METHODS` → 用 `adjusted_p`；两者同时非 None → `ambiguous_track`；未知 → `unknown_correction_method` |
| 效果量 | `effect_metric ∈ ("lambda_mean","ic_mean","sharpe")`（与 L516 白名单一致）；`ci` 必须 `low<=effect<=high` |
| 返回 | `GateResultPayload(passed=not reasons, reasons=..., action="allow"/"downgrade", evidence_refs=[record.record_id], evaluated_by="script")` |
| 副作用 | **无**；不写库、不回调、不阻断 |
| import | 不 import `multiple_testing_ledger`（常量本地定义 + T41b 防漂移）；台账已有 `FDR_METHODS`/`FWER_METHODS`（`multiple_testing_ledger.py` L70-L77，元素为 `CorrectionMethod`），按 D10 不引用，仅以 T41b 断言两处字符串集合一致 |

**回退点**：删除 `G2Policy`/`evaluate_g2` 与校验块；旧记录不传 `dsr/pbo/oos_metric` 时行为不变。

### 2.7 `scripts/verify_stat_evidence.py`（E7）

```python
def main(argv: Optional[List[str]] = None) -> int: ...
# CLI: --section {dsr,pbo,cpcv,curve,all} --n-sim N --seed S
#      --output PATH（默认 logs/stat_evidence_verify.json，logs/ 已 gitignore）
```

| 检查 | 内容 | 判据 |
|------|------|------|
| DSR 解析对照 | 手算 `T=58, SR=0.2714, N∈{2,5,10,20}` | 与 `deflated_sharpe_ratio` 相对误差 `<=1e-12` |
| DSR MC 校准 | 零假设下多组 `N` 的 DSR 分布 | 随 `N` 增大 DSR 中位数单调不增 |
| PBO 纯噪声 | 独立噪声矩阵 `S=8, N=10, T=56` | `pbo ∈ [0.3, 0.7]`（宽松） |
| PBO 真技能 | 1 条强正 SR + 9 条噪声 | `pbo` 低于纯噪声场景 |
| CPCV 泄漏探针 | purge 区填入极端值 | 训练索引不含 purge 区；测试并集覆盖正确 |
| spec curve 校准 | 零效应矩阵 `B=1000` | `p<0.05` 的比例不超过名义值 + 2 倍标准误 |
| 退出码 | 全部通过 0；任一失败 1 | — |

**回退点**：删除脚本；`stata_econ_crosscheck.py` 仅改 detail 文案，仍 SKIP。

---

## §3 文件级 diff 计划

| 文件 | 类型 | 具体改动 | 兼容性断言 |
|------|------|---------|-----------|
| `backtest/cross_validation.py` | 新增 | 2.1 全部符号 + 私有 `_segments` / `_excluded_mask` / `_canonical_json` | 无既有 import |
| `backtest/overfitting.py` | 新增 | 2.2 全部符号 | 无既有 import |
| `backtest/effect_size.py` | 新增 | 2.3 全部符号 + 私有 `_sharpe_per_period` / `_bootstrap_indices` | 无既有 import |
| `backtest/specification_logger/spec_log.py` | 修改 | (1) `log_run` 增 5 个 keyword-only 参数与 v2 分支（L40-L74 之后追加，旧分支不动）；(2) 新增 `get_specification_matrix`（放在 `get_specification_curve` 之后）；(3) 新增私有 `_content_hash` / `_canonical_json` | 旧调用记录字段集合不变；8 位 `commit_hash` 不变；5 键 curve 不变 |
| `backtest/specification_logger/spec_curve.py` | 修改 | 文件末尾新增模块级 `joint_inference`（索引生成内联，见 §2.4 定案 (a)；不改 `SpecificationCurve`） | `analyze()` 不变 |
| `backtest/specification_logger/pre_registration.py` | 修改 | `commit` 增 `content_hash`/`hash_algo`（L37-L46 扩展）；`verify_compliance` 增 3 个 keyword 参数与匹配回退（L53-L76）；`_find_record` 增 `by="commit_hash"/"content_hash"` | 旧 4 键返回不变；旧 hash 可查 |
| `backtest/specification_logger/__init__.py` | 修改 | import + `__all__` 增 `joint_inference`（L14-L23） | 既有 4 个导出不变 |
| `backtest/multiple_testing_ledger.py` | 修改 | (1) `FamilySpec` 增 `stage: str = "factor"`（L103 后）；fingerprint 不变（L107-L129）；(2) `__init__` 增 `holdout_checker=None`；(3) `register_family` 增 stage 校验与回调（L424-L451 之间）；(4) `record_trial` 增 stage 交叉校验（L472-L482 之间） | 旧 payload 无 stage → 默认 `factor`；旧 family 指纹不变 |
| `backtest/governance.py` | 修改 | (1) 校验块追加 `dsr/pbo` 标量区间（L457-L461「标量合法区间」块尾，与 `p_value/q_value/adjusted_p` 同风格）+ `oos_metric` 结构校验（L491-L492 `ci` 校验之后）；(2) 文件末尾新增 `_FDR_METHODS`/`_FWER_METHODS`/`G2Policy`/`evaluate_g2` | 字段缺省不触发新校验 |
| `benchmarks/stata_econ_crosscheck.py` | 修改 | L628 detail：`"P1 未实装（DESIGN §8.2）"` → `"N/A: 无 Stata 官方实现；见 scripts/verify_stat_evidence.py"` | 仍 SKIP，退出码 0 |
| `tests/test_backtest/test_cross_validation.py` | 新增 | T01-T14b | — |
| `tests/test_backtest/test_overfitting.py` | 新增 | T15-T26 | — |
| `tests/test_backtest/test_effect_size.py` | 新增 | T27-T33 + T32b | — |
| `tests/test_backtest/test_spec_curve_v2.py` | 新增 | T34-T40b | — |
| `tests/test_backtest/test_g2_gate.py` | 新增 | T41-T45b + T46 | — |
| `tests/test_backtest/test_specification_logger.py` | 扩展 | 追加兼容用例（旧记录读取、v2 新字段、`content_hash` 稳定） | 既有 19 项用例不改 |
| `tests/test_backtest/test_multiple_testing_ledger.py` | 扩展 | 追加 `_family(stage=...)` 用例、`holdout_checker` 用例 | 既有 `_family` 默认不传 stage 仍通过 |
| `scripts/verify_stat_evidence.py` | 新增 | 2.7 | — |
| `pyproject.toml` | 修改 | `version = "3.7.0"`（L7） | 缓存代际不变 |
| `factor_pipeline/__init__.py` / `config_v2.py` / `reporting.py` | 修改 | `__version__` / `PipelineV2ConfigUnified.version` / `PipelineExecutionReport.pipeline_version` 默认值 → `3.7.0`（3 处代码锚点，对应 test_01/02/03）；缓存 `CODE_VERSION` **不变** | 版本一致性测试通过 |
| `tests/test_fix3_version_unification.py` | 修改 | `EXPECTED_VERSION = "3.7.0"`（L34） | — |
| `tests/test_backtest/verify_fix3_manual.py` | 修改 | 本地 `EXPECTED_VERSION`（L21）→ `3.7.0`；`OLD_VERSIONS`（L22）增 `"3.6.0"` | 残留扫描退出码 0 |
| `docs/DECISIONS.md` | 修改 | ADR-055 ~ ADR-058（L58 起追加） | — |
| `docs/CHANGELOG.md` / `docs/PROJECT_STATUS.md` / `README.md` | 修改 | v3.7.0 条目与 P1 状态 | — |

**不修改**：`backtest/__init__.py`（D11）、`backtest/engine.py`、`pipelines_v2.py`（版本字面量在 `config_v2.py`，不经由本文件）、缓存代际常量。

---

## §4 测试执行矩阵（T01-T46b，共 55 项 = 52 计划 + 复审修正 3）

> 每项先红后绿。「首轮红」列是步骤 9 首次运行的预期失败形态（用于确认测试真正覆盖新代码）。

### 4.1 `test_cross_validation.py`（E1，16 项）

| # | 测试 | 首轮红 | 绿后断言 |
|---|------|--------|---------|
| T01 | `PurgedKFold` 基本 | `ModuleNotFoundError` | 5 折；train/test 无交集；并集为 `[0,T)` |
| T02 | purge | 同上 | `a−1` 不在 train；`a−2` 在 train（`h=1`） |
| T03 | embargo | 同上 | `b+1..b+embargo` 不在 train |
| T04 | 参数校验 | 同上 | `n_splits<2`、`purge<0`、`T` 太小 → `ValueError` |
| T05 | CPCV 路径数 | 同上 | `N=6,k=2` → `n_paths=15`；`split_id="cpcv_n6_k2_p1_e1_h1"` |
| T06 | CPCV 不连续测试块 | 同上 | 每段分别 purge/embargo；段间训练样本保留 |
| T07 | CPCV 确定性 | 同上 | 两次 `split` 索引逐位一致 |
| T08 | CPCV 校验 | 同上 | `k>=N`、`N<2`、`T<N` → `ValueError` |
| T09 | holdout lock | 同上 | 首次写入；`check` 返回 9 键（§2.1「`check` 返回」行）；`locked_at` 非空 |
| T10 | holdout 幂等 | 同上 | 同 batch 同窗口二次 `lock` 返回同 id；表行数 1 |
| T11 | holdout 跨 batch 拒绝 | 同上 | 同窗口不同 batch → `HoldoutReuseError` |
| T12 | holdout 重叠拒绝 | 同上 | 部分重叠窗口不同 batch → `HoldoutReuseError` |
| T12b | holdout 多 universe | 同上 | 同 batch 同 start/end 不同 universe → 允许；同 batch 不同 start/end → 拒绝 |
| T13 | holdout `dev_mask` | 同上 | 2025-01…2025-12、2024-12、2026-01 → False；2024-11 → True；58 个 True |
| T14 | holdout 未启用 | 同上 | `enable=False` → `HoldoutRegistryError`（lock/check/dev_mask 全抛） |
| T14b | `assert_locked_before` | 同上 | `run_at < locked_at` → `HoldoutRegistryError`；`>=` 通过 |

### 4.2 `test_overfitting.py`（E2，13 项）

| # | 测试 | 首轮红 | 绿后断言 |
|---|------|--------|---------|
| T15 | DSR 公式直算 | `ModuleNotFoundError` | 与手算/独立实现 `<=1e-12`（含分母） |
| T16 | DSR N 单调 | 同上 | `N` 增大 → `dsr` 不增 |
| T17 | DSR 逐期口径 | 同上 | `sr_per_period == mean/std(ddof=1)`；`sr_annualized == sr_per_period·√12` |
| T18 | DSR 退化 | 同上 | `n_trials=1`、`T<3`、零方差 → `ValueError` |
| T19 | DSR 分母非正 | 同上 | 构造 `denom<=0` → `dsr=nan, reason="denominator_non_positive"`（不抛） |
| T20 | DSR 方差来源 | 同上 | `sr_variance`/`trial_sharpes` 二选一；都传 → `ValueError`；`variance_source` 正确 |
| T21 | PBO 暴力对照 | 同上 | `S=4,N=3,T=8` 与独立暴力枚举 `<=1e-12` |
| T22 | PBO 纯噪声 | 同上 | 多策略独立噪声 → `pbo ∈ [0.3,0.7]`（固定 seed；失败则换 seed 并登记） |
| T23 | PBO 真技能 | 同上 | 强正 SR + 噪声 → `pbo` 低于 T22 场景 |
| T24 | PBO 整除 | 同上 | `T%S!=0` → `ValueError`；`trim_to_divisible` 两种 `keep` 正确 |
| T25 | PBO 并列秩 | 同上 | 构造并列 OOS → 平均秩；结果确定 |
| T26 | PBO 可复现 | 同上 | 同输入两次逐位一致（无 RNG） |
| T26b | 常数序列 FP 假阳（复审 H1） | — | `sharpe_ratio(np.full(58, 0.01))`（std≈1e-19>0 绕过零方差守卫）与 PBO 块内常数列 → `ValueError`（`np.ptp == 0` 守卫） |

### 4.3 `test_effect_size.py`（E3，9 项）

> 命名注记（步骤 6）：`test_multiple_testing_ledger.py` 既有测试内部编号 T21-T26（前一批次遗留，如 `test_t21_preregistration_required`），与本节 T15-T26 撞号；不同文件无冲突，但步骤 9 新测试用具描述性名称（如 `test_dsr_formula_reference`、`test_pbo_bruteforce`），避免检索混淆。

| # | 测试 | 首轮红 | 绿后断言 |
|---|------|--------|---------|
| T27 | NW iid 极限 | `ModuleNotFoundError` | iid 大样本 `se ≈ std/√T`（容差 5%） |
| T28 | NW vs statsmodels | 同上 | 固定序列与 `cov_hac` 对拍 `<=1e-10` |
| T29 | NW 自相关 | 同上 | AR(1)>0 → `se` 大于 iid 值 |
| T30 | `mean_ci` | 同上 | `ci_low <= mean <= ci_high`；`alpha` 非法 → `ValueError` |
| T31 | stationary bootstrap | 同上 | 同 seed 可复现；索引 ∈ `[0,T)`；块长生效（块长 1 == iid） |
| T32 | `sharpe_ci` | 同上 | 同 seed 可复现；`ci_low <= sharpe <= ci_high`（允许边界） |
| T32b | Sharpe 口径一致（C1） | 同上 | `effect_summary("sharpe", r)["effect_size"]` == `overfitting.sharpe_ratio(r)["sharpe"]`（`<=1e-12`） |
| T33 | `effect_summary` | 同上 | 三 metric 分派正确；非法 metric → `ValueError` |
| T33b | 常数序列 FP 假阳（复审 H1） | — | `newey_west_se(np.full(20, 0.01))` / `sharpe_ci(np.full(58, 0.02))` → `ValueError` |

### 4.4 `test_spec_curve_v2.py`（E4，9 项）

| # | 测试 | 首轮红 | 绿后断言 |
|---|------|--------|---------|
| T34 | schema v2 写入 | `ImportError: joint_inference` / `TypeError: log_run` | `values/value_type/spec_id/content_hash` 落盘；`commit_hash` 仍 8 位 |
| T35 | 旧记录兼容 | 同上 | 旧 JSONL 可读；`get_specification_curve` 恰好 5 键 |
| T36 | 矩阵提取 | 同上 | 同长度 → `values.shape == (T,M)`；缺 values + `strict=True` → `ValueError` |
| T37 | 矩阵截断 | 同上 | `strict=False` → 最短长度 + `truncated=True` |
| T38 | 联合推断零效应 | 同上 | 纯噪声矩阵三统计量 `p > 0.05`（宽松；失败换 seed 登记） |
| T39 | 联合推断强效应 | 同上 | 人为正效应 → median/Z 的 `p` 小；share 高 |
| T40 | 联合推断确定性 | 同上 | 同 seed 逐位一致；`iid`/`stationary` 均可运行 |
| T40b | 预注册 v2 | 同上 | 同 spec 不同 timestamp → `content_hash` 相同；`verify_compliance` 可回退 `commit_hash`；`matched_by` 正确 |
| T40c | 常数列 FP 假阳（复审 H1） | — | `joint_inference` 矩阵含 `np.full` 常数列 → `ValueError` |

### 4.5 `test_g2_gate.py`（E5/E6，8 项）

| # | 测试 | 首轮红 | 绿后断言 |
|---|------|--------|---------|
| T41 | G2 FDR 通过 | `ImportError: evaluate_g2` | BH `q_value<=0.05` + effect + DSR + OOS → `passed=True, action="allow"` |
| T41b | 方法名防漂移（C2） | 同上 | `_FDR_METHODS`/`_FWER_METHODS` 与 `CorrectionMethod` 枚举逐字一致 |
| T42 | G2 FWER 通过 | 同上 | Holm `adjusted_p<=0.05` → passed |
| T43 | G2 混轨拒绝 | 同上 | `q_value` 与 `adjusted_p` 同时非 None → `ambiguous_track` |
| T44 | G2 阈值失败 | 同上 | `dsr=0.9` → `dsr_below_threshold`；`pbo=0.2` + `require_pbo=True` → `pbo_above_threshold`；`action="downgrade"` |
| T45 | G2 OOS 缺失 | 同上 | 无 `oos_metric` → `missing_oos`；`same_sign=False` → `oos_not_same_sign` |
| T45b | 记录结构校验（C3） | 同上 | `dsr=1.2`/`nan`、`pbo=-0.1`、`oos_metric` 缺 `n_periods` → `ValueError` |
| T46 | ledger stage | `TypeError: FamilySpec(stage=...)` | portfolio family + `S3` trial → `FamilyConflictError`；factor family + `S4`/`portfolio` trial → `FamilyConflictError`；旧 family（`stage="S3"`）不报错 |

### 4.6 既有测试扩展（E4/E5）

| 文件 | 追加用例 | 断言 |
|------|---------|------|
| `test_specification_logger.py` | `test_log_run_v2_fields` / `test_content_hash_stable` / `test_legacy_record_read` | 新字段落盘；同 spec 不同 timestamp → `content_hash` 相同；旧记录 `get_specification_curve` 5 键 |
| `test_multiple_testing_ledger.py` | `test_family_stage_default` / `test_family_stage_portfolio` / `test_holdout_checker_called` / `test_holdout_checker_error` / `test_family_stage_idempotent` | 默认 `"factor"`；指纹不含 stage；回调被调用且异常上抛；**同指纹不同 stage 二次注册 → 返回既有 family_id、stage 以首次注册为准**（§9 疑点 3 定案，对齐 L448-L451 既有幂等分支） |

---

## §5 实施门禁与读数

### 5.1 E0 基线冻结（改动前执行并记录）

```powershell
python -m pytest tests -q
python -m pytest tests/test_backtest/test_golden_master.py -q
python -m pytest tests/test_fix3_version_unification.py -q
```

记录：总用例数、通过数、失败/跳过清单、golden master 场景数。基线失败项若与本批无关，登记为「既有失败」，不扩大修复范围。

**E0 基线读数（2026-11-18，改动前 3.6.0 工作区）**

| 命令 | 读数 |
|------|------|
| `python -m pytest tests -q` | **1866 passed / 15 skipped / 166 warnings**（759.52s；0 failed） |
| `python -m pytest tests/test_backtest/test_golden_master.py -q` | 6 passed（T16-T20 + T58） |
| `python -m pytest tests/test_fix3_version_unification.py -q` | 9 passed（`EXPECTED_VERSION=3.6.0`） |

既有失败：无。跳过项为外部数据/环境依赖（`RUN_DUCKDB_INTEGRATION` 等），与本批无关。

### 5.2 全量门禁（E8 前必须全绿）

| 门禁 | 命令 | 判据 |
|------|------|------|
| 新增单测 | `python -m pytest tests/test_backtest/test_cross_validation.py tests/test_backtest/test_overfitting.py tests/test_backtest/test_effect_size.py tests/test_backtest/test_spec_curve_v2.py tests/test_backtest/test_g2_gate.py -q` | 55 项全通过（52 计划 + 复审修正 3） |
| 既有回归 | `python -m pytest tests/test_backtest/test_specification_logger.py tests/test_backtest/test_multiple_testing_ledger.py tests/test_backtest/test_governance.py -q` | 无新增失败 |
| 默认零变更 | `python -m pytest tests/test_backtest/test_golden_master.py -q` | 同环境零差异 |
| 全量 | `python -m pytest tests -q` | 与基线相比无新增失败 |
| 版本一致性 | `python -m pytest tests/test_fix3_version_unification.py -q` | 全通过（`EXPECTED_VERSION=3.7.0`） |
| Python 3.9 语法 | `python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8'), feature_version=(3,9)) for p in list(pathlib.Path('backtest').rglob('*.py'))+list(pathlib.Path('scripts').rglob('*.py'))]"` | 退出码 0 |
| 无新依赖 | `git diff pyproject.toml` | 仅 `version` 一行变更 |
| 独立验证 | `python scripts/verify_stat_evidence.py --section all --n-sim 200` | 退出码 0 |
| Stata 对拍 | `python benchmarks/stata_econ_crosscheck.py --case all --skip-stata` | 退出码 0；`dsr`/`pbo` detail 为 N/A |

### 5.3 阶段读数回填（步骤 9 填写）

| 阶段 | 红（首次失败摘要） | 绿（通过项/总数） | 门禁结果 | 备注 |
|------|------------------|------------------|---------|------|
| E1 | `ModuleNotFoundError: No module named 'factor_pipeline.backtest.cross_validation'`（16 例收集失败） | 16/16 passed | PASS | purge 口径首版按 `a−label_horizon−purge` 剔除 `a−2`，T02 红；改为 `back=max(purge,label_horizon)` 后绿 |
| E2 | `ModuleNotFoundError: ...overfitting`（12 例收集失败） | 12/12 passed | PASS | T19（分母非正）经 Pearson 不等式证明合法序列不可达，改用 `_dsr_from_stats` 内部构造；`trim_to_divisible` 修正 EXECUTION §2.2 `keep="recent"` 笔误为 `slice(T%S, T)` |
| E3 | `ModuleNotFoundError: ...effect_size`（8 例收集失败） | 8/8 passed | PASS | T31 首版断言 block_size=1 延续率为 0，实测 1/60（iid 巧合），改为 `approx(1/60, abs=0.01)` |
| E4 | `ImportError: joint_inference` + `TypeError: log_run() got an unexpected keyword argument 'spec_id'`（8 例） | 8/8 passed（+ 旧文件 3 例） | PASS | T37 夹具列表拼接笔误（`list(...) + 100.0`）修正为逐元素加 |
| E5 | `TypeError: FamilySpec.__init__() got an unexpected keyword argument 'stage'`（T46 + 5 例） | 8/8 passed（test_g2_gate）+ 5/5 passed（ledger） | PASS | `test_family_stage_default` 首版比对原始对象指纹失败（`register_family` 补全 `lead_variant_id`），改用 `replace(..., lead_variant_id="v1")` 后比对 |
| E6 | `ImportError: cannot import name 'G2Policy' from 'factor_pipeline.backtest.governance'`（7 例） | 7/7 passed（T41-T45b） | PASS | 与 E5 的 T46 合并在 `test_g2_gate.py`，该文件总计 8 passed |
| E7 | 脚本不存在（`ModuleNotFoundError` / 退出码非 0） | 四段 `dsr/pbo/curve/leakage` 全 PASS，退出码 0 | PASS | 输出 `out/stat_evidence_verification.json`；`benchmarks/stata_econ_crosscheck.py --case all --skip-stata` 退出码 0，dsr/pbo detail = N/A |
| E8 | 版本一致性 2 failed（`3.6.0 != 3.7.0`）；`test_fix3_version_unification.py` 红 | 9/9 passed（版本统一）+ 6/6 passed（golden master） | PASS | 6 处版本锚点统一 3.7.0；缓存代际仍 `v2.3.0-cache`；Python 3.9 AST 校验退出码 0；`git diff pyproject.toml` 仅 version 一行 |

**E8 全量回归读数（2026-11-18，v3.7.0 工作区）**

| 命令 | 读数 |
|------|------|
| `python -m pytest tests -q` | **1929 passed / 15 skipped / 167 warnings**（910.92s，exit 0；0 failed） |
| 对照 E0 基线 | 1866 → 1929（**+63** = 新增 55（52 计划 + 异构复审修正 3）+ 既有扩展 8），跳过数不变（15） |

跳过项与 E0 完全一致（外部数据/环境依赖），无新增跳过。

> 异构复审（2026-11-18）：P2 真实缺陷 H1（常数序列浮点假阳绕过零方差守卫）修复 + 3 例回归测试
> （T26b/T33b/T40c）后复跑全量 **1929 passed**；探针 84 项全 PASS；详见
> [审计报告](audit/2026-11-18-v3.7.0-stat-evidence-chain-audit.md)。

---

## §6 性能与 MC 实测回填

| 操作 | 规模 | 设计预算 | 实测（步骤 9 填） | 结论 |
|------|------|---------|------------------|------|
| DSR | `T=58` | `<5ms` | **0.886 ms** | PASS |
| PBO | `S=8,N=10,T=56` | `<0.5s` | **6.3 ms** | PASS |
| PBO 敏感 | `S=14,N=10,T=56` | `<2s` | **351 ms** | PASS |
| CPCV 折界 | `N=6,k=2,T=54` | `<10ms` | **0.384 ms** | PASS |
| `joint_inference` | `B=1000,T=58,M=8` | `<1s` | **10.1 ms** | PASS |
| `joint_inference` 因子层 | `B=1000,T=40,M=24` | `<2s` | **10.5 ms** | PASS |
| holdout lock | 单次（首次 / 幂等） | `<50ms` | **35.5 ms / 0.6 ms**（`check` 0.56 ms） | PASS |

> 实测口径：`time.perf_counter`，单次/均值（DSR 200 次均值，PBO 3 次均值，CPCV 20 次均值，
> `joint_inference` 3 次均值），`numpy.random.RandomState(20261118)`；环境同全量回归。

**超预算处置**：记录实测值并在步骤 10 审计说明；不为此改变统计口径（不降 `B`、不换 bootstrap 类型）。若 `B=1000` 显著超预算，优先在调用层降 `B` 并披露（p 分辨率降为 `1/(B+1)`）。

---

## §7 兼容性核对清单

| # | 兼容对象 | 核对方法 | 通过判据 |
|---|---------|---------|---------|
| 1 | 旧 spec JSONL（无 `schema_version`/`values`） | 用 3.6.0 生成的 `logs/specifications.jsonl` 读取 | `get_specification_curve` 5 键；无异常 |
| 2 | `log_run` 旧调用 | `test_log_run_returns_hash` / `test_log_run_append_only` / `test_log_run_json_serializable` | 原样通过；记录字段集合不变 |
| 3 | 旧 ledger family（无 `stage`） | 读取 v3.6.0 `factor_db.duckdb` 或既有测试 fixture | 默认 `"factor"`；`fingerprint()` 与旧值一致 |
| 4 | `holdout_checker=None` | 既有 ledger 测试 | 逐位一致 |
| 5 | 旧 `PreRegistration` 记录（仅 `commit_hash`） | `verify_compliance(actual, old_hash)` | 命中 `matched_by="commit_hash"` |
| 6 | `GovernanceRecord` 旧记录（不传 `dsr/pbo/oos_metric`） | 既有 `test_governance.py` | 通过 |
| 7 | `backtest/__init__.py` | `git diff` | 无改动 |
| 8 | 缓存代际 | `git diff` + 版本测试 | `v2.3.0-cache` 未变 |
| 9 | Python 3.9 | §5.2 AST 扫描 | 退出码 0 |
| 10 | 默认路径 | golden master | 同环境零差异 |

---

## §8 风险、回退与运维

| # | 风险 | 处置 | 回退 |
|---|------|------|------|
| X1 | `holdout_db.duckdb` 路径漂移（不同 cwd 产生多份登记） | **U13 定案**：默认 `holdout_db.duckdb`（cwd，已 gitignore）；研究脚本必须显式传 `db_path` 并在报告写绝对路径；`list_locks()` 用于审计 | 文件可整体归档/复制；丢失则锁定时间不可重建（不可重放历史） |
| X2 | 并发写 holdout registry | DuckDB 单写；研究脚本串行 `lock`；不做跨进程锁（设计 R10） | 串行重跑 |
| X3 | 预期 G2 整体 downgrade（设计 §5.4） | 报告按「降级为 monitor」披露；**不**调阈值/`N`/方差口径 | 不适用（这是预期结果） |
| X4 | MC 断言随机失败（T22/T38） | 固定 seed；失败时换 seed 并在 §5.3 登记新 seed 与读数 | 保留记录，不改判据区间 |
| X5 | spec 矩阵长度不一致（历史规格缺期） | `strict=True` 报错并列出 spec_id；确需合并时用 `strict=False` + 报告披露 `truncated` | 单独重跑缺失规格 |
| X6 | `joint_inference` 与原文 iid 抽行差异 | 默认 stationary（保留自相关），报告写方法；`resampling="iid"` 复刻原文 | 参数切换即可 |
| X7 | `FamilySpec.stage` 误用（改标签续用） | 文档明示 stage 不可变更；portfolio 必须新 `family_id`（设计 R8） | 新建 family 重新预注册 |
| X8 | G2 误用（单因子 `require_pbo=True`） | 默认 False；示例注明仅组合层开启（设计 R9） | 显式传参 |
| X9 | 版本号锚点遗漏 | 4 处代码/配置锚点（`__init__.py` / `config_v2.py` / `reporting.py` / `pyproject.toml`）+ `test_fix3_version_unification.py` L34 + `verify_fix3_manual.py` L21/L22，逐项更新 | 测试即失败，立即暴露 |

---

## §9 流程状态

| 步骤 | 状态 | 工件/证据 |
|------|------|----------|
| 1-2 调研 | 完成 | `docs/research/RESEARCH_STAT_EVIDENCE_CHAIN.md` v1.2 |
| 3 设计 | 完成 | `docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md` v1.2 |
| 4 独立复审（设计） | 完成 PASS_WITH_FIXES | 设计 §21（F0-F6 全部修正） |
| **5 实施文档** | **完成（本文件）** | 12 个工件计划 + 55 项测试 + E1-E8 顺序 |
| 6 实施文档 review | 完成（PASS_WITH_FIXES） | 本文件 v1.1 §10（F1-F7 全部修正；§9 四个疑点全部定案） |
| 7 验收 checklist | 完成 | `docs/audit/CHECKLIST_V3.7.0_STAT_EVIDENCE_CHAIN.md` v1.0（55 项测试 + 11 兼容 + 8 门禁 + 7 性能 + 9 风险，状态待步骤 9 回填） |
| 8 一致性 review | 完成 PASS_WITH_FIXES → 修正后 PASS | [CONSISTENCY_REVIEW_V3.7.0_STAT_EVIDENCE_CHAIN.md](audit/CONSISTENCY_REVIEW_V3.7.0_STAT_EVIDENCE_CHAIN.md)（F1-F7 全部闭环） |
| 9 TDD 实现 | 完成 (2026-11-18) | 按 §1 顺序；§5.3 / §6 已回填（全量 1929 passed） |
| 10 审计 + 异构复审 | 完成 (2026-11-18) PASS_WITH_FIXES | [审计报告](audit/2026-11-18-v3.7.0-stat-evidence-chain-audit.md)（H1 修复 + 探针 84 项 PASS） |

**步骤 6 review 疑点定案（核对与处置详见 §10）**：

1. C1 `sharpe_ratio` 归属：**维持**——唯一公共实现放 `overfitting.sharpe_ratio`，`effect_size` 私有同公式实现 + T32b 跨模块断言；设计 §8.2 的代码示例视为示意，§11.1 的模块归属为准。
2. `joint_inference` 自带 bootstrap 索引：**允许且定为方案 (a)**——索引生成内联于 `spec_curve.py`，不违反 D10（模块间无 import）。
3. stage 幂等语义：指纹相同（stage 不入指纹）→ 二次注册返回既有 family_id，stage 以首次注册为准——已核验 ledger L448-L451 既有分支；§4.6 增 `test_family_stage_idempotent` 显式断言。
4. T32b/T41b/T45b 回填设计 §14：**是**，设计升 v1.2 时 append-only 追加三行（T32b/T41b/T45b）与 b 项总数 52；§21 后追加补口注记。

---

**实施文档结论**：六项能力全部落在 3 个新模块 + 4 个文件的兼容扩展内，零新增依赖、默认零变更；实施的关键不在算法，而在 §4 的 55 项断言与 §7 的 10 条兼容核对。E1-E3 可并行，E4-E6 串行依赖，E7-E8 收尾。

---

## §10 步骤 6 独立复审记录（v1.0 → v1.1）

> 复审方式：实施文档全文重读 + 全部代码锚点一手重放（本轮实证读取，非沿用记忆）+
> 设计前提（§4.4/§7.4/§8.2/§10.1-10.3/§11.1/§14/§16）逐条比对 + 版本锚点实测。
> 结论：**PASS_WITH_FIXES**（0 推翻；F1-F7 全部已修正落盘）。

### 10.1 发现与处置

| # | 级别 | 发现 | 证据 | 处置 |
|---|------|------|------|------|
| F1 | P1 | §2.1 `dev_mask` 改为非 Optional 且「不接受 None」，与设计 §4.4 冲突：设计 L256 签名为 `holdout_id: Optional[str]`，L269 规则 7「holdout_id 非 None 时找不到才抛错」，L279「未锁定批次 holdout_id=None → 全 True + full_retrospective 披露」（D14 配套路径）。执行文档的收紧会切断回顾性诚实披露流程 | 设计 L256/L269/L279 vs 执行 §2.1 原文 | 恢复 `Optional[str]`；None → 全 True；非 None 找不到 → `HoldoutRegistryError`（§2.1 已改） |
| F2 | P2 | 版本锚点错误 + 数目矛盾 + 一处遗漏：①§3 写 `pipelines_v2.py`，实测锚点在 `config_v2.py` 的 `PipelineV2ConfigUnified.version`（test_02 导入自 `config_v2`）；②§8 X9「5 处」与 §3「4 处」矛盾；③漏 `verify_fix3_manual.py` L21 本地 `EXPECTED_VERSION = "3.6.0"`（不同步则残留扫描自报） | `tests/test_fix3_version_unification.py` test_01/02/03 导入锚点；`verify_fix3_manual.py` L21/L22 | §3 改为 `config_v2.py`；X9 改为「4 处代码/配置锚点 + test L34 + verify L21/L22」；§3 增 verify L21 行 |
| F3 | P2 | T09「`check` 返回 6 键」键集未定义（设计与执行均未固定），测试不可写 | 设计 §4.4 无返回键清单 | 定案 9 键（表列 6 字段 + payload 展开 price/return/note），写入 §2.1「`check` 返回」行并同步 T09 |
| F4 | P3 | §3 governance 校验锚点偏差：dsr/pbo 标量校验的自然插入点是 L457-L461「标量合法区间」块尾（与 p/q/adjusted_p 同风格），原文「L491-L496 附近」不准确 | `governance.py` L457-L461/L491-L492 实读 | 锚点修正 |
| F5 | P3 | §2.4 `joint_inference` 校验漏设计 §7.4 两项：bootstrap 样本内零方差列 → ValueError（提示换 seed）；「所有列同量纲」文档级约束 | 设计 §7.4 校验清单 | 已补入 |
| F6 | P3 | 测试编号撞名：`test_multiple_testing_ledger.py` 既有测试内部编号 T21-T26（前批次遗留），与新 §4.2 T15-T26 撞号（不同文件无冲突，但易误检索） | 该测试文件 `test_t21_preregistration_required` 等 | §4.3 前加命名注记：步骤 9 用描述性名称 |
| F7 | P3 | §9 疑点 3 的 stage 幂等行为缺显式测试断言 | ledger L448-L451 幂等分支实读 | §4.6 增 `test_family_stage_idempotent` |

### 10.2 核对通过清单（全部一手实证）

| # | 核对项 | 证据 |
|---|--------|------|
| 1 | `spec_log.py` 锚点：`log_run` L40-L74、record 六字段、8 位 SHA1（timestamp 不入哈希）、curve 5 键 | 实读 |
| 2 | `pre_registration.py` 锚点：`commit` L30-L51（记录体 L37-L46）、`verify_compliance` L53-L76 返回 4 键、`_find_record` L78 | 实读 |
| 3 | `FamilySpec` 含 `batch_id`+`holdout_id`（holdout_checker 回调可实现）；fingerprint 不含 stage 可行；`_family_payload` 用 `asdict`；`_load_family` 以 `FamilySpec(**data)` 重建（旧 payload 缺 stage → 默认值生效） | 实读 L90-L104/L308-L311/L407 |
| 4 | `register_family` 幂等分支（指纹相同 → 返回既有 id）L448-L451；`FamilyConflictError` L47；`__init__` 可加 `holdout_checker` | 实读 |
| 5 | `CorrectionMethod` 7 个值逐字吻合（`BH="benjamini_hochberg"` 等）；`FDR_METHODS`/`FWER_METHODS` L70-L77 → T41b 可实现 | 实读 L60-L77 |
| 6 | `GateResultPayload.action` 含 `"allow"/"downgrade"`、`evaluated_by` 含 `"script"`；`GovernanceRecord` 含 `record_id/stage/q_value/adjusted_p/dsr/pbo/oos_metric/effect_metric/effect_size/ci/n_trials`；`ci: Tuple[float,float]` | 实读 L134-L143/L335-L401 |
| 7 | `Stage` 枚举含 S3/FINAL/PORTFOLIO；现有 S3 门禁块 L510 同口径 | 实读 L146-L159 |
| 8 | `effect_metric` 白名单 L516 逐字吻合；`_validate_stage_requirements` 区间实锚点 L451+ | 实读 |
| 9 | Stata detail 锚点 L628 逐字吻合；`pyproject.toml` L7；`test_fix3` L34；`.gitignore` logs/L42、*.duckdb/L56、private/L65 | 实读 |
| 10 | `specification_logger/__init__.py` 恰 4 导出（L14-L23）；`test_specification_logger.py` 恰 19 项；`test_golden_master.py`/`test_governance.py` 存在；`_family` 帮手 L40 | 实读/Glob |
| 11 | 设计前提成立：§8.2 L576 与 §11.1 L752 的 sharpe 归属不一致（C1）；§10.2 L734 防漂移（C2）；§10.3 结构校验（C3）；§14.5 T41-T46 与 §14.6 与执行文档一致 | 实读 |
| 12 | 测试计数：设计 46 基号 + T12b/T14b/T40b = 49；执行 +T32b/T41b/T45b = 52；§4.1-4.5 分节计数（16/12/8/8/8）与总数一致 | 逐节核对 |
| 13 | §7.4 返回键与执行 §2.4 逐字吻合（statistics 三项 + 9 个标量键 + method） | 实读 L486-L520 |
| 14 | 设计 §16 R8/R9/R10 与执行 X7/X8/X2 一一对应 | 实读 L961-L963 |

### 10.3 定案与遗留

- **§9 四疑点全部定案**（见 §9 定案清单）：C1 维持、E4 取方案 (a)、stage 幂等显式断言、设计 v1.2 回填三行。
- **设计同步义务**：设计文档升 v1.2 时，append-only 追加 (i) §14 三行 T32b/T41b/T45b + 总数 52；(ii) §21 后追加「步骤 6 补口注记」（C1 归属定案 + E4 方案 (a) + stage 幂等语义）。
- **遗留至步骤 9**：无新增阻塞项；F1-F7 均已落盘。T19/T22/T38 的 MC 类断言在红转绿时若遇随机失败，按 §8 X4 换 seed 并在 §5.3 登记。
