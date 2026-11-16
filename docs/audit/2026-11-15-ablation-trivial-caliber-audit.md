# 2026-11-15 代码质量审计 — v3.4.8 消融臂 trivial 判定口径

**审计版本**: v1.0
**日期**: 2026-11-15
**审计对象**: v3.4.8 P2-1 修复 (`run_l4_oat` 无市值退化臂的 trivial 判定)
**审计基准**: [RESEARCH v1.1](../research/RESEARCH_ABLATION_TRIVIAL_CALIBER.md) /
[DESIGN v1.1](../private/DESIGN_ABLATION_TRIVIAL_CALIBER.md) /
[EXECUTION v1.1](../EXECUTION_V3.4.8_ABLATION_TRIVIAL_CALIBER.md) /
[CHECKLIST v1.0](CHECKLIST_V3.4.8.md) / [CONSISTENCY REVIEW v1.0](CONSISTENCY_REVIEW_V3.4.8.md)
**审计方式**: 主会话逐维审计 + TDD 实测 (Red 5 failed → Green 112 passed; T4 复审后追加 → 113 passed)
**总评**: **PASS**

---

## Phase 1: Spec Inventory

| 工件 | 内容 | 审查维度 |
|------|------|---------|
| RESEARCH v1.1 §2 | BH (1995) `m` 定义 / Bourgon et al. (2010) 独立过滤 | 引用可核实性 |
| RESEARCH v1.1 §3 | F1-F9 代码事实 (行号级) | 事实准确性 |
| DESIGN v1.1 §2 | G1-G6 不变式 | 行为契约 |
| DESIGN v1.1 §4 | 实跑口径判定 / 告警文案 / 测试点 E1-E5 | 设计落地 |
| DESIGN v1.1 §5 | N1-N5 不做的事 | 范围控制 |
| EXECUTION v1.1 §3 | 代码变更精确定位与片段 | 逐行落地 |
| EXECUTION v1.1 §4 | 3 例更新 + 3 例新增 / Red-Green 预期 | 测试规格 |

---

## Phase 2: Multi-Dimensional Audit

### 2.1 E 任务 vs 代码对齐

