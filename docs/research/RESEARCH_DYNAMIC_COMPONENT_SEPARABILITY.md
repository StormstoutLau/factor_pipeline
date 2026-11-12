# RESEARCH DYNAMIC COMPONENT SEPARABILITY

> **版本**: v1.1 (2026-11-12)
> **任务**: v3.4.3 — O2 Dynamic 组件解耦修复 (ADR-045)
> **调研工具**: mcp_paper-search (Semantic Scholar / CrossRef) + mcp_english-search + WebFetch
> **范围**: Dynamic 管道"中性化"与"AR 解耦"两个组件的统计独立性、消融隔离原则、组合器工程契约

---

## §1 调研问题清单

- **Q1**: 截面中性化 (行业/市值) 与 AR 残差化 (时序新息) 是否是两个可以独立开关的统计操作?
- **Q2**: 消融实验 (ablation study) 对"一次只关闭一个组件"有何要求? 组件绑定会带来什么后果?
- **Q3**: 组合器 (composite) 的工程接口应如何表达"可选子组件", 同时保持向后兼容?
- **Q4**: 现有代码事实是否支持"`module_enabled={'neutralizer': False}` 同时关闭 AR 解耦"这一判断?
- **Q5**: 修复的兼容性边界是什么 (哪些行为应逐位不变, 哪些语义必须改变)?

---

## §2 学术文献调研

| 引用 | MCP 工具 | paper_id / DOI | 关键结论 | 状态 |
|------|---------|---------------|---------|------|
| Fama & MacBeth (1973), *Risk, Return, and Equilibrium: Empirical Tests*, JPE 81(3):607-636 | search_crossref | DOI: 10.1086/260061 | 横截面回归框架: 行业/市值等暴露作为回归协变量被剥离, 属于**截面**操作 | ✅ VERIFIED |
| Grinold & Kahn (2000), *Active Portfolio Management*, 2nd ed. | search_crossref | 书目见 DOI: 10.1093/rfs/13.4.1153 (书评) / 10.2307/2329407 (1st ed. 书评) | 风险模型将行业、市值等暴露视为独立风险因子; 中性化 = 剥离暴露, 不涉及时序动态 | ✅ 书目 VERIFIED (正文页码未核实) |
| Hamilton (1994), *Time Series Analysis*, Princeton University Press | search_crossref | DOI: 10.1515/9780691218632 | AR 模型对**时序自相关**建模, 残差 (新息) 是时间维操作, 与截面回归相互独立 | ✅ VERIFIED |
| Meyes, Lu, Waubert de Puiseau & Meisen (2019), *Ablation Studies in Artificial Neural Networks*, arXiv:1901.08644 | WebFetch (arXiv abs) | DOI: 10.48550/arXiv.1901.08644 | 消融通过**移除单个组件**考察其贡献; 组件边界不清时无法归因 | ✅ VERIFIED |

**Q1 结论**: 中性化在截面维 (每个交易日的行业/市值回归), AR 解耦在时间维 (每个股票序列的滞后项拟合)。二者数学上正交, 可以独立启用/禁用。

**Q2 结论**: 消融的因果解释依赖"只改变目标组件"。若关闭 A 同时连带关闭 B, 观测到的差异无法归因给 A —— 这正是 O2 的缺陷。

---

## §3 工程实践调研

| 声明 | 核实方式 | 证据 | 状态 |
|------|---------|------|------|
| 组合器应由显式步骤/子组件构成, 每个步骤独立实现 `fit`/`transform` | WebFetch scikit-learn 用户指南 §8.1 | <https://scikit-learn.org/stable/modules/compose.html>: "All estimators in a pipeline, except the last one, must be transformers" | ✅ VERIFIED |
| 新增可选构造参数并给默认值可保持向后兼容 | 本地源码 + 既有测试基线 | `CompositeDecoupler.__init__` 现有 5 个关键字参数均有默认值 (`dual_neutralizer.py:354-359`); 新增默认 `True` 的开关不改变既有调用 | ✅ VERIFIED |
| `module_enabled` 的语义是"模块级消融开关", 键名对应步骤名 | 本地源码 | `pipelines_v2.py:513-516` 注释; `backtest/ablation_runner.py:899-908` L1 臂列表 | ✅ VERIFIED |

