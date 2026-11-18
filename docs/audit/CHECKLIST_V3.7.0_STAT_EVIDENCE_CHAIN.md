# CHECKLIST v3.7.0 统计证据链 — 验收清单

> **版本**: v1.0 (2026-11-18) — 步骤 7 产出
> **对应实施**: [EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md](../EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md) v1.1（步骤 6 复审 PASS_WITH_FIXES，见其 §10）
> **对应设计**: `docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md` v1.2（§14.7 补口测试 + §22 注记）
> **对应调研**: [RESEARCH_STAT_EVIDENCE_CHAIN.md](../research/RESEARCH_STAT_EVIDENCE_CHAIN.md) v1.2
> **对应路线图**: [MULTIFACTOR_GOVERNANCE_ROADMAP.md](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) §5 P1 / §6 G2
> **档位**: T1（3 新模块 + 3 契约扩展 + 4 ADR → 全 10 步）
> **状态词**: `待验证` / `通过` / `失败` / `阻塞` / `N/A（附理由）`
> **时点**: 本文件在**实施前**编写；状态列全部为 `待验证`，步骤 9 逐项回填，步骤 10 审计复核
> **禁止**：无证据的 ✅；汇总只能来自逐行状态计数（RULE-2）；E5 级（推测）证据不得支撑「通过」

---

## §1 DoR / DoD 定义

| 术语 | 含义 |
|------|------|
| **DoR**（Definition of Ready） | 该项可开始验证的前置条件（上游工件就绪 / 依赖阶段完成 / 环境可用） |
| **DoD**（Definition of Done） | 该项判定通过的**可观察**条件（命令 + 读数 / 文件 + 字段 / 断言表达式） |

**状态升级规则**：

1. `待验证` → `通过`：必须附「命令 + 退出码 + 关键读数 + 日期」。
2. `待验证` → `失败`：必须附失败用例名与首行错误。
3. `待验证` → `阻塞`：必须附阻塞原因与解阻触发条件。
4. `N/A`：必须写理由与替代证据。
5. TDD 类项目（§3）必须同时登记**红读数**与**绿读数**；红读数缺失视为未验证（对齐 F5 纪律）。

**证据等级**（沿用本仓约定）：

| 等级 | 含义 |
|------|------|
| E1 | 实跑命令输出（pytest / 脚本 stdout / gate 事件流） |
| E2 | 落盘工件（JSON / JSONL / DuckDB 表 / `out/*.json`） |
| E3 | 代码行号锚点（`Lxxx@<commit>`）或 `git diff` |
| E4 | 文档间逐字比对（本 checklist 与 EXECUTION/DESIGN 的映射） |
| E5 | 推理与估计（**不可**单独支撑「通过」） |

---

## §2 E0-E8 任务验收

