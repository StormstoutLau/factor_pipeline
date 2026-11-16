# RESEARCH 消融臂 trivial 判定口径 (ABLATION_TRIVIAL_CALIBER)

> **版本**: v1.1 (2026-11-15, 步骤 2 review 后)
> **调研工具**: `mcp_paper-search` (search_semantic) / WebSearch
> **范围**: `AblationRunner.run_l4_oat` 在缺少市值数据时 `industry+mktcap` 臂的
> 实跑口径退化问题, 以及「与基线同口径的臂是否应计入 BH-FDR 分母」的统计依据。

## §1 调研问题清单

- **Q1**: BH-FDR 的 `m` (被检验假设总数) 在步进过程中如何定义? 把已知为零效应的假设计入 `m` 有何后果?
- **Q2**: 是否存在「先行过滤与检验统计量独立的无信息假设可提高检测力」的权威结论?
- **Q3**: 本仓 `_is_trivial` 既有语义是什么? 由谁消费?
- **Q4**: `run_l4_oat` 现实现中, 哪些臂在「无市值」场景下与 B3 基线实跑口径相同?
- **Q5**: 退化臂若继续计入 BH 分母, 对 q 值与检测力的影响方向?

## §2 学术文献调研

| 引用 | 工具 | 标识 | 关键结论 | 状态 |
|------|------|------|---------|------|
| Benjamini & Hochberg (1995), *Controlling the false discovery rate: a practical and powerful approach to multiple testing*, JRSS-B 57(1):289-300 | `search_semantic` | DOI: 10.1111/j.2517-6161.1995.tb02031.x | BH 步进以 `q_(i) = p_(i) · m / i` 与 α 比较, `m` 为参与检验的假设总数; `m` 增大使阈值收紧 | ✅ VERIFIED |
| Bourgon, Gentleman & Huber (2010), *Independent filtering increases detection power for high-throughput experiments*, PNAS 107(21):9546-9551 | WebSearch (PNAS 原文) | DOI: 10.1073/pnas.0914005107 | 以「与检验统计量独立」的准则先过滤无信息变量, 可在控制 FDR 前提下提高检测力 | ✅ VERIFIED |

**推论 (Q5)**: 退化臂的真实 Δ 恒为 0, 其 p 值分布退化在 1 附近。把它计入 `m` 只会单向放大 `q_(i)` 阈值分母, 降低其余臂的检出概率, 不提供任何信息。这与 Bourgon et al. (2010) 的「独立过滤提升检测力」方向一致: 结构性零假设应在检验前排除。

## §3 工程实践调研

