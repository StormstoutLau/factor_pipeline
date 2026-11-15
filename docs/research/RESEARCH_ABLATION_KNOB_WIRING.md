# RESEARCH — AblationRunner L3/L4 旋钮接线审计

> **版本**: v1.0 (2026-11-15)
> **上游**: [RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md](RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md) v1.0 §5 O1
> **范围**: `AblationConfig` 的 11 个 L3/L4 自由度字段是否存在真实消费者; 若无, 能否接线到 `FactorProcessingPipelineV2` 的等价能力
> **调研手段**: 全仓符号检索 (Grep) + 源码定点阅读 (Read). 本轮**不新增学术主张**, 归因原则沿用 v3.4.6 已核实引用 (Meyes et al. 2019, arXiv:1901.08644; Athey & Imbens 2017, DOI 10.1257/jep.31.2.3)

---

## §1 调研问题清单

| # | 问题 |
|---|------|
| Q1 | `_l3_*` / `_l4_*` 私有属性是否有任何读者 (含动态读取)? |
| Q2 | 6 个 L4 自由度在真实管线中分别由什么控制 — 配置字段、构造参数, 还是硬编码? |
| Q3 | L3 的 `cusum_k/h` 接入后是否改变处理输出? |
| Q4 | `ewma_halflife` / `ewma_alpha` 是否存在可接线目标? |
| Q5 | `routing_threshold_scale` 与 `correction_method` 是否还有运行时语义? |
| Q6 | 现有 trivial 标记是否与实际执行口径一致? |

---

## §2 代码事实 (F1-F20)

### 2.1 属性读者 (Q1)

| 编号 | 事实 | 证据 |
|------|------|------|
| F1 | `_l3_ewma_halflife` / `_l3_ewma_alpha` / `_l3_routing_threshold_scale` / `_l3_winsorize_ratio` / `_l3_correction_method` / `_l4_outlier_method` / `_l4_scaler_method` / `_l4_imputer_strategy` / `_l4_neutralization` / `_l4_time_align` / `_l4_data_window` 共 11 个属性, **唯一写入点**是 `_apply_l3_overrides` / `_apply_l4_overrides` | `backtest/ablation_runner.py:621-633`, `:659-688` |
| F2 | 全仓命中该 11 个符号的其余位置: 上述方法的 docstring、`tests/test_backtest/test_ablation_runner.py` 的 6 处属性断言。**无生产读者**, 无 `getattr` / `vars()` / `__dict__` 遍历 / `model_dump` 动态读取 | Grep 结果 41 行, 全部为写入/文档/测试 |
| F3 | 结论: 11 个字段中 5+6 全部为**死注入** (写入后无人读取) | F1+F2 |

### 2.2 真实管线控制点 (Q2)

统一管道 (`pipeline_mode='unified'`) 执行 `StaticFactorPipeline`, 其四步构造为:

| 编号 | 事实 | 证据 |
|------|------|------|
| F4 | 插补: `ImputerAdapter(strategy='ffill_ts', ...)`, **策略硬编码**, 仅 `module_enabled['imputer']` 可开/关 | `pipelines_v2.py:715` |
| F5 | 去极值: `ProcessingAdapter(process_type='outlier', method='percentile', percentile_lower=1.0, percentile_upper=99.0)`, **方法与分位点均硬编码**, 仅 `module_enabled['winsorizer']` 可开/关 | `pipelines_v2.py:716-718` |
| F6 | 变换: `method=tp.get('method', 'rank')`, 由 `static_transformation_method` / `static_target_distribution` 驱动 | `pipelines_v2.py:708-709`, `:722-727`; 字段定义 `:470-471`; 注入 `:1320-1323` |
| F7 | 标准化: `ProcessingAdapter(process_type='standardization', method='auto')`, **方法硬编码**, 仅 `module_enabled['scaler']` 可开/关 | `pipelines_v2.py:735-738` |
| F8 | 中性化: `NeutralizerAdapter(enabled=..., **(neutralizer_params))`, 参数由 `_build_neutralizer_params(industry_data, market_cap_data)` 生成; 传市值时**硬编码**切 `'industry_marketcap'` | `pipelines_v2.py:720-721`, `:1161-1162`, `:1415-1423` |
| F9 | 时间对齐: `PipelineV2Config` 无任何对齐/滞后字段; 因果性由 v3.3.6/v3.3.7 (ADR-040) 固定在一步预测 | 字段清单 `pipelines_v2.py:458-596` |
| F10 | 数据窗口: `PipelineV2Config` 无窗口裁剪字段; 窗口由调用方传入的 `factor_data` 索引决定, runner 不做裁剪 | 同上; `ablation_runner.py:521-585` |
| F11 | `AblationConfig` 的 L4 六字段里, 只有 `missing_method='drop'` 与 `neutralization='none'` 被转成 `module_enabled` 开关, 真正改变行为 | `ablation_runner.py:664-688` |

