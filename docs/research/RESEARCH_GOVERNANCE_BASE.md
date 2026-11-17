# RESEARCH 治理底座 — P0 四件套 (GR-1 ~ GR-4)

> **版本**: v1.1 (2026-11-17；v1.0 = 步骤 2 初稿；v1.1 = 按 SPEC_PROCESS v1.7.2 补步骤 2 门禁与 F1-F4 形态对账，见 §9)
> **范围**: `GovernanceRecord` + 存储 / 数据契约 / Golden master / 多重检验台账 / 计量基准对拍 / 性能
> **上游**: [多因子治理路线图 §4-§6](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) / [PROJECT_STATUS P1-A](../PROJECT_STATUS.md)
> **调研工具**: Crossref / OpenAlex / WebSearch / WebFetch / 本地代码回溯 / Stata 18 批处理冒烟
> **说明**: Semantic Scholar 与 Google 镜像本次返回空/522，学术元数据以 Crossref + 原文 PDF 为准；
> 付费墙文献仅核实到摘要/公式片段，状态标注为 ⚠️。

---

## §1 调研问题清单

| # | 问题 | 对应任务 |
|---|------|---------|
| Q1 | 治理记录应记录哪些字段、如何保证确定性与 append-only？ | GR-1 |
| Q2 | 数据契约如何做新鲜度/PIT/覆盖率校验，且默认零变更？ | GR-2 |
| Q3 | 数值回归基线如何存储、比较、跨环境判定？ | GR-3 |
| Q4 | 多重检验台账如何预注册 family、统计全部试验、区分 q 与校正 p？ | GR-4 |
| Q5 | 计量模型如何与 Stata/独立实现对标，避免 RNG 不可对齐？ | GR-4 / P1 |
| Q6 | 多因子宽表（T×N）下各环节的性能瓶颈与预算？ | 全部 |
| Q7 | 现有代码哪些可复用、哪些有语义缺陷必须绕开？ | 全部 |
| Q8 | 版本/依赖/兼容边界（Python 3.9、DuckDB、pydantic）？ | 全部 |

---

## §2 学术文献调研

### 2.1 多重检验与 data snooping

| 文献 | 出处 / DOI | 关键定义 | 状态 |
|------|-----------|---------|------|
| Benjamini & Hochberg (1995) | JRSS-B 57(1):289-300 | BH step-up：`q_(i)=min_{j≥i}(m/j)p_(j)`，控制 FDR；独立/PRDS 下有效 | ✅ 通行定义 |
| Benjamini & Yekutieli (2001) | *Ann. Statist.* 29(4):1165-1188, DOI 10.1214/aos/1013699998 | 任意相依下 `q_(i)=min_{j≥i}(m·H_m/j)p_(j)`，`H_m=Σ1/i`；更保守 | ✅ Crossref |
| Holm (1979) | *Scand. J. Statist.* 6(2):65-70 | 逐步下降 FWER：`p_adj_(i)=max_{j≤i} min(1,(m-j+1)p_(j))` | ✅ 通行定义 |
| Romano & Wolf (2005) | *Econometrica* 73(4):1237-1282, DOI 10.1111/j.1468-0262.2005.00615.x | 基于 bootstrap 的 stepdown，控制 FWER；利用检验统计量联合相依结构 | ✅ Crossref |
| Romano & Wolf (2016) | *Statist. Probab. Lett.* | 调整 p 值的高效算法；`rwolf`/`rwolf2` 实现依据 | ⚠️ 仅二次源 |
| White (2000) | *Econometrica* 68(5):1097-1126 | Reality Check：`V=max_k √T·f̄_k`；stationary bootstrap 零分布；控制 data snooping | ✅ 通行定义 |
| Hansen (2005) | *JBES* 23(4):365-380, DOI 10.1198/073500105000000063 | SPA：studentize + 样本依赖 recentering；LIL 阈值 `√(ω̂²/T)·√(2 log log T)`；三区域 p（lc / consistent / uc） | ✅ Crossref + 摘要 |
| Harvey, Liu & Zhu (2016) | *RFS* 29(1):5-68 | 多重检验下 t>3 门槛；因子动物园的 FDR/FWER 校准 | ✅ 通行定义 |

> 页码为标准引用；带 DOI 的条目已用 Crossref 核实（✅），其余按通行引用（⚠️ 页码未逐项核实）。

**对台账的直接约束**：

1. **FDR q 与 FWER 校正 p 不可混用**：BH/BY 输出 q 值；Bonferroni/Holm/Romano-Wolf/White/Hansen 输出校正 p 或联合 p。台账必须按预注册轨二选一，并分列存储。
2. **family 必须预注册**：family 的假设集合、检验轨、α、试验上限在 S0 固定；事后按结果重新分组会使校正失效。
3. **n_trials 必须是全部已执行试验**：仅报告"进入报告的变体"会系统性低估搜索规模（Harvey 等所谓的 file drawer）。
4. **相依结构**：BH 在任意相依下不保证 FDR；BY 保守；Romano-Wolf/White/Hansen 通过重抽样保留相依结构，但要求 bootstrap 方案与统计量口径一致。

