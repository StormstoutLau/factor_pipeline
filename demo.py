# -*- coding: utf-8 -*-
"""
Factor Processing Pipeline 演示与验证
展示正确的处理顺序和顺序校验机制
"""

import numpy as np
import pandas as pd
import sys
import os

# 将当前目录加入路径
sys.path.insert(0, os.path.dirname(__file__))

from pipeline import FactorProcessingPipeline, PipelineOrderValidator
from adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter
from config import StepType


def create_sample_data(n_dates=100, n_stocks=50, missing_rate=0.1, seed=42):
    """创建带缺失值的模拟因子数据"""
    np.random.seed(seed)
    
    dates = pd.date_range('2020-01-01', periods=n_dates, freq='B')
    stocks = [f"STOCK_{i:04d}" for i in range(n_stocks)]
    
    # 创建基础因子（重尾分布 + 偏态）
    data = np.random.standard_t(df=3, size=(n_dates, n_stocks))
    data = data * 2 + 10  # 缩放平移
    
    # 添加一些极值
    outlier_mask = np.random.random(data.shape) < 0.02
    data[outlier_mask] = np.random.choice([-1, 1], outlier_mask.sum()) * np.random.uniform(20, 40, outlier_mask.sum())
    
    df = pd.DataFrame(data, index=dates, columns=stocks)
    
    # 添加缺失值
    missing_mask = np.random.random(df.shape) < missing_rate
    df = df.mask(missing_mask)
    
    return df


def create_industry_data(stocks):
    """创建模拟行业数据"""
    industries = ['Technology', 'Finance', 'Healthcare', 'Energy', 'Consumer']
    return pd.Series(
        np.random.choice(industries, len(stocks)),
        index=stocks
    )


def demo_correct_order():
    """演示正确的处理顺序"""
    print("=" * 70)
    print("演示 1: 正确的处理顺序 (插补 → 去极值 → 变换 → 标准化 → 中性化)")
    print("=" * 70)
    
    # 创建数据
    factor_data = create_sample_data(n_dates=50, n_stocks=30, missing_rate=0.15)
    industry_data = create_industry_data(factor_data.columns)
    
    print(f"\n原始数据: {factor_data.shape}")
    print(f"缺失值: {factor_data.isnull().sum().sum()} / {factor_data.size}")
    print(f"均值: {factor_data.mean().mean():.4f}, 标准差: {factor_data.std().mean():.4f}")
    
    # 构建正确顺序的流水线
    pipeline = FactorProcessingPipeline([
        ImputerAdapter(strategy='auto'),
        ProcessingAdapter(process_type='outlier', method='auto'),
        ProcessingAdapter(process_type='transformation', method='auto'),
        ProcessingAdapter(process_type='standardization', method='auto'),
        NeutralizerAdapter(neutralization_type='industry', industry_data=industry_data),
    ])
    
    print(f"\n流水线: {pipeline}")
    
    # 执行
    result = pipeline.fit_transform(factor_data)
    
    print(f"\n{pipeline.get_execution_summary()}")
    
    print(f"\n处理后数据: {result.shape}")
    print(f"缺失值: {result.isnull().sum().sum()}")
    print(f"均值: {result.mean().mean():.6f}, 标准差: {result.std().mean():.4f}")
    
    return result


def demo_wrong_order_validation():
    """演示错误顺序被拦截"""
    print("\n" + "=" * 70)
    print("演示 2: 错误的处理顺序将被校验器拦截")
    print("=" * 70)
    
    # 尝试创建错误顺序: 去极值 → 插补
    print("\n尝试创建顺序: 去极值 → 插补")
    
    try:
        pipeline = FactorProcessingPipeline([
            ProcessingAdapter(process_type='outlier', method='mad'),
            ImputerAdapter(strategy='auto'),
        ])
        print("错误: 流水线创建成功（不应该到这里）")
    except ValueError as e:
        print(f"\n✓ 顺序校验成功拦截!")
        print(f"错误信息:\n{e}")
    
    # 尝试创建错误顺序: 标准化 → 去极值
    print("\n" + "-" * 50)
    print("尝试创建顺序: 标准化 → 去极值")
    
    try:
        pipeline = FactorProcessingPipeline([
            ImputerAdapter(strategy='auto'),
            ProcessingAdapter(process_type='standardization', method='z_score'),
            ProcessingAdapter(process_type='outlier', method='mad'),
        ])
        print("错误: 流水线创建成功（不应该到这里）")
    except ValueError as e:
        print(f"\n✓ 顺序校验成功拦截!")
        print(f"错误信息:\n{e}")


def demo_validator_directly():
    """直接演示校验器"""
    print("\n" + "=" * 70)
    print("演示 3: 直接使用 PipelineOrderValidator 校验顺序")
    print("=" * 70)
    
    test_cases = [
        # (顺序列表, 描述)
        ([StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION], 
         "正确: 插补→去极值→标准化→中性化"),
        ([StepType.OUTLIER_DETECTION, StepType.IMPUTATION, StepType.STANDARDIZATION],
         "错误: 去极值→插补→标准化"),
        ([StepType.IMPUTATION, StepType.STANDARDIZATION, StepType.OUTLIER_DETECTION],
         "错误: 插补→标准化→去极值"),
        ([StepType.IMPUTATION, StepType.OUTLIER_DETECTION, StepType.TRANSFORMATION, StepType.STANDARDIZATION, StepType.NEUTRALIZATION],
         "正确: 完整五步法"),
        ([StepType.NEUTRALIZATION, StepType.IMPUTATION],
         "错误: 中性化→插补"),
    ]
    
    for steps, desc in test_cases:
        is_valid, errors = PipelineOrderValidator.validate(steps)
        status = "✓ 通过" if is_valid else "✗ 失败"
        print(f"\n{status} {desc}")
        if errors:
            for err in errors:
                print(f"   原因: {err.split(chr(10))[0]}")


def demo_default_pipeline():
    """演示默认流水线配置"""
    print("\n" + "=" * 70)
    print("演示 4: 使用默认配置创建流水线")
    print("=" * 70)
    
    from config import PipelineConfig
    
    config = PipelineConfig.default_config()
    print(f"\n默认配置名称: {config.name}")
    print(f"描述: {config.description}")
    print(f"\n步骤:")
    for i, step in enumerate(config.steps, 1):
        print(f"  {i}. {step.step_type.value} -> {step.class_name} ({step.module_path})")
    
    # 保存配置
    config_path = os.path.join(os.path.dirname(__file__), 'default_pipeline_config.json')
    config.to_json(config_path)
    print(f"\n配置已保存到: {config_path}")
    
    # 从配置创建流水线
    pipeline = FactorProcessingPipeline(config=config)
    print(f"\n从配置创建的流水线: {pipeline}")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("Factor Processing Pipeline 统一流水线演示")
    print("=" * 70)
    
    # 演示1: 正确顺序
    demo_correct_order()
    
    # 演示2: 错误顺序被拦截
    demo_wrong_order_validation()
    
    # 演示3: 直接校验
    demo_validator_directly()
    
    # 演示4: 默认配置
    demo_default_pipeline()
    
    print("\n" + "=" * 70)
    print("演示完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
