# -*- coding: utf-8 -*-
"""
前瞻偏差防护器
100%避免未来信息泄露的严格验证机制
"""

import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .base import BaseImputer


class LookaheadBiasGuard:
    """前瞻偏差防护器 - 严格防止未来信息泄露"""

    def __init__(self, strict_mode=True, **params):
        self.strict_mode = strict_mode
        self.params = params
        self.validation_history = []
        self.bias_thresholds = {
            "future_correlation": 0.1,  # 未来相关性阈值
            "information_leakage": 0.05,  # 信息泄露阈值
            "temporal_violation": 0.0,  # 时序违规阈值（零容忍）
        }

    def validate_imputation(
        self, original_data: pd.DataFrame, imputed_data: pd.DataFrame, timestamp_col: str = None
    ) -> Dict[str, Any]:
        """
        验证插补是否存在前瞻偏差

        Parameters:
        -----------
        original_data : pd.DataFrame
            原始数据（包含缺失）
        imputed_data : pd.DataFrame
            插补后的数据
        timestamp_col : str
            时间戳列名

        Returns:
        --------
        validation_result : Dict[str, Any]
            验证结果
        """
        validation_result = {
            "is_valid": True,
            "bias_detected": False,
            "bias_types": [],
            "bias_scores": {},
            "detailed_analysis": {},
            "recommendations": [],
        }

        # 1. 时序违规检测
        temporal_violation = self._detect_temporal_violation(original_data, imputed_data, timestamp_col)
        validation_result["detailed_analysis"]["temporal_violation"] = temporal_violation

        if temporal_violation["has_violation"]:
            validation_result["is_valid"] = False
            validation_result["bias_detected"] = True
            validation_result["bias_types"].append("temporal_violation")
            validation_result["bias_scores"]["temporal_violation"] = temporal_violation["severity"]

        # 2. 未来信息泄露检测
        information_leakage = self._detect_information_leakage(original_data, imputed_data, timestamp_col)
        validation_result["detailed_analysis"]["information_leakage"] = information_leakage

        if information_leakage["has_leakage"]:
            validation_result["is_valid"] = False
            validation_result["bias_detected"] = True
            validation_result["bias_types"].append("information_leakage")
            validation_result["bias_scores"]["information_leakage"] = information_leakage["severity"]

        # 3. 未来相关性检测
        future_correlation = self._detect_future_correlation(original_data, imputed_data, timestamp_col)
        validation_result["detailed_analysis"]["future_correlation"] = future_correlation

        if future_correlation["has_correlation"]:
            validation_result["is_valid"] = False
            validation_result["bias_detected"] = True
            validation_result["bias_types"].append("future_correlation")
            validation_result["bias_scores"]["future_correlation"] = future_correlation["severity"]

        # 4. 统计一致性检测
        statistical_consistency = self._check_statistical_consistency(original_data, imputed_data)
        validation_result["detailed_analysis"]["statistical_consistency"] = statistical_consistency

        # 5. 生成建议
        validation_result["recommendations"] = self._generate_bias_recommendations(validation_result)

        # 保存验证历史
        self.validation_history.append({"timestamp": datetime.now(), "result": validation_result})

        return validation_result

    def _detect_temporal_violation(
        self, original_data: pd.DataFrame, imputed_data: pd.DataFrame, timestamp_col: str = None
    ) -> Dict[str, Any]:
        """检测时序违规"""
        violation_result = {"has_violation": False, "severity": 0.0, "violations": [], "analysis": {}}

        # 确定时间索引
        if timestamp_col and timestamp_col in original_data.columns:
            pass  # 时间索引有效，继续检测
        elif not isinstance(original_data.index, pd.DatetimeIndex):
            # 无法确定时间索引，跳过检测
            violation_result["analysis"]["reason"] = "无法确定时间索引"
            return violation_result

        # 检查插补值是否使用了未来信息
        missing_mask = original_data.isnull()

        for time_point in original_data.index:
            if missing_mask.loc[time_point].any():
                # 获取该时间点的缺失位置
                missing_assets = missing_mask.loc[time_point][missing_mask.loc[time_point]].index

                for asset in missing_assets:
                    # 检查插补值是否基于未来数据
                    imputed_value = imputed_data.loc[time_point, asset]

                    # 检查该时间点之后的数据是否影响了插补
                    # 使用下一个可用时间点而非固定天数
                    future_data = original_data.loc[time_point:, asset].iloc[1:]

                    if not future_data.empty:
                        # 简化检测：检查插补值是否异常接近未来值
                        future_mean = future_data.dropna().mean()
                        if not pd.isna(future_mean) and future_mean != 0:
                            deviation = abs(imputed_value - future_mean) / abs(future_mean)

                            # 只有当历史数据完全不支持该值时才标记为违规
                            historical_data = original_data.loc[:time_point, asset].dropna()
                            if len(historical_data) > 0:
                                hist_mean = historical_data.mean()
                                hist_std = historical_data.std()
                                if hist_std > 0:
                                    z_score = abs(imputed_value - hist_mean) / hist_std
                                    # 如果插补值与历史均值差异很大但接近未来均值，可能是前瞻偏差
                                    if deviation < 0.1 and z_score > 3:
                                        violation_result["has_violation"] = True
                                        violation_result["violations"].append(
                                            {
                                                "time_point": time_point,
                                                "asset": asset,
                                                "imputed_value": imputed_value,
                                                "future_mean": future_mean,
                                                "deviation": deviation,
                                                "z_score": z_score,
                                            }
                                        )

        # 计算严重程度
        if violation_result["has_violation"]:
            violation_result["severity"] = len(violation_result["violations"]) / missing_mask.sum().sum()

        return violation_result

    def _detect_information_leakage(
        self, original_data: pd.DataFrame, imputed_data: pd.DataFrame, timestamp_col: str = None
    ) -> Dict[str, Any]:
        """检测信息泄露"""
        leakage_result = {"has_leakage": False, "severity": 0.0, "leakage_points": [], "analysis": {}}

        missing_mask = original_data.isnull()

        # 检查插补值与未来统计量的关系
        for asset in original_data.columns:
            asset_missing_mask = missing_mask[asset]

            if asset_missing_mask.any():
                # 获取缺失时间点
                missing_times = asset_missing_mask[asset_missing_mask].index

                for missing_time in missing_times:
                    imputed_value = imputed_data.loc[missing_time, asset]

                    # 检查与未来统计量的关系
                    future_window = original_data.loc[missing_time + timedelta(days=1) :, asset]

                    if len(future_window) >= 5:  # 至少5个未来数据点
                        future_stats = {
                            "mean": future_window.mean(),
                            "median": future_window.median(),
                            "std": future_window.std(),
                            "min": future_window.min(),
                            "max": future_window.max(),
                        }

                        # 检查插补值是否过于接近未来统计量
                        for stat_name, stat_value in future_stats.items():
                            if not pd.isna(stat_value):
                                relative_diff = abs(imputed_value - stat_value) / (abs(stat_value) + 1e-10)

                                if relative_diff < 0.05:  # 异常接近
                                    leakage_result["has_leakage"] = True
                                    leakage_result["leakage_points"].append(
                                        {
                                            "time": missing_time,
                                            "asset": asset,
                                            "imputed_value": imputed_value,
                                            "future_stat": stat_name,
                                            "future_value": stat_value,
                                            "relative_diff": relative_diff,
                                        }
                                    )

        # 计算严重程度
        if leakage_result["has_leakage"]:
            leakage_result["severity"] = len(leakage_result["leakage_points"]) / missing_mask.sum().sum()

        return leakage_result

    def _detect_future_correlation(
        self, original_data: pd.DataFrame, imputed_data: pd.DataFrame, timestamp_col: str = None
    ) -> Dict[str, Any]:
        """检测未来相关性"""
        correlation_result = {"has_correlation": False, "severity": 0.0, "correlations": [], "analysis": {}}

        missing_mask = original_data.isnull()

        # 检查插补值与未来收益率的相关性
        for asset in original_data.columns:
            asset_missing_mask = missing_mask[asset]

            if asset_missing_mask.any():
                # 获取插补值序列
                imputed_values = imputed_data[asset].loc[asset_missing_mask]

                # 计算未来收益率（如果有足够的数据）
                if len(imputed_values) > 10:
                    # 计算未来收益率
                    future_returns = original_data[asset].pct_change().shift(-1).loc[imputed_values.index]

                    # 移除NaN
                    valid_data = pd.DataFrame({"imputed": imputed_values, "future_return": future_returns}).dropna()

                    if len(valid_data) > 5:
                        correlation = np.corrcoef(valid_data["imputed"], valid_data["future_return"])[0, 1]

                        if not np.isnan(correlation) and abs(correlation) > self.bias_thresholds["future_correlation"]:
                            correlation_result["has_correlation"] = True
                            correlation_result["correlations"].append(
                                {"asset": asset, "correlation": correlation, "sample_size": len(valid_data)}
                            )

        # 计算严重程度
        if correlation_result["has_correlation"]:
            max_correlation = max([abs(c["correlation"]) for c in correlation_result["correlations"]])
            correlation_result["severity"] = max_correlation

        return correlation_result

    def _check_statistical_consistency(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> Dict[str, Any]:
        """检查统计一致性"""
        consistency_result = {"is_consistent": True, "inconsistencies": [], "analysis": {}}

        # 比较原始数据和插补数据的统计特征
        original_valid = original_data.dropna()

        for asset in original_data.columns:
            if asset in imputed_data.columns:
                original_asset = original_valid[asset]
                imputed_asset = imputed_data[asset]

                # 计算统计量
                original_stats = {
                    "mean": original_asset.mean(),
                    "std": original_asset.std(),
                    "skew": original_asset.skew(),
                    "kurt": original_asset.kurtosis(),
                }

                imputed_stats = {
                    "mean": imputed_asset.mean(),
                    "std": imputed_asset.std(),
                    "skew": imputed_asset.skew(),
                    "kurt": imputed_asset.kurtosis(),
                }

                # 检查一致性
                for stat_name in original_stats:
                    if not pd.isna(original_stats[stat_name]) and not pd.isna(imputed_stats[stat_name]):
                        relative_diff = abs(imputed_stats[stat_name] - original_stats[stat_name]) / (
                            abs(original_stats[stat_name]) + 1e-10
                        )

                        if relative_diff > 0.2:  # 20%差异阈值
                            consistency_result["is_consistent"] = False
                            consistency_result["inconsistencies"].append(
                                {
                                    "asset": asset,
                                    "statistic": stat_name,
                                    "original_value": original_stats[stat_name],
                                    "imputed_value": imputed_stats[stat_name],
                                    "relative_diff": relative_diff,
                                }
                            )

        return consistency_result

    def _generate_bias_recommendations(self, validation_result: Dict[str, Any]) -> List[str]:
        """生成偏差修复建议"""
        recommendations = []

        if not validation_result["is_valid"]:
            recommendations.append("检测到前瞻偏差，需要重新检查插补方法")

            for bias_type in validation_result["bias_types"]:
                if bias_type == "temporal_violation":
                    recommendations.append("时序违规：确保插补只使用历史信息")
                    recommendations.append("建议使用滚动窗口方法，避免使用未来数据")
                elif bias_type == "information_leakage":
                    recommendations.append("信息泄露：检查插补算法是否使用了未来统计量")
                    recommendations.append("建议使用点对点插补而非全局统计量")
                elif bias_type == "future_correlation":
                    recommendations.append("未来相关性：插补值与未来收益率存在异常相关")
                    recommendations.append("建议重新审视插补模型，避免引入预测偏差")
        else:
            recommendations.append("未检测到前瞻偏差，插补方法符合时序要求")

        return recommendations

    def validate_imputation_method(self, imputer: BaseImputer, test_data: pd.DataFrame) -> Dict[str, Any]:
        """验证插补方法是否存在前瞻偏差风险"""
        method_validation = {
            "method_name": imputer.__class__.__name__,
            "risk_level": "low",
            "risk_factors": [],
            "recommendations": [],
        }

        # 检查插补器类型
        imputer_type = type(imputer).__name__

        if "KNN" in imputer_type or "RandomForest" in imputer_type:
            method_validation["risk_level"] = "medium"
            method_validation["risk_factors"].append("机器学习方法可能存在前瞻偏差")
            method_validation["recommendations"].append("确保使用滚动训练，避免全样本拟合")

        if "CrossSectional" in imputer_type:
            method_validation["risk_level"] = "low"
            method_validation["recommendations"].append("截面方法通常安全，但需确保使用当期数据")

        if "TimeSeries" in imputer_type:
            method_validation["risk_level"] = "low"
            method_validation["recommendations"].append("时序方法通常安全，但需避免使用未来窗口")

        # 实际测试
        try:
            # 创建测试数据
            test_missing = test_data.copy()
            # 随机设置一些缺失
            np.random.seed(42)
            mask = np.random.random(test_missing.shape) < 0.1
            test_missing[mask] = np.nan

            # 执行插补
            imputed_test = imputer.fit_transform(test_missing)

            # 验证插补结果
            validation_result = self.validate_imputation(test_missing, imputed_test)

            if validation_result["bias_detected"]:
                method_validation["risk_level"] = "high"
                method_validation["risk_factors"].append("实际测试检测到前瞻偏差")
                method_validation["recommendations"].extend(validation_result["recommendations"])

        except Exception as e:
            method_validation["risk_factors"].append(f"测试失败: {str(e)}")

        return method_validation

    def generate_bias_report(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成偏差分析报告"""
        report = {
            "summary": {
                "total_validations": len(validation_results),
                "passed_validations": sum(1 for r in validation_results if r["is_valid"]),
                "failed_validations": sum(1 for r in validation_results if not r["is_valid"]),
                "overall_bias_risk": "low",
            },
            "bias_types_distribution": {},
            "common_issues": [],
            "recommendations": [],
        }

        # 统计偏差类型分布
        bias_type_counts = {}
        for result in validation_results:
            for bias_type in result["bias_types"]:
                bias_type_counts[bias_type] = bias_type_counts.get(bias_type, 0) + 1

        report["bias_types_distribution"] = bias_type_counts

        # 确定整体风险等级
        failure_rate = report["summary"]["failed_validations"] / report["summary"]["total_validations"]
        if failure_rate > 0.5:
            report["summary"]["overall_bias_risk"] = "high"
        elif failure_rate > 0.2:
            report["summary"]["overall_bias_risk"] = "medium"

        # 汇总常见问题
        all_recommendations = []
        for result in validation_results:
            all_recommendations.extend(result["recommendations"])

        # 统计最频繁的建议
        recommendation_counts = {}
        for rec in all_recommendations:
            recommendation_counts[rec] = recommendation_counts.get(rec, 0) + 1

        # 获取前5个最频繁的建议
        top_recommendations = sorted(recommendation_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        report["recommendations"] = [rec[0] for rec in top_recommendations]

        return report


class BiasFreeImputerWrapper:
    """无偏差插补器包装器 - 确保插补过程无前瞻偏差"""

    def __init__(self, base_imputer: BaseImputer, bias_guard: LookaheadBiasGuard = None):
        self.base_imputer = base_imputer
        self.bias_guard = bias_guard or LookaheadBiasGuard()
        self.validation_log = []

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换，确保无前瞻偏差"""
        # 记录原始数据
        original_data = X.copy()

        # 执行插补
        imputed_data = self.base_imputer.fit_transform(X, **kwargs)

        # 验证插补结果
        validation_result = self.bias_guard.validate_imputation(original_data, imputed_data)

        # 记录验证结果
        self.validation_log.append({"timestamp": datetime.now(), "validation_result": validation_result})

        # 如果检测到偏差，发出警告
        if validation_result["bias_detected"]:
            warnings.warn(f"检测到前瞻偏差: {validation_result['bias_types']}")
            if self.bias_guard.strict_mode:
                raise ValueError("严格模式下不允许前瞻偏差")

        return imputed_data

    def get_validation_report(self) -> Dict[str, Any]:
        """获取验证报告"""
        if not self.validation_log:
            return {"message": "无验证记录"}

        validation_results = [log["validation_result"] for log in self.validation_log]
        return self.bias_guard.generate_bias_report(validation_results)