| E | 验收项 | DoR | DoD | 证据 | 状态 |
|---|--------|-----|-----|------|------|
| E0 | 基线冻结 | 3.6.0 工作区可运行；依赖已装 | 全量 `pytest tests -q` 有完整读数并登记（总数/通过/失败/跳过）；`test_golden_master.py` 全绿；`test_fix3_version_unification.py` 全绿（`EXPECTED_VERSION=3.6.0`）；既有失败单独列「与本批无关」 | E1（EXECUTION §5.1 回填：1866 passed / 15 skipped / 0 failed；golden 6 passed；版本统一 9 passed） | 通过 (2026-11-18) |
| E1 | `cross_validation.py` | 设计 §4 定稿 | T01-T14b 共 16 项全通过；两折类 `split_id` 与 §2.1 字面一致；holdout 表行数与幂等读数一致 | E1 + E2（`test_cross_validation.py` 16 passed） | 通过 (2026-11-18) |
| E2 | `overfitting.py` | 设计 §5/§6 定稿 | T15-T26b 共 13 项全通过（含复审 H1 修正 T26b）；DSR 与独立直算 `<=1e-12`；PBO 与暴力枚举 `<=1e-12` | E1（`test_overfitting.py` 13 passed） | 通过 (2026-11-18) |
| E3 | `effect_size.py` | 设计 §8 定稿 | T27-T33b + T32b 共 9 项全通过（含复审 H1 修正 T33b）；NW 与 statsmodels `cov_hac` 对拍 `<=1e-10` | E1（`test_effect_size.py` 9 passed，T28 对拍通过） | 通过 (2026-11-18) |
| E4 | 规格曲线 v2 | E3 已完成（仅口径参考，不 import） | T34-T40c 共 9 项全通过（含复审 H1 修正 T40c）；`test_specification_logger.py` 新增 3 例通过且**既有 19 项零变化**；`commit_hash` 仍 8 位、curve 仍 5 键 | E1 + E3（`test_spec_curve_v2.py` 9 passed；旧文件 22 passed = 既有 19 + 新增 3） | 通过 (2026-11-18) |
| E5 | 台账 stage / holdout 回调 | E1 已完成 | T46 通过；`test_multiple_testing_ledger.py` 新增 5 例通过；旧 fixture 无 `stage` 可读且 `fingerprint()` 值不变 | E1 + E3（`test_g2_gate.py` 8 passed 含 T46；ledger 文件 17 passed = 既有 12 + 新增 5） | 通过 (2026-11-18) |
| E6 | G2 门禁 | E2/E3/E5 已完成 | T41-T46 + T41b/T45b 共 8 项全通过；`test_governance.py` 既有用例零新增失败；`evaluate_g2` 不写库（无 DuckDB 写入调用） | E1 + E3（`test_governance.py` 18 passed；`evaluate_g2` 源码无 store 引用） | 通过 (2026-11-18) |
| E7 | 独立验证脚本 | E1-E6 已完成 | `python scripts/verify_stat_evidence.py --section all --n-sim 200` 退出 0 且 `out/` 落盘 JSON；`stata_econ_crosscheck.py --case all --skip-stata` 退出 0 且 `dsr`/`pbo` detail 为 N/A（原「P1 未实装」消失） | E1 + E2（四段全 PASS；`out/stat_evidence_verification.json` 落盘；Stata 退出 0） | 通过 (2026-11-18) |
| E8 | 文档闭环 | E1-E7 全绿 | 4 处代码/配置版本锚点 = 3.7.0（`__init__.py` / `config_v2.py` / reporting / `pyproject.toml` L7）+ `test_fix3_version_unification.py` L34 + `verify_fix3_manual.py` L21/L22（含 `OLD_VERSIONS` 追加 3.6.0）；ADR-055~058 落 `DECISIONS.md`；CHANGELOG / PROJECT_STATUS / README 同步；缓存代际仍 `v2.3.0-cache` | E1 + E3 + E4（全量 1929 passed / 15 skipped / 0 failed，+63 vs 基线（含复审修正 3 例）；版本统一 9 passed + golden 6 passed；`git diff pyproject.toml` 仅 version 一行；`CODE_VERSION=v2.3.0-cache`） | 通过 (2026-11-18) |

**阶段纪律**：E4/E5/E6 均要求「先红后绿 + §5.3 读数回填」，不得跳阶段合并提交。

---

## §3 测试用例验收（55 项 = 52 计划 + 异构复审修正 3）

> 「红形态」= 步骤 9 首次运行预期失败形态（确认测试真正压到新代码）；「DoD」= 绿后断言。
> 任一用例的红读数缺失 → 该行保持 `待验证`（不得直接标绿）。

