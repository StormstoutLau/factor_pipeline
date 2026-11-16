# 2026-11-16 代码质量审计 — v3.4.9 L1/L2 消融臂 trivial 判定口径

**审计版本**: v1.0
**日期**: 2026-11-16
**审计对象**: v3.4.9 L1/L2 口径清扫 (`run_l1` / `run_l2` 的 trivial 判定与合并覆盖)
**审计基准**: [RESEARCH v1.0](../research/RESEARCH_L1L2_TRIVIAL_CALIBER.md) /
[DESIGN v1.0](../private/DESIGN_L1L2_TRIVIAL_CALIBER.md) /
[EXECUTION v1.0](../EXECUTION_V3.4.9_L1L2_TRIVIAL_CALIBER.md) /
[CHECKLIST v1.0](CHECKLIST_V3.4.9.md) / [CONSISTENCY REVIEW v1.0](CONSISTENCY_REVIEW_V3.4.9.md)
**审计方式**: 主会话逐维审计 + TDD 实测 (Red 6 failed / 1 passed → Green 7 passed)
**总评**: **PASS**

---

## Phase 1: Spec Inventory

| 工件 | 内容 | 审查维度 |
|------|------|---------|
| RESEARCH v1.0 §3 | F1-F14 代码事实 (行号级) | 事实准确性 |
| RESEARCH v1.0 §4 | L1/L2 退化臂清单 + 非默认 base 边界 | 推导完整性 |
| DESIGN v1.0 §2 | G1-G7 不变式 | 行为契约 |
| DESIGN v1.0 §3-§4 | 判定式 / 告警 / 外部提示 | 设计落地 |
| DESIGN v1.0 §6 | N1-N6 不做的事 | 范围控制 |
| EXECUTION v1.0 §3 | 代码变更精确定位与片段 | 逐行落地 |
| EXECUTION v1.0 §4 | E1-E7 测试规格 | 测试规格 |

---

## Phase 2: Multi-Dimensional Audit

### 2.1 E 任务 vs 代码对齐

