# Factor Processing Pipeline v1.0

## 统一因子处理流水线

**Factor Processing Pipeline** 是一个面向量化投资领域的统一因子处理编排系统，将三个独立开发的 v2.0 模块（插补、处理、中性化）整合为标准化、可配置、带学术级顺序校验的完整流水线。

> **GitHub**: https://github.com/StormstoutLau/factor_pipeline

---

## 目录

- [核心结论](#核心结论)
- [架构设计](#架构设计)
- [模块组成](#模块组成)
- [处理顺序校验](#处理顺序校验)
- [与开源社区对比](#与开源社区对比)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [文件结构](#文件结构)

---

## 核心结论

### 为什么插补必须是第一步？

从学术理论与业界实践双重维度验证：

| 维度 | 分析 |
|------|------|
| **统计原理** | 去极值（MAD/分位数）需要完整数据计算统计量，缺失数据会导致阈值估计有偏 |
| **分布假设** | 变换参数（Box-Cox lambda）基于完整数据估计，缺失会扭曲参数 |
| **标准化基准** | 均值/标准差计算需要完整样本，缺失导致标准化基准偏移 |
| **业界标准** | Barra、MSCI 等框架均遵循 Imputation → Outlier → Transform → Standardize → Neutralize 顺序 |

**标准五步法：**

```
原始因子数据
    ↓
缺失值插补 (Imputation)
    ↓
去极值 (Outlier Detection)
    ↓
自适应变换 (Transformation)
    ↓
标准化 (Standardization)
    ↓
中性化 (Neutralization)
    ↓
因子合成 / 模型输入
```

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    FactorProcessingPipeline                      │
│                     (统一编排层 Orchestrator)                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   ORDER     │  │   ADAPTER   │  │   STATE     │            │
│  │  VALIDATOR  │  │   LAYER     │  │  TRACKER    │            │
│  │  (顺序校验)  │  │  (适配器层)  │  │  (状态追踪)  │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│         └────────────────┼────────────────┘                    │
│                          ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  IMPUTER → OUTLIER → TRANSFORM → STANDARDIZE → NEUTRAL │   │
│  │   [cyan]    [green]    [green]      [green]      [pink]  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 三大核心组件

| 组件 | 职责 | 独特价值 |
|------|------|---------|
| **PipelineOrderValidator** | 校验处理步骤顺序 | 开源社区完全空白领域 |
| **Adapter Layer** | 统一三个模块接口 | 将异构接口封装为 sklearn-style |
| **State Tracker** | 追踪每步输入/输出/统计量 | 完整可复现的数据血缘 |

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
| **NEUTRALIZATION 必须在最后** | 中性化基于回归残差，后续变换会破坏效果 |

### 错误顺序拦截示例

```python
# 错误：去极值在插补之前
pipeline = FactorProcessingPipeline([
    ProcessingAdapter(process_type='outlier'),  # ❌ 第一步
    ImputerAdapter(strategy='auto'),             # 插补放第二
])
# → ValueError: 第一步必须是插补(IMPUTATION)
#   原因: 去极值(MAD/分位数)需要完整数据计算统计量

# 错误：标准化在去极值之前
pipeline = FactorProcessingPipeline([
    ImputerAdapter(strategy='auto'),
    ProcessingAdapter(process_type='standardization'),  # ❌
    ProcessingAdapter(process_type='outlier'),          # 去极值放后面
])
# → ValueError: standardization 必须在 outlier 之后
#   原因: 极值会显著影响标准化后的分布
```

---

## 与开源社区对比

### 主流量化框架分析

| 项目 | Stars | 数据处理覆盖 | 顺序校验 | 活跃度 |
|------|-------|-------------|---------|--------|
| **Microsoft Qlib** | 29.2k | ⭐⭐⭐⭐⭐ | ❌ 无 | 极高 |
| **Quantopian Alphalens** | 3.8k | ⭐⭐ | ❌ 无 | 停滞 |
| **Zipline** | 17k | ⭐⭐ | ❌ 无 | 停滞 |
| **本 Pipeline** | - | ⭐⭐⭐⭐⭐ | ✅ **独有** | 活跃 |

### 功能深度对比

| 功能 | 本 Pipeline | Qlib | Alphalens |
|------|------------|------|-----------|
| 缺失值插补 | ✅ 5策略分层智能插补 | ⚠️ 简单填充/删除 | ❌ 无 |
| 自适应去极值 | ✅ 6方法智能选择 | ⚠️ 仅Tanh压缩 | ❌ 无 |
| 分布变换 | ✅ 自适应Box-Cox/YJ | ❌ 无 | ❌ 无 |
| 标准化 | ✅ 统计量投票选择 | ✅ Z-score/Rank | ❌ 无 |
| 中性化 | ✅ 行业/市值/指数 | ❌ 无 | ❌ 无 |
| **顺序校验** | ✅ **学术级校验器** | ❌ 无 | ❌ 无 |
| 流程追踪 | ✅ 每步状态追踪 | ⚠️ 基础日志 | ❌ 无 |

### 核心边际贡献

1. **处理顺序校验器** — 开源社区完全空白，将 Barra/MSCI 最佳实践编码为可执行规则
2. **自适应方法选择** — 基于数据特征自动选择最优算法，远超固定参数方案
3. **统一 Pipeline 封装** — 三个异构模块整合为标准化接口

---

## 快速开始

### 方式 1: 默认五步法

```python
from factor_pipeline import FactorProcessingPipeline

# 创建默认流水线
pipeline = FactorProcessingPipeline.default_pipeline()

# 拟合并变换
result = pipeline.fit_transform(factor_data)

# 查看执行摘要
print(pipeline.get_execution_summary())
```

### 方式 2: 自定义步骤

```python
from factor_pipeline import (
    FactorProcessingPipeline,
    ImputerAdapter,
    ProcessingAdapter,
    NeutralizerAdapter,
)

pipeline = FactorProcessingPipeline([
    ImputerAdapter(strategy='auto'),
    ProcessingAdapter(process_type='outlier', method='mad'),
    ProcessingAdapter(process_type='transformation', method='auto'),
    ProcessingAdapter(process_type='standardization', method='z_score'),
    NeutralizerAdapter(
        neutralization_type='industry',
        industry_data=industry_series
    ),
])

result = pipeline.fit_transform(factor_data)
```

### 方式 3: 配置驱动

```python
from factor_pipeline import PipelineConfig, FactorProcessingPipeline

# 加载配置
config = PipelineConfig.from_json('pipeline_config.json')

# 从配置创建流水线
pipeline = FactorProcessingPipeline(config=config)
result = pipeline.fit_transform(factor_data)
```

---

## 配置说明

### 默认配置结构

```python
PipelineConfig(
    name="default_factor_pipeline",
    description="标准因子处理流水线",
    steps=[
        StepConfig(
            step_type=StepType.IMPUTATION,
            module_path="Factor_Imputer_v2.0",
            class_name="HierarchicalImputer",
            params={'strategy': 'auto'}
        ),
        StepConfig(
            step_type=StepType.OUTLIER_DETECTION,
            module_path="Factor_AdaptiveWinsor",
            class_name="SmartOutlierDetector",
            params={'method': 'auto', 'auto_select': True}
        ),
        StepConfig(
            step_type=StepType.TRANSFORMATION,
            module_path="Factor_AdaptiveWinsor",
            class_name="AdaptiveTransformer",
            params={'method': 'auto', 'auto_optimize': True}
        ),
        StepConfig(
            step_type=StepType.STANDARDIZATION,
            module_path="Factor_AdaptiveWinsor",
            class_name="AdaptiveStandardizer",
            params={'method': 'auto'}
        ),
        StepConfig(
            step_type=StepType.NEUTRALIZATION,
            module_path="Factor_Neutralizer_v2.0",
            class_name="FactorNeutralizer",
            params={'neutralization_type': 'industry'}
        ),
    ],
    strict_order=True,      # 启用严格顺序校验
    allow_skip=True,        # 允许跳过某些步骤
    track_intermediate=True # 追踪中间状态
)
```

### 配置保存与加载

```python
# 保存为 JSON
config.to_json('pipeline_config.json')

# 从 JSON 加载
config = PipelineConfig.from_json('pipeline_config.json')
```

---

## API 参考

### FactorProcessingPipeline

| 方法 | 说明 |
|------|------|
| `default_pipeline()` | 类方法，创建默认五步法流水线 |
| `fit(X)` | 拟合整个流水线 |
| `transform(X)` | 应用整个流水线 |
| `fit_transform(X)` | 拟合并变换 |
| `get_execution_summary()` | 获取执行摘要 |

### PipelineOrderValidator

| 方法 | 说明 |
|------|------|
| `validate(steps, strict=True)` | 验证步骤顺序是否合法 |
| `suggest_correction(steps)` | 建议修正后的顺序 |

### 适配器

| 适配器 | 封装模块 | 核心功能 |
|--------|---------|---------|
| `ImputerAdapter` | Factor_Imputer_v2.0 | 缺失值插补 |
| `ProcessingAdapter` | Factor_AdaptiveWinsor | 去极值/变换/标准化 |
| `NeutralizerAdapter` | Factor_Neutralizer_v2.0 | 因子中性化 |

---

## 文件结构

```
factor_pipeline/
├── __init__.py                 # 包入口
├── config.py                   # 配置管理 (StepType, PipelineConfig)
├── adapters.py                 # 三个模块的统一适配器
├── pipeline.py                 # 核心流水线 + 顺序校验器
├── demo.py                     # 演示验证脚本
├── cli_arcade_intro.html       # CLI 风格介绍页面
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

---

## 版本信息

- **Pipeline 版本**: v1.0.0-orchestrator
- **子模块版本**: Factor_Imputer_v2.0 / Factor_AdaptiveWinsor / Factor_Neutralizer_v2.0
- **构建日期**: 2026.05.12
- **状态**: STABLE

---

## 学术依据

本流水线的处理顺序基于以下学术与业界标准：

- Barra 多因子模型数据处理规范
- MSCI 因子标准化最佳实践
- Quantopian 因子研究框架
- 《Quantitative Equity Portfolio Management》(Qian et al.)
- 《Active Portfolio Management》(Grinold & Kahn)