### 3.1 `test_cross_validation.py`（E1，16 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T01 | PurgedKFold 基本 | `ModuleNotFoundError` | 5 折；train/test 无交集；并集 `[0,T)` | 通过 |
| T02 | purge 保守口径 | 同上 | `a−1` 不在 train、`a−2` 在 train（`h=1`） | 通过 |
| T03 | embargo | 同上 | `b+1..b+embargo` 不在 train | 通过 |
| T04 | 参数校验 | 同上 | `n_splits<2` / `purge<0` / `T` 过小 → `ValueError` | 通过 |
| T05 | CPCV 路径数 | 同上 | `N=6,k=2` → `n_paths=15`；`split_id="cpcv_n6_k2_p1_e1_h1"` | 通过 |
| T06 | CPCV 不连续测试块 | 同上 | 每个连续段分别 purge/embargo；段间训练样本保留 | 通过 |
| T07 | CPCV 确定性 | 同上 | 两次 `split` 索引逐位一致 | 通过 |
| T08 | CPCV 校验 | 同上 | `k>=N` / `N<2` / `T<N` → `ValueError` | 通过 |
| T09 | holdout lock | 同上 | 首次写入成功；`check` 返回**9 键**（§2.1 定案集）；`locked_at` 非空 | 通过 |
| T10 | holdout 幂等 | 同上 | 同 batch 同窗口二次 `lock` 返回同 id；表行数 1 | 通过 |
| T11 | 跨 batch 拒绝 | 同上 | 同窗口不同 batch → `HoldoutReuseError` | 通过 |
| T12 | 重叠拒绝 | 同上 | 部分重叠窗口不同 batch → `HoldoutReuseError` | 通过 |
| T12b | 多 universe | 同上 | 同 batch 同 start/end 不同 universe → 允许；同 batch 不同 start/end → 拒绝 | 通过 |
| T13 | `dev_mask` | 同上 | 2025-01…2025-12、2024-12、2026-01 → False；2024-11 → True；True 计数 **58** | 通过 |
| T14 | 未启用 | 同上 | `enable=False` → `lock`/`check`/`dev_mask` 全抛 `HoldoutRegistryError` | 通过 |
| T14b | `assert_locked_before` | 同上 | `run_at < locked_at` → `HoldoutRegistryError`；`>=` 通过 | 通过 |

### 3.2 `test_overfitting.py`（E2，13 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T15 | DSR 公式直算 | `ModuleNotFoundError` | 与手算/独立实现 `<=1e-12`（**含分母**，非仅 PSR） | 通过 |
| T16 | DSR N 单调 | 同上 | `N` 增大 → `dsr` 不增 | 通过 |
| T17 | 逐期口径 | 同上 | `sr_per_period == mean/std(ddof=1)`；`sr_annualized == sr_per_period·√12` | 通过 |
| T18 | 退化输入 | 同上 | `n_trials=1` / `T<3` / 零方差 → `ValueError` | 通过 |
| T19 | 分母非正 | 同上 | 构造 `denom<=0` → `dsr=nan` 且 `reason="denominator_non_positive"`（不抛） | 通过 |
| T20 | 方差来源 | 同上 | `sr_variance` / `trial_sharpes` 二选一；同时传 → `ValueError`；`variance_source` 正确 | 通过 |
| T21 | PBO 暴力对照 | 同上 | `S=4,N=3,T=8` 与独立暴力枚举 `<=1e-12` | 通过 |
| T22 | PBO 纯噪声 | 同上 | 独立噪声矩阵 → `pbo ∈ [0.3,0.7]`（固定 seed；换 seed 须登记） | 通过 |
| T23 | PBO 真技能 | 同上 | 强正 SR 场景 `pbo` 低于 T22 | 通过 |
| T24 | 整除与裁剪 | 同上 | `T%S!=0` → `ValueError`；`trim_to_divisible` 的 `recent`/`earliest` 切点正确 | 通过 |
| T25 | 并列秩 | 同上 | 并列 OOS → 平均秩；结果确定 | 通过 |
| T26 | 可复现 | 同上 | 同输入两次逐位一致（无 RNG） | 通过 |
| T26b | 常数序列 FP 假阳（复审 H1） | 修复前 `np.full(58, 0.01)` 不抛（std≈1e-19>0 绕过守卫，Sharpe≈5e17） | `sharpe_ratio` 常数序列 / PBO 块内常数列 → `ValueError`（`np.ptp == 0` 守卫） | 通过 (2026-11-18) |

