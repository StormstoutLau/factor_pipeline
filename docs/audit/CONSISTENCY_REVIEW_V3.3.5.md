# CONSISTENCY REVIEW V3.3.5 — PL-06 Mixed 缩尾因果性修复

**版本**: v1.0
**日期**: 2026-11-04
**review 时机**: spec 步骤 8 (checklist 完成后, TDD 实现前)
**review 对象**:
- 调研: [PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md](../analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_RESEARCH.md) v1.0
- 设计: [PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md](../analysis/PL06_MIXED_WINSORIZE_LOOKAHEAD_DESIGN.md) v1.1
- 实施: [EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](../EXECUTION_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) v1.2
- 验收: [CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md](CHECKLIST_V3.3.5_PL06_MIXED_WINSORIZE_CAUSALITY.md) v1.0
- 决策: ADR-039 模板 (实施文档 §5.3) + `DECISIONS.md` 占用表
**结论**: **通过** — 无 CRITICAL; 2 项 MAJOR + 4 项 MINOR 已修复; 可进入步骤 9 (TDD)。

---

## §0 范围与方法

按 WORKFLOW_METHODOLOGY v1.3 §13.3 工件 C, 检查四类一致性 + 决策对齐:

1. 引用一致性: 学术/工业引用的结论与证据等级。
2. 接口签名一致性: 设计声明 ↔ 实施声明 ↔ 源代码。
3. 验收标准一致性: 实施 §4/§7 ↔ checklist Gate。
4. 决策记录对齐: D1-D8 ↔ ADR-039 ↔ 占用表。
5. 数值一致性: 同一实测值在各文档中的表述。

方法: 逐项读取四份文档原文 + 对照源代码/`pyproject.toml`/`DECISIONS.md`, 不做记忆推断。

---

## §1 引用一致性

| 引用 | 调研 | 设计 | 实施 (ADR-039) | checklist | 状态 |
|------|------|------|---------------|----------|------|
| Bali, Engle & Murray (2016) | §4 A; "cross-sectional distributions" 逐字引文标 U | §3.4 B (未逐字核验) | A (winsorization vs truncation); 逐字引文 U | — | ✅ 一致 |
| Hampel (1974) / Rousseeuw & Croux (1993) | §4 A (MAD/稳健尺度) | §3.4 A | A | — | ✅ 一致 |
| MSCI FaCS (Bonne et al., 2018) | §4 A (稳健均值 ± 3 稳健σ) | §3.4 A | A | — | ✅ 一致 |
| Banz & Breen (1986) / Kaufman et al. (2012) / Kapoor & Narayanan (2023) | §4 A | §3.4 A | A | — | ✅ 一致 |
| Arnott, Harvey & Markowitz (2019) | §4 A | §3.4 A | A | — | ✅ 一致 |
| Leeb & Pötscher (2006/2008) | §2.2 + §8 参考文献 #10/#11 (A/B) | §2.2 只述原则, 未点名 | A/B | — | ✅ 可追溯 (研究 §8 #10/#11) |
| ADR-027 (固定方法) | §4 C | §0 D4 / §1.2 | ADR 备选段引用 | — | ✅ 一致 |
| ADR-037 (逐日截面) | §4 C / §5.1 | §1.2 / §3.4 | ADR 备选段引用 | — | ✅ 一致 |

**说明**: 调研 §4 已明确"未读原文不作为强论据"; 设计 §3.4 与实施 ADR 均沿用该等级, 无升格。

---

## §2 接口签名一致性