### 2.2 过拟合校正：DSR 与 PBO（P1）

| 文献 | 出处 / DOI | 关键公式 | 状态 |
|------|-----------|---------|------|
| Bailey & López de Prado (2014) | *JPM* 40(5):94-107 | `DSR = Φ((SR̂−SR0)√(T−1)/√(1−γ3SR̂+((γ4−1)/4)SR̂²))`；`SR0=√V[SR_n]·((1−γ)Φ⁻¹(1−1/N)+γΦ⁻¹(1−1/(Ne)))` | ✅ 原文 PDF |
| Bailey, Borwein, LdP & Zhu (2017) | *J. Comput. Finance* 20(4), DOI 10.21314/JCF.2016.322 | CSCV：S 个连续块、`C(S,S/2)` 对称切分；IS 最优在 OOS 的相对秩 `ω`，`λ=log(ω/(1−ω))`；`PBO=P(λ≤0)` | ✅ 原文 PDF |
| López de Prado (2018) | *Advances in Financial Machine Learning*, Wiley | Purged K-Fold / CPCV + embargo；标签区间与测试折重叠的样本必须剔除 | ✅ 通行定义 |

**关键口径陷阱**：

- DSR 的 `SR̂`、`SR0` 是**逐期（per-bar）Sharpe**，不是年化；`γ4` 是**非超额**峰度（正态=3）；`N` 是独立试验数，试验相关时需用有效试验数或做 N 敏感性；`V[SR_n]` 是各试验 Sharpe 的截面方差，未知时可用零假设抽样方差 `1/(T−1)` 作为最小 deflator。
- DSR 输出是**概率**（真实 SR 超过 SR0 的置信度），不是 p 值；门禁阈值必须预注册。
- PBO 是**对搜索过程**的评估，不是对获胜者的评估；对 S、N、T 与绩效指标敏感，S 必须预注册并做敏感性（如 S=10/12/16）。
- CSCV 要求 S 为偶数、T 可被 S 整除；块内绩效用同一指标（常用 Sharpe）；相对秩的并列需用平均秩。

### 2.3 效应量与置信区间

学术报告的最低要求是 **p 值 + 效应量 + 置信区间** 三件套；只报 p/q 会把"统计显著"误读为"经济显著"。
本仓库已有 `PremiumEstimator.estimate_with_errors`（Fama-MacBeth + Epanechnikov 带宽 + HAC SE），
其 HAC 引擎已通过 Stata `newey` 三层对拍（[EXECUTION_V3.4.12](../EXECUTION_V3.4.12_PREMIUM_HAC_SE.md) §9.2），
可直接作为效应量/CI 的计量基座。

### 2.4 模型风险治理

- **SR 11-7**（Fed/OCC, 2011）：model inventory、independent validation、ongoing monitoring、change management、model tiering。
- **Model Cards**（Mitchell et al., 2019, DOI 10.1145/3287560.3287596）：面向人的模型说明卡，含用途、训练数据、评估条件、局限。
- 与本路线图的映射：`FactorCard` ≈ Model Card；`GovernanceRecord` ≈ inventory + evidence；`Tier` ≈ tiering；`reviewer`/`independent validation` ≈ 二道防线。

### 2.5 A 股数据偏差的学术与业界口径（数据层复审增补）

> 依据：[数据层治理复审 §3](../analysis/DATA_LAYER_GOVERNANCE_REVIEW.md) 一手实证 + 公认数据偏差原则。
> 四类偏差中，**前视可检测、幸存者只能披露**，是本仓库契约设计的关键不对称。

| 偏差 | 机理 | 本仓库实证现状 | 契约可做什么 |
|------|------|---------------|-------------|
| **幸存者偏差** | 只用"存活至今"的股票回测，剔除退市/被并购者，高估收益 | 面板**已含 217 只退市/长期停牌股**（DATA_GAPS §2.1），非纯幸存者面板；但覆盖完整性未核验 | **不可检测**（缺"历史全市场名单"参照集，无法感知"缺席"）；只能以 `universe_bias` 枚举 + `known_gaps` **披露** |
| **前视偏差** | 用未来才可知的信息（财报公告日、成分生效日、ST 生效日）构造当期因子 | `list_date` 已有（5797 只）；公告日/生效日缺 | **可检测**：`pit` 检查（值不得早于 `list_date`）；公告日/生效日缺失 → `pit_status='unavailable'` 披露，production 才阻断 |
| **复权口径** | 前复权 qfq 随新除权事件**改写全部历史价**，破坏可复现；后复权 hfq 历史价不变 | `stock_adj` 实测为 **hfq**（末值=1 仅 2.2%、因子递增）；`stock_return` 为复权收益（corr 0.99998） | `price_convention` 锁 `hfq`/`raw+adj_factor`，**禁 qfq**（防回归）；adj>0 + 行数对齐 + 单调性披露 |
| **ST/停牌/涨跌停** | 不可交易标的进入组合 → 虚增可得收益；停牌日收益处理不当 → 偏差 | `stock_name` 历史名称可推导 **ST 代理**（459 列曾含 ST）；`stock_suspend` 为 'S'/'R' 事件表 | `tradable_convention` 枚举过滤 + **代理口径披露**；停牌状态需从事件表重建 |

