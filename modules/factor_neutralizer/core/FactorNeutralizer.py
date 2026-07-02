"""
修复后的因子中性化批量处理程序
所有错误已修复，专注于核心功能
"""

from __future__ import annotations

# 标准库
import asyncio
import concurrent.futures
import gc
import glob
import hashlib
import json
import logging
import os
import pickle
import threading
import time
import warnings
import zlib
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
from typing import Dict, Optional, Tuple, Union, List, Any

# 第三方库
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False
    import logging
    logging.getLogger(__name__).warning("joblib 未安装，缓存功能将使用 pickle")
try:
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    fm = None
    plt = None
    import logging
    logging.getLogger(__name__).warning("matplotlib 未安装，可视化功能不可用")
import numpy as np
import pandas as pd
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    import logging
    logging.getLogger(__name__).warning("psutil 未安装，内存监控功能不可用")
import statsmodels.api as sm

# 本地模块
from ..utils.logger_config import FactorNeutralizerLogger

# 常量定义
CACHE_EXPIRY_SECONDS = 24 * 60 * 60  # 缓存过期时间: 24小时
JOBLIB_PROTOCOL = 4  # joblib序列化协议版本
JOBLIB_COMPRESS_LEVEL = 3  # zlib压缩级别
FILLNA_VALUE = 0  # 缺失值填充默认值
DUMMY_DROP_FIRST = True  # 哑变量是否丢弃第一列

# 尝试导入 Numba 进行加速
try:
    from numba import jit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    logging.getLogger(__name__).warning("Numba 未安装，将使用纯 NumPy 计算")

# 设置中文字体 - 增强版本

def setup_chinese_font():
    """设置中文字体"""
    if not HAS_MATPLOTLIB:
        return None
    # 检查可用字体
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    # 中文字体优先级列表
    chinese_fonts = [
        'SimHei',           # 黑体 (Windows)
        'Microsoft YaHei',  # 微软雅黑 (Windows)
        'Arial Unicode MS', # Arial Unicode (跨平台)
        'DejaVu Sans',      # DejaVu (跨平台)
        'WenQuanYi Zen Hei', # 文泉驿正黑 (Linux)
        'Noto Sans CJK SC', # 思源黑体 (跨平台)
        'PingFang SC',      # 苹方 (macOS)
        'Hiragino Sans GB'  # 冬青黑体 (macOS)
    ]
    
    # 选择第一个可用字体
    selected_font = None
    for font in chinese_fonts:
        if font in available_fonts:
            selected_font = font
            break
    
    if selected_font:
        plt.rcParams['font.sans-serif'] = [selected_font] + [f for f in chinese_fonts if f != selected_font]
    else:
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
    
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['font.size'] = 10
    
    return selected_font