| 接口 | 设计 (§2.1 / §3.2) | 实施 (§3.7) | 源代码 | 状态 |
|------|-------------------|-------------|--------|------|
| `_apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame` | 同 | 同 | `pipelines_v2.py` L1180 | ✅ |
| `MixedFactorPipeline.fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline'` | 未列签名, 只述顺序 | 同源码 | L1088 | ✅ |
| `MixedFactorPipeline.transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame` | 未列签名 | 同源码 | L1142 | ✅ |
| `MixedFactorPipeline.__init__(..., mixed_winsor_sigma: float = 3.0, ...)` | §3.2.1 "继续由构造函数传入" | 完整签名 | L1070-L1074 | ✅ |
| `_compute_winsorize_params(self, X: pd.DataFrame) -> Dict` | 删除 | 删除 | L1164-L1178 | ✅ |
| `PipelineV2Config.mixed_winsor_sigma: float = 3.0` | 保留 | 保留 | L709 | ✅ |
| `PipelineV2ConfigUnified.mixed_winsor_sigma` / `transform_aggressiveness` | 保留 | 保留 | `config_v2.py` L417-L424 | ✅ |
| `optimizer.DEFAULT_SEARCH_SPACE['mixed_winsor_sigma']` | 保留 | 保留 | `optimizer.py` L47-L56 | ✅ (行号已在本次修正) |

**结论**: 无签名漂移; 设计未显式写出的 3 个签名由实施 §3.7 补齐并以源码为准。

---

## §3 验收标准一致性

| 验收项 | 实施 (§4 / §7.2) | checklist | 状态 |
|--------|-----------------|-----------|------|
| 新增单测 11 例全绿 | §4.1 / §7.2 | Gate 2 (G2-1…G2-12) | ✅ |
| Red = 10 failed / 1 passed | §4.1 / §6.2 步 1 | Gate 1 (G1-4/G1-5) | ✅ |
| 配置迁移 12 passed | §4.4 / §7.2 | Gate 4 (G4-2) | ✅ |
| 集成 10 passed / 2 xfailed | §4.3 / §7.2 | Gate 3 (G3-4) | ✅ |
| Mixed 截断不变式 0 格 / 0 | §7.2 | Gate 3 (G3-3) | ✅ |
| 输出变更 561/3000, max 1.0446 | §7.2 | Gate 8 / §1 (由诊断复测) | ✅ |
| 性能 ≈0.200s, 不慢于 0.281s | §4.6 / §7.2 | Gate 5 (G5-1) | ✅ |
| 版本统一 7 passed | §5.1 / §7.2 | Gate 6 (G6-7) | ✅ |
| 接口签名 / 依赖 / 低效操作 | §3.7-3.9 / §7.2 | Gate 8 / G8 | ✅ |

**补记**: checklist 的 Gate 0 期望值 (9/3、33、12、7、0.281s) 与实施 §1.2 完全一致。

---

## §4 决策记录对齐

| 决策 | 设计 | 实施 | checklist / ADR | 状态 |
|------|------|------|----------------|------|
| D1 逐日截面 (`axis=1`) | §0 / §3.2 | §3.2 | Gate 2 / ADR 决策 1 | ✅ |
| D2 `fit` no-op | §0 / §3.1.1 | §3.1 | Gate 2 (G2-1) / ADR 决策 2 | ✅ |
| D3 A 选定, B 备选不实施 | §3.4 | §0 不实施 / ADR 备选 | Gate 0-8 均不含 B | ✅ |
| D4 无 pre-test | §0 / §2.2 | §3.5 | — / ADR 决策 4 | ✅ |
| D5 步骤顺序不变 | §0 | §3.1 (仅改 Step 2 实现) | — / ADR 决策 5 | ✅ |
| D6 v3.3.5 / `v2.2.3-cache` / ADR-039 | §6.1 | §5.1-5.3 | Gate 6 / Gate 7 | ✅ |
| D7 新增单测 + 摘 xfail | §4 | §4.1 / §4.3 | Gate 1 / Gate 3 | ✅ |
| D8 不加选择器, 不删配置 | §0 / §1.2 | §3.6 | Gate 6 (config 不变) | ✅ |
| ADR 占用表 | "ADR-039 占用, ADR-040 起未占用" | §5.3 模板 | Gate 7 (G7-2) | ✅ |

---

## §5 数值一致性