**关键原则**：
1. **幸存者偏差不可由数据契约"检测"**——契约只能校验"在场数据"的合法性，无法感知"应到而缺席"的退市股；
   必须靠 `universe_bias` 显式声明 + 历史全市场名单（专项 B）才能根治。把"检测幸存者偏差"写进契约是过度承诺。
2. **复权可复现性是硬约束**：qfq 的"同输入不同日期产出不同值"会同时击穿 `data_snapshot_hash` 与 golden master；
   本仓库已是 hfq，契约的作用是**锁定防回归**，而非修复现状。
3. **代理口径必须披露**：名称含 ST ≠ 官方 ST 标记（更名/借壳干扰）；`amount==0` 作停牌代理亦有误判；
   凡代理口径，`tradable_convention` 必须显式记录，供 G3 披露与下游复核。

---

## §3 社区与工程实践调研

### 3.1 数据契约 / 数据质量

| 方案 | 模式 | 优点 | 代价 | 本仓库适配 |
|------|------|------|------|-----------|
| Great Expectations | 声明式 expectations + Validation Result + Data Docs | 产物可读、可分享；检查丰富 | 依赖重、配置多；未安装 | ❌ 不引入 |
| Pandera | 代码即 schema（`DataFrameModel`），pytest 友好 | 轻、类型化、可做统计检查 | 需新增依赖；未安装 | ⚠️ 可选适配，不作为 P0 |
| Deequ | Spark 约束验证 + 指标 | 大数据生态 | Spark 依赖 | ❌ 不适用 |
| Data contracts（业界） | schema + 语义 + 新鲜度 SLA + owner + 版本化 | 明确 producer/consumer 责任 | 需要流程配套 | ✅ 采用其**要素**，轻量实现 |

**结论**：P0 不引入第三方数据校验框架，按 data contract 的四要素（schema/语义/新鲜度/owner）实现
轻量 `FieldSpec + CheckResult + ContractReport`；保留 `FieldReader` 协议，便于未来接 Pandera/GE。

### 3.2 实验追踪与模型注册

| 方案 | 可借鉴 | 不借鉴 |
|------|--------|--------|
| MLflow Tracking / Model Registry | run 元数据、lineage、版本、stage transition、audit log、alias（champion/challenger） | 服务端/UI 依赖；本仓库只需本地 append-only |
| OpenLineage | run/job/dataset facet 的事件 schema | 事件总线与序列化开销 |
| DVC | 数据版本与 pipeline 重放 | 与现有缓存体系重复 |

**结论**：`GovernanceRecord` 采用"不可变记录 + 父指针 + 批次/实验标识 + 版本化 schema"，
等价于 MLflow 的 run/registry 最小子集；不引入服务端。

### 3.3 Golden master / 数值回归

| 方案 | 模式 | 结论 |
|------|------|------|
| pytest-regressions | data directory + baseline 文件 + tolerant 比较 | 思路采用；不新增依赖 |
| Approval Tests | 人工批准基线变更 | 采用"显式 capture/force"流程 |
| Characterization tests | 锁定现有行为，重构时防回归 | 正是 GR-3 的目的 |
| 社区经验 | 严格比较用于确定性变换，容差比较用于数值/模型输出；golden 版本化；只在显式 review 后重生成 | ✅ 直接采用 |

**结论**：基线必须**版本化**、**可审计**、**默认不覆盖**；同环境用 `rtol=1e-10/atol=1e-12`，
跨环境禁止 bitwise 断言（BLAS/线程/浮点重排）。

### 3.4 存储：DuckDB 写入模式

DuckDB 官方文档明确警告：**不要用 `executemany` 大批量插入**，应使用
`INSERT INTO ... SELECT * FROM df`（replacement scan）或 Appender。本次实测（见 §5 P1）：
10,000 行 `executemany` 17.540s，`INSERT ... SELECT` 0.009s，差约 **1950×**。