class FactorNeutralizer:
    """优化后的因子中性化处理器"""
    
    def __init__(self,
                 factor_dir: str,
                 price_dir: str,
                 industry_file: str,
                 index_file: str,
                 market_value_file: str,
                 output_dir: str = 'neutralized_factors',
                 index_code: str = '000001.SH',
                 enable_cache: bool = True,
                 industry_file_type: str = 'auto',
                 index_file_type: str = 'auto',
                 market_value_file_type: str = 'auto'):
        """
        初始化中性化处理器
        
        参数:
        factor_dir: 因子数据目录
        price_dir: 价格数据目录
        industry_file: 行业映射文件
        index_file: 指数成分股文件
        market_value_file: 市值数据文件
        output_dir: 输出目录
        index_code: 指数代码，默认为上证指数
        enable_cache: 是否启用缓存机制
        industry_file_type: 行业文件类型 ('csv', 'pkl', 'auto')
        index_file_type: 指数文件类型 ('csv', 'pkl', 'auto')
        market_value_file_type: 市值文件类型 ('csv', 'pkl', 'auto')
        """
        # 初始化日志系统（在数据加载之前）
        self.logger = FactorNeutralizerLogger(log_dir=os.path.join(output_dir, 'logs'))
        
        self.factor_dir = factor_dir
        self.price_dir = price_dir
        self.industry_file = industry_file
        self.index_file = index_file
        self.market_value_file = market_value_file
        self.output_dir = output_dir
        self.index_code = index_code
        self.enable_cache = enable_cache
        
        # 文件类型配置
        self.industry_file_type = industry_file_type
        self.index_file_type = index_file_type
        self.market_value_file_type = market_value_file_type
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'factors'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'visualizations'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'analysis'), exist_ok=True)
        
        # 缓存目录
        if self.enable_cache:
            self.cache_dir = os.path.join(output_dir, '.cache')
            os.makedirs(self.cache_dir, exist_ok=True)
            self._cache_lock = threading.Lock()
        
        # 数据容器
        self.factors = {}
        self.price_data = None
        self.industry_data = None
        self.index_data = None
        self.market_value_data = None
        
        # 中性化结果
        self.neutralized_factors = {}
        self.analysis_results = {}
        
        # 设置中文字体（延迟到实例化时）
        selected_font = setup_chinese_font()
        if selected_font:
            self.logger.info(f"使用中文字体: {selected_font}")
        else:
            self.logger.warning("未找到合适的中文字体，可能出现中文乱码")
        
        # 加载数据
        self.load_data()
    
    def _format_stock_code(self, code) -> str:
        """根据股票代码规则添加正确的交易所后缀
        
        规则:
        - 60/68/51/52/53 开头 -> .SH (沪市)
        - 00/30/15/16 开头 -> .SZ (深市)
        - 8/4/43 开头 -> .BJ (北交所)
        - 已有后缀 -> 保持不变
        """
        if isinstance(code, str) and '.' in code:
            return code
        
        code_str = str(code).zfill(6)
        if code_str.startswith(('60', '68', '51', '52', '53')):
            return f"{code_str}.SH"
        elif code_str.startswith(('00', '30', '15', '16')):
            return f"{code_str}.SZ"
        elif code_str.startswith(('8', '4', '43')):
            return f"{code_str}.BJ"
        return code_str
    
    def _optimize_memory_usage(self, df: pd.DataFrame) -> pd.DataFrame:
        """优化DataFrame内存使用"""
        if df.empty:
            return df
        
        # 转换数值列为更高效的数据类型
        for col in df.select_dtypes(include=['float64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='float')
        
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
        
        # 转换对象列为category类型（如果唯一值较少）
        for col in df.select_dtypes(include=['object', 'str']).columns:
            if df[col].nunique() / len(df) < 0.5:  # 如果唯一值比例小于50%
                df[col] = df[col].astype('category')
        
        return df
    
    def _get_memory_usage(self) -> Dict[str, float]:
        """获取当前内存使用情况"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024
        }
    
    def _cleanup_memory(self) -> None:
        """清理内存"""
        gc.collect()
    
    def _detect_file_type(self, file_path: str) -> str:
        """自动检测文件类型"""
        if not os.path.exists(file_path):
            return 'csv'  # 默认返回csv
        
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext[1:] if file_ext else 'csv'  # 去掉点号
    
    def _load_file_by_type(self, file_path: str, file_type: str, **kwargs) -> Any:
        """根据文件类型加载数据（失败时抛出异常）"""
        if file_type == 'auto':
            file_type = self._detect_file_type(file_path)
        
        if file_type == 'pkl':
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        elif file_type == 'csv':
            return pd.read_csv(file_path, **kwargs)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")
    
    def _get_cache_key(self, data_type: str, **kwargs) -> str:
        """生成缓存键（使用SHA256 + JSON序列化，避免冲突）"""
        key_dict = {
            'data_type': data_type,
            'factor_dir': self.factor_dir,
            'price_dir': self.price_dir,
            'industry_file': self.industry_file,
            **kwargs
        }
        # 使用JSON序列化确保唯一性，避免字符串拼接导致的冲突
        key_json = json.dumps(key_dict, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(key_json.encode()).hexdigest()[:32]
    
    def _get_cache_path(self, cache_key: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{cache_key}.pkl")
    
    def _save_to_cache(self, cache_key: str, data: Any) -> None:
        """保存数据到缓存（快速序列化）"""
        if not self.enable_cache:
            return
        
        cache_path = self._get_cache_path(cache_key)
        try:
            with self._cache_lock:
                cached_data = {
                    'data': data,
                    'timestamp': time.time()
                }
                # 使用joblib进行快速序列化，并压缩
                joblib.dump(cached_data, cache_path, protocol=JOBLIB_PROTOCOL, compress=('zlib', JOBLIB_COMPRESS_LEVEL))
        except Exception as e:
            self.logger.error(f"缓存保存失败: {e}")
    
    def _load_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存加载数据（快速序列化）"""
        if not self.enable_cache:
            return None
        
        cache_path = self._get_cache_path(cache_key)
        if os.path.exists(cache_path):
            try:
                with self._cache_lock:
                    cached_data = joblib.load(cache_path)
                    # 检查缓存是否过期 (24小时)
                    if time.time() - cached_data['timestamp'] < CACHE_EXPIRY_SECONDS:
                        self.logger.info(f"从缓存加载: {cache_key[:8]}...")
                        return cached_data['data']
            except Exception as e:
                self.logger.error(f"缓存加载失败: {e}")
        return None
    
    def _fast_save_factor(self, factor_data: pd.DataFrame, output_path: str) -> None:
        """快速保存因子数据"""
        try:
            # 使用joblib进行快速序列化
            joblib.dump(factor_data, output_path, protocol=JOBLIB_PROTOCOL, compress=('zlib', JOBLIB_COMPRESS_LEVEL))
        except Exception as e:
            # 回退到标准pickle
            with open(output_path, 'wb') as f:
                pickle.dump(factor_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    def _fast_load_factor(self, file_path: str) -> Any:
        """快速加载因子数据（确保文件句柄正确关闭）"""
        try:
            # 使用joblib进行快速加载
            return joblib.load(file_path)
        except Exception:
            # 回退到标准pickle，使用with语句确保文件句柄关闭
            with open(file_path, 'rb') as f:
                return pickle.load(f)
    
    def _clear_cache(self) -> None:
        """清理缓存"""
        if not self.enable_cache:
            return
        
        try:
            with self._cache_lock:
                for file in glob.glob(os.path.join(self.cache_dir, "*.pkl")):
                    os.remove(file)
            self.logger.info("缓存已清理")
        except Exception as e:
            self.logger.error(f"缓存清理失败: {e}")
    
    def load_data(self) -> None:
        """并行加载所有数据（带缓存）"""
        self.logger.info("="*60)
        self.logger.info("开始并行加载数据...")
        self.logger.info("="*60)
        
        # 检查整体数据缓存
        data_cache_key = self._get_cache_key('all_data', 
                                            factor_dir=self.factor_dir,
                                            price_dir=self.price_dir,
                                            industry_file=self.industry_file,
                                            index_file=self.index_file,
                                            market_value_file=self.market_value_file)
        
        cached_data = self._load_from_cache(data_cache_key)
        if cached_data:
            self.price_data = cached_data['price_data']
            self.factors = cached_data['factors']
            self.industry_data = cached_data['industry_data']
            self.index_data = cached_data['index_data']
            self.market_value_data = cached_data['market_value_data']
            self.logger.info("从缓存加载所有数据完成!")
            return
        
        # 使用线程池并行加载数据
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 提交所有加载任务
            futures = {
                'price': executor.submit(self._load_price_data),
                'factors': executor.submit(self._load_factor_data),
                'industry': executor.submit(self._load_industry_data),
                'index': executor.submit(self._load_index_data),
                'market_value': executor.submit(self._load_market_value_data)
            }
            
            # 等待所有任务完成并获取结果
            for data_type, future in futures.items():
                try:
                    result = future.result()
                    if data_type == 'price':
                        self.price_data = result
                    elif data_type == 'factors':
                        self.factors = result
                    elif data_type == 'industry':
                        self.industry_data = result
                    elif data_type == 'index':
                        self.index_data = result
                    elif data_type == 'market_value':
                        self.market_value_data = result
                except Exception as e:
                    self.logger.error(f"加载 {data_type} 数据失败: {e}")
                    if data_type == 'price':
                        raise FileNotFoundError(f"价格数据加载失败: {e}")
                    elif data_type == 'industry':
                        raise FileNotFoundError(f"行业数据加载失败: {e}")
                    elif data_type == 'factors':
                        raise FileNotFoundError(f"因子数据加载失败: {e}")
        
        # 保存到缓存
        data_to_cache = {
            'price_data': self.price_data,
            'factors': self.factors,
            'industry_data': self.industry_data,
            'index_data': self.index_data,
            'market_value_data': self.market_value_data
        }
        self._save_to_cache(data_cache_key, data_to_cache)
        
        self.logger.info("="*60)
        self.logger.info("并行数据加载完成!")
        self.logger.info("="*60)
    
    def _load_price_data(self) -> pd.DataFrame:
        """加载价格数据（支持CSV和PKL格式，内存优化）"""
        self.logger.info("1. 加载价格数据...")
        
        # 记录初始内存
        initial_memory = self._get_memory_usage()
        self.logger.debug(f"初始内存: {initial_memory['rss_mb']:.2f} MB")
        
        # 优先尝试PKL文件
        pkl_file = os.path.join(self.price_dir, "stock_close.pkl")
        if os.path.exists(pkl_file):
            try:
                price_data = self._load_file_by_type(pkl_file, 'pkl')
                if isinstance(price_data, pd.DataFrame):
                    # 确保索引是日期格式
                    if price_data.index.name == 'trade_date':
                        price_data.index = pd.to_datetime(price_data.index)
                    
                    # 检查并处理列名格式
                    if len(price_data.columns) > 0:
                        first_col = price_data.columns[0]
                        # 如果列名是ts_code格式，保持不变
                        # 如果是数字格式，可能需要添加交易所后缀
                        if isinstance(first_col, str) and first_col.isdigit():
                            self.logger.info("检测到数字股票代码格式，添加交易所后缀...")
                            new_columns = []
                            for col in price_data.columns:
                                new_columns.append(self._format_stock_code(col))
                            price_data.columns = new_columns
                    
                    # 内存优化
                    price_data = self._optimize_memory_usage(price_data)
                    
                    self.logger.info(f"价格数据(PKL)加载完成，形状: {price_data.shape}")
                    self.logger.info(f"时间范围: {price_data.index[0]} 到 {price_data.index[-1]}")
                    
                    # 记录加载后内存
                    loaded_memory = self._get_memory_usage()
                    self.logger.debug(f"加载后内存: {loaded_memory['rss_mb']:.2f} MB (+{loaded_memory['rss_mb']-initial_memory['rss_mb']:.2f} MB)")
                    
                    return price_data
            except Exception as e:
                self.logger.error(f"PKL文件加载失败: {e}")
        
        # 回退到CSV文件
        csv_files = glob.glob(os.path.join(self.price_dir, "*.csv"))
        if csv_files:
            try:
                price_data = pd.read_csv(csv_files[0], index_col=0, parse_dates=True)
                # 内存优化
                price_data = self._optimize_memory_usage(price_data)
                
                self.logger.info(f"价格数据(CSV)加载完成，形状: {price_data.shape}")
                return price_data
            except Exception as e:
                self.logger.error(f"CSV文件加载失败: {e}")
        
        # 如果都失败了，检查是否price_dir直接指向pkl文件
        if self.price_dir.endswith('.pkl') and os.path.exists(self.price_dir):
            try:
                price_data = self._load_file_by_type(self.price_dir, 'pkl')
                if isinstance(price_data, pd.DataFrame):
                    if price_data.index.name == 'trade_date':
                        price_data.index = pd.to_datetime(price_data.index)
                    # 内存优化
                    price_data = self._optimize_memory_usage(price_data)
                    
                    self.logger.info(f"价格数据(直接PKL)加载完成，形状: {price_data.shape}")
                    return price_data
            except Exception as e:
                self.logger.error(f"直接PKL文件加载失败: {e}")
        
        raise FileNotFoundError(f"在目录 {self.price_dir} 中未找到有效的价格数据文件")
    
    def _load_factor_data(self) -> Dict[str, pd.DataFrame]:
        """并行加载因子数据"""
        self.logger.info("2. 并行加载因子数据...")
        factor_files = glob.glob(os.path.join(self.factor_dir, "*.pkl"))
        if not factor_files:
            raise FileNotFoundError(f"在目录 {self.factor_dir} 中未找到因子数据")
        
        factors = {}
        
        def load_single_factor(factor_file):
            """加载单个因子文件"""
            factor_name = os.path.basename(factor_file).replace('.pkl', '')
            try:
                with open(factor_file, 'rb') as f:
                    factor_data = pickle.load(f)
                return factor_name, factor_data, None
            except Exception as e:
                return factor_name, None, e
        
        # 使用线程池并行加载因子文件
        with ThreadPoolExecutor(max_workers=min(8, len(factor_files))) as executor:
            futures = [executor.submit(load_single_factor, f) for f in factor_files]
            
            for future in futures:
                factor_name, factor_data, error = future.result()
                if error:
                    self.logger.error(f"加载因子 '{factor_name}' 失败: {error}")
                    continue
                
                # 确保与价格数据时间对齐
                if self.price_data is not None:
                    common_idx = factor_data.index.intersection(self.price_data.index)
                    factor_data = factor_data.loc[common_idx]
                    
                    # 只保留价格数据中存在的股票
                    common_cols = factor_data.columns.intersection(self.price_data.columns)
                    factor_data = factor_data[common_cols]
                    
                    # 统一股票代码格式：添加交易所后缀
                    new_columns = []
                    for col in factor_data.columns:
                        new_columns.append(self._format_stock_code(col))
                    
                    factor_data.columns = new_columns
                
                if not factor_data.empty:
                    factors[factor_name] = factor_data
                    self.logger.debug(f"因子 '{factor_name}' 加载完成，形状: {factor_data.shape}")
                else:
                    self.logger.warning(f"因子 '{factor_name}' 数据为空或与价格数据无交集")
        
        self.logger.info(f"共加载 {len(factors)} 个因子")
        return factors
    
    def _load_industry_data(self) -> pd.Series:
        """加载行业数据"""
        self.logger.info("3. 加载行业数据...")
        try:
            # 使用新的文件类型检测方法
            industry_data = self._load_file_by_type(
                self.industry_file, 
                self.industry_file_type,
                sep=',', 
                dtype={'证券代码': str}
            )
            
            if industry_data is None:
                raise RuntimeError("文件加载失败")
            
            # 处理不同格式的行业数据
            if isinstance(industry_data, pd.DataFrame):
                if '证券代码' in industry_data.columns and '所属申万行业' in industry_data.columns:
                    industry_data = industry_data.set_index('证券代码')['所属申万行业']
                elif 'code' in industry_data.columns and 'industry' in industry_data.columns:
                    industry_data = industry_data.set_index('code')['industry']
                elif len(industry_data.columns) >= 2:
                    # 尝试使用前两列
                    industry_data = industry_data.set_index(industry_data.columns[0])[industry_data.columns[1]]
                else:
                    raise ValueError("无法识别行业数据格式")
            elif isinstance(industry_data, pd.Series):
                # 已经是Series格式，直接使用
                pass
            else:
                raise ValueError("不支持的数据格式")
            
            self.logger.info(f"行业数据加载完成，股票数量: {len(industry_data)}")
            return industry_data
            
        except Exception as e:
            self.logger.error(f"加载行业数据失败: {e}")
            # 不再生成模拟数据，而是明确报错
            raise FileNotFoundError(
                f"行业数据加载失败: {e}. 请检查文件路径: {self.industry_file}"
            )
    
    def _load_index_data(self) -> Optional[pd.DataFrame]:
        """加载指数成分股数据"""
        self.logger.info("4. 加载指数成分股数据...")
        try:
            # 使用新的文件类型检测方法
            index_data = self._load_file_by_type(self.index_file, self.index_file_type)
            
            if index_data is None:
                raise RuntimeError("文件加载失败")
            
            if isinstance(index_data, pd.DataFrame):
                if 'index_code' in index_data.columns:
                    index_data = index_data[index_data['index_code'] == self.index_code]
                if 'trade_date' in index_data.columns:
                    index_data['trade_date'] = pd.to_datetime(index_data['trade_date'], format='%Y%m%d')
                self.logger.info(f"指数 '{self.index_code}' 数据加载完成，记录数: {len(index_data)}")
                return index_data
            else:
                raise ValueError("指数数据格式不正确")
        except Exception as e:
            self.logger.error(f"加载指数成分股数据失败: {e}")
            return None
    
    def _load_market_value_data(self) -> Optional[pd.DataFrame]:
        """加载市值数据"""
        self.logger.info("5. 加载市值数据...")
        try:
            # 使用新的文件类型检测方法
            market_value_data = self._load_file_by_type(
                self.market_value_file, 
                self.market_value_file_type,
                index_col=0
            )
            
            if market_value_data is None:
                raise RuntimeError("文件加载失败")
            
            if isinstance(market_value_data, pd.DataFrame):
                # 尝试多种日期格式
                date_formats = ['%Y/%m/%d', '%Y-%m-%d', '%Y%m%d']
                for fmt in date_formats:
                    try:
                        market_value_data.index = pd.to_datetime(market_value_data.index, format=fmt)
                        self.logger.info(f"市值数据日期格式解析成功: {fmt}")
                        break
                    except:
                        continue
                else:
                    market_value_data.index = pd.to_datetime(market_value_data.index, infer_datetime_format=True)
                    self.logger.info("市值数据日期格式自动解析成功")
                
                # 将列名转换为完整股票代码（根据代码规则判断交易所）
                new_columns = []
                for col in market_value_data.columns:
                    new_columns.append(self._format_stock_code(col))
                market_value_data.columns = new_columns
                
                self.logger.info(f"市值数据加载完成，形状: {market_value_data.shape}")
                return market_value_data
            else:
                raise ValueError("市值数据格式不正确")
        except Exception as e:
            self.logger.error(f"加载市值数据失败: {e}")
            return None
    
    def industry_neutralization(self, factor_data: pd.DataFrame, method: str = 'regression') -> pd.DataFrame:
        """向量化行业中性化（带缓存）"""
        if self.industry_data is None:
            self.logger.warning("无行业数据，跳过行业中性化")
            return factor_data
        
        self.logger.info(f"开始向量化行业中性化，方法: {method}")
        
        # 筛选共同股票
        common_symbols = factor_data.columns.intersection(self.industry_data.index)
        if len(common_symbols) < 10:
            self.logger.warning("共同股票数量不足，跳过行业中性化")
            return factor_data
        
        factor_data_aligned = factor_data[common_symbols]
        industry_series = self.industry_data[common_symbols]
        
        # 生成缓存键
        factor_hash = hashlib.md5(pd.util.hash_pandas_object(factor_data_aligned).values).hexdigest()
        industry_hash = hashlib.md5(pd.util.hash_pandas_object(industry_series).values).hexdigest()
        cache_key = self._get_cache_key('industry_neutralization', 
                                      method=method, 
                                      factor_hash=factor_hash,
                                      industry_hash=industry_hash)
        
        # 尝试从缓存加载
        cached_result = self._load_from_cache(cache_key)
        if cached_result is not None:
            self.logger.info("从缓存加载行业中性化结果")
            # 重新对齐到原始因子数据格式
            result_aligned = pd.DataFrame(index=factor_data.index, columns=factor_data.columns, dtype=float)
            result_aligned[common_symbols] = cached_result
            return result_aligned.ffill().bfill()
        
        # 执行中性化计算
        if method == 'regression':
            result = self._vectorized_industry_regression(factor_data_aligned, industry_series)
        elif method == 'standardization':
            result = self._vectorized_industry_standardization(factor_data_aligned, industry_series)
        else:
            self.logger.warning(f"中性化方法 {method} 暂未实现")
            return factor_data_aligned
        
        # 保存到缓存
        self._save_to_cache(cache_key, result)
        
        # 重新对齐到原始因子数据格式
        result_aligned = pd.DataFrame(index=factor_data.index, columns=factor_data.columns, dtype=float)
        result_aligned[common_symbols] = result
        
        return result_aligned.ffill().bfill()
    
    def _vectorized_industry_regression(self, factor_data: pd.DataFrame, industry_series: pd.Series) -> pd.DataFrame:
        """向量化行业回归中性化（内存优化版 + 索引安全）"""
        self.logger.info("执行向量化行业回归...")
        
        # 创建行业哑变量矩阵 (一次性创建)
        industry_dummies = pd.get_dummies(industry_series, drop_first=DUMMY_DROP_FIRST)
        industry_dummies = sm.add_constant(industry_dummies)  # 添加常数项
        
        # 确保数据类型为float并优化内存
        industry_dummies = industry_dummies.astype(np.float32)
        factor_data = factor_data.astype(np.float32)
        
        # 向量化计算：对每个交易日进行矩阵运算
        neutralized_factor = pd.DataFrame(
            index=factor_data.index,
            columns=factor_data.columns,
            dtype=np.float32
        )
        
        valid_dates = []
        for date in factor_data.index:
            date_factor = factor_data.loc[date].dropna()
            if len(date_factor) < 10:
                continue
            
            # Bug-008 修复: 使用交集确保索引安全，避免 KeyError
            valid_symbols = date_factor.index.intersection(industry_dummies.index)
            if len(valid_symbols) < 5:
                continue
            
            # 获取对应日期的行业哑变量
            X = industry_dummies.loc[valid_symbols]
            y = date_factor.loc[valid_symbols].values
            
            # 移除NaN值
            valid_mask = ~(np.isnan(y) | np.isnan(X).any(axis=1))
            if valid_mask.sum() < 5:
                continue
                
            X_clean = X[valid_mask]
            y_clean = y[valid_mask]
            
            try:
                # 使用伪逆矩阵进行向量化回归计算
                if NUMBA_AVAILABLE and len(y_clean) > 50:
                    # 大数据量时使用Numba加速
                    residuals = self._fast_regression(X_clean.values, y_clean)
                else:
                    X_pinv = np.linalg.pinv(X_clean.values)
                    beta = X_pinv @ y_clean
                    residuals = y_clean - X_clean.values @ beta
                
                # 将残差赋值给对应股票
                valid_symbols_clean = valid_symbols[valid_mask]
                neutralized_factor.loc[date, valid_symbols_clean] = residuals
                valid_dates.append(date)
                
                # 及时清理临时变量
                del X_clean, y_clean, residuals
                if not NUMBA_AVAILABLE or len(y_clean) <= 50:
                    del X_pinv, beta
                
            except Exception as e:
                self.logger.error(f"日期 {date} 向量化回归失败: {e}")
                continue
        
        # 清理大型临时变量
        del industry_dummies
        
        self.logger.info(f"向量化行业回归完成，处理日期数: {len(valid_dates)}")
        
        # 填充缺失值
        neutralized_factor = neutralized_factor.ffill().bfill()
        
        # 强制垃圾回收
        self._cleanup_memory()
        
        return neutralized_factor
    
    def _fast_regression(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """使用Numba加速的回归残差计算（回退到NumPy）"""
        # 纯NumPy实现，避免Numba编译开销
        X_pinv = np.linalg.pinv(X)
        beta = X_pinv @ y
        residuals = y - X @ beta
        return residuals
    
    def _vectorized_industry_standardization(self, factor_data: pd.DataFrame, industry_series: pd.Series) -> pd.DataFrame:
        """向量化行业标准化中性化"""
        self.logger.info("执行向量化行业标准化...")
        
        neutralized_factor = pd.DataFrame(
            index=factor_data.index,
            columns=factor_data.columns,
            dtype=float
        )
        
        # 按行业分组进行向量化标准化
        for industry in industry_series.unique():
            industry_symbols = industry_series[industry_series == industry].index
            industry_data = factor_data[industry_symbols]
            
            if len(industry_symbols) <= 1:
                continue
            
            # 向量化标准化：整个行业矩阵同时计算
            industry_mean = industry_data.mean(axis=1)
            industry_std = industry_data.std(axis=1)
            
            # 避免除零错误
            valid_mask = industry_std > 1e-8
            if valid_mask.any():
                # 标准化计算
                standardized = (industry_data.subtract(industry_mean, axis=0)).divide(industry_std, axis=0)
                # 只对有效日期赋值
                standardized.loc[~valid_mask] = 0  # 无效日期设为0
                neutralized_factor[industry_symbols] = standardized
        
        self.logger.info("向量化行业标准化完成")
        
        # 填充缺失值
        neutralized_factor = neutralized_factor.ffill().bfill()
        
        return neutralized_factor
    
    def _batch_save_factors(self, factors_dict: Dict[str, pd.DataFrame], base_dir: str) -> int:
        """批量保存因子数据（I/O优化 - 快速序列化）"""
        self.logger.info(f"批量保存 {len(factors_dict)} 个因子到 {base_dir}")
        
        # 准备所有要保存的数据
        save_tasks = []
        for factor_name, factor_data in factors_dict.items():
            output_path = os.path.join(base_dir, f'{factor_name}_neutralized.pkl')
            save_tasks.append((output_path, factor_data))
        
        # 批量写入（使用快速序列化）
        saved_count = 0
        for output_path, factor_data in save_tasks:
            try:
                self._fast_save_factor(factor_data, output_path)
                saved_count += 1
            except Exception as e:
                self.logger.error(f"保存因子失败，回退到标准方法: {e}")
                # 回退到标准方法
                try:
                    with open(output_path, 'wb') as f:
                        pickle.dump(factor_data, f, protocol=pickle.HIGHEST_PROTOCOL)
                    saved_count += 1
                except Exception as e2:
                    self.logger.error(f"保存因子 {factor_name} 最终失败: {e2}")
        
        self.logger.info(f"批量保存完成，成功保存 {saved_count}/{len(save_tasks)} 个因子")
        return saved_count
    
    def _batch_load_factors(self, factor_dir: str) -> Dict[str, pd.DataFrame]:
        """批量加载因子数据（I/O优化 - 快速序列化）"""
        self.logger.info(f"批量加载因子数据从 {factor_dir}")
        
        factor_files = glob.glob(os.path.join(factor_dir, "*.pkl"))
        if not factor_files:
            return {}
        
        factors = {}
        loaded_count = 0
        
        # 批量读取（使用快速序列化）
        for factor_file in factor_files:
            factor_name = os.path.basename(factor_file).replace('.pkl', '').replace('_neutralized', '')
            try:
                factor_data = self._fast_load_factor(factor_file)
                factors[factor_name] = factor_data
                loaded_count += 1
            except Exception as e:
                self.logger.error(f"快速加载失败，回退到标准方法: {e}")
                # 回退到标准方法
                try:
                    with open(factor_file, 'rb') as f:
                        factor_data = pickle.load(f)
                    factors[factor_name] = factor_data
                    loaded_count += 1
                except Exception as e2:
                    self.logger.error(f"加载因子 {factor_name} 最终失败: {e2}")
        
        self.logger.info(f"批量加载完成，成功加载 {loaded_count}/{len(factor_files)} 个因子")
        return factors
    
    def process_all_factors(self,
                           neutralization_type: str = 'industry',
                           industry_method: str = 'regression',
                           force_reprocess: bool = False) -> None:
        """处理所有因子（I/O优化版）"""
        self.logger.info("="*60)
        self.logger.info(f"开始批量处理所有因子，中性化类型: {neutralization_type}")
        self.logger.info(f"强制重新处理: {force_reprocess}")
        self.logger.info("="*60)
        
        # 记录处理开始时的内存
        start_memory = self._get_memory_usage()
        self.logger.debug(f"处理开始内存: {start_memory['rss_mb']:.2f} MB")
        
        factors_to_process = {}
        
        for factor_name, factor_data in self.factors.items():
            self.logger.info(f"处理因子: {factor_name}")
            self.logger.info("-" * 40)
            
            # 使用局部变量控制当前因子的重新处理行为
            should_reprocess = force_reprocess
            
            try:
                # 检查是否已存在处理结果
                output_path = os.path.join(self.output_dir, 'factors', f'{factor_name}_neutralized.pkl')
                
                if not should_reprocess and os.path.exists(output_path):
                    self.logger.info(f"因子 {factor_name} 已存在处理结果，跳过处理")
                    # 加载已存在的结果到内存
                    try:
                        with open(output_path, 'rb') as f:
                            existing_data = pickle.load(f)
                        self.neutralized_factors[factor_name] = existing_data
                        self.logger.info(f"已加载因子 {factor_name} 的现有结果")
                    except Exception as e:
                        self.logger.error(f"加载现有结果失败: {e}，将重新处理")
                        should_reprocess = True
                
                if should_reprocess or not os.path.exists(output_path):
                    if neutralization_type == 'industry':
                        # 仅行业中性化
                        neutralized = self.industry_neutralization(factor_data, industry_method)
                    else:
                        self.logger.warning(f"中性化类型 {neutralization_type} 暂未实现")
                        continue
                    
                    # 存储到临时字典中，稍后批量保存
                    factors_to_process[factor_name] = neutralized
                    self.neutralized_factors[factor_name] = neutralized
                    
                    self.logger.info(f"因子 {factor_name} 处理完成")
                
            except Exception as e:
                self.logger.error(f"处理因子 {factor_name} 时出错: {e}")
                continue
        
        # 批量保存处理完成的因子
        if factors_to_process:
            self._batch_save_factors(factors_to_process, os.path.join(self.output_dir, 'factors'))
            # 清理临时字典
            del factors_to_process
            self._cleanup_memory()
        
        # 记录处理结束时的内存
        end_memory = self._get_memory_usage()
        self.logger.debug(f"处理结束内存: {end_memory['rss_mb']:.2f} MB (+{end_memory['rss_mb']-start_memory['rss_mb']:.2f} MB)")
        
        self.logger.info("="*60)
        self.logger.info("批量处理完成!")
        self.logger.info("="*60)
    
    def rotation_analysis(self) -> None:
        """行业/市值/指数轮动分析"""
        self.logger.info("="*60)
        self.logger.info("开始轮动分析...")
        self.logger.info("="*60)
        
        if not self.neutralized_factors:
            self.logger.warning("无中性化后的因子数据，跳过轮动分析")
            return
        
        # 1. 行业轮动分析
        if self.industry_data is not None:
            self._industry_rotation_analysis()
        
        # 2. 市值轮动分析
        if self.market_value_data is not None:
            self._market_value_rotation_analysis()
        
        self.logger.info("轮动分析完成")
    
    def _industry_rotation_analysis(self) -> None:
        """行业轮动分析"""
        self.logger.info("进行行业轮动分析...")
        
        # 按季度分析行业暴露变化
        industry_rotation_results = {}
        
        for factor_name, factor_data in self.neutralized_factors.items():
            try:
                # 按季度重采样
                quarterly_data = factor_data.resample('QE').last()
                
                industry_exposure_by_quarter = {}
                
                for quarter_end in quarterly_data.index:
                    try:
                        # 检查日期是否在因子数据中存在
                        if quarter_end not in factor_data.index:
                            continue
                            
                        factor_values = factor_data.loc[quarter_end].dropna()
                        
                        # 对齐行业数据
                        common_symbols = factor_values.index.intersection(self.industry_data.index)
                        if len(common_symbols) < 10:
                            continue
                        
                        factor_aligned = factor_values[common_symbols]
                        industry_aligned = self.industry_data[common_symbols]
                        
                        # 计算每个行业的平均因子值
                        industry_exposure = {}
                        for industry in industry_aligned.unique():
                            industry_symbols = industry_aligned[industry_aligned == industry].index
                            industry_mean = factor_aligned[industry_symbols].mean()
                            
                            if not pd.isna(industry_mean):
                                industry_exposure[industry] = float(industry_mean)  # 确保转换为float
                        
                        if industry_exposure:
                            industry_exposure_by_quarter[quarter_end] = industry_exposure
                    except Exception as e:
                        self.logger.error(f"处理季度 {quarter_end} 时出错: {e}")
                        continue
                
                industry_rotation_results[factor_name] = industry_exposure_by_quarter
                
            except Exception as e:
                self.logger.error(f"处理因子 {factor_name} 的行业轮动分析时出错: {e}")
                continue
        
        # 可视化行业轮动
        try:
            self._visualize_industry_rotation(industry_rotation_results)
        except Exception as e:
            self.logger.error(f"行业轮动可视化时出错: {e}")
        
        # 保存结果
        try:
            output_path = os.path.join(self.output_dir, 'analysis', 'industry_rotation.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                # 转换为可序列化格式
                serializable_results = {}
                for factor_name, quarterly_data in industry_rotation_results.items():
                    serializable_results[factor_name] = {
                        str(date): exposure for date, exposure in quarterly_data.items()
                    }
                
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"行业轮动分析结果保存到: {output_path}")
        except Exception as e:
            self.logger.error(f"保存行业轮动结果时出错: {e}")
    
    def _save_figure_sync(self, fig: plt.Figure, output_path: str, dpi: int = 150) -> Tuple[bool, Optional[str]]:
        """同步保存图片（供线程池调用）"""
        try:
            fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
            plt.close(fig)
            return True, None
        except Exception as e:
            plt.close(fig)
            return False, str(e)
    
    def _batch_save_figures(self, figure_tasks: List[Tuple[plt.Figure, str, int]]) -> None:
        """批量异步保存图片（单一层级线程池，避免嵌套）"""
        if not figure_tasks:
            return
        
        self.logger.info(f"批量异步保存 {len(figure_tasks)} 个图片")
        
        with ThreadPoolExecutor(max_workers=min(4, len(figure_tasks))) as executor:
            futures = []
            for fig, output_path, dpi in figure_tasks:
                future = executor.submit(self._save_figure_sync, fig, output_path, dpi)
                futures.append(future)
            
            # 等待所有保存完成
            for future in concurrent.futures.as_completed(futures):
                try:
                    success, error = future.result()
                    if success:
                        self.logger.info("图片保存成功")
                    else:
                        self.logger.error(f"图片保存失败: {error}")
                except Exception as e:
                    self.logger.error(f"批量保存中出错: {e}")
        
        self.logger.info("批量异步保存完成")
    
    def _visualize_industry_rotation(self, industry_rotation_results: Dict[str, Dict]) -> None:
        """可视化行业轮动（优化版 - 减少图形复杂度）"""
        for factor_name, quarterly_data in industry_rotation_results.items():
            if not quarterly_data:
                continue
            
            # 提取所有行业
            all_industries = set()
            for exposure_dict in quarterly_data.values():
                all_industries.update(exposure_dict.keys())
            
            all_industries = sorted(list(all_industries))
            
            # 限制显示的行业数量以减少复杂度
            max_industries = 15  # 从20减少到15
            if len(all_industries) > max_industries:
                # 按最新期的暴露绝对值排序，选择前N个
                latest_date = max(quarterly_data.keys())
                industry_ranking = sorted(
                    quarterly_data[latest_date].items(), 
                    key=lambda x: abs(x[1]), 
                    reverse=True
                )
                top_industries = [item[0] for item in industry_ranking[:max_industries]]
            else:
                top_industries = all_industries
            
            # 创建数据框 - 优化内存使用
            rotation_df = pd.DataFrame(
                index=sorted(quarterly_data.keys()), 
                columns=top_industries, 
                dtype=np.float32  # 使用float32减少内存
            )
            
            for date, exposure_dict in quarterly_data.items():
                for industry in top_industries:
                    if industry in exposure_dict:
                        rotation_df.loc[date, industry] = float(exposure_dict[industry])
            
            # 填充NaN为0
            rotation_df = rotation_df.fillna(FILLNA_VALUE)
            
            # 创建简化的热力图
            fig, ax = plt.subplots(figsize=(12, 6))  # 减小图形尺寸
            try:
                # 使用简化的颜色映射和参数
                im = ax.imshow(rotation_df.T, aspect='auto', cmap='RdBu_r', vmin=-2, vmax=2)
                
                # 简化坐标轴设置
                ax.set_xticks(range(len(rotation_df.index)))
                ax.set_xticklabels([date.strftime('%Y-%m') for date in rotation_df.index], 
                                 rotation=45, ha='right', fontsize=8)
                ax.set_yticks(range(len(top_industries)))
                
                # 简化标签设置
                try:
                    ax.set_yticklabels(top_industries, fontsize=8)
                    ax.set_title(f'因子 {factor_name} 行业轮动 (Top {len(top_industries)})', fontsize=10)
                    plt.colorbar(im, ax=ax, label='行业暴露')
                except Exception:
                    # 回退到英文标签
                    ax.set_yticklabels([f'Ind_{i+1}' for i in range(len(top_industries))], fontsize=8)
                    ax.set_title(f'Factor {factor_name} Industry Rotation (Top {len(top_industries)})', fontsize=10)
                    plt.colorbar(im, ax=ax, label='Industry Exposure')
                
                plt.tight_layout()
                
                # 保存图形（同步保存）
                output_path = os.path.join(self.output_dir, 'visualizations', f'{factor_name}_industry_rotation.png')
                self._save_figure_sync(fig, output_path, dpi=150)
            finally:
                plt.close(fig)
            
            # 清理内存
            del rotation_df
            self._cleanup_memory()
    
    def _market_value_rotation_analysis(self) -> None:
        """市值轮动分析"""
        self.logger.info("进行市值轮动分析...")
        
        market_value_rotation_results = {}
        
        for factor_name, factor_data in self.neutralized_factors.items():
            # 按季度分析
            quarterly_dates = factor_data.resample('QE').last().index
            
            mv_exposure_by_quarter = {}
            
            for quarter_end in quarterly_dates:
                # 检查日期是否在因子数据中存在
                if quarter_end not in factor_data.index:
                    continue
                    
                if quarter_end not in self.market_value_data.index:
                    continue
                
                factor_values = factor_data.loc[quarter_end].dropna()
                mv_data = self.market_value_data.loc[quarter_end]
                
                # 对齐数据
                common_symbols = factor_values.index.intersection(mv_data.index)
                if len(common_symbols) < 20:
                    continue
                
                factor_aligned = factor_values[common_symbols]
                mv_aligned = mv_data[common_symbols]
                
                # 只取正市值
                valid_mask = mv_aligned > 0
                if valid_mask.sum() < 20:
                    continue
                
                factor_valid = factor_aligned[valid_mask]
                mv_valid = mv_aligned[valid_mask]
                
                # 计算对数市值
                log_mv = np.log(mv_valid)
                
                # 计算市值相关性
                corr = factor_valid.corr(log_mv)
                
                if not pd.isna(corr):
                    mv_exposure_by_quarter[quarter_end] = corr
            
            market_value_rotation_results[factor_name] = mv_exposure_by_quarter
        
        # 可视化市值轮动
        self._visualize_market_value_rotation(market_value_rotation_results)
        
        # 保存结果
        output_path = os.path.join(self.output_dir, 'analysis', 'market_value_rotation.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            serializable_results = {}
            for factor_name, quarterly_data in market_value_rotation_results.items():
                serializable_results[factor_name] = {
                    str(date): exposure for date, exposure in quarterly_data.items()
                }
            
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"市值轮动分析结果保存到: {output_path}")
    
    def _visualize_market_value_rotation(self, market_value_rotation_results: Dict[str, Dict]) -> None:
        """可视化市值轮动"""
        output_path = os.path.join(self.output_dir, 'visualizations', 'market_value_rotation.png')
        fig, axes = plt.subplots(len(market_value_rotation_results), 1, 
                                figsize=(12, 4 * len(market_value_rotation_results)))
        try:
            if len(market_value_rotation_results) == 1:
                axes = [axes]
            
            for idx, (factor_name, quarterly_data) in enumerate(market_value_rotation_results.items()):
                if not quarterly_data:
                    continue
                
                # 创建数据框
                dates = sorted(quarterly_data.keys())
                exposures = [quarterly_data[date] for date in dates]
                
                # 绘制折线图
                axes[idx].plot(dates, exposures, marker='o', linewidth=2)
                axes[idx].axhline(y=0, color='r', linestyle='--', alpha=0.5)
                axes[idx].set_title(f'因子 {factor_name} 市值暴露轮动')
                axes[idx].set_xlabel('季度')
                axes[idx].set_ylabel('市值相关性')
                axes[idx].grid(True, alpha=0.3)
                
                # 添加数值标签
                for date, exposure in zip(dates, exposures):
                    axes[idx].text(date, exposure, f'{exposure:.3f}', 
                                  ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            
            # 保存图形
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)
        
        self.logger.info(f"市值轮动图保存到: {output_path}")
    
    def _visualize_index_rotation(self, index_rotation_results: Dict[str, Dict]) -> None:
        """可视化指数轮动"""
        output_path = os.path.join(self.output_dir, 'visualizations', 'index_rotation.png')
        fig, axes = plt.subplots(len(index_rotation_results), 1, 
                                figsize=(12, 4 * len(index_rotation_results)))
        try:
            if len(index_rotation_results) == 1:
                axes = [axes]
            
            for idx, (factor_name, quarterly_data) in enumerate(index_rotation_results.items()):
                if not quarterly_data:
                    continue
                
                # 创建数据框
                dates = sorted(quarterly_data.keys())
                exposures = [quarterly_data[date] for date in dates]
                
                # 绘制折线图
                axes[idx].plot(dates, exposures, marker='o', linewidth=2)
                axes[idx].axhline(y=0, color='r', linestyle='--', alpha=0.5)
                axes[idx].set_title(f'因子 {factor_name} 指数暴露轮动')
                axes[idx].set_xlabel('季度')
                axes[idx].set_ylabel('指数暴露')
                axes[idx].grid(True, alpha=0.3)
                
                # 添加数值标签
                for date, exposure in zip(dates, exposures):
                    axes[idx].text(date, exposure, f'{exposure:.3f}', 
                                  ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            
            # 保存图形
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)
        
        self.logger.info(f"指数轮动图保存到: {output_path}")

# 主函数
def main():
    """主函数"""
    config = {
        'factor_dir': r'D:\Coding\factor_Neutralizer\factors_input',
        'price_dir': r'E:\Ashare_data\market_data\stock_close.pkl',  # 直接指向PKL文件
        'industry_file': r'E:\Ashare_data\market_data\industry_mapping.pkl',
        'index_file': r'E:\Ashare_data\market_data\index_constituents.pkl',
        'market_value_file': r'E:\Ashare_data\market_data\stock_market_value.pkl',
        'output_dir': r'D:\Coding\factor_Neutralizer\neutralized_results',
        'index_code': '000001.SH',
        'neutralization_type': 'industry',
        'industry_method': 'regression',
        'force_reprocess': False, # False: 不强制重新处理
        # 新增文件类型配置
        'industry_file_type': 'pkl',  # 指定为pkl文件
        'index_file_type': 'pkl',      # 指定为pkl文件
        'market_value_file_type': 'pkl', # 指定为pkl文件
        'enable_cache': True
    }
    
    logger = logging.getLogger(__name__)
    logger.info("配置信息:")
    logger.info(f"价格数据: {config['price_dir']} (PKL格式)")
    logger.info(f"行业数据: {config['industry_file']}")
    logger.info(f"指数数据: {config['index_file']}")
    logger.info(f"市值数据: {config['market_value_file']}")
    logger.info(f"因子目录: {config['factor_dir']}")
    logger.info(f"缓存启用: {config['enable_cache']}")
    
    # 创建中性化处理器
    neutralizer = FactorNeutralizer(
        factor_dir=config['factor_dir'],
        price_dir=config['price_dir'],
        industry_file=config['industry_file'],
        index_file=config['index_file'],
        market_value_file=config['market_value_file'],
        output_dir=config['output_dir'],
        index_code=config['index_code'],
        enable_cache=config['enable_cache'],
        industry_file_type=config['industry_file_type'],
        index_file_type=config['index_file_type'],
        market_value_file_type=config['market_value_file_type']
    )
    
    # 处理所有因子
    neutralizer.process_all_factors(
        neutralization_type=config['neutralization_type'],
        industry_method=config['industry_method'],
        force_reprocess=config['force_reprocess']
    )
    
    # 轮动分析
    neutralizer.rotation_analysis()
    
    logger.info("所有任务完成!")

if __name__ == "__main__":
    main()
