# -*- coding: utf-8 -*-
"""
因子类型感知工作流
集成因子类型感知插补器的完整工作流，支持性能监控与报告生成
"""

import os
import pickle
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .factor_type_aware_imputer import FactorTypeAwareImputer
from .real_factor_workflow import RealFactorWorkflow


class FactorTypeAwareWorkflow(RealFactorWorkflow):
    """因子类型感知工作流（统一版）"""

    def __init__(self, factor_path: str, output_dir: str = None):
        super().__init__(factor_path, output_dir)
        self.factor_type_aware_imputer = None
        self.factor_analysis = None
        self.performance_metrics = {}

    def setup_factor_type_aware_imputer(self, config: dict = None) -> None:
        default_config = {
            "auto_detect_factor_type": True,
            "specified_factor_type": None,
            "enable_parallel": True,
            "enable_caching": True,
            "group_by": "sw_industry",
            "time_aware": True,
            "validate_compliance": True,
        }
        if config:
            default_config.update(config)
        self.factor_type_aware_imputer = FactorTypeAwareImputer(**default_config)

    def run_factor_type_aware_imputation(self) -> pd.DataFrame:
        if self.original_data is None:
            raise ValueError("请先加载因子数据")
        if self.factor_type_aware_imputer is None:
            raise ValueError("请先设置因子类型感知插补器")

        start_time = time.time()
        start_memory = self._get_memory_usage()

        self.processed_data = self.factor_type_aware_imputer.fit_transform(self.original_data)
        self.imputation_report = self.factor_type_aware_imputer.get_imputation_report(
            self.original_data, self.processed_data
        )

        end_time = time.time()
        end_memory = self._get_memory_usage()

        self.performance_metrics = {
            "execution_time": end_time - start_time,
            "memory_usage": end_memory - start_memory,
            "data_shape": self.original_data.shape,
            "missing_rate": self.original_data.isnull().sum().sum() / self.original_data.size,
            "factor_type": self.factor_type_aware_imputer.factor_type,
            "imputation_strategy": self.factor_type_aware_imputer.imputation_strategy,
            "parallel_enabled": self.factor_type_aware_imputer.enable_parallel,
            "caching_enabled": self.factor_type_aware_imputer.enable_caching,
            "n_workers": self.factor_type_aware_imputer.n_workers,
        }

        self.factor_analysis = self.imputation_report.get("factor_type_analysis", {})
        return self.processed_data

    def _get_memory_usage(self) -> float:
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except (ImportError, OSError):
            return 0.0

    def run_complete_factor_type_aware_workflow(self, imputer_config: dict = None) -> dict:
        workflow_results = {
            "success": False,
            "steps_completed": [],
            "errors": [],
            "performance_metrics": {},
            "factor_type_analysis": {},
        }

        try:
            self.load_factor_data()
            workflow_results["steps_completed"].append("data_loaded")

            quality_report = self.analyze_data_quality()
            workflow_results["steps_completed"].append("quality_analyzed")
            workflow_results["quality_report"] = quality_report

            self.setup_factor_type_aware_imputer(imputer_config)
            workflow_results["steps_completed"].append("factor_type_aware_imputer_setup")

            self.run_factor_type_aware_imputation()
            workflow_results["steps_completed"].append("factor_type_aware_imputation_completed")

            self.save_results()
            workflow_results["steps_completed"].append("results_saved")

            self.generate_visualization_report()
            workflow_results["steps_completed"].append("visualization_generated")

            self.generate_factor_type_report()
            workflow_results["steps_completed"].append("factor_type_report_generated")

            self.generate_performance_report()
            workflow_results["steps_completed"].append("performance_report_generated")

            workflow_results["success"] = True
            workflow_results["performance_metrics"] = self.performance_metrics
            workflow_results["factor_type_analysis"] = self.factor_analysis

        except Exception as e:
            workflow_results["errors"].append(str(e))

        return workflow_results

    def generate_factor_type_report(self) -> None:
        if not self.factor_analysis:
            return
        report_content = self._generate_factor_type_report_content()
        report_file = self.output_dir / f"factor_type_analysis_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

    def _generate_factor_type_report_content(self) -> str:
        content = []
        content.append("# 因子类型感知插补分析报告")
        content.append(f"\n生成时间: {pd.Timestamp.now()}")
        content.append(f"\n因子数据: {self.factor_path}")
        content.append("\n---\n")
        content.append("## 因子类型分析")
        content.append(f"\n**检测到的因子类型**: {self.factor_analysis.get('factor_type', '未知')}")
        content.append(f"\n**缺失模式**: {self.factor_analysis.get('missing_pattern', '未知')}")
        content.append(f"\n**缺失率**: {self.factor_analysis.get('missing_rate', 0):.4f}")
        content.append(f"\n**插补策略**: {self.factor_analysis.get('imputation_strategy', '未知')}")

        characteristics = self.factor_analysis.get("factor_characteristics", {})
        if characteristics:
            content.append("\n### 因子特征")
            for key, value in characteristics.items():
                content.append(f"- **{key}**: {value}")

        content.append("\n---\n")
        content.append("## 插补方法对比")
        content.append("\n| 插补方法 | 截面缺失 | 时序缺失 | 块状缺失 | 缺失率 | 因子类型 | 前瞻风险 | 推荐度 |")
        content.append("|---------|---------|---------|---------|--------|----------|----------|--------|")

        methods_table = [
            ("截面分组中位数", "✅✅✅", "❌", "❌", "<20%", "基本面/估值/质量", "极低", "⭐⭐⭐⭐⭐"),
            ("ffill前向填充", "❌", "✅✅✅", "✅✅", "<50%", "财报/宏观/慢变因子", "极低", "⭐⭐⭐⭐⭐"),
            ("滚动窗口时序插补", "❌", "✅✅✅", "✅", "<30%", "量价/波动/动量", "低", "⭐⭐⭐⭐"),
            ("KNN/树模型滚动插补", "✅✅✅", "✅✅", "❌", "20~50%", "高维风格因子", "中（可控）", "⭐⭐⭐⭐"),
            ("EM/MCMC多重插补", "✅✅", "✅✅", "✅✅", "30~60%", "学术/协方差去噪", "低", "⭐⭐⭐"),
            ("MNAR哑变量标记", "✅✅✅", "✅", "✅", "任意", "亏损/停牌/特殊股", "无", "⭐⭐⭐⭐⭐"),
        ]

        for method, cross_section, time_series, block, missing_rate, factor_types, risk, rating in methods_table:
            row = (
                f"| {method} | {cross_section} | {time_series} | {block} "
                f"| {missing_rate} | {factor_types} | {risk} | {rating} |"
            )
            content.append(row)

        if self.imputation_report:
            compliance = self.imputation_report.get("compliance_result", {})
            content.append("\n---\n")
            content.append("## 合规性分析")
            content.append(f"\n**前瞻偏差合规性**: {'✅ 通过' if compliance.get('is_compliant', False) else '❌ 失败'}")
            content.append(f"\n**合规评分**: {compliance.get('compliance_score', 0):.4f}")

        return "\n".join(content)

    def generate_performance_report(self) -> None:
        if not self.performance_metrics:
            return
        report_content = self._generate_performance_report_content()
        report_file = self.output_dir / f"performance_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

    def _generate_performance_report_content(self) -> str:
        content = []
        content.append("# 因子类型感知插补性能分析报告")
        content.append(f"\n生成时间: {pd.Timestamp.now()}")
        content.append(f"\n因子数据: {self.factor_path}")
        content.append("\n---\n")
        content.append("## 性能概览")
        content.append(f"\n**执行时间**: {self.performance_metrics['execution_time']:.2f} 秒")
        content.append(f"\n**内存使用**: {self.performance_metrics['memory_usage']:.1f} MB")
        content.append(f"\n**数据规模**: {self.performance_metrics['data_shape']}")
        content.append(f"\n**缺失率**: {self.performance_metrics['missing_rate']:.4f}")
        content.append("\n---\n")
        content.append("## 优化配置")
        content.append(f"\n**并行计算**: {'启用' if self.performance_metrics['parallel_enabled'] else '禁用'}")
        content.append(f"\n**缓存机制**: {'启用' if self.performance_metrics['caching_enabled'] else '禁用'}")
        content.append(f"\n**工作线程**: {self.performance_metrics['n_workers']}")
        return "\n".join(content)