| E 任务 | 实施文档声明 | 代码实测 | 结论 |
|--------|-------------|---------|------|
| E1 实跑口径判定 | [EXECUTION §3.2-§3.3](../EXECUTION_V3.4.9_L1L2_TRIVIAL_CALIBER.md) | [ablation_runner.py L924-L981](../backtest/ablation_runner.py#L924-L981) | ✅ |
| E2 合并覆盖 | EXECUTION §3.2 | [ablation_runner.py L963](../backtest/ablation_runner.py#L963) `{**base_modules, module: False}` | ✅ |
| E3 退化告警一次 | EXECUTION §3.2 | [L936-L939](../backtest/ablation_runner.py#L936-L939) 循环外单次 | ✅ |
| E4 外部 B3 提示 | EXECUTION §3.2/§3.3 | [L940-L944](../backtest/ablation_runner.py#L940-L944) / [L1071-L1075](../backtest/ablation_runner.py#L1071-L1075) | ✅ |
| E5 辅助函数 | EXECUTION §3.1 | [L400-L408](../backtest/ablation_runner.py#L400-L408) | ✅ |
| E6 版本六锚点 | EXECUTION §2 | 版本测试 7 passed + 手工 6/6 | ✅ |
| E7 文档同步 | EXECUTION §7 | 见 Phase 4 | ✅ |

### 2.2 不变式与兼容性

| 契约 | 验证 | 结论 |
|------|------|------|
| G1 默认 base 输出零变更 | E1/E2 只新增 `_is_trivial`; 臂字段断言 (E5 对照) | ✅ |
| G2 L1 分母 5→4 / L2 2→1 | E1 / E2 | ✅ |
| G3 base 启用正交化时非平凡 | E4 | ✅ |
| G4 合并覆盖不重启 base 已关模块 | E5 (`scaler` 臂保留 `imputer: False`) | ✅ |
| G5 臂数 / 臂名不变 | 既有 `test_run_l1_returns_6_results` / `test_run_l2_returns_2_results` 未改仍通过 | ✅ |
| G6 `compare_all` / 生产管线零改动 | `git diff --stat` 不含 `multiple_testing.py` / `pipelines_v2.py` | ✅ |
| G7 外部 B3 只提示不改判定 | E6 | ✅ |

### 2.3 接口签名核对

- `run_l1(self, factor_data, fwd_returns, industry_data=None, market_cap_data=None, b3_full_result=None)` — 未变 ✅
- `run_l2(...)` 同上 — 未变 ✅
- `AblationConfig` 字段集合 — 未变 ✅
- `generate_report` 列结构 — 未变 ✅

### 2.4 测试盲区识别

| 盲区类型 | 检查结果 | 处置 |
|---------|---------|------|
| 1. 断言恒真式 | 无。E1/E2 为集合相等; E3/E5 为计数相等; E5 为 dict 相等 | 无需处置 |
| 2. 单文件检查盲区 | 判定与告警同在 `run_l1`; E1/E3/E5 覆盖两个退化来源 (模块 / 正交化) | 已覆盖 |
| 3. 设计约束无测试 | 「告警在循环外只调用一次」由 E3/E5 计数锁定; 「合并覆盖」由 E5 dict 锁定 | 已覆盖 |
| 4. 修正项无测试 | G5 (臂数/臂名) 由既有用例守护; G6 (生产零改动) 由 `git diff` 与全量回归守护 | 已覆盖 |

### 2.5 数值一致性

| 数值 | 实测 | 文档 | 结论 |
|------|------|------|------|
| Red | 6 failed / 1 passed | EXECUTION §4 (E4 为防回归, 预先通过) | ✅ |
| Green (新类) | 7 passed (0.34s) | EXECUTION §4 | ✅ |
| 4 个消融文件 | 133 passed (11.57s) | CHANGELOG 实测矩阵 | ✅ |
| 版本统一 | 7 passed + 手工 6/6 | EXECUTION A7 | ✅ |
| 定向回归 | `tests/test_backtest` **588 passed / 8 skipped** (837.23s); 4 个消融文件 133 passed | CHECKLIST C1 | ✅ |
| 全量回归 | **1735 passed / 15 skipped / 0 failed** (1559.39s) | CHECKLIST C2 | ✅ |

### 2.6 幻觉验证 (L1-L4)

| 级别 | 检查 | 结果 |
|------|------|------|
| L1 文件 | 调研/设计/实施/审计引用的文件全部存在 | ✅ |
| L2 行号 | `ablation_runner.py` L400-408 / L895-985 / L1041-1090、`pipelines_v2.py` L492-494 / L520-522 / L801-804 / L1088-1094、`config_v2.py` L258 | ✅ |
| L3 关键词 | `_base_module_switches` / `_base_ortho_active` / `与 B3 同口径` / `未校验` 均真实存在 | ✅ |
| L4 结构 | 告警在 B3 参照之前、判定在循环内, 与 DESIGN §3-§4 一致 | ✅ |

---

## Phase 3: 审计发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P3 | E1 首稿把 B3 参照计入「非平凡」分母 (6-1≠4), 测试自身算术错误 | ✅ 步骤 9 已改为按 `layer == 'L1'` 过滤后计数 |
| 2 | P3 | RESEARCH 首稿称 `Wiring` 可标 `default`, 越界扩展字段语义 | ✅ 步骤 2 review 已删除, 报告不新增列 |
| 3 | P3 | DESIGN E5 首稿同时关闭 `imputer`/`scaler` 却断言 `scaler` 臂非平凡, 与判定式矛盾 | ✅ 步骤 4 review 已改为仅关闭 `imputer` |

**P0/P1**: 无。

---

## Phase 4: 结论

**PASS**。E1-E7 全部落地; 默认 `base_config` 输出零变更;
L1/L2 的 BH-FDR 分母与实跑口径一致; 非默认 `module_enabled` 的归因污染已修复;
生产管线与 `compare_all` 零改动; Red→Green 可复现; 版本六锚点统一 3.4.9。

**残余风险**:
- L1 分母 5→4 / L2 2→1, 其余臂 q 值可能变小 — 属口径修正 (CHANGELOG 兼容性已说明);
- 非默认 `module_enabled` 的臂配置语义变更 (整体替换 → 合并覆盖), 输出可能变化 — 已在 CHANGELOG 与 docstring 标注;
- `docs/private/DESIGN_*.md` 不入库 (既有 gitignore 惯例)。

**发版实测**: 定向 `tests/test_backtest` **588 passed / 8 skipped** (837.23s);
全量 **1735 passed / 15 skipped / 0 failed** (1559.39s)。

---

## Phase 6: 独立异构复审 (2026-11-16)

**范围**: v3.4.9 全部未提交变更 (代码 / 测试 / 版本锚点)。
**方式**: TRAE-code-review 流程 + 2 个独立验证代理交叉定位, 主会话基于一手证据判定
(候选 6 条: 3 存在 / 3 证伪)。
**结论**: 3 个 Minor, 无 critical/major; 用户批准后全部处置。

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | Minor | `run_l1_decoupler` off 臂 `module_enabled={'decoupler': False}` 整体替换, 未合并 base 开关; 非默认 base 下与参照臂 (继承 base) 除 decoupler 外口径不一致 → AR 归因污染 (同族残留, 默认 base 不受影响) | ✅ off 臂改为 `{**_base_module_switches(base_config), 'decoupler': False}` (R-1), docstring 同步 |
| 2 | Minor | `L2_unified` 硬编码 `_is_trivial=True` 的前提 (full/unified 均注入 unified) 与硬编码之间无显式关联标注 | ✅ 复核确认 `test_run_pipeline_injects_mode` 已分别断言两分支注入值, 守卫实际存在 (复审初判降级); 补关联注释明确该断言同时守护 trivial 前提 |
| 3 | Minor | `test_fix3_version_unification.py` L12 历史叙述「统一目标 (v3.4.8, 2026-11-15)」被 replace_all 误改为 (v3.4.9, 2026-11-15), 历史失真 | ✅ 改为「v3.4.8 首次统一, 2026-11-15; 锚点随版本演进, 当前 3.4.9」 |

**证伪 (未列入)**: ① 外部 B3 只提示不校验 — v3.4.6 O3 既有责任划分, 非缺陷;
② `OrthogonalizationConfig` 非 frozen pydantic, `enabled=False` 赋值总生效,
try/except 静默兜底无实际风险; ③ 双 WARNING 并存对象不同 (内部判定 vs 外部不确定性), 语义成立。

**复审后实测**: 4 个消融文件 + 版本统一 **140 passed** (13.47s)。