| E 任务 | 实施文档声明 | 代码实测 | 结论 |
|--------|-------------|---------|------|
| E1 trivial 实跑口径 + 告警 | [EXECUTION §3.1-§3.2](../EXECUTION_V3.4.8_ABLATION_TRIVIAL_CALIBER.md) | [ablation_runner.py L1098-L1110](../backtest/ablation_runner.py#L1098-L1110) 告警; L1137-L1145 实跑口径判定 | ✅ |
| E2 更新 3 个既有断言 | 2→3 / 6→5 / 退化臂 trivial | [test_ablation_knob_wiring.py L137-L153](../tests/test_backtest/test_ablation_knob_wiring.py#L137-L153); [test_ablation_runner.py L1327-L1350](../tests/test_backtest/test_ablation_runner.py#L1327-L1350); [test_ablation_mktcap_alignment.py L186-L199](../tests/test_backtest/test_ablation_mktcap_alignment.py#L186-L199) | ✅ |
| E3 新增 T1-T4 | 无市值集合 / 告警 1 条 / 有市值不变 / 外部 B3 提示 | [test_ablation_knob_wiring.py L156-L238](../tests/test_backtest/test_ablation_knob_wiring.py#L156-L238) | ✅ |
| E4 版本六锚点 | 6 处 = 3.4.8 | 版本测试 7 passed + 手工 6/6 | ✅ |
| E5 文档同步 | CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | 均已更新 | ✅ |

### 2.2 不变式与兼容性

| 契约 | 验证 | 结论 |
|------|------|------|
| G1 有市值行为逐位不变 | T3 (2 trivial 集合) + `test_run_l4_with_market_cap_switches_default` | ✅ |
| G2 无市值 9 臂 / 3 trivial / 5 非平凡 | T1 + `test_l4_trivial_count` + `test_l4_oat_marks_trivial_configs` | ✅ |
| G3 生产管线零改动 | `git diff --stat` 无 `pipelines_v2.py` | ✅ |
| G4 臂名 / `config.neutralization` 不变 | 既有 E1/E2 断言未修改仍通过 | ✅ |
| G5 退告警恰 1 条 | T2 (`caplog` 精确匹配 1 条) | ✅ |
| G6 `_is_trivial` 仅影响 BH 分母与显著性 | `compare_all` 逻辑未改动; 既有 BH 用例通过 | ✅ |

### 2.3 接口签名核对

- `run_l4_oat(self, factor_data, fwd_returns, industry_data=None, market_cap_data=None, b3_full_result=None)` — 未变 ✅
- `AblationConfig` 字段集合 — 未变 ✅
- `generate_report` 列结构 — 未变 ✅

### 2.4 测试盲区识别

| 盲区类型 | 检查结果 | 处置 |
|---------|---------|------|
| 1. 断言恒真式 | 无。T1/T3 为集合相等; T2 为计数相等; 旧断言均改数值 | 无需处置 |
| 2. 单文件检查盲区 | 告警与判定同在 `run_l4_oat`; 由 T1/T2/T3 三例覆盖两个分支 | 已覆盖 |
| 3. 设计约束无测试 | 「告警在循环外只调用一次」由 T2 计数锁定 | 已覆盖 |
| 4. 修正项无测试 | G4 (臂名不变) 由既有 E1/E2 断言持续守护 | 已覆盖 |

### 2.5 数值一致性

| 数值 | 实测 | 文档 | 结论 |
|------|------|------|------|
| Red | 5 failed / 107 passed | EXECUTION §4.3 = 5 失败 (3 既有 + T1 + T2; T3 预先通过) | ✅ |
| Green (3 文件) | 112 passed (T1-T3 阶段); T4 复审后追加 → **113 passed** | — | ✅ |
| 版本统一 | 7 passed + 手工 6/6 | EXECUTION A7 | ✅ |
| 定向回归 | 580 passed / 8 skipped (1338.27s) | CHECKLIST C1 ≥ 576 | ✅ |
| 全量回归 | 1728 passed / 15 skipped / 0 failed (2143.86s) | CHECKLIST C2 ≥ 1723 | ✅ |

### 2.6 幻觉验证 (L1-L4)

| 级别 | 检查 | 结果 |
|------|------|------|
| L1 文件 | 调研/设计/实施/审计引用的文件全部存在 | ✅ |
| L2 行号 | `ablation_runner.py` L1098-1110 / L1137-1145 / L1217-1225、`pipelines_v2.py` L1431-1440、3 个测试文件行号均一致 | ✅ |
| L3 关键词 | `market_cap_available` / `effective_option` / `退化为仅行业` 均真实存在 | ✅ |
| L4 结构 | 告警在 B3 之前、判定在内层循环, 与 DESIGN §4.1 图示一致 | ✅ |

---

## Phase 3: 审计发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P3 | DESIGN 原文「修改与新增用例数」与落地 (4 例) 表述不一致 | ✅ CONSISTENCY_REVIEW §1/§3 已说明合并关系 |
| 2 | P3 | DESIGN G1「逐位一致」验证方式初稿不具体 | ✅ 步骤 4 review 已修正为「既有市值转发 + 新增 E4」 |
| 3 | P3 | EXECUTION 初稿拟新建测试文件, 会复制 4 个 helper | ✅ 步骤 6 review 改为同文件新类 |

**P0/P1**: 无。

---

## Phase 4: 结论

**PASS**。E1-E5 全部落地; 有市值路径行为不变; 无市值路径 trivial 口径与实跑一致;
生产管线零改动; Red→Green 可复现; 版本六锚点统一。

**残余风险**:
- 无市值场景 BH-FDR 分母 6→5, 其余臂 q 值可能变小 — 属口径修正 (已在 CHANGELOG 兼容性小节说明);
- `docs/private/DESIGN_*.md` 不入库 (既有 gitignore 惯例)。

---

## Phase 5: 独立复审 (2026-11-16)

**范围**: 全部未提交 v3.4.8 变更 (代码 / 测试 / 版本锚点)。
**结论**: 1 个 Minor, 无 critical/major; 已按「方案 C」处置。

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | Minor | 退化告警硬断言「与 B3 同口径」: `b3_full_result` 短路分支下 B3 由调用方构造, runner 无法校验口径 (v3.4.6 O3)。若外部 B3 按市值口径计算, 该臂相对 B3 存在真实差异, `trivial` 标记会把该比较排除出 BH-FDR 分母 | ✅ 文案改为「与无市值默认口径一致」; 新增「外部 B3 口径未校验」提示; 新增 T4 覆盖; EXECUTION §3.2 同步 (判定逻辑不变, 主路径仍正确) |

**复审后实测**: 3 个消融测试文件 **113 passed** (6.05s); 全量回归 **1728 passed / 15 skipped / 0 failed** (2143.86s)。