**结论**：
- 单条记录（低频）用参数化 `execute`；
- 批量记录用 DataFrame + `INSERT INTO ... SELECT`；
- 表结构采用"提升列 + JSON payload"混合，避免字段演进频繁 `ALTER TABLE`；
- JSONL 作为无 DuckDB 环境的 fallback；并发写优先 JSONL（单行 append 原子性更好）。

### 3.5 Stata 对拍

本机已安装 **Stata 18 MP**（`C:\Program Files\Stata18\StataMP-64.exe`），
`subprocess.run([exe, '/e', 'do', 'x.do'])` 冒烟通过（exit 0，日志含 `STATA_OK` / `18`）。

| 需求 | Stata 参照 | 可用性 |
|------|-----------|--------|
| HAC / Newey-West SE | `newey y, lag(q)` | ✅ 内置；已有 `scripts/verify_hac_stata.py` |
| 横截面 OLS SE | `statsby ...: regress` | ✅ 内置；已有对拍 |
| Bonferroni / Holm | `mtest` 或 `.do` 手写 | ✅ 内置 |
| BH / BY | `multproc`（Jann 2015, SSC）或 `.do` 手写 | ⚠️ `multproc` 未安装；手写公式可精确对拍 |
| Romano-Wolf | `rwolf2`（Clarke/Romano/Wolf, SSC） | ⚠️ 未安装；可导出 bootstrap 矩阵做确定性重放 |
| White RC / Hansen SPA | 无内置；`.do` + Mata 按算法实现 | ⚠️ 需自写参照 |
| DSR / PBO | 无内置；`.do` + Mata 公式实现 | ⚠️ 需自写参照 |

**关键方法**：不追求两侧 RNG 对齐（Stata 与 NumPy 的随机流不同），而是
**Python 生成确定性 fixture（含 bootstrap 索引矩阵/分区列表），Stata 只做确定性重放**。
这样对拍的是算法实现，不是随机数发生器；可实现 1e-10 级精确比较。

### 3.6 选型结论

| 维度 | 选择 | 理由 |
|------|------|------|
| 记录模型 | pydantic v2（已依赖） | 校验/序列化/版本化；与 `config_v2` 风格一致 |
| 存储 | DuckDB（已依赖）+ JSONL fallback | 列式、零额外依赖、批量插入快 |
| 数据契约 | 自实现轻量协议 | 不新增 GE/Pandera 依赖；可插拔 reader |
| Golden master | DuckDB 读写 parquet + JSON manifest | 避免 pyarrow 成为硬依赖（虽本机已装） |
| 台账 | 自实现 registry + 复用 `backtest.multiple_testing` 计算核 | 单一计算真相源，台账只管口径与存证 |
| 对拍 | 独立 `benchmarks/` 脚本 + Stata 批处理 | 不进入 pytest 主路径，Stata 缺失时 SKIP |

### 3.7 数据层治理社区案例（数据层复审增补）

> 支撑"契约词汇并入本批次 / 数据接入层另立专项 A / 数据资产另立专项 B"的三层拆分。

| 案例 / 模式 | 核心做法 | 对本仓库的启示 |
|------------|---------|---------------|
| **DataPortal 统一数据入口**（QuantConnect Lean / zipline 等回测框架的通用模式） | 单一 `DataPortal` 封装多源读取、字段映射、单位换算、缓存；上层策略/因子只面向 canonical schema | 专项 A 的 `DataPortal` 即此模式；**契约（GR-2）消费 DataPortal 输出，而非自己实现 IO**——避免契约与读取层绑死 |
| **Data Contracts**（业界数据契约实践） | schema + 语义 + 新鲜度 SLA + owner + 版本化，producer/consumer 责任显式 | 本批次契约词汇表（DESIGN §5.7）即契约的"语义 + 口径"部分；freshness/owner 已在 GR-2 |
| **Great Expectations / Pandera**（数据校验框架） | 声明式期望 / 代码即 schema，产出可读校验报告 | §3.1 已评估：P0 不引入重依赖，自实现轻量 `FieldSpec + CheckResult`，保留可插拔 reader 便于未来接入 |
| **DataHub / OpenMetadata**（元数据 / lineage 目录） | 数据集血缘、字段字典、来源链、版本 | 专项 A 的 lineage（`data_snapshot + universe_version + calendar_hash + content_digest + 来源链`）借鉴其"字段级血缘"思想，但本地轻量实现，不引入服务端 |

**拆分判据（数据层复审 §1）**：
1. **契约闭合性**：口径字段是 G0/G3 判据，须先枚举化（本批次）；
2. **耦合方向**：GR-2 依赖数据访问接口而非实现它（DataPortal 另立专项 A）——真实理由是**范围/可测性/默认零变更**，
   而非字面违反模块 DAG（复审 H5 已澄清）；
