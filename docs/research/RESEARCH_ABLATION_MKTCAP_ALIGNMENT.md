# 调研: AblationRunner L3/L4 市值口径对齐 (v3.4.6)

> **版本**: v1.0 (2026-11-13)
> **任务**: 补齐 `run_l3` / `run_l4_oat` 的 `market_cap_data` 入口, 消除跨层消融的中性化口径不一致
> **前置**: v3.4.4 (`run_l1`/`run_single` 断链修复), v3.4.5 (`run_l2`/`run_baselines` 断链修复)
> **归属**: PROJECT_STATUS §2 P1 建议项 A

---

## §1 问题陈述

v3.4.4/v3.4.5 修复后, L1 / L2 / Baseline 三层都能真正使用市值中性化, 但:

1. `run_l3` 与 `run_l4_oat` 的签名里**没有** `market_cap_data` 参数 —— 调用方无法传入;
2. L4 的 `neutralization` 自由度里有 `industry+mktcap` 选项, 但在**没有市值数据**的情况下,
   该选项与 `industry` 完全相同 (见 F4/F5) —— 即该消融臂目前是空转的。

后果: 同一次消融中 L3/L4 的臂全部走「仅行业」中性化, 而 L1/L2/B3 走「行业 + 市值」,
跨层 ΔIC/ΔSharpe 混入了中性化口径差异, 违反消融归因前提 (参照臂与实验臂仅目标组件不同;
Meyes et al. 2019, arXiv:1901.08644; Athey & Imbens 2017, DOI 10.1257/jep.31.2.3)。

---

## §2 代码事实 (A 类: 直接读取)

> **快照口径**: F1-F8 记录 v3.4.6 **实现前** (即 v3.4.5) 的代码状态, 用于界定问题;
> F9-F12 描述实现前后均成立的结构性事实。行号以 v3.4.5 快照为准, 实现后会漂移。

| # | 事实 | 证据 |
|---|------|------|
| F1 | `run_l4_oat` 签名为 `(factor_data, fwd_returns, industry_data=None, b3_full_result=None)`, 无 `market_cap_data` | `backtest/ablation_runner.py:1085-1091` |
| F2 | `run_l3` 签名同上, 无 `market_cap_data` | `backtest/ablation_runner.py:1155-1161` |
| F3 | 两者所有臂的 `run_single` 调用均为 `(config, factor_data, fwd_returns, industry_data)`, 无额外关键字 | `:1104`, `:1151`, `:1179`, `:1189`, `:1199`, `:1207`, `:1215`, `:1223` |
| F4 | L4 的 `neutralization` DOF 有 3 个选项 `none / industry / industry+mktcap`, 默认 `industry` | `:1117-1119`, `:1136` |
| F5 | `industry+mktcap` 选项仅通过 `_apply_l4_overrides` 写入 `modified_config._l4_neutralization`, 该属性在整个仓库**无任何消费者** | `:1132-1151` + 全仓 grep `_l4_neutralization` 仅命中写入点与测试 |
| F6 | 管线在 `market_cap_data is not None` 时**自动**把 `neutralization_type` 切为 `industry_marketcap` (硬编码, 无开关) | `pipelines_v2.py:1414-1423` |
| F7 | `NeutralizerAdapter.fit` 只有在 `neutralization_type == 'industry_marketcap'` 且收到 `market_cap_data` 时才缓存 log_mv; `transform` 以缓存非空为条件加入回归矩阵 | `adapters.py:926-928`, `adapters.py:977-983` |
| F8 | 因此「仅行业」无法通过「传市值 + 配置」表达 —— 必须**不传市值** | F6 + F7 推论 |
| F9 | `run_l1` 已采用参数顺序 `(industry_data, market_cap_data, b3_full_result)` | `:894-900` |
| F10 | 全仓无任何位置把 `b3_full_result` 作为位置参数传入 (均用关键字或省略) | grep `run_l3(` / `run_l4_oat(`, 4 处测试均为前两参位置传入 |
| F11 | L3 的 `_l3_*` 属性 (ewma / threshold_scale / winsorize_ratio / correction_method) 与 L4 的 `_l4_outlier_method` / `_l4_scaler_method` / `_l4_imputer_strategy` / `_l4_time_align` / `_l4_data_window` 同样**无消费者**; 真正生效的只有 `cusum_k/h`、`missing_method='drop'`、`neutralization='none'` | 全仓 grep |
| F12 | 现有测试 `test_l4_oat_trivial_marking` 断言 `L4_neutralization_industry` 为 trivial, 测试调用不传市值 | `tests/test_backtest/test_ablation_runner.py:1368-1410` |

