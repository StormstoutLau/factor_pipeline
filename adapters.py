# -*- coding: utf-8 -*-
"""
适配器模块
将三个独立的 v2.0 模块统一封装为 PipelineStep 接口
"""

import sys
import os
from typing import Dict, Any, Optional, List, Type
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# 可选依赖：statsmodels
try:
    import statsmodels.api as sm
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    sm = None

# =============================================================================
# 常量定义
# =============================================================================

# 默认缩尾分位限
DEFAULT_WINSORIZE_LIMITS = (0.05, 0.05)

# 中性化截面最小样本量
MIN_CROSS_SECTIONAL_OBS = 10
MIN_INDUSTRY_COMMON_OBS = 5

# GARCH 默认参数与阈值
GARCH_DEFAULT_P = 1
GARCH_DEFAULT_Q = 1
GARCH_MIN_OBS = 50

# 滚动标准差近似参数
ROLLING_WINDOW = 20
ROLLING_MIN_PERIODS = 10


# =============================================================================
# 动态导入工具函数
# =============================================================================

def _import_external_class(
    module_path: str,
    import_path: str,
    class_name: str
) -> Optional[Type]:
    """从外部模块动态导入类
    
    Parameters
    ----------
    module_path : str
        模块所在目录的相对路径（如 '..', 'Factor_Imputer_v2.0'）
    import_path : str
        Python 导入路径（如 'core.imputers'）
    class_name : str
        要导入的类名
    
    Returns
    -------
    type | None
        导入的类，失败则返回 None
    
    Examples
    --------
    >>> cls = _import_external_class(
    ...     '..', 'Factor_Imputer_v2.0', 'core.imputers', 'HierarchicalImputer'
    ... )
    """
    try:
        full_path = os.path.join(os.path.dirname(__file__), module_path)
        # TODO: 使用上下文管理器临时修改 sys.path，避免污染全局状态
        # 当前实现是已知的设计权衡：只在导入外部类时添加路径
        if full_path not in sys.path:
            sys.path.insert(0, full_path)
        module = __import__(import_path, fromlist=[class_name])
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        logger.warning(
            f"无法从 {module_path}/{import_path} 导入 {class_name}: {e}"
        )
        return None


class PipelineStep(ABC):
    """流水线步骤抽象基类"""
    
    def __init__(self, name: str, step_type: str, **params):
        self.name = name
        self.step_type = step_type
        self.params = params
        self.is_fitted = False
        self.fitted_params = {}
        self._inner_instance = None
    
    @abstractmethod
    def fit(self, X: pd.DataFrame, **kwargs) -> 'PipelineStep':
        """拟合步骤参数"""
        pass
    
    @abstractmethod
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用步骤变换"""
        pass
    
    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(X, **kwargs).transform(X, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取步骤统计信息"""
        return {
            'name': self.name,
            'step_type': self.step_type,
            'is_fitted': self.is_fitted,
            'params': self.params
        }


