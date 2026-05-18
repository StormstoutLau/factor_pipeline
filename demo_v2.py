# -*- coding: utf-8 -*-
"""
Factor Processing Pipeline v2.0 演示与验证

展示完整的指纹提取 → 分类 → 差异化处理 → 迁移监测流程。
使用模拟数据验证：
1. PB（静态因子）应被分类为 STATIC
2. 短期反转（动态因子）应被分类为 DYNAMIC
3. 1个月动量（混合因子）应被分类为 MIXED
"""

import numpy as np
import pandas as pd
import sys
import os

# 将当前目录加入路径
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Factor_Fingerprint import (
    FactorFingerprinter, FactorFingerprint, FingerprintConfig,
    AdaptiveFactorClassifier, ClassificationConfig,
    MonitorConfig,
)
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2, PipelineV2Config,
    StaticFactorPipeline, DynamicFactorPipeline, MixedFactorPipeline
)


def create_static_factor(n_dates=60, n_stocks=50, seed=42):
    """
    创建静态因子（如PB）
    特征：高自相关，截面排序稳定
    """
    np.random.seed(seed)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='M')
    stocks = [f"STOCK_{i:04d}" for i in range(n_stocks)]

    # 基础值：每只股票有一个固定的"真实"PB值
    base_pb = np.random.lognormal(mean=0.5, sigma=0.5, size=n_stocks)

    # 时序演化：缓慢均值回归 + 小幅噪声
    data = np.zeros((n_dates, n_stocks))
    data[0] = base_pb * (1 + np.random.normal(0, 0.05, n_stocks))

    for t in range(1, n_dates):
        # 强自相关：今天的值 = 0.95 * 昨天的值 + 0.05 * 基础值 + 噪声
        data[t] = 0.95 * data[t-1] + 0.05 * base_pb + np.random.normal(0, 0.02, n_stocks)

    df = pd.DataFrame(data, index=dates, columns=stocks)
    return df


def create_dynamic_factor(n_dates=60, n_stocks=50, seed=43):
    """
    创建动态因子（如短期反转）
    特征：低自相关，近似白噪声
    """
    np.random.seed(seed)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='M')
    stocks = [f"STOCK_{i:04d}" for i in range(n_stocks)]

    # 近似白噪声 + 微弱的均值回归
    data = np.random.normal(0, 1, size=(n_dates, n_stocks))

    # 添加微弱的自相关（模拟短期反转的真实特征）
    for t in range(1, n_dates):
        data[t] = -0.1 * data[t-1] + 0.9 * data[t]  # 轻微负自相关

    df = pd.DataFrame(data, index=dates, columns=stocks)
    return df


def create_mixed_factor(n_dates=60, n_stocks=50, seed=44):
    """
    创建混合因子（如1个月动量）
    特征：中等自相关，介于静态和动态之间
    """
    np.random.seed(seed)
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='M')
    stocks = [f"STOCK_{i:04d}" for i in range(n_stocks)]

    # 中等自相关
    data = np.zeros((n_dates, n_stocks))
    data[0] = np.random.normal(0, 1, n_stocks)

    for t in range(1, n_dates):
        # 中等自相关：phi ≈ 0.6
        data[t] = 0.6 * data[t-1] + np.random.normal(0, 0.8, n_stocks)

    df = pd.DataFrame(data, index=dates, columns=stocks)
    return df


def demo_fingerprint_extraction():
    """演示1: 指纹提取"""
    print("=" * 70)
    print("演示 1: 因子指纹提取")
    print("=" * 70)

    # 创建三种因子
    pb_data = create_static_factor(seed=42)
    reversal_data = create_dynamic_factor(seed=43)
    momentum_data = create_mixed_factor(seed=44)

    factor_dict = {
        'PB': pb_data,
        'ShortTerm_Reversal': reversal_data,
        'Momentum_1M': momentum_data,
    }

    # 提取指纹
    config = FingerprintConfig(min_window=24, decay_halflife=12)
    fingerprinter = FactorFingerprinter(config)

    print("\n提取因子指纹...")
    fingerprints = fingerprinter.batch_extract(factor_dict)

    print("\n指纹结果:")
    print("-" * 70)
    for name, fp in fingerprints.items():
        print(f"\n{name}:")
        print(f"  AR(1)中位数:       {fp.ar1_median:.4f}")
        print(f"  截面秩自相关:      {fp.rank_autocorr:.4f}")
        print(f"  半衰期:            {fp.half_life:.1f}")
        print(f"  偏度标准差:        {fp.skewness_std:.4f}")
        print(f"  峰度标准差:        {fp.kurtosis_std:.4f}")
        print(f"  JS散度均值:        {fp.js_divergence_mean:.4f}")
        print(f"  静态-动态得分:     {fp.sd_score:.4f}")
        print(f"  复杂度需求:        {fp.complexity_need:.4f}")
        print(f"  信噪比估计:        {fp.snr_estimate:.4f}")

    return factor_dict, fingerprints


def demo_classification(fingerprints):
    """演示2: 因子分类"""
    print("\n" + "=" * 70)
    print("演示 2: 因子自适应分类")
    print("=" * 70)

    config = ClassificationConfig(soft_boundary=True)
    classifier = AdaptiveFactorClassifier(config)

    print("\n分类结果:")
    print("-" * 70)

    results = classifier.batch_classify(fingerprints)

    for name, result in results.items():
        print(f"\n{name}:")
        print(f"  主类型:     {result.primary_type.value}")
        print(f"  主概率:     {result.primary_prob:.4f}")
        if result.secondary_type:
            print(f"  次类型:     {result.secondary_type.value}")
            print(f"  次概率:     {result.secondary_prob:.4f}")
        print(f"  硬分类:     {result.is_hard}")
        print(f"  置信度:     {result.confidence:.4f}")

    # 验证预期
    print("\n验证:")
    print(f"  PB -> STATIC:         {'✓ PASS' if results['PB'].primary_type.value == 'static' else '✗ FAIL'}")
    print(f"  Reversal -> DYNAMIC:  {'✓ PASS' if results['ShortTerm_Reversal'].primary_type.value == 'dynamic' else '✗ FAIL'}")
    print(f"  Momentum -> MIXED:    {'✓ PASS' if results['Momentum_1M'].primary_type.value == 'mixed' else '✗ FAIL'}")

    return results