### 3.3 `test_effect_size.py`（E3，9 项）

> 命名注记：同仓 `test_multiple_testing_ledger.py` 内部编号 T21-T26 与本表撞号（不同文件无冲突）；步骤 9 一律使用描述性测试名。

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T27 | NW iid 极限 | `ModuleNotFoundError` | iid 大样本 `se ≈ std/√T`（容差 5%） | 通过 |
| T28 | NW vs statsmodels | 同上 | 固定序列与 `cov_hac` 对拍 `<=1e-10` | 通过 |
| T29 | NW 自相关 | 同上 | AR(1)>0 → `se` 大于 iid 值 | 通过 |
| T30 | `mean_ci` | 同上 | `ci_low <= mean <= ci_high`；`alpha` 非法 → `ValueError` | 通过 |
| T31 | stationary bootstrap | 同上 | 同 seed 可复现；索引 ∈ `[0,T)`；块长 1 退化为 iid | 通过 |
| T32 | `sharpe_ci` | 同上 | 同 seed 可复现；`ci_low <= sharpe <= ci_high`（允许边界） | 通过 |
| T32b | Sharpe 口径一致（C1） | 同上 | `effect_summary("sharpe", r)["effect_size"]` == `overfitting.sharpe_ratio(r)["sharpe"]`（`<=1e-12`）；两模块无互相 import | 通过 |
| T33 | `effect_summary` | 同上 | 三 metric 分派正确；非法 metric → `ValueError` | 通过 |
| T33b | 常数序列 FP 假阳（复审 H1） | 修复前 `np.full` 常数序列不抛（std≈1e-19>0） | `newey_west_se(np.full(20, 0.01))` / `sharpe_ci(np.full(58, 0.02))` → `ValueError` | 通过 (2026-11-18) |

### 3.4 `test_spec_curve_v2.py`（E4，9 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T34 | schema v2 写入 | `ImportError: joint_inference` / `TypeError: log_run` | `values`/`value_type`/`spec_id`/`content_hash` 落盘；`commit_hash` 仍 8 位 | 通过 |
| T35 | 旧记录兼容 | 同上 | 旧 JSONL 可读；`get_specification_curve` 恰好 5 键 | 通过 |
| T36 | 矩阵提取 | 同上 | 同长度 → `values.shape == (T,M)`；缺 `values` + `strict=True` → `ValueError` | 通过 |
| T37 | 矩阵截断 | 同上 | `strict=False` → 最短长度 + `truncated=True` | 通过 |
| T38 | 联合推断零效应 | 同上 | 纯噪声矩阵三统计量 `p > 0.05`（宽松；失败换 seed 登记） | 通过 |
| T39 | 联合推断强效应 | 同上 | 人为正效应 → median / Stouffer Z 的 `p` 小；share significant 高 | 通过 |
| T40 | 联合推断确定性 | 同上 | 同 seed 逐位一致；`iid` / `stationary` 两模式均可运行 | 通过 |
| T40b | 预注册 v2 | 同上 | 同 spec 不同 timestamp → `content_hash` 相同；`verify_compliance` 可回退 `commit_hash`；`matched_by` 正确 | 通过 |
| T40c | 常数列 FP 假阳（复审 H1） | 修复前含 `np.full` 常数列的矩阵不抛（std≈1e-19>0） | `joint_inference` 含 `np.full` 常数列 → `ValueError` | 通过 (2026-11-18) |