### 2.3 L3 语义 (Q3-Q5)

| 编号 | 事实 | 证据 |
|------|------|------|
| F12 | `cusum_k/h` 已接线到 `PipelineV2Config.cusum_k/h` + `enable_cusum_drift_monitor=True` | `ablation_runner.py:614-619`; 字段 `pipelines_v2.py:509-511` |
| F13 | CUSUM 监测器**不侵入 fit/transform** (源码注释原文), 仅填充 `cusum_monitors` / `drift_alerts` | `pipelines_v2.py:1082-1106` |
| F14 | 推论: `cusum_k/h` 臂的 ΔIC / ΔSharpe **恒为 0**, 仅 `drift_alerts` 诊断输出不同 | F12+F13 |
| F15 | EWMA 存在于**度量层**: `factor_metrics.calculate_ic(weighting='ewma', halflife=...)`, 以及 `optimizer.py:217-228`; 管线处理层无 EWMA | `backtest/factor_metrics.py:113-169` |
| F16 | `AblationRunner` 的指标计算路径**未传** `weighting` (全文件无该符号), 因此 `ewma_halflife` 当前完全未接线; 但存在真实可接线目标 (F15) | Grep `calculate_ic|weighting` → 仅 `multiple_testing` 命中 |
| F17 | `ewma_alpha` 与 `ewma_halflife` 是同一参数的两种表述 (`alpha = 1 - exp(-ln2/halflife)`, 见 `factor_metrics.py:169`), **不可作为两个独立 OAT 自由度并行** | `factor_metrics.py:167-169` |
| F18 | `routing_threshold_scale`: v3.4.0 (ADR-042) 已删除三路路由运行时逻辑, `PipelineV2Config` 无阈值字段 → **不可接线** | 字段清单 `pipelines_v2.py:458-596` |
| F19 | `correction_method`: `multiple_testing.apply_bh_fdr` 的调用点是 `compare_all` (`:1423`), 属**消融显著性校正层**, 不是管线参数 → 不可作为管线参数接线 | `ablation_runner.py:36`, `:1408-1423` |

### 2.4 trivial 标记一致性 (Q6)

| 编号 | 事实 | 证据 |
|------|------|------|
| F20 | L4 `defaults` 与实际执行口径不符三处: (a) `outlier_method='mad'` 标 trivial, 但管线实跑 `percentile 1/99`; (b) `missing_method='median'` 标 trivial, 但管线实跑 `ffill_ts`; (c) `scaler_method='zscore'` 标 trivial, 但变换层实跑 `rank` + 标准化层 `auto`。另 L3 `winsorize_ratio=0.01` 与硬编码 1/99 等价却**未**标 trivial, `routing_threshold_scale=1.0` / `time_align='t+1'` / `data_window` 第三项同为默认值却未标 trivial | `ablation_runner.py:1146-1158`, `:1259-1277`; 对照 F5/F4/F6/F7 |

---

## §3 三分类结论

### 3.1 L4 (19 个非 B3 臂)

| 自由度 | 选项 | 分类 | 说明 |
|--------|------|------|------|
| `neutralization` | none / industry / industry+mktcap | ✅ **已接线** | `module_enabled['neutralizer']` + 市值自动切换 (F8/F11) |
| `missing_method` | drop | ✅ 已接线 | 转 `module_enabled['imputer']=False` (F11) |
| `missing_method` | median / knn | ❌ 不可接线 (当前) | 插补策略硬编码 `ffill_ts` (F4); 要接线需给 `StaticFactorPipeline` 新增 strategy 参数 |
| `outlier_method` | 3sigma / mad / winsorize_1pct / winsorize_5pct | ⚠️ **可接线** | 需把 `method` + 分位点/MAD 倍数从硬编码提到构造参数 (F5) |
| `scaler_method` | rank | ⚠️ 可接线 (部分) | 可映射 `static_transformation_method` (F6) |
| `scaler_method` | zscore / minmax | ❌ 不可接线 (当前) | 标准化层硬编码 `auto` (F7) |
| `time_align` | t+1 / t+5 / week_ahead | ❌ 不可接线 | 无配置项, 因果性由 ADR-040 固定 (F9) |
| `data_window` | 3 个区间 | ❌ 不可接线 | runner 不裁剪数据 (F10) |

