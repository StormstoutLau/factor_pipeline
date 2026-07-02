# -*- coding: utf-8 -*-
"""
统一配置模块
集中管理项目中的常量、权重和默认配置，避免多处重复定义
"""

from typing import Dict

# 质量评估权重配置
# 用于综合质量评分的各维度权重，总和应为 1.0
DEFAULT_QUALITY_WEIGHTS: Dict[str, float] = {
    'missing_improvement': 0.15,
    'outlier_improvement': 0.20,
    'skewness_improvement': 0.15,
    'kurtosis_improvement': 0.10,
    'information_retention': 0.20,
    'rank_retention': 0.15,
    'stability_improvement': 0.05,
}

# 兼容性权重配置（不含 kurtosis_improvement，用于旧版评估逻辑）
COMPAT_QUALITY_WEIGHTS: Dict[str, float] = {
    'missing_improvement': 0.15,
    'outlier_improvement': 0.20,
    'skewness_improvement': 0.15,
    'information_retention': 0.25,
    'rank_retention': 0.20,
    'stability_improvement': 0.05,
}

# 质量评估阈值
QUALITY_THRESHOLDS = {
    'min_acceptable_score': 0.7,
    'min_information_retention': 0.8,
    'min_rank_retention': 0.8,
    'min_outlier_improvement': 0.1,
    'min_skewness_improvement': 0.2,
    'min_missing_improvement': 0.1,
}

# 数据诊断阈值
DIAGNOSIS_THRESHOLDS = {
    'max_missing_ratio': 0.5,
    'max_outlier_ratio': 0.15,
    'skewness_threshold': 0.5,
    'kurtosis_threshold': 3.0,
}

# 默认最小数据点数
MIN_DATA_POINTS = 10
