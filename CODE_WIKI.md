# Factor Processing Pipeline — Code Wiki

> **版本**: v3.2.0 | **构建日期**: 2026-07-10 | **状态**: STABLE (学术准则驱动重构完成)
> **GitHub**: https://github.com/StormstoutLau/factor_pipeline
> **作者**: Scott (Peng Liu)

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构](#3-目录结构)
4. [核心模块详解](#4-核心模块详解)
   - [4.1 `types.py` — 核心类型系统](#41-typespy--核心类型系统)
   - [4.2 `config.py` — v1.0 配置管理](#42-configpy--v10-配置管理)
   - [4.3 `config_v2.py` — v2.0 Pydantic 配置管理](#43-config_v2py--v20-pydantic-配置管理)
   - [4.4 `exceptions.py` — 自定义异常体系](#44-exceptionspy--自定义异常体系)
   - [4.5 `adapters.py` — 统一适配器层](#45-adapterspy--统一适配器层)
   - [4.6 `dag.py` — 有向无环图（DAG）](#46-dagpy--有向无环图dag)
   - [4.7 `pipeline.py` — v1.0 核心流水线](#47-pipelinepy--v10-核心流水线)
   - [4.8 `pipelines_v2.py` — v2.0 智能流水线](#48-pipelines_v2py--v20-智能流水线)
   - [4.9 `cache.py` — 中间结果缓存](#49-cachepy--中间结果缓存)
   - [4.10 `performance.py` — 性能优化工具](#410-performancepy--性能优化工具)
   - [4.11 `reporting.py` — 执行报告生成](#411-reportingpy--执行报告生成)
   - [4.12 `modules/statistical_classifier` — 形式统计因子分类器 (NEW v3.2.0)](#412-modulesstatistical_classifier--形式统计因子分类器)
5. [依赖关系图](#5-依赖关系图)
6. [外部子模块依赖](#6-外部子模块依赖)
7. [项目运行方式](#7-项目运行方式)
8. [测试体系](#8-测试体系)
9. [API 完整参考](#9-api-完整参考)
10. [学术依据](#10-学术依据)

---

## 1. 项目概述

**Factor Processing Pipeline** 是一个面向量化投资领域的统一因子处理编排系统。它将三个独立的因子处理模块（Factor_Imputer_v2.0、Factor_AdaptiveWinsor、Factor_Neutralizer_v2.0）整合为统一的处理流程，并提供 sklearn 风格的 `fit/transform/fit_transform` 接口。

### v2.0 核心特性

| 特性 | 说明 |
|------|------|
| **因子指纹诊断层** | 21 维核心指纹 (v3.0.0 T1, 13 维基础 + 8 维尾部依赖/体制转换) + 5 维健康度指标（FactorHealthMonitor），自动诊断因子时序/截面/尾部/体制特征 + 拥挤度/效能/容量/衰减/体制敏感性 |
| **自适应因子分类** | 静态 / 动态 / 混合三类自动分流 |
| **语义-统计融合** | 自然语言构造规则 + 统计指纹的贝叶斯融合 |
| **三重中性化** | 原始值中性化 → AR 建模 → 残差中性化 |
| **GARCH 白化（可选）** | 对高自相关静态因子消除波动率聚集 |
| **处理顺序校验** | 基于学术规则的自动化顺序校验 |
| **持续迁移监测** | 因子风格漂移自动告警 |

### v1.0 → v2.0 架构演进

```
v1.0: 单一固定流程
原始因子 → 插补 → 去极值 → 变换 → 标准化 → 中性化

v2.0: 智能自适应流程
原始因子 → 指纹提取 → 分类(语义+统计) → 分流处理 → 迁移监测
                ↓
        ┌───────┼───────┐
        ↓       ↓       ↓
    静态管道  动态管道  混合管道
```

---

## 2. 整体架构

```
                          ┌──────────────────────────────────────┐
                          │          外部输入 (Inputs)             │
                          │  ┌────────────┐  ┌────────────────┐  │
                          │  │ factor_data│  │ industry_data  │  │
                          │  │ Dict[name, │  │ pd.Series      │  │
                          │  │ DataFrame] │  │ (股票→行业)     │  │
                          │  └─────┬──────┘  └───────┬────────┘  │
                          │        │                  │           │
                          │  ┌─────┴──────────────────┴───────┐  │
                          │  │  descriptions: Dict[name, str] │  │
                          │  │  (自然语言因子描述，可选)       │  │
                          │  └────────────────┬───────────────┘  │
                          └───────────────────┼──────────────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              │               FactorProcessingPipelineV2                      │
              │                  (智能编排层 Orchestrator)                      │
              ├───────────────────────────────────────────────────────────────┤
              │                                                               │
              │  ┌─────────────────────────────────────────────────────────┐  │
              │  │              Layer 1: 前置智能层 (Intelligence)          │  │
              │  │                                                         │  │
              │  │  ┌──────────────────────┐    ┌──────────────────────┐   │  │
              │  │  │  FactorFingerprinter │    │ PipelineV2Config      │   │  │
              │  │  │  ─────────────────── │    │ ────────────────────  │   │  │
              │  │  │  • batch_extract()   │    │ • fingerprint_window   │   │  │
              │  │  │  • extract_fingerprint│   │ • classification       │   │  │
              │  │  │                      │    │ • monitor thresholds   │   │  │
              │  │  │  输出: 21维指纹向量   │    │ • pipeline params      │   │  │
              │  │  │  • ar1_median        │    └───────────┬───────────┘   │  │
              │  │  │  • rank_autocorr     │                │               │  │
              │  │  │  • half_life         │                │               │  │
              │  │  │  • sd_score          │                │               │  │
              │  │  │  • complexity_need   │                │               │  │
              │  │  │  • snr_estimate      │                │               │  │
              │  │  │  • skewness_std      │                │               │  │
              │  │  │  • kurtosis_std      │                │               │  │
              │  │  │  • ... (共21维, v3.0.0 T1) │           │               │  │
              │  │  └──────────┬───────────┘                │               │  │
              │  │             │ 指纹向量                     │ 配置          │  │
              │  │             ▼                            ▼               │  │
              │  │  ┌──────────────────────────────────────────────────┐   │  │
              │  │  │         因子分类器 (Classifier)                    │   │  │
              │  │  │  ┌────────────────────┐  ┌────────────────────┐  │   │  │
              │  │  │  │ AdaptiveFactor     │  │ SemanticStatistical │  │   │  │
              │  │  │  │ Classifier         │  │ Fusion              │  │   │  │
              │  │  │  │ ─────────────────  │  │ ─────────────────── │  │   │  │
              │  │  │  │ • classify(fp)     │  │ • classify(desc,fp) │  │   │  │
              │  │  │  │ • batch_classify() │  │ • 贝叶斯先验融合    │  │   │  │
              │  │  │  │ • AR1阈值判定      │  │ • 自然语言→统计校准 │  │   │  │
              │  │  │  └────────┬───────────┘  └────────┬───────────┘  │   │  │
              │  │  │           └───────────┬───────────┘              │   │  │
              │  │  └───────────────────────┼──────────────────────────┘   │  │
              │  └──────────────────────────┼──────────────────────────────┘  │
              │                             │ ClassificationResult             │
              │                             │ • primary_type (STATIC/DYNAMIC/MIXED) │
              │                             │ • primary_prob, confidence       │
              │                             ▼                                 │
              │  ┌─────────────────────────────────────────────────────────┐  │
              │  │         Layer 2: 概率加权软路由 (v2.1 P0-1)            │  │
              │  │                                                         │  │
              │  │   _get_pipeline_weights()  →  ClassificationResult      │  │
              │  │                                 ↓                       │  │
              │  │   _merge_transition_weights()  ←  FactorFingerprintMonitor│  │
              │  │                                 ↓                       │  │
              │  │   _ks_migration_significance() ←  KS 双样本 + BH-FDR    │  │
              │  │                                 ↓                       │  │
              │  │   _apply_weighted_transform()  → 加权混合输出           │  │
              │  │                                                         │  │
              │  │   示例: 0.70*static + 0.20*mixed + 0.10*dynamic         │  │
              │  │   高置信度(>0.90) → 硬路由; 否则 → 软路由               │  │
              │  └─────────────────────────────────────────────────────────┘  │
              │           │                     │                   │         │
              │           ▼                     ▼                   ▼         │
              │  ┌─────────────────────────────────────────────────────────┐  │
              │  │          Layer 3: 差异化处理层 (Processing)              │  │
              │  │                                                         │  │
              │  │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────┐ │  │
              │  │  │StaticPipeline   │ │MixedPipeline    │ │Dynamic     │ │  │
              │  │  │─────────────────│ │─────────────────│ │Pipeline    │ │  │
              │  │  │                 │ │                 │ │────────────│ │  │
              │  │  │ ① ImputerAdapter│ │ ① ImputerAdapter│ │ ① Imputer  │ │  │
              │  │  │    (auto策略)   │ │    (auto策略)   │ │   Adapter  │ │  │
              │  │  │      ↓          │ │      ↓          │ │     ↓      │ │  │
              │  │  │ ② Processing    │ │ ② 温和缩尾      │ │ ② Composite│ │  │
              │  │  │   Adapter       │ │   (3σ clip)     │ │   Decoupler│ │  │
              │  │  │   (outlier)     │ │      ↓          │ │   ┌─────── │ │  │
              │  │  │      ↓          │ │ ③ 条件性变换     │ │   │原始值  │ │  │
              │  │  │ ③ Processing    │ │   (偏度>2.0     │ │   │中性化  │ │  │
              │  │  │   Adapter       │ │    或峰度>5.0)  │ │   │  ↓     │ │  │
              │  │  │   (transform)   │ │      ↓          │ │   │AR建模  │ │  │
              │  │  │      ↓          │ │ ④ Neutralizer   │ │   │  ↓     │ │  │
              │  │  │ ④ [可选] GARCH  │ │   Adapter       │ │   │残差    │ │  │
              │  │  │   Whitening     │ │      ↓          │ │   │中性化  │ │  │
              │  │  │   Adapter       │ │ ⑤ Processing    │ │   └─────── │ │  │
              │  │  │      ↓          │ │   Adapter       │ │     ↓      │ │  │
              │  │  │ ⑤ Neutralizer   │ │   (standardize) │ │ ③ Processing│ │  │
              │  │  │   Adapter       │ │                 │ │   Adapter  │ │  │
              │  │  │      ↓          │ │ 禁止: GARCH     │ │   (standard│ │  │
              │  │  │ ⑥ Processing    │ │ 禁止: AR解耦    │ │    ize)    │ │  │
              │  │  │   Adapter       │ │                 │ │           │ │  │
              │  │  │   (standardize) │ │                 │ │ 禁止: 变换 │ │  │
              │  │  │                 │ │                 │ │ 禁止: GARCH│ │  │
              │  │  └────────┬────────┘ └────────┬────────┘ └─────┬──────┘ │  │
              │  └───────────┼───────────────────┼────────────────┼────────┘  │
              │              │                   │                │           │
              │              └───────────────────┼────────────────┘           │
              │                                  │ 处理后的因子数据             │
              │              ┌───────────────────┘                            │
              │              ▼                                                │
              │  ┌─────────────────────────────────────────────────────────┐  │
              │  │           Layer 4: 持续监测层 (Monitoring)               │  │
              │  │                                                         │  │
              │  │  ┌──────────────────────────────────────────────────┐   │  │
              │  │  │         FactorFingerprintMonitor                  │   │  │
              │  │  │  ──────────────────────────────────────────────── │   │  │
              │  │  │  • add_fingerprint(name, fp)    ← 记录历史指纹    │   │  │
              │  │  │  • check_type_migration(name, fp) ← 类型迁移检测  │   │  │
              │  │  │  • get_factor_stability_score(name) ← 稳定性得分  │   │  │
              │  │  │  • get_transition_weights(name, fp) ← 软过渡权重  │   │  │
              │  │  │  • fingerprint_history: Dict[name, List[fp]]      │   │  │
              │  │  └──────────────────────────────────────────────────┘   │  │
              │  │                                                         │  │
              │  │  ┌──────────────────────────────────────────────────┐   │  │
              │  │  │         FactorHealthMonitor (v1.0 新增)          │   │  │
              │  │  │  ──────────────────────────────────────────────── │   │  │
              │  │  │  • evaluate_health(name, data, returns, mcap)    │   │  │
              │  │  │  • evaluate_health_batch(...) ← 批量评估         │   │  │
              │  │  │  • get_health_trend(name, lookback) ← 趋势追踪   │   │  │
              │  │  │                                                  │   │  │
              │  │  │  五维正交评估 (加权合成 → 综合健康分 [0-100]):    │   │  │
              │  │  │  ┌───────────┬──────┬──────────────────────────┐ │   │  │
              │  │  │  │ 拥挤度    │ 0.25 │ 配对相关性·HHI·换手率    │ │   │  │
              │  │  │  │ 效能      │ 0.35 │ IC IR·IC胜率·IC自相关    │ │   │  │
              │  │  │  │ 容量      │ 0.15 │ 有效N·Top5集中度         │ │   │  │
              │  │  │  │ 衰减      │ 0.15 │ Mann-Kendall趋势·IC斜率  │ │   │  │
              │  │  │  │ 体制敏感性│ 0.10 │ 牛熊IC比·波动率条件IC    │ │   │  │
              │  │  │  └───────────┴──────┴──────────────────────────┘ │   │  │
              │  │  │                                                  │   │  │
              │  │  │  四级警报: HEALTHY · WATCH · WARNING · CRITICAL  │   │  │
              │  │  └──────────────────────────────────────────────────┘   │  │
              │  │                                                         │  │
              │  │  输出:                                                   │  │
              │  │  • MigrationAlert (类型迁移告警)                         │  │
              │  │  • Stability Score (类型稳定性)                          │  │
              │  │  • Transition Weights (软过渡权重)                       │  │
              │  │  • FactorHealthReport (五维健康度报告)                   │  │
              │  └─────────────────────────────────────────────────────────┘  │
              │                                                               │
              └───────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                          ┌──────────────────────────────────────┐
                          │          最终输出 (Outputs)            │
                          │  ┌────────────────────────────────┐   │
                          │  │  Dict[name, pd.DataFrame]      │   │
                          │  │  (处理后的因子数据)              │   │
                          │  └────────────────────────────────┘   │
                          │  ┌────────────────────────────────┐   │
                          │  │  PipelineExecutionSummary       │   │
                          │  │  • 分类汇总 DataFrame           │   │
                          │  │  • 指纹汇总 DataFrame           │   │
                          │  │  • 迁移告警 Dict                │   │
                          │  └────────────────────────────────┘   │
                          └──────────────────────────────────────┘


          ┌─────────────────────────────────────────────────────────┐
          │              底层支撑: 适配器层 (Adapter Layer)           │
          │                                                         │
          │  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐ │
          │  │ ImputerAdapter│  │Processing     │  │Neutralizer  │ │
          │  │               │  │Adapter        │  │Adapter      │ │
          │  │ → Hierarchical│  │ → SmartOutlier│  │ → Factor    │ │
          │  │   Imputer     │  │   Detector    │  │   Neutralizer│ │
          │  │   (动态导入)   │  │ → Adaptive    │  │   (动态导入) │ │
          │  │               │  │   Transformer │  │             │ │
          │  │ 回退: 中位数   │  │ → Adaptive    │  │ 回退: OLS   │ │
          │  │               │  │   Standardizer│  │ 行业哑变量  │ │
          │  │               │  │   (动态导入)   │  │             │ │
          │  │               │  │               │  │             │ │
          │  │               │  │ 回退: 分位数   │  │             │ │
          │  │               │  │ 缩尾 / Z-score│  │             │ │
          │  └───────────────┘  └───────────────┘  └─────────────┘ │
          │                                                         │
          │  ┌───────────────────────────────────────────────────┐  │
          │  │  GarchWhiteningAdapter (v2.0新增, 可选)           │  │
          │  │  → arch.arch_model(GARCH/GJR/EGARCH)              │  │
          │  │  回退: 滚动标准差近似                               │  │
          │  └───────────────────────────────────────────────────┘  │
          └─────────────────────────────────────────────────────────┘


          ┌─────────────────────────────────────────────────────────┐
          │              底层支撑: 基础设施层 (Infrastructure)        │
          │                                                         │
          │  ┌──────────────┐ ┌──────────────┐ ┌────────────────┐  │
          │  │ PipelineDAG  │ │PipelineCache │ │PipelineOrder   │  │
          │  │ (networkx)   │ │ (parquet)    │ │Validator       │  │
          │  │              │ │              │ │                │  │
          │  │ • validate() │ │ • get()      │ │ • validate()   │  │
          │  │ • suggest()  │ │ • set()      │ │ • suggest_     │  │
          │  │ • get_path() │ │ • clear()    │ │   correction() │  │
          │  │ • visualize()│ │ • 采样hash   │ │                │  │
          │  └──────────────┘ └──────────────┘ └────────────────┘  │
          │                                                         │
          │  ┌──────────────┐ ┌──────────────┐ ┌────────────────┐  │
          │  │ reporting.py │ │performance.py│ │ exceptions.py  │  │
          │  │              │ │              │ │                │  │
          │  │ • Report     │ │ • timed()    │ │ • 8种异常类型   │  │
          │  │   (MD/JSON/  │ │ • benchmark()│ │ • 上下文追踪    │  │
          │  │    Text)     │ │ • batch_     │ │ • to_dict()    │  │
          │  │ • Profiler   │ │   process()  │ │   序列化        │  │
          │  └──────────────┘ └──────────────┘ └────────────────┘  │
          └─────────────────────────────────────────────────────────┘


          ┌─────────────────────────────────────────────────────────┐
          │               v1.0 兼容层 (Legacy)                       │
          │                                                         │
          │  ┌──────────────────────────────────────────────────┐   │
          │  │  FactorProcessingPipeline (固定五步法)             │   │
          │  │  插补 → 去极值 → 变换 → 标准化 → 中性化            │   │
          │  │  • default_pipeline() 类方法快速创建               │   │
          │  │  • 支持 JSON/YAML/字典配置                         │   │
          │  └──────────────────────────────────────────────────┘   │
          └─────────────────────────────────────────────────────────┘
```

### 架构分层说明

| 层级 | 名称 | 核心类 | 职责 |
|------|------|--------|------|
| **Layer 1** | 前置智能层 | `FactorFingerprinter`, `AdaptiveFactorClassifier`, `SemanticStatisticalFusion` | 21维核心指纹提取 (v3.0.0 T1, 含尾部依赖/体制转换) + 4层NLP语义理解 → 贝叶斯融合分类 |
| **Layer 2** | 类型路由层 | 内嵌于 `FactorProcessingPipelineV2.fit()` | 根据 AR(1) 阈值将因子分流至三条管道 |
| **Layer 3** | 差异化处理层 | `StaticFactorPipeline`, `DynamicFactorPipeline`, `MixedFactorPipeline` | 按因子类型执行差异化处理流程 |
| **Layer 4** | 持续监测层 | `FactorFingerprintMonitor`, `FactorHealthMonitor` | 类型迁移检测（多时间尺度）+ 五维健康度评估（拥挤度/效能/容量/衰减/体制敏感性） |
| **Adapter** | 适配器层 | `ImputerAdapter`, `ProcessingAdapter`, `NeutralizerAdapter`, `GarchWhiteningAdapter` | 统一封装外部子模块，提供回退方案 |
| **Infrastructure** | 基础设施层 | `PipelineDAG`, `PipelineCache`, `PipelineOrderValidator`, `reporting`, `performance`, `exceptions` | 顺序校验、缓存、报告、性能、异常 |
| **Legacy** | v1.0 兼容层 | `FactorProcessingPipeline` | 向后兼容的固定五步法流水线 |

### 五条核心组件

| 组件 | 所在层 | 职责 | 独特价值 |
|------|--------|------|---------|
| **PipelineOrderValidator** | 基础设施层 | 校验处理步骤顺序 | 开源社区完全空白领域 |
| **Adapter Layer** | 适配器层 | 统一模块接口 + 回退 | sklearn-style 封装，子模块缺失时自动降级 |
| **FactorFingerprint** | 前置智能层 | 21 维核心指纹 (v3.0.0 T1: 13 维基础 + 8 维尾部依赖/体制转换) + 5 维健康度 | 从经验判断到数据驱动，覆盖因子全生命周期 |
| **SemanticStatisticalFusion** | 前置智能层 | 语义 + 统计融合分类 | 先验引导，后验校准，5 种冲突诊断 |
| **FactorHealthMonitor** | 持续监测层 | 五维正交评估：拥挤度/效能/容量/衰减/体制敏感性 | 量化因子健康度的标准化框架 |

### v2.5.0 三层架构 (已实施, ADR-020)

v2.5.0 引入**多因子正交化三层架构分离**, 职责清晰:

| Layer | 职责 | 模块位置 | 监督性 | 状态 |
|-------|------|---------|--------|------|
| **Layer 1** | per-factor 处理 (已有) | `pipelines_v2.py` | 无监督 | 已实施 |
| **Layer 2** | cross-factor 横截面正交化 (新增) | `modules/factor_orthogonalizer/` | 无监督 | 已实施 |
| **Layer 3** | target-aware 显著性检验 (新增) | `backtest/factor_significance.py` | 有监督 (需 Y) | 已实施 |

**Layer 2 核心算法** (5 种):
- **Symmetric (Löwdin)**: 默认主方法, `W = (F^T F)^(-1/2)`, VRR=1, 无顺序依赖
- **Ridge**: 病态矩阵兜底, λ 自适应 (Ledoit-Wolf 2004)
- **PCA**: 降维场景, center 参数兼容 Layer 1 标准化
- **Gram-Schmidt**: 顺序依赖场景, κ>100 启用 Kahan (1966) 二次投影
- **Cholesky**: 半正定保证场景

**Layer 3 显著性检验**:
- **双重 Lasso** (Belloni-Chernozhukov 2014 PDS): treatment 轮询模式, HC3 稳健标准误, BH FDR 校正
- **Elastic Net**: α/λ 网格搜索, 处理多因子共线性

**核心约束**: 正交化默认关闭 (`enabled=False`), 不影响 632 基线测试; Pipeline 不重构, 通过 `post_transform_hooks` 半侵入式接入。

**实施成果** (O1-O6 全部完成, 860 passed + 5 skipped):

| 阶段 | 模块 | 单元测试 | 手工校验 |
|------|------|---------|---------|
| O1 算法核心 | `modules/factor_orthogonalizer/core/` | 44 | 15 |
| O2 适配器 | `adapters.py:OrthogonalizerAdapter` + `cross_sectional.py` | 22 | 12 |
| O3a 几何诊断 | `modules/factor_orthogonalizer/diagnostics.py` | 18 | 24 |
| O3b Layer 3 检验 | `backtest/factor_significance.py` | 17 | 14 |
| O4 回测扩展 | `modules/factor_orthogonalizer/rolling.py` | 11 | 19 |
| O5 协同验证 | `modules/factor_orthogonalizer/grouped.py` + `triple_chain.py` | 15 | 17 |
| O6 文档验证 | `tests/manual/verify_v2_5_0_manual.py` | 0 | 5 |
| **合计** | — | **127** | **106** |

详见 [docs/EXECUTION_V2.5.0.md](docs/EXECUTION_V2.5.0.md) (执行方案 v1.1, 40 个深化子章节)。

#### Layer 2 使用示例 — `factor_orthogonalizer`

**1. 全样本对称正交化 (默认主方法)**:

```python
from factor_pipeline.modules.factor_orthogonalizer.core import SymmetricOrthogonalizer
import numpy as np

# F: (N_stocks, K_factors) 横截面因子矩阵
F = np.random.randn(100, 5)
orth = SymmetricOrthogonalizer()
T = orth.fit_transform(F)  # T^T T ≈ I, VRR=1
```

**2. 通过适配器接入 Pipeline (半侵入式)**:

```python
from factor_pipeline.adapters import OrthogonalizerAdapter
from factor_pipeline.config_v2 import OrthogonalizationConfig

# 默认 enabled=False (零开销, 不影响基线)
config = OrthogonalizationConfig(enabled=True, method='symmetric')
adapter = OrthogonalizerAdapter(config)

# factor_dict: Dict[str, DataFrame], 每个 DataFrame 为 (N_stocks, T_dates)
result = adapter.fit_transform(factor_dict)  # 输出格式与输入一致
```

**3. 滚动正交化 (无 look-ahead bias)**:

```python
from factor_pipeline.modules.factor_orthogonalizer.rolling import RollingOrthogonalizer

# F_panel: (T, N, K) 因子面板
rolling = RollingOrthogonalizer(window_size=252, min_obs=60)
T_result, is_orth = rolling.fit_transform(F_panel)
# is_orth[t] = True 表示该期已正交化 (样本 > min_obs)
# 用 [t-window, t-1] 数据估计 W_t, 应用到 F_t (无 look-ahead)
```

**4. Layer 3 因子显著性检验 (双重 Lasso)**:

```python
from factor_pipeline.backtest.factor_significance import FactorSignificanceTest

test = FactorSignificanceTest(method='double_lasso', cv_folds=5)
test.fit(factor_dict, fwd_returns, factor_names=['f0', 'f1', 'f2'])
result = test.test_incremental_alpha('f0')  # f0 作为 treatment
# result: {coefficient, std_error, t_statistic, p_value, ci_lower, ci_upper, ...}
```

**5. 三件套串联 (Fingerprint → Decoupler → Orthogonalizer)**:

```python
from factor_pipeline.modules.factor_orthogonalizer.triple_chain import TripleChainCoordinator

coordinator = TripleChainCoordinator()
# 描述 (Fingerprint) → 时序解耦 (Decoupler) → 横截面正交化 (Orthogonalizer)
result = coordinator.run_chain(factor_dict, method='symmetric')
```

---

## 3. 目录结构

```
factor_pipeline/
├── __init__.py                  # 包入口，版本号 v2.5.0，统一导出
├── types.py                     # 核心类型系统（Protocol、TypedDict、DataClass）
├── config.py                    # v1.0 配置管理（StepType、PipelineConfig）
├── config_v2.py                 # v2.0 Pydantic 配置管理（统一验证）
├── exceptions.py                # 自定义异常体系（8 种异常类型）
├── adapters.py                  # 统一适配器层（5 个适配器）
│   ├── PipelineStep             # 抽象基类
│   ├── ImputerAdapter           # 插补适配器 (REQUIRED)
│   ├── ProcessingAdapter        # 处理适配器（去极值/变换/标准化, REQUIRED）
│   ├── NeutralizerAdapter       # 中性化适配器 (REQUIRED, ADR-018 fit/transform 语义一致)
│   └── GarchWhiteningAdapter    # GARCH 白化适配器 (OPTIONAL, arch 依赖)
├── dag.py                       # DAG 有向无环图（依赖关系与拓扑排序）
├── pipeline.py                  # v1.0 核心流水线 + 顺序校验器
├── pipelines_v2.py              # v2.0 智能流水线（三条差异化管道 + 软路由 + KS 迁移）
├── optimizer.py                 # v2.6.0 优化器 (Pipeline-in-the-loop + CV + 6 项目标函数 + 正交化搜索 + Layer 3 显著性)
├── cache.py                     # 中间结果缓存（parquet 格式）
├── performance.py               # 性能优化工具（计时/缓存/批量处理/基准测试）
├── reporting.py                 # 执行报告生成（Markdown/JSON/Text）
├── exceptions.py                # 自定义异常体系
├── types.py                     # 核心类型系统
├── pyproject.toml               # 项目配置 (flat-layout, where=[".."], ADR-014)
├── tox.ini                      # 双轨 CI 本地配置 (ADR-017)
├── .github/workflows/ci.yml     # GitHub Actions CI 矩阵 (Python 3.10/3.11/3.12)
├── backtest/                    # 回测引擎模块 (v2.2.0, ADR-007)
│   ├── __init__.py              # 26 个公开 API 导出
│   ├── factor_metrics.py        # 因子级指标单一真相源（IC/ICIR/Decay/Turnover/LS/Spread/HitRate）
│   ├── data_bridge.py           # Pipeline → DataLoaderV3 格式适配器
│   ├── engine.py                # 因子回测引擎（改编自 engine_v3_vector.py）
│   ├── health_bridge.py         # 回测引擎 → FactorHealthMonitor 适配器
│   ├── unified_drift.py         # 双轨融合漂移判定（滚动 KS + EWMA + 三模式融合, T3.5 默认 BH-FDR）
│   ├── cusum_drift_monitor.py   # CUSUM 在线漂移监测 (v3.0.0 T3, Page 1954 双侧递推)
│   ├── multiple_testing.py      # 多重检验校正共享模块 (v3.0.0 T3.5, BH/Bonferroni/None)
│   ├── pipeline_integration.py  # 端到端 Pipeline 集成运行器
│   ├── cache_manager.py         # L2 磁盘缓存基础设施 (ADR-008)
│   ├── cached_data_loader.py    # 缓存统一入口 (一处替换启用缓存)
│   ├── factor_cache.py          # 因子矩阵缓存 (部分命中)
│   ├── price_cache.py           # 价格矩阵缓存
│   ├── fwd_returns_cache.py     # 前向收益缓存
│   ├── factor_pivot.py          # DuckDB PIVOT 因子宽表转换
│   └── parallel_runner.py       # 多因子进程并行 (按日期分组, ADR-009)
├── modules/                     # 内化处理模块 (v2.4.0 ADR-019 + v2.5.0 ADR-020)
│   ├── factor_fingerprint/      # 因子指纹 (21维统计指标 v3.0.0 T1 + 5维健康度)
│   ├── factor_decoupler/        # 时序解耦 (AR 建模 + 残差中性化)
│   ├── factor_adaptive_winsor/  # 自适应缩尾 (仅 core/ 最小子包化)
│   ├── factor_imputer/          # 因子插补 (无前瞻偏差)
│   ├── factor_neutralizer/      # 因子中性化 (38 方法, 仅内化类不实例化)
│   └── factor_orthogonalizer/   # 多因子横截面正交化 (v2.5.0, ADR-020, 5 种算法 + 滚动/分组/三件套)
├── docs/                        # 文档目录
│   ├── EXECUTION_V2.5.0.md      # v2.5.0 执行方案 v1.1 (40 深化子章节)
│   ├── ANALYSIS_V2.5.0.md       # v2.5.0 方案分析报告
│   ├── KABC_paper_draft.md      # KABC 论文草稿
│   └── ...                      # 其他分析文档
├── tests/                       # 测试目录 (632+ 测试)
│   ├── conftest.py              # pytest 共享 fixtures
│   ├── unit/                    # 单元测试
│   ├── test_backtest/           # 回测模块测试
│   ├── test_fix1-7_*.py         # v2.2.2 代码质量修复测试
│   ├── test_p0-p3_*.py          # v2.1/v2.2 改进测试
│   └── verify_*_manual.py       # 手工数值校验脚本
└── README.md                    # 项目主文档
```

---

## 4. 核心模块详解

### 4.1 `types.py` — 核心类型系统

**文件路径**: [types.py](file:///f:/Coding/factor_pipeline/types.py)

定义流水线相关的协议、TypedDict、类型别名和数据类，为整个 factor_pipeline 提供统一的类型系统。

#### 关键类型

| 类型 | 种类 | 说明 |
|------|------|------|
| `PipelineStepProtocol` | Protocol | 流水线步骤协议，所有步骤必须实现 `fit/transform/fit_transform/get_stats` 接口 |
| `StepStats` | TypedDict | 步骤统计信息（名称、类型、形状、缺失率、耗时等） |
| `StepExecutionRecord` | TypedDict | 步骤执行记录（时间戳、形状、缺失率、错误等） |
| `PipelineExecutionSummary` | TypedDict | 流水线执行摘要（总耗时、各步骤记录、分类结果） |
| `NeutralizationSummary` | TypedDict | 中性化摘要（两阶段统计、方法、行业数） |
| `ARModelSummary` | TypedDict | AR 模型摘要（阶数、AIC/BIC、系数、残差标准差） |
| `FactorData` | TypeAlias | `dict[str, pd.DataFrame]` — 因子名到数据的映射 |
| `IndustryData` | TypeAlias | `pd.Series` — 行业分类数据 |
| `MarketCapData` | TypeAlias | `pd.DataFrame` — 市值数据 |
| `FactorDescriptions` | TypeAlias | `dict[str, str]` — 因子名到自然语言描述的映射 |
| `StepOutput` | DataClass | 步骤变换输出（数据 + 统计 + 耗时 + 成功标志） |
| `PipelineOutput` | DataClass | 流水线完整输出（数据 + 摘要 + 步骤结果列表） |

---

### 4.2 `config.py` — v1.0 配置管理

**文件路径**: [config.py](file:///f:/Coding/factor_pipeline/config.py)

支持 YAML/JSON/字典配置的流水线配置系统。

#### 关键类

| 类 | 说明 |
|----|------|
| `StepType` | 枚举：`IMPUTATION` / `OUTLIER_DETECTION` / `TRANSFORMATION` / `STANDARDIZATION` / `NEUTRALIZATION` |
| `StepConfig` | 单个步骤配置（step_type、module_path、class_name、params、enabled），支持 `to_dict()` / `from_dict()` |
| `PipelineConfig` | 流水线完整配置（name、steps、strict_order、allow_skip、track_intermediate），支持 `to_json()` / `from_json()` / `default_config()` |

**默认配置**（标准五步法）:

```
插补(HierarchicalImputer) → 去极值(SmartOutlierDetector)
  → 变换(AdaptiveTransformer) → 标准化(AdaptiveStandardizer)
  → 中性化(FactorNeutralizer)
```

---

### 4.3 `config_v2.py` — v2.0 Pydantic 配置管理

**文件路径**: [config_v2.py](file:///f:/Coding/factor_pipeline/config_v2.py)

基于 Pydantic v2 的类型安全配置系统，提供自动验证、字段约束和序列化功能。

#### 关键类

| 类 | 说明 |
|----|------|
| `ImputationConfig` | 插补配置（strategy、max_missing_ratio） |
| `OutlierConfig` | 去极值配置（method、threshold、上下分位数，含交叉验证） |
| `TransformationConfig` | 变换配置（method、偏度/峰度阈值） |
| `StandardizationConfig` | 标准化配置（method、target_mean、target_std） |
| `NeutralizationConfig` | 中性化配置（method、alpha、行业/市值开关） |
| `GarchConfig` | GARCH 配置（p/q 阶数、波动率模型、最小观测数，含阶数交叉验证） |
| `StaticPipelineConfig` | 静态管道配置（继承所有步骤配置 + neutralize_before_standardize 标志） |
| `DynamicPipelineConfig` | 动态管道配置（强制禁用变换和 GARCH） |
| `MixedPipelineConfig` | 混合管道配置（conditional_transform、mild_winsorization） |
| `PipelineV2ConfigUnified` | 统一配置入口，整合所有子配置 + 指纹/分类/监控参数 |

**工具函数**:
- `load_config_from_json(path)` — 从 JSON 加载配置
- `load_config_from_yaml(path)` — 从 YAML 加载配置
- `save_config_to_json(config, path)` — 保存配置到 JSON
- `save_config_to_yaml(config, path)` — 保存配置到 YAML

---

### 4.4 `exceptions.py` — 自定义异常体系

**文件路径**: [exceptions.py](file:///f:/Coding/factor_pipeline/exceptions.py)

为 factor_pipeline 提供结构化、可追踪的异常处理机制。所有异常均包含上下文信息，便于调试和日志记录。

#### 异常层次结构

```
PipelineError (基类)
├── OrderValidationError      # 处理顺序校验失败
├── StepExecutionError        # 步骤执行失败（含原始异常引用）
├── AdapterImportError        # 适配器导入失败（子模块缺失）
├── ConfigurationError        # 配置参数非法或不一致
├── FactorTypeError           # 因子数据格式不符合要求
├── NeutralizationError       # 中性化失败
├── GarchFittingError         # GARCH 模型拟合失败
└── MigrationAlertError       # 因子迁移告警（非致命，用于告警）
```

**基类 `PipelineError` 公共接口**:
- `to_dict()` — 将异常转换为字典格式（便于 JSON 序列化）
- `__str__()` — 结构化字符串表示，包含错误类型、步骤名、因子名、上下文

---

### 4.5 `adapters.py` — 统一适配器层

**文件路径**: [adapters.py](file:///f:/Coding/factor_pipeline/adapters.py)

将三个独立的 v2.0 子模块统一封装为 `PipelineStep` 接口，是整个流水线的核心适配层。

#### 类层次结构

```
PipelineStep (ABC)                         # 抽象基类
├── ImputerAdapter                         # 插补适配器
├── ProcessingAdapter                      # 处理适配器（三种子类型）
├── NeutralizerAdapter                     # 中性化适配器
└── GarchWhiteningAdapter (v2.0新增)      # GARCH 白化适配器
```

#### `PipelineStep` (抽象基类)

| 方法 | 说明 |
|------|------|
| `__init__(name, step_type, **params)` | 初始化步骤名、类型、参数 |
| `fit(X, **kwargs)` | 拟合步骤参数（抽象方法） |
| `transform(X, **kwargs)` | 应用步骤变换（抽象方法） |
| `fit_transform(X, **kwargs)` | 拟合并变换 |
| `get_stats()` | 获取步骤统计信息 |

#### `ImputerAdapter`

封装 `Factor_Imputer_v2.0` 的 `HierarchicalImputer`。

- **动态导入路径**: `../Factor_Imputer_v2.0/core/imputers.HierarchicalImputer`
- **回退策略**: 内置中位数插补
- **缺失检测**: 支持 `detect_missing_type` 进行 MCAR/MAR/MNAR 识别
- **关键方法**: `fit()` 自动检测缺失类型后拟合，`transform()` 执行插补并记录统计

#### `ProcessingAdapter`

封装 `Factor_AdaptiveWinsor` 的去极值/变换/标准化，支持三种子类型:

| 子类型 | 对应类 | 回退方案 |
|--------|--------|----------|
| `outlier` | `SmartOutlierDetector` | 5% 分位数缩尾 |
| `transformation` | `AdaptiveTransformer` | 保持原值 |
| `standardization` | `AdaptiveStandardizer` | Z-score 标准化 |

- **动态导入路径**: `../Factor_AdaptiveWinsor/core/transformers.{ClassName}`
- **`fit()` 逻辑**: 将数据展平后拟合处理器
- **`transform()` 逻辑**: 对 DataFrame 每列逐列应用变换，失败时保持原值

#### `NeutralizerAdapter`

封装 `Factor_Neutralizer_v2.0` 的 `FactorNeutralizer`。

- **动态导入路径**: `../Factor_Neutralizer_v2.0/factor_neutralizer.core.FactorNeutralizer`
- **中性化方式**: 截面 OLS 回归残差法
- **`_simple_industry_neutralize()`**: 内置简单行业中性化实现
  - 使用 `statsmodels.OLS` 逐日期截面回归
  - 行业哑变量 + 常数项 → 提取残差
  - 最小截面样本量: 10，最小行业样本量: 5

#### `GarchWhiteningAdapter` (v2.0 新增)

使用 GARCH 模型提取条件异方差，对残差进行预白化。

- **依赖**: `arch` 包 (`pip install arch`)
- **默认参数**: p=1, q=1, vol='Garch', min_obs=50
- **处理流程**: 对每列时间序列拟合 GARCH(p,q) → 提取标准化残差 → 返回白化序列
- **回退方案**: 滚动标准差近似（`_simple_whiten()`）
- **安全机制**: 数据不足 min_obs 时跳过，拟合失败时跳过

#### 动态导入工具函数

`_import_external_class(module_path, import_path, class_name)` — 从外部模块动态导入类，失败返回 None。

---

### 4.6 `dag.py` — 有向无环图（DAG）

**文件路径**: [dag.py](file:///f:/Coding/factor_pipeline/dag.py)

基于 `networkx.DiGraph` 实现因子处理步骤的依赖关系管理，替代原有的静态字典和列表。

#### 类: `PipelineDAG`

**DAG 结构**:

```
IMPUTATION ──→ OUTLIER_DETECTION ──→ TRANSFORMATION
    │               │                      │
    │               └──────────────────────┤
    │                                      ▼
    ├──────────────────────────→ STANDARDIZATION
    │                                      │
    └──────────────────────────→ NEUTRALIZATION
```

**关键方法**:

| 方法 | 说明 |
|------|------|
| `validate(steps, strict)` | 验证步骤顺序是否满足 DAG 约束；strict=True 时检查是否在标准顺序列表中 |
| `suggest(steps)` | 返回满足 DAG 约束的拓扑排序建议（NEUTRALIZATION 在最后） |
| `get_path(from, to)` | 获取两个步骤之间的最短路径 |
| `get_all_paths(from, to)` | 获取两个步骤之间的所有简单路径 |
| `visualize(output_path)` | 导出 DAG 可视化图片（需要 matplotlib） |

**标准顺序列表**（严格模式参考）:

```python
[
    [IMPUTATION, OUTLIER, TRANSFORMATION, STANDARDIZATION, NEUTRALIZATION],
    [IMPUTATION, OUTLIER, STANDARDIZATION, NEUTRALIZATION],
    [IMPUTATION, OUTLIER, NEUTRALIZATION],
    [IMPUTATION, STANDARDIZATION, NEUTRALIZATION],
]
```

**优先级排序**（用于拓扑排序 tiebreaker）:

```
IMPUTATION(0) < OUTLIER(1) < TRANSFORMATION(2) < STANDARDIZATION(3) < NEUTRALIZATION(4)
```

---

### 4.7 `pipeline.py` — v1.0 核心流水线

**文件路径**: [pipeline.py](file:///f:/Coding/factor_pipeline/pipeline.py)

v1.0 的核心流水线编排器，实现顺序校验、步骤执行、状态追踪。

#### 类: `PipelineOrderValidator`

流水线顺序校验器，委托给 `PipelineDAG` 进行依赖关系管理。

**验证规则**:

| 规则 | 原因 |
|------|------|
| IMPUTATION 必须是第一步 | 去极值/标准化需要完整数据计算统计量 |
| OUTLIER 必须在 TRANSFORM 之前 | 极值会扭曲变换参数估计 |
| OUTLIER 必须在 STANDARDIZE 之前 | 极值会显著影响标准化后的分布 |
| NEUTRALIZATION 必须在最后 | 中性化后的残差不应再进行分布变换 |

**关键方法**:
- `validate(steps, strict)` → `(bool, List[str])` — 验证步骤顺序
- `suggest_correction(steps)` → `List[StepType]` — 建议修正顺序

#### 数据类: `StepResult` / `PipelineResult`

| 数据类 | 字段 |
|--------|------|
| `StepResult` | step_name, step_type, input_shape, output_shape, execution_time, missing_count_before, missing_count_after, stats, error |
| `PipelineResult` | success, final_data, step_results, total_time, errors, config |

#### 类: `FactorProcessingPipeline`

v1.0 核心流水线编排器。

**构造函数**:
```python
FactorProcessingPipeline(
    steps: Optional[List[PipelineStep]] = None,
    config: Optional[PipelineConfig] = None,
    strict_order: bool = True,
    cache: Optional[PipelineCache] = None
)
```

**关键方法**:

| 方法 | 说明 |
|------|------|
| `default_pipeline(**kwargs)` | 类方法，创建默认五步法流水线 |
| `fit(X, **kwargs)` | 拟合整个流水线（逐步骤 fit + 中间数据传递） |
| `transform(X, **kwargs)` | 应用整个流水线 |
| `fit_transform(X, **kwargs)` | 拟合并变换 |
| `get_execution_summary()` | 获取执行摘要（文本格式） |
| `_execute(X, **kwargs)` | 内部执行方法，含缓存集成和错误拦截 |
| `_add_steps(steps)` | 添加步骤并进行顺序校验 |

**执行流程** (`_execute`):
1. 遍历每个步骤
2. 尝试从 `PipelineCache` 读取缓存（如果启用）
3. 执行 `step.transform()`，记录执行时间
4. 写入缓存（如果启用）
5. 记录步骤结果（`StepResult`）
6. 严格模式下出错即停止

---

### 4.8 `pipelines_v2.py` — v2.0 智能流水线

**文件路径**: [pipelines_v2.py](file:///f:/Coding/factor_pipeline/pipelines_v2.py)

v2.0 的核心模块，实现"先诊断分类，再分流处理"的智能自适应流程。

#### 配置类: `PipelineV2Config`

```python
@dataclass
class PipelineV2Config:
    fingerprint: FingerprintConfig        # 指纹提取配置
    classification: ClassificationConfig  # 分类配置
    monitor: MonitorConfig               # 监控配置
    dynamic_decorrelation_strength: float = 1.0  # AR 残差提取强度
    dynamic_max_ar_order: int = 5         # 最大 AR 阶数
    dynamic_ar_criterion: str = 'aic'     # 阶数选择准则
    mixed_conditional_transform: bool = True  # 是否条件性变换
    mixed_skew_threshold: float = 2.0    # 偏度阈值
    mixed_kurt_threshold: float = 5.0    # 峰度阈值
    static_enable_garch: bool = False    # 是否启用 GARCH 白化
    static_garch_p: int = 1              # GARCH p 阶
    static_garch_q: int = 1              # GARCH q 阶
    static_garch_vol: str = 'Garch'      # 波动率模型
    static_garch_min_obs: int = 50       # 最小观测数
```

#### 基类: `_BaseFactorPipeline`

提供通用的 `fit/transform/fit_transform` 接口。

#### 类: `StaticFactorPipeline` (静态因子管道)

**适用条件**: `ar1_median > 0.80` 且 `rank_autocorr > 0.70`

**处理流程**:
```
缺失插补 → 去极值 → 自适应非线性变换 → [可选]GARCH白化 → 中性化 → 标准化
```

**关键参数**:
- `neutralizer_params` — 中性化参数（行业数据等）
- `enable_garch` — 是否启用 GARCH 白化（默认 False）
- `garch_params` — GARCH 参数（p, q, vol, min_obs）

**v2.0 调整**: 先中性化后标准化，符合 Barra/MSCI 最佳实践。

#### 类: `DynamicFactorPipeline` (动态因子管道)

**适用条件**: `ar1_median < 0.40`

**处理流程**:
```
缺失插补 → 原始值双重中性化 → AR建模 → 残差中性化 → 标准化
```

**关键参数**:
- `decorrelation_strength` — AR 残差提取强度 [0, 1]
- `max_ar_order` — 最大 AR 阶数
- `ar_criterion` — 阶数选择准则 (aic/bic/hqic)
- `neutralizer_params` — 中性化参数

**核心组件**:
- `CompositeDecoupler` — 组合解耦器（三重中性化核心）
- **禁止**: 非线性变换、GARCH 白化

**三重中性化流程**:
1. 原始值中性化（剥离行业/市值暴露）
2. AR 建模 → 残差提取（剥离时序自相关）
3. 残差再中性化（剥离残差中的行业/市值暴露）

**关键方法**: `get_decoupling_summary()` — 获取解耦摘要（含 AR 模型信息）

#### 类: `MixedFactorPipeline` (混合因子管道)

**适用条件**: `0.40 <= ar1_median <= 0.80`

**处理流程**:
```
缺失插补 → 温和去极值(3σ缩尾) → [条件性]非线性变换 → 中性化 → 标准化
```

**关键参数**:
- `conditional_transform` — 是否条件性变换
- `skew_threshold` — 偏度阈值（默认 2.0）
- `kurt_threshold` — 峰度阈值（默认 5.0）
- `neutralizer_params` — 中性化参数

**条件性变换诊断**: `_diagnose_transform_need()` — 当偏度或峰度超过阈值时启用变换

#### 类: `FactorProcessingPipelineV2` (v2.0 智能编排器)

**核心组件**:
- `fingerprinter: FactorFingerprinter` — 21 维核心指纹提取器 (v3.0.0 T1)
- `classifier: AdaptiveFactorClassifier` — 因子分类器
- `semantic_fusion: SemanticStatisticalFusion` — 语义-统计融合（5 种冲突诊断）
- `static_pipeline / dynamic_pipeline / mixed_pipeline` — 三条处理管道
- `monitor: FactorFingerprintMonitor` — 类型迁移监测器（多时间尺度）
- `health_monitor: FactorHealthMonitor` — 五维健康度监测器（拥挤度/效能/容量/衰减/体制敏感性）

**关键方法**:

| 方法 | 说明 |
|------|------|
| `fit(factor_data, industry_data, descriptions, **kwargs)` | 拟合：指纹提取 → 分类 → 管道初始化 → 分组拟合 → 记录监测 |
| `transform(factor_data, **kwargs)` | 按分类结果路由到对应管道执行变换 |
| `fit_transform(factor_data, **kwargs)` | 拟合并变换 |
| `get_classification_summary()` | 获取分类汇总 DataFrame |
| `get_fingerprint_summary()` | 获取指纹汇总 DataFrame |
| `check_migrations(factor_data)` | 检查因子类型迁移 |
| `get_execution_summary()` | 获取执行摘要（文本格式） |

**fit 流程**:
1. 为每个因子提取指纹（`batch_extract`）
2. 分类（语义-统计融合 或 纯统计分类）
3. 初始化三条管道
4. 按类型分组拟合（同类型因子合并后拟合）
5. 记录到监测器

---

### 4.9 `cache.py` — 中间结果缓存

**文件路径**: [cache.py](file:///f:/Coding/factor_pipeline/cache.py)

使用 parquet 格式存储中间步骤结果，避免重复计算。

#### 类: `PipelineCache`

**缓存策略**:
- 缓存 key = `sha256(step_name + factor_name + data_hash + params_json)[:16]`
- 数据 hash 采用采样策略（前 50 行 + 后 50 行 + metadata），O(1) 计算
- 参数变化自动失效（JSON 序列化对比）

**关键方法**:

| 方法 | 说明 |
|------|------|
| `__init__(cache_dir, enabled)` | 初始化缓存目录和启用开关 |
| `get(step_name, factor_name, params, input_data)` | 尝试从缓存读取，miss 返回 None |
| `set(step_name, factor_name, params, input_data, result)` | 写入缓存 |
| `clear()` | 清空所有缓存文件 |

---

### 4.10 `performance.py` — 性能优化工具

**文件路径**: [performance.py](file:///f:/Coding/factor_pipeline/performance.py)

提供向量化计算、并行处理和性能监控功能。

#### 关键组件

| 组件 | 说明 |
|------|------|
| `timed(step_name)` | 装饰器，自动记录函数执行时间到日志 |
| `vectorized_industry_neutralize(factor_data, industry_data, ...)` | 向量化行业中性化（使用 groupby 替代逐日期循环） |
| `SimpleCache(max_size)` | 简单内存缓存（LFU 淘汰策略） |
| `cached(cache, key_func)` | 缓存装饰器 |
| `batch_process(data, processor, batch_size, axis)` | 分批处理大数据集（按行或按列） |
| `benchmark(func, *args, n_runs, warmup, **kwargs)` | 函数性能基准测试，返回统计信息 |

---

### 4.11 `reporting.py` — 执行报告生成

**文件路径**: [reporting.py](file:///f:/Coding/factor_pipeline/reporting.py)

提供结构化执行报告、性能摘要和数据血缘追踪功能。

#### 类: `PipelineExecutionReport`

记录完整的流水线执行过程，支持多种输出格式。

**关键属性**:

| 属性 | 说明 |
|------|------|
| `pipeline_name` | 流水线名称 |
| `pipeline_version` | 版本号 |
| `total_duration_ms` | 总执行时长（毫秒） |
| `total_duration_sec` | 总执行时长（秒） |
| `success` | 是否全部成功 |
| `step_count` | 步骤数量 |
| `classification_results` | 分类结果（v2.0） |

**关键方法**:

| 方法 | 说明 |
|------|------|
| `add_step(record)` | 添加步骤执行记录 |
| `finalize()` | 标记执行完成 |
| `to_dict()` | 转换为字典格式 |
| `to_json(indent)` | 生成 JSON 格式报告 |
| `to_markdown()` | 生成 Markdown 格式报告（含步骤表格、性能摘要） |
| `to_text()` | 生成纯文本格式报告 |

#### 类: `PerformanceProfiler`

**关键方法**:

| 方法 | 说明 |
|------|------|
| `record(step_name, step_type, duration_ms, ...)` | 记录性能数据 |
| `get_summary()` | 获取性能摘要（总耗时、平均、最大/最小、最快/最慢步骤） |
| `get_bottlenecks(threshold_percent)` | 获取瓶颈步骤（耗时超过总时间的阈值百分比） |

### 4.12 `backtest/cusum_drift_monitor.py` — CUSUM 在线漂移监测 (v3.0.0 T3)

**文件路径**: [backtest/cusum_drift_monitor.py](file:///f:/Coding/factor_pipeline/backtest/cusum_drift_monitor.py)

实现 Page (1954) CUSUM (Cumulative Sum) 双侧递推算法,用于因子横截面统计量 (均值/标准差) 的在线漂移监测。定位为**事后诊断工具**,不侵入 `fit/transform` 循环,仅提供附加漂移告警。

#### 类: `CUSUMDriftMonitor`

```python
class CUSUMDriftMonitor:
    def __init__(self, baseline_mean: float, baseline_std: float,
                 k: float = 0.5, h: float = 5.0,
                 min_observations: int = 1, two_sided: bool = True)
    def update(self, x: float) -> Dict[str, Any]  # 在线更新,返回 {'detected', 'direction', 'S_pos', 'S_neg', 'n_observations'}
    def reset(self) -> None                        # 重置累积统计量 S_pos=S_neg=0
    def get_history(self) -> Dict[str, List]       # 获取历史记录
    def get_stats(self) -> Dict[str, Any]          # 获取统计信息
```

#### 核心算法 (Page 1954 双侧递推)

```
S_pos[t] = max(0, S_pos[t-1] + (x - μ₀ - k·σ))    # 上侧漂移累积
S_neg[t] = min(0, S_neg[t-1] + (x - μ₀ + k·σ))    # 下侧漂移累积
触发: S_pos[t] > h·σ  →  上漂移  或  S_neg[t] < -h·σ  →  下漂移
触发后: S_pos 或 S_neg 重置为 0 (重新开始累积)
```

#### 关键设计

| 项 | 说明 |
|----|------|
| **参数标准化** | `k_sigma = k * baseline_std`, `h_sigma = h * baseline_std`,所有内部计算用标准化单位 |
| **NaN 跳过** | `update(NaN)` 不更新 S_pos/S_neg,但 `n_observations` 也不递增 |
| **参数校验** | `baseline_std ≤ 0` / `k < 0` / `h < 0` 抛 `ValueError` |
| **min_observations** | 累积观测数不足时不触发告警 |
| **触发后自动重置** | S_pos/S_neg 触发后归 0,符合 CUSUM 标准定义 |

#### ARL 校准结果 (T3.3 Monte Carlo, N=500, T=3000)

| 参数组合 | MC ARL | Siegmund 近似 | 文献值 |
|---------|--------|---------------|--------|
| h=5σ, k=0.5, 无漂移 | 507 | 285 | 930 |
| h=5σ, k=0.5, 1σ 漂移 | 5-30 (容差内) | — | 10 |
| h=5σ, k=0.5, 3σ 漂移 | 1-8 (容差内) | — | 2 |

**校准结论**: k=0.5, h=5.0 默认参数经 Monte Carlo 验证合理 (ARL 单调性 + 方向对称性 + k 最优性成立)。T3.4 管线集成用 h=5.5 补偿两个 CUSUM (mean+std) 叠加,ARL₀_eff ≈ ARL₀/2 ≈ 250。

#### 学术依据

- Page, E. S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115.
- Siegmund, D. (1985). *Sequential Analysis*. Springer. — ARL 近似公式

### 4.13 `backtest/multiple_testing.py` — 多重检验校正共享模块 (v3.0.0 T3.5)

**文件路径**: [backtest/multiple_testing.py](file:///f:/Coding/factor_pipeline/backtest/multiple_testing.py)

提供 BH-FDR / Bonferroni / 无校正三种多重检验校正方法的低级函数 + 统一入口,供 `unified_drift.py` / `pipelines_v2.py` / `factor_significance.py` 三处共享,消除重复实现。

#### 关键函数

```python
def apply_bh_fdr(p_values: List[float], alpha: float = 0.05) -> Tuple[List[float], List[bool]]
def apply_bonferroni(p_values: List[float], alpha: float = 0.05) -> Tuple[List[float], List[bool]]
def apply_no_correction(p_values: List[float], alpha: float = 0.05) -> Tuple[List[float], List[bool]]
def apply_correction(p_values: List[float], method: str = 'benjamini_hochberg',
                     alpha: float = 0.05) -> Tuple[List[float], List[bool]]
```

#### BH-FDR 算法 (Benjamini-Hochberg 1995)

1. 排序 p 值: `p_(1) ≤ p_(2) ≤ ... ≤ p_(K)`
2. 计算原始校正: `bh_raw_(k) = p_(k) * K / rank`
3. 从大到小累积 min: `p_adj_(k) = min(bh_raw_(k), p_adj_(k+1))`
4. clip 到 [0, 1]
5. step-up: 找最大 k* 使 `p_adj_(k*) ≤ alpha`,所有 rank ≤ k* 的拒绝 H₀

#### 黄金参考 (Benjamini-Hochberg 1995 经典示例)

```
输入: p_values = [0.005, 0.01, 0.02, 0.04, 0.5], K=5, alpha=0.05
排序: [0.005, 0.01, 0.02, 0.04, 0.5], rank=[1,2,3,4,5]
bh_raw: [0.025, 0.025, 0.0333, 0.05, 0.5]
累积 min (从大到小): [0.025, 0.025, 0.0333, 0.05, 0.5]
p_adj (原顺序) = [0.025, 0.025, 0.0333, 0.05, 0.5]
alpha=0.05 → 前 4 个显著 (is_significant = [True, True, True, True, False])
alpha=0.01 → 0 个显著
```

#### 检测力层级

`None (无校正) ≥ BH-FDR ≥ Bonferroni` (检测力从高到低,保守性从低到高)

#### 校验函数

- `_validate_p_values(p_values)`: 检查 NaN / 负数 / >1,抛 `ValueError`
- `_validate_alpha(alpha)`: 检查 (0, 1] 范围,抛 `ValueError`

#### 调用方

| 调用方 | 用途 | 默认方法 |
|--------|------|---------|
| `backtest/unified_drift.py` | `_compute_rolling_structure_drift` ~504 次 KS 检验假阳性控制 | `benjamini_hochberg` |
| `pipelines_v2.py` | `_check_ks_migration` 因子迁移多重比较校正 | `benjamini_hochberg` |
| `backtest/factor_significance.py` | `_apply_correction` K 因子增量 alpha 多重检验 | `benjamini_hochberg` (Holm 路径保留内联) |

#### 向后兼容机制

调用方统一用 `_HAS_MULTIPLE_TESTING` flag + 内联 fallback:

```python
try:
    from backtest.multiple_testing import apply_bh_fdr, apply_bonferroni
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False

# 调用时:
if _HAS_MULTIPLE_TESTING:
    p_adj_list, _ = apply_bh_fdr(p_values, alpha=alpha)
else:
    # 内联 fallback (旧实现)
    ...
```

#### 学术依据

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *JRSS Series B*, 57(1), 289-300.
- Dunn, O. J. (1961). Multiple comparisons among means. *JASA*, 56(293), 52-64. (Bonferroni 校正)

---

## 5. 依赖关系图

### 模块间依赖

```
__init__.py
    ├── types.py                    (无依赖)
    ├── config.py                   (无依赖)
    ├── config_v2.py                → config.py
    ├── exceptions.py               (无依赖)
    ├── dag.py                      → config.py, networkx
    ├── adapters.py                 → (无内部依赖，依赖外部子模块)
    ├── cache.py                    (无依赖)
    ├── performance.py              (无依赖)
    ├── reporting.py                → types.py
    ├── pipeline.py                 → config.py, adapters.py, exceptions.py, dag.py, cache.py
    ├── pipelines_v2.py             → pipeline.py, adapters.py,
    │                                  Factor_Fingerprint, Factor_Decoupler
    └── backtest/                   → numpy, pandas, (external: Factor_Trading_v3.0, Factor_Fingerprint)
         ├── factor_metrics.py      → numpy, pandas (无内部依赖)
         ├── data_bridge.py         → factor_metrics.py, importlib (external: DataLoaderV3)
         ├── engine.py              → factor_metrics.py
         ├── health_bridge.py       → factor_metrics.py, importlib (external: FactorHealthMonitor)
         ├── unified_drift.py       → engine.py, scipy.stats (KS test), multiple_testing.py (T3.5 BH-FDR)
         ├── cusum_drift_monitor.py → numpy (无内部依赖, v3.0.0 T3)
         ├── multiple_testing.py    → numpy (无内部依赖, v3.0.0 T3.5, 供 unified_drift/pipelines_v2/factor_significance 共享)
         └── pipeline_integration.py → config_v2.py, data_bridge.py, engine.py,
                                          health_bridge.py, unified_drift.py
```

**v3.0.0 T3 新增依赖**:
- `pipelines_v2.py` → `backtest.cusum_drift_monitor.py` (T3.4, `enable_cusum_drift_monitor=True` 时启用, try/except ImportError)
- `pipelines_v2.py` → `backtest.multiple_testing.py` (T3.5, `_HAS_MULTIPLE_TESTING` flag + 内联 fallback)
- `backtest/factor_significance.py` → `backtest.multiple_testing.py` (T3.5, 同上)
- `backtest/unified_drift.py` → `backtest.multiple_testing.py` (T3.5, try/except ImportError fallback 到旧路径)

### 外部依赖

| 包 | 用途 | 必需 |
|----|------|------|
| `pandas` | 核心数据结构 | 是 |
| `numpy` | 数值计算 | 是 |
| `networkx` | DAG 依赖关系管理 | 是 |
| `pydantic >= 2.0` | v2.0 配置验证 | 否（仅 config_v2.py） |
| `statsmodels` | 行业中性化 OLS 回归 | 否（回退方案可用） |
| `arch` | GARCH 白化 | 否（仅 GarchWhiteningAdapter） |
| `matplotlib` | DAG 可视化 | 否（仅 dag.visualize()） |
| `pyyaml` | YAML 配置加载 | 否（仅 config_v2.py） |

### 外部子模块依赖

| 子模块 | 导入路径 | 提供类 |
|--------|----------|--------|
| Factor_Imputer_v2.0 | `../Factor_Imputer_v2.0/core/imputers` | `HierarchicalImputer` |
| Factor_AdaptiveWinsor | `../Factor_AdaptiveWinsor/core/transformers` | `SmartOutlierDetector`, `AdaptiveTransformer`, `AdaptiveStandardizer` |
| Factor_Neutralizer_v2.0 | `../Factor_Neutralizer_v2.0/factor_neutralizer.core` | `FactorNeutralizer` |
| Factor_Fingerprint | `Factor_Fingerprint` | `FactorFingerprinter`, `AdaptiveFactorClassifier`, `SemanticStatisticalFusion`, `FactorFingerprintMonitor` 等 |
| Factor_Decoupler | `Factor_Decoupler` | `CompositeDecoupler`, `DecouplerConfig` |
| Factor_Trading_v3.0 | `../Factor_Trading_v3.0/core/data_v3` | `DataLoaderV3` (backtest 数据输入格式) |

---

## 6. 外部子模块依赖

### 子模块 1: Factor_Imputer_v2.0

| 属性 | 详情 |
|------|------|
| **核心类** | `HierarchicalImputer` |
| **插补策略** | 5 种：截面均值/时序前向/面板分层/ML 高级/因子专属 |
| **缺失检测** | MCAR/MAR/MNAR 类型识别 + 缺失模式分析 |
| **特色** | Lookahead-Free 设计，向量化执行 |

### 子模块 2: Factor_AdaptiveWinsor

| 属性 | 详情 |
|------|------|
| **核心类** | `SmartOutlierDetector` / `AdaptiveTransformer` / `AdaptiveStandardizer` |
| **去极值方法** | 6 种自动选择：分位数/Z-score/MAD/IQR/自适应/Sigmoid |
| **变换方法** | Box-Cox / Yeo-Johnson / 分位数变换，自适应选择 |
| **标准化** | Z-score / Rank / MinMax / Robust，统计量投票 |

### 子模块 3: Factor_Neutralizer_v2.0

| 属性 | 详情 |
|------|------|
| **核心类** | `FactorNeutralizer` |
| **中性化类型** | 行业中性化 / 市值中性化 / 指数中性化 |
| **回归方法** | OLS / WLS / Ridge，截面回归残差提取 |

### 子模块 4: Factor_Fingerprint (v2.0 新增)

| 属性 | 详情 |
|------|------|
| **核心类** | `FactorFingerprinter` / `AdaptiveFactorClassifier` / `SemanticStatisticalFusion` / `FactorFingerprintMonitor` / **`FactorHealthMonitor`** |
| **指纹维度** | 21 维核心指纹 (v3.0.0 T1): AR(1)、秩自相关、半衰期、波动率聚集、偏度、峰度等 (13 维基础) + 尾部依赖 (tail_dependence_lower/upper, gpd_shape, hill_estimator) + 体制转换 (regime_transition_prob/persistence/ic_diff) + 综合衍生 (tail_regime_score) |
| **健康度维度** | **5 维正交评估**（FactorHealthMonitor）：拥挤度(0.25) / 效能(0.35) / 容量(0.15) / 衰减(0.15) / 体制敏感性(0.10)，加权合成综合健康分 [0-100] |
| **分类方法** | AR(1) 阈值法 + 贝叶斯融合（支持语义先验），含 5 种冲突诊断类型 |
| **监测功能** | 类型迁移检测（多时间尺度：快速1期/标准3期/长期6期）+ 五维健康度评估 + 四级警报（HEALTHY/WATCH/WARNING/CRITICAL） |
| **语义理解** | 4 层 NLP 流水线：FinancialTokenizer → SemanticRoleLabeler → FinancialKnowledgeGraph → SemanticMatcher |
| **冲突仲裁** | 3 阶段策略：冷启动信任语义 → 观察期降级混合 → 成熟期触发人工审查 |

### 子模块 5: Factor_Decoupler (v2.0 新增)

| 属性 | 详情 |
|------|------|
| **核心类** | `CompositeDecoupler` / `AROrderSelector` / `DualNeutralizer` |
| **解耦方法** | AR 模型 / 一阶差分 / HP 滤波 / 自动选择 |
| **双重中性化** | 原始值中性化 → AR 建模 → 残差中性化 |
| **学术依据** | Hausman (1978) 内生性理论 |

---

## 7. 项目运行方式

### 环境要求

- Python 3.10+
- 操作系统: Windows / Linux / macOS

### 安装依赖

```bash
# 核心依赖
pip install pandas numpy networkx

# 可选依赖
pip install pydantic>=2.0       # v2.0 配置验证
pip install statsmodels          # 行业中性化
pip install arch                 # GARCH 白化
pip install matplotlib           # DAG 可视化
pip install pyyaml               # YAML 配置
```

### 运行方式

#### 方式 1: v2.0 智能流水线（推荐）

```python
from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config
from Factor_Fingerprint import FingerprintConfig, ClassificationConfig, MonitorConfig

config = PipelineV2Config(
    fingerprint=FingerprintConfig(min_window=24),
    classification=ClassificationConfig(),
    monitor=MonitorConfig(),
)

pipeline = FactorProcessingPipelineV2(config)

# 语义-统计融合模式
descriptions = {
    'pb_factor': '市净率因子，基于最新财报账面价值除以总市值',
    'reversal_factor': '过去1个月日收益率的相反数',
}

pipeline.fit(
    factor_data={'pb_factor': pb_df, 'reversal_factor': rev_df},
    industry_data=industry_series,
    descriptions=descriptions,
)

results = pipeline.transform(factor_data)
print(pipeline.get_classification_summary())
```

#### 方式 2: 单独使用三条管道

```python
from factor_pipeline.pipelines_v2 import StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline

# 静态因子（可选 GARCH）
static = StaticFactorPipeline(
    neutralizer_params={'industry_data': industry},
    enable_garch=True,
    garch_params={'p': 1, 'q': 1}
)
result = static.fit_transform(pb_data)

# 动态因子（三重中性化）
dynamic = DynamicFactorPipeline(
    decorrelation_strength=1.0,
    max_ar_order=5,
    neutralizer_params={'industry_data': industry}
)
result = dynamic.fit_transform(reversal_data)

# 混合因子
mixed = MixedFactorPipeline(
    conditional_transform=True,
    neutralizer_params={'industry_data': industry}
)
result = mixed.fit_transform(momentum_data)
```

#### 方式 3: v1.0 兼容模式

```python
from factor_pipeline import FactorProcessingPipeline

pipeline = FactorProcessingPipeline.default_pipeline()
result = pipeline.fit_transform(factor_data)
print(pipeline.get_execution_summary())
```

#### 方式 4: 自定义步骤

```python
from factor_pipeline import FactorProcessingPipeline
from factor_pipeline.adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter

pipeline = FactorProcessingPipeline([
    ImputerAdapter(strategy='auto'),
    ProcessingAdapter(process_type='outlier', method='mad'),
    ProcessingAdapter(process_type='standardization', method='z_score'),
    NeutralizerAdapter(industry_data=industry_series),
])
result = pipeline.fit_transform(factor_data)
```

#### 运行演示脚本

```bash
# v1.0 演示
python demo.py

# v2.0 演示（含语义融合和迁移监测）
python demo_v2.py
```

#### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 仅单元测试
pytest tests/unit/ -v

# 带覆盖率报告
pytest tests/ --cov=factor_pipeline --cov-report=html
```

---

## 8. 测试体系

### 测试架构

```
tests/
├── conftest.py                      # 共享 fixtures 和 mock 对象
├── test_cache.py                    # PipelineCache 缓存测试
├── test_dag.py                      # PipelineDAG 依赖图测试
├── test_integration.py              # 集成测试（需要子模块）
├── test_pipelines_v2.py             # v2.0 管道测试
├── test_pipeline_v2_full.py         # v2.0 完整流程测试
├── test_dynamic_pipeline.py         # 动态管道测试
├── test_pipeline_comprehensive.py   # 综合测试
└── unit/                            # 单元测试（无外部依赖）
    ├── test_adapters_mock.py        # 适配器 mock 测试
    ├── test_config.py               # v1.0 配置测试
    ├── test_config_v2.py            # v2.0 配置测试
    ├── test_exceptions.py           # 异常体系测试
    ├── test_performance.py          # 性能工具测试
    ├── test_pipeline_order_validator.py  # 顺序校验器测试
    ├── test_pipeline_v1.py          # v1.0 流水线测试
    └── test_reporting.py            # 报告生成测试
```

### 共享 Fixtures (conftest.py)

| Fixture | 说明 |
|---------|------|
| `sample_factor_data` | 标准因子数据（100 天 × 50 股，5% 缺失率，含极值） |
| `sample_industry_data` | 行业分类数据（6 个行业） |
| `sample_market_cap` | 市值数据（对数正态分布） |
| `clean_factor_data` | 无缺失、无极值的干净数据（50 天 × 20 股） |
| `high_missing_data` | 高缺失率数据（35%） |
| `extreme_outlier_data` | 含极端异常值数据（±30-50σ） |
| `mock_imputer` | Mock 插补器 |
| `mock_step` | Mock 通用步骤工厂函数 |

### pytest 标记

| 标记 | 说明 |
|------|------|
| `@pytest.mark.unit` | 单元测试（无外部依赖） |
| `@pytest.mark.integration` | 集成测试（需要子模块） |
| `@pytest.mark.slow` | 慢速测试（性能测试等） |

---

## 9. API 完整参考

### 包入口 (`__init__.py`)

```python
from factor_pipeline import (
    # 类型系统
    PipelineStepProtocol, StepStats, StepExecutionRecord,
    PipelineExecutionSummary, NeutralizationSummary, ARModelSummary,
    FactorData, IndustryData, MarketCapData, FactorDescriptions,
    StepOutput, PipelineOutput,
    # v1.0 核心
    FactorProcessingPipeline, PipelineOrderValidator,
    PipelineStep, ImputerAdapter, ProcessingAdapter,
    NeutralizerAdapter, GarchWhiteningAdapter,
    PipelineConfig, StepType, StepConfig,
    # v2.0 智能流水线
    FactorProcessingPipelineV2, PipelineV2Config,
    StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline,
)
```

### `FactorProcessingPipeline` (v1.0)

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(steps, config, strict_order, cache)` | 初始化流水线 |
| `default_pipeline` | `(**kwargs) -> FactorProcessingPipeline` | 类方法，创建默认流水线 |
| `fit` | `(X, **kwargs) -> FactorProcessingPipeline` | 拟合流水线 |
| `transform` | `(X, **kwargs) -> pd.DataFrame` | 应用流水线 |
| `fit_transform` | `(X, **kwargs) -> pd.DataFrame` | 拟合并变换 |
| `get_execution_summary` | `() -> str` | 获取执行摘要 |

### `FactorProcessingPipelineV2` (v2.0)

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(config, strict_mode)` | 初始化智能流水线 |
| `fit` | `(factor_data, industry_data, descriptions, **kwargs) -> self` | 拟合流水线 |
| `transform` | `(factor_data, **kwargs) -> Dict[str, pd.DataFrame]` | 应用流水线 |
| `fit_transform` | `(factor_data, **kwargs) -> Dict[str, pd.DataFrame]` | 拟合并变换 |
| `get_classification_summary` | `() -> pd.DataFrame` | 分类汇总表 |
| `get_fingerprint_summary` | `() -> pd.DataFrame` | 指纹汇总表 |
| `check_migrations` | `(factor_data) -> Dict[str, List]` | 迁移检测 |
| `get_execution_summary` | `() -> str` | 执行摘要 |

### 三条管道 (v2.0)

**`StaticFactorPipeline`**:
| 方法 | 说明 |
|------|------|
| `fit(X, **kwargs)` | 拟合：插补→去极值→变换→[GARCH]→中性化→标准化 |
| `transform(X, **kwargs)` | 应用管道变换 |
| `fit_transform(X, **kwargs)` | 拟合并变换 |

**`DynamicFactorPipeline`**:
| 方法 | 说明 |
|------|------|
| `fit(X, **kwargs)` | 拟合：插补→三重中性化→标准化 |
| `transform(X, **kwargs)` | 应用管道变换 |
| `fit_transform(X, **kwargs)` | 拟合并变换 |
| `get_decoupling_summary()` | 获取解耦摘要（含 AR 模型信息） |

**`MixedFactorPipeline`**:
| 方法 | 说明 |
|------|------|
| `fit(X, **kwargs)` | 拟合：插补→温和缩尾→条件性变换→中性化→标准化 |
| `transform(X, **kwargs)` | 应用管道变换 |
| `fit_transform(X, **kwargs)` | 拟合并变换 |

### 适配器

**`GarchWhiteningAdapter`**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `p` | int | 1 | ARCH 阶数 |
| `q` | int | 1 | GARCH 阶数 |
| `vol` | str | 'Garch' | 波动率模型 |
| `min_obs` | int | 50 | 最小观测数 |

### 异常体系

| 异常类 | 触发条件 |
|--------|----------|
| `OrderValidationError` | 步骤顺序违反学术规则 |
| `StepExecutionError` | 步骤执行失败（含原始异常） |
| `AdapterImportError` | 外部子模块无法导入 |
| `ConfigurationError` | 配置参数非法 |
| `FactorTypeError` | 因子数据格式不符合要求 |
| `NeutralizationError` | 中性化失败 |
| `GarchFittingError` | GARCH 模型拟合失败 |
| `MigrationAlertError` | 因子类型漂移告警（非致命） |

### 配置系统

**`PipelineConfig` (v1.0)**:
| 方法 | 说明 |
|------|------|
| `default_config()` | 创建默认五步法配置 |
| `from_dict(data)` | 从字典创建配置 |
| `from_json(path)` | 从 JSON 文件创建配置 |
| `to_dict()` | 转换为字典 |
| `to_json(path)` | 保存到 JSON 文件 |

**`PipelineV2ConfigUnified` (v2.0)**:
- Pydantic 模型，自动验证字段约束
- 支持 `load_config_from_json()` / `load_config_from_yaml()` 加载
- 支持 `save_config_to_json()` / `save_config_to_yaml()` 保存
- 提供 `to_pipeline_config()` 兼容层转换

### 工具模块

**`PipelineCache`**:
| 方法 | 说明 |
|------|------|
| `get(step_name, factor_name, params, input_data)` | 读取缓存 |
| `set(step_name, factor_name, params, input_data, result)` | 写入缓存 |
| `clear()` | 清空缓存 |

**`PipelineExecutionReport`**:
| 方法 | 说明 |
|------|------|
| `add_step(record)` | 添加步骤记录 |
| `finalize()` | 标记完成 |
| `to_markdown()` | 生成 Markdown 报告 |
| `to_json(indent)` | 生成 JSON 报告 |
| `to_text()` | 生成纯文本报告 |

**`PerformanceProfiler`**:
| 方法 | 说明 |
|------|------|
| `record(...)` | 记录性能数据 |
| `get_summary()` | 性能摘要 |
| `get_bottlenecks(threshold_percent)` | 瓶颈分析 |

**`PipelineDAG`**:
| 方法 | 说明 |
|------|------|
| `validate(steps, strict)` | 验证顺序 |
| `suggest(steps)` | 建议顺序 |
| `get_path(from, to)` | 最短路径 |
| `visualize(output_path)` | 导出可视化 |

---

## 10. 学术依据

本流水线的处理顺序与分类逻辑基于以下学术与业界标准：

- Barra 多因子模型数据处理规范
- MSCI 因子标准化最佳实践
- Quantopian 因子研究框架
- Hausman (1978) 内生性检验与工具变量理论
- Engle (1982) ARCH/GARCH 波动率建模
- Box & Cox (1964) 变换理论
- Bergstra et al. (2011) "Algorithms for Hyper-parameter Optimization" (TPE)
- Lopez de Prado (2018) "Advances in Financial Machine Learning" (时序交叉验证)
- *Quantitative Equity Portfolio Management* (Qian et al.)
- *Active Portfolio Management* (Grinold & Kahn)

---

## 11. v2.1.0 架构修复详解

### 11.1 P0-1: 概率加权软路由

**位置**: `pipelines_v2.py` — `FactorProcessingPipelineV2.transform()`

**问题**: v2.0 使用硬路由，因子类型切换时处理流程瞬间改变，产生断崖效应。

**修复**: 三阶段概率加权路由。

```python
# 阶段 1: 分类 → 管道权重
weights = _get_pipeline_weights(classification_result)
# → {'static': 0.70, 'mixed': 0.20, 'dynamic': 0.10}

# 阶段 2: 迁移权重融合 (P1-5)
if monitor.enable_smooth_transition:
    trans_weights = monitor.get_transition_weights(name, fp)
    weights = _merge_transition_weights(weights, trans_weights)

# 阶段 3: KS 显著性过滤 (P2-6)
if _ks_migration_significance(hist_data, recent_data).is_sig:
    # 确认迁移，使用合并权重
else:
    # 噪声，忽略迁移

# 最终: 加权混合
result = _apply_weighted_transform(factor_data, weights, pipelines)
```

**关键函数**:
- `_get_pipeline_weights()`: `ClassificationResult` → 权重字典
- `_apply_weighted_transform()`: 多管道加权混合
- `_merge_transition_weights()`: 分类权重 + 迁移权重融合

### 11.2 P0-2: 数据驱动阈值校准

**位置**: `pipelines_v2.py` — `ThresholdCalibrator`

```python
calibrator = ThresholdCalibrator(market='a_share')
calibrator.fit(factor_data)
# → static_threshold=0.75, dynamic_threshold=0.35 (基于数据分位数)
```

三种校准方法: 分位数法 (默认) / 市场预设 / 手动覆盖

### 11.3 P1-3: 统一管道 fit() 模式

**位置**: `pipelines_v2.py` — `_BaseFactorPipeline`

```python
# 所有三条管道统一的中间数据接口
pipeline.fit(X)
intermediate = pipeline.get_intermediate_data()
# → {'imputer': {...}, 'transform': {...}, 'neutralizer': {...}}
```

### 11.4 P1-4: 适配器回退 Warning

**位置**: `adapters.py` — `PipelineStep` 基类 + 四个适配器

- `PipelineStep.is_fallback_mode`: 回退模式标记
- `warnings.warn(UserWarning)`: 回退时显式告警
- `get_stats()['fallback_mode']`: 报告中的回退状态

### 11.5 P2-6: KS 迁移显著性检验

**位置**: `pipelines_v2.py` — `_ks_migration_significance()`

```python
# T4 v3.0.0: 默认 BH-FDR, 三路径分流
is_sig, p_value, details = _ks_migration_significance(
    historical_data, recent_data, alpha=0.05
)
# 默认 correction_method='benjamini_hochberg':
#   p_adj_(k) = p_(k) * K / rank, 累积 min, clip [0,1]
#   is_significant = (min_p_value_adjusted < alpha)
# 向后兼容: correction_method='bonferroni' (alpha_corrected = alpha / K)
# 研究调试: correction_method='none' (无校正, min_p < alpha)
```

### 11.6 P2-8: importlib 上下文管理器

**位置**: `adapters.py` — `_temp_sys_path`, `_import_external_class`

```python
with _temp_sys_path(full_path):
    module = importlib.import_module(import_path)
    return getattr(module, class_name)
# 无论成功或失败，sys.path 均恢复原状
```

---

## 12. P3 规划: 端到端自动阈值搜索

### 12.1 目标函数 (v2.6.0 修正版, 6 项 ADR-004)

**决策**: ADR-004 + ADR-021 — IC 主目标 + 5 项约束惩罚 (v2.6.0 E4+E6 完成)

```python
score = (IC
         - λ_vol       * volatility_penalty      # 0.5
         - λ_cov       * coverage_penalty        # 0.3
         - λ_fid       * ks_distortion_penalty   # 0.1 (符号修正: + → -)
         - λ_health    * health_penalty          # 0.4 (代理方案 B)
         - λ_red       * redundancy_penalty)     # 0.05 (v1.1 从 0.1 降)
```

| 指标 | 原方案 | 修正方案 | 依据 |
|------|--------|---------|------|
| IC + ICIR | 0.40 + 0.25 | IC 主目标 (EWMA 时间加权, Ferson-Siegel 2001) | Q3: ρ=0.885 冗余 |
| stability | 0.15 | KS 扭曲惩罚 (符号修正) | 约束优于目标 |
| coverage | 0.10 | 覆盖率约束 (<0.70→-0.5) | Q3: std=0.014 无区分力 |
| diversity | 0.10 | 移除 → redundancy_penalty (VRR) | 几何诊断直接测量 |
| — | — | health_penalty 代理 (decay/hit_rate/ic_vol 三档) | ADR-021 方案 B |
| — | — | HM 约束 (<40→-0.5) → 代理指标 | ADR-021 |

### 12.2 搜索空间 (8 维默认 + 3 维正交化可选, ADR-005 + ADR-022)

**决策**: ADR-005 + ADR-022 — 默认 8 维 (向后兼容), `search_orth=True` 时扩展至 11 维

| 维度 | 范围 | 当前值 | 类别 |
|------|------|--------|------|
| `hard_routing_prob` | [0.5, 1.0] | 0.90 | float |
| `merge_alpha` | [0.0, 1.0] | 0.50 | float |
| `ks_alpha` | [0.001, 0.5] | 0.05 | float |
| `mixed_winsor_sigma` | [1.0, 10.0] | 3.0 | float |
| `transform_aggressiveness` | [0.3, 5.0] | 1.0 | float |
| `classification_threshold_static` | [0.5, 1.0] | 0.7 | float |
| `classification_threshold_dynamic` | [0.0, 0.5] | 0.3 | float |
| `migration_threshold` | [0.0, 1.0] | 0.10 | float |
| `orth_method` | symmetric/ridge/pca/gram_schmidt | symmetric | categorical (search_orth) |
| `orth_align_mode` | intersection/union_nan | intersection | categorical (search_orth) |
| `orth_ridge_lambda` | [0.01, 100.0] | 1.0 | log-uniform (search_orth) |

### 12.3 搜索算法

- 算法: Optuna TPE (Tree-structured Parzen Estimator)
- 试验数: 200
- 交叉验证: 扩展窗口 (expanding window), 3 折
- 剪枝: `MedianPruner(n_startup_trials=10)`

### 12.4 实施路线

| 阶段 | 内容 | 文件 |
|------|------|------|
| 1 | `PipelineV2ConfigUnified` 扩展 8 个新字段 | `config_v2.py` |
| 2 | 硬编码常量 → `self.config` 读取 | `pipelines_v2.py` |
| 3 | `EndToEndThresholdOptimizer` 类 | `pipelines_v2.py` |
| 4 | TDD 测试 + 手工校验 | `tests/test_p3_threshold_search.py` |
| 5 | 参数重要性可视化 | `reporting.py` |

---

## 13. Backtest 模块详解 (v2.2.0 新增)

### 13.1 架构概览

`backtest/` 是 v2.2.0 新增的 peer module，采用适配器模式将因子回测引擎集成到 Pipeline，实现全链路闭环：Pipeline 输出 → 回测 → 健康度评估 → 漂移检测。

```
  Pipeline 输出 (n_stocks, n_dates)
      ↓
  DataBridge: 转置 + 格式转换 → DataLoaderV3 (n_dates, n_stocks)
      ↓
  DataLoaderV3: 构建 {price_data, factor_data, mask_data}
      ↓
  FactorBacktestEngine: IC/ICIR/Decay/HitRate/Turnover/LS/Spread
      ↓
  HealthMonitorAdapter: 注入 FactorHealthMonitor → 5 维健康评分
      ↓
  UnifiedDriftReporter: 结构+性能+换手率 → 融合漂移判定
```

### 13.2 `factor_metrics.py` — 因子级指标单一真相源

**文件路径**: [factor_metrics.py](file:///f:/Coding/factor_pipeline/backtest/factor_metrics.py)

整个回测系统指标计算的唯一权威来源。所有模块（engine、health_bridge、unified_drift）统一使用此模块，不再重复实现。

**核心约定**: `factor[:, t]` 对应 `returns[:, t+1]`，`returns[:, 0]` 是填充位（NaN）。

**关键函数**:

| 函数 | 说明 |
|------|------|
| `compute_rank_ic(factor, returns)` | 截面 Spearman 秩相关系数，返回 (n_dates,) 数组 |
| `compute_pearson_ic(factor, returns)` | 截面 Pearson 相关系数 |
| `compute_ic_series(factor, returns)` | 返回 (rank_ic, pearson_ic) 元组 |
| `compute_icir(ic_series)` | IC 信息比率 = mean(IC) / std(IC) |
| `compute_ic_decay(factor, returns, max_lag=12)` | IC 衰减曲线，返回 (n_lags,) 数组 |
| `compute_turnover(factor, top_n=0.2)` | 换手率 = 1 - mean(IoU of top_n stocks) |
| `compute_long_short_returns(factor, returns, top_n=0.2)` | 多空组合收益（top 做多，bottom 做空） |
| `compute_spread(factor, returns, top_n=0.2)` | 多空组合收益差 |
| `compute_hit_rate(factor, returns, top_n=0.2)` | top_n 股票下一期收益为正的比例 |

**测试**: 30/30 通过，覆盖所有函数 + 手工数值校验。

### 13.3 `data_bridge.py` — Pipeline → DataLoaderV3 适配器

**文件路径**: [data_bridge.py](file:///f:/Coding/factor_pipeline/backtest/data_bridge.py)

将 Pipeline 输出格式 (n_stocks, n_dates) 转换为 DataLoaderV3 格式 (n_dates, n_stocks)。

**关键方法**:

| 方法 | 说明 |
|------|------|
| `_transpose_factor_data(factor_df)` | 转置因子数据 (n_stocks, n_dates) → (n_dates, n_stocks) |
| `_build_price_dataframe(factor_data, price_col)` | 从因子数据构建价格 DataFrame |
| `create_dataloader(factor_data, price_data)` | 创建完整的 DataLoaderV3 实例 |
| `validate_shapes(factor_data, dataloader)` | 验证转置后形状一致性 |

**设计要点**:
- 使用 `importlib` 直接加载 `data_v3.py`，绕过 `core/__init__.py` 的重依赖链（cvxpy/jax）
- 价格数据自动对齐因子数据的日期和股票索引

**测试**: 10/10 通过。

### 13.4 `engine.py` — 因子回测引擎

**文件路径**: [engine.py](file:///f:/Coding/factor_pipeline/backtest/engine.py)

改编自 `F:\Coding\Factor_Trading_v3.0\core\engine_v3_vector.py`，使用 `factor_metrics.py` 作为单一真相源。

**类: `FactorBacktestEngine`**

| 方法 | 说明 |
|------|------|
| `run()` | 执行完整回测：IC 系列 → ICIR → Decay → Hit Rate → Turnover → LS Returns → Spread |
| `rank_by_icir()` | 按 ICIR 排序因子，返回排名列表 |
| `summary()` | 返回回测摘要字典，包含 IC/ICIR/Decay/HitRate/Turnover/LS/Spread |

**关键设计**:
- 前向收益计算后自动 padding NaN 列，满足 `factor[:, t]` ↔ `returns[:, t+1]` 约定
- 所有指标计算委托给 `factor_metrics.py`，引擎自身不实现任何指标计算

**测试**: 20/20 通过，含手工数值校验。

### 13.5 `health_bridge.py` — 回测 → FactorHealthMonitor 适配器

**文件路径**: [health_bridge.py](file:///f:/Coding/factor_pipeline/backtest/health_bridge.py)

将回测引擎预计算指标注入外部 Factor_Fingerprint 的 `FactorHealthMonitor`，不修改外部模块。

**类: `HealthMonitorAdapter`**

| 方法 | 说明 |
|------|------|
| `_map_efficacy_metrics(engine_results)` | 效能指标映射：IC → rolling_ic_mean, ICIR → ic_ir, Hit Rate → ic_win_rate |
| `_map_crowding_metrics(engine_results)` | 拥挤度指标映射：Turnover → turnover, Spread → spread |
| `_map_decay_metrics(engine_results)` | 衰减指标映射：IC Decay → decay_curve, ICIR → ic_ir |
| `build_report_from_engine(engine, factor_name)` | 从引擎构建单因子健康报告 |
| `build_batch_reports(engine, factor_names)` | 批量构建多因子健康报告 |

**关键设计**:
- 使用 `types.ModuleType` 注册 `core` 为 package，解决 `core` 模块命名空间冲突（Factor_Trading_v3.0 和 Factor_Fingerprint 均使用 `core` 作为包名）
- 注入指标后 HealthMonitor 不再独立计算 IC，避免重复

**测试**: 13/13 通过。

### 13.6 `unified_drift.py` — 双轨融合漂移判定

**文件路径**: [unified_drift.py](file:///f:/Coding/factor_pipeline/backtest/unified_drift.py)

融合三个漂移信号源：结构漂移 (Fingerprint) + 性能漂移 (Backtest) + 换手率漂移。

**类: `UnifiedDriftReporter`**

| 方法 | 说明 |
|------|------|
| `_compute_structure_drift(hist_fp, recent_fp)` | KS 双样本检验，检测指纹分布偏移 |
| `_compute_performance_drift(hist_icir, recent_icir)` | ICIR 变化率，检测性能退化 |
| `_compute_turnover_drift(hist_turnover, recent_turnover)` | 换手率变化，检测流动性变化 |
| `evaluate_from_engine(engine, factor_name, hist_data)` | 从引擎结果评估单因子漂移 |
| `batch_evaluate(engine, factor_names, hist_data)` | 批量评估多因子漂移 |
| `summary_report()` | 生成漂移汇总报告 |

**判定等级**: `stable` / `warning` / `drift_detected` / `severe_drift`

**测试**: 13/13 通过。

### 13.7 `pipeline_integration.py` — 端到端 Pipeline 集成

**文件路径**: [pipeline_integration.py](file:///f:/Coding/factor_pipeline/backtest/pipeline_integration.py)

端到端集成运行器，串联全链路。

**类: `PipelineBacktestRunner`**

| 方法 | 说明 |
|------|------|
| `run(factor_data, price_data, factor_names)` | 完整运行：DataBridge → DataLoaderV3 → Engine → HealthMonitorAdapter → UnifiedDriftReporter |
| `run_quick(factor_data, price_data, factor_name)` | 快速模式：单因子回测 + ICIR 排名 |
| `summary()` | 返回完整汇总（回测摘要 + 健康报告 + 漂移报告） |

**测试**: 9/9 通过。

### 13.8 `threshold_drift_monitor.py` — 阈值组合有效性漂移监测 (v2.6.0 E8, ADR-023)

**文件路径**: [threshold_drift_monitor.py](file:///f:/Coding/factor_pipeline/backtest/threshold_drift_monitor.py)

监测优化器最优阈值组合的有效性漂移 (区别于 `UnifiedDriftReporter` 监测因子漂移)。当 EWMA 加权的 score 相对 best_score 衰减超过 `decay_threshold` (默认 20%) 时, 触发 `needs_research` 标志, 提示需要重新搜索阈值参数。

**类: `ThresholdDriftMonitor`**

| 方法 | 说明 |
|------|------|
| `__init__(best_score, best_params, halflife=63, decay_threshold=0.2, min_observations=5)` | 初始化监测器, halflife 默认 63 (约一个季度) |
| `update(score)` | 接收新 score, 更新 EWMA, 返回 `{ewma_score, decay_ratio, needs_research}` |
| `_compute_ewma()` | 手工计算 EWMA 用于校验: `alpha = 1 - exp(-ln2/halflife)` |
| `get_history()` | 返回 score 历史副本 (避免外部修改) |
| `reset(best_score, best_params)` | 重置监测器 (新阈值搜索后调用) |

**触发逻辑**: `decay_ratio = ewma_score / best_score`, 当 `decay_ratio < (1 - decay_threshold)` 且观测数 ≥ `min_observations` 时触发 `needs_research=True`。

**学术依据**: Bailey-López de Prado (2014) Sharpe ratio efficient frontier + Sullivan-TW (1999) data snooping + McLean-Pontiff (2016) factor decay。

**测试**: 10/10 通过 (test_p3_phase3_threshold_drift_monitor.py)。

### 13.9 配置扩展 (`config_v2.py`)

**新增 `BacktestConfig` 类**:

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ic_method` | str | `"rank"` | IC 计算方法 (rank/pearson) |
| `top_n` | float | 0.2 | 多空组合 top/bottom 比例 |
| `ls_method` | str | `"equal_weight"` | 多空组合构建方法 |
| `max_lag` | int | 12 | IC 衰减最大滞后阶数 |
| `enable_drift_detection` | bool | True | 启用漂移检测 |
| `drift_warning_threshold` | float | 0.05 | 漂移预警阈值 |
| `drift_severe_threshold` | float | 0.01 | 严重漂移阈值 |
| `enable_health_check` | bool | True | 启用健康度评估 |

`PipelineV2ConfigUnified` 新增 `backtest: BacktestConfig` 字段。

---

## 14. L2 磁盘缓存层 (v2.2.1 新增)

### 14.1 架构概览

L2 磁盘缓存层为回测引擎的数据加载阶段提供透明加速。设计三原则 (优先级递减):

1. **P0 可调试性**: 三层透明度 — 日志层 (HIT/MISS/INVALIDATE) + 元数据层 (.meta.json) + 环境变量逃生舱
2. **P1 正确性**: 数据指纹校验 (head/tail hash + nan_ratio) + 损坏自愈 + 双轴 freq 保真
3. **P2 性能**: 数据真相驱动失效 (不依赖 TTL 猜测)

```
CachedDataLoader (统一入口)
├── FactorMatrixCache   → FactorPivotAdapter.get_pivoted()
│   └── CacheManager    → .parquet + .meta.json
├── PriceMatrixCache    → PriceQuery.get_price_matrix()
│   └── CacheManager    → .parquet + .meta.json
└── FwdReturnsCache     → compute_fn() (按需)
    └── CacheManager    → .npy + .meta.json
```

### 14.2 `cache_manager.py` — L2 磁盘缓存基础设施

**职责**: 提供通用的磁盘缓存读写,支持 DataFrame (.parquet) 和 ndarray (.npy)。

**核心类**:
- `CacheKey(namespace, identifier, version)`: 缓存键,SHA256 前缀 + 可读后缀
- `CacheMeta`: 元数据,记录来源签名、数据指纹、freq、code_version
- `CacheManager`: 主类,提供 `set()` / `get()` / `get_with_meta()` / `invalidate()` / `clear_all()` / `status()` / `verify()`

**关键设计**:
- 环境变量 `FACTOR_PIPELINE_CACHE=disabled` 一键禁用 (最高优先级)
- 每个缓存文件附 `.meta.json`,记录完整来源信息 (SQL/参数/db_loaded_at_max)
- 读取时校验指纹,不匹配自动删除 (损坏自愈)
- DataFrame 双轴 freq 检测与恢复 (parquet 不保留 DatetimeIndex.freq)

### 14.3 `price_cache.py` — 价格矩阵缓存

**职责**: 包装 `PriceQuery.get_price_matrix()`,透明缓存结果。

**缓存键**: `price_matrix` 命名空间,identifier = `{field}_{start}_{end}_{stock_hash}_{adjust}_{as_of}`

**source_signature**: 包含 `db_loaded_at_max`,用于 staleness 追溯。

### 14.4 `factor_cache.py` — 因子矩阵缓存

**职责**: 包装 `FactorPivotAdapter.get_pivoted()`,透明缓存每个因子的结果。

**部分命中**: 请求多个因子时,仅未缓存的因子走 adapter,已缓存的直接从磁盘读取。

**缓存键**: `factor_matrix` 命名空间,identifier = `{factor_name}_{start}_{end}_{stock_hash}`

### 14.5 `fwd_returns_cache.py` — 前向收益缓存

**职责**: 缓存 `fwd_returns` ndarray,接受 `compute_fn` 按需计算。

**API**: `get_or_compute(stock_codes, start_date, end_date, field, adjust, compute_fn)`

**缓存键**: `fwd_returns` 命名空间,identifier = `{field}_{adjust}_{start}_{end}_{stock_hash}`

### 14.6 `cached_data_loader.py` — 统一入口

**职责**: 封装 FactorMatrixCache + PriceMatrixCache,提供单一入口。业务代码一处替换即可启用缓存。

**替换方式**:
```python
# 旧代码
adapter = FactorPivotAdapter(DB_PATH)
pq = PriceQuery(DB_PATH)
factor_data = adapter.get_pivoted([...], start_date, end_date)
price_data = pq.get_price_matrix(field="close", start_date, end_date)

# 新代码 (启用缓存)
loader = CachedDataLoader(db_path=DB_PATH, cache_dir="./cache", enabled=True)
factor_data = loader.get_pivoted_factors([...], start_date, end_date)
price_data = loader.get_price_matrix(field="close", start_date, end_date)
```

**统一管理 API**: `status()` / `clear_all()` / `invalidate_factor()` / `invalidate_price()`

### 14.7 性能数据

| 场景 | 第一次 (DB) | 第二次 (缓存) | 加速 |
|------|------------|-------------|------|
| 因子矩阵查询 (3 因子, Q1 2024) | 0.667s | 0.076s | 8.77x |
| 价格矩阵查询 (close, Q1 2024) | 0.798s | 0.260s | 3.07x |
| 数据加载总计 | 1.466s | 0.336s | 4.36x |
| 端到端 Pipeline (含回测引擎) | 3.862s | 3.714s | 1.04x |

**注意**: 端到端加速被回测引擎计算时间掩盖。数据加载阶段本身加速显著 (4.36x)。

---

## 15. v2.6.0 优化器与漂移检测增强 (规划中, ADR-021/022/023)

### 15.1 章节定位

本章节描述 v2.6.0 的执行方案设计阶段产出。v2.5.0 完成多因子横截面正交化三层架构 (ADR-020) 后, v2.6.0 聚焦于**优化器层面**与**漂移检测层面**的增强, 让三层架构在优化器层面完整闭环, 同时对齐 ADR-004 (目标函数) / ADR-005 (搜索空间) / ADR-006 (扩展窗口 CV) 三项设计契约。

**核心文档**:
- [docs/ANALYSIS_V2.6.0.md](docs/ANALYSIS_V2.6.0.md) v1.1 (810 行) — 深度核查 8 类问题 / 8 项任务 / 11 项风险
- [docs/EXECUTION_V2.6.0.md](docs/EXECUTION_V2.6.0.md) (1595 行) — 9 个执行阶段 (E1-E9), ~59 新测试

### 15.2 9 阶段执行方案 (E1-E9)

```
v2.6.0 优化器与漂移检测增强 [ADR-004/005/006 修订 + ADR-021/022/023 新增]
│
├─ E1: P3-11' 文档状态修正 (P0, 无依赖, 仅文档)
├─ E2: P3-10' migration_threshold 字段位置 + ADR-005 更新 (P0)
├─ E3: P3-1' IC 时间加权 EWMA (P1)
├─ E4: P3-9' 目标函数对齐 ADR-004 — health_penalty 代理 (P1, 依赖 E3)
├─ E5: P3-13 正交化参数纳入搜索空间 (P1, 依赖 E2)
├─ E6: P3-14 几何诊断纳入目标函数 (P2, 依赖 E5)
├─ E7: P3-15 Layer 3 显著性最终验证 (P2, 依赖 E4)
├─ E8: P3-12' 阈值漂移监测 (P2, 依赖 E4)
└─ E9: 文档验证 + 全量回归 (P1, 依赖 E1-E8)
```

| 阶段 | 任务 | 优先级 | 依赖 | 测试数 | 关键文件变更 |
|------|------|--------|------|--------|-------------|
| E1 | P3-11' 文档状态修正 | P0 | 无 | 0 (仅文档) | DECISIONS.md |
| E2 | P3-10' migration_threshold 字段位置 + ADR-005 | P0 | 无 | ~5 | optimizer.py:150-158, DECISIONS.md |
| E3 | P3-1' IC 时间加权 EWMA | P1 | 无 | ~8 | factor_metrics.py, optimizer.py |
| E4 | P3-9' 目标函数对齐 ADR-004 | P1 | E3 | ~10 | optimizer.py (_composite_objective) |
| E5 | P3-13 正交化参数纳入搜索空间 | P1 | E2 | ~8 | optimizer.py (DEFAULT_SEARCH_SPACE_ORTH) |
| E6 | P3-14 几何诊断 + Adapter 扩展 | P2 | E5 | ~12 | adapters.py, optimizer.py |
| E7 | P3-15 Layer 3 显著性最终验证 | P2 | E4 | ~6 | optimizer.py (_validate_significance) |
| E8 | P3-12' 阈值漂移监测 | P2 | E4 | ~10 | backtest/threshold_drift_monitor.py (新建) |
| E9 | 文档验证 + 全量回归 | P1 | E1-E8 | 8 项手工校验 | README/CHANGELOG/CODE_WIKI/DECISIONS |

**总计**: ~59 新测试 + 860 基线 = ~919 passed

### 15.3 ADR-021: 目标函数对齐 ADR-004 — health_penalty 代理指标方案

**问题**: ADR-004 设计 `score = IC - stability_penalty - ks_penalty - health_penalty - coverage_penalty`, 但代码实现 (1) 缺 health_penalty 项, (2) fidelity 符号相反 (+ 奖励而非 - 惩罚), (3) `HealthMonitorAdapter.build_report_from_engine` 需要 engine_results 字典, 只能在回测后计算, 不能在 CV fold 内部直接调用 (时序依赖).

**决策 (ADR-021)**: 采用代理指标方案 B — 在 CV fold 内部用 IC decay / hit_rate / ic_volatility 三档近似 health_score:

```python
def _health_penalty_proxy(self, ic_array: np.ndarray) -> float:
    decay_ratio = ...  # IC[t] / IC[0], 衰减比例
    hit_rate = ...     # IC > 0 比例
    ic_vol = float(np.nanstd(ic_array))

    if decay_ratio < 0.5 or hit_rate < 0.4 or ic_vol > 0.2:
        return 0.5  # ADR-004: < 40 → -0.5
    elif decay_ratio < 0.8 or hit_rate < 0.5 or ic_vol > 0.15:
        return 0.2  # ADR-004: < 60 → -0.2
    return 0.0
```

同时修正 fidelity 符号: `+ lambda_fidelity * fidelity` → `- lambda_fidelity * (1 - fidelity)`.

### 15.4 ADR-022: 搜索空间扩展 — 正交化参数纳入 (P3-13)

**问题**: v2.5.0 完成正交化三层架构, 但优化器搜索空间仍为 8 维 ADR-005 阈值, 未纳入正交化参数.

**决策 (ADR-022)**: 新增 `DEFAULT_SEARCH_SPACE_ORTH` 搜索空间, 默认关闭 (`search_orth=False`):

| 维度 | 类型 | 范围 | 默认值 | 说明 |
|------|------|------|--------|------|
| `orth_method` | categorical | ['symmetric', 'ridge', 'pca', 'gram_schmidt', 'cholesky'] | 'symmetric' | 正交化算法 |
| `align_mode` | categorical | ['intersection', 'union_nan', 'raise_on_mismatch'] | 'intersection' | 因子对齐模式 |
| `ridge_lambda` | float (log) | [0.01, 100.0] | 1.0 | Ridge λ (仅 orth_method='ridge' 时生效) |

**不搜索 `orth_enabled`** (默认关闭, 启用搜索即隐含启用正交化).

**look-ahead bias 防护**: 正交化参数的 fit 必须在 CV fold 内部用 train 数据完成, 不能用全量数据 fit + train/test transform.

### 15.5 ADR-023: 阈值漂移监测 — ThresholdDriftMonitor (P3-12')

**问题**: `optimizer.optimize()` 返回 best_params 后, 阈值组合在部署后可能因市场体制变化而失效. 现有 `UnifiedDriftReporter` 监测的是**因子值漂移**, 不监测**阈值组合本身的有效性漂移**.

**决策 (ADR-023)**: 新建 `backtest/threshold_drift_monitor.py`, 采用 EWMA 衰减检测:

```python
class ThresholdDriftMonitor:
    def __init__(self, best_score, best_params, halflife=63,
                 decay_threshold=0.2, min_observations=5):
        ...

    def update(self, current_score) -> Dict:
        # EWMA: alpha = 1 - exp(-ln2/halflife)
        # 触发: EWMA(current) < (1 - decay_threshold) * best_score
        # 返回 {ewma_score, decay_ratio, needs_research, n_observations}
```

**与 UnifiedDriftReporter 的边界**:

| 监测器 | 监测对象 | 信号源 | 触发动作 |
|--------|---------|--------|---------|
| `UnifiedDriftReporter` | 因子值漂移 | structure (KS) + performance (ICIR) + turnover | 因子重新分类/插补 |
| `ThresholdDriftMonitor` | 阈值组合有效性 | best_score EWMA 衰减 | 阈值重新搜索 (调用 optimizer.optimize) |

### 15.6 核心约束 (6 项)

1. **基线保护**: 默认行为不变, 不影响 860 测试基线
2. **ADR 契约对齐**: ADR-004 (health_penalty) 改代码, ADR-005 (static/dynamic) 改 ADR
3. **TDD 开发**: 每阶段严格 Red-Green-Refactor, 含手工数值校验
4. **数值精度**: 与独立 numpy/statsmodels 实现对比, 精度 < 1e-10
5. **无 look-ahead bias**: 正交化参数搜索时必须在 CV fold 内部 fit (用 train 数据)
6. **计算成本控制**: FactorSignificanceTest 仅用于最终验证, 不用于每 trial 评估

### 15.7 学术依据修正 (v1.0 → v1.1)

| 任务 | v1.0 误引 | v1.1 修正 | 原因 |
|------|----------|----------|------|
| P3-1 IC 时间加权 | Cohen-Coval-Pastor (2005) | Ferson-Siegel (2001) | Cohen-Coval 讨论基金持仓相似度, 与 EWMA 无关 |
| P3-1 IC 时间加权 | Dimson / Moreira-Muir | Barroso-Santa-Clara (2015) | Dimson 是 beta 估计, Moreira-Muir 是 risk premium |
| P3-12 阈值漂移 | Hsu (2010) 误称 Bayesian | Sullivan-TW (1999) + McLean-Pontiff (2016) | Hsu (2010) 实际是 frequentist SDF |
| P3-11 参数重要性 | — | Bergstra (2011) TPE + Hutter (2014) fANOVA | 拆分原引用 |

### 15.8 风险与回退

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| health_penalty 代理与 health_score 相关性不足 | 中 | 目标函数引导偏差 | E4 手工校验 + A/B 测试 |
| 正交化搜索维度增加致 n_trials 不足 | 中 | 优化不收敛 | n_trials 从 100 提到 150-200 |
| FactorSignificanceTest 计算成本超预期 | 低 | E7 集成测试超时 | 仅最终验证, 不每 trial 评估 |
| fidelity 符号修正改变历史 best_score | 中 | 与 v2.5.0 best_score 不可比 | 文档标注 + 重新运行优化 |

**8 阶段独立回退**: 各阶段文件变更隔离, 失败可独立回退 (详见 EXECUTION_V2.6.0.md:1555-1566).

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026-05-12 | 初始版本：统一编排层 + 顺序校验 |
| v2.0.0 | 2026-05-17 | 智能版本：指纹诊断 + 自适应分类 + 语义融合 + 三重中性化 + GARCH 白化 |
| v2.0.1 | 2026-07-01 | 文档更新：补充 FactorHealthMonitor 五维健康度评估 |
| v2.1.0 | 2026-07-01 | 架构修复：软路由 + 阈值校准 + 统一 fit() + 适配器 Warning + 迁移权重 + KS 显著性 + importlib 重构 |
| v2.2.0 | 2026-07-01 | Backtest 集成：回测引擎 (95/95) + 双轨漂移融合 + HealthMonitor 适配器 + BacktestConfig 配置扩展 |
| v2.2.1 | 2026-07-01 | L2 磁盘缓存层：CacheManager + PriceMatrixCache + FactorMatrixCache + FwdReturnsCache + CachedDataLoader (85/85) |
| v2.2.2 | 2026-07-01 | 漂移检测与优化器改进：滚动窗口 KS + Pipeline-in-the-loop + per-factor min_dates + 三模式信号融合 + CV 改进 + 分组并行 A/B 实验 (ADR-009) |
| v2.2.3 | 2026-07-02 | 外部模块子包化 + 命名空间根治 (ADR-013): 6 个外部模块 __init__.py + pyproject.toml, importlib/sys.path 黑魔法清理 |
| v2.2.4 | 2026-07-02 | 依赖锁定 (ADR-014): pyproject.toml REQUIRED + OPTIONAL extras 分离, 删除优雅回退, HAS_SCIPY/STATSMODELS 死代码清理 |
| v2.2.5 | 2026-07-02 | adapters 重构 (ADR-015): NeutralizerAdapter REQUIRED 化 + GarchWhiteningAdapter 模块级导入 |
| v2.2.6 | 2026-07-02 | 技术债清理 (ADR-016): Factor_Trading_v3.0 子包化 + data_bridge importlib hack 清理 + test_parallel flaky 修复 |
| v2.3.0 | 2026-07-02 | 跨版本 CI 矩阵 (ADR-017): GitHub Actions (Python 3.10/3.11/3.12 × ubuntu) + tox 双轨 |
| v2.4.0 | 2026-07-03 | 外部模块内化 (ADR-019): 5 个处理模块 (Fingerprint/Decoupler/AdaptiveWinsor/Imputer/Neutralizer) 内化到 modules/, 632 passed 零回归 |
| v2.5.0 | 2026-07-03 | 多因子正交化三层架构 (ADR-020): Layer 1/2/3 分离 + 5 种正交化算法 + VRR/κ/VIF 诊断 + 双重 Lasso (Belloni 2014 PDS) + Rolling + Grouped + TripleChain, 860 passed + 5 skipped |
| v2.6.0 | 2026-07-04 | 优化器与漂移检测增强 (已实施, ADR-021/022/023, E1-E9 全部完成): 6 项目标函数 (IC-vol-cov-ks-health-redundancy) + 正交化参数搜索空间 (8→11 维) + Layer 3 显著性最终验证 (Belloni 2014 PDS) + ThresholdDriftMonitor (EWMA 衰减检测), 918 passed + 6 skipped + 11 subtests |
| v3.1.0 | 2026-07-09 | Audit-Driven Code Quality Remediation (ADR-026): P0×8+P1×8+P2+×15 (断言恒真式重写 5 + 设计约束 10 + 端到端 2 + E5 测试 5) + spec 反向对齐 11 项, audit-driven-development 4 阶段流程 (Spec Inventory→Multi-Dimensional Audit→Fix Priority Matrix→Fix Baseline+Tracking), 子集回归 754 passed+1 skipped |