### 3.2 L3 (24 个非 B3 臂)

| 自由度 | 臂数 | 分类 | 说明 |
|--------|------|------|------|
| `cusum_k` | 3 | 🔶 已接线但指标空转 | 改诊断不改数据 (F13/F14) |
| `cusum_h` | 3 | 🔶 同上 | 同上 |
| `ewma_halflife` | 3 | ⚠️ 可接线 (度量层) | 可传 `weighting='ewma'` (F15/F16); 属评估口径自由度, 非处理自由度 |
| `ewma_alpha` | 5 | ❌ 不可接线 | 与 halflife 共线 (F17), 应删除该族 |
| `routing_threshold_scale` | 3 | ❌ 不可接线 | 路由已删 (F18) |
| `winsorize_ratio` | 3 | ⚠️ 可接线 | 同 `outlier_method` (F5); 且 0.01 与基线等价 (F20) |
| `outlier_method='mad'` | 1 | ⚠️ 可接线 | 同上 |
| `correction_method` | 3 | ❌ 不可接线 (管线层) | 属 compare 层 (F19); 且它**不改变**任一臂的 IC 序列, 只改变显著性判定 |

**汇总**: 43 个非 B3 臂中, 已接线且指标敏感 = **2** (`neutralization` 的 none / industry+mktcap) + **1** (`missing_method=drop`); 已接线但指标空转 = 6 (`cusum_*`); 可接线 = 10 (`outlier_*` 4 + `winsorize_*` 4 + `scaler=rank` 1 + `ewma_halflife` 3 中实际 3 臂); 不可接线 = 24。

---

## §4 观察项

| # | 观察 | 处置建议 |
|---|------|---------|
| O1 | 「已接线但指标空转」与「未接线」在报表上表现相同 (Δ≈0), 无法区分 | 报告中需标注字段接线状态, 或把诊断类臂单列 |
| O2 | `ewma_alpha` 与 `ewma_halflife` 共线, 同时存在会虚增自由度 | 删除 `ewma_alpha` 族 (5 臂) |
| O3 | `correction_method` 被当作管线参数注入, 但语义在 compare 层; 三个臂的 IC 序列完全相同 | 从 L3 臂集合移除, 改为 `compare_all` 的可选参数(已有能力) |
| O4 | trivial 标记与实跑口径不一致 (F20), 会让平凡臂混入 BH-FDR 分母或让真实等价臂被当作实验臂 | 以实跑口径重定义 `defaults` |
| O5 | 数据窗口 / 时间对齐两族在当前 runner 下永远 Δ=0 | 移除或改为「调用方责任」文档说明 |

---

## §5 结论

1. L3/L4 的 43 个臂中只有 3 个真正改变处理结果, 6 个只改变诊断, 10 个可通过扩展 `StaticFactorPipeline` 接线, 24 个在当前架构下不可接线。
2. 这不是实现 bug, 而是**消融框架与实际管线能力脱节**: `_apply_*_overrides` 当初按「设想中的管线能力」编写, 而管线从未实现这些字段。
3. 修正路径有两条: (A) 扩展管线参数面, 把可接线的 10 个臂接上; (B) 剔除不可接线臂, 使臂集合等于真实自由度。二者需同时做, 否则报表仍不可解释。

## §6 Review

| 检查项 | 结果 |
|--------|------|
| 每条事实均有 `文件:行号` | ✅ F1-F20 |
| 是否存在未核实推断 | F14 (Δ恒为 0) 为 F12+F13 的直接推论; F20 为字段与实跑值对照, 均已标注依据 |
| 学术引用 | 沿用 v3.4.6 已核实两条, 本轮无新增 |
| 与 v3.4.6 文档一致性 | O1 与 `RESEARCH_ABLATION_MKTCAP_ALIGNMENT.md` §5 O1 一致, 本文件为其展开 |
