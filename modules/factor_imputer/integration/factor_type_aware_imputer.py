# -*- coding: utf-8 -*-
"""
因子类型感知插补器
支持自动检测/人为指定因子类型、并行计算、缓存机制
"""

import hashlib
import multiprocessing as mp
import os
import pickle
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..core.integrated_data_loader import IntegratedDataLoader
from ..core.lookahead_free_integrated_imputer import LookaheadFreeIntegratedImputer


class FactorTypeAwareImputer(LookaheadFreeIntegratedImputer):
    """因子类型感知插补器（统一版）"""

    def __init__(
        self,
        auto_detect_factor_type=True,
        specified_factor_type=None,
        enable_parallel=True,
        enable_caching=True,
        cache_dir=None,
        n_workers=None,
        **params,
    ):
        super().__init__(**params)

        self.auto_detect_factor_type = auto_detect_factor_type
        self.specified_factor_type = specified_factor_type
        self.factor_type = None

        self.enable_parallel = enable_parallel
        self.enable_caching = enable_caching
        self.cache_dir = cache_dir or "cache"
        self.n_workers = n_workers or min(mp.cpu_count(), 4)

        self._feature_cache = {}
        self._imputation_cache = {}
        self._cache_lock = threading.Lock()

        if self.enable_caching:
            os.makedirs(self.cache_dir, exist_ok=True)

        self.imputation_methods = {
            "cross_sectional_median": self._cross_sectional_median_impute,
            "ffill": self._forward_fill_impute,
            "rolling_window": self._rolling_window_impute,
            "knn_rolling": self._knn_rolling_impute,
            "em_multiple": self._em_multiple_impute,
            "mnar_indicator": self._mnar_indicator_impute,
        }

        self.factor_characteristics = {
            "financial": {
                "optimal_methods": ["cross_sectional_median", "rolling_window", "mnar_indicator"],
                "max_missing_rate": 0.3,
                "lookahead_risk": "very_low",
                "preferred_grouping": "sw_industry",
                "robust_stats": True,
                "time_series_weight": 0.7,
                "cross_sectional_weight": 0.3,
            },
            "valuation": {
                "optimal_methods": ["cross_sectional_median", "rolling_window", "mnar_indicator"],
                "max_missing_rate": 0.3,
                "lookahead_risk": "very_low",
                "preferred_grouping": "sw_industry",
                "robust_stats": True,
                "time_series_weight": 0.6,
                "cross_sectional_weight": 0.4,
            },
            "growth": {
                "optimal_methods": ["cross_sectional_median", "knn_rolling", "mnar_indicator"],
                "max_missing_rate": 0.5,
                "lookahead_risk": "low",
                "preferred_grouping": "market_cap",
                "robust_stats": False,
                "time_series_weight": 0.4,
                "cross_sectional_weight": 0.6,
            },
            "technical": {
                "optimal_methods": ["ffill", "rolling_window", "mnar_indicator"],
                "max_missing_rate": 0.5,
                "lookahead_risk": "low",
                "preferred_grouping": "market_cap",
                "robust_stats": False,
                "time_series_weight": 0.8,
                "cross_sectional_weight": 0.2,
            },
            "quality": {
                "optimal_methods": ["cross_sectional_median", "rolling_window", "mnar_indicator"],
                "max_missing_rate": 0.3,
                "lookahead_risk": "very_low",
                "preferred_grouping": "sw_industry",
                "robust_stats": False,
                "time_series_weight": 0.7,
                "cross_sectional_weight": 0.3,
            },
            "risk": {
                "optimal_methods": ["cross_sectional_median", "knn_rolling", "mnar_indicator"],
                "max_missing_rate": 0.5,
                "lookahead_risk": "low",
                "preferred_grouping": "index_groups",
                "robust_stats": True,
                "time_series_weight": 0.5,
                "cross_sectional_weight": 0.5,
            },
            "macro": {
                "optimal_methods": ["ffill", "rolling_window", "em_multiple"],
                "max_missing_rate": 0.6,
                "lookahead_risk": "low",
                "preferred_grouping": "time_series",
                "robust_stats": False,
                "time_series_weight": 0.9,
                "cross_sectional_weight": 0.1,
            },
        }

    def fit(self, X: pd.DataFrame, missing_info: Dict[str, Any] = None) -> "FactorTypeAwareImputer":
        super().fit(X, missing_info)
        self._analyze_factor_characteristics(X)
        self._select_optimal_strategy()
        return self

    def _analyze_factor_characteristics(self, X: pd.DataFrame) -> None:
        if self.specified_factor_type:
            self.factor_type = self.specified_factor_type
        elif self.auto_detect_factor_type:
            self.factor_type = self._detect_factor_type_enhanced(X)
        else:
            self.factor_type = getattr(self, "factor_type", "financial")

        self.missing_pattern = self._analyze_missing_pattern_enhanced(X)
        self.missing_rate = X.isnull().sum().sum() / X.shape[0] / X.shape[1]

    def _detect_factor_type_enhanced(self, X: pd.DataFrame) -> str:
        data_hash = self._generate_data_hash(X)
        if self.enable_caching:
            cached_result = self._get_cached_result(data_hash, "factor_type")
            if cached_result:
                return cached_result

        features = self._compute_features_parallel(X)
        factor_type = self._classify_factor_type_enhanced(features)

        if self.enable_caching:
            self._cache_result(data_hash, "factor_type", factor_type)
        return factor_type

    def _generate_data_hash(self, data: pd.DataFrame) -> str:
        stats = {
            "shape": data.shape,
            "missing_rate": data.isnull().sum().sum() / data.size,
            "mean": data.mean().mean() if data.size > 0 else 0,
            "std": data.std().mean() if data.size > 0 else 0,
        }
        stats_str = str(sorted(stats.items()))
        return hashlib.md5(stats_str.encode()).hexdigest()

    def _compute_features_parallel(self, X: pd.DataFrame) -> Dict[str, float]:
        if not self.enable_parallel or X.shape[1] < 10:
            return self._compute_features_sequential(X)

        tasks = {
            "distribution_features": self._compute_distribution_features,
            "time_series_features": self._compute_time_series_features,
            "cross_section_features": self._compute_cross_section_features,
        }

        features = {}
        with ThreadPoolExecutor(max_workers=min(3, self.n_workers)) as executor:
            future_to_task = {executor.submit(task_func, X): task_name for task_name, task_func in tasks.items()}
            for future in future_to_task:
                try:
                    task_features = future.result()
                    features.update(task_features)
                except (RuntimeError, TimeoutError):
                    pass
        return features

    def _compute_features_sequential(self, X: pd.DataFrame) -> Dict[str, float]:
        features = {}
        features.update(self._compute_distribution_features(X))
        features.update(self._compute_time_series_features(X))
        features.update(self._compute_cross_section_features(X))
        return features

    def _compute_distribution_features(self, X: pd.DataFrame) -> Dict[str, float]:
        features = {}
        valid_data = X.dropna().values.flatten()
        if len(valid_data) > 0:
            s = pd.Series(valid_data)
            features["skewness"] = s.skew()
            features["kurtosis"] = s.kurtosis()
            features["std"] = s.std()
            features["mean"] = s.mean()
            q1, q3 = np.percentile(valid_data, [25, 75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = (valid_data < lower_bound) | (valid_data > upper_bound)
            features["outlier_ratio"] = np.mean(outliers)
            features["q25"] = q1
            features["q75"] = q3
            features["iqr"] = iqr
            features["cv"] = features["std"] / abs(features["mean"]) if features["mean"] != 0 else np.inf
        return features

    def _compute_time_series_features(self, X: pd.DataFrame) -> Dict[str, float]:
        features = {}
        if isinstance(X.index, pd.DatetimeIndex) and len(X) > 10:
            asset_tasks = []
            for asset in X.columns[: min(50, len(X.columns))]:
                asset_data = X[asset].dropna()
                if len(asset_data) > 5:
                    asset_tasks.append(asset)

            if self.enable_parallel and len(asset_tasks) > 5:
                with ThreadPoolExecutor(max_workers=min(self.n_workers, len(asset_tasks))) as executor:
                    autocorr_results = list(executor.map(self._compute_autocorr, asset_tasks))
            else:
                autocorr_results = [self._compute_autocorr(asset) for asset in asset_tasks]

            valid_autocorrs = [ac for ac in autocorr_results if ac is not None]
            if valid_autocorrs:
                features["time_series_persistence"] = np.mean(valid_autocorrs)
                features["time_series_persistence_std"] = np.std(valid_autocorrs)
        return features

    def _compute_autocorr(self, asset_data: pd.Series) -> Optional[float]:
        try:
            autocorr = [asset_data.autocorr(lag) for lag in range(1, min(6, len(asset_data) // 2))]
            valid_autocorr = [ac for ac in autocorr if not np.isnan(ac)]
            return np.mean(np.abs(valid_autocorr)) if valid_autocorr else None
        except (ValueError, TypeError):
            return None

    def _compute_cross_section_features(self, X: pd.DataFrame) -> Dict[str, float]:
        features = {}
        if len(X.columns) > 10:
            sample_size = min(20, len(X))
            sample_indices = np.linspace(0, len(X) - 1, sample_size, dtype=int)
            sample_times = X.index[sample_indices]

            cross_corrs = [self._compute_time_cross_corr(X, time_point) for time_point in sample_times]
            valid_corrs = [corr for corr in cross_corrs if corr is not None]
            if valid_corrs:
                features["cross_section_correlation"] = np.mean(valid_corrs)
                features["cross_section_correlation_std"] = np.std(valid_corrs)
        return features

    def _compute_time_cross_corr(self, X: pd.DataFrame, time_point: pd.Timestamp) -> Optional[float]:
        try:
            cross_section = X.loc[time_point].dropna()
            if len(cross_section) > 5:
                other_times = X.index.drop(time_point)
                if len(other_times) > 0:
                    sample_other_times = np.random.choice(other_times, size=min(5, len(other_times)), replace=False)
                    corrs = []
                    for other_time in sample_other_times:
                        other_section = X.loc[other_time].dropna()
                        common_assets = set(cross_section.index) & set(other_section.index)
                        if len(common_assets) > 3:
                            corr = np.corrcoef(cross_section[list(common_assets)], other_section[list(common_assets)])[
                                0, 1
                            ]
                            if not np.isnan(corr):
                                corrs.append(abs(corr))
                    return np.mean(corrs) if corrs else None
        except (ValueError, TypeError):
            pass
        return None

    def _classify_factor_type_enhanced(self, features: Dict[str, float]) -> str:
        scores = {}

        financial_score = 0
        if features.get("skewness", 0) > 0.5:
            financial_score += 2
        if features.get("outlier_ratio", 0) > 0.1:
            financial_score += 2
        if features.get("time_series_persistence", 0) > 0.3:
            financial_score += 1
        if features.get("cv", 0) > 1.0:
            financial_score += 1
        scores["financial"] = financial_score

        valuation_score = 0
        if features.get("skewness", 0) > 0.3:
            valuation_score += 2
        if features.get("outlier_ratio", 0) > 0.05:
            valuation_score += 1
        if features.get("cross_section_correlation", 0) > 0.3:
            valuation_score += 2
        if features.get("cv", 0) > 0.5:
            valuation_score += 1
        scores["valuation"] = valuation_score

        growth_score = 0
        if abs(features.get("skewness", 0)) < 1:
            growth_score += 1
        if features.get("outlier_ratio", 0) < 0.1:
            growth_score += 1
        if features.get("time_series_persistence", 0) < 0.3:
            growth_score += 2
        scores["growth"] = growth_score

        technical_score = 0
        if abs(features.get("skewness", 0)) < 0.5:
            technical_score += 1
        if features.get("outlier_ratio", 0) < 0.05:
            technical_score += 1
        if features.get("time_series_persistence", 0) < 0.2:
            technical_score += 3
        if features.get("cv", 0) < 0.5:
            technical_score += 1
        scores["technical"] = technical_score

        quality_score = 0
        if features.get("time_series_persistence", 0) > 0.3:
            quality_score += 1
        if features.get("cv", 0) < 1.0:
            quality_score += 1
        scores["quality"] = quality_score

        risk_score = 0
        if features.get("cross_section_correlation", 0) > 0.3:
            risk_score += 1
        if features.get("cv", 0) > 0.3:
            risk_score += 1
        scores["risk"] = risk_score

        macro_score = 0
        if features.get("time_series_persistence", 0) > 0.5:
            macro_score += 1
        scores["macro"] = macro_score

        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                best_types = [ft for ft, score in scores.items() if score == max_score]
                return best_types[0]
        return "financial"

    def _analyze_missing_pattern_enhanced(self, X: pd.DataFrame) -> str:
        missing_matrix = X.isnull()
        cross_section_missing = missing_matrix.mean(axis=1)
        if cross_section_missing.max() > 0.8:
            return "cross_sectional"

        time_series_missing = missing_matrix.mean(axis=0)
        if time_series_missing.max() > 0.8:
            return "time_series"

        missing_blocks = self._identify_missing_blocks(missing_matrix)
        if missing_blocks["max_block_size"] > X.shape[1] * 0.3:
            return "block"

        total_missing = missing_matrix.sum().sum()
        expected_random = missing_matrix.size * missing_matrix.mean().mean()
        if expected_random > 0 and abs(total_missing - expected_random) / expected_random < 0.1:
            return "random"

        return "mixed"

    def _identify_missing_blocks(self, missing_matrix: pd.DataFrame) -> Dict[str, Any]:
        max_block_size = 0
        block_count = 0
        for asset in missing_matrix.columns:
            asset_missing = missing_matrix[asset].astype(int)
            consecutive_ones = 0
            for is_missing in asset_missing:
                if is_missing:
                    consecutive_ones += 1
                    max_block_size = max(max_block_size, consecutive_ones)
                else:
                    if consecutive_ones > 0:
                        block_count += 1
                    consecutive_ones = 0
        return {"max_block_size": max_block_size, "block_count": block_count}

    def _select_optimal_strategy(self) -> None:
        if not self.factor_type:
            self.imputation_strategy = "generic"
            return

        characteristics = self.factor_characteristics.get(self.factor_type, {})

        if self.missing_rate > characteristics.get("max_missing_rate", 0.5):
            self.imputation_strategy = "em_multiple"
        elif self.missing_pattern == "cross_sectional":
            self.imputation_strategy = "cross_sectional_median"
        elif self.missing_pattern == "time_series":
            self.imputation_strategy = "ffill"
        elif self.missing_pattern == "block":
            self.imputation_strategy = "rolling_window"
        else:
            optimal_methods = characteristics.get("optimal_methods", ["cross_sectional_median"])
            self.imputation_strategy = optimal_methods[0]

    def _get_cached_result(self, data_hash: str, result_type: str) -> Any:
        if not self.enable_caching:
            return None
        cache_file = os.path.join(self.cache_dir, f"{result_type}_{data_hash}.pkl")
        try:
            if os.path.exists(cache_file):
                with open(cache_file, "rb") as f:
                    return pickle.load(f)
        except (OSError, pickle.PickleError):
            pass
        return None

    def _cache_result(self, data_hash: str, result_type: str, result: Any) -> None:
        if not self.enable_caching:
            return
        cache_file = os.path.join(self.cache_dir, f"{result_type}_{data_hash}.pkl")
        try:
            with self._cache_lock:
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
        except (OSError, TypeError):
            pass

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted:
            raise ValueError("插补器尚未拟合，请先调用fit方法")

        data_hash = self._generate_data_hash(X)
        if self.enable_caching:
            cached_result = self._get_cached_result(data_hash, "imputation")
            if cached_result is not None:
                return cached_result

        if self.imputation_strategy in self.imputation_methods:
            imputed_data = self.imputation_methods[self.imputation_strategy](X)
        else:
            imputed_data = super().transform(X)

        imputed_data = self._add_mnar_indicators(X, imputed_data)

        if self.validate_compliance:
            compliance_result = self.integrated_loader.validate_lookahead_free_compliance(X, imputed_data)
            if not compliance_result["is_compliant"]:
                warnings.warn(f"检测到前瞻偏差违规: {len(compliance_result['violations'])} 项")

        if self.enable_caching:
            self._cache_result(data_hash, "imputation", imputed_data)

        return imputed_data

    def _cross_sectional_median_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        X_imputed = X.copy()
        time_points = X.index.tolist()

        if self.enable_parallel and len(time_points) > 10:
            chunk_size = max(1, len(time_points) // self.n_workers)
            time_chunks = [time_points[i : i + chunk_size] for i in range(0, len(time_points), chunk_size)]
            with ThreadPoolExecutor(max_workers=self.n_workers) as executor:
                futures = [executor.submit(self._impute_time_chunk, X, chunk) for chunk in time_chunks]
                for future in futures:
                    chunk_results = future.result()
                    for time_point, imputed_values in chunk_results.items():
                        missing_mask = X.loc[time_point].isnull()
                        X_imputed.loc[time_point, missing_mask] = imputed_values
        else:
            for time_point in X.index:
                missing_mask = X.loc[time_point].isnull()
                if missing_mask.any():
                    imputed_values = self._impute_single_time_point(X, time_point, missing_mask)
                    X_imputed.loc[time_point, missing_mask] = imputed_values
        return X_imputed

    def _impute_time_chunk(self, X: pd.DataFrame, time_chunk: List[pd.Timestamp]) -> Dict[pd.Timestamp, pd.Series]:
        results = {}
        for time_point in time_chunk:
            missing_mask = X.loc[time_point].isnull()
            if missing_mask.any():
                imputed_values = self._impute_single_time_point(X, time_point, missing_mask)
                results[time_point] = imputed_values
        return results

    def _impute_single_time_point(
        self, X: pd.DataFrame, time_point: pd.Timestamp, missing_mask: pd.Series
    ) -> pd.Series:
        imputed_values = pd.Series(index=missing_mask[missing_mask].index, dtype=float)
        for asset in missing_mask[missing_mask].index:
            if self.factor_type in ["financial", "valuation", "quality"]:
                imputed_value = self._get_industry_median(X, time_point, asset)
            elif self.factor_type in ["growth", "technical"]:
                imputed_value = self._get_market_cap_median(X, time_point, asset)
            else:
                available_data = X.loc[time_point].dropna()
                imputed_value = available_data.median() if len(available_data) > 0 else np.nan
            if not np.isnan(imputed_value):
                imputed_values[asset] = imputed_value
        return imputed_values

    def _get_industry_median(self, X: pd.DataFrame, time_point: pd.Timestamp, asset: str) -> float:
        try:
            industry = self.integrated_loader.get_appropriate_group(asset, "sw_industry", time_point)
            if industry:
                industry_assets = [
                    col
                    for col in X.columns
                    if self.integrated_loader.get_appropriate_group(col, "sw_industry", time_point) == industry
                ]
                industry_data = X.loc[time_point, industry_assets].dropna()
                if len(industry_data) > 0:
                    return industry_data.median()
            overall_data = X.loc[time_point].dropna()
            return overall_data.median() if len(overall_data) > 0 else np.nan
        except (ValueError, TypeError, KeyError):
            return np.nan

    def _get_market_cap_median(self, X: pd.DataFrame, time_point: pd.Timestamp, asset: str) -> float:
        try:
            cap_group = self.integrated_loader.get_appropriate_group(asset, "market_cap", time_point)
            if cap_group:
                cap_assets = [
                    col
                    for col in X.columns
                    if self.integrated_loader.get_appropriate_group(col, "market_cap", time_point) == cap_group
                ]
                cap_data = X.loc[time_point, cap_assets].dropna()
                if len(cap_data) > 0:
                    return cap_data.median()
            overall_data = X.loc[time_point].dropna()
            return overall_data.median() if len(overall_data) > 0 else np.nan
        except (ValueError, TypeError, KeyError):
            return np.nan

    def _forward_fill_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        return X.ffill()

    def _rolling_window_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        X_imputed = X.copy()
        window_size = 20
        for asset in X.columns:
            asset_data = X[asset]
            for i in range(len(asset_data)):
                if pd.isna(asset_data.iloc[i]):
                    start_idx = max(0, i - window_size)
                    historical_data = asset_data.iloc[start_idx:i].dropna()
                    if len(historical_data) > 0:
                        if self.factor_type in ["financial", "valuation"]:
                            X_imputed.iloc[i, X.columns.get_loc(asset)] = historical_data.median()
                        else:
                            X_imputed.iloc[i, X.columns.get_loc(asset)] = historical_data.mean()
        return X_imputed

    def _knn_rolling_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        return self._cross_sectional_median_impute(X)

    def _em_multiple_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        X_imputed = X.copy()
        for time_point in X.index:
            missing_mask = X.loc[time_point].isnull()
            if missing_mask.any():
                available_data = X.loc[time_point].dropna()
                if len(available_data) > 5:
                    mean_val = available_data.mean()
                    std_val = available_data.std()
                    for asset in missing_mask[missing_mask].index:
                        X_imputed.loc[time_point, asset] = np.random.normal(mean_val, std_val)
        return X_imputed

    def _mnar_indicator_impute(self, X: pd.DataFrame) -> pd.DataFrame:
        if self.imputation_strategy in ["cross_sectional_median", "ffill", "rolling_window"]:
            return self.imputation_methods[self.imputation_strategy](X)
        return self._cross_sectional_median_impute(X)

    def _add_mnar_indicators(self, original_data: pd.DataFrame, imputed_data: pd.DataFrame) -> pd.DataFrame:
        additional_cols = []
        for asset in original_data.columns:
            missing_mask = original_data[asset].isnull()
            if missing_mask.any():
                indicator_name = f"{asset}_missing"
                additional_cols.append((indicator_name, missing_mask.astype(int)))

        if self.factor_type in ["financial", "valuation"]:
            for asset in original_data.columns:
                asset_data = original_data[asset].dropna()
                if len(asset_data) > 0:
                    q1, q3 = np.percentile(asset_data, [25, 75])
                    iqr = q3 - q1
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    extreme_mask = (original_data[asset] < lower_bound) | (original_data[asset] > upper_bound)
                    if extreme_mask.any():
                        indicator_name = f"{asset}_extreme"
                        additional_cols.append((indicator_name, extreme_mask.astype(int)))

        if additional_cols:
            additional_data = pd.DataFrame(
                {col_name: col_data for col_name, col_data in additional_cols}, index=original_data.index
            )
            return pd.concat([imputed_data, additional_data], axis=1)
        return imputed_data.copy()

    def clear_cache(self) -> None:
        if self.enable_caching and os.path.exists(self.cache_dir):
            import shutil

            try:
                shutil.rmtree(self.cache_dir)
                os.makedirs(self.cache_dir, exist_ok=True)
            except OSError:
                pass

    def get_cache_info(self) -> Dict[str, Any]:
        if not self.enable_caching:
            return {"enabled": False}
        cache_files = []
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, file)
                if os.path.isfile(file_path):
                    cache_files.append(
                        {"name": file, "size": os.path.getsize(file_path), "modified": os.path.getmtime(file_path)}
                    )
        return {
            "enabled": True,
            "directory": self.cache_dir,
            "files": cache_files,
            "total_size": sum(f["size"] for f in cache_files),
            "file_count": len(cache_files),
        }