---

## §3 问题拆解 (Q)

| # | 问题 | 结论 |
|---|------|------|
| Q1 | L3 是否应统一注入市值? | 是。L3 没有与中性化冲突的自由度, 所有臂与 B3 应使用同一口径 (行业+市值) |
| Q2 | L4 能否统一注入市值? | **不能**。F6 使「传市值」等价于「强制 industry_marketcap」, 统一注入会让 `industry` 与 `industry+mktcap` 两臂恒等 |
| Q3 | 那 L4 的 `industry` 臂如何表达? | 该臂**不注入**市值; 其余非中性化自由度臂统一注入 |
| Q4 | L4 默认选项 (trivial) 该是什么? | 传市值时默认应为 `industry+mktcap` (与 B3 口径一致, 平凡比较才成立); 未传市值时保持 `industry` |
| Q5 | 插入位置? | 与 `run_l1` 一致: `industry_data, market_cap_data, b3_full_result`; F10 证明无位置参数调用, 兼容 |

---

## §4 设计含义

1. **接口**: 两个方法各新增 `market_cap_data: Optional[pd.DataFrame] = None`, 位于 `industry_data` 之后、
   `b3_full_result` 之前。
2. **L3**: B3 与 24 个臂统一注入 (仅非 None), 臂集合与返回数量 (25) 不变。
3. **L4**: B3 与绝大多数臂注入; `neutralization == 'industry'` 的臂**跳过注入** (F8);
   `neutralization == 'industry+mktcap'` 注入。
4. **默认口径**: `defaults['neutralization']` 在传市值时改为 `industry+mktcap`, 否则保持 `industry`
   —— 保证 trivial 臂仍与 B3 同口径。
5. **兼容**: 不传市值时行为与现状**逐位一致** (L4 的 6 个 trivial 断言不受影响)。

---

## §5 范围外观察项 (登记, 不在本任务修复)

| # | 观察 | 影响 |
|---|------|------|
| O1 | L3/L4 大量自由度开关 (`_l3_*` / `_l4_*`) 无消费者, 对应消融臂与基线数值完全相同 (F11) | 消融报表中这些臂的 Δ≈0 是「空转」而非「无效应」, 会误导归因。属独立任务, 需逐旋钮映射到真实管线配置 |
| O2 | L4 的 `time_align` / `data_window` 需要改变输入数据切片, 而 `_run_pipeline` 目前不支持 | 同上 |
| O3 | `run_l3` 的 `b3_full_result` 由调用方提供时, 其口径由调用方负责 (本任务不校验) | 文档中明示 |

---

## §6 结论

在本任务范围内, 最小且语义正确的改动是:

- `run_l3`: 统一注入市值 (口径对齐);
- `run_l4_oat`: 统一注入市值, **但** `neutralization='industry'` 臂显式跳过, 且默认口径随
  「是否提供市值」切换。

这样既消除跨层口径差, 又让 L4 的 `industry+mktcap` 从空转变回真实可测。

> O1 是本任务发现的**更大问题** (多数 L4/L3 消融臂为空转), 但修复需要对每个旋钮做
> 管线级映射, 与本任务的「入口断链」不是同一量级, 单独立项。

---

## §7 Review

| 检查 | 结论 |
|------|------|
| 事实是否均来自代码 (非推测) | ✅ F1-F12 均标注文件:行 |
| 是否回答了「为什么不能统一注入」 | ✅ F6 + F8 |
| 是否识别出空转的消融臂 | ✅ F5/F11 |
| 是否把范围外问题写入观察项 | ✅ O1-O3 |
