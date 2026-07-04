r"""横截面正交化协调器 (O2.3 + O2.8.6)

管理 K 因子联合应用 W: 对每期 t, T_t = F_t @ W

职责:
- 对齐 K 个因子的 index/columns (委托 utils.align_factors)
- 对每期 t 应用 W: T_t = F_t @ W (W 在 fit 中估计)
- 拆分回 Dict[str, DataFrame] 格式
- W 缓存 (full_sample 模式, O2.8.6)

架构层: Layer 2 (无监督变换)
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import align_factors


class CrossSectionalOrthogonalizer:
    """横截面正交化协调器

    Args:
        orthogonalizer: BaseOrthogonalizer 实例 (已 fit, 含 W_ 属性)

    Attributes:
        W_cached_: Optional[np.ndarray] — 缓存的 W 矩阵 (full_sample 模式)
    """

    def __init__(self, orthogonalizer):
        """orthogonalizer: BaseOrthogonalizer 实例 (已 fit)"""
        self.orthogonalizer = orthogonalizer
        self.W_cached_: Optional[np.ndarray] = None

    def transform(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        align_mode: str = 'intersection',
    ) -> Dict[str, pd.DataFrame]:
        """对每期截面应用 W

        Args:
            factor_dict: {因子名: (N, T) DataFrame}
            align_mode: 对齐策略 (默认 'intersection')

        Returns:
            Dict[str, pd.DataFrame]: 同格式, K 个正交化后因子

        Note:
            - NaN 处理 (O2.8.2): 含 NaN 的行填 0 应用 W, 再恢复 NaN
            - W 缓存 (O2.8.6): full_sample 模式下 W 不变, 缓存后直接用
        """
        # 1. 对齐
        aligned = align_factors(factor_dict, align_mode)
        factor_names = list(aligned.keys())
        K = len(factor_names)

        first_df = aligned[factor_names[0]]
        N, T = first_df.shape

        # 2. 构造 (N, T, K) 面板
        F_panel = np.zeros((N, T, K), dtype=np.float64)
        for k, name in enumerate(factor_names):
            F_panel[:, :, k] = aligned[name].values

        # 3. 缓存 W (若未缓存)
        if self.W_cached_ is None and hasattr(self.orthogonalizer, 'W_'):
            self.W_cached_ = self.orthogonalizer.W_

        # 4. 对每期 t 应用 W: T_t = F_t @ W
        T_panel = np.zeros_like(F_panel)
        for t in range(T):
            F_t = F_panel[:, t, :]  # (N, K)
            # NaN 处理: 含 NaN 的行填 0, 应用 W, 恢复 NaN
            nan_mask = np.any(np.isnan(F_t), axis=1)
            if np.any(nan_mask):
                F_t_filled = np.nan_to_num(F_t, nan=0.0)
                if self.W_cached_ is not None:
                    T_t = F_t_filled @ self.W_cached_
                else:
                    T_t = self.orthogonalizer.transform(F_t_filled)
                T_t[nan_mask] = np.nan
            else:
                if self.W_cached_ is not None:
                    T_t = F_t @ self.W_cached_
                else:
                    T_t = self.orthogonalizer.transform(F_t)
            T_panel[:, t, :] = T_t

        # 5. 拆分回 Dict[str, DataFrame]
        result = {}
        for k, name in enumerate(factor_names):
            result[name] = pd.DataFrame(
                T_panel[:, :, k],
                index=first_df.index,
                columns=first_df.columns,
            )
        return result
