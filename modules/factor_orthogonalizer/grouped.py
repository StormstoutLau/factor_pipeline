r"""分组正交化 — Layer 2 (O5)

组内对称正交 + 组间保留相关性

策略:
- 组内: 对称正交化 (消除同组因子冗余)
- 组间: 保留相关性 (不同经济含义的因子组不强行正交)

学术依据:
- Stambaugh-Yuan (2017) 风险因子 vs alpha 因子区别处理
- Asness (2013) Value and Momentum Everywhere
  — Value 与 Momentum 负相关 (ρ ≈ -0.4), 不应强行正交

架构层: Layer 2 (无监督变换)

O5.6.3 工程深化: 缺失因子处理 (raise / skip / fill_zero)
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from factor_pipeline.modules.factor_orthogonalizer.core.symmetric import (
    SymmetricOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.cross_sectional import (
    CrossSectionalOrthogonalizer,
)
from factor_pipeline.modules.factor_orthogonalizer.utils.stacking import (
    align_factors,
    stack_factors_cross_section,
)


class GroupedOrthogonalizer:
    """分组正交化

    组内对称正交 + 组间保留相关性

    Args:
        groups: {组名: [因子名]} 字典
        missing_factor_strategy: 缺失因子处理策略
            - 'raise' (默认): 抛 ValueError
            - 'skip': 跳过缺失因子的组 (该组不正交化)
            - 'fill_zero': 填零 (该因子贡献为 0)

    Attributes:
        orthogonalizers_: {组名: SymmetricOrthogonalizer} fit 后填充
        factor_to_group_: {因子名: 组名} 反查表
    """

    def __init__(
        self,
        groups: Dict[str, List[str]],
        missing_factor_strategy: str = 'raise',
    ):
        # 校验: 所有因子唯一
        all_factors = [f for fs in groups.values() for f in fs]
        if len(all_factors) != len(set(all_factors)):
            dup = [f for f in all_factors if all_factors.count(f) > 1]
            raise ValueError(
                f"分组中存在重复因子名: {set(dup)}"
            )
        if missing_factor_strategy not in ('raise', 'skip', 'fill_zero'):
            raise ValueError(
                f"未知 missing_factor_strategy: {missing_factor_strategy}, "
                f"支持: 'raise' / 'skip' / 'fill_zero'"
            )
        self.groups = groups
        self.missing_factor_strategy = missing_factor_strategy
        self.orthogonalizers_: Dict[str, SymmetricOrthogonalizer] = {}
        self.factor_to_group_: Dict[str, str] = {
            f: g for g, fs in groups.items() for f in fs
        }
        # 每组实际使用的因子名 (skip 后可能小于初始 groups[g])
        self.group_factors_: Dict[str, List[str]] = {}

    def fit(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        **kwargs,
    ) -> 'GroupedOrthogonalizer':
        """对每组分别估计 W (组内正交, 组间保留)

        Args:
            factor_dict: {因子名: (N, T) DataFrame}
            **kwargs: 传给 SymmetricOrthogonalizer.fit

        Returns: self
        """
        # 必要时拷贝 (fill_zero 会修改 factor_dict)
        if self.missing_factor_strategy == 'fill_zero':
            factor_dict = dict(factor_dict)  # 浅拷贝外层字典

        for group_name, factor_names in self.groups.items():
            available = [f for f in factor_names if f in factor_dict]
            missing = [f for f in factor_names if f not in factor_dict]

            if missing:
                if self.missing_factor_strategy == 'raise':
                    raise ValueError(
                        f"组 {group_name} 缺少因子: {missing} "
                        f"(可用: {available})"
                    )
                elif self.missing_factor_strategy == 'skip':
                    if len(available) < 2:
                        # 单因子或无因子, 无法正交化, 跳过该组
                        continue
                    factor_names = available
                elif self.missing_factor_strategy == 'fill_zero':
                    if not available:
                        continue  # 无参考因子, 跳过
                    ref = factor_dict[available[0]]
                    for f in missing:
                        factor_dict[f] = pd.DataFrame(
                            0.0, index=ref.index, columns=ref.columns,
                        )
                    factor_names = available + missing

            # 单因子组无法正交化 (K=1, W=[1]), 跳过
            if len(factor_names) < 2:
                continue

            # 组内对齐 + 堆叠
            group_dict = {f: factor_dict[f] for f in factor_names}
            F_stacked, _, _, _ = stack_factors_cross_section(group_dict)

            # 估计组内 W
            orth = SymmetricOrthogonalizer()
            orth.fit(F_stacked, **kwargs)
            self.orthogonalizers_[group_name] = orth
            self.group_factors_[group_name] = factor_names

        return self

    def transform(
        self,
        factor_dict: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """应用组内正交化, 组间相关性保留

        Args:
            factor_dict: {因子名: (N, T) DataFrame}

        Returns:
            Dict[str, pd.DataFrame]: 同格式, 组内正交化后因子
        """
        result: Dict[str, pd.DataFrame] = {}
        for group_name, factor_names in self.group_factors_.items():
            group_dict = {f: factor_dict[f] for f in factor_names}
            orth = self.orthogonalizers_[group_name]
            # 用 CrossSectionalOrthogonalizer 应用 W 到每期截面
            coordinator = CrossSectionalOrthogonalizer(orth)
            transformed = coordinator.transform(group_dict)
            result.update(transformed)
        # 未正交化的因子 (单因子组或被跳过的组) 原样返回
        for name, df in factor_dict.items():
            if name not in result:
                result[name] = df
        return result

    def fit_transform(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        **kwargs,
    ) -> Dict[str, pd.DataFrame]:
        """fit + transform 一步完成"""
        return self.fit(factor_dict, **kwargs).transform(factor_dict)