def demo_pipeline_v2(factor_dict, industry_data=None):
    """演示3: 完整 Pipeline v2.0（纯统计模式）"""
    print("\n" + "=" * 70)
    print("演示 3: FactorProcessingPipelineV2 完整流程")
    print("=" * 70)

    config = PipelineV2Config(
        fingerprint=FingerprintConfig(min_window=24),
        classification=ClassificationConfig(soft_boundary=True),
        monitor=MonitorConfig(),
        dynamic_decorrelation_strength=0.8,  # 80%解耦
        mixed_conditional_transform=True,
    )

    pipeline = FactorProcessingPipelineV2(config)

    print("\n拟合流水线（纯统计模式）...")
    pipeline.fit(factor_dict, industry_data=industry_data)

    print("\n" + pipeline.get_execution_summary())

    print("\n应用流水线...")
    results = pipeline.transform(factor_dict)

    print("\n处理后数据形状:")
    for name, data in results.items():
        print(f"  {name}: {data.shape}")

    return pipeline, results


def demo_semantic_fusion(factor_dict, industry_data=None):
    """演示3b: 语义-统计融合 Pipeline"""
    print("\n" + "=" * 70)
    print("演示 3b: 语义-统计融合 Pipeline")
    print("=" * 70)

    # 因子构造描述
    descriptions = {
        'PB': '市净率因子，基于最新财报数据',
        'ShortTerm_Reversal': '短期反转因子，基于过去1个月收益率',
        'Momentum_1M': '1个月动量因子',
    }

    config = PipelineV2Config(
        fingerprint=FingerprintConfig(min_window=24),
        classification=ClassificationConfig(soft_boundary=True),
        monitor=MonitorConfig(),
        dynamic_decorrelation_strength=0.8,
        mixed_conditional_transform=True,
    )

    pipeline = FactorProcessingPipelineV2(config)

    print("\n拟合流水线（语义-统计融合模式）...")
    print("因子描述:")
    for name, desc in descriptions.items():
        print(f"  {name}: {desc}")

    pipeline.fit(
        factor_dict,
        industry_data=industry_data,
        descriptions=descriptions,
        data_months={'PB': 60, 'ShortTerm_Reversal': 60, 'Momentum_1M': 60}
    )

    print("\n" + pipeline.get_execution_summary())

    print("\n应用流水线...")
    results = pipeline.transform(factor_dict)

    print("\n处理后数据形状:")
    for name, data in results.items():
        print(f"  {name}: {data.shape}")

    return pipeline, results


def demo_migration_monitoring(pipeline, factor_dict):
    """演示4: 迁移监测"""
    print("\n" + "=" * 70)
    print("演示 4: 因子指纹迁移监测")
    print("=" * 70)

    # 模拟下一期数据（轻微变化）
    print("\n模拟下一期数据...")
    next_period_data = {}
    for name, data in factor_dict.items():
        # 添加轻微漂移
        drift = np.random.normal(0, 0.01, data.shape)
        next_period_data[name] = data + drift

    # 检查迁移
    print("\n检查类型迁移...")
    alerts = pipeline.check_migrations(next_period_data)

    if alerts:
        for name, alert_list in alerts.items():
            print(f"\n{name} 触发警报:")
            for alert in alert_list:
                print(f"  [{alert.level}] {alert.from_type.value} -> {alert.to_type.value}")
                print(f"    窗口: {alert.window}期")
                print(f"    建议: {alert.recommendation}")
    else:
        print("  无迁移警报（因子类型稳定）")

    # 稳定性得分
    print("\n因子稳定性得分:")
    for name in factor_dict.keys():
        score = pipeline.monitor.get_factor_stability_score(name)
        print(f"  {name}: {score:.4f}")


def demo_soft_transition(pipeline):
    """演示5: 软过渡权重"""
    print("\n" + "=" * 70)
    print("演示 5: 类型迁移时的软过渡权重")
    print("=" * 70)

    # 为每个因子获取过渡权重
    for name in ['PB', 'ShortTerm_Reversal', 'Momentum_1M']:
        # 使用当前最新指纹
        fp_history = pipeline.monitor.fingerprint_history.get(name, [])
        if fp_history:
            weights = pipeline.monitor.get_transition_weights(name, fp_history[-1])
            print(f"\n{name}:")
            for factor_type, weight in weights.items():
                print(f"  {factor_type.value}: {weight:.4f}")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("Factor Processing Pipeline v2.0 演示")
    print("因子指纹图谱与自适应分类系统")
    print("=" * 70)

    # 演示1: 指纹提取
    factor_dict, fingerprints = demo_fingerprint_extraction()

    # 演示2: 分类
    classifications = demo_classification(fingerprints)

    # 演示3: 完整 Pipeline（纯统计）
    pipeline, results = demo_pipeline_v2(factor_dict)

    # 演示3b: 语义-统计融合 Pipeline
    pipeline_fusion, results_fusion = demo_semantic_fusion(factor_dict)

    # 演示4: 迁移监测
    demo_migration_monitoring(pipeline, factor_dict)

    # 演示5: 软过渡
    demo_soft_transition(pipeline)

    print("\n" + "=" * 70)
    print("演示完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
