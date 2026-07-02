# -*- coding: utf-8 -*-
"""
L2 磁盘缓存管理器 — CacheManager

设计原则（优先级）:
    P0 可调试性 > P1 正确性 > P2 性能

透明度三层:
    1. 日志层: 每次操作记录 HIT/MISS/INVALIDATE
    2. 元数据层: 每个缓存文件附 .meta.json，记录完整来源信息
    3. 环境变量逃生舱: FACTOR_PIPELINE_CACHE=disabled 全局禁用

失效策略（不依赖 TTL 猜测）:
    - 显式 invalidate()
    - 数据指纹校验失败时自愈丢弃
    - 文件损坏时返回 None

支持的数据类型:
    - pd.DataFrame → .parquet
    - np.ndarray   → .npy

Usage:
    manager = CacheManager(cache_dir="./cache", enabled=True)
    key = CacheKey("price_matrix", "close_2024", "v1")
    manager.set(key, df, source_signature={"sql": "...", "db_loaded_at_max": "..."})
    result = manager.get(key)  # 命中返回 df，未命中返回 None
    manager.invalidate(key)    # 显式失效
    manager.verify(key)        # 一致性检查
    manager.status()           # 可观测性
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# =============================================================================
# 常量
# =============================================================================

ENV_VAR = "FACTOR_PIPELINE_CACHE"
ENV_DISABLED = "disabled"
ENV_ENABLED = "enabled"

CODE_VERSION = "v2.2.0-cache"


# =============================================================================
# 数据类
# =============================================================================

@dataclass(frozen=True)
class CacheKey:
    """缓存键: namespace + identifier + version 唯一确定一个缓存条目。

    namespace: 逻辑命名空间（price_matrix / factor_matrix / fwd_returns）
    identifier: 具体标识（如 close_2024_01_2024_12）
    version: 版本号（数据格式或代码版本变更时升级）
    """
    namespace: str
    identifier: str
    version: str = "v1"

    @property
    def filename_stem(self) -> str:
        """文件名 stem（无扩展名），SHA256 前缀 + 可读后缀。

        SHA256 前缀避免特殊字符和碰撞；可读后缀便于人工排查。
        """
        raw = f"{self.namespace}__{self.identifier}__{self.version}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        # 清理 identifier 中的不安全字符
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.identifier)
        return f"{h}_{self.namespace}_{safe_id}"

    def __str__(self) -> str:
        return f"CacheKey({self.namespace}/{self.identifier}@{self.version})"


@dataclass
class CacheMeta:
    """缓存元数据，与数据文件一一对应。

    每个字段都是 JSON 可序列化的，便于人工查看和工具读取。
    """
    cache_key: str
    created_at: str
    namespace: str
    identifier: str
    version: str
    source_signature: Dict[str, Any]
    data_fingerprint: Dict[str, Any]
    code_version: str
    data_type: str  # "dataframe" | "ndarray"
    index_freq: Optional[str] = None  # DataFrame.index（行）的 freq
    columns_freq: Optional[str] = None  # DataFrame.columns（列）的 freq

    def to_dict(self) -> dict:
        return {
            "cache_key": self.cache_key,
            "created_at": self.created_at,
            "namespace": self.namespace,
            "identifier": self.identifier,
            "version": self.version,
            "source_signature": self.source_signature,
            "data_fingerprint": self.data_fingerprint,
            "code_version": self.code_version,
            "data_type": self.data_type,
            "index_freq": self.index_freq,
            "columns_freq": self.columns_freq,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CacheMeta":
        return cls(**d)


@dataclass
class CacheStatus:
    """verify() 返回值"""
    is_valid: bool
    reason: str


# =============================================================================
# 指纹计算
# =============================================================================

def _compute_dataframe_fingerprint(df: pd.DataFrame) -> dict:
    """计算 DataFrame 指纹: head/tail hash + nan_ratio + shape。

    使用前 50 行 + 后 50 行的 tobytes() 哈希，O(1) 复杂度。
    """
    arr = df.values
    n = len(df)
    k = min(50, n) if n > 0 else 0
    if k > 0:
        head_bytes = df.iloc[:k].values.tobytes()
        tail_bytes = df.iloc[-k:].values.tobytes()
    else:
        head_bytes = b""
        tail_bytes = b""
    return {
        "head_hash": hashlib.sha256(head_bytes).hexdigest()[:16],
        "tail_hash": hashlib.sha256(tail_bytes).hexdigest()[:16],
        "nan_ratio": float(np.isnan(arr).sum() / arr.size) if arr.size > 0 else 0.0,
        "shape": list(df.shape),
    }


def _compute_array_fingerprint(arr: np.ndarray) -> dict:
    """计算 numpy 数组指纹"""
    n = len(arr)
    k = min(50, n) if n > 0 else 0
    if k > 0:
        head_bytes = arr[:k].tobytes()
        tail_bytes = arr[-k:].tobytes()
    else:
        head_bytes = b""
        tail_bytes = b""
    return {
        "head_hash": hashlib.sha256(head_bytes).hexdigest()[:16],
        "tail_hash": hashlib.sha256(tail_bytes).hexdigest()[:16],
        "nan_ratio": float(np.isnan(arr).sum() / arr.size) if arr.size > 0 else 0.0,
        "shape": list(arr.shape),
    }


# =============================================================================
# CacheManager
# =============================================================================

class CacheManager:
    """L2 磁盘缓存管理器。

    透明度优先: 每次操作记录日志，每个文件附 .meta.json，
    环境变量 FACTOR_PIPELINE_CACHE=disabled 一键禁用。
    """

    def __init__(
        self,
        cache_dir: str,
        enabled: bool = True,
        code_version: str = CODE_VERSION,
    ):
        """初始化缓存管理器。

        Args:
            cache_dir: 缓存目录路径
            enabled: 是否启用（受环境变量覆盖）
            code_version: 代码版本号，写入 meta 用于追踪
        """
        self.cache_dir = str(cache_dir)
        self._init_enabled = enabled
        self.code_version = code_version
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # ── 启用状态（受环境变量覆盖）──────────────────────

    @property
    def enabled(self) -> bool:
        """是否启用。环境变量优先级最高。"""
        env = os.environ.get(ENV_VAR, "").lower()
        if env == ENV_DISABLED:
            return False
        if env == ENV_ENABLED:
            return True
        return self._init_enabled

    # ── 路径计算 ──────────────────────────────

    def _stem(self, key: CacheKey) -> str:
        return key.filename_stem

    def _meta_path(self, key: CacheKey) -> Path:
        return Path(self.cache_dir) / f"{self._stem(key)}.meta.json"

    def _data_path(self, key: CacheKey, data_type: str) -> Path:
        ext = ".parquet" if data_type == "dataframe" else ".npy"
        return Path(self.cache_dir) / f"{self._stem(key)}{ext}"

    def _find_existing_data_path(self, key: CacheKey) -> Optional[Path]:
        """查找已存在的数据文件（类型未知时）"""
        for ext in [".parquet", ".npy"]:
            p = Path(self.cache_dir) / f"{self._stem(key)}{ext}"
            if p.exists():
                return p
        return None

    # ── 公开 API ──────────────────────────────

    def set(
        self,
        key: CacheKey,
        data: Union[pd.DataFrame, np.ndarray],
        source_signature: Optional[Dict[str, Any]] = None,
        index_freq: Optional[str] = None,
    ) -> None:
        """写入缓存。

        Args:
            key: 缓存键
            data: DataFrame 或 numpy 数组
            source_signature: 数据来源签名（SQL/参数/loaded_at 等）
            index_freq: 已废弃（旧 API 兼容）。自动检测 DataFrame 两轴的 freq。
        """
        if not self.enabled:
            logger.info(f"[CACHE] SKIP key={key} (disabled)")
            return

        # 空 DataFrame 不缓存
        if isinstance(data, pd.DataFrame) and data.empty:
            logger.info(f"[CACHE] SKIP key={key} (empty DataFrame)")
            return

        # 清理同 key 的旧文件（可能类型不同）
        old_data_path = self._find_existing_data_path(key)
        if old_data_path is not None:
            try:
                old_data_path.unlink()
            except Exception as e:
                logger.warning(f"[CACHE] failed to remove old {old_data_path}: {e}")

        # 写入数据
        if isinstance(data, pd.DataFrame):
            data_type = "dataframe"
            data_path = self._data_path(key, data_type)
            data.to_parquet(data_path)
            fingerprint = _compute_dataframe_fingerprint(data)
            # 自动检测两轴 freq（parquet 不保留 freq）
            detected_index_freq = self._detect_freq(data.index)
            # columns_freq: 优先用显式传入的 index_freq（旧 API 兼容），否则自动检测
            detected_columns_freq = index_freq or self._detect_freq(data.columns)
        elif isinstance(data, np.ndarray):
            data_type = "ndarray"
            data_path = self._data_path(key, data_type)
            np.save(data_path, data)
            fingerprint = _compute_array_fingerprint(data)
            detected_index_freq = None
            detected_columns_freq = None
        else:
            raise TypeError(f"不支持的数据类型: {type(data)}")

        # 写入 meta.json
        meta = CacheMeta(
            cache_key=f"{key.namespace}/{key.identifier}@{key.version}",
            created_at=datetime.now().isoformat(),
            namespace=key.namespace,
            identifier=key.identifier,
            version=key.version,
            source_signature=source_signature or {},
            data_fingerprint=fingerprint,
            code_version=self.code_version,
            data_type=data_type,
            index_freq=detected_index_freq,
            columns_freq=detected_columns_freq,
        )
        meta_path = self._meta_path(key)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(
            f"[CACHE] SET key={key} type={data_type} "
            f"shape={fingerprint['shape']} fingerprint={fingerprint['head_hash'][:8]}"
        )

    def get(self, key: CacheKey) -> Optional[Union[pd.DataFrame, np.ndarray]]:
        """读取缓存。命中返回数据，未命中返回 None。"""
        result, _ = self.get_with_meta(key)
        return result

    def get_with_meta(
        self, key: CacheKey
    ) -> Tuple[Optional[Union[pd.DataFrame, np.ndarray]], Optional[CacheMeta]]:
        """读取缓存，返回 (data, meta)。未命中返回 (None, None)。"""
        if not self.enabled:
            logger.info(f"[CACHE] MISS key={key} (disabled)")
            return None, None

        meta_path = self._meta_path(key)

        # meta 文件不存在
        if not meta_path.exists():
            logger.info(f"[CACHE] MISS key={key} (meta not found)")
            return None, None

        # 读取 meta
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
            meta = CacheMeta.from_dict(meta_dict)
        except Exception as e:
            logger.warning(f"[CACHE] MISS key={key} (meta corrupted: {e})")
            return None, None

        # 定位数据文件
        data_path = self._data_path(key, meta.data_type)
        if not data_path.exists():
            logger.warning(f"[CACHE] MISS key={key} (data file missing, meta exists)")
            return None, None

        # 读取数据
        try:
            if meta.data_type == "dataframe":
                df = pd.read_parquet(data_path)
                # 恢复两轴 freq
                if meta.index_freq:
                    try:
                        df.index.freq = meta.index_freq
                    except Exception:
                        pass  # freq 恢复失败不影响数据
                if meta.columns_freq:
                    try:
                        df.columns.freq = meta.columns_freq
                    except Exception:
                        pass
                # 校验指纹
                actual_fp = _compute_dataframe_fingerprint(df)
                if actual_fp != meta.data_fingerprint:
                    logger.warning(
                        f"[CACHE] MISS key={key} (fingerprint mismatch: "
                        f"expected {meta.data_fingerprint['head_hash'][:8]}, "
                        f"got {actual_fp['head_hash'][:8]})"
                    )
                    self._safe_remove(data_path, meta_path)
                    return None, None
                logger.info(
                    f"[CACHE] HIT key={key} type=dataframe shape={df.shape} "
                    f"head_hash={actual_fp['head_hash'][:8]}"
                )
                return df, meta
            elif meta.data_type == "ndarray":
                arr = np.load(data_path)
                actual_fp = _compute_array_fingerprint(arr)
                if actual_fp != meta.data_fingerprint:
                    logger.warning(
                        f"[CACHE] MISS key={key} (fingerprint mismatch: "
                        f"expected {meta.data_fingerprint['head_hash'][:8]}, "
                        f"got {actual_fp['head_hash'][:8]})"
                    )
                    self._safe_remove(data_path, meta_path)
                    return None, None
                logger.info(
                    f"[CACHE] HIT key={key} type=ndarray shape={arr.shape} "
                    f"head_hash={actual_fp['head_hash'][:8]}"
                )
                return arr, meta
            else:
                logger.warning(f"[CACHE] MISS key={key} (unknown data_type: {meta.data_type})")
                return None, None
        except Exception as e:
            logger.warning(f"[CACHE] MISS key={key} (data corrupted: {e})")
            self._safe_remove(data_path, meta_path)
            return None, None

    def invalidate(self, key: CacheKey) -> None:
        """显式失效单个 key。不存在的 key 不报错。"""
        meta_path = self._meta_path(key)
        data_path = self._find_existing_data_path(key)
        paths_to_remove = [p for p in [data_path, meta_path] if p is not None and p.exists()]
        removed = self._safe_remove(*paths_to_remove)
        if removed:
            logger.info(f"[CACHE] INVALIDATE key={key}")
        else:
            logger.info(f"[CACHE] INVALIDATE key={key} (not found, no-op)")

    def clear_all(self) -> None:
        """清空所有缓存文件（parquet + npy + meta.json）。"""
        cache_path = Path(self.cache_dir)
        if not cache_path.exists():
            return
        count = 0
        for f in cache_path.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                    count += 1
                except Exception as e:
                    logger.warning(f"[CACHE] failed to remove {f}: {e}")
        logger.info(f"[CACHE] CLEAR_ALL removed {count} files")

    def verify(self, key: CacheKey) -> CacheStatus:
        """验证缓存一致性。返回 CacheStatus(is_valid, reason)。"""
        if not self.enabled:
            return CacheStatus(is_valid=False, reason="cache disabled")

        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return CacheStatus(is_valid=False, reason="meta file missing")

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
            meta = CacheMeta.from_dict(meta_dict)
        except Exception as e:
            return CacheStatus(is_valid=False, reason=f"meta corrupted: {e}")

        data_path = self._data_path(key, meta.data_type)
        if not data_path.exists():
            return CacheStatus(is_valid=False, reason="data file missing")

        try:
            if meta.data_type == "dataframe":
                df = pd.read_parquet(data_path)
                actual_fp = _compute_dataframe_fingerprint(df)
            else:
                arr = np.load(data_path)
                actual_fp = _compute_array_fingerprint(arr)

            if actual_fp != meta.data_fingerprint:
                return CacheStatus(
                    is_valid=False,
                    reason=(
                        f"fingerprint mismatch: expected head={meta.data_fingerprint['head_hash'][:8]}, "
                        f"got head={actual_fp['head_hash'][:8]}"
                    ),
                )
            return CacheStatus(is_valid=True, reason="OK")
        except Exception as e:
            return CacheStatus(is_valid=False, reason=f"data corrupted: {e}")

    def status(self) -> dict:
        """返回缓存状态摘要。"""
        entries = []
        total_size = 0
        cache_path = Path(self.cache_dir)
        if not cache_path.exists():
            return {"total_entries": 0, "total_size_bytes": 0, "entries": []}

        for meta_file in cache_path.glob("*.meta.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # 定位数据文件
                data_path = self._data_path(
                    CacheKey(meta["namespace"], meta["identifier"], meta["version"]),
                    meta["data_type"],
                )
                size = data_path.stat().st_size if data_path.exists() else 0
                total_size += size
                entries.append({
                    "namespace": meta["namespace"],
                    "identifier": meta["identifier"],
                    "version": meta["version"],
                    "created_at": meta["created_at"],
                    "size_bytes": size,
                    "shape": meta["data_fingerprint"]["shape"],
                    "data_type": meta["data_type"],
                })
            except Exception:
                continue

        return {
            "total_entries": len(entries),
            "total_size_bytes": total_size,
            "entries": entries,
        }

    # ── 内部工具 ──────────────────────────────

    @staticmethod
    def _detect_freq(axis) -> Optional[str]:
        """自动检测 pandas Index 的 freq，返回 freqstr 或 None。

        使用 freqstr 而非 str()，因为 str(BusinessDay)="<BusinessDay>" 无法恢复。
        """
        try:
            freq = axis.freq
            if freq is not None and hasattr(freq, "freqstr"):
                return freq.freqstr
        except Exception:
            pass
        return None

    def _safe_remove(self, *paths: Path) -> bool:
        """安全删除文件，返回是否删除了任意文件。"""
        removed = False
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
                    removed = True
            except Exception as e:
                logger.warning(f"[CACHE] failed to remove {p}: {e}")
        return removed