### 3.5 `test_g2_gate.py`（E5/E6，8 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T41 | FDR 轨通过 | `ImportError: evaluate_g2` | BH `q_value<=0.05` + effect + DSR + OOS → `passed=True`、`action="allow"` | 通过 |
| T41b | 方法名防漂移（C2） | 同上 | `governance._FDR_METHODS` / `_FWER_METHODS` 与 `CorrectionMethod` 七值逐字一致 | 通过 |
| T42 | FWER 轨通过 | 同上 | Holm `adjusted_p<=0.05` → passed | 通过 |
| T43 | 混轨拒绝 | 同上 | `q_value` 与 `adjusted_p` 同时非 None → `ambiguous_track` | 通过 |
| T44 | 阈值失败 | 同上 | `dsr=0.9` → `dsr_below_threshold`；`pbo=0.2` + `require_pbo=True` → `pbo_above_threshold`；`action="downgrade"` | 通过 |
| T45 | OOS 缺失/反向 | 同上 | 无 `oos_metric` → `missing_oos`；`same_sign=False` → `oos_not_same_sign` | 通过 |
| T45b | 记录结构校验（C3） | 同上 | `dsr=1.2` / NaN、`pbo=-0.1`、`oos_metric` 缺 `metric`/`value`/`n_periods`/`same_sign` 任一或类型错 → `ValueError` | 通过 |
| T46 | ledger stage | `TypeError: FamilySpec(stage=...)` | portfolio family + `S3` trial → `FamilyConflictError`；factor family + `S4`/`portfolio` trial → `FamilyConflictError`；旧 family（无 stage）不报错 | 通过 |

### 3.6 既有测试扩展（不计入 55 项，E4/E5）

| 文件 | 追加用例 | DoD | 状态 |
|------|---------|-----|------|
| `test_specification_logger.py` | `test_log_run_v2_fields` / `test_content_hash_stable` / `test_legacy_record_read` | 新字段落盘；同 spec 不同 timestamp → 同 `content_hash`；旧记录 curve 仍 5 键；**既有 19 项零变化** | 通过 |
| `test_multiple_testing_ledger.py` | `test_family_stage_default` / `test_family_stage_portfolio` / `test_holdout_checker_called` / `test_holdout_checker_error` / `test_family_stage_idempotent` | 默认 `"factor"`；指纹不含 stage；回调被调用且异常上抛；同指纹不同 stage 二次注册 → 返回既有 `family_id`，stage 以首次为准 | 通过 |

---

## §4 兼容性与零变更验收（对应 EXECUTION §7）

> 第 1-10 项逐条对应 EXECUTION §7；第 11 项「无新增依赖」取自 EXECUTION §5.2 门禁表。

| # | 兼容对象 | 核对方法 | 通过判据 | 状态 |
|---|---------|---------|---------|------|
| 1 | 旧 spec JSONL（无 `schema_version`/`values`） | 用 3.6.0 生成的 JSONL 读取 | `get_specification_curve` 5 键；无异常 | 通过 |
| 2 | `log_run` 旧调用 | `test_log_run_returns_hash` / `test_log_run_append_only` / `test_log_run_json_serializable` | 原样通过；旧调用记录**字段集合不变**（非旧调用才追加新字段） | 通过 |
| 3 | 旧 ledger family（无 `stage`） | 既有 fixture 或 3.6.0 DuckDB | 默认 `"factor"`；`fingerprint()` 与旧值一致 | 通过 |
| 4 | `holdout_checker=None` | 既有 ledger 测试 | 逐位一致 | 通过 |
| 5 | 旧 `PreRegistration` 记录（仅 `commit_hash`） | `verify_compliance(actual, old_hash)` | 命中 `matched_by="commit_hash"` | 通过 |
| 6 | `GovernanceRecord` 旧记录（不传 `dsr/pbo/oos_metric`） | `test_governance.py` | 全部通过 | 通过 |
| 7 | 导入面 | `git diff backtest/__init__.py` | 空 diff | 通过 |
| 8 | 缓存代际 | `git diff` + 版本测试 | 仍 `v2.3.0-cache` | 通过 |
| 9 | Python 3.9 语法 | §5.2 AST 扫描命令 | 退出码 0（无 PEP 604 / 内置泛型下标） | 通过 |
| 10 | 默认路径零变更 | `test_golden_master.py` | 同环境 `rtol=1e-10` 零差异 | 通过 |
| 11 | 无新增依赖 | `git diff pyproject.toml` | 仅 `version` 一行 | 通过 |

