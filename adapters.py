# -*- coding: utf-8 -*-
"""
适配器模块
将三个独立的 v2.0 模块统一封装为 PipelineStep 接口
"""

import sys
import os
from typing import Dict, Any, Union, Optional
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


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
        try:
            # 尝试直接导入
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Factor_Imputer_v2.0'))
            from core.imputers import HierarchicalImputer
            return HierarchicalImputer
        except ImportError as e:
            logger.warning(f"无法从 Factor_Imputer_v2.0 导入: {e}")
            return None
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ImputerAdapter':
        """拟合插补器"""
        ImputerClass = self._get_imputer_class()
        
        if ImputerClass is None:
            # 回退：使用简单的中位数插补
            logger.info("使用内置简单插补器")
            self._imputer = None
            self.is_fitted = True
            return self
        
        self._imputer = ImputerClass(strategy=self.strategy)
        
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
            return X.fillna(X.median())
        
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
        
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Factor_AdaptiveWinsor'))
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            logger.warning(f"无法从 Factor_AdaptiveWinsor 导入 {class_name}: {e}")
            return None
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ProcessingAdapter':
        """拟合处理器"""
        ProcessorClass = self._get_processor_class()
        
        if ProcessorClass is None:
            logger.info(f"使用内置简单{self.process_type}处理器")
            self._processor = None
            self.is_fitted = True
            return self
        
        # 实例化处理器
        processor_params = {'method': self.method}
        processor_params.update(self.params)
        self._processor = ProcessorClass(**processor_params)
        
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
                except Exception as e:
                    logger.warning(f"列 {col} 变换失败: {e}，保持原值")
        
        return result
    
    def _simple_winsorize(self, X: pd.DataFrame, limits: tuple = (0.05, 0.05)) -> pd.DataFrame:
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
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Factor_Neutralizer_v2.0'))
            from factor_neutralizer.core.FactorNeutralizer import FactorNeutralizer
            return FactorNeutralizer
        except ImportError as e:
            logger.warning(f"无法从 Factor_Neutralizer_v2.0 导入: {e}")
            return None
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'NeutralizerAdapter':
        """
        拟合中性化器
        注意: FactorNeutralizer 需要外部数据，这里做轻量级适配
        """
        NeutralizerClass = self._get_neutralizer_class()
        
        if NeutralizerClass is None:
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
        import statsmodels.api as sm

        result = pd.DataFrame(index=factor_data.index, columns=factor_data.columns, dtype=float)

        for date in factor_data.index:
            date_factor = factor_data.loc[date].dropna()
            if len(date_factor) < 10:
                continue

            # 对齐行业数据
            common = date_factor.index.intersection(industry_data.index)
            if len(common) < 5:
                continue

            y = date_factor[common].values.astype(float)
            industries = industry_data[common]

            # 创建行业哑变量
            dummies = pd.get_dummies(industries, drop_first=True).astype(float)
            X = sm.add_constant(dummies, has_constant='add').astype(float)

            try:
                model = sm.OLS(y, X).fit()
                residuals = model.resid.values if hasattr(model.resid, 'values') else model.resid
                result.loc[date, common] = residuals
            except Exception as e:
                logger.warning(f"日期 {date} 中性化失败: {e}")
                result.loc[date, common] = y

        return result.fillna(0)
    
    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['neutralization_type'] = self.neutralization_type
        stats['industry_method'] = self.industry_method
        stats['has_industry_data'] = self.industry_data is not None
        return stats
