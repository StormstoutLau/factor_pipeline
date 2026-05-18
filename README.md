# Factor Processing Pipeline v2.0

## 统一因子处理流水线

**Factor Processing Pipeline** 是一个面向量化投资领域的统一因子处理编排系统。v2.0 在 v1.0 的基础上引入了**因子指纹前置诊断层**、**语义-统计融合分类**、**三条差异化处理管道**、**可选 GARCH 白化**以及**持续迁移监测**，实现从"固定流程"到"智能自适应"的跨越。

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

### v2.0 重大更新（2026.05）

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
    (高AR1)  (低AR1)  (中AR1)
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
├── config.py                   # 配置管理 (StepType, PipelineConfig)
├── adapters.py                 # 统一适配器层
│   ├── PipelineStep            # 抽象基类
│   ├── ImputerAdapter          # 插补适配器
│   ├── ProcessingAdapter       # 处理适配器（去极值/变换/标准化）
│   ├── NeutralizerAdapter      # 中性化适配器
│   └── GarchWhiteningAdapter   # GARCH白化适配器 (v2.0新增)
├── pipeline.py                 # v1.0 核心流水线 + 顺序校验器
├── pipelines_v2.py             # v2.0 智能流水线（指纹+分类+三条管道）
├── demo.py                     # v1.0 演示脚本
├── demo_v2.py                  # v2.0 演示脚本（含语义融合演示）
├── cli_arcade_intro.html       # CLI 风格介绍页面
├── docs/                       # 文档目录 (v2.0新增)
│   ├── doc_pipeline_analysis.md
│   ├── factor_preprocessing_meaning.md
│   └── pipeline_analysis.md
├── tests/                      # 测试目录
│   ├── test_pipelines_v2.py    # v2.0 测试
│   ├── test_pipeline_v2_full.py
│   ├── test_dynamic_pipeline.py
│   └── test_pipeline_comprehensive.py
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

- **Pipeline 版本**: v2.0.0-intelligent
- **子模块版本**: Factor_Imputer_v2.0 / Factor_AdaptiveWinsor / Factor_Neutralizer_v2.0 / Factor_Fingerprint / Factor_Decoupler
- **构建日期**: 2026.05.17
- **状态**: STABLE

### 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v1.0.0 | 2026.05.12 | 初始版本：统一编排层 + 顺序校验 |
| v2.0.0 | 2026.05.17 | 智能版本：指纹诊断 + 自适应分类 + 语义融合 + 三重中性化 + GARCH白化 |

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
