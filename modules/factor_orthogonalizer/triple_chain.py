r"""因子诊断三件套串联协调器 (O5)

跨 Layer 1/2/3 串联:
1. Fingerprint (Layer 1 描述): 13 维指标 + STATIC/DYNAMIC/MIXED 分类
2. Decoupler (Layer 1 时序解耦): 消除单因子自相关 (在 Pipeline 内部)
3. Orthogonalizer (Layer 2 横截面正交): 消除因子间相关性
4. FactorSignificanceTest (Layer 3 增量检验): 双重 Lasso + HC3

数据流协议 (O5.6.1):
    raw_factors: FactorDict (原始, 含 NaN/异常值)
       ↓ [Layer 1: Fingerprint 提取] (只读, 不修改)
    raw_factors → Fingerprinter.extract() → fingerprints
       ↓ [Layer 1: Pipeline 处理] (per-factor, 含 Decoupler)
    processed_factors: FactorDict (已清洗/标准化/中性化/解耦)
       ↓ [Layer 2: Orthogonalizer] (cross-factor)
    orthogonalized_factors: FactorDict
       ↓ [Layer 3: FactorSignificanceTest] (需 Y)
    significance_report: Dict[name, TestResult]

契约:
- Fingerprinter: 输入 FactorDict, 输出 Dict[name, Fingerprint], 不修改输入
- Pipeline: 输入 FactorDict, 输出 FactorDict, 同 keys 同 shape
- Orthogonalizer: 输入 FactorDict, 输出 FactorDict, 同 keys 同 shape
- SignificanceTest: 输入 FactorDict + fwd_returns, 输出 Dict[name, dict]

学术依据:
- Barra 风险模型: 行业中性化 (Layer 1) 先于因子正交化 (Layer 2)
- Asness (2013): Value 与 Momentum 负相关, 不应强行正交

O5.6.4 缓存: 相同输入第二次调用走缓存
O5.6.5 冲突解决: conservative / aggressive / ic_priority 三策略
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd


# 数据类型别名 (清晰区分)
FactorDict = Dict[str, pd.DataFrame]


class TripleChainCoordinator:
    """三件套串联协调器

    职责:
    - 协调 Fingerprint / Pipeline / Orthogonalizer / SignificanceTest
    - 提供端到端诊断报告
    - 不修改 Layer 1 Pipeline (保持 per-factor 不变)

    Args:
        fingerprinter: Fingerprinter 实例 (可选, Layer 1 描述)
        decoupler: Decoupler 实例 (可选, Layer 1 时序解耦, 通常在 Pipeline 内部)
        orthogonalizer: Orthogonalizer 实例 (可选, Layer 2 横截面正交)
            - 必须有 `enabled` 属性 (bool) 和 `fit_transform(factor_dict)` 方法
        significance_test: FactorSignificanceTest 实例 (可选, Layer 3 检验)
        cache_enabled: 是否启用缓存 (O5.6.4, 默认 True)

    Attributes:
        _cache: {cache_key: report} 缓存字典
    """

    def __init__(
        self,
        fingerprinter: Optional[Any] = None,
        decoupler: Optional[Any] = None,
        orthogonalizer: Optional[Any] = None,
        significance_test: Optional[Any] = None,
        cache_enabled: bool = True,
    ):
        self.fingerprinter = fingerprinter
        self.decoupler = decoupler
        self.orthogonalizer = orthogonalizer
        self.significance_test = significance_test
        self.cache_enabled = cache_enabled
        self._cache: Dict[Any, Any] = {}

    def full_diagnosis(
        self,
        raw_factors: FactorDict,
        processed_factors: FactorDict,
        fwd_returns: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """端到端诊断报告

        Args:
            raw_factors: 原始因子 (Layer 1 输入)
            processed_factors: Pipeline 处理后因子 (Layer 1 输出)
            fwd_returns: 前向收益 (可选, Layer 3 用)

        Returns:
            {
                'fingerprints': Dict[name, Any],
                'orthogonalization': Optional[Dict],
                'significance': Optional[Dict],
            }
        """
        # O5.6.1: 数据流契约校验
        self._validate_contract(raw_factors, processed_factors)

        # O5.6.4: 缓存命中检查
        if self.cache_enabled:
            cache_key = self._compute_cache_key(
                raw_factors, processed_factors, fwd_returns
            )
            if cache_key in self._cache:
                return self._cache[cache_key]

        # 计算诊断报告
        report = self._compute_full_diagnosis(
            raw_factors, processed_factors, fwd_returns
        )

        # O5.6.4: 缓存结果
        if self.cache_enabled:
            self._cache[cache_key] = report

        return report

    def _validate_contract(
        self,
        raw_factors: FactorDict,
        processed_factors: FactorDict,
    ) -> None:
        """O5.6.1: 数据流契约校验

        - raw 和 processed 的 keys 必须一致
        - 每个因子的 shape 必须一致
        """
        if set(raw_factors.keys()) != set(processed_factors.keys()):
            raise ValueError(
                f"raw_factors 和 processed_factors 的 keys 不一致: "
                f"raw={set(raw_factors.keys())}, "
                f"processed={set(processed_factors.keys())}"
            )
        for name in raw_factors:
            r_shape = raw_factors[name].shape
            p_shape = processed_factors[name].shape
            if r_shape != p_shape:
                raise ValueError(
                    f"因子 {name}: raw shape {r_shape} != "
                    f"processed shape {p_shape}"
                )

    def _compute_full_diagnosis(
        self,
        raw_factors: FactorDict,
        processed_factors: FactorDict,
        fwd_returns: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """实际计算诊断报告 (无缓存)"""
        report: Dict[str, Any] = {
            'fingerprints': {},
            'orthogonalization': None,
            'significance': None,
        }

        # Layer 1: Fingerprint (对 raw, 只读, 不修改输入)
        if self.fingerprinter is not None:
            for name, df in raw_factors.items():
                report['fingerprints'][name] = self.fingerprinter.extract(df)

        # Layer 2: Orthogonalization (对 processed)
        orth_factors = processed_factors
        if (
            self.orthogonalizer is not None
            and getattr(self.orthogonalizer, 'enabled', False)
        ):
            orth_factors = self.orthogonalizer.fit_transform(processed_factors)
            report['orthogonalization'] = {
                'method': getattr(self.orthogonalizer, 'method', 'unknown'),
                'diagnostics': 'see OrthogonalizationDiagnostics',
            }

        # Layer 3: Significance (对 orth_factors, 需 Y)
        if (
            self.significance_test is not None
            and fwd_returns is not None
        ):
            sig = self.significance_test.fit(
                orth_factors, fwd_returns,
                list(processed_factors.keys()),
            )
            report['significance'] = sig.test_all_factors()

        return report

    @staticmethod
    def _hash_factor_dict(factor_dict: FactorDict) -> str:
        """O5.6.4: 基于内容生成 factor_dict 的哈希

        Args:
            factor_dict: {因子名: DataFrame}

        Returns: md5 哈希字符串
        """
        h = hashlib.md5()
        for name in sorted(factor_dict.keys()):
            df = factor_dict[name]
            h.update(name.encode('utf-8'))
            h.update(str(df.shape).encode('utf-8'))
            # values.tobytes 不可用时用 flatten
            try:
                h.update(df.values.tobytes())
            except (ValueError, AttributeError):
                # Fallback: 用 sum/statistics (精度低但避免崩溃)
                h.update(str(float(np.nansum(df.values))).encode('utf-8'))
        return h.hexdigest()

    @classmethod
    def _compute_cache_key(
        cls,
        raw_factors: FactorDict,
        processed_factors: FactorDict,
        fwd_returns: Optional[pd.DataFrame],
    ) -> tuple:
        """构造缓存 key"""
        raw_hash = cls._hash_factor_dict(raw_factors)
        proc_hash = cls._hash_factor_dict(processed_factors)
        if fwd_returns is not None:
            y_hash = cls._hash_factor_dict({'_y': fwd_returns})
        else:
            y_hash = None
        return (raw_hash, proc_hash, y_hash)

    def resolve_conflicts(
        self,
        report: Dict[str, Any],
        strategy: str = 'ic_priority',
    ) -> Dict[str, Dict[str, Any]]:
        """O5.6.5: 跨 Layer 诊断冲突解决

        Args:
            report: full_diagnosis 返回的报告
            strategy: 冲突解决策略
                - 'conservative': 任一诊断不利则 drop
                - 'aggressive': 任一诊断有利则 keep
                - 'ic_priority' (默认): IC 为最终裁判, IC 显著则 keep

        Returns:
            {因子名: {recommendation: 'keep'/'drop', reasons: {...}, strategy: str}}
        """
        if strategy not in ('conservative', 'aggressive', 'ic_priority'):
            raise ValueError(
                f"未知 strategy: {strategy}, "
                f"支持: 'conservative' / 'aggressive' / 'ic_priority'"
            )

        # 从 report 中提取诊断信息
        orth_diag = (
            report.get('orthogonalization', {})
            .get('diagnostics', {})
            .get('vrr', {})
        )
        sig_report = report.get('significance', {}) or {}

        recommendations: Dict[str, Dict[str, Any]] = {}
        for name in report.get('fingerprints', {}):
            vrr = orth_diag.get(name, 1.0)
            sig = sig_report.get(name, {})
            is_significant = sig.get(
                'is_significant_adjusted',
                sig.get('is_significant', False),
            )
            # IC 变化比率 (负值表示 IC 下降)
            ic_change_ratio = sig.get('ic_change_ratio', 0.0)
            # is_degraded: |ic_change_ratio| > 0.8
            ic_degraded = (
                ic_change_ratio is not None
                and abs(ic_change_ratio) > 0.8
            )
            is_redundant = vrr < 0.3

            if strategy == 'conservative':
                keep = is_significant and not is_redundant and not ic_degraded
            elif strategy == 'aggressive':
                keep = is_significant or (not is_redundant and not ic_degraded)
            elif strategy == 'ic_priority':
                # IC 为最终裁判
                keep = bool(is_significant)

            recommendations[name] = {
                'recommendation': 'keep' if keep else 'drop',
                'reasons': {
                    'is_significant': bool(is_significant),
                    'is_redundant': bool(is_redundant),
                    'ic_degraded': bool(ic_degraded),
                    'vrr': float(vrr),
                    'ic_change_ratio': float(ic_change_ratio) if ic_change_ratio is not None else None,
                },
                'strategy': strategy,
            }
        return recommendations

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