---

## §5 门禁、性能与 MC 验收（对应 EXECUTION §5.2 / §6）

| # | 门禁 | 命令 | 通过判据 | 状态 |
|---|------|------|---------|------|
| G1 | 新增单测 | `pytest tests/test_backtest/test_cross_validation.py tests/test_backtest/test_overfitting.py tests/test_backtest/test_effect_size.py tests/test_backtest/test_spec_curve_v2.py tests/test_backtest/test_g2_gate.py -q` | 55 项全通过（52 计划 + 复审修正 3） | 通过 |
| G2 | 既有回归 | `pytest tests/test_backtest/test_specification_logger.py tests/test_backtest/test_multiple_testing_ledger.py tests/test_backtest/test_governance.py -q` | 无新增失败 | 通过 |
| G3 | 默认零变更 | `pytest tests/test_backtest/test_golden_master.py -q` | 零差异 | 通过 |
| G4 | 全量 | `pytest tests -q` | 相对 E0 基线无新增失败 | 通过 |
| G5 | 版本一致性 | `pytest tests/test_fix3_version_unification.py -q` | 全通过（`EXPECTED_VERSION=3.7.0`） | 通过 |
| G6 | Py3.9 语法 | EXECUTION §5.2 AST 扫描 | 退出码 0 | 通过 |
| G7 | 独立验证 | `python scripts/verify_stat_evidence.py --section all --n-sim 200` | 退出码 0；JSON 落盘 | 通过 |
| G8 | Stata 对拍 | `python benchmarks/stata_econ_crosscheck.py --case all --skip-stata` | 退出码 0；`dsr`/`pbo` detail 为 N/A | 通过 |

| 性能项 | 规模 | 预算 | 实测 | 状态 |
|--------|------|------|------|------|
| DSR | `T=58` | `<5ms` | 0.886 ms | 通过 |
| PBO | `S=8,N=10,T=56` | `<0.5s` | 6.3 ms | 通过 |
| PBO 敏感 | `S=14,N=10,T=56` | `<2s` | 351 ms | 通过 |
| CPCV 折界 | `N=6,k=2,T=54` | `<10ms` | 0.384 ms | 通过 |
| `joint_inference` 组合层 | `B=1000,T=58,M=8` | `<1s` | 10.1 ms | 通过 |
| `joint_inference` 因子层 | `B=1000,T=40,M=24` | `<2s` | 10.5 ms | 通过 |
| holdout lock | 单次 | `<50ms` | 35.5 ms（首次）/ 0.6 ms（幂等）/ 0.56 ms（check） | 通过 |

> 超预算只登记与披露，**不**降 `B`、不换 bootstrap 类型、不改统计口径（EXECUTION §6 超预算处置）。

---

## §6 风险处置验收（对应 EXECUTION §8 X1-X9）

