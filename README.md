[English](README.en.md) | [中文](README.md)

![Factor Pipeline](docs/badges/factor_pipeline_cli.svg)

# Factor Processing Pipeline

## 统一因子处理流水线

**Factor Processing Pipeline** 是一个面向量化投资领域的统一因子处理编排系统。系统从 v1.0 的"固定流程"演进至 v2.5.0 的"多因子正交化三层架构 + 860 测试零回归"，并正在推进 v2.6.0 的**优化器与漂移检测增强** (ADR-004/005/006 修订 + ADR-021/022/023 新增)。核心能力涵盖**因子指纹前置诊断层**、**语义-统计融合分类**、**三条差异化处理管道**、**可选 GARCH 白化**、**持续迁移监测**、**回测引擎集成**、**L2 磁盘缓存层**、**多因子横截面正交化 (5 种算法)**与**双轨漂移融合判定**。

> **GitHub**: https://github.com/StormstoutLau/factor_pipeline

---

## 目录

- [版本更新摘要](#版本更新摘要)
- [架构设计](#架构设计)
- [模块组成](#模块组成)
- [三条差异化管道](#三条差异化管道)
- [处理顺序校验](#处理顺序校验)
- [与开源社区对比](#与开源社区对比)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [文件结构](#文件结构)

---

## 版本更新摘要

### v3.0.0 T4 KS 迁移检测 BH-FDR 替代 Bonferroni (2026.07, 已实施)

> **状态**: 已实施, 934 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.6.0 的 918 多 16 个新测试)
> **文档**: [docs/EXECUTION_V3.0.0_T4.md](docs/EXECUTION_V3.0.0_T4.md) | [docs/ANALYSIS_V3.0.0.md](docs/ANALYSIS_V3.0.0.md)
> **基线**: 918 passed + 6 skipped (v2.6.0) → 934 passed + 6 skipped (v3.0.0 T4, 含 11 subtests)
> **关系**: v3.0.0 远期 4 项任务 (T1-T4) 中 T4 (P0) 已完成; T1 (指纹扩展) / T2 (流式) / T3 (CUSUM) 待启动

**3 阶段执行方案 (E1-E3)**:

| 阶段 | 任务 | 测试数 | 关键变更 |
|------|------|--------|---------|
| **E1** | BH 核心实现 (Red→Green→Review) | 13 | `_ks_migration_significance` 新增 `correction_method` 参数 (默认 'benjamini_hochberg'), 三路径分流 (BH/Bonferroni/none), 字段隔离, ADR-002a 写入 DECISIONS.md |
| **E2** | 测试更新 | 3 | verify_fix1_manual.py 校验 3 改为 BH-FDR 公式校验, test_factor_significance_manual.py 新增 TestKSMigrationBHCorrection 类 |
| **E3** | 文档同步 + 全量回归 | 0 | CHANGELOG/CODE_WIKI/README 同步, verify_v3_0_0_t4_manual.py 8/8 手工校验, 全量回归 934 passed |

**1 项新 ADR**:
- **ADR-002a**: Benjamini-Hochberg FDR 替代 Bonferroni (supersede ADR-002 的校正方法, ADR-002 历史保留)

**5 项关键设计决策**:
1. 默认改 BH, 保留 Bonferroni 向后兼容 (`correction_method='bonferroni'` 显式 opt-in 旧路径)
2. 三路径字段隔离 (BH: min_p_value_adjusted/correction_method; Bonferroni: alpha_corrected/bonferroni_correction)
3. None 路径供研究/调试 (`correction_method='none'` 无校正, 直接 `min_p < alpha`)
4. 黄金参考: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5 → p_adj=[0.05, 0.0667, 0.0667, 0.25, 0.50]
5. 行为变化: BH 比 Bonferroni 宽松, 之前不显著的迁移现在可能变显著 (`is_sig` 可能 False→True)

**学术依据**:
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *JRSS-B*, 57(1), 289-300.
- 与 `factor_significance.py` 的 BH 默认一致 (E7 已用 BH)

### v2.6.0 优化器与漂移检测增强 (2026.07, 已实施)

> **状态**: 已实施, 918 passed + 6 skipped + 11 subtests passed (零回归, 比 v2.5.0 的 860 多 58 个新测试)
> **文档**: [docs/EXECUTION_V2.6.0.md](docs/EXECUTION_V2.6.0.md) | [docs/ANALYSIS_V2.6.0.md](docs/ANALYSIS_V2.6.0.md)
> **基线**: 860 passed + 5 skipped (v2.5.0) → 918 passed + 6 skipped (v2.6.0, 含 11 subtests)

**9 阶段执行方案 (E1-E9)**:

| 阶段 | 任务 | 优先级 | 关键变更 |
|------|------|--------|---------|
| **E1** | P3-11' 文档状态修正 | P0 | DECISIONS.md P3-11 `[ ]` → `[x]` |
| **E2** | P3-10' migration_threshold 字段位置 + ADR-005 | P0 | optimizer.py:150-158 (`config.monitor` → `config`) |
| **E3** | P3-1' IC 时间加权 EWMA | P1 | factor_metrics.py `compute_ic_series` 添加 `weighting`/`halflife` |
| **E4** | P3-9' 目标函数对齐 ADR-004 (ADR-021) | P1 | `_health_penalty_proxy` (IC decay/hit_rate/ic_vol 三档) + fidelity 符号修正 |
| **E5** | P3-13 正交化参数纳入搜索空间 (ADR-022) | P1 | `DEFAULT_SEARCH_SPACE_ORTH` (orth_method/align_mode/ridge_lambda) |
| **E6** | P3-14 几何诊断纳入目标函数 | P2 | `OrthogonalizerAdapter.get_diagnostics()` + `_redundancy_penalty` (compute_vrr) |
| **E7** | P3-15 Layer 3 显著性最终验证 | P2 | `_validate_significance` (FactorSignificanceTest, 仅最终验证) |
| **E8** | P3-12' 阈值漂移监测 (ADR-023) | P2 | `backtest/threshold_drift_monitor.py` (ThresholdDriftMonitor, EWMA 衰减检测) |
| **E9** | 文档验证 + 全量回归 | P1 | verify_v2_6_0_manual.py 8 项手工校验 |

**3 项新 ADR**:
- **ADR-021**: 目标函数对齐 ADR-004 — health_penalty 代理指标方案 (IC decay/hit_rate/ic_vol 三档近似 health_score, 解决 HealthMonitorAdapter 时序依赖)
- **ADR-022**: 搜索空间扩展 — 正交化参数纳入 (`search_orth=False` 默认关闭, 启用后搜索 method/align/lambda 三维度, 不搜索 orth_enabled)
- **ADR-023**: 阈值漂移监测 — ThresholdDriftMonitor (EWMA 衰减检测, halflife=63, decay > 20% 触发 `needs_research`)

**6 项核心约束**:
1. 基线保护: 默认行为不变, 不影响 860 测试基线
2. ADR 契约对齐: ADR-004 (health_penalty) 改代码, ADR-005 (static/dynamic) 改 ADR
3. TDD 开发: 每阶段严格 Red-Green-Refactor, 含手工数值校验
4. 数值精度: 与独立 numpy/statsmodels 实现对比, 精度 < 1e-10
5. 无 look-ahead bias: 正交化参数搜索时必须在 CV fold 内部 fit (用 train 数据)
6. 计算成本控制: FactorSignificanceTest 仅用于最终验证, 不用于每 trial 评估

**学术依据修正** (v1.0 误引 → v1.1 修正):
- P3-1 IC 时间加权: Cohen-Coval-Pastor (2005) → Ferson-Siegel (2001)
- P3-12 阈值漂移: Hsu (2010) 误称 Bayesian → Sullivan-TW (1999) + McLean-Pontiff (2016)
- P3-11 参数重要性: 拆分为 Bergstra (2011) TPE + Hutter (2014) fANOVA

### v2.5.0 多因子正交化三层架构 (2026.07)

> **状态**: 已实施, 860 测试零回归 (比 v2.4.0 的 632 多 228 个)
> **文档**: [docs/EXECUTION_V2.5.0.md](docs/EXECUTION_V2.5.0.md) | [docs/ANALYSIS_V2.5.0.md](docs/ANALYSIS_V2.5.0.md)

**三层架构分离** (ADR-020):

| Layer | 职责 | 模块位置 | 监督性 |
|-------|------|---------|--------|
| **Layer 1** | per-factor 处理 (已有) | `pipelines_v2.py` | 无监督 |
| **Layer 2** | cross-factor 横截面正交化 (新增) | `modules/factor_orthogonalizer/` | 无监督 |
| **Layer 3** | target-aware 显著性检验 (新增) | `backtest/factor_significance.py` | 有监督 (需 Y) |

**Layer 2 核心算法** (5 种):
- **Symmetric (Löwdin)**: 默认主方法, VRR=1, 无顺序依赖
- **Ridge**: 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004)
- **PCA**: 降维场景, center 参数兼容 Layer 1 标准化
- **Gram-Schmidt**: 顺序依赖场景, κ>100 启用 Kahan (1966) 二次投影
- **Cholesky**: 半正定保证场景

**Layer 3 显著性检验**:
- **双重 Lasso**: treatment 轮询模式, 每个因子独立当 treatment, 轮次顺序不影响结果
- **Elastic Net**: α/λ 网格搜索, 处理多因子共线性

**执行方案 v1.1 深化内容** (40 个子章节):
- O1.12 算法核心 (7): threshold_mode 三模式 / eigh-svd 选择 / fit_from_gram / dtype 强制
- O2.8 适配器层 (6): align_mode / NaN 处理 / post_transform_hooks 零开销 / W 缓存
- O3a.6 几何诊断 (5): VRR ddof / VIF 多方法 / 条件数分级 (Belsley-Kuh-Welsch 1980)
- O4.9 双重 Lasso (7): treatment 轮询 / 稳健标准误 / 多重检验校正
- O4.11 RollingOrthogonalizer (5): 增量 Gram 重置 / is_orthogonalized 标记 / warm-start LOBPCG
- O5.6 协同设计 (5): 数据流协议 / Neutralizer 顺序 / Grouped 缺失因子 / 冲突解决
- O6.7-O6.11 文档验证 (5): TDD 分阶段回归 (6 Stage) / 手工校验矩阵 (21 项) / 性能基准

**性能预期**: K=20 时 Symmetric fit < 0.5ms; 增量 Gram + warm-start 实现 42x 加速 (vs 全量重算)

**约束**: 正交化默认关闭 (`enabled=False`), 不影响 632 基线测试

**实施成果** (O1-O6 全部完成):
- **O1 算法核心**: 5 种正交化器 (Symmetric/Ridge/PCA/Gram-Schmidt/Cholesky) + fit_from_gram 接口 + dtype 强制 — 44 单元测试 + 15 手工校验
- **O2 适配器层**: OrthogonalizerAdapter + CrossSectionalOrthogonalizer + post_transform_hooks 半侵入式接入 + align_mode 三模式 — 22 单元测试 + 12 手工校验
- **O3a 几何诊断**: VRR/κ/VIF/正交性误差 + VIF 多方法 (lstsq/qr/pinv) + 条件数分级 (Belsley-Kuh-Welsch 1980) — 18 单元测试 + 24 手工校验
- **O3b Layer 3 检验**: 双重 Lasso (Belloni 2014 PDS) + treatment 轮询 + HC3 稳健标准误 + BH FDR 校正 — 17 单元测试 + 14 手工校验
- **O4 回测扩展**: RollingOrthogonalizer + ICChangeMonitor + 增量 Gram + is_orthogonalized 标记 — 11 单元测试 + 19 手工校验
- **O5 协同验证**: Grouped + TripleChain (Fingerprint/Decoupler/Orthogonalizer 三件套串联) — 15 单元测试 + 17 手工校验
- **O6 文档验证**: 版本号 8 处同步 + ADR-020 状态更新 + 全量回归 860 passed + 5 skipped + 手工校验 5/5 通过
- **技术债修复**: tests/manual/test_adapter_manual.py:test_disabled_adapter_no_import 添加 try/finally 恢复 sys.modules, 消除 class identity (is 检查) 失败的隐蔽污染

### v2.4.0 外部模块内化 (2026.07)

> **状态**: 已实施, 632 测试零回归

**5 个处理模块内化** (ADR-019):

| 模块 | 原外部路径 | 内化路径 | 依赖裁剪 |
|------|-----------|---------|---------|
| **factor_fingerprint** | Factor_Fingerprint/ | `modules/factor_fingerprint/` | — |
| **factor_decoupler** | Factor_Decoupler/ | `modules/factor_decoupler/` | — |
| **factor_adaptive_winsor** | Factor_AdaptiveWinsor/ | `modules/factor_adaptive_winsor/` | 仅迁移 core/ (最小子包化) |
| **factor_imputer** | Factor_Imputer_v2.0/ | `modules/factor_imputer/` | — |
| **factor_neutralizer** | Factor_Neutralizer_v2.0/ | `modules/factor_neutralizer/` | 去除 matplotlib/joblib/psutil/numba |

**关键决策**:
- **命名统一**: 小写蛇形, 移除 v2.0/v3.0 版本后缀 (版本信息留在模块内 `__version__`)
- **内化优于子包化** (ADR-019): 单仓库场景下独立性是虚假收益, 内化消除 importlib hack 与 sys.path 污染
- **保留外部数据边界**: Factor_DB 和 Factor_Trading 仍作为外部模块 (数据源)
- **CI 简化**: monorepo 模拟从 7 个外部模块缩减为 2 个

**5 阶段全量回归**: I1 (Fingerprint+Decoupler) → I2 (AdaptiveWinsor) → I3 (Imputer) → I4 (Neutralizer) → I5 (CI/文档清理), 全程 632 passed 零回归

### v2.3.0 CI 矩阵与双轨 CI (2026.07)

> **状态**: 已实施

**GitHub Actions 矩阵** (ADR-017):
- Python 3.10 / 3.11 / 3.12 × ubuntu-latest
- `fail-fast: false`: 一个版本失败不阻塞其他版本
- Windows 因 spawn 方法进程启动开销暂不纳入 (ADR-016)

**tox 双轨 CI**:
- 远程 (GitHub Actions): 保障推送质量
- 本地 (tox): 快速验证跨版本兼容性, 每 env 独立安装外部模块保证隔离性
- CI 配置文件脚本校验: 37/37 通过

**CI monorepo 模拟**: 外部模块通过 `git clone` 到父目录模拟本地结构, 目录名重命名匹配 pyproject.toml package-dir 映射

### v2.2.2 漂移检测与优化器改进（2026.07）

| 改进项 | 优先级 | 说明 | 测试 | 手工校验 |
|--------|--------|------|------|----------|
| **P0-1: 滚动窗口 KS** | P0 | 替代二分分割,滚动窗口 + p值过滤降低假阳性 | 15/15 ✅ | — |
| **P0-2: Pipeline-in-the-loop** | P0 | 优化器真正调用 Pipeline fit+transform,完整 8 参数映射 | 5/5 ✅ | — |
| **P1: per-factor min_dates** | P1 | Barra 41天 vs 日频 1212天自适应阈值 + reindex 对齐 | 7/7 ✅ | 8/8 ✅ |
| **P2-1: 三模式信号融合** | P2 | and/or/max 替代单一 AND 逻辑,解决漏报 | 11/11 ✅ | 12/12 ✅ |
| **P2-2: 优化器 CV 改进** | P2 | _cv_evaluate 接口重写,每 fold train fit/test transform 消除 look-ahead | 9/9 ✅ | 12/12 ✅ |
| **P3-2: 分组并行 A/B 实验** | P3 | 20 因子对比,保留方案 A (ADR-009) | — | 实验验证 |

**核心改进**:
- 漂移检测: 滚动窗口 KS + p值过滤 + 三模式融合 (and/or/max)
- 优化器: Pipeline-in-the-loop + CV 消除 look-ahead bias
- 数据适配: per-factor min_dates + reindex 对齐处理混合频率因子

**关键决策 (ADR-009)**: P3-2 分组并行 A/B 对比实验证明方案 B (统一日期范围) 不可行 — 不同频率因子的 fwd_returns 语义不同,统一到日频会改变 IC 含义。保留方案 A (按日期分组)。

**测试**: 612/612 全部通过,32/32 手工校验通过,回归测试无新增失败。

### v2.2.1 L2 磁盘缓存层（2026.07）

| 模块 | 优先级 | 说明 | 测试 |
|------|--------|------|------|
| **`cache_manager.py`** | P0 | L2 磁盘缓存基础设施,支持 DataFrame (.parquet) + ndarray (.npy) + .meta.json 元数据 | 34/34 ✅ |
| **`price_cache.py`** | P1 | 价格矩阵缓存,包装 PriceQuery.get_price_matrix() | 12/12 ✅ |
| **`factor_cache.py`** | P1 | 因子矩阵缓存,包装 FactorPivotAdapter.get_pivoted(),支持部分命中 | 12/12 ✅ |
| **`cached_data_loader.py`** | P2 | 统一入口,业务代码一处替换即可启用缓存 | 13/13 ✅ |
| **`fwd_returns_cache.py`** | P2 | 前向收益 ndarray 缓存,接受 compute_fn 按需计算 | 10/10 ✅ |
| **端到端集成测试** | P3 | 真实 DB 跑完整 Pipeline,验证缓存命中和结果一致性 | 4/4 ✅ |

**核心设计** (ADR-008):
- 三原则: P0 可调试性 > P1 正确性 > P2 性能
- 三层透明度: 日志 (HIT/MISS) + .meta.json 元数据 + 环境变量逃生舱 (`FACTOR_PIPELINE_CACHE=disabled`)
- 数据指纹校验 + 损坏自愈 + 双轴 freq 保真
- 数据加载阶段加速 4.36x (1.466s → 0.336s)

**使用方式**:
```python
from factor_pipeline.backtest.cached_data_loader import CachedDataLoader

# 一处替换,即可启用缓存
loader = CachedDataLoader(
    db_path="factor_db.duckdb",
    cache_dir="./cache",
    enabled=True,
)
factor_data = loader.get_pivoted_factors(["PE", "PB"], start_date, end_date)
price_data = loader.get_price_matrix(field="close", start_date, end_date)

# 调试时一键禁用
# export FACTOR_PIPELINE_CACHE=disabled
```

**测试**: 85/85 全部通过,回归测试无新增失败。

### v2.2.0 Backtest 集成（2026.07）

| 模块 | 优先级 | 说明 | 测试 |
|------|--------|------|------|
| **`factor_metrics.py`** | P1 | 因子级指标单一真相源，IC/ICIR/Decay/Turnover/LS/Spread 唯一权威 | 30/30 ✅ |
| **`data_bridge.py`** | P2 | Pipeline → DataLoaderV3 格式适配器，转置 (n_stocks, n_dates) → (n_dates, n_stocks) | 10/10 ✅ |
| **`engine.py`** | P3 | 因子回测引擎，改编自 `engine_v3_vector.py`，使用单一真相源 | 20/20 ✅ |
| **`health_bridge.py`** | P4 | 回测 → FactorHealthMonitor 适配器，不修改外部模块 | 13/13 ✅ |
| **`unified_drift.py`** | P5 | 双轨融合漂移判定：结构漂移 (Fingerprint) + 性能漂移 (Backtest) + 换手率漂移 | 13/13 ✅ |
| **`pipeline_integration.py`** | P6 | 端到端 Pipeline 集成运行器 + BacktestConfig 配置扩展 | 9/9 ✅ |

**核心设计**:
- 单一真相源：`factor_metrics.py` 唯一权威，避免重复计算
- 适配器模式：两个适配器隔离依赖，不改动外部模块
- 双轨融合：结构漂移 + 性能漂移，提升漂移检测可靠性
- importlib 绕过重依赖：解决 `core` 命名空间冲突

**测试**: 95/95 全部通过，回归测试无新增失败。

### v2.1.0 架构修复（2026.07）

| 修复项 | 优先级 | 说明 | 影响 |
|--------|--------|------|------|
| **概率加权软路由** | P0 | 硬路由 → 多管道加权混合，消除因子类型切换时的断崖效应 | 过渡平滑，无跳跃 |
| **数据驱动阈值校准** | P0 | `ThresholdCalibrator` 分位数法 + 市场预设，替代硬编码阈值 | 自适应数据分布 |
| **统一 `fit()` 中间数据** | P1 | 三条管道统一 `_intermediate_data` + `get_intermediate_data()` | 全流程可追溯 |
| **适配器回退 Warning** | P1 | 外部模块不可用时 `warnings.warn(UserWarning)` 替代静默失败 | 透明度提升 |
| **迁移权重融合** | P1 | `_merge_transition_weights()` 融合分类权重 + 指数衰减迁移权重 | 过渡期平滑 |
| **KS 迁移显著性检验** | P2 | `scipy.stats.ks_2samp` + BH-FDR 校正 (T4 v3.0.0, 默认; Bonferroni 向后兼容)，过滤噪声迁移 | 假阳性可控, 检测力提升 |
| **`importlib` 上下文管理器** | P2 | `_temp_sys_path` 替代 `sys.path.insert`，异常安全恢复 | 全局状态隔离 |

**测试**: 229 测试，222 通过，3 既有失败，无新增回归。

### v2.0.0 智能自适应流水线（2026.05）

| 新增特性 | 说明 | 影响 |
|---------|------|------|
| **因子指纹诊断层** | 13维统计指标自动诊断因子时序/截面特征 | 替代人工判断，客观分类 |
| **自适应因子分类** | 静态 / 动态 / 混合 三类自动分流 | 不同类型走不同处理流程 |
| **语义-统计融合** | 自然语言构造规则 + 统计指纹的贝叶斯融合 | 先验知识降低数据依赖 |
| **三重中性化** | 原始值中性化 → AR建模 → 残差中性化 | 解决传统方法内生性缺陷 |
| **GARCH 白化（可选）** | 对高自相关静态因子消除波动率聚集 | 默认关闭，显式启用 |
| **处理顺序调整** | 静态/混合因子：先中性化后标准化 | 符合 Barra/MSCI 最佳实践 |
| **持续迁移监测** | 因子风格漂移自动告警 | 生命周期管理 |
| **GarchWhiteningAdapter** | 新增适配器，复用现有 PipelineStep 模式 | 最小侵入式扩展 |

### v1.0 → v2.0 → v2.1 → v2.2 → v2.4.0 → v2.5.0 架构演进

```
v1.0: 单一固定流程
原始因子 → 插补 → 去极值 → 变换 → 标准化 → 中性化

v2.0: 智能自适应流程
原始因子 → 指纹提取 → 分类(语义+统计) → 分流处理 → 迁移监测
                ↓
        ┌───────┼───────┐
        ↓       ↓       ↓
    静态管道  动态管道  混合管道
    (高AR1)  (低AR1)  (中AR1)

v2.1: 概率加权软路由 + KS 统计过滤
原始因子 → 指纹提取 → 概率加权 → 多管道混合 → KS 验证 → 输出
                ↓
        权重: 0.70 static + 0.20 mixed + 0.10 dynamic → 加权融合

v2.2: 回测引擎集成 + 全链路闭环
原始因子 → Pipeline → 处理因子
                ↓
         DataBridge → Engine → HealthMonitor → UnifiedDrift
                ↓
         IC/ICIR/Decay/Turnover + 5维健康度 + 融合漂移判定

v2.2.2: 漂移检测与优化器改进
滚动KS + p值过滤 → 三模式融合 (and/or/max)
优化器: Pipeline-in-the-loop + CV train-fit/test-transform (无 look-ahead)
数据适配: per-factor min_dates + reindex 对齐 (Barra 41天 vs 日频 1212天)

v2.3.0: CI 矩阵 + 双轨 CI
GitHub Actions (Python 3.10/3.11/3.12 × ubuntu) + tox 本地跨版本验证

v2.4.0: 外部模块内化 (ADR-019)
5 个处理模块内化到 modules/: Fingerprint / Decoupler / AdaptiveWinsor / Imputer / Neutralizer
保留外部数据边界: Factor_DB / Factor_Trading
632 测试零回归, CI monorepo 模拟从 7 个外部模块缩减为 2 个

v2.5.0: 多因子正交化三层架构 (已实施)
Layer 1 (per-factor) → Layer 2 (cross-factor 正交化) → Layer 3 (target-aware 检验)
  对称正交化 (Löwdin) / Ridge / PCA / GS / Cholesky
  双重 Lasso (treatment 轮询) + Elastic Net
  默认 enabled=False, 不影响 632 基线
  860 测试零回归 (O1-O6 全部完成, 127 单元测试 + 101 手工校验)

v2.6.0: 优化器与漂移检测增强 (已实施)
  E1-E9 9 阶段 TDD (~58 新测试, 918 passed + 6 skipped)
  ADR-021 目标函数对齐 ADR-004 (health_penalty 代理方案 B)
  ADR-022 搜索空间扩展 (正交化参数, search_orth=False 默认)
  ADR-023 阈值漂移监测 (ThresholdDriftMonitor, EWMA 衰减检测)
  目标函数 6 项: IC - λ_vol·vol - λ_cov·cov - λ_fid·ks_distortion
                - λ_health·health - λ_red·redundancy
  Layer 3 显著性验证 (Belloni 2014 PDS Lasso + HC3 + BH)

v3.0.0 T4: KS 迁移检测 BH-FDR 替代 Bonferroni (已实施)
  E1-E3 3 阶段 TDD (+16 新测试, 934 passed + 6 skipped)
  ADR-002a supersede ADR-002 校正方法 (Bonferroni → BH-FDR 默认)
  _ks_migration_significance 三路径分流 (BH/Bonferroni/none)
  字段隔离 + 向后兼容 + 黄金参考校验
  Benjamini-Hochberg (1995) FDR 控制, 检测力提升
  v3.0.0 远期 4 项任务 (T1-T4) 中 T4 (P0) 已完成
```

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│              FactorProcessingPipelineV2                          │
│                 (智能编排层 Orchestrator)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              前置智能层 (Intelligence Layer)              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │   │
│  │  │  Fingerprint│  │  Classifier │  │Semantic-Statistical│ │   │
│  │  │  Extractor  │  │  (AR1-based)│  │    Fusion         │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────────┘ │   │
│  │         └─────────────────┘                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              类型路由层 (Type Router)                     │   │
│  │         STATIC    DYNAMIC    MIXED                       │   │
│  │            ↓         ↓         ↓                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              差异化处理层 (Processing Layer)              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │   │
│  │  │StaticPipeline│  │DynamicPipeline│  │MixedPipeline│    │   │
│  │  │  非线性变换   │  │ 三重中性化   │  │ 条件性变换   │    │   │
│  │  │  可选GARCH   │  │ AR解耦       │  │ 温和缩尾     │    │   │
│  │  │  中性化→标准化│  │ 标准化       │  │ 中性化→标准化│    │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              持续监测层 (Monitoring Layer)                │   │
│  │         FactorFingerprintMonitor                         │   │
│  │         - 类型迁移检测                                    │   │
│  │         - 风格漂移告警                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 四大核心组件

| 组件 | 职责 | 独特价值 |
|------|------|---------|
| **PipelineOrderValidator** | 校验处理步骤顺序 | 开源社区完全空白领域 |
| **Adapter Layer** | 统一模块接口 | sklearn-style 封装 |
| **FactorFingerprint** | 13维因子诊断 | 从经验判断到数据驱动 |
| **SemanticStatisticalFusion** | 语义+统计融合分类 | 先验引导，后验校准 |

---

## 模块组成

### 子模块 1: Factor Imputer v2.0

| 属性 | 详情 |
|------|------|
| **主题风格** | OpenClaw (蓝紫) |
| **核心类** | `HierarchicalImputer` |
| **插补策略** | 5种：截面均值/时序前向/面板分层/ML高级/因子专属 |
| **缺失检测** | MCAR/MAR/MNAR 类型识别 + 缺失模式分析 |
| **特色** | Lookahead-Free 设计，向量化执行 |

### 子模块 2: Factor AdaptiveWinsor v2.0

| 属性 | 详情 |
|------|------|
| **主题风格** | CLI Arcade (绿色) |
| **核心类** | `SmartOutlierDetector` / `AdaptiveTransformer` / `AdaptiveStandardizer` |
| **去极值方法** | 6种自动选择：分位数/Z-score/MAD/IQR/自适应/Sigmoid |
| **变换方法** | Box-Cox / Yeo-Johnson / 分位数变换，自适应选择 |
| **标准化** | Z-score / Rank / MinMax / Robust，统计量投票 |

### 子模块 3: Factor Neutralizer v2.0

| 属性 | 详情 |
|------|------|
| **主题风格** | Synthwave (粉橙日落) |
| **核心类** | `FactorNeutralizer` |
| **中性化类型** | 行业中性化 / 市值中性化 / 指数中性化 |
| **回归方法** | OLS / WLS / Ridge，截面回归残差提取 |

### 新增子模块 4: Factor_Fingerprint

| 属性 | 详情 |
|------|------|
| **核心类** | `FactorFingerprinter` / `AdaptiveFactorClassifier` / `SemanticStatisticalFusion` |
| **指纹维度** | 13维：AR(1)、秩自相关、半衰期、波动率聚集、偏度、峰度等 |
| **分类方法** | AR(1)阈值法 + 贝叶斯融合（支持语义先验） |
| **监测功能** | 类型迁移检测、风格漂移告警 |

### 新增子模块 5: Factor_Decoupler

| 属性 | 详情 |
|------|------|
| **核心类** | `CompositeDecoupler` / `AROrderSelector` / `DualNeutralizer` |
| **解耦方法** | AR模型 / 一阶差分 / HP滤波 / 自动选择 |
| **双重中性化** | 原始值中性化 → AR建模 → 残差中性化 |
| **学术依据** | Hausman (1978) 内生性理论 |

---

## 三条差异化管道

### 管道 1: StaticFactorPipeline（静态因子）

**适用条件**: `ar1_median > 0.80` 且 `rank_autocorr > 0.70`
**典型代表**: 市净率(PB)、市盈率(PE)、股息率

```
原始因子
    ↓
缺失值插补 (Imputation)
    ↓
去极值 (Outlier Detection)
    ↓
自适应非线性变换 (Transformation)
    ↓
[可选] GARCH白化 (GarchWhiteningAdapter)  ← 默认关闭
    ↓
中性化 (Neutralization)                      ← v2.0调整：先中性化
    ↓
标准化 (Standardization)                     ← v2.0调整：后标准化
    ↓
处理完成
```

**为何这样处理**:
- 静态因子的价值在截面排序，非线性变换可有效驯服厚尾和偏态
- 高自相关性意味着 GARCH 预白化可能有必要（消除波动率聚集）
- **v2.0 调整**: 先中性化后标准化，符合 Barra/MSCI 最佳实践

**GARCH 白化启用方式**:
```python
pipeline = StaticFactorPipeline(
    neutralizer_params={'industry_data': industry_series},
    enable_garch=True,  # 显式启用
    garch_params={'p': 1, 'q': 1, 'vol': 'Garch', 'min_obs': 50}
)
```

---

### 管道 2: DynamicFactorPipeline（动态因子）

**适用条件**: `ar1_median < 0.40`
**典型代表**: 短期反转、换手率变化、波动率变化

```
原始因子
    ↓
缺失值插补 (Imputation)
    ↓
原始值双重中性化 (Dual Neutralization Stage 1)
    ↓
AR建模 → 残差提取 (AR Decoupling)
    ↓
残差中性化 (Dual Neutralization Stage 2)
    ↓
标准化 (Standardization)
    ↓
处理完成
```

**为何这样处理**:
- 动态因子的价值在时序变化，**禁止非线性变换**以保护时序信号
- 中性化必须在原始值阶段进行以剥离内生性暴露（第一重中性化）
- AR 建模后再进行第二重中性化以剥离残差中的行业/市值暴露
- **绝对禁止 GARCH 白化**，因为已接近白噪声的序列再做波动率标准化会引入新噪声

---

### 管道 3: MixedFactorPipeline（混合因子）

**适用条件**: `0.40 <= ar1_median <= 0.80`
**典型代表**: 1个月动量、3个月动量

```
原始因子
    ↓
缺失值插补 (Imputation)
    ↓
温和去极值 (3σ缩尾)
    ↓
[条件性] 非线性变换 (Conditional Transformation)
    ↓
中性化 (Neutralization)                      ← v2.0调整：先中性化
    ↓
标准化 (Standardization)                     ← v2.0调整：后标准化
    ↓
处理完成
```

**为何这样处理**:
- 这类因子介于两者之间，最保守的策略是降级处理
- 只做温和缩尾和中性化，条件性做非线性变换（根据偏度/峰度阈值判断）
- 宁可保留一些原始噪声，也不冒险破坏其信号结构

---

## 处理顺序校验

### 校验规则（学术级）

```python
DEPENDENCIES = {
    OUTLIER_DETECTION: [IMPUTATION],
    TRANSFORMATION:    [IMPUTATION, OUTLIER_DETECTION],
    STANDARDIZATION:   [IMPUTATION, OUTLIER_DETECTION],
    NEUTRALIZATION:    [IMPUTATION],
}
```

| 规则 | 原因 |
|------|------|
| **IMPUTATION 必须在第一步** | 去极值的统计量（MAD/分位数）需要完整数据 |
| **OUTLIER 必须在 TRANSFORM 之前** | 极值会严重扭曲变换参数估计 |
| **OUTLIER 必须在 STANDARDIZE 之前** | 极值会显著影响标准化后的分布 |
| **NEUTRALIZATION 顺序因类型而异** | 静态/混合：先中性化后标准化；动态：中性化在 AR 之前 |

### v2.0 顺序调整说明

**v1.0 顺序**（所有因子统一）:
```
插补 → 去极值 → 变换 → 标准化 → 中性化
```

**v2.0 顺序**（因类型而异）:
```
静态/混合: 插补 → 去极值 → 变换 → 中性化 → 标准化
动态:      插补 → 中性化 → AR建模 → 残差中性化 → 标准化
```

**调整原因**:
- 静态因子的标准化应基于中性化后的残差，避免行业/市值暴露影响标准化基准
- 动态因子的中性化必须在 AR 建模之前，以控制内生性（Hausman, 1978）

---

## 与开源社区对比

### 主流量化框架分析

| 项目 | Stars | 数据处理覆盖 | 因子分类 | 顺序校验 | 语义融合 | 活跃度 |
|------|-------|-------------|---------|---------|---------|--------|
| **Microsoft Qlib** | 29.2k | ⭐⭐⭐⭐⭐ | ❌ 无 | ❌ 无 | ❌ 无 | 极高 |
| **Quantopian Alphalens** | 3.8k | ⭐⭐ | ❌ 无 | ❌ 无 | ❌ 无 | 停滞 |
| **Zipline** | 17k | ⭐⭐ | ❌ 无 | ❌ 无 | ❌ 无 | 停滞 |
| **本 Pipeline v2.0** | - | ⭐⭐⭐⭐⭐ | ✅ **独有** | ✅ **独有** | ✅ **独有** | 活跃 |

### 功能深度对比

| 功能 | 本 Pipeline v2.0 | Qlib | Alphalens |
|------|-----------------|------|-----------|
| 缺失值插补 | ✅ 5策略分层智能插补 | ⚠️ 简单填充/删除 | ❌ 无 |
| 自适应去极值 | ✅ 6方法智能选择 | ⚠️ 仅Tanh压缩 | ❌ 无 |
| 分布变换 | ✅ 自适应Box-Cox/YJ | ❌ 无 | ❌ 无 |
| 标准化 | ✅ 统计量投票选择 | ✅ Z-score/Rank | ❌ 无 |
| 中性化 | ✅ 行业/市值/指数 | ❌ 无 | ❌ 无 |
| **因子指纹分类** | ✅ **13维诊断+自适应分类** | ❌ 无 | ❌ 无 |
| **语义-统计融合** | ✅ **先验引导+后验校准** | ❌ 无 | ❌ 无 |
| **三重中性化** | ✅ **原始值→残差双重** | ❌ 无 | ❌ 无 |
| **GARCH白化** | ✅ **可选预白化** | ❌ 无 | ❌ 无 |
| **顺序校验** | ✅ **学术级校验器** | ❌ 无 | ❌ 无 |
| **迁移监测** | ✅ **风格漂移检测** | ❌ 无 | ❌ 无 |

### 核心边际贡献

1. **因子指纹诊断系统** — 开源社区完全空白，将因子分类从经验判断提升为数据驱动
2. **语义-统计融合** — 引入自然语言构造规则作为先验，降低数据依赖和过拟合风险
3. **三重中性化** — 解决传统单一中性化的内生性缺陷（Hausman, 1978）
4. **处理顺序自适应** — 不同类型因子走不同流程，而非一刀切
5. **GARCH 白化选项** — 为高自相关静态因子提供波动率聚集消除能力

---

## 快速开始

### 方式 1: v2.0 智能流水线（推荐）

```python
from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
from Factor_Fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

# 配置
config = PipelineV2Config(
    fingerprint=FingerprintConfig(min_window=24),
    classification=ClassificationConfig(),
    monitor=MonitorConfig(),
    dynamic_decorrelation_strength=1.0,
    dynamic_max_ar_order=5,
    dynamic_ar_criterion='aic',
    static_enable_garch=False,  # 默认关闭，需要时启用
)

# 创建流水线
pipeline = FactorProcessingPipelineV2(config)

# 拟合（支持语义描述）
descriptions = {
    'pb_factor': '市净率因子，基于最新财报账面价值除以总市值',
    'reversal_factor': '过去1个月日收益率的相反数',
    'momentum_factor': '过去12个月扣除最近1个月后的累积收益率',
}

pipeline.fit(
    factor_data={'pb_factor': pb_df, 'reversal_factor': rev_df, 'momentum_factor': mom_df},
    industry_data=industry_series,
    descriptions=descriptions,  # 可选：启用语义-统计融合
)

# 变换
results = pipeline.transform(factor_data)

# 查看分类结果
print(pipeline.get_classification_summary())

# 检查迁移
alerts = pipeline.check_migrations(factor_data)
```

### 方式 2: 单独使用三条管道

```python
from factor_pipeline.pipelines_v2 import (
    StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
)

# 静态因子管道（可选启用 GARCH）
static_pipe = StaticFactorPipeline(
    neutralizer_params={'industry_data': industry_series},
    enable_garch=True,  # 显式启用 GARCH 白化
    garch_params={'p': 1, 'q': 1, 'min_obs': 50}
)
result = static_pipe.fit_transform(pb_data)

# 动态因子管道（三重中性化）
dynamic_pipe = DynamicFactorPipeline(
    decorrelation_strength=1.0,
    max_ar_order=5,
    ar_criterion='aic',
    neutralizer_params={'industry_data': industry_series}
)
result = dynamic_pipe.fit_transform(reversal_data)

# 混合因子管道
mixed_pipe = MixedFactorPipeline(
    conditional_transform=True,
    skew_threshold=2.0,
    kurt_threshold=5.0,
    neutralizer_params={'industry_data': industry_series}
)
result = mixed_pipe.fit_transform(momentum_data)
```

### 方式 3: v1.0 兼容模式（固定五步法）

```python
from factor_pipeline import FactorProcessingPipeline

# 创建默认流水线
pipeline = FactorProcessingPipeline.default_pipeline()
result = pipeline.fit_transform(factor_data)
```

### 方式 4: Backtest 回测引擎 (v2.2.0 新增)

```python
from factor_pipeline.backtest import (
    FactorBacktestEngine, DataBridge, HealthMonitorAdapter,
    UnifiedDriftReporter, PipelineBacktestRunner
)
from factor_pipeline.config_v2 import PipelineV2ConfigUnified, BacktestConfig

# 配置
config = PipelineV2ConfigUnified(
    backtest=BacktestConfig(
        ic_method="rank",
        top_n=0.2,
        enable_drift_detection=True,
        enable_health_check=True,
    )
)

# 端到端运行
runner = PipelineBacktestRunner(config)
results = runner.run(factor_data, price_data, factor_names=["pb_factor", "reversal"])
print(runner.summary())

# 单独使用回测引擎
engine = FactorBacktestEngine(dataloader)
engine.run()
print(engine.summary())  # IC/ICIR/Decay/HitRate/Turnover/LS/Spread

# 健康度评估
adapter = HealthMonitorAdapter()
report = adapter.build_report_from_engine(engine, "pb_factor")
print(report.health_score)  # 0-100 综合健康分

# 漂移检测
drift = UnifiedDriftReporter()
result = drift.evaluate_from_engine(engine, "pb_factor", historical_data)
print(result.level)  # stable / warning / drift_detected / severe_drift
```

---

## 配置说明

### PipelineV2Config 完整配置

```python
@dataclass
class PipelineV2Config:
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    
    # 动态因子解耦参数
    dynamic_decorrelation_strength: float = 1.0   # AR残差提取强度 [0, 1]
    dynamic_max_ar_order: int = 5                  # 最大AR阶数
    dynamic_ar_criterion: str = 'aic'              # 阶数选择准则: aic/bic/hqic
    
    # 混合因子参数
    mixed_conditional_transform: bool = True       # 是否条件性变换
    mixed_skew_threshold: float = 2.0              # 偏度阈值
    mixed_kurt_threshold: float = 5.0              # 峰度阈值
    
    # 静态因子 GARCH 参数（默认关闭）
    static_enable_garch: bool = False              # 是否启用 GARCH 白化
    static_garch_p: int = 1                        # GARCH p 阶
    static_garch_q: int = 1                        # GARCH q 阶
    static_garch_vol: str = 'Garch'                # 波动率模型
    static_garch_min_obs: int = 50                 # 最小观测数
```

---

## API 参考

### FactorProcessingPipelineV2

| 方法 | 说明 |
|------|------|
| `fit(factor_data, industry_data, descriptions)` | 拟合整个流水线（含指纹提取、分类、管道初始化） |
| `transform(factor_data)` | 应用流水线变换 |
| `fit_transform(factor_data, industry_data)` | 拟合并变换 |
| `get_classification_summary()` | 获取分类汇总表 |
| `get_fingerprint_summary()` | 获取指纹汇总表 |
| `check_migrations(factor_data)` | 检查因子类型迁移 |
| `get_execution_summary()` | 获取执行摘要 |

### StaticFactorPipeline

| 方法 | 说明 |
|------|------|
| `fit(X, **kwargs)` | 拟合管道（插补→去极值→变换→[GARCH]→中性化→标准化） |
| `transform(X)` | 应用管道变换 |
| `fit_transform(X)` | 拟合并变换 |

### DynamicFactorPipeline

| 方法 | 说明 |
|------|------|
| `fit(X, **kwargs)` | 拟合管道（插补→三重中性化→标准化） |
| `transform(X)` | 应用管道变换 |
| `fit_transform(X)` | 拟合并变换 |
| `get_decoupling_summary()` | 获取解耦摘要（含AR模型信息） |

### GarchWhiteningAdapter

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `p` | ARCH 阶数 | 1 |
| `q` | GARCH 阶数 | 1 |
| `vol` | 波动率模型 | 'Garch' |
| `min_obs` | 最小观测数 | 50 |

---

## 文件结构

```
factor_pipeline/
├── __init__.py                 # 包入口
├── config.py                   # v1.0 配置管理 (StepType, PipelineConfig)
├── config_v2.py                # v2.0 Pydantic 配置管理 (PipelineV2ConfigUnified)
├── adapters.py                 # 统一适配器层
│   ├── PipelineStep            # 抽象基类
│   ├── ImputerAdapter          # 插补适配器 (REQUIRED)
│   ├── ProcessingAdapter       # 处理适配器 (去极值/变换/标准化, REQUIRED)
│   ├── NeutralizerAdapter      # 中性化适配器 (REQUIRED, ADR-018 fit/transform 语义一致)
│   └── GarchWhiteningAdapter   # GARCH 白化适配器 (OPTIONAL, arch 依赖)
├── pipeline.py                 # v1.0 核心流水线 + 顺序校验器
├── pipelines_v2.py             # v2.0 智能流水线 (指纹+分类+三条管道+软路由)
├── optimizer.py                # v2.2.1 优化器 (Pipeline-in-the-loop + CV)
├── dag.py                      # 有向无环图依赖管理
├── cache.py                    # 中间结果缓存
├── reporting.py                # 执行报告生成
├── performance.py              # 性能优化工具
├── exceptions.py               # 自定义异常体系
├── types.py                    # 核心类型系统
├── pyproject.toml              # 项目配置 (flat-layout, where=[".."])
├── tox.ini                     # 双轨 CI 本地配置 (ADR-017)
├── .github/workflows/ci.yml    # GitHub Actions CI 矩阵
├── docs/                       # 文档目录
│   ├── EXECUTION_V2.5.0.md     # v2.5.0 执行方案 v1.1 (40 深化子章节)
│   ├── ANALYSIS_V2.5.0.md      # v2.5.0 方案分析报告
│   ├── EXECUTION_V2.4.0.md     # v2.4.0 执行记录
│   ├── KABC_paper_draft.md     # KABC 论文草稿
│   └── ...                     # 其他分析文档
├── backtest/                   # 回测引擎模块 (v2.2.0, ADR-007)
│   ├── factor_metrics.py       # 因子级指标单一真相源 (IC/ICIR/Decay/Turnover)
│   ├── data_bridge.py          # Pipeline → DataLoaderV3 适配器
│   ├── engine.py               # 因子回测引擎
│   ├── health_bridge.py        # 回测 → FactorHealthMonitor 适配器
│   ├── unified_drift.py        # 双轨融合漂移判定 (滚动 KS + EWMA)
│   ├── pipeline_integration.py # 端到端 Pipeline 集成
│   ├── cache_manager.py        # L2 磁盘缓存基础设施 (ADR-008)
│   ├── cached_data_loader.py   # 缓存统一入口
│   ├── factor_cache.py         # 因子矩阵缓存 (部分命中)
│   ├── price_cache.py          # 价格矩阵缓存
│   ├── fwd_returns_cache.py    # 前向收益缓存
│   ├── factor_pivot.py         # DuckDB PIVOT 因子宽表转换
│   ├── parallel_runner.py      # 多因子进程并行 (按日期分组)
│   └── __init__.py             # 26 个公开 API 导出
├── modules/                    # 内化处理模块 (v2.4.0, ADR-019)
│   ├── factor_fingerprint/     # 因子指纹 (13维统计指标)
│   ├── factor_decoupler/       # 时序解耦 (AR 建模 + 残差中性化)
│   ├── factor_adaptive_winsor/ # 自适应缩尾 (仅 core/ 最小子包化)
│   ├── factor_imputer/         # 因子插补 (无前瞻偏差)
│   └── factor_neutralizer/     # 因子中性化 (38 方法, 仅内化类不实例化)
├── scripts/                    # 辅助脚本
│   ├── check_trading_v3.py
│   ├── verify_p3_manual.py
│   └── verify_td1_manual.py
├── tests/                      # 测试目录 (632+ 测试)
│   ├── unit/                   # 单元测试
│   ├── test_backtest/          # 回测模块测试
│   ├── test_fix1-7_*.py        # v2.2.2 代码质量修复测试
│   ├── test_p0-p3_*.py         # v2.1/v2.2 改进测试
│   └── verify_*_manual.py      # 手工数值校验脚本
└── README.md                   # 本文档
```

---

## 技术特性

- **sklearn-style 接口**: 统一的 `fit/transform/fit_transform` 模式
- **配置化流程**: 支持 JSON/YAML/字典配置
- **严格顺序校验**: 基于学术规则的自动化校验
- **中间状态追踪**: 每步的输入/输出形状、缺失率、统计量
- **错误拦截**: 错误顺序在初始化阶段即被拦截
- **回退机制**: 子模块缺失时自动降级为简单实现
- **语义融合**: 支持自然语言描述作为分类先验
- **迁移监测**: 因子风格漂移自动检测与告警
- **GARCH 白化**: 可选的波动率聚集消除（默认关闭）

---

## 版本信息

- **Pipeline 版本**: v3.0.0 T4 (已实施, 934 passed + 6 skipped + 11 subtests)
- **内化模块**: factor_fingerprint / factor_decoupler / factor_adaptive_winsor / factor_imputer / factor_neutralizer / factor_orthogonalizer (v2.4.0 ADR-019 + v2.5.0 ADR-020)
- **外部数据边界**: Factor_DB / Factor_Trading (DataLoaderV3)
- **测试基线**: 934 passed, 6 skipped, 0 failed
- **CI 矩阵**: Python 3.10/3.11/3.12 × ubuntu-latest (ADR-017)
- **构建日期**: 2026.07.04
- **状态**: STABLE (v3.0.0 T4)

### 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026.05.12 | 初始版本：统一编排层 + 顺序校验 |
| v2.0.0 | 2026.05.17 | 智能版本：指纹诊断 + 自适应分类 + 语义融合 + 三重中性化 + GARCH白化 |
| v2.1.0 | 2026.07.01 | 架构修复：软路由 + 阈值校准 + 统一 fit() + 适配器 Warning + KS 显著性 + importlib 重构 |
| v2.2.0 | 2026.07.01 | Backtest 集成：回测引擎 (95/95) + 双轨漂移融合 + HealthMonitor 适配器 + BacktestConfig |
| v2.2.1 | 2026.07.01 | 漂移检测改进 + L2 缓存层 (ADR-008, 4.36x 加速) + 优化器 Pipeline-in-the-loop + CV 消除 look-ahead |
| v2.2.2 | 2026.07.02 | 代码质量修复 7 项 (self.factors bug / 配置统一 / 版本号统一 / backtest 导出 / core 命名空间隔离 / 硬编码路径配置化) |
| v2.3.0 | 2026.07.02 | CI 矩阵 (Python 3.10/3.11/3.12 × ubuntu, ADR-017) + tox 双轨 CI + CI 配置脚本校验 (37/37) |
| v2.4.0 | 2026.07.03 | 外部模块内化 (5 模块 → modules/, ADR-019) + 命名统一小写蛇形 + 依赖裁剪 + 632 测试零回归 |
| v2.5.0 | 2026.07.03 | 多因子正交化三层架构 (ADR-020, O1-O6 全部完成): Layer 2 横截面正交化 (5 种算法) + Layer 3 双重 Lasso 检验 + 滚动/分组/三件套, 860 passed + 5 skipped |
| v2.6.0 | 2026.07.04 | 优化器与漂移检测增强 (ADR-021/022/023, E1-E9 全部完成): 目标函数对齐 ADR-004 (6 项 IC-vol-cov-ks-health-redundancy) + 正交化参数搜索空间 + Layer 3 显著性验证 (Belloni 2014 PDS) + ThresholdDriftMonitor (EWMA 衰减检测), 918 passed + 6 skipped + 11 subtests |
| v3.0.0 T4 | 2026.07.04 | KS 迁移检测 BH-FDR 替代 Bonferroni (ADR-002a, E1-E3 全部完成): `_ks_migration_significance` 三路径分流 (BH/Bonferroni/none, 默认 BH) + 字段隔离 + 向后兼容 + 黄金参考校验, Benjamini-Hochberg (1995) FDR 控制, 934 passed + 6 skipped + 11 subtests |

---

## 学术依据

本流水线的处理顺序与分类逻辑基于以下学术与业界标准：

- Barra 多因子模型数据处理规范
- MSCI 因子标准化最佳实践
- Quantopian 因子研究框架
- Hausman (1978) 内生性检验与工具变量理论
- Engle (1982) ARCH/GARCH 波动率建模
- Box & Cox (1964) 变换理论
- 《Quantitative Equity Portfolio Management》(Qian et al.)
- 《Active Portfolio Management》(Grinold & Kahn)
- Löwdin (1950) 对称正交化 (v2.5.0 Layer 2 主方法)
- Ledoit & Wolf (2004) 协方差矩阵收缩估计 (v2.5.0 Ridge λ 自适应)
- Kahan (1966) Gram-Schmidt 二次投影数值稳定性 (v2.5.0 GS re-orth)
- Belsley, Kuh & Welsch (1980) 条件数诊断与共线性分析 (v2.5.0 几何诊断)
- Belloni & Chernozhukov (2013) 双重 Lasso 选择推断 (v2.5.0 Layer 3 显著性检验)
