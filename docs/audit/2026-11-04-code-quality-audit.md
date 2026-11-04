# 2026-11-04 代码质量审计 — v3.3.5 PL-06 Mixed 缩尾因果性修复

**审计版本**: v1.0
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