3. **验证可行性**：P0 用合成 fixture；数据接入/资产需真实数据（专项 A/B）。
   **H1 深化**：停牌/ST/退市/日历数据已存在 → 专项 A 不被外部采购阻塞，可先行。

---

## §4 本仓库代码核对

### 4.1 `backtest/multiple_testing.py`

| 位置 | 现状 | 设计影响 |
|------|------|---------|
| L52 `apply_bh_fdr` | Python 循环 + `np.argsort`（默认 quicksort，非稳定）；返回 q 与掩码 | 台账复用 q；**并列组 q 相同**（累积 min 性质，5040 排列实测），按 variant_id 输出即可 |
| L119 `apply_bonferroni` | `p_adj=min(mp,1)`；拒绝用 `p < α/m`（严格） | 台账统一用 `p_adj <= α` 重算掩码 |
| L210 `apply_by_fdr` | 调和数校正；拒绝用 `q < α`（严格） | 同上，统一 `<=` |
| L586 `apply_romano_wolf` | stepdown；每个 j 对子矩阵重复 `np.sort` | k=1 时第 k 小恒为 `sorted_boot[:,0]`，可 O(m) 向量化；保留原实现作参照 |
| L919 `WhiteRealityCheck` | B×K 双重 Python 循环；块大小取第 0 列；逐策略再 bootstrap | 需注入索引矩阵 + 分块向量化；块大小口径需披露 |
| L1119 `HansenSPA` | `boot_stats_uc=0` → `spa_uc_p=0`（构造性退化） | **不是完整 Hansen 上界**；P0 只把 consistent p 当结论，uc 标注为退化 |
| L654 `_generate_bootstrap_p_values_for_ks` | B×K 循环 + `ks_2samp` | 不在 P0 台账主路径；性能登记 |

### 4.2 存储与日志现状

| 模块 | 现状 | 与治理底座的关系 |
|------|------|-----------------|
| `fingerprint_performance_logger.py` L47/L73/L95 | DuckDB 单行 INSERT；`enable=False`；21 维指纹 | 复用其"同库表 + append-only"思路；**不复用**单行 INSERT |
| `specification_logger/spec_log.py` L25/L40 | JSONL append-only；8 位 SHA1；无 schema | 复用 append-only 思路；**不能**作治理记录（无校验/无确定性全哈希） |
| `spec_log.py` L106 `enforce_test_set_once` | 只返回警告，不阻断 | holdout 锁定的**辅助**检查，不是真相源 |
| `cache_manager.py` L58/L66 | `CacheKey(namespace, identifier, version)`；`CODE_VERSION=v2.3.0-cache` | 数据指纹思路可复用；治理底座不改缓存代际 |

### 4.3 管线接入点

| 位置 | 现状 | 设计接入 |
|------|------|---------|
| `pipelines_v2.py` L1135 `fit` | 每因子循环 L1194-1222；写 `factor_routing`；L1222 `_log_spec` | 在路由记录写完后发一个**纯 dict 事件**；不 import 治理模块 |
| `pipelines_v2.py` L1470 `_log_spec` | `enable_specification_logger=False` 时直接返回 | 不能作默认接入点（路线图 F4 已定） |
| `pipelines_v2.py` L500 `pipeline_mode` | `unified`/`dynamic_ab` 全局决定 arm | 事件中的 `arm` 直接取 `pipe_type` |

### 4.4 数据布局事实

`scripts/verify_multifactor_multiyear.py` L59-72 显示实际字段：

| 逻辑字段 | 实际文件 | 备注 |
|---------|---------|------|
| price | `stock_close.pkl` | DataFrame，日期×股票（1475×5688） |
| adj | `stock_adj.pkl` | **后复权 hfq 累计因子**（数据层复审 H3 实测：末值=1 仅 2.2%、因子递增）；**与 close 行数不对齐（1394 vs 1475，81 日缺失）** |
| amount | `stock_amount.pkl` | 成交额 |
| mv | `market_value.csv` | 市值，末次 2026-01-23 |
| list_date | `list_date_df.pkl['list_date']` | PIT 上市日；覆盖 **5797 只**（多于价格面板 5688，含面板外个股） |
| volume | `stock_volume.pkl` | **已存在**，`load_market` 未加载（数据层复审 H1） |
| open/high/low | `stock_open/high/low.pkl` | **已存在**，`load_market` 未加载 |
| suspend | `stock_suspend.pkl` | **已存在**，'S'/'R' **事件表**（非每日 0/1），需重建逐日停牌状态 |
| name | `stock_name.pkl` | **已存在**，历史名称面板（2606 列随时间变化、459 列曾含 ST），可推导 **ST 代理** |
| return | `stock_return.pkl` | **已存在**，复权日收益（与 `(close*adj).pct_change()` corr 0.99998）；`load_market` 另用派生 `close*adj` 下期收益 |
| calendar | `all_dates.pkl` | **交易日历已存在**（1475 交易日，2020-01-02→2026-01-30，list of str） |

