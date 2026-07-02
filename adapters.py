# -*- coding: utf-8 -*-
"""
适配器模块
将三个独立的 v2.0 模块统一封装为 PipelineStep 接口
"""

import sys
import os
import importlib
import contextlib
from typing import Dict, Any, Optional, List, Type
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
import logging
import warnings

from .exceptions import AdapterImportError

logger = logging.getLogger(__name__)

# P2.5: statsmodels 现为 REQUIRED 依赖 (pyproject.toml 声明), 直接导入
import statsmodels.api as sm

# 可选依赖：arch (GARCH 白化) — pyproject.toml [garch] extra
try:
    from arch import arch_model as _arch_model
    HAS_ARCH = True
except ImportError:
    HAS_ARCH = False
    _arch_model = None

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

@contextlib.contextmanager
def _temp_sys_path(path: str):
    """
    上下文管理器：临时添加路径到 sys.path，退出时自动恢复。

    P2-8 修复: 替代直接 sys.path.insert(0, ...) 以避免全局状态污染。

    Usage:
        with _temp_sys_path('/some/path'):
            module = importlib.import_module('some.module')
    """
    path = os.path.abspath(path)
    added = path not in sys.path
    if added:
        sys.path.insert(0, path)
    try:
        yield
    finally:
        if added and path in sys.path:
            sys.path.remove(path)


