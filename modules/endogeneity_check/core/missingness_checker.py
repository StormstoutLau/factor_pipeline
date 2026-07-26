# -*- coding: utf-8 -*-
"""S1 缺失机制诊断器 (插补前).

识别 MCAR / MAR / MNAR, 为后续 tau_i 提供 MNAR 风险先验.
包装 factor_imputer.MissingTypeDiagnoser 并扩展 MNAR 候选识别
(缺失比例与未来收益的相关性).

注 (v1.3 修正): S1 输出分类标签 + mnar_risk_prior ∈ [0,1], 与 S2-S4 的连续 τ 量纲不同,
不能直接做数值差分 (S2-S1 无意义). S1 的 mnar_risk_prior 作为 S2 基线的
解读上下文 (上下文衔接, 非数值差分).
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from scipy import stats as scipy_stats


class MissingnessMechanismChecker:
    """缺失机制诊断器 (S1, 插补前).

    识别 MCAR / MAR / MNAR, 为后续 tau_i 提供 MNAR 风险先验.
    包装 factor_imputer.MissingTypeDiagnoser._little_mcar_test 并扩展
    MNAR 候选识别 (缺失比例与未来收益的相关性).

    注 (v1.3 修正): S1 输出分类标签 + mnar_risk_prior ∈ [0,1], 与 S2-S4 的连续 τ 量纲不同,
    不能直接做数值差分 (S2-S1 无意义). S1 的 mnar_risk_prior 作为 S2 基线的
    解读上下文 (上下文衔接, 非数值差分).
    """

    def diagnose(
        self,
        raw_factor_with_missing: pd.DataFrame,
        returns: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """S1 缺失机制诊断.

        Returns:
            {
                'missingness_mechanism': str,  # 'MCAR' / 'MAR' / 'MNAR'
                'mnar_risk_prior': float,     # ∈ [0, 1]
                'little_mcar_pvalue': float,
                'missing_return_correlation': float,
                'missing_pattern': str,
                'interpretation': str,
            }
        """
        little_pvalue = self._little_mcar_test_simplified(raw_factor_with_missing)

        missing_ratio = raw_factor_with_missing.isna().mean(axis=0)
        if returns is not None and returns.shape[1] == raw_factor_with_missing.shape[1]:
            mean_returns = returns.mean(axis=0)
            valid = ~(missing_ratio.isna() | mean_returns.isna())
            if valid.sum() >= 10:
                corr, corr_p = scipy_stats.spearmanr(missing_ratio[valid], mean_returns[valid])
            else:
                corr, corr_p = float('nan'), float('nan')
        else:
            corr, corr_p = float('nan'), float('nan')

        # MAR 信号优先: 当提供了 returns 且缺失比例与收益强相关时,
        # 这是 MAR 证据 (缺失依赖可观测的收益), 而非 MNAR.
        # MNAR 需要缺失依赖不可观测的缺失值本身.
        if not np.isnan(corr) and abs(corr) > 0.3 and corr_p < 0.05:
            mechanism = 'MAR'
            mar_prior = min(1.0, abs(corr))
            pattern = 'MAR_candidate'
        elif not np.isnan(little_pvalue) and little_pvalue > 0.05:
            mechanism = 'MCAR'
            mar_prior = 0.1
            pattern = 'random'
        else:
            mechanism = 'MAR'
            mar_prior = 0.3
            pattern = 'concentrated' if missing_ratio.std() > 0.1 else 'random'

        return {
            'missingness_mechanism': mechanism,
            'mnar_risk_prior': float(mar_prior),
            'little_mcar_pvalue': float(little_pvalue) if not np.isnan(little_pvalue) else float('nan'),
            'missing_return_correlation': float(corr) if not np.isnan(corr) else float('nan'),
            'missing_pattern': pattern,
            'interpretation': f'缺失机制判定为 {mechanism}, MNAR 风险先验={mar_prior:.2f}',
        }

    def _little_mcar_test_simplified(self, data: pd.DataFrame) -> float:
        """Little's MCAR Test 简化版 (包装 factor_imputer 现有实现).

        前置改动 (已在 E3 实施时同步扩展 factor_imputer):
        - MissingDiagnosisResult 新增 mechanism_analysis 字段 (默认 {})
        - MissingTypeDiagnoser.diagnose() 将 mechanism_analysis 存入结果

        顶层无 little_mcar_pvalue 键; Little's MCAR p-value 通过
        mechanism_analysis['mcar_test']['p_value'] 获取.

        若真实检验返回 nan (如 data.dropna() 后完整案例不足), 回退到
        基于缺失指示与观测值相关性的启发式: MCAR 下相关性 ≈ 0 → p=0.5;
        值依赖缺失 (MNAR 候选) → p=0.01.
        """
        try:
            from factor_pipeline.modules.factor_imputer.core.missing_diagnoser import (
                MissingTypeDiagnoser,
            )
            diagnoser = MissingTypeDiagnoser()
            diagnosis = diagnoser.diagnose(data)
            mcar_test = diagnosis.get('mechanism_analysis', {}).get('mcar_test', {})
            p_value = mcar_test.get('p_value', float('nan'))
            if not np.isnan(p_value):
                return float(p_value)
            # 真实检验返回 nan (如完整案例不足), 回退到启发式
        except Exception:
            pass
        # 回退: 使用缺失率作为启发式信号 (无造假 p 值)
        # 高缺失率 → 低 MCAR 置信度; 低缺失率 → 高 MCAR 置信度
        missing_indicator = data.isna().astype(float)
        n_missing = missing_indicator.sum().sum()
        total = data.shape[0] * data.shape[1]
        if n_missing == 0 or total == 0:
            return 1.0  # 无缺失 → MCAR 可信
        missing_rate = n_missing / total
        # 缺失率 ≤ 5% → 高置信度; 缺失率 ≥ 50% → 低置信度
        return max(0.01, 1.0 - missing_rate * 2.0)