| 数值 | 调研 | 设计 | 实施 | checklist | 状态 |
|------|------|------|------|-----------|------|
| PL-06 基线 | 257/1800, 6.984124662957469e-01, 31/60 行, 首日 2020-01-31 | 257/1800, 6.98e-01 | 同调研 | "≈6.98e-01" | ✅ |
| 基线 Spearman | 中位 0.999555 / 最小 0.984872 | — | — | — | ✅ (仅调研陈述) |
| A 触发率 | 77/3000 (2.57%), 73/100 行 | 77/3000 (2.57%) | 77/3000, 2.57% | — | ✅ |
| A 输出差异 | 561/3000, 63/100 行, max 1.0446 | 561/3000, 63/100 行, 1.0446 | 561/3000, 1.0446 | — | ✅ |
| A Spearman | 0.999110 / 0.942603 | — | 0.999110 / 0.942603 | — | ✅ |
| A ties | 4 | 4 | — (ADR 未列 ties) | — | ✅ (不矛盾) |
| B 备选数值 | 200/3000, 612/3000, 1.2203, 0.998665/0.918131, ties 0 | 同 | 不实施 | 不适用 | ✅ |
| 当前触发率 | 61/3000 (2.03%) | — | 61/3000 (2.03%) | — | ✅ |
| 性能 (探针) | 0.268 / 0.512 | 0.268 / 0.512 | 标注为调研口径 | — | ✅ |
| 性能 (真实方法) | — | 0.281 / 0.200 (转引实施 §1.2) | 0.281 / 0.200 | 0.281 门限 | ✅ |
| 小截面 | N≤10 no-op; N=11 起可触发 | 同 | 同 | Gate 2 (G2-9/G2-11) | ✅ |
| 版本 / 缓存 | 建议 v3.3.5 / `v2.2.3-cache` | 锁定 | 锁定 | Gate 6 | ✅ |

---

## §6 不一致项与修复

| # | 级别 | 位置 | 问题 | 修复 |
|---|------|------|------|------|
| F1 | **MAJOR** | 实施 §5.3 ADR-039 模板 | 状态写 "已实施", 但实施尚未开始, 与步骤 8 的时点矛盾 | 改为 "待实施 (v3.3.5 实施完成后改为 '已实施')"; 并在 §5.3 前加"待写入模板"说明 |
| F2 | **MAJOR** | 实施 §5.2 / checklist G6-9 | 要求把 test_fix3 L83 的归因 "从 PL-02 改为 PL-06", 会抹掉 v2.2.1→v2.2.2 的历史 bump 记录 | 改为"保留 PL-02 历史, 追加 PL-06 的 v2.2.2→v2.2.3 bump" |
| F3 | MINOR | 设计 §2.1 | `optimizer.DEFAULT_SEARCH_SPACE` 行号写作 L45-L54, 实际 L47-L56 | 已更正行号与链接 |
| F4 | MINOR | 设计 §4.1 测试数据策略 | 规定"随机面板仅用于截断不变式", 与实施 §4.1 在性质类测试中使用合成面板不一致 | 设计改为: 边界语义必须手算小面板; 性质类允许合成面板但须独立路径/不变量断言 |
| F5 | MINOR | 调研 §6.2 第 2 项 | "winsorizer 关闭时 identity" 易被误读为端到端输出等于输入 | 改为"步骤级 identity (`outlier` == `imputation`; 端到端仍执行后续步骤)" |
| F6 | MINOR | 调研 §6.2 第 5 项 | 性能仅写探针口径 0.268/0.512, 未标注真实方法口径 | 追加"真实方法口径 0.281s → 0.200s" |

**修复验证**: 上述 6 项已直接修改源文档; 修改均未改变任何数值结论或接口契约。

---

## §7 结论与放行

| 维度 | 结果 |
|------|------|
| 引用一致性 | 通过 (无等级升格/无虚构引用) |
| 接口签名一致性 | 通过 (8/8; 行号问题已修) |
| 验收标准一致性 | 通过 (9/9 映射) |
| 决策对齐 | 通过 (D1-D8 + ADR 占用表) |
| 数值一致性 | 通过 (12 组; 无跨文档漂移) |
| 发现不一致 | 6 项 (2 MAJOR + 4 MINOR), 全部已修复 |
| 阻塞项 | 无 |

**放行**: 可进入 spec 步骤 9 (TDD 实现)。实施时以本报告修订后的四份文档为准; 步骤 10 审计对照 checklist 逐项确认。