> **数据层复审 H1/H3 修正**：原"volume/suspend 根目录未见同名文件"判断**被证伪**——
> `stock_volume/open/high/low/return/suspend/name` 与 `all_dates` 均已存在，仅 `load_market` 未加载，
> 属"接入/规范化"（专项 A）而非"数据缺口"（专项 B）。详见
> [数据层治理复审 §3](../analysis/DATA_LAYER_GOVERNANCE_REVIEW.md)。

**设计约束**：契约默认字段集必须匹配上述现实；已存在但未接入的字段标为可选，
接入前降级为披露项；`return` 可用现成 `stock_return`（复权口径）或派生 `close*adj`，二者须口径对账。

### 4.5 版本与兼容锚点

| 项 | 当前值 | 位置 |
|----|--------|------|
| 项目版本 | 3.5.3 | `pyproject.toml:7` / `__init__.py:58` / `config_v2.py:371` / `reporting.py:40` |
| 版本测试 | 3.5.3 | `tests/test_fix3_version_unification.py:34` |
| 缓存代际 | `v2.3.0-cache` | `backtest/cache_manager.py:58` |
| Python | 本机 3.13.5；声明 `>=3.9` | `pyproject.toml` |
| 关键依赖 | numpy 2.1.3 / pandas 2.2.3 / scipy 1.15.3 / duckdb 2.0.0 / pydantic 2.13.4 / statsmodels 0.14.4 | 本机实测 |
| Stata | 18 MP | `C:\Program Files\Stata18\StataMP-64.exe` |

**兼容约束**：模块注解避免 PEP 604（`X | Y`），使用 `Optional/Union` 以兼容 Python 3.9；
不要向 `backtest/__init__.py` 增加新导出（该文件已 eager import 多个模块，会增加导入副作用）。

---

## §5 性能探针（2026-11-17 实测）

环境：Python 3.13.5 / numpy 2.1.3 / pandas 2.2.3 / duckdb 2.0.0 / Windows。
探针在临时目录运行，不写仓库。

| # | 场景 | 结果 | 设计含义 |
|---|------|------|---------|
| P1 | DuckDB 10,000 行插入 | `executemany` **17.540s**；`INSERT ... SELECT` **0.009s** | 禁止 executemany；批量必须走 DataFrame |
| P2 | BH 校正（当前循环 vs 向量化） | K=1,000: 0.0004 vs 0.0001s；K=10,000: 0.0036 vs 0.0003s；K=100,000: 0.0433 vs 0.0041s | 向量化收益约 10×；10 万假设仍 < 5ms |
| P3 | Romano-Wolf 调整 p（m=50, B=1000） | 逐 j 循环 0.0004s；`searchsorted` 0.00003s | k=1 时可用次序统计量 + `searchsorted` |
| P4 | PBO CSCV（T=1200, N=100, S=10, 252 分区） | 朴素逐分区 0.071s；块充分统计量 0.011s | 预计算每块 sum/sumsq，分区只做加法 |
| P5 | 数据契约扫描（2500×5000） | 0.084s | 单次宽表扫描可接受；按字段缓存 |
| P6 | 记录规范化 + SHA256（10,000 条） | 0.049s | 记录写入不是瓶颈 |
| P7 | Golden 比较（24×300，1000 次） | 0.023s | 小样本基线比较可忽略 |
| P8 | Stata 18 批处理冒烟 | exit 0；`c(version)=18` | `/e do` 协议可用 |

**预算建议**：

| 环节 | 预算 |
|------|------|
| 数据契约（7 字段，2500×5000，冷启动） | < 10s（含 pickle/CSV IO）；缓存命中 < 0.1s |
| 治理记录写入（10k） | < 0.1s |
| BH/BY（10 万假设） | < 0.05s |
| Romano-Wolf（m=1000, B=1000） | < 0.5s（含 bootstrap 矩阵排序） |
| White RC / Hansen SPA（T=1000, K=100, B=1000） | < 10s（分块；内存 < 1GB） |
| PBO（T=1200, N=1000, S=10） | < 1s；S=16 约 5-6s |
| Golden 比较（24×300×4） | < 0.1s |

---

## §6 结论与设计约束

### 6.1 可直接复用

1. `backtest.multiple_testing` 的 BH/BY/Bonferroni/Romano-Wolf/White/Hansen 计算核；
2. `SpecificationLogger` 的 append-only JSONL 思路（不复用其哈希与 schema）；
3. `CacheKey` 的 namespace/identifier/version 三段式（用于契约快照缓存）；
4. `PremiumEstimator` 的 HAC/效应量/CI（P1 直接消费）；
5. 已有 Stata 对拍脚本的 fixture 导出 + `/e do` + 日志解析模式。

