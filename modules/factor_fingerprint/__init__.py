# -*- coding: utf-8 -*-
"""
Factor Fingerprint - 因子指纹与语义理解模块

提供因子指纹提取、自适应分类和语义理解功能。

核心组件：
- FactorFingerprinter: 因子指纹提取器
- AdaptiveFactorClassifier: 自适应因子分类器
- FactorSemanticUnderstanding: 因子构造语义理解系统

设计哲学：
- 数据驱动自适应：因子管道由指纹指标自动决定
- 前瞻偏差防护：指纹在扩展窗口上计算，无未来信息泄露
- 先验知识融合：构造规则语义分析 + 统计指纹

GitHub: https://github.com/StormstoutLau/factor_pipeline
"""

from .core.fingerprint import (
    FactorFingerprinter,
    FactorFingerprint,
    FingerprintConfig,
    FactorType,
)

from .core.classifier import (
    AdaptiveFactorClassifier,
    ClassificationConfig,
    ClassificationResult,
)

from .core.monitor import (
    FactorFingerprintMonitor,
    MonitorConfig,
    MigrationAlert,
)

from .core.semantic_fusion import (
    SemanticPrior,
    BayesianFactorClassifier,
    ConflictArbitrator,
    ConflictDiagnosis,
    ArbitratedResult,
    SemanticStatisticalFusion,
)

from .core.semantic import (
    FactorSemanticUnderstanding,
    FinancialTokenizer,
    FinancialKnowledgeGraph,
    SemanticMatcher,
    FactorMeta,
    ExtractedRule,
    extract_from_text,
    extract_to_meta,
)

from .core.health import (
    FactorHealthMonitor,
    HealthConfig,
    HealthAlertLevel,
    FactorHealthReport,
    HealthAlert,
)

__version__ = "1.0.0"
__all__ = [
    'FactorFingerprinter',
    'FactorFingerprint',
    'FingerprintConfig',
    'FactorType',
    'AdaptiveFactorClassifier',
    'ClassificationConfig',
    'ClassificationResult',
    'FactorFingerprintMonitor',
    'MonitorConfig',
    'MigrationAlert',
    'SemanticPrior',
    'BayesianFactorClassifier',
    'ConflictArbitrator',
    'ConflictDiagnosis',
    'ArbitratedResult',
    'SemanticStatisticalFusion',
    'FactorSemanticUnderstanding',
    'FinancialTokenizer',
    'FinancialKnowledgeGraph',
    'SemanticMatcher',
    'FactorMeta',
    'ExtractedRule',
    'extract_from_text',
    'extract_to_meta',
    'FactorHealthMonitor',
    'HealthConfig',
    'HealthAlertLevel',
    'FactorHealthReport',
    'HealthAlert',
]