**本地代码事实核实**:

1. `DynamicFactorPipeline.__init__` 只读取 `imputer` / `neutralizer` / `scaler` 三个键 (`pipelines_v2.py:785-789`)。
2. `fit` 中解耦器创建被包在 `if self._neutralizer_enabled:` 分支内 (`pipelines_v2.py:813-827`); `transform` 以 `_decoupler is not None` 为条件 (`pipelines_v2.py:851-853`)。
3. `CompositeDecoupler` 内部固定组合 `DualNeutralizer` + `ARDecoupler` (`dual_neutralizer.py:374-378`, `384-428`)。
4. `DualNeutralizer.transform` 的两次回归: 第一阶段行业哑变量, 第二阶段市值 (无市值数据时退化为行业残差再中性化) (`dual_neutralizer.py:165-200`)。
5. `CompositeDecoupler.transform` 的 Stage 2 已有 `skip_stage2` 轻量路径 (`dual_neutralizer.py:489-495`), 但 `fit` 仍强制构建 AR 模型 —— 说明"跳过 AR"在现有代码中只是运行时参数, 不是组件开关。

**Q3 结论**: 推荐在组合器内部用显式布尔开关表达子组件, 默认全开; 管线只负责把 `module_enabled` 映射到开关。避免在管线层重新拼装三个原语 (会产生多套阶段逻辑)。

**Q4 结论**: 代码事实成立, 缺陷位置在 `pipelines_v2.py:813` 的绑定, 而非 `CompositeDecoupler` 的统计实现。

---

## §4 待核实项 (⚠️ UNVERIFIABLE)

- Semantic Scholar MCP 对 5 组查询均返回空数组 (可能为配额/索引问题), 本调研不依赖其结果。
- Google 镜像检索返回 HTTP 522; 已改用 WebFetch 官方文档替代。
- Grinold & Kahn 书内具体章节页码未核实, 仅引用书目与结论。

---

## §5 调研结论

**可直接引用**:
- 中性化 (截面) 与 AR 解耦 (时序) 是两个独立统计操作 (§2 Q1)。
- 消融必须隔离单一组件 (§2 Q2, Meyes et al. 2019)。
- 组合器用显式子组件开关、默认全开, 是标准且向后兼容的工程做法 (§3, scikit-learn §8.1)。

**设计含义**:
1. `DynamicFactorPipeline` 需要两个独立开关: `neutralizer` (截面中性化) 与 `decoupler` (AR 解耦)。
2. `CompositeDecoupler` 应接受 `enable_neutralization` / `enable_ar` (默认 `True`), 由管线映射开关。
3. 全开组合必须逐位复现现有输出; 全关组合退化为 imputer 后 identity。
4. `neutralizer=False` 的语义从"关闭解耦"改为"仅关闭中性化", 这是**有意的行为修正**, 需在 CHANGELOG 标注消融结果变化。

**不可引用**: 无 (未采用未核实来源)。

---

## §6 Review 记录 (步骤 2, v1.1)

| 级别 | 检查项 | 结果 | 修正 |
|------|--------|------|------|
| L1 文件 | 4 个外部引用 URL/DOI 可解析 | ✅ | — |
| L2 行号 | `pipelines_v2.py:785-789 / 813-827 / 851-853`、`dual_neutralizer.py:354-379 / 384-428 / 489-495` | ✅ 与源码一致 | — |
| L3 关键词 | `_neutralizer_enabled`、`_decoupler`、`skip_stage2`、`module_enabled` | ✅ 精确存在 | — |
| L4 结构 | 未对 `CompositeDecoupler` 内部统计公式做超出源码的断言 | ✅ | — |
| 表述修正 | 初稿称"双重中性化含行业+市值两阶段且都在 stage1" | ❌ 不准确 | 改为"第一阶段行业, 第二阶段市值 (无市值时行业残差再中性化)", 见 §3 第 4 条 |
| 引用修正 | 初稿拟引用 Semantic Scholar 结果 | ❌ 返回空 | 删除, 改列 §4 不可核实项 |