def _import_external_class(
    module_path: str,
    import_path: str,
    class_name: str
) -> Optional[Type]:
    """从外部模块动态导入类

    P2-8 修复: 使用 importlib + 上下文管理器替代 sys.path.insert + __import__，
    确保导入完成后 sys.path 恢复原状。

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
    ...     os.path.join('..', 'Factor_Imputer_v2.0'),
    ...     'core.imputers', 'HierarchicalImputer'
    ... )
    """
    try:
        full_path = os.path.join(os.path.dirname(__file__), module_path)
        with _temp_sys_path(full_path):
            module = importlib.import_module(import_path)
            return getattr(module, class_name)
    except (ImportError, AttributeError, ModuleNotFoundError) as e:
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
        self.is_fallback_mode = False
    
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
    
    def __init__(self, strategy: str = 'auto', module_path=None, import_path=None, class_name=None, **params):
        super().__init__(
            name="FactorImputer",
            step_type="imputation",
            strategy=strategy,
            **params
        )
        self.strategy = strategy
        self._imputer = None
        self._missing_info = None
        
        # P2.4: 保留 override 参数仅供测试 mock 使用, 生产路径直接导入
        self._module_path_override = module_path
        self._import_path_override = import_path
        self._class_name_override = class_name

        # P2.4: REQUIRED 依赖, 构造时即校验, 失败抛 AdapterImportError
        # 缓存类供 fit() 使用, 避免重复导入
        self._imputer_class = self._get_imputer_class()
        # is_fallback_mode 保留向后兼容, REQUIRED 依赖下永远为 False
        self.is_fallback_mode = False
    
    def _get_imputer_class(self):
        """导入插补器类 — P2.4: REQUIRED 依赖, 失败抛 AdapterImportError"""
        # 测试 mock 路径: 通过 override 触发导入失败
        if self._module_path_override and self._import_path_override and self._class_name_override:
            cls = _import_external_class(
                self._module_path_override,
                self._import_path_override,
                self._class_name_override
            )
            if cls is None:
                raise AdapterImportError(
                    f"ImputerAdapter: 测试 mock 路径导入失败 ({self._module_path_override}/{self._import_path_override}.{self._class_name_override})",
                    module_path=self._module_path_override,
                    class_name=self._class_name_override,
                )
            return cls
        # P2.4: 生产路径直接导入, 失败抛 AdapterImportError (不再静默回退)
        try:
            from factor_pipeline.modules.factor_imputer.core.imputers import HierarchicalImputer
            return HierarchicalImputer
        except ImportError as e:
            raise AdapterImportError(
                f"ImputerAdapter: REQUIRED 依赖 factor-imputer 导入失败: {e}. "
                f"factor_imputer 模块已内化, 请运行 pip install -e . 安装 factor_pipeline",
                module_path="factor_pipeline.modules.factor_imputer.core.imputers",
                class_name="HierarchicalImputer",
            ) from e
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ImputerAdapter':
        """拟合插补器 — P2.4: REQUIRED 依赖, 构造时已校验, 直接使用"""
        self._imputer = self._imputer_class(strategy=self.strategy)

        # 检测缺失信息
        if hasattr(self._imputer, 'detect_missing_type'):
            self._missing_info = self._imputer.detect_missing_type(X)

        # 拟合
        self._imputer.fit(X, self._missing_info)
        self.is_fitted = True

        logger.info(f"插补器拟合完成，策略: {self.strategy}")
        return self
    
    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用插补 — P2.4: REQUIRED 依赖, _imputer 必非 None"""
        if not self.is_fitted:
            raise ValueError("插补器未拟合，请先调用 fit()")

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
        stats['fallback_mode'] = self.is_fallback_mode
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
    
    def __init__(self, process_type: str = 'outlier', method: str = 'auto',
                 module_path=None, import_path=None, class_name=None, **params):
        super().__init__(
            name=f"FactorProcessing_{process_type}",
            step_type=process_type,
            method=method,
            **params
        )
        self.process_type = process_type
        self.method = method
        self._processor = None
        # P1.3 修复: standardization 类型按列拟合（截面因子时序标准化语义）
        # 全局展平 fit + 按列 transform 不能保证每列均值=0, 需按列单独 fit
        self._column_processors: Dict[str, Any] = {}

        # 存储外部模块导入覆盖参数
        self._module_path_override = module_path
        self._import_path_override = import_path
        self._class_name_override = class_name

        # P2.4: REQUIRED 依赖, 构造时即校验, 失败抛 AdapterImportError
        self._processor_class = self._get_processor_class()
        # is_fallback_mode 保留向后兼容, REQUIRED 依赖下永远为 False
        self.is_fallback_mode = False
    
    def _get_processor_class(self):
        """导入处理器类 — P2.4: REQUIRED 依赖, 失败抛 AdapterImportError"""
        # 测试 mock 路径
        if self._module_path_override and self._import_path_override and self._class_name_override:
            cls = _import_external_class(
                self._module_path_override,
                self._import_path_override,
                self._class_name_override
            )
            if cls is None:
                raise AdapterImportError(
                    f"ProcessingAdapter({self.process_type}): 测试 mock 路径导入失败",
                    module_path=self._module_path_override,
                    class_name=self._class_name_override,
                )
            return cls
        # P2.4: 生产路径直接导入, 失败抛 AdapterImportError
        module_name, class_name = self.STEP_CLASS_MAP.get(
            self.process_type,
            ('core.transformers', 'SmartOutlierDetector')
        )
        try:
            # v2.4.0 (ADR-019): 内化后路径从 Factor_AdaptiveWinsor 改为
            # factor_pipeline.modules.factor_adaptive_winsor
            mod = __import__(f"factor_pipeline.modules.factor_adaptive_winsor.{module_name}", fromlist=[class_name])
            cls = getattr(mod, class_name, None)
            if cls is None:
                raise AdapterImportError(
                    f"ProcessingAdapter({self.process_type}): {class_name} 不在 factor_pipeline.modules.factor_adaptive_winsor.{module_name}",
                    module_path=f"factor_pipeline.modules.factor_adaptive_winsor.{module_name}",
                    class_name=class_name,
                )
            return cls
        except ImportError as e:
            raise AdapterImportError(
                f"ProcessingAdapter({self.process_type}): 内化模块导入失败: {e}. "
                f"请检查 factor_pipeline.modules.factor_adaptive_winsor 安装状态",
                module_path=f"factor_pipeline.modules.factor_adaptive_winsor.{module_name}",
                class_name=class_name,
            ) from e
    
    def fit(self, X: pd.DataFrame, **kwargs) -> 'ProcessingAdapter':
        """拟合处理器 — P2.4: REQUIRED 依赖, 构造时已校验, 直接使用"""
        # 实例化处理器
        processor_params = {'method': self.method}
        processor_params.update(self.params)

        # P1.3 修复: standardization 类型按列拟合（截面因子时序标准化语义）
        # 全局展平 fit + 按列 transform 不能保证每列均值=0, 需按列单独 fit
        if self.process_type == 'standardization' and isinstance(X, pd.DataFrame):
            self._processor = None
            self._column_processors = {}
            for col in X.columns:
                col_data = X[col].dropna()
                if len(col_data) > 0:
                    col_processor = self._processor_class(**processor_params)
                    col_processor.fit(col_data)
                    self._column_processors[col] = col_processor
        else:
            # 其他类型: 全局展平 fit + 按列 transform
            self._processor = self._processor_class(**processor_params)
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
        """应用处理 — P2.4: REQUIRED 依赖, _processor/_column_processors 必非空"""
        if not self.is_fitted:
            raise ValueError("处理器未拟合，请先调用 fit()")

        # P1.3 修复: standardization 类型按列应用对应 processor
        if self.process_type == 'standardization' and self._column_processors:
            result = X.copy()
            for col in X.columns:
                if col not in self._column_processors:
                    continue
                col_data = X[col].dropna()
                if len(col_data) > 0:
                    try:
                        transformed = self._column_processors[col].transform(col_data)
                        result.loc[col_data.index, col] = transformed
                    except (ValueError, TypeError, RuntimeError) as e:
                        logger.warning(f"列 {col} 变换失败: {e}，保持原值")
            return result

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

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats['process_type'] = self.process_type
        stats['method'] = self.method
        stats['fallback_mode'] = self.is_fallback_mode
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
                 module_path=None, import_path=None, class_name=None,
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

        # TD-3 (ADR-018): fit() 预计算的 industry dummies 缓存
        # {date: (dummy_matrix_with_const, common_stocks_Index)}
        self._industry_dummies_cache: Dict[Any, Any] = {}
        # fit() 时绑定的 industry_data (可能来自 kwargs 或 __init__)
        self._fitted_industry_data: Optional[pd.Series] = None

        # 存储外部模块导入覆盖参数
        self._module_path_override = module_path
        self._import_path_override = import_path
        self._class_name_override = class_name

        # P3.2: REQUIRED 依赖, 构造时即校验, 失败抛 AdapterImportError
        # 缓存类供 fit() 使用, 避免重复导入
        self._neutralizer_class = self._get_neutralizer_class()
        # is_fallback_mode 保留向后兼容, REQUIRED 依赖下永远为 False
        self.is_fallback_mode = False

    def _get_neutralizer_class(self):
        """导入中性化器类 — P3.2: REQUIRED 依赖, 失败抛 AdapterImportError"""
        # 测试 mock 路径
        if self._module_path_override and self._import_path_override and self._class_name_override:
            cls = _import_external_class(
                self._module_path_override,
                self._import_path_override,
                self._class_name_override
            )
            if cls is None:
                raise AdapterImportError(
                    f"NeutralizerAdapter: 测试 mock 路径导入失败 ({self._module_path_override}/{self._import_path_override}.{self._class_name_override})",
                    module_path=self._module_path_override,
                    class_name=self._class_name_override,
                )
            return cls
        # P3.2: 生产路径直接导入, 失败抛 AdapterImportError (不再静默回退)
        try:
            from factor_pipeline.modules.factor_neutralizer.core import FactorNeutralizer
            return FactorNeutralizer
        except ImportError as e:
            raise AdapterImportError(
                f"NeutralizerAdapter: REQUIRED 依赖 factor-neutralizer 导入失败: {e}. "
                f"factor_neutralizer 模块已内化, 请运行 pip install -e . 安装 factor_pipeline",
                module_path="factor_pipeline.modules.factor_neutralizer.core",
                class_name="FactorNeutralizer",
            ) from e

    def fit(self, X: pd.DataFrame, **kwargs) -> 'NeutralizerAdapter':
        """
        拟合中性化器 — TD-3 (ADR-018): 预计算 industry dummies 矩阵

        fit() 对每个截面日期预计算 (dummy_matrix_with_const, common_stocks),
        缓存到 _industry_dummies_cache. transform() 直接用缓存的 dummies 做 OLS,
        不再每次重新计算 pd.get_dummies.

        industry_data 来源优先级:
            1. kwargs['industry_data'] (fit_transform 透传)
            2. self.industry_data (__init__ 传入)
        """
        # 解析 industry_data: kwargs 优先 (fit_transform 透传), 其次 __init__
        industry_data = kwargs.get('industry_data', None)
        if industry_data is None:
            industry_data = self.industry_data
        self._fitted_industry_data = industry_data

        # 重置缓存 (允许重复 fit)
        self._industry_dummies_cache = {}

        if industry_data is not None:
            for date in X.index:
                date_factor = X.loc[date].dropna()
                if len(date_factor) < MIN_CROSS_SECTIONAL_OBS:
                    continue

                # 对齐行业数据
                common = date_factor.index.intersection(industry_data.index)
                if len(common) < MIN_INDUSTRY_COMMON_OBS:
                    continue

                industries = industry_data[common]

                # 预计算行业哑变量矩阵 (含常数项)
                dummies = pd.get_dummies(industries, drop_first=True).astype(float)
                if dummies.empty or dummies.shape[1] == 0:
                    logger.warning(f"日期 {date} 行业哑变量为空，跳过该日期预计算")
                    continue

                dummy_matrix = sm.add_constant(dummies, has_constant='add').astype(float)
                if dummy_matrix.shape[0] != len(date_factor[common]):
                    logger.warning(f"日期 {date} 回归矩阵维度不匹配，跳过预计算")
                    continue

                self._industry_dummies_cache[date] = (dummy_matrix, common)

            logger.info(
                f"中性化器拟合完成，类型: {self.neutralization_type}, "
                f"预计算 {len(self._industry_dummies_cache)}/{len(X.index)} 个日期的 dummies"
            )
        else:
            logger.info(f"中性化器拟合完成，无 industry_data, transform 时将跳过中性化")

        self._neutralizer = None  # 不使用外部 FactorNeutralizer 实例
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """应用中性化 — TD-3 (ADR-018): 用 fit() 缓存的 dummies 做 OLS + 残差

        优先级:
            1. external_neutralizer kwargs (向后兼容, 调用外部完整 Neutralizer)
            2. fit() 缓存的 _industry_dummies_cache (TD-3 新路径, 截面 OLS 残差)
            3. 无缓存且无 external_neutralizer: 跳过中性化 (warning + return X)
        """
        if not self.is_fitted:
            raise ValueError("中性化器未拟合，请先调用 fit()")

        # 优先级 1: external_neutralizer (向后兼容)
        external_neutralizer = kwargs.get('external_neutralizer')
        if external_neutralizer is not None:
            return external_neutralizer.industry_neutralization(X, self.industry_method)

        # 优先级 2: 用 fit() 缓存的 dummies 做 OLS
        if self._industry_dummies_cache:
            return self._neutralize_with_cache(X)

        # 优先级 3: 无 dummies 缓存, 跳过
        logger.warning("无行业数据，跳过中性化")
        return X

    def _neutralize_with_cache(self, X: pd.DataFrame) -> pd.DataFrame:
        """用 fit() 预计算的 dummies 做截面 OLS + 残差 (TD-3 ADR-018)"""
        result = pd.DataFrame(index=X.index, columns=X.columns, dtype=float)

        for date in X.index:
            if date not in self._industry_dummies_cache:
                continue

            dummy_matrix, common = self._industry_dummies_cache[date]
            date_factor = X.loc[date]
            y = date_factor[common].values.astype(float)

            # 维度校验 (transform 数据应与 fit 数据一致)
            if dummy_matrix.shape[0] != len(y):
                logger.warning(f"日期 {date} transform 数据维度与 fit 不匹配，跳过")
                result.loc[date, common] = y
                continue

            try:
                model = sm.OLS(y, dummy_matrix).fit()
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
        stats['fallback_mode'] = self.is_fallback_mode
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
        # P3.3: 直接使用模块级 _arch_model (顶层 try/except 已处理导入)
        self._has_arch = HAS_ARCH
        self.is_fallback_mode = not HAS_ARCH

    def fit(self, X: pd.DataFrame, **kwargs) -> 'GarchWhiteningAdapter':
        """
        拟合 GARCH 模型 — P3.3: 直接使用模块级 _arch_model, 删除重复导入

        对每列时间序列单独拟合 GARCH(p,q) 模型。
        """
        if not self._has_arch or _arch_model is None:
            warnings.warn(
                f"GarchWhiteningAdapter: arch 包不可用，"
                f"回退到滚动标准差白化。数据质量可能受影响。",
                UserWarning
            )
            self.is_fallback_mode = True
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
                model = _arch_model(
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
        stats['fallback_mode'] = self.is_fallback_mode
        if self._models:
            avg_aic = np.mean([m.aic for m in self._models.values()])
            stats['average_aic'] = avg_aic
        return stats
