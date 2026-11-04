# 2026-11-04 代码质量审计 — v3.3.5 PL-06 / v3.3.6 PL-05

**审计版本**: v1.1 (追加 v3.3.6 续篇; v1.0 为 PL-06 审计)
**日期**: 2026-11-04
**审计对象**: DEFECT-PL-06 修复 (v3.3.5)
**审计基准**: [CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) v1.1 (Gate 0-8)
**对齐文档**: [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) v1.3 / [ADR-039](../../DECISIONS.md)
**审计方式**: 本任务为单模块小任务 (实施文档 §13.8 裁剪), 采用主会话逐维审计 + checklist 逐项确认, 未派发并行 subagent
**总评**: **PASS**

---

## Phase 1: Spec Inventory

| 工件 | 内容 | 审查维度 |
|------|------|---------|
| EXECUTION v1.3 §2.1 | E1-E6 任务定义 | 每项 vs 代码落地 |
| EXECUTION v1.3 §3 | 代码实施 (fit no-op / 逐日截面 / 删除方法 / docstring / 配置面) | 代码 vs 设计 |
| EXECUTION v1.3 §4 | TDD 测试 (11 新例 + 3 重写 + xfail 摘除) | 测试契约 |
| EXECUTION v1.3 §5 | 版本 / 缓存 / ADR / CHANGELOG / 架构 | 文档同步 |
| ADR-039 | 决策 1-5 + 备选 + 实测证据 | 决策与代码一致性 |
| CONSISTENCY_REVIEW v1.0 | 6 项修复 | 修复是否落进最终文档 |

---

## Phase 2: Multi-Dimensional Audit

### 2.1 E 任务 vs 代码对齐

