# -*- coding: utf-8 -*-
"""
管道中间结果缓存

使用 parquet 格式存储中间步骤结果，避免重复计算。
缓存 key 基于输入数据采样 hash + 步骤参数 hash。

Usage:
    cache = PipelineCache("./cache")
    
    # 写入缓存
    cache.set("imputation", "momentum_6m", {"method": "auto"}, input_df, result_df)
    
    # 读取缓存（miss 时返回 None）
    cached = cache.get("imputation", "momentum_6m", {"method": "auto"}, input_df)
    if cached is not None:
        result_df = cached
"""

import hashlib
import json
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class PipelineCache:
    """
    管道中间结果缓存
    
    使用 parquet 格式存储中间步骤结果。
    缓存 key = sha256(step_name + factor_name + params_json + data_sample_hash)[:16]
    
    缓存策略:
    - 基于输入数据采样 hash（前 50 行 + 后 50 行 + metadata），O(1) 计算
    - 参数变化自动失效（JSON 序列化对比）
    - 启用/禁用开关
    
    Parameters
    ----------
    cache_dir : str
        缓存目录路径
    enabled : bool
        是否启用缓存（默认 True）
    """
    
    def __init__(self, cache_dir: str = "./cache", enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    
    def get(
        self, step_name: str, factor_name: str,
        params: Dict[str, Any], input_data: pd.DataFrame
    ) -> Optional[pd.DataFrame]:
        """
        尝试从缓存读取中间结果
        
        Parameters
        ----------
        step_name : str
            步骤名称（如 "imputation", "outlier"）
        factor_name : str
            因子名称
        params : Dict[str, Any]
            步骤参数
        input_data : pd.DataFrame
            输入数据（用于计算 hash）
        
        Returns
        -------
        pd.DataFrame or None
            缓存命中时返回 DataFrame，miss 时返回 None
        """
        if not self.enabled:
            return None
        
        key = self._make_key(step_name, factor_name, params, self._data_hash(input_data))
        cache_path = self.cache_dir / f"{key}.parquet"
        
        if cache_path.exists():
            logger.info(f"[Cache HIT] {step_name}/{factor_name} -> {cache_path.name}")
            return pd.read_parquet(cache_path)
        
        logger.debug(f"[Cache MISS] {step_name}/{factor_name}")
        return None
    
    def set(
        self, step_name: str, factor_name: str,
        params: Dict[str, Any], input_data: pd.DataFrame,
        result: pd.DataFrame
    ):
        """
        写入缓存
        
        Parameters
        ----------
        step_name : str
            步骤名称
        factor_name : str
            因子名称
        params : Dict[str, Any]
            步骤参数
        input_data : pd.DataFrame
            输入数据（用于计算 hash）
        result : pd.DataFrame
            要缓存的结果数据
        """
        if not self.enabled:
            return
        
        key = self._make_key(step_name, factor_name, params, self._data_hash(input_data))
        cache_path = self.cache_dir / f"{key}.parquet"
        result.to_parquet(cache_path, index=True)
        logger.debug(f"[Cache SET] {step_name}/{factor_name} -> {cache_path.name}")
    
    def clear(self):
        """清空所有缓存文件"""
        if not self.cache_dir.exists():
            return
        removed = 0
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
            removed += 1
        if removed > 0:
            logger.info(f"Cache cleared: {removed} files removed")
    
    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    
    def _make_key(
        self, step_name: str, factor_name: str,
        params: Dict[str, Any], data_hash: str
    ) -> str:
        """生成缓存 key: sha256(step + factor + params + data_hash)[:16]"""
        params_str = json.dumps(params, sort_keys=True, default=str)
        raw = f"{step_name}:{factor_name}:{data_hash}:{params_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def _data_hash(self, df: pd.DataFrame) -> str:
        """
        计算 DataFrame 的快速采样 hash
        
        策略: 取前 50 行 + 后 50 行 + metadata (shape, columns, dtypes)
        复杂度 O(100 × N) 而非 O(T × N)，对大 DataFrame 友好。
        16 位 hex = 64 bit，碰撞概率极低（~2^32 条缓存条目才有 50% 碰撞）。
        """
        head = df.head(50).to_numpy().tobytes() if len(df) > 0 else b""
        tail = df.tail(50).to_numpy().tobytes() if len(df) > 50 else b""
        meta = f"{df.shape}|{list(df.columns)}|{df.dtypes.to_dict()}".encode()
        return hashlib.sha256(head + tail + meta).hexdigest()[:12]