class ImputerAdapter(PipelineStep):
    """
    插补模块适配器
    封装 Factor_Imputer_v2.0 的 HierarchicalImputer
    """
    
    def __init__(self, strategy: str = 'auto', **params):
        super().__init__(
            name="FactorImputer",
            step_type="imputation",
            strategy=strategy,
            **params
        )
        self.strategy = strategy
        self._imputer = None
        self._missing_info = None
    
    def _get_imputer_class(self):
        """动态导入插补器类"""
        return _import_external_class(
            os.path.join('..', 'Factor_Imputer_v2.0'),
            'core.imputers',
            'HierarchicalImputer'
        )
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ImputerAdapter':
        """拟合插补器"""
        imputer_class = self._get_imputer_class()
        
        if imputer_class is None:
            # 回退：使用简单的中位数插补
            logger.info("使用内置简单插补器")
            self._imputer = None
            self.is_fitted = True
            return self
        
        self._imputer = imputer_class(strategy=self.strategy)
        
        # 检测缺失信息
        if hasattr(self._imputer, 'detect_missing_type'):
            self._missing_info = self._imputer.detect_missing_type(X)
        
        # 拟合
        self._imputer.fit(X, self._missing_info)
        self.is_fitted = True
        
        logger.info(f"插补器拟合完成，策略: {self.strategy}")
        return self
    
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用插补"""
        if not self.is_fitted:
            raise ValueError("插补器未拟合，请先调用 fit()")
        
        if self._imputer is None:
            # 回退：简单中位数插补
            if X.empty or X.isnull().all().all():
                logger.warning("输入数据为空或全为NaN，返回原始数据")
                return X
            median_vals = X.median()
            if median_vals.isnull().all():
                logger.warning("所有列的中位数均为NaN，返回原始数据")
                return X
            return X.fillna(median_vals)
        
        result = self._imputer.transform(X)
        
        # 记录插补统计
        missing_before = X.isnull().sum().sum()
        missing_after = result.isnull().sum().sum()
        logger.info(f"插补完成: {missing_before} -> {missing_after} 缺失值")
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['strategy'] = self.strategy
        stats['missing_info'] = self._missing_info
        return stats


class ProcessingAdapter(PipelineStep):
    """
    处理模块适配器
    封装 Factor_AdaptiveWinsor 的去极值、变换、标准化
    支持三种子类型: outlier, transformation, standardization
    """
    
    STEP_CLASS_MAP = {
        'outlier': ('core.transformers', 'SmartOutlierDetector'),
        'transformation': ('core.transformers', 'AdaptiveTransformer'),
        'standardization': ('core.transformers', 'AdaptiveStandardizer'),
    }
    
    def __init__(self, process_type: str = 'outlier', method: str = 'auto', **params):
        super().__init__(
            name=f"FactorProcessing_{process_type}",
            step_type=process_type,
            method=method,
            **params
        )
        self.process_type = process_type
        self.method = method
        self._processor = None
    
    def _get_processor_class(self):
        """动态导入处理器类"""
        module_name, class_name = self.STEP_CLASS_MAP.get(
            self.process_type,
            ('core.transformers', 'SmartOutlierDetector')
        )
        return _import_external_class(
            os.path.join('..', 'Factor_AdaptiveWinsor'),
            module_name,
            class_name
        )
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ProcessingAdapter':
        """拟合处理器"""
        processor_class = self._get_processor_class()
        
        if processor_class is None:
            logger.info(f"使用内置简单{self.process_type}处理器")
            self._processor = None
            self.is_fitted = True
            return self
        
        # 实例化处理器
        processor_params = {'method': self.method}
        processor_params.update(self.params)
        self._processor = processor_class(**processor_params)
        
        # 拟合 - 需要展平数据
        if isinstance(X, pd.DataFrame):
            flat_data = X.values.flatten()
            flat_data = flat_data[~np.isnan(flat_data)]
        else:
            flat_data = X
        
        if len(flat_data) > 0:
            self._processor.fit(flat_data)
        
        self.is_fitted = True
        logger.info(f"{self.process_type} 处理器拟合完成，方法: {self.method}")
        return self
    
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用处理"""
        if not self.is_fitted:
            raise ValueError("处理器未拟合，请先调用 fit()")
        
        if self._processor is None:
            # 回退处理
            if self.process_type == 'outlier':
                return self._simple_winsorize(X)
            elif self.process_type == 'standardization':
                return self._simple_standardize(X)
            else:
                return X
        
        # 对 DataFrame 的每一列应用变换
        result = X.copy()
        
        for col in X.columns:
            col_data = X[col].dropna()
            if len(col_data) > 0:
                try:
                    transformed = self._processor.transform(col_data)
                    result.loc[col_data.index, col] = transformed
                except (ValueError, TypeError, RuntimeError) as e:
                    logger.warning(f"列 {col} 变换失败: {e}，保持原值")
        
        return result
    
    def _simple_winsorize(self, X: pd.DataFrame, limits: tuple = DEFAULT_WINSORIZE_LIMITS) -> pd.DataFrame:
        """简单缩尾处理（回退方案）"""
        result = X.copy()
        lower = X.quantile(limits[0])
        upper = X.quantile(1 - limits[1])
        return result.clip(lower=lower, upper=upper, axis=1)
    
    def _simple_standardize(self, X: pd.DataFrame) -> pd.DataFrame:
        """简单Z-score标准化（回退方案）"""
        mean = X.mean()
        std = X.std()
        std_safe = std.replace(0, 1)
        return (X - mean) / std_safe
    
    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['process_type'] = self.process_type
        stats['method'] = self.method
        if self._processor and hasattr(self._processor, 'fitted_params'):
            stats['fitted_params'] = self._processor.fitted_params
        return stats


