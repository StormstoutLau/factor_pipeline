"""
错误处理增强模块
"""

import os
import sys
import traceback
from typing import Optional, Dict, Any, Callable
from functools import wraps
from enum import Enum
from .logger_config import get_logger

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class FactorNeutralizerError(Exception):
    """因子中性化基础异常"""
    
    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM, 
                 error_code: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        """
        初始化异常
        
        Args:
            message: 错误消息
            severity: 错误严重程度
            error_code: 错误代码
            context: 错误上下文信息
        """
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.error_code = error_code
        self.context = context or {}
        self.traceback_str = traceback.format_exc()

class DataLoadError(FactorNeutralizerError):
    """数据加载错误"""
    
    def __init__(self, message: str, file_path: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if file_path:
            context['file_path'] = file_path
        super().__init__(message, ErrorSeverity.HIGH, "DATA_LOAD_ERROR", context)

class ProcessingError(FactorNeutralizerError):
    """处理错误"""
    
    def __init__(self, message: str, factor_name: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if factor_name:
            context['factor_name'] = factor_name
        super().__init__(message, ErrorSeverity.MEDIUM, "PROCESSING_ERROR", context)

class CacheError(FactorNeutralizerError):
    """缓存错误"""
    
    def __init__(self, message: str, cache_key: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if cache_key:
            context['cache_key'] = cache_key
        super().__init__(message, ErrorSeverity.LOW, "CACHE_ERROR", context)

class VisualizationError(FactorNeutralizerError):
    """可视化错误"""
    
    def __init__(self, message: str, factor_name: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if factor_name:
            context['factor_name'] = factor_name
        super().__init__(message, ErrorSeverity.LOW, "VISUALIZATION_ERROR", context)

class ConfigurationError(FactorNeutralizerError):
    """配置错误"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if config_key:
            context['config_key'] = config_key
        super().__init__(message, ErrorSeverity.HIGH, "CONFIGURATION_ERROR", context)

class ErrorHandler:
    """错误处理器"""
    
    def __init__(self):
        """初始化错误处理器"""
        self.logger = get_logger()
        self.error_counts = {}
        self.error_callbacks = {}
    
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        处理错误
        
        Args:
            error: 异常对象
            context: 错误上下文
            
        Returns:
            bool: 是否应该继续执行
        """
        # 记录错误
        self._log_error(error, context)
        
        # 统计错误
        self._count_error(error)
        
        # 执行回调
        self._execute_callbacks(error, context)
        
        # 根据错误严重程度决定是否继续
        if isinstance(error, FactorNeutralizerError):
            return error.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]
        else:
            # 对于未知错误，记录并停止执行
            self.logger.critical(f"未知错误: {error}")
            return False
    
    def _log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """记录错误"""
        if isinstance(error, FactorNeutralizerError):
            self.logger.error(f"[{error.severity.value.upper()}] {error.message}")
            if error.error_code:
                self.logger.error(f"错误代码: {error.error_code}")
            if error.context:
                self.logger.error(f"错误上下文: {error.context}")
            if error.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
                self.logger.error(f"错误堆栈: {error.traceback_str}")
        else:
            self.logger.error(f"未知错误: {error}")
            self.logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        if context:
            self.logger.error(f"附加上下文: {context}")
    
    def _count_error(self, error: Exception):
        """统计错误"""
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # 如果错误次数过多，记录警告
        if self.error_counts[error_type] > 10:
            self.logger.warning(f"错误 {error_type} 已发生 {self.error_counts[error_type]} 次")
    
    def _execute_callbacks(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """执行错误回调"""
        error_type = type(error).__name__
        if error_type in self.error_callbacks:
            try:
                self.error_callbacks[error_type](error, context)
            except Exception as callback_error:
                self.logger.error(f"错误回调执行失败: {callback_error}")
    
    def register_callback(self, error_type: str, callback: Callable):
        """注册错误回调"""
        self.error_callbacks[error_type] = callback
    
    def get_error_statistics(self) -> Dict[str, int]:
        """获取错误统计"""
        return self.error_counts.copy()
    
    def reset_statistics(self):
        """重置错误统计"""
        self.error_counts.clear()

def safe_execute(
    default_return: Any = None,
    reraise: bool = False,
    log_errors: bool = True,
    error_handler: Optional[ErrorHandler] = None
):
    """
    安全执行装饰器
    
    Args:
        default_return: 发生错误时的默认返回值
        reraise: 是否重新抛出异常
        log_errors: 是否记录错误
        error_handler: 错误处理器
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    if error_handler:
                        should_continue = error_handler.handle_error(e, {'function': func.__name__})
                        if not should_continue and not reraise:
                            return default_return
                    else:
                        logger = get_logger()
                        logger.error(f"函数 {func.__name__} 执行失败: {e}")
                
                if reraise:
                    raise
                
                return default_return
        return wrapper
    return decorator

def validate_file_path(file_path: str, must_exist: bool = True) -> bool:
    """
    验证文件路径
    
    Args:
        file_path: 文件路径
        must_exist: 是否必须存在
        
    Returns:
        bool: 是否有效
        
    Raises:
        ConfigurationError: 路径无效
    """
    if not file_path:
        raise ConfigurationError("文件路径不能为空", config_key="file_path")
    
    if must_exist and not os.path.exists(file_path):
        raise ConfigurationError(f"文件不存在: {file_path}", config_key="file_path")
    
    # 检查文件扩展名
    valid_extensions = ['.csv', '.pkl', '.json', '.xlsx', '.xls']
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext not in valid_extensions:
        raise ConfigurationError(
            f"不支持的文件格式: {file_ext}", 
            config_key="file_path",
            context={"valid_extensions": valid_extensions}
        )
    
    return True

def validate_dataframe(df, min_rows: int = 1, min_cols: int = 1, 
                      required_columns: Optional[list] = None) -> bool:
    """
    验证DataFrame
    
    Args:
        df: DataFrame对象
        min_rows: 最小行数
        min_cols: 最小列数
        required_columns: 必需的列
        
    Returns:
        bool: 是否有效
        
    Raises:
        ProcessingError: DataFrame无效
    """
    if df is None:
        raise ProcessingError("DataFrame不能为None")
    
    if not isinstance(df, pd.DataFrame):
        raise ProcessingError(f"期望DataFrame，实际类型: {type(df)}")
    
    if df.empty:
        raise ProcessingError("DataFrame为空")
    
    if len(df) < min_rows:
        raise ProcessingError(f"行数不足: {len(df)} < {min_rows}")
    
    if len(df.columns) < min_cols:
        raise ProcessingError(f"列数不足: {len(df.columns)} < {min_cols}")
    
    if required_columns:
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            raise ProcessingError(
                f"缺少必需列: {missing_cols}",
                context={"required_columns": required_columns, "existing_columns": list(df.columns)}
            )
    
    return True

def create_fallback_data(shape: tuple, data_type: str = "random") -> pd.DataFrame:
    """
    创建回退数据
    
    Args:
        shape: 数据形状
        data_type: 数据类型
        
    Returns:
        pd.DataFrame: 回退数据
    """
    logger = get_logger()
    logger.warning(f"创建回退数据: {shape}, 类型: {data_type}")
    
    if data_type == "random":
        data = np.random.randn(*shape)
    elif data_type == "zeros":
        data = np.zeros(shape)
    elif data_type == "ones":
        data = np.ones(shape)
    else:
        data = np.random.randn(*shape)
    
    # 创建索引和列名
    index = pd.date_range('2023-01-01', periods=shape[0], freq='D')
    columns = [f'COL_{i:06d}' for i in range(shape[1])]
    
    return pd.DataFrame(data, index=index, columns=columns)

# 全局错误处理器
_global_error_handler: Optional[ErrorHandler] = None

def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler

def handle_critical_error(error: Exception, context: Optional[Dict[str, Any]] = None):
    """
    处理严重错误
    
    Args:
        error: 异常对象
        context: 错误上下文
    """
    logger = get_logger()
    error_handler = get_error_handler()
    
    # 记录严重错误
    logger.critical(f"严重错误发生: {error}")
    if context:
        logger.critical(f"错误上下文: {context}")
    
    # 尝试清理资源
    try:
        # 这里可以添加清理逻辑
        pass
    except Exception as cleanup_error:
        logger.error(f"资源清理失败: {cleanup_error}")
    
    # 保存错误信息到文件
    try:
        error_info = {
            'error': str(error),
            'context': context,
            'traceback': traceback.format_exc(),
            'timestamp': pd.Timestamp.now().isoformat()
        }
        
        error_file = f'critical_error_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(error_info, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"错误信息已保存到: {error_file}")
        
    except Exception as save_error:
        logger.error(f"保存错误信息失败: {save_error}")
    
    # 根据错误类型决定是否退出
    if isinstance(error, (ConfigurationError, DataLoadError)):
        logger.critical("配置或数据加载错误，程序退出")
        sys.exit(1)
    else:
        logger.critical("处理错误，程序继续执行")

# 导入pandas用于验证函数
import pandas as pd
import json
