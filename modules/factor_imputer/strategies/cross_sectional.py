# -*- coding: utf-8 -*-
"""
截面插补策略
基于截面统计量和分组信息的插补方法
"""

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats

from ..core.base import BaseImputer


def _calculate_mad(series):
    """计算 MAD (Median Absolute Deviation)"""
    if isinstance(series, pd.DataFrame):
        return series.apply(lambda x: (x - x.median()).abs().median())
    else:
        median = series.median()
        return (series - median).abs().median()


class CrossSectionalImputer(BaseImputer):
    """截面插补器 - 专门处理截面缺失模式"""

    def __init__(self, method="group_median", group_by="industry", min_group_size=5, robust_method=True, **params):
        super().__init__(**params)
        self.method = method
        self.group_by = group_by
        self.min_group_size = min_group_size
        self.robust_method = robust_method
        self.group_stats = {}
        self.global_stats = {}
        self.group_mappings = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "CrossSectionalImputer":
        """拟合截面插补参数"""
        # 计算全局统计量
        self.global_stats = self._calculate_global_stats(X)

        # 计算分组统计量
        if self.group_by:
            self.group_stats = self._calculate_group_stats(X)
            self.group_mappings = self._create_group_mappings(X)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用截面插补"""
        X_imputed = X.copy()

        # 对每个时间点分别处理
        for time_point in X.index:
            cross_section = X.loc[time_point]
            missing_mask = cross_section.isnull()

            if missing_mask.any():
                # 获取该时间点的插补值
                imputed_values = self._impute_cross_section(cross_section, missing_mask)

                # 更新数据
                X_imputed.loc[time_point, missing_mask] = imputed_values

        return X_imputed

    def _calculate_global_stats(self, X: pd.DataFrame) -> Dict[str, Any]:
        """计算全局统计量"""
        stats_dict = {}

        # 基础统计量
        stats_dict["mean"] = X.mean()
        stats_dict["median"] = X.median()
        stats_dict["std"] = X.std()
        stats_dict["mad"] = _calculate_mad(X)

        # 鲁棒统计量
        if self.robust_method:
            stats_dict["trimmed_mean"] = self._calculate_trimmed_mean(X)
            stats_dict["winsorized_mean"] = self._calculate_winsorized_mean(X)
            stats_dict["huber_mean"] = self._calculate_huber_mean(X)

        return stats_dict

    def _calculate_group_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算分组统计量"""
        group_stats = {}

        # 根据分组方式计算统计量
        if self.group_by == "industry":
            group_stats = self._calculate_industry_stats(X)
        elif self.group_by == "market_cap":
            group_stats = self._calculate_market_cap_stats(X)
        elif self.group_by == "momentum":
            group_stats = self._calculate_momentum_stats(X)
        elif self.group_by == "size":
            group_stats = self._calculate_size_stats(X)
        else:
            # 自定义分组
            group_stats = self._calculate_custom_stats(X)

        return group_stats

    def _create_group_mappings(self, X: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
        """创建资产分组映射"""
        mappings = {}

        if self.group_by == "industry":
            mappings = self._create_industry_mappings(X)
        elif self.group_by == "market_cap":
            mappings = self._create_market_cap_mappings(X)
        elif self.group_by == "momentum":
            mappings = self._create_momentum_mappings(X)
        elif self.group_by == "size":
            mappings = self._create_size_mappings(X)

        return mappings

    def _impute_cross_section(self, cross_section: pd.Series, missing_mask: pd.Series) -> pd.Series:
        """对单个截面进行插补"""
        missing_assets = missing_mask[missing_mask].index
        imputed_values = pd.Series(index=missing_assets)

        for asset in missing_assets:
            # 尝试分组插补
            if self.group_by and asset in self.group_mappings:
                group_name = self._get_asset_group(asset)

                if group_name and group_name in self.group_stats:
                    group_stat = self.group_stats[group_name]

                    # 检查组内是否有足够的样本
                    valid_assets = [
                        a
                        for a in cross_section.index
                        if not pd.isna(cross_section[a]) and a in self.group_mappings.get(group_name, {})
                    ]

                    if len(valid_assets) >= self.min_group_size:
                        imputed_values[asset] = self._get_group_imputed_value(asset, group_stat, cross_section)
                        continue

            # 回退到全局插补
            imputed_values[asset] = self._get_global_imputed_value(asset, cross_section)

        return imputed_values

    def _get_group_imputed_value(self, asset: str, group_stat: Dict[str, pd.Series], cross_section: pd.Series) -> float:
        """获取分组插补值"""
        if self.method == "group_median":
            return group_stat["median"].get(asset, self.global_stats["median"].get(asset, 0))
        elif self.method == "group_mean":
            return group_stat["mean"].get(asset, self.global_stats["mean"].get(asset, 0))
        elif self.method == "group_winsorized":
            return group_stat["winsorized_mean"].get(asset, self.global_stats["winsorized_mean"].get(asset, 0))
        elif self.method == "group_huber":
            return group_stat["huber_mean"].get(asset, self.global_stats["huber_mean"].get(asset, 0))
        else:
            return group_stat["median"].get(asset, self.global_stats["median"].get(asset, 0))

    def _get_global_imputed_value(self, asset: str, cross_section: pd.Series) -> float:
        """获取全局插补值"""
        if self.method == "global_median":
            return self.global_stats["median"].get(asset, 0)
        elif self.method == "global_mean":
            return self.global_stats["mean"].get(asset, 0)
        elif self.method == "global_winsorized":
            return self.global_stats["winsorized_mean"].get(asset, 0)
        elif self.method == "global_huber":
            return self.global_stats["huber_mean"].get(asset, 0)
        else:
            return self.global_stats["median"].get(asset, 0)

    def _calculate_trimmed_mean(self, X: pd.DataFrame, trim_percent=0.1) -> pd.Series:
        """计算缩尾均值"""
        trimmed_means = {}

        for col in X.columns:
            series = X[col].dropna()
            if len(series) > 0:
                lower = series.quantile(trim_percent)
                upper = series.quantile(1 - trim_percent)
                trimmed_series = series[(series >= lower) & (series <= upper)]
                trimmed_means[col] = trimmed_series.mean()
            else:
                trimmed_means[col] = 0

        return pd.Series(trimmed_means)

    def _calculate_winsorized_mean(self, X: pd.DataFrame, limits=(0.05, 0.05)) -> pd.Series:
        """计算Winsorized均值"""
        winsorized_means = {}

        for col in X.columns:
            series = X[col].dropna()
            if len(series) > 0:
                lower = series.quantile(limits[0])
                upper = series.quantile(1 - limits[1])
                winsorized_series = series.clip(lower=lower, upper=upper)
                winsorized_means[col] = winsorized_series.mean()
            else:
                winsorized_means[col] = 0

        return pd.Series(winsorized_means)

    def _calculate_huber_mean(self, X: pd.DataFrame, k=1.5) -> pd.Series:
        """计算Huber均值"""
        huber_means = {}

        for col in X.columns:
            series = X[col].dropna()
            if len(series) > 0:
                median = series.median()
                mad = (series - series.median()).abs().median()

                if mad == 0:
                    huber_means[col] = median
                else:
                    # Huber权重
                    weights = np.where(np.abs(series - median) <= k * mad, 1.0, k * mad / np.abs(series - median))

                    weight_sum = np.sum(weights)
                    if weight_sum == 0:
                        huber_mean = median
                    else:
                        huber_mean = np.sum(weights * series) / weight_sum
                    huber_means[col] = huber_mean
            else:
                huber_means[col] = 0

        return pd.Series(huber_means)

    def _calculate_industry_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算行业分组统计量"""
        # 这里需要行业分类信息，简化实现
        # 实际应用中需要传入行业映射

        # 假设有一些行业信息
        industries = ["tech", "finance", "consumer", "industrial", "healthcare"]
        industry_stats = {}

        for industry in industries:
            # 随机分配一些资产到该行业（简化）
            assets_in_industry = np.random.choice(X.columns, size=len(X.columns) // 5, replace=False)

            if len(assets_in_industry) > 0:
                industry_data = X[assets_in_industry]

                industry_stats[industry] = {
                    "mean": industry_data.mean(),
                    "median": industry_data.median(),
                    "std": industry_data.std(),
                    "mad": _calculate_mad(industry_data),
                }

                if self.robust_method:
                    industry_stats[industry]["trimmed_mean"] = self._calculate_trimmed_mean(industry_data)
                    industry_stats[industry]["winsorized_mean"] = self._calculate_winsorized_mean(industry_data)
                    industry_stats[industry]["huber_mean"] = self._calculate_huber_mean(industry_data)

        return industry_stats

    def _calculate_market_cap_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算市值分组统计量"""
        # 简化实现：按资产数量比例分组
        assets = X.columns
        n_assets = len(assets)

        large_cap_assets = assets[: int(n_assets * 0.3)]
        mid_cap_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        small_cap_assets = assets[int(n_assets * 0.7) :]

        market_cap_stats: Dict[str, Dict[str, pd.Series]] = {}
        for group_name, group_assets in [
            ("large_cap", large_cap_assets),
            ("mid_cap", mid_cap_assets),
            ("small_cap", small_cap_assets),
        ]:
            if len(group_assets) > 0:
                group_data = X[group_assets]

                market_cap_stats[group_name] = {
                    "mean": group_data.mean(),
                    "median": group_data.median(),
                    "std": group_data.std(),
                    "mad": _calculate_mad(group_data),
                }

                if self.robust_method:
                    market_cap_stats[group_name]["trimmed_mean"] = self._calculate_trimmed_mean(group_data)
                    market_cap_stats[group_name]["winsorized_mean"] = self._calculate_winsorized_mean(group_data)
                    market_cap_stats[group_name]["huber_mean"] = self._calculate_huber_mean(group_data)

        return market_cap_stats

    def _calculate_momentum_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算动量分组统计量"""
        # 基于过去收益率分组
        momentum_stats = {}

        # 简化实现：按资产名称排序分组
        assets = X.columns
        n_assets = len(assets)

        high_momentum_assets = assets[: int(n_assets * 0.3)]
        medium_momentum_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        low_momentum_assets = assets[int(n_assets * 0.7) :]

        for group_name, group_assets in [
            ("high_momentum", high_momentum_assets),
            ("medium_momentum", medium_momentum_assets),
            ("low_momentum", low_momentum_assets),
        ]:
            if len(group_assets) > 0:
                group_data = X[group_assets]

                momentum_stats[group_name] = {
                    "mean": group_data.mean(),
                    "median": group_data.median(),
                    "std": group_data.std(),
                    "mad": _calculate_mad(group_data),
                }

                if self.robust_method:
                    momentum_stats[group_name]["trimmed_mean"] = self._calculate_trimmed_mean(group_data)
                    momentum_stats[group_name]["winsorized_mean"] = self._calculate_winsorized_mean(group_data)
                    momentum_stats[group_name]["huber_mean"] = self._calculate_huber_mean(group_data)

        return momentum_stats

    def _calculate_size_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算规模分组统计量"""
        # 基于公司规模分组
        size_stats = {}

        # 简化实现：按资产索引分组
        assets = X.columns
        n_assets = len(assets)

        large_size_assets = assets[: int(n_assets * 0.3)]
        medium_size_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        small_size_assets = assets[int(n_assets * 0.7) :]

        for group_name, group_assets in [
            ("large_size", large_size_assets),
            ("medium_size", medium_size_assets),
            ("small_size", small_size_assets),
        ]:
            if len(group_assets) > 0:
                group_data = X[group_assets]

                size_stats[group_name] = {
                    "mean": group_data.mean(),
                    "median": group_data.median(),
                    "std": group_data.std(),
                    "mad": _calculate_mad(group_data),
                }

                if self.robust_method:
                    size_stats[group_name]["trimmed_mean"] = self._calculate_trimmed_mean(group_data)
                    size_stats[group_name]["winsorized_mean"] = self._calculate_winsorized_mean(group_data)
                    size_stats[group_name]["huber_mean"] = self._calculate_huber_mean(group_data)

        return size_stats

    def _calculate_custom_stats(self, X: pd.DataFrame) -> Dict[str, Dict[str, pd.Series]]:
        """计算自定义分组统计量"""
        # 可以根据用户自定义规则分组
        custom_stats = {}

        # 简化实现：按资产名称首字母分组
        assets = X.columns

        for asset in assets:
            first_letter = asset[0].upper() if asset else "OTHER"

            if first_letter not in custom_stats:
                custom_stats[first_letter] = []
            custom_stats[first_letter].append(asset)

        # 计算每个组的统计量
        for group_name, group_assets in custom_stats.items():
            if len(group_assets) > 0:
                group_data = X[group_assets]

                custom_stats[group_name] = {
                    "mean": group_data.mean(),
                    "median": group_data.median(),
                    "std": group_data.std(),
                    "mad": _calculate_mad(group_data),
                }

                if self.robust_method:
                    custom_stats[group_name]["trimmed_mean"] = self._calculate_trimmed_mean(group_data)
                    custom_stats[group_name]["winsorized_mean"] = self._calculate_winsorized_mean(group_data)
                    custom_stats[group_name]["huber_mean"] = self._calculate_huber_mean(group_data)

        return custom_stats

    def _create_industry_mappings(self, X: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
        """创建行业映射"""
        mappings = {}

        # 简化实现：随机分配行业
        industries = ["tech", "finance", "consumer", "industrial", "healthcare"]
        assets = X.columns

        for asset in assets:
            industry = np.random.choice(industries)
            if industry not in mappings:
                mappings[industry] = []
            mappings[industry].append(asset)

        return mappings

    def _create_market_cap_mappings(self, X: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
        """创建市值映射"""
        mappings = {}

        assets = X.columns
        n_assets = len(assets)

        large_cap_assets = assets[: int(n_assets * 0.3)]
        mid_cap_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        small_cap_assets = assets[int(n_assets * 0.7) :]

        mappings["large_cap"] = list(large_cap_assets)
        mappings["mid_cap"] = list(mid_cap_assets)
        mappings["small_cap"] = list(small_cap_assets)

        return mappings

    def _create_momentum_mappings(self, X: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
        """创建动量映射"""
        mappings = {}

        assets = X.columns
        n_assets = len(assets)

        high_momentum_assets = assets[: int(n_assets * 0.3)]
        medium_momentum_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        low_momentum_assets = assets[int(n_assets * 0.7) :]

        mappings["high_momentum"] = list(high_momentum_assets)
        mappings["medium_momentum"] = list(medium_momentum_assets)
        mappings["low_momentum"] = list(low_momentum_assets)

        return mappings

    def _create_size_mappings(self, X: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
        """创建规模映射"""
        mappings = {}

        assets = X.columns
        n_assets = len(assets)

        large_size_assets = assets[: int(n_assets * 0.3)]
        medium_size_assets = assets[int(n_assets * 0.3) : int(n_assets * 0.7)]
        small_size_assets = assets[int(n_assets * 0.7) :]

        mappings["large_size"] = list(large_size_assets)
        mappings["medium_size"] = list(medium_size_assets)
        mappings["small_size"] = list(small_size_assets)

        return mappings

    def _get_asset_group(self, asset: str) -> Optional[str]:
        """获取资产所属分组"""
        for group_name, group_assets in self.group_mappings.items():
            if asset in group_assets:
                return group_name
        return None


class AdaptiveCrossSectionalImputer(CrossSectionalImputer):
    """自适应截面插补器 - 根据数据特征自动选择最优方法"""

    def __init__(self, auto_select=True, **params):
        super().__init__(**params)
        self.auto_select = auto_select
        self.best_method = None
        self.method_scores = {}

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "AdaptiveCrossSectionalImputer":
        """拟合并选择最优方法"""
        if self.auto_select:
            self.best_method = self._select_best_method(X)
            self.method = self.best_method

        super().fit(X, missing_info)
        return self

    def _select_best_method(self, X: pd.DataFrame) -> str:
        """选择最优插补方法"""
        methods = ["group_median", "group_mean", "group_winsorized", "global_median"]
        scores = {}

        # 对每个方法进行评估
        for method in methods:
            score = self._evaluate_method(X, method)
            scores[method] = score

        self.method_scores = scores
        return max(scores, key=scores.get)

    def _evaluate_method(self, X: pd.DataFrame, method: str) -> float:
        """评估插补方法"""
        # 创建测试数据
        test_data = X.copy()

        # 随机设置一些缺失值
        np.random.seed(42)
        mask = np.random.random(test_data.shape) < 0.1
        test_data[mask] = np.nan

        # 使用该方法插补
        temp_imputer = CrossSectionalImputer(method=method, group_by=self.group_by)
        imputed_data = temp_imputer.fit_transform(test_data)

        # 计算插补质量
        original_values = X[mask]
        imputed_values = imputed_data[mask]

        if len(original_values) > 0:
            # 计算均方误差
            mse = np.mean((original_values - imputed_values) ** 2)

            # 计算相关性
            correlation = np.corrcoef(original_values, imputed_values)[0, 1]

            # 综合评分（相关性越高，MSE越低，评分越高）
            score = correlation - np.log(mse + 1e-10)

            return score if not np.isnan(score) else 0
        else:
            return 0