### 6.2 必须绕开或修正的语义

| # | 问题 | 处置 |
|---|------|------|
| C1 | `apply_by_fdr` / `apply_bonferroni` 的拒绝用严格 `<`，BH 用 `<=` | 台账统一从 q/p_adj 以 `<=` 重算掩码，不改原函数 |
| C2 | 初稿误判 BH 的 `argsort` 非稳定会使并列 p 的 q 依赖输入顺序 | 5040 种排列实测 q 向量唯一：累积 min 使并列组 q 相同；台账按 variant_id 输出即可，无需改排序 |
| C3 | Romano-Wolf 逐 j 重复排序 | 台账提供 O(m) 快速核，原实现作对照（等价性测试） |
| C4 | White/Hansen 内部自行 bootstrap，无法注入索引 | 给类 `test()` 增加可选 `bootstrap_indices`（默认 None，零行为变更） |
| C5 | Hansen `uc` 构造性为 0，不是完整上界 | P0 只采用 consistent p；uc 标注退化，P1 再补 |
| C6 | White 块大小取第 0 列 | 设计 §7.4.1 Bootstrap 协议升级为全 K 列 ρ 中位数（B19 复审修正）；`block_size` 显式传参仍优先 |
| C7 | 数据根 volume/suspend **已存在**（数据层复审 H1 证伪原"无文件"判断），仅 `load_market` 未加载 | 契约字段标可选；属"接入"非"缺口"；suspend 为 'S'/'R' 事件表需重建逐日状态 |
| C8 | DuckDB `executemany` 极慢 | 批量只走 `INSERT ... SELECT` |

### 6.3 明确不做

1. 不引入 Great Expectations / Pandera / MLflow 服务端；
2. 不把 `SpecificationLogger` 改造成治理记录（职责不同）；
3. 不在 P0 实现 DSR/PBO/purged CV（P1 任务，本次只预留接口）；
4. 不修改 `pipeline_mode` 路由语义；
5. 不对齐 Stata/NumPy 的 RNG（改为确定性 fixture 重放）；
6. 不做跨环境 bitwise golden 断言。

---

## §7 不可核实项与后续

| 项 | 原因 | 处置 |
|----|------|------|
| Romano & Wolf (2016) 精确页码 | 付费墙/仅二次源 | 设计只引用算法，不引页码 |
| White (2000) / Holm (1979) DOI | 未逐项查 Crossref | 设计引用作者-年份-标题，不依赖 DOI |
| `rwolf2` / `multproc` 的 Stata 数值 | SSC 包未安装（无用户 ado 目录） | 基准脚本以自写 `.do` 为主；可选安装后做第二参照 |
| DSR/PBO 的 Stata 官方实现 | 不存在 | 以原文公式 + 独立 Python 实现 + MC 三重验证 |
| 真实数据上 PBO/DSR 的稳定性 | 依赖 P1 实装 | 列为 P1 验收项，不在本设计承诺 |

---

## §8 步骤 2 review 记录（调研文档）

**方法**: 逐项回源（代码行号/签名/版本/实测数字）；文献元数据与 Crossref/原文 PDF 对照；
社区结论只保留可操作项，不引用无法核实的数值。

| # | 检查项 | 方法 | 结果 |
|---|--------|------|------|
| R1 | 代码行号锚点（`multiple_testing` / `pipelines_v2` / `spec_log` / `cache_manager`） | grep + 读码 | 全部吻合 |
| R2 | 版本锚点（3.5.3 / `v2.3.0-cache`） | grep | 全部吻合 |
| R3 | 实际数据文件名（close/adj/amount/mv/list_date） | 读 `verify_multifactor_multiyear.py` | 吻合；volume/suspend 已改为"该加载器未使用" |
| R4 | 文献 DOI（BY/Hansen/Romano-Wolf/Model Cards/Pandera） | Crossref | 5/5 吻合 |
| R5 | DSR/PBO 公式 | 原文 PDF + 多源摘要 | 一致；已标注 per-bar/非超额峰度/概率语义 |
| R6 | 性能数字（P1-P8） | 本机实测 | 原始输出直接抄录，无外推 |
| R7 | Stata 可用性 | subprocess 冒烟 | exit 0 / version 18 |
| R8 | "不引入 GE/Pandera/MLflow" | 依赖检查 | 三者均未安装，结论成立 |

**发现并修正（3 处）**：

| # | 问题 | 修正 |
|---|------|------|
| F1 | "volume/suspend 实际不存在"过强（仅该加载器未使用） | 改为"该加载器未使用；其他数据源未核实" |
| F2 | 初稿误判 BH 并列 p 的排序敏感性 | 5040 排列探针实测 q 向量唯一；已修正 §4.1 C2 与 §6.2 C2 |
| F3 | Romano-Wolf 2016 页码/DOI 未核实 | 标为 ⚠️，仅引用算法不引页码 |

