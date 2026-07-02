"""
日志系统配置
"""

import logging
import os
from datetime import datetime
from typing import Optional

class FactorNeutralizerLogger:
    """因子中性化日志系统"""
    
    def __init__(self, log_dir: str = 'logs', log_level: str = 'INFO'):
        """
        初始化日志系统
        
        Args:
            log_dir: 日志目录
            log_level: 日志级别
        """
        self.log_dir = log_dir
        self.log_level = getattr(logging, log_level.upper())
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志器"""
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 创建唯一标识的日志器，避免不同实例间冲突
        import uuid
        self._logger_name = f'FactorNeutralizer_{uuid.uuid4().hex[:8]}'
        self.logger = logging.getLogger(self._logger_name)
        self.logger.setLevel(self.log_level)
        
        # 避免重复添加处理器（仅针对当前实例）
        if self.logger.handlers:
            return
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 文件处理器
        log_file = os.path.join(self.log_dir, f'factor_neutralizer_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self._file_handler = file_handler  # 保存引用以便关闭
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self._console_handler = console_handler  # 保存引用以便关闭
    
    def close(self):
        """关闭日志处理器，释放文件句柄"""
        if hasattr(self, '_file_handler'):
            self._file_handler.close()
            self.logger.removeHandler(self._file_handler)
        if hasattr(self, '_console_handler'):
            self._console_handler.close()
            self.logger.removeHandler(self._console_handler)
    
    def __del__(self):
        """析构时关闭处理器"""
        self.close()
    
    def info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """记录错误日志"""
        self.logger.error(message)
    
    def debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)
    
    def critical(self, message: str):
        """记录严重错误日志"""
        self.logger.critical(message)
    
    def log_memory_usage(self, memory_mb: float, stage: str):
        """记录内存使用情况"""
        self.info(f"[内存] {stage}: {memory_mb:.2f} MB")
    
    def log_performance(self, operation: str, duration: float, details: str = ""):
        """记录性能信息"""
        self.info(f"[性能] {operation}: {duration:.2f}秒 {details}")
    
    def log_data_info(self, data_type: str, shape: tuple, file_path: str = ""):
        """记录数据信息"""
        info = f"[数据] {data_type}: 形状{shape}"
        if file_path:
            info += f" 文件: {file_path}"
        self.info(info)
    
    def log_cache_operation(self, operation: str, cache_key: str, success: bool):
        """记录缓存操作"""
        status = "成功" if success else "失败"
        self.info(f"[缓存] {operation}: {cache_key[:8]}... {status}")
    
    def log_neutralization_result(self, factor_name: str, method: str, 
                                processed_dates: int, success: bool):
        """记录中性化结果"""
        status = "成功" if success else "失败"
        self.info(f"[中性化] {factor_name} ({method}): {processed_dates}个交易日 {status}")

# 全局日志实例
_logger_instance: Optional[FactorNeutralizerLogger] = None

def get_logger() -> FactorNeutralizerLogger:
    """获取全局日志实例"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = FactorNeutralizerLogger()
    return _logger_instance

def setup_logger(log_dir: str = 'logs', log_level: str = 'INFO'):
    """设置全局日志"""
    global _logger_instance
    _logger_instance = FactorNeutralizerLogger(log_dir, log_level)
    return _logger_instance