class NeutralizerAdapter(PipelineStep):
    """
    中性化模块适配器
    封装 Factor_Neutralizer_v2.0 的 FactorNeutralizer
    
    注意: FactorNeutralizer 的接口与其他两个模块不同，
    它需要在初始化时传入行业/市值等数据路径
    """
    
    def __init__(self, 
                 neutralization_type: str = 'industry',
                 industry_method: str = 'regression',
                 industry_data: Optional[pd.Series] = None,
                 market_value_data: Optional[pd.DataFrame] = None,
                 **params):
        super().__init__(
            name="FactorNeutralizer",
            step_type="neutralization",
            neutralization_type=neutralization_type,
            industry_method=industry_method,
            **params
        )
        self.neutralization_type = neutralization_type
        self.industry_method = industry_method
        self.industry_data = industry_data
        self.market_value_data = market_value_data
        self._neutralizer = None
    
    def _get_neutralizer_class(self):
        """动态导入中性化器类"""
        return _import_external_class(
            module_path=os.path.join('..', 'Factor_Neutralizer_v2.0'),
            import_path='factor_neutralizer.core.FactorNeutralizer',
            class_name='FactorNeutralizer'
        )

    def fit(self, X: pd.DataFrame, **kwargs) -> 'NeutralizerAdapter':
        """
        拟合中性化器
        注意: FactorNeutralizer 需要外部数据，这里做轻量级适配
        """
        neutralizer_class = self._get_neutralizer_class()

        if neutralizer_class is None:
            logger.info("使用内置简单中性化器")
            self._neutralizer = None
            self.is_fitted = True
            return self
        
        # 由于 FactorNeutralizer 需要文件路径初始化，
        # 这里我们只记录状态，实际 transform 时再处理
        self._neutralizer = 'external'  # 标记为外部模块
        self.is_fitted = True
        
        logger.info(f"中性化器准备完成，类型: {self.neutralization_type}")
        return self
    
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用中性化"""
        if not self.is_fitted:
            raise ValueError("中性化器未拟合，请先调用 fit()")
        
        # 如果有外部传入的行业数据，执行简单行业中性化
        if self.industry_data is not None:
            return self._simple_industry_neutralize(X, self.industry_data)
        
        # 如果提供了完整配置的 Neutralizer 实例
        external_neutralizer = kwargs.get('external_neutralizer')
        if external_neutralizer is not None:
            return external_neutralizer.industry_neutralization(X, self.industry_method)
        
        logger.warning("无行业数据，跳过中性化")
        return X
    
    def _simple_industry_neutralize(self,
                                     factor_data: pd.DataFrame,
                                     industry_data: pd.Series) -> pd.DataFrame:
        """简单行业中性化（截面回归残差）"""
        if not HAS_STATSMODELS or sm is None:
            logger.warning("statsmodels 不可用，跳过行业中性化")
            return factor_data

        result = pd.DataFrame(index=factor_data.index, columns=factor_data.columns, dtype=float)

        for date in factor_data.index:
            date_factor = factor_data.loc[date].dropna()
            if len(date_factor) < MIN_CROSS_SECTIONAL_OBS:
                continue

            # 对齐行业数据
            common = date_factor.index.intersection(industry_data.index)
            if len(common) < MIN_INDUSTRY_COMMON_OBS:
                continue

            y = date_factor[common].values.astype(float)
            industries = industry_data[common]

            # 创建行业哑变量
            dummies = pd.get_dummies(industries, drop_first=True).astype(float)
            if dummies.empty or dummies.shape[1] == 0:
                logger.warning(f"日期 {date} 行业哑变量为空，跳过中性化")
                result.loc[date, common] = y
                continue

            X = sm.add_constant(dummies, has_constant='add').astype(float)
            if X.shape[0] != len(y):
                logger.warning(f"日期 {date} 回归矩阵维度不匹配，跳过")
                result.loc[date, common] = y
                continue

            try:
                model = sm.OLS(y, X).fit()
                residuals = model.resid.values if hasattr(model.resid, 'values') else model.resid
                result.loc[date, common] = residuals
            except (ValueError, TypeError, RuntimeError) as e:
                logger.warning(f"日期 {date} 中性化失败: {e}")
                result.loc[date, common] = y

        return result.fillna(0)
    
    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['neutralization_type'] = self.neutralization_type
        stats['industry_method'] = self.industry_method
        stats['has_industry_data'] = self.industry_data is not None
        return stats


class GarchWhiteningAdapter(PipelineStep):
    """
    GARCH白化适配器

    使用 GARCH 模型提取条件异方差，对残差进行预白化。
    适用于高自相关、高波动率聚集的静态因子。

    处理流程：
        1. 对每列时间序列拟合 GARCH(p,q) 模型
        2. 提取标准化残差：resid / conditional_volatility
        3. 返回白化后的序列（消除波动率聚集）

    注意：
        - 需要至少 50 个观测值才能拟合 GARCH
        - 数据不足时跳过白化，返回原始值
        - 需要安装 arch 包：pip install arch
    """

    def __init__(self,
                 method: str = 'garch',
                 p: int = GARCH_DEFAULT_P,
                 q: int = GARCH_DEFAULT_Q,
                 vol: str = 'Garch',
                 min_obs: int = GARCH_MIN_OBS,
                 **params):
        super().__init__(
            name="GarchWhitening",
            step_type="garch_whitening",
            method=method,
            p=p,
            q=q,
            vol=vol,
            **params
        )
        self.method = method
        self.p = p
        self.q = q
        self.vol = vol
        self.min_obs = min_obs
        self._models: Dict[str, Any] = {}
        self._skipped_cols: List[str] = []

    def _get_arch_model_class(self):
        """动态导入 arch 模型类"""
        try:
            from arch import arch_model
            return arch_model
        except ImportError as e:
            logger.warning(f"无法导入 arch 包: {e}，GARCH白化将跳过")
            return None

    def fit(self, X: pd.DataFrame, **kwargs) -> 'GarchWhiteningAdapter':
        """
        拟合 GARCH 模型

        对每列时间序列单独拟合 GARCH(p,q) 模型。
        """
        arch_model_func = self._get_arch_model_class()

        if arch_model_func is None:
            self.is_fitted = True
            return self

        for col in X.columns:
            series = X[col].dropna()

            if len(series) < self.min_obs:
                logger.warning(
                    f"列 {col} 观测值不足 ({len(series)} < {self.min_obs})，跳过 GARCH 白化"
                )
                self._skipped_cols.append(col)
                continue

            try:
                model = arch_model_func(
                    series,
                    vol=self.vol,
                    p=self.p,
                    q=self.q,
                    rescale=False
                )
                fitted = model.fit(disp='off', show_warning=False)
                self._models[col] = fitted
                logger.info(f"列 {col} GARCH({self.p},{self.q}) 拟合完成，AIC={fitted.aic:.2f}")

            except (ValueError, TypeError, RuntimeError, ImportError) as e:
                logger.warning(f"列 {col} GARCH 拟合失败: {e}，跳过白化")
                self._skipped_cols.append(col)

        self.is_fitted = True
        logger.info(f"GARCH白化拟合完成：{len(self._models)} 列成功，{len(self._skipped_cols)} 列跳过")
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        应用 GARCH 白化

        返回标准化残差：resid / conditional_volatility
        """
        if not self.is_fitted:
            raise ValueError("GARCH白化器未拟合，请先调用 fit()")

        if not self._models:
            logger.info("无 GARCH 模型，跳过白化")
            return X

        result = X.copy()

        for col, fitted_model in self._models.items():
            if col not in X.columns:
                continue

            try:
                # 获取标准化残差：残差 / 条件标准差
                resid = fitted_model.resid
                cond_vol = fitted_model.conditional_volatility

                # 安全除法
                cond_vol_safe = cond_vol.replace(0, np.nan)
                standardized = resid / cond_vol_safe

                # 检查结果有效性
                if standardized.isnull().all():
                    logger.warning(f"列 {col} 条件波动率全为零，跳过白化，保持原值")
                    continue

                # 对齐索引
                common_idx = X.index.intersection(standardized.index)
                valid_idx = common_idx[~standardized.loc[common_idx].isnull()]
                result.loc[valid_idx, col] = standardized.loc[valid_idx]

                logger.info(f"列 {col} GARCH 白化完成，残差均值={standardized.mean():.4f}，std={standardized.std():.4f}")

            except Exception as e:
                logger.warning(f"列 {col} GARCH 白化变换失败: {e}，保持原值")

        return result

    def _simple_whiten(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        简单白化（回退方案）

        当 arch 包不可用时，使用滚动标准差近似。
        """
        result = X.copy()
        for col in X.columns:
            series = X[col]
            rolling_std = series.rolling(window=ROLLING_WINDOW, min_periods=ROLLING_MIN_PERIODS).std()
            rolling_std_safe = rolling_std.replace(0, np.nan)
            result[col] = series / rolling_std_safe
        return result

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['method'] = self.method
        stats['p'] = self.p
        stats['q'] = self.q
        stats['fitted_models'] = len(self._models)
        stats['skipped_columns'] = self._skipped_cols
        if self._models:
            avg_aic = np.mean([m.aic for m in self._models.values()])
            stats['average_aic'] = avg_aic
        return stats