| # | 风险 | 可观察验收点 | 状态 |
|---|------|-------------|------|
| X1 | `holdout_db.duckdb` 路径漂移 | 研究脚本显式传 `db_path`；报告写绝对路径；`list_locks()` 可审计 | N/A（本批未接入研究脚本；模块侧 `db_path` 为构造参数、`list_locks()` 已具备，接入时按 §8 X1 执行） |
| X2 | 并发写 registry | 脚本串行 `lock`；无跨进程锁（设计 R10） | N/A（本批无并发调用方；设计要求无跨进程锁已在 ADR-055 披露） |
| X3 | 预期整体 downgrade | 报告按「降级为 monitor」披露；阈值/N/方差口径未改（diff 可证） | 通过 |
| X4 | MC 随机失败 | T22/T38 固定 seed；换 seed 已在 §3 与 EXECUTION §5.3 登记 | 通过 |
| X5 | 规格矩阵长度不一致 | `strict=True` 报错并列出 `spec_id`；`strict=False` 披露 `truncated` | 通过 |
| X6 | 与原文 iid 差异 | 默认 stationary；报告写明方法；`resampling="iid"` 可复现原文 | 通过 |
| X7 | `stage` 误用 | 既有 family 不改 stage；portfolio 必须新 `family_id`（T46 + 文档） | 通过 |
| X8 | 单因子误开 `require_pbo` | `G2Policy.require_pbo` 默认 `False`；示例仅组合层开启 | 通过 |
| X9 | 版本锚点遗漏 | 4 处锚点 + `test_fix3_version_unification.py` L34 + `verify_fix3_manual.py` L21/L22 全部 3.7.0 | 通过 |

---

## §7 文档同步验收（E8）

| 项 | DoD | 状态 |
|----|-----|------|
| `DECISIONS.md`（仓库根） | ADR-055（样本外协议+holdout 锁）/ ADR-056（DSR+PBO 口径）/ ADR-057（规格曲线联合推断）/ ADR-058（G2 门禁与效应量强制）四条落档，各含「背景/决策/替代方案/后果」 | 通过 |
| `CHANGELOG.md`（仓库根） | v3.7.0 段落：新增模块、55 项测试、兼容声明 | 通过 |
| `docs/PROJECT_STATUS.md` | P1 批次状态更新（含 E0 基线 vs E8 全量读数对比） | 通过 |
| `README.md` | 版本号 3.7.0；新模块一句话说明（不夸大） | 通过 |
| EXECUTION 回填 | §0.1 状态列 → 已完成；§5.3 阶段读数；§6 性能实测 | 通过 |
| 一致性 review | [CONSISTENCY_REVIEW_V3.7.0_STAT_EVIDENCE_CHAIN.md](CONSISTENCY_REVIEW_V3.7.0_STAT_EVIDENCE_CHAIN.md) 产出并通过 | 通过 |

---

## §8 汇总（实施前基线，步骤 10 复核）

| 分项 | 项数 | 通过 | 失败 | 阻塞 | 不适用 |
|------|------|------|------|------|--------|
| E 任务（E0-E8） | 9 | 9 | 0 | 0 | 0 |
| TDD 用例（55 项） | 55 | 55 | 0 | 0 | 0 |
| 既有测试扩展（8 例） | 8 | 8 | 0 | 0 | 0 |
| 兼容性 | 11 | 11 | 0 | 0 | 0 |
| 门禁 | 8 | 8 | 0 | 0 | 0 |
| 性能 | 7 | 7 | 0 | 0 | 0 |
| 风险处置 | 9 | 7 | 0 | 0 | 2（X1/X2） |
| 文档同步 | 6 | 6 | 0 | 0 | 0 |

> 计数只由上文逐行状态汇总（RULE-2）；本表在步骤 9 之后按实际状态重算，步骤 10 审计不得只引用本表而不核对逐行状态。
> **当前结论（2026-11-18，步骤 9 完成）**：验收通过。E0-E8 全部落地；55 项 TDD 用例双读数红→绿（52 计划 + 异构复审修正 3）；8 例既有测试扩展通过；11 项兼容性、8 项门禁、7 项性能、6 项文档全部通过；风险处置 7 通过、2 项不适用（无研究脚本/并发调用方接入）；全量回归 **1929 passed / 15 skipped / 0 failed**（对比 E0 基线 1866，+63，零新增失败）。异构复审 PASS_WITH_FIXES（H1 已修复 + 探针 84 项 PASS），见 [审计报告](2026-11-18-v3.7.0-stat-evidence-chain-audit.md)。
