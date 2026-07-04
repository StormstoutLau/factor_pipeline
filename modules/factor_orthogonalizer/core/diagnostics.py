# -*- coding: utf-8 -*-
"""O3a: 正交化几何诊断 — OrthogonalizationDiagnostics

四项诊断指标:
1. VRR (Variance Retention Ratio): 方差保留率, VRR < 0.3 → 冗余
2. κ (Condition Number): 条件数 (λ_max/λ_min), κ > 1000 → 病态
3. VIF (Variance Inflation Factor): 方差膨胀因子, VIF > 5 → 多重共线性
4. 正交性误差: ‖Σ* - diag(Σ*)‖, 应接近 0

O3a.6 深化:
- O3a.6.1: VRR ddof 参数 (0=总体方差, 1=样本方差)
- O3a.6.2: VIF 多方法 (lstsq/qr/pinv) + 完美共线 inf 处理
- O3a.6.3: 条件数分级 (Belsley-Kuh-Welsch: good/acceptable/warning/severe)
- O3a.6.4: 正交性误差归一化 (frobenius/normalized/max_abs)
- O3a.6.5: JSON 序列化 (full_diagnostics_json, inf → null)

架构层: Layer 2 (无监督, 不需 Y)

数学注记 (VRR):
  VRR_k = Var(T_k) / Var(F_k)
  对称正交化使 T^T T = I (||T_k||=1), 故 Var(T_k) ≈ 1/N (mean≈0).
  对于 randn F (||F_k||≈sqrt(N), Var(F_k)≈1), VRR ≈ 1/N < 1.
  VRR = 1 仅当 F 列预归一化为单位范数时成立 (见 O1 测试 _unit_norm_F).
  文档 O3a.4 "对称正交化 VRR=1" 的期望基于 "保持方差" 直觉, 实际保持的是正交性.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Union

import numpy as np


class OrthogonalizationDiagnostics:
    """正交化几何诊断

    四项诊断指标:
    1. VRR (Variance Retention Ratio): 方差保留率, VRR < 0.3 → 冗余
    2. κ (Condition Number): 条件数, κ > 1000 → 病态
    3. VIF (Variance Inflation Factor): 方差膨胀因子, VIF > 5 → 多重共线性
    4. 正交性误差: ‖Σ* - diag(Σ*)‖_F, 应接近 0

    架构层: Layer 2 (无监督, 不需 Y)
    """

    # ── 1. VRR (方差保留率) ──────────────────────────────────

    @staticmethod
    def compute_vrr(
        F: np.ndarray,
        T: np.ndarray,
        ddof: int = 0,
    ) -> np.ndarray:
        """方差保留率 (Variance Retention Ratio)

        VRR_k = Var(T_k) / Var(F_k)
        - VRR ≈ 1: 因子 k 方差完全保留 (F 列预归一化为单位范数时)
        - VRR < 0.3: 因子 k 高度冗余或方差被压缩
        - VRR > 1: 因子 k 方差被放大 (异常, 检查数值稳定性)

        Args:
            F: (N, K) 原始因子
            T: (N, K) 正交化后因子
            ddof: 自由度调整 (0=总体方差, 1=样本方差, O3a.6.1)
                注: VRR = Var(T,ddof)/Var(F,ddof), 分子分母同时乘 N/(N-1),
                比值不变, 所以 ddof 不影响 VRR 值.

        Returns: VRR (K,) 数组, 零方差因子 VRR=0
        """
        var_F = np.var(F, axis=0, ddof=ddof)
        var_T = np.var(T, axis=0, ddof=ddof)
        # 零方差处理: var_F=0 → VRR=0 (避免除零)
        vrr = np.zeros_like(var_F, dtype=np.float64)
        mask = var_F > 0
        vrr[mask] = var_T[mask] / var_F[mask]
        return vrr

    # ── 2. 条件数 κ ──────────────────────────────────

    @staticmethod
    def compute_condition_number(F: np.ndarray) -> float:
        """条件数 κ = λ_max(F^T F) / λ_min(F^T F)

        用特征值比 (与 base.py BaseOrthogonalizer.condition_number_ 一致),
        不是 SVD 奇异值比 (σ_max/σ_min = sqrt(λ_max/λ_min)).

        - κ < 10: 良好
        - 10 ≤ κ < 100: 可接受
        - 100 ≤ κ < 1000: 警告
        - κ ≥ 1000: 病态

        Args:
            F: (N, K) 因子矩阵

        Returns: 条件数 (标量), 奇异矩阵返回 inf
        """
        G = F.T @ F
        eigvals = np.linalg.eigvalsh(G)
        eig_max = eigvals[-1]
        eig_min = eigvals[0]
        if eig_min <= 0:
            return float('inf')
        return float(eig_max / eig_min)

    @staticmethod
    def condition_number_severity(kappa: float) -> str:
        """O3a.6.3: Belsley-Kuh-Welsch 条件数四级分级

        判定规则 (Belsley, Kuh, Welsch 1980 "Regression Diagnostics"):
        - κ < 10: 'good' (无多重共线性)
        - 10 ≤ κ < 100: 'acceptable' (弱多重共线性)
        - 100 ≤ κ < 1000: 'warning' (中到强多重共线性)
        - κ ≥ 1000: 'severe' (严重多重共线性)

        Args:
            kappa: 条件数 (λ_max/λ_min)

        Returns: 'good' / 'acceptable' / 'warning' / 'severe'
        """
        if kappa < 10:
            return 'good'
        elif kappa < 100:
            return 'acceptable'
        elif kappa < 1000:
            return 'warning'
        else:
            return 'severe'

    # ── 3. VIF (方差膨胀因子) ──────────────────────────────────

    @staticmethod
    def compute_vif(
        F: np.ndarray,
        method: str = 'lstsq',
    ) -> np.ndarray:
        """O3a.6.2: 方差膨胀因子 (Variance Inflation Factor)

        VIF_k = 1 / (1 - R²_k)
        R²_k 是 F_k 对其他 K-1 个因子 (含截距) 回归的决定系数.
        - VIF < 5: 无多重共线性
        - 5 ≤ VIF < 10: 中等多重共线性
        - VIF ≥ 10: 严重多重共线性
        - VIF = inf: 完美共线 (R²=1)

        三种数值方法 (O3a.6.2):
        - 'lstsq': np.linalg.lstsq (默认, 最稳定)
        - 'qr': QR 分解求解
        - 'pinv': 伪逆求解 (对病态矩阵鲁棒)

        Args:
            F: (N, K) 因子矩阵
            method: 'lstsq' / 'qr' / 'pinv'

        Returns: VIF (K,) 数组, 完美共线因子 VIF=inf
        """
        N, K = F.shape
        if K < 2:
            # 单因子无共线性, VIF=1
            return np.ones(K, dtype=np.float64)

        vif = np.zeros(K, dtype=np.float64)
        for k in range(K):
            F_others = np.delete(F, k, axis=1)
            F_k = F[:, k]
            # 含截距的回归矩阵
            X = np.column_stack([np.ones(N), F_others])

            # 求解最小二乘
            if method == 'lstsq':
                beta, _, _, _ = np.linalg.lstsq(X, F_k, rcond=None)
            elif method == 'qr':
                Q, R = np.linalg.qr(X)
                # 解 R beta = Q^T F_k (R 是上三角)
                beta = np.linalg.solve(R, Q.T @ F_k)
            elif method == 'pinv':
                beta = np.linalg.pinv(X) @ F_k
            else:
                raise ValueError(
                    f"未知 method: {method}, 支持 'lstsq'/'qr'/'pinv'"
                )

            F_k_pred = X @ beta
            ss_res = float(np.sum((F_k - F_k_pred) ** 2))
            ss_tot = float(np.sum((F_k - np.mean(F_k)) ** 2))

            if ss_tot == 0:
                # F_k 零方差, VIF 未定义, 设为 inf
                vif[k] = float('inf')
                continue

            r2 = 1.0 - ss_res / ss_tot
            # 完美共线: R² ≥ 1 (浮点误差可能略 > 1)
            if r2 >= 1.0 - 1e-15:
                vif[k] = float('inf')
            else:
                vif[k] = 1.0 / (1.0 - r2)

        return vif

    # ── 4. 正交性误差 ──────────────────────────────────

    @staticmethod
    def compute_orthogonality_error(
        T: np.ndarray,
        norm: str = 'frobenius',
    ) -> float:
        """O3a.6.4: 正交性误差 ‖Σ - diag(Σ)‖

        Σ = T^T T (K×K 协方差/内积矩阵).
        正交化后 Σ ≈ I, 故 Σ - diag(Σ) ≈ 0.

        三种归一化 (O3a.6.4):
        - 'frobenius': ‖Σ - diag(Σ)‖_F (绝对误差, 默认)
        - 'normalized': ‖Σ - diag(Σ)‖_F / ‖Σ‖_F (相对误差, 跨 K 可比较)
        - 'max_abs': max|Σ_jk| for j≠k (最大非对角元)

        Args:
            T: (N, K) 正交化后因子
            norm: 'frobenius' / 'normalized' / 'max_abs'

        Returns: 正交性误差 (标量)
        """
        Sigma = T.T @ T
        Sigma_diag = np.diag(np.diag(Sigma))
        off_diag = Sigma - Sigma_diag

        if norm == 'frobenius':
            return float(np.linalg.norm(off_diag, 'fro'))
        elif norm == 'normalized':
            norm_sigma = float(np.linalg.norm(Sigma, 'fro'))
            if norm_sigma == 0:
                return 0.0
            return float(np.linalg.norm(off_diag, 'fro') / norm_sigma)
        elif norm == 'max_abs':
            if off_diag.size == 0:
                return 0.0
            return float(np.max(np.abs(off_diag)))
        else:
            raise ValueError(
                f"未知 norm: {norm}, 支持 'frobenius'/'normalized'/'max_abs'"
            )

    # ── 5. 完整诊断报告 ──────────────────────────────────

    @classmethod
    def full_diagnostics(
        cls,
        F: np.ndarray,
        T: np.ndarray,
    ) -> Dict[str, Union[np.ndarray, float, List[int]]]:
        """完整诊断报告

        Args:
            F: (N, K) 原始因子
            T: (N, K) 正交化后因子

        Returns:
            {
                'vrr': (K,) 方差保留率,
                'condition_number': 标量,
                'vif': (K,) 方差膨胀因子 (基于 F),
                'orthogonality_error': 标量,
                'redundant_factors': List[int],  # VRR < 0.3 的因子索引
                'multicollinear_factors': List[int],  # VIF > 5 的因子索引
            }
        """
        vrr = cls.compute_vrr(F, T)
        kappa = cls.compute_condition_number(F)
        vif = cls.compute_vif(F)
        orth_err = cls.compute_orthogonality_error(T)
        return {
            'vrr': vrr,
            'condition_number': kappa,
            'vif': vif,
            'orthogonality_error': orth_err,
            'redundant_factors': np.where(vrr < 0.3)[0].tolist(),
            'multicollinear_factors': np.where(vif > 5)[0].tolist(),
        }

    # ── 6. JSON 序列化 ──────────────────────────────────

    @classmethod
    def full_diagnostics_json(
        cls,
        F: np.ndarray,
        T: np.ndarray,
    ) -> str:
        """O3a.6.5: JSON 序列化的诊断报告

        inf → null (JSON 无 inf 表示), nan → null.

        Args:
            F: (N, K) 原始因子
            T: (N, K) 正交化后因子

        Returns: JSON 字符串
        """
        diag = cls.full_diagnostics(F, T)
        return json.dumps(_to_jsonable(diag))


def _to_jsonable(obj):
    """递归转换 numpy 类型为 JSON 可序列化类型, inf/nan → null"""
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return [_to_jsonable(v) for v in obj.tolist()]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        v = float(obj)
        return None if not np.isfinite(v) else v
    elif isinstance(obj, float):
        return None if not np.isfinite(obj) else obj
    elif isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    else:
        # 兜底: 尝试 float 转换
        try:
            v = float(obj)
            return None if not np.isfinite(v) else v
        except (TypeError, ValueError):
            return str(obj)