| E 任务 | 实施文档声明 | 代码实测 | 结论 |
|--------|-------------|---------|------|
| E1 `_apply_winsorize` 逐日截面 | `mu=X.mean(axis=1)`, `sd=X.std(axis=1, ddof=1)`, `clip(axis=0)` | [pipelines_v2.py L1164-L1175](../../pipelines_v2.py#L1164-L1175) 与声明逐行一致 | ✅ |
| E2 `fit` Step 2 no-op | `_winsorize_params = None`; 不再计算参数 | L1098-L1106 一致; 两分支均置 `None` | ✅ |
| E3 删除 `_compute_winsorize_params` | 方法整体删除; 3 处引用全部处理 | 全仓 grep: 定义/调用 0; 测试无 `_compute_winsorize_params` | ✅ |
| E4 11 例单测 | 公共 7 + A 专属 4, Red 10 失败 / 1 通过 | 文件存在 11 函数; Red 实测 10 failed / 1 passed; Green 11 passed | ✅ |
| E5 重写 test_07/08/09 + 摘 xfail | 逐日截面语义; 登记表移除 PL-06 | test_07/08 直接对拍边界; test_09 走 `fit` 取 `outlier`; xfail 已摘, docstring 更新 | ✅ |
| E6 版本 / 缓存 / ADR / 文档 | 3.3.5 / `v2.2.3-cache` / ADR-039 | test_fix3 7 passed; 手工 5/5; 全部文档落位 | ✅ |

### 2.2 跨模块契约 (ADR 不变式)

| 契约 | 验证 | 结论 |
|------|------|------|
| 配置面不变 (`mixed_winsor_sigma` / `transform_aggressiveness`) | `git diff`: `config_v2.py` 仅版本号; `optimizer.py` 无 diff | ✅ |
| 公共 API 不变 (`__init__` / `fit` / `transform` 签名) | diff 仅 Step 2 体内与 `_apply_winsorize` 体内; 签名行未动 | ✅ |
| 步骤顺序不变 (I-INT) | diff 未触碰 Step 3-5 | ✅ |
| `module_enabled` 语义 (winsorizer=False → identity) | diff 保持 else 分支; `test_winsorizer_disabled_skips_clip` 通过 | ✅ |
| 缓存代际自愈 | `TestCodeVersionGeneration` 3 passed | ✅ |
| 子包版本隔离 | `git diff -- modules` 为空 | ✅ |

### 2.3 接口签名核对 (实际代码 vs 文档声明)

- `MixedFactorPipeline.__init__(mixed_winsor_sigma=3.0, transformation_params=None, neutralizer_params=None, module_enabled=None)` — 与实施文档 §3.7 一致 ✅
- `_apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame` — 一致 ✅
- 删除的私有方法原签名 `(self, X) -> Dict` — 已随方法消失 ✅
- 无新增公共 API ✅

### 2.4 测试盲区识别 (4 类)

| 盲区类型 | 检查结果 | 处置 |
|---------|---------|------|
| 1. 断言恒真式 | 无。`test_bounds` 用 numpy 独立路径 (nanmean/nanstd/np.clip); `test_n11_can_clip` 断言"发生改变"而非"不抛错"; `test_sigma_monotonicity` 输出计数便于失败诊断 | 无需处置 |
| 2. 单文件检查盲区 | `transform` 路径与 `fit` 共用 `_apply_winsorize`, 单测只覆盖方法本身 → 由集成截断不变式 (端到端含 transform) 覆盖; `_create_pipeline` 传参由既有 `test_module_enabled` 覆盖 | 已被集成测试覆盖 |
| 3. 设计约束无测试 | 配置默认值 (`test_01_config_defaults` 既有) / winsorizer 开关 (新 G2-6) / N≤10 (新 G2-9) 均有测试; optimizer 搜索空间未新增测试, 但 `optimizer.py` 本次零改动 (git diff 证明) | 接受, 记录在案 |
| 4. 修正项无测试 | 实施中唯一发现 (P2): 文档 §4.4 的 test_09 代码 `assert_array_less` 未广播形状 → 修正后由 test_09 本身 (12 passed) 覆盖; 文档交叉引用修复为纯文档项 | 已闭环 |

### 2.5 数值与登记一致性

| 数值 | 代码/测试输出 | CHANGELOG / ADR / 登记表 | 结论 |
|------|-------------|------------------------|------|
| Mixed 截断不变式 | 0/1800, 0 | 0/0 (三处一致) | ✅ |
| 诊断矩阵 | 违反 1 / 满足 8 / 合计 9 | 一致 | ✅ |
| 输出差异 | 561/3000, 1.0446, 63/100 行 | 一致 | ✅ |
| 触发率 | 61 → 77 /3000 | 一致 | ✅ |
| 性能 | 0.184s (0.175/0.184/0.193) | 一致 (基线 0.281s) | ✅ |
| PL-07 reason | 复测仍 1.84e+00 / 1650 格 | reason 更新归因、数值未变 | ✅ |
| 集成计数 | 10 passed / 2 xfailed | 三份文档一致 | ✅ |

---

## Phase 3: Fix Priority Matrix

| 级别 | 发现 | 状态 |
|------|------|------|
| P0 Blocker | 无 | — |
| P1 Critical | 无 | — |
| P2 Major | F-1: 文档 §4.4 test_09 代码 `np.testing.assert_array_less` 未广播 `(5,1)` vs `(5,30)` → 运行期形状 mismatch | ✅ 已修复 (test + 文档同步, 12 passed) |
| P3 Minor | F-2: `verify_fix3_manual.py` 的 `OLD_VERSIONS=["2.0.0","2.1.0"]` 不含 `3.3.4`, 残留扫描抓不到漏改的 3.3.4 | ⏸ 既有行为; 4 处声明由 test_01-04 的一致性断言覆盖, 无需改动 |
| P3 Minor | F-3: PL-01 checklist 位于 `docs/` 根, 与方法论 §13.7 的 `docs/audit/` 不一致 | ⏸ 历史位置, 已在 v3.3.5 checklist 头部注明, 不迁移 |

**Tier 1 (本轮)**: F-1 已修复。**Tier 2/3**: F-2 / F-3 记录性遗留, 无行动项。

---

## Phase 4: Fix Baseline + Tracking

| 编号 | 严重度 | 描述 | 状态 | 修复验证 |
|------|--------|------|------|---------|
| F-1 | P2 | test_09 形状广播缺失 | ✅ 已修复 | `np.broadcast_to` + test_p3_phase2 12 passed + 实施文档 v1.3 同步 |
| F-2 | P3 | OLD_VERSIONS 不含 3.3.4 | ⏸ 记录 | test_01-04 覆盖 4 处声明; 无行动 |
| F-3 | P3 | checklist 历史位置不一致 | ⏸ 记录 | v3.3.5 起新 checklist 入 `docs/audit/`; 无行动 |

**回归验证**: 修复 F-1 后重跑全量靶向 → **73 passed / 2 xfailed / 0 failed (终验 10.76s)**; 零回归。

---

## 评分

| 维度 | 结论 |
|------|------|
| E1-E6 代码 vs 实施文档 | 6/6 对齐 |
| ADR 不变式 / 跨模块契约 | 6/6 通过 |
| 接口签名 | 一致, 无漂移 |
| 测试盲区 | 4 类无遗留 (2 项记录性说明) |
| 数值一致性 | 7/7 组一致 |
| Checklist Gate 0-8 | 全部 "必须" 项通过 |
| 回归 | 73 passed / 2 xfailed, 零回归 |
| **总评** | **PASS** |

---

## 遗留与后续

| 项 | 归属 |
|----|------|
| PL-05 (Dynamic AR `fitted_values`) | 独立缺陷, xfail 登记 |
| PL-07 (顶层指纹路由) | 独立缺陷, xfail 登记 (归因已更新为 PL-05) |
| B (percentile 1,99) / 方法选择器 | 独立任务 (设计 §3.3 / §8.3) |
| Mixed 3σ vs Static percentile 口径统一 | 独立任务 (ADR-039 已知遗留) |
| optimizer 重新调参 | 输出变更后另行评估 |
| Mixed 统一走 `ProcessingAdapter(outlier)` | 架构重构任务 |

---

## 审计签署

| 项 | 值 |
|----|-----|
| 审计结论 | **PASS** (无 P0/P1; 1 项 P2 已修复闭环; 2 项 P3 记录性遗留) |
| 阻塞交付 | 无 |
| 交付建议 | 可提交; 提交时建议单原子 commit (代码 + 测试 + 版本 + 文档), 提交前 `git diff --cached --check` |

---

# 续篇: v3.3.6 PL-05 Dynamic AR 因果性修复审计

**审计对象**: DEFECT-PL-05 修复 (v3.3.6)
**审计基准**: [CHECKLIST_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](CHECKLIST_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) v1.2 (Gate 0-8, 步骤 9 已回填)
**对齐文档**: [EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md](../EXECUTION_V3.3.6_PL05_DYNAMIC_AR_CAUSALITY.md) v1.3 / [ADR-040](../../DECISIONS.md) / [CONSISTENCY_REVIEW_V3.3.6.md](CONSISTENCY_REVIEW_V3.3.6.md) v1.2
**审计方式**: 单模块小任务 (实施文档 §13.8 裁剪), 主会话逐维审计 + checklist 逐项确认, 未派发并行 subagent
**总评**: **PASS**

---

## Phase 1: Spec Inventory

| 工件 | 内容 | 审查维度 |
|------|------|---------|
| EXECUTION v1.3 §0.1 / §3 | E1-E7 任务定义 + 代码实施 (`_fit_best` / `warmup_obs` / 前缀 fit / 三段式 transform) | 每项 vs 代码落地 |
| EXECUTION v1.3 §4 | TDD 测试 (10 函数 / 16 用例 + Red 实测 15/1 + 摘 2 xfail + 容差) | 测试契约 |
| EXECUTION v1.3 §5 | 版本 / 缓存 / ADR-040 / CHANGELOG / 架构 | 文档同步 |
| ADR-040 | 决策 1-5 + 备选 + 实测证据 + 不覆盖 | 决策与代码一致性 |
| CONSISTENCY_REVIEW v1.2 | 26 项修复 + 步骤 9 Red 计数回注 | 修复是否落进最终文档 |

## Phase 2: Multi-Dimensional Audit

### 2.1 E 任务 vs 代码对齐

| E 任务 | 实施文档声明 | 代码实测 | 结论 |
|--------|-------------|---------|------|
| E1 `_fit_best` 拆分 | `fit` 保留 INFO 日志; 私有 `_fit_best` 无日志 | [ar_model.py](../../modules/factor_decoupler/core/ar_model.py) `fit`→`_fit_best` 两方法与 §3.1 逐行一致; `batch_fit` 复用路径不变 | ✅ |
| E2 `warmup_obs` + 校验 | 签名末尾追加 `warmup_obs: int = 120`; `<= min_obs` 抛 `ValueError` | `__init__` 签名一致; 校验含建议文案, `test_warmup_must_exceed_min_obs` 匹配 | ✅ |
| E3 前缀冻结 fit | `warm = min(warmup_obs, len(data))`; `batch_fit(data.iloc[:warm])` | L302-L306 逐行一致; 短面板退化为全部行 | ✅ |
| E4 三段式 transform | 冷启动 identity / 固定 min_order / 全阶 AIC / 冻结向量化; `_WARMUP_REFIT_STRIDE=10`; 移除列门控与 `fitted_values.reindex` | L341-L403 与 §3.4 伪代码一致; `for col in data.columns` (N4); 全仓 grep `fitted_values\.reindex` = 0 | ✅ |
| E5 新单测 | 10 函数 / 16 用例; Red 实测 15 failed / 1 passed | 文件核对 10 函数 (1 个 7 参数化); Red 15/1 在 v3.3.5 旧实现复现 (0.44s); Green 16 passed | ✅ |
| E6 摘 xfail + 路由测试 + 容差 | 2 xfail 摘除; routes 断言移入新测试; φ 容差 0.15 + 区间 | 集成文件无 xfail 装饰器; `test_v2_pipeline_routing_is_causal` 3 参数; L512 `0.15` + L515 `0.5<φ<0.9`; L539 `0.08` + L540 区间 | ✅ |
| E7 版本 / 缓存 / 文档 | 3.3.6 / `v2.2.4-cache` / ADR-040 / CHANGELOG | `verify_fix3_manual` 5/5 PASS; 4 个 cache 类 diff 为空; ADR/CHANGELOG/ARCHITECTURE/DEV_PROGRESS 落位 | ✅ |

### 2.2 跨模块契约 (ADR 不变式)

| 契约 | 验证 | 结论 |
|------|------|------|
| ADR-030 诊断契约钩子 | `_get_ar_phi_for_diagnosis` 保留, docstring 改为前缀窗口语义; `test_hosts_implement_phi_hook` / 布局钉子 / 委托测试全过 (29 passed 内) | ✅ |
| `CompositeDecoupler` 公共 API | `fit`/`transform` 签名未动; 内部 `ARDecoupler` 未显式传 `warmup_obs` (默认 120 生效 → 生产 Dynamic 管线自动因果化); `test_endogeneity_regularizer` 17 passed | ✅ |
| 配置面 / optimizer | `config_v2.py` diff 仅版本号; `optimizer.py` 零 diff | ✅ |
| 缓存代际自愈 | `CODE_VERSION` bump; `TestCodeVersionGeneration` passed; 读取侧零改动 | ✅ |
| PL-06 (ADR-039) 修复保持 | Mixed 管线 13 passed + 集成 Static/Mixed PASS 0/0 | ✅ |
| 子包版本隔离 | `git diff -- modules` 仅 ar_model.py, 无 `__version__` 变更 | ✅ |

### 2.3 接口签名核对 (实际代码 vs 文档声明)

- `ARDecoupler.__init__(max_order=5, min_order=1, criterion='aic', strength=1.0, min_obs=20, warmup_obs=120)` — 与实施文档 §3.7 一致 ✅
- `AROrderSelector.fit(self, series) -> ARModelResult` 签名不变; 新增私有 `_fit_best(self, series) -> ARModelResult` ✅
- `ARDecoupler.fit/transform` 签名不变; 新增 `@staticmethod _predict_one_step(vals, t, coef, p) -> float` (类内经 `self.` 调用, 避开模块命名空间 NameError) ✅
- 无删除的公共 API; 新增面 = 1 公开参数 + 2 私有方法 + 1 模块常量 ✅

### 2.4 测试盲区识别 (4 类)

| 盲区类型 | 检查结果 | 处置 |
|---------|---------|------|
| 1. 断言恒真式 | 无。前缀估计用 `atol=0, rtol=0` 精确比对; 多截断点 NaN 模式 `array_equal` + 数值 `atol=1e-12`; 手算对照为独立算式 (不调用生产方法); spy 断言 `max≤40 且 min<40` 双向约束 | 无需处置 |
| 2. 单文件检查盲区 | 单测只覆盖 `ARDecoupler` 隔离行为; `CompositeDecoupler` 组合路径与路由由集成截断不变式 (15 passed, 端到端 + 3 seeds) 覆盖; 诊断钩子由 `test_factor_decoupler` 契约测试覆盖 | 已被集成/契约测试覆盖 |
| 3. 设计约束无测试 | `warmup_obs=120` 默认值与 `_WARMUP_REFIT_STRIDE=10` 无直接断言: 默认值被 `test_ar_decoupler_hook_returns_known_phi` (T=240, 前 120 行拟合) 间接依赖; stride 语义被 spy 测试间接行使; 截断不变式对 stride 取值不敏感 (调研探针 6: stride 1/10/20 均 0/0), 数值属性能/质量权衡而非正确性不变式 | F-A3 记录, 无行动 |
| 4. 修正项无测试 | 步骤 8 修正以文档为主; 代码级修正 (`self._predict_one_step` 调用) 由手算对照用例覆盖 (缺失即 NameError/数值偏离); 容差修正如实反映在 29 passed | 已闭环 |

### 2.5 数值与登记一致性

| 数值 | 代码/测试输出 | CHANGELOG / ADR-040 / EXECUTION §7.2 | 结论 |
|------|-------------|--------------------------------------|------|
| Dynamic 截断 | 0/1800, 0 NaN, 0 | 三处一致 0/0/0 | ✅ |
| 顶层截断 + 路由 | 0/0/0; 3 组 (seed,kind) 一致 | 一致 | ✅ |
| 诊断矩阵 | 0 违反 / 9 满足 / 9 | ADR/EXECUTION 一致; **CHANGELOG 修复前值误写 `3/6/9`** (权威 `1/8/9`, 见 v3.3.5 节 L110 与 checklist G3-8) | ❌ → F-A1 已修复 |
| 输出偏移 | 2851/2852/2854/2855; max 2.1038–4.1873; mean 0.2287–0.3486 | 三处一致 (区间 2851–2855 / 2.1–4.2 / 0.23–0.35) | ✅ |
| NaN | AR 146/149→0; Dynamic 145/148→0 | 一致 | ✅ |
| `mean_ar1` | raw 0.7025 / 旧 0.0029 / 新 0.0302 (seed=42, 起点第 60 行) | 一致 | ✅ |
| AR 性能 | 6 次复测 2.10–5.23s, 单次离群 6.25s | 一致 (含离群披露; 中位 ≈2.24s vs 实算 2.25s, "≈" 口径内, F-A5 INFO) | ✅ |
| 管线性能 | 39.29s (基线 33.19s, +18.4%) | 一致 | ✅ |
| Red / Green / 集成 | 15/1 → 16; 10/2 → 15/0 | 三处一致 (步骤 8 预测 14/2 已在 EXECUTION/DESIGN/checklist/CONSISTENCY_REVIEW 回注更正) | ✅ |
| 回归计数 | decoupler 29 / 管线 13 / 开关 20 / 内生性 17 / fix3 7; 合并复跑 117 passed | 一致 (checklist G4-1 中间值已补注最终 117, F-A2) | ✅ |
| 版本 / 缓存 | 3.3.6 / `v2.2.4-cache`; `verify_fix3_manual` 5/5 | 一致 | ✅ |

## Phase 3: Fix Priority Matrix

| 级别 | 发现 | 状态 |
|------|------|------|
| P0 Blocker | 无 | — |
| P1 Critical | 无 | — |
| P2 Major | F-A1: CHANGELOG v3.3.6 诊断矩阵修复前值误写 `3/6/9`, 权威为 `1/8/9` (仅 Dynamic FAIL) | ✅ 已修复 (L34 更正并注明"仅 Dynamic FAIL") |
| P3 Minor | F-A2: checklist G4-1 记录的 110 passed 为版本 bump 前 6 套件运行; 最终合并复跑 (含 fix3) = 117 passed (29.57s) | ✅ 已修复 (G4-1 补注) |
| P3 Minor | F-A3: `warmup_obs=120` 默认值与 `_WARMUP_REFIT_STRIDE=10` 无直接断言 (间接覆盖; stride 非正确性不变式) | ⏸ 记录性遗留, 无行动 |
| P3 Minor | F-A4: `test_missing_results_column_not_blanket_identity` 的"已解耦"断言为不等式 (弱), 由多截断不变式 + 手算对照补偿成网 | ⏸ 记录性遗留, 无行动 |
| INFO | F-A5: AR 计时中位 ≈2.24s vs 6 值实算 2.25s; 单机负载敏感 (调研脚注已声明量级口径) | ⏸ 不修 |

**Tier 1 (本轮)**: F-A1 / F-A2 已修复。**Tier 2/3**: F-A3 / F-A4 / F-A5 记录性, 无行动项。

## Phase 4: Fix Baseline + Tracking

| 编号 | 严重度 | 描述 | 状态 | 修复验证 |
|------|--------|------|------|---------|
| F-A1 | P2 | CHANGELOG 诊断矩阵修复前值 `3/6/9` → `1/8/9` | ✅ 已修复 | L34 更正; 与 v3.3.5 节 L110 / checklist G3-8 对齐 |
| F-A2 | P3 | checklist G4-1 补注最终合并复跑 117 passed | ✅ 已修复 | 与 EXECUTION §7.2 / ADR-040 回归计数一致 |
| F-A3 | P3 | 默认参数/常量无直接断言 | ⏸ 记录 | 间接覆盖成立; stride 正确性不变式不依赖取值 |
| F-A4 | P3 | 单点不等式断言偏弱 | ⏸ 记录 | 多层测试网 (不变式 + 手算 + spy) 补偿 |
| F-A5 | INFO | 计时中位近似值 | ⏸ 记录 | 调研脚注已声明计时口径 |

**回归验证**: F-A1/F-A2 均为文档行编辑, 不触代码; 修复后最终状态 = 步骤 9 收尾全量靶向 **117 passed / 0 failed (29.57s)**, 零回归。

## 评分 (v3.3.6)

| 维度 | 结论 |
|------|------|
| E1-E7 代码 vs 实施文档 | 7/7 对齐 |
| ADR 不变式 / 跨模块契约 | 6/6 通过 |
| 接口签名 | 一致, 无漂移 |
| 测试盲区 | 4 类无阻塞项 (2 项记录性说明) |
| 数值一致性 | 10/11 组一致; 1 组 (诊断矩阵修复前值) 已更正闭环 |
| Checklist Gate 0-8 | 全部 "必须" 项通过 (G1-3 预测偏差 15/1 vs 14/2 已回注闭环) |
| 回归 | 117 passed / 0 xfailed / 0 failed, 零回归 |
| **总评** | **PASS** |

## 遗留与后续 (v3.3.6)

| 项 | 归属 |
|----|------|
| `OptimizedARDecoupler` / `TemporalDecoupler` 同类缺陷 | 非生产路径, 独立任务 |
| `PL-08-candidate` (`_fit_ar` AIC 跨阶数不可比, statsmodels `hold_back` 语义) | 独立缺陷, 未登记 xfail (无生产触发路径) |
| 指纹路由分类逻辑 | 未改动; 因果性由 3-seed 测试守卫 |
| 冻结模型对非平稳因子失配 | 未做专项回测; `warmup_obs` 由 ValueError + 文档约束 |
| 非因果标准化方法 (`robust`/`min_max`/`quantile`) | 无生产路径使用, 维持既有登记 |

## 审计签署 (v3.3.6)

| 项 | 值 |
|----|-----|
| 审计结论 | **PASS** (无 P0/P1; 1 项 P2 + 1 项 P3 文档项已修复闭环; 3 项记录性遗留) |
| 阻塞交付 | 无 |
| 交付建议 | 可提交; 单原子 commit (代码 + 测试 + 版本 + 文档); 提交前 `git diff --cached --check` |
