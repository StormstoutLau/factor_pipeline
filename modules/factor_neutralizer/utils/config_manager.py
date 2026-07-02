"""
配置管理系统
"""

import json
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class DataConfig:
    """数据配置"""
    factor_dir: str
    price_dir: str
    industry_file: str
    index_file: str
    market_value_file: str
    industry_file_type: str = 'auto'
    index_file_type: str = 'auto'
    market_value_file_type: str = 'auto'

@dataclass
class ProcessingConfig:
    """处理配置"""
    neutralization_type: str = 'industry'
    industry_method: str = 'regression'
    force_reprocess: bool = False
    enable_cache: bool = True
    cache_expiry_hours: int = 24

@dataclass
class OptimizationConfig:
    """优化配置"""
    enable_memory_optimization: bool = True
    enable_io_optimization: bool = True
    enable_visualization_optimization: bool = True
    max_industries_display: int = 15
    figure_dpi: int = 150
    batch_size: int = 10

@dataclass
class LoggingConfig:
    """日志配置"""
    log_dir: str = 'logs'
    log_level: str = 'INFO'
    enable_file_logging: bool = True
    enable_console_logging: bool = True

@dataclass
class FactorNeutralizerConfig:
    """完整配置"""
    # 基本配置
    output_dir: str = 'neutralized_results'
    index_code: str = '000001.SH'
    
    # 子配置
    data: DataConfig = None
    processing: ProcessingConfig = None
    optimization: OptimizationConfig = None
    logging: LoggingConfig = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.data is None:
            raise ValueError("数据配置不能为空")
        if self.processing is None:
            self.processing = ProcessingConfig()
        if self.optimization is None:
            self.optimization = OptimizationConfig()
        if self.logging is None:
            self.logging = LoggingConfig()

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file or 'factor_neutralizer_config.json'
        self.config: Optional[FactorNeutralizerConfig] = None
        self.load_config()
    
    def load_config(self) -> FactorNeutralizerConfig:
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_dict = json.load(f)
                
                # 转换为配置对象
                self.config = self._dict_to_config(config_dict)
                print(f"配置已从 {self.config_file} 加载")
                
            except Exception as e:
                print(f"加载配置失败: {e}，使用默认配置")
                self.config = self._get_default_config()
        else:
            print("配置文件不存在，使用默认配置")
            self.config = self._get_default_config()
        
        return self.config
    
    def save_config(self, config: FactorNeutralizerConfig):
        """保存配置"""
        try:
            config_dict = asdict(config)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            print(f"配置已保存到 {self.config_file}")
            
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def _dict_to_config(self, config_dict: Dict[str, Any]) -> FactorNeutralizerConfig:
        """字典转配置对象"""
        # 提取各部分配置
        data_config = DataConfig(**config_dict.get('data', {}))
        processing_config = ProcessingConfig(**config_dict.get('processing', {}))
        optimization_config = OptimizationConfig(**config_dict.get('optimization', {}))
        logging_config = LoggingConfig(**config_dict.get('logging', {}))
        
        # 创建完整配置
        return FactorNeutralizerConfig(
            output_dir=config_dict.get('output_dir', 'neutralized_results'),
            index_code=config_dict.get('index_code', '000001.SH'),
            data=data_config,
            processing=processing_config,
            optimization=optimization_config,
            logging=logging_config
        )
    
    def _get_default_config(self) -> FactorNeutralizerConfig:
        """获取默认配置"""
        return FactorNeutralizerConfig(
            data=DataConfig(
                factor_dir=r'D:\Coding\factor_Neutralizer\factors_input',
                price_dir=r'E:\Ashare_data\market_data\stock_close.pkl',
                industry_file=r'E:\Ashare_data\market_data\industry_mapping.pkl',
                index_file=r'E:\Ashare_data\market_data\index_constituents.pkl',
                market_value_file=r'E:\Ashare_data\market_data\stock_market_value.pkl',
                industry_file_type='pkl',
                index_file_type='pkl',
                market_value_file_type='pkl'
            ),
            processing=ProcessingConfig(),
            optimization=OptimizationConfig(),
            logging=LoggingConfig()
        )
    
    def update_config(self, **kwargs):
        """更新配置"""
        if self.config is None:
            self.load_config()
        
        # 更新配置
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # 保存更新后的配置
        self.save_config(self.config)
    
    def get_config_section(self, section: str):
        """获取配置的某个部分"""
        if self.config is None:
            self.load_config()
        
        return getattr(self.config, section, None)
    
    def validate_config(self) -> bool:
        """验证配置有效性"""
        if self.config is None:
            return False
        
        try:
            # 检查数据路径
            data_config = self.config.data
            
            # 检查因子目录
            if not os.path.exists(data_config.factor_dir):
                print(f"警告: 因子目录不存在: {data_config.factor_dir}")
            
            # 检查价格数据
            if data_config.price_dir.endswith('.pkl'):
                if not os.path.exists(data_config.price_dir):
                    print(f"错误: 价格文件不存在: {data_config.price_dir}")
                    return False
            else:
                if not os.path.exists(data_config.price_dir):
                    print(f"警告: 价格目录不存在: {data_config.price_dir}")
            
            # 检查其他文件
            files_to_check = [
                (data_config.industry_file, '行业文件'),
                (data_config.index_file, '指数文件'),
                (data_config.market_value_file, '市值文件')
            ]
            
            for file_path, file_desc in files_to_check:
                if not os.path.exists(file_path):
                    print(f"警告: {file_desc}不存在: {file_path}")
            
            # 检查输出目录
            if not os.path.exists(self.config.output_dir):
                os.makedirs(self.config.output_dir, exist_ok=True)
                print(f"创建输出目录: {self.config.output_dir}")
            
            return True
            
        except Exception as e:
            print(f"配置验证失败: {e}")
            return False

# 全局配置管理器
_config_manager: Optional[ConfigManager] = None

def get_config_manager(config_file: Optional[str] = None) -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_file)
    return _config_manager

def get_config() -> FactorNeutralizerConfig:
    """获取当前配置"""
    return get_config_manager().config