| 声明 | 核实方式 | 证据 | 状态 |
|------|---------|------|------|
| `_is_trivial=True` 的比较不进入 BH-FDR 分母, 但保留在报告列表 | 源码阅读 | [ablation_runner.py L1341-L1349](../../backtest/ablation_runner.py#L1341-L1349) (`non_trivial_indices` 过滤) | ✅ VERIFIED |
| trivial 比较的 `is_significant` 被强制为 `False` | 源码阅读 | [ablation_runner.py L1354-L1356](../../backtest/ablation_runner.py#L1354-L1356) | ✅ VERIFIED |
| `_is_trivial` 的既有语义是「该臂与 baseline 同口径」 (M5 修正) | 源码注释 | [ablation_runner.py L1336-L1337](../../backtest/ablation_runner.py#L1336-L1337) | ✅ VERIFIED |
| 市值仅在非 `None` 时注入 runner 各臂 | 源码阅读 | [ablation_runner.py L1098-L1101](../../backtest/ablation_runner.py#L1098-L1101) | ✅ VERIFIED |
| L4 默认中性化口径随市值可用性切换 | 源码阅读 | [ablation_runner.py L1129-L1133](../../backtest/ablation_runner.py#L1129-L1133) | ✅ VERIFIED |
| trivial 判定当前仅比较「选项名 == 默认选项名」 | 源码阅读 | [ablation_runner.py L1137](../../backtest/ablation_runner.py#L1137) | ✅ VERIFIED |
| `industry` 臂强制不传市值 (否则自由度失效) | 源码注释 + 代码 | [ablation_runner.py L1145-L1149](../../backtest/ablation_runner.py#L1145-L1149) | ✅ VERIFIED |
| 管线收到市值才切 `industry_marketcap`, 否则保持仅行业中性化 | 源码阅读 | [pipelines_v2.py L1431-L1440](../../pipelines_v2.py#L1431-L1440) | ✅ VERIFIED |
| v3.4.7 测试断言「不传市值 → 2 trivial + 6 非平凡」 | 测试阅读 | [test_ablation_knob_wiring.py L137-L152](../../tests/test_backtest/test_ablation_knob_wiring.py#L137-L152) | ✅ VERIFIED |

**Q4 结论 (退化臂清单)**: `market_cap_data is None` 时, `extra_kwargs = {}`; `L4_neutralization_industry+mktcap` 臂同样不传市值 → 管线回落至仅行业中性化, 与 B3 基线 (`defaults['neutralization'] = 'industry'`) 实跑口径完全相同。其余 7 个臂的实跑口径与 B3 不同, 无退化。

当前 8 臂中该臂被标为 `_is_trivial=False`, 即「口径相同却计入 BH 分母」——与 `_is_trivial` 的既有语义矛盾。

## §4 待核实项 (⚠️ UNVERIFIABLE)

- `search_semantic` 对 Bourgon et al. (2010) 的标题检索返回空列表 (MCP 检索侧缺失), 改由 WebSearch 命中 PNAS 原文页核实 DOI/卷期, 结论可信。
- BH (1995) 原文 paywall, 上述 `m` 定义依据 Semantic Scholar 元数据 + 本仓 [multiple_testing.py](../../backtest/multiple_testing.py) 既有实现 (步进公式 `p·m/i`) 双向印证, 未逐字比对原文公式排版。

## §5 调研结论

- **可直接引用**: BH-FDR 的 `m` 为参与检验假设总数 (BH 1995); 与检验统计量独立的预过滤可提升检测力 (Bourgon et al. 2010); `_is_trivial` 在本仓的语义 = 「与 baseline 同口径」。
- **需用户核实**: 无。
- **不可引用 (已证伪)**: 「选项名与默认名相同」等价于「实跑口径与基线相同」——在缺少市值数据时不成立。
- **处置方向**: trivial 判定改为**按实跑口径**比较 (而非按选项名), 并在退化发生时输出一次告警, 使报告使用者能区分「该臂无效应」与「该臂口径退化」。

---

## §6 步骤 2 review 记录 (2026-11-15, v1.0 → v1.1)

| 检查维度 | 检查方式 | 结果 |
|---------|---------|------|
| 引用真实性 | BH (1995) 经 `search_semantic` 返回 DOI/作者; Bourgon et al. (2010) 经 WebSearch 命中 PNAS 原文页 (卷期 107(21):9546-9551, DOI 10.1073/pnas.0914005107) | ✅ 两处均可溯源, 无臆造 |
| 行号准确性 | 逐条回读 `ablation_runner.py` L1098-1156 / L1331-1366、`pipelines_v2.py` L1431-1440、测试 L137-152 | ✅ 全部一致 |
| 符号准确性 | `_is_trivial` / `extra_kwargs` / `defaults` / `industry_marketcap` / `neutralization_type` 均真实存在 | ✅ |
| 结论可推导性 | 「m 增大 → 阈值收紧」由 `q_(i)=p_(i)·m/i` 直接得出; 退化臂清单由 L1098-1101 + L1129-1133 + L1145-1149 + pipelines L1431-1440 联合推出 | ✅ |
| 过度断言 | 「不可引用」条目限定为「选项名等价实跑口径」这一具体命题, 未推广到其他自由度 | ✅ 无外溢 |

**review 结论**: PASS (0 幻觉, 0 需删除引用)。文档状态更新为 v1.1。
