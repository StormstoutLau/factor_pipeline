r"""因子对齐与堆叠工具 (O2.3 + O2.8.1)

功能:
1. align_factors: 按 align_mode 对齐 K 个因子的 index/columns
2. stack_factors_cross_section: 堆叠 K 个 (N, T) DataFrame 为 (N·T, K) 面板

对齐策略 (O2.8.1):
- 'intersection' (默认): 取交集, 严格对齐, 丢弃不共有的股票/日期
- 'union_nan': 取并集, 缺失填 NaN (配合 dropna 使用)
- 'raise_on_mismatch': 不匹配时抛错, 严格调试用

架构层: Layer 2 (无监督变换)
"""
from typing import Dict, Tuple, List

import numpy as np
import pandas as pd


def align_factors(
    factor_dict: Dict[str, pd.DataFrame],
    align_mode: str = 'intersection',
) -> Dict[str, pd.DataFrame]:
    """对齐 K 个因子的 index 和 columns

    Args:
        factor_dict: {因子名: (N, T) DataFrame}
        align_mode: 对齐策略
            - 'intersection': 取交集 (默认, 向后兼容 v1.0)
            - 'union_nan': 取并集, 缺失填 NaN
            - 'raise_on_mismatch': 不匹配时抛错

    Returns:
        Dict[str, pd.DataFrame]: 对齐后的因子字典

    Raises:
        ValueError: 交集为空 / 不匹配 (raise_on_mismatch)
    """
    if not factor_dict:
        raise ValueError("factor_dict 为空")

    names = list(factor_dict.keys())
    first = factor_dict[names[0]]

    if align_mode == 'intersection':
        common_index = first.index
        common_columns = first.columns
        for name in names[1:]:
            df = factor_dict[name]
            common_index = common_index.intersection(df.index)
            common_columns = common_columns.intersection(df.columns)
        if len(common_index) == 0 or len(common_columns) == 0:
            raise ValueError(
                "因子间无公共 index 或 columns, 无法对齐. "
                "考虑使用 align_mode='union_nan'"
            )
        return {
            name: df.loc[common_index, common_columns]
            for name, df in factor_dict.items()
        }

    elif align_mode == 'union_nan':
        all_index = first.index
        all_columns = first.columns
        for name in names[1:]:
            df = factor_dict[name]
            all_index = all_index.union(df.index)
            all_columns = all_columns.union(df.columns)
        return {
            name: df.reindex(index=all_index, columns=all_columns)
            for name, df in factor_dict.items()
        }

    elif align_mode == 'raise_on_mismatch':
        ref_idx = first.index
        ref_col = first.columns
        for name in names[1:]:
            df = factor_dict[name]
            if not df.index.equals(ref_idx) or not df.columns.equals(ref_col):
                raise ValueError(
                    f"因子 {name} 的 index/columns 与参考不一致, "
                    f"请先在 Pipeline 中对齐"
                )
        return dict(factor_dict)

    else:
        raise ValueError(
            f"未知 align_mode: {align_mode}, "
            f"支持: 'intersection' / 'union_nan' / 'raise_on_mismatch'"
        )


def stack_factors_cross_section(
    factor_dict: Dict[str, pd.DataFrame],
    align_mode: str = 'intersection',
) -> Tuple[np.ndarray, List[str], pd.Index, pd.Index]:
    """堆叠 K 个因子为 (N·T, K) 横截面面板

    将 K 个 (N, T) DataFrame 堆叠为 (N·T, K) ndarray,
    用于在全样本模式下估计单一正交化矩阵 W.

    Args:
        factor_dict: {因子名: (N, T) DataFrame}
        align_mode: 对齐策略 (见 align_factors)

    Returns:
        F_stacked: (N·T, K) ndarray
        factor_names: 因子名列表 (顺序与 F_stacked 列一致)
        aligned_index: 对齐后的股票 index (N,)
        aligned_columns: 对齐后的日期 columns (T,)

    Note:
        堆叠顺序为 (stock_0_date_0, stock_0_date_1, ..., stock_1_date_0, ...),
        即先按股票再按日期. 对称正交化对此排列不敏感 (W 是排列不变的).
    """
    aligned = align_factors(factor_dict, align_mode)
    factor_names = list(aligned.keys())
    K = len(factor_names)

    first_df = aligned[factor_names[0]]
    N, T = first_df.shape

    # 构造 (N, T, K) 面板
    F_panel = np.zeros((N, T, K), dtype=np.float64)
    for k, name in enumerate(factor_names):
        F_panel[:, :, k] = aligned[name].values

    # 堆叠为 (N·T, K)
    F_stacked = F_panel.reshape(N * T, K)

    return F_stacked, factor_names, first_df.index, first_df.columns