**结论**: 调研文档无幻觉级错误；可作为步骤 3 设计的依据。

---

## §9 步骤 2 门禁与 F1-F4 形态对账（SPEC_PROCESS v1.7.2）

> 2026-11-17 追加。只补**形态**，不改结论；对应上游 §Step 2 Review 门禁 (a)-(d) 与 §契约取证字段形态 F1-F5。

### 9.1 Step 2 门禁四项

| 门禁 | 状态 | 证据 |
|------|------|------|
| (a) FALSIFIED 断言已改写并记入修订记录 | ✅ | §8 F1「volume/suspend 实际不存在」→「该加载器未使用」；F2 BH 并列排序敏感性 → 5040 排列实测后改写 §4.1/§6.2；F3 Romano-Wolf 2016 页码标 ⚠️ |
| (b) CONFLICT / STEP_GAP_OPEN 已仲裁 | ✅ 无 OPEN | Hansen 未 studentize 属「实现与原文偏差」而非文献冲突，已在 §2.1 与设计 §7.4 登记为 F-G；无 STEP_GAP_OPEN |
| (c) 阻断性断言双源 | ✅ | Hansen studentization：原文摘要（T1）+ 原文 PDF（T1）；DSR/PBO 公式：原文 PDF（T1）+ 二次源；RW 重抽单元：RW 2005（T1）+ RAPS 综述（T2）。单源项仅 §3.4 DuckDB 官方警告，已由本机实测 P1 交叉（T1 + E2） |
| (d) 假设区已转 A/B 或显式 [待定] | ✅ | 「mv 走独立导出流程」→ [待定]（DATA_GAPS §2.2 推断，根因未取证）；「tushare 行业可换源」→ [待定]（专项 B）；「真实 A 股 size/power」→ U1（E5 待核） |

### 9.2 F1-F4 出具形态

| 字段 | 出具 |
|------|------|
| **F1 来源日期** | 全部外部来源**读取日 = 2026-11-17**（本次 Crossref/原文 PDF 复核日）；发布日信息 = 文献年份 + 卷期（见 §2 表）。内部文件写版本 + 行号区间（如 `multiple_testing.py L1119 @ 3.5.3`）。无「近期/最新」表述 |
| **F2 来源版本** | 文献：期刊卷期/DOI 版本（§2 表）；内部文件：`factor_pipeline 3.5.3` + 行号（§4）；工具：DuckDB 1.5.3 / pydantic 2.13.4 / Stata 18 MP（§5）。无留空行 |
| **F3 降级链** | 三段式：`Semantic Scholar (search_semantic) 返回空 + mcp_english-search 522 → Crossref REST + 原文 PDF / WebFetch → 读到 DOI 命中、摘要与公式片段；未取证项 = 付费墙页码（§7）`；`Stata SSC 包（rwolf2/multproc）未安装 → 自写 .do + Mata 参照 → 算法级对拍可用，包级第二参照未取证（§2.1/§7）` |
| **F4 引用验证表** | 外部引用 >3 条，§2.1/§2.2 已建表（引用 / DOI / 关键定义 / 状态）。核验读数：Crossref 命中 **5/5**（BY、Hansen、Romano-Wolf、Model Cards、Pandera）；**元数据错配 0 条**；**未验证 2 条**（Romano-Wolf 2016 页码、White 2000 / Holm 1979 的 DOI 未逐项查） |
| **F5 先失败记录** | **N/A**：本批为文档（Layer-0），无代码 / fixture 改动；F5 只约束 Step 9 有代码改动时 |

### 9.3 证据等级自评

| 结论 | 等级 | 说明 |
|------|------|------|
| 代码行号/签名/默认值（§4） | E1 | 读码可原样重放（grep/Read） |
| 文献公式与定义（§2） | E1 | 回原文 PDF / Crossref 元数据 |
| 性能数字 P1-P8（§5） | E2 | 本机实测，含失败/边界场景（executemany 慢、契约宽表扫描） |
| 工具可用性（Stata 冒烟） | E2 | 单场景冒烟，已附命令与退出码 |
| 社区实践结论（§3） | E4 | 判断陈述，仅作工程陷阱线索，不作方法学依据 |

---

**调研结论**：P0 四件套可以在**零新增依赖**（pydantic/duckdb 已是核心依赖）下实现；
关键不是工具选型，而是口径（预注册、全部试验、q/p 分离、确定性 record_id）与
可验证性（Stata/独立实现/性能预算）。设计与代码现状的差异已在 §4/§6 登记，进入步骤 3 设计文档。
