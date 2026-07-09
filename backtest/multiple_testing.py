# -*- coding: utf-8 -*-
"""多重检验校正模块 (v3.0.0 T3.5)

低级多重检验校正函数, 供 unified_drift / pipelines_v2 / factor_significance 共享调用.

支持三种校正方法:
1. BH-FDR (Benjamini-Hochberg 1995) — 默认, 检测力高
2. Bonferroni — 保守, FWER 控制
3. None — 无校正 (raw p-value)

学术依据:
- Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
  JRSS-B 57(1):289-300.
- Bonferroni, C. E. (1936). "Teoria statistica delle classi e calcolo delle
  probabilità." Pubblicazioni del R Istituto Superiore di Scienze Sociali e
  Politiche di Firenze 8:3-62.

API 设计:
    apply_bh_fdr(p_values, alpha) -> (p_adj, is_significant)
    apply_bonferroni(p_values, alpha) -> (p_adj, is_significant)
    apply_no_correction(p_values, alpha) -> (p_adj, is_significant)

    p_adj: List[float] — 校正后 p 值 (与输入顺序一致)
    is_significant: List[bool] — 是否显著
"""
from typing import List, Tuple
import logging
import numpy as np

logger = logging.getLogger(__name__)


def _validate_p_values(p_values: List[float]) -> None:
    """校验 p 值合法性"""
    if len(p_values) == 0:
        return
    arr = np.asarray(p_values, dtype=float)
    if np.any(np.isnan(arr)):
        raise ValueError("p_values contains NaN")
    if np.any(arr < 0):
        raise ValueError("p_values contains negative value")
    if np.any(arr > 1):
        raise ValueError("p_values contains value > 1")


def _validate_alpha(alpha: float) -> None:
    """校验 alpha 合法性"""
    if not (0 < alpha <= 1):
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")


def apply_bh_fdr(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """BH-FDR 校正 (Benjamini-Hochberg 1995)

    控制 False Discovery Rate (FDR) — 错误拒绝数占总拒绝数的期望比例.

    公式:
        p_adj_(k) = p_(k) * K / rank, 从大到小累积 min, clip [0, 1]
        判定: 找到最大 k* 使 p_adj_(k*) <= alpha, 然后 1..k* 都显著

    Args:
        p_values: 原始 p 值列表 (顺序任意)
        alpha: 显著性水平 (默认 0.05)

    Returns:
        (p_adj, is_significant)
        p_adj: 校正后 p 值 (与输入顺序一致)
        is_significant: 是否显著 (与输入顺序一致)

    Raises:
        ValueError: p 值非法 / alpha 非法

    Reference:
        Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery
        Rate." JRSS-B 57(1):289-300.
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    K = len(p_values)
    p_arr = np.asarray(p_values, dtype=float)

    # BH 校正: 排序, 从大到小累积 min
    order = np.argsort(p_arr)
    p_adj = np.empty_like(p_arr)
    prev = 1.0
    for i in range(K - 1, -1, -1):
        rank = i + 1
        idx = order[i]
        bh = p_arr[idx] * K / rank
        prev = min(prev, bh)
        p_adj[idx] = min(prev, 1.0)

    # 显著性判定: BH step-up procedure
    # 找到最大的 k 使 p_(k) <= alpha * k / K
    sorted_p = np.sort(p_arr)
    is_sig_sorted = np.zeros(K, dtype=bool)
    k_star = 0
    for k in range(1, K + 1):
        if sorted_p[k - 1] <= alpha * k / K:
            k_star = k
    if k_star > 0:
        is_sig_sorted[:k_star] = True

    # 还原到原顺序
    is_significant = np.zeros(K, dtype=bool)
    for i in range(K):
        is_significant[order[i]] = is_sig_sorted[i]

    return p_adj.tolist(), is_significant.tolist()


def apply_bonferroni(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """Bonferroni 校正 (FWER 控制)

    控制 Family-Wise Error Rate (FWER) — 至少一个错误拒绝的概率.

    公式:
        p_adj = p * N
        判定: p_adj < alpha (等价 p < alpha / N)

    Args:
        p_values: 原始 p 值列表
        alpha: 显著性水平

    Returns:
        (p_adj, is_significant)
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    N = len(p_values)
    p_arr = np.asarray(p_values, dtype=float)
    p_adj = np.minimum(p_arr * N, 1.0)
    is_significant = (p_arr < alpha / N).tolist()

    return p_adj.tolist(), is_significant


def apply_no_correction(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """无校正 (raw p-value)

    直接用原始 p 值与 alpha 比较, 不做多重检验校正.

    Args:
        p_values: 原始 p 值列表
        alpha: 显著性水平

    Returns:
        (p_values_copy, is_significant)
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    if len(p_values) == 0:
        return [], []

    p_arr = np.asarray(p_values, dtype=float)
    is_significant = (p_arr < alpha).tolist()

    return p_arr.tolist(), is_significant


def apply_correction(
    p_values: List[float],
    method: str = 'benjamini_hochberg',
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """统一入口: 根据方法名调用对应校正

    Args:
        p_values: 原始 p 值列表
        method: 'benjamini_hochberg' | 'bonferroni' | 'none'
        alpha: 显著性水平

    Returns:
        (p_adj, is_significant)

    Raises:
        ValueError: method 不识别
    """
    if method == 'benjamini_hochberg':
        return apply_bh_fdr(p_values, alpha)
    elif method == 'bonferroni':
        return apply_bonferroni(p_values, alpha)
    elif method == 'none':
        return apply_no_correction(p_values, alpha)
    else:
        raise ValueError(
            f"Unknown correction method: {method}. "
            f"Supported: benjamini_hochberg, bonferroni, none"
        )


def apply_by_fdr(
    p_values: List[float],
    alpha: float = 0.05,
) -> Tuple[List[float], List[bool]]:
    """Benjamini-Yekutieli FDR 校正 (依赖稳健, §3 L3 扩展, v3.1.0 E2).

    BY-FDR 在 BH 基础上引入调和数校正 C(m) = Σ_{i=1}^{m} 1/i,
    当检验相关性未知时更保守但更稳健.

    数学: p_adj_BY_(k) = p_(k) * m * C(m) / rank, C(m) = H_m (调和数)

    与 multiple_testing.py 现有 API (apply_bh_fdr / apply_correction) 一致,
    返回 Tuple[List[float], List[bool]] = (p_adj, is_significant).

    Args:
        p_values: p 值列表
        alpha: 显著性水平

    Returns:
        (p_adj, is_significant): p_adj 为校正后 p 值列表,
            is_significant 为是否显著 (p_adj < alpha) 的布尔列表.
            解包方式: p_adj, is_sig = apply_by_fdr(p_values, alpha)
    """
    _validate_alpha(alpha)
    _validate_p_values(p_values)

    m = len(p_values)
    if m == 0:
        return [], []

    # 调和数 C(m) = Σ_{i=1}^{m} 1/i
    c_m = sum(1.0 / i for i in range(1, m + 1))

    p_arr = np.asarray(p_values, dtype=float)

    # BY 校正: 排序, p_adj_(k) = p_(k) * m * C(m) / rank, 从大到小累积 min
    order = np.argsort(p_arr)
    sorted_p = p_arr[order]
    ranks = np.arange(1, m + 1)
    adjusted_sorted = sorted_p * m * c_m / ranks
    # 累积 min (从大到小), 保持单调性
    adjusted_sorted = np.minimum.accumulate(adjusted_sorted[::-1])[::-1]
    adjusted_sorted = np.clip(adjusted_sorted, 0, 1)

    # 还原到原顺序
    adjusted_p = np.empty(m)
    adjusted_p[order] = adjusted_sorted

    is_significant = (adjusted_p < alpha).tolist()

    return adjusted_p.tolist(), is_significant


# ============================================================
# E1: PowerCurveAnalyzer (Monte Carlo 检测力曲线)
# RESEARCH_NOTES §1.4 第一块补强
# ============================================================
import matplotlib  # noqa: E402

matplotlib.use("Agg")  # 非交互后端, 避免 display 问题
import matplotlib.pyplot as plt  # noqa: E402
from typing import Optional, Dict, Any  # noqa: E402
from scipy import stats as sps  # noqa: E402


class PowerCurveAnalyzer:
    """Monte Carlo 检测力曲线分析器 (RESEARCH_NOTES §1.4 第一块补强)

    对比 BH-FDR / Bonferroni / 无校正的检测力与经验 FDR,
    用于论文发表前补强 BH-FDR 在 KS 迁移检验中的统计性质论证.

    学术依据:
        - Cohen, J. (1988). "Statistical Power Analysis for the Behavioral
          Sciences." (effect size / Cohen's d)
        - Benjamini, Y. & Hochberg, Y. (1995). JRSS-B 57(1):289-300.
        - Bonferroni, C. E. (1936).

    检测力 (Power) 定义: 在 H1 为真时正确拒绝的概率
        Power(δ, n, K, π1) = P(reject H_k | H_k is false)

    Monte Carlo 估计:
        Power_hat = (1/n_sim) * Σ_s |{k: H_k rejected in sim s ∧ H_k is false}|
                                 / |{k: H_k is false}|

    经验 FDR:
        FDR_hat = (1/n_sim) * Σ_s |{k: H_k rejected in sim s ∧ H_k is true}|
                                / max(|{k: H_k rejected in sim s}|, 1)
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        alpha: float = 0.05,
        random_state: Optional[int] = None,
    ):
        self.n_simulations = n_simulations
        self.alpha = alpha
        self.rng = np.random.default_rng(random_state)
        self._last_fdr_curves_: Optional[Dict[str, np.ndarray]] = None

    def _simulate_p_values(
        self,
        effect_size: float,
        n_samples: int,
        n_hypotheses: int,
        true_alt_fraction: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """模拟一组 p 值, 返回 (p_values, is_true_alt)

        H0 为真的假设: p ~ Uniform(0, 1)
        H1 为真的假设: 经 Welch t 检验生成 p 值 (双样本, 不同均值)
        """
        n_true_alt = int(n_hypotheses * true_alt_fraction)
        n_true_null = n_hypotheses - n_true_alt

        # H0: p ~ U(0, 1)
        p_null = self.rng.uniform(0.0, 1.0, size=n_true_null)

        # H1: 经 Welch t 检验生成 p 值 (双样本, 不同均值)
        if n_true_alt > 0 and effect_size > 0:
            x1 = self.rng.standard_normal((n_true_alt, n_samples))
            x2 = self.rng.standard_normal((n_true_alt, n_samples)) + effect_size
            var1 = x1.var(axis=1, ddof=1) / n_samples
            var2 = x2.var(axis=1, ddof=1) / n_samples
            denom = np.sqrt(var1 + var2)
            t_stat = (x1.mean(axis=1) - x2.mean(axis=1)) / np.maximum(denom, 1e-12)
            # Welch-Satterthwaite 自由度
            df_num = (var1 + var2) ** 2
            df_den = (
                var1 ** 2 / max(n_samples - 1, 1)
                + var2 ** 2 / max(n_samples - 1, 1)
            )
            df = df_num / np.maximum(df_den, 1e-10)
            p_alt = 2.0 * (1.0 - sps.t.cdf(np.abs(t_stat), df=df))
            p_alt = np.clip(p_alt, 0.0, 1.0)
        else:
            p_alt = self.rng.uniform(0.0, 1.0, size=n_true_alt)

        p_values = np.concatenate([p_null, p_alt])
        is_true_alt = np.concatenate(
            [
                np.zeros(n_true_null, dtype=bool),
                np.ones(n_true_alt, dtype=bool),
            ]
        )
        # 随机打乱, 让 H0/H1 在位置上不固定
        perm = self.rng.permutation(n_hypotheses)
        return p_values[perm], is_true_alt[perm]

    def compute_power_curve(
        self,
        effect_sizes: np.ndarray,
        n_samples: int,
        n_hypotheses: int,
        true_alt_fraction: float,
        methods: Optional[List[str]] = None,
    ) -> Dict[str, np.ndarray]:
        """计算检测力曲线

        Args:
            effect_sizes: Cohen's d 效应量数组
            n_samples: 每个假设的样本量 (Welch t 检验每组样本数)
            n_hypotheses: 假设总数 K
            true_alt_fraction: 真实备择假设比例 π1 ∈ [0, 1]
            methods: 待比较的校正方法列表 (默认 bonferroni / BH / none)

        Returns:
            {method: np.ndarray(len(effect_sizes))} 检测力估计 ∈ [0, 1]
            副作用: 同时累计 FDR 到 self._last_fdr_curves_
        """
        if methods is None:
            methods = ["bonferroni", "benjamini_hochberg", "none"]

        effect_sizes = np.asarray(effect_sizes, dtype=float)
        power_curves = {m: np.zeros(len(effect_sizes)) for m in methods}
        fdr_curves = {m: np.zeros(len(effect_sizes)) for m in methods}

        for i, delta in enumerate(effect_sizes):
            power_acc = {m: 0.0 for m in methods}
            fdr_acc = {m: 0.0 for m in methods}
            for _ in range(self.n_simulations):
                p_vals, is_alt = self._simulate_p_values(
                    delta, n_samples, n_hypotheses, true_alt_fraction
                )
                n_true_alt = int(is_alt.sum())
                n_true_null = n_hypotheses - n_true_alt
                for m in methods:
                    _, rejected = apply_correction(
                        p_vals.tolist(), method=m, alpha=self.alpha
                    )
                    rejected = np.asarray(rejected, dtype=bool)
                    # Power: 在 H1 为真时拒绝的比例
                    if n_true_alt > 0:
                        power_acc[m] += float((rejected & is_alt).sum()) / n_true_alt
                    # FDR: 在 H0 为真时拒绝数 / 总拒绝数
                    n_rejected = int(rejected.sum())
                    if n_rejected > 0 and n_true_null > 0:
                        fdr_acc[m] += float((rejected & ~is_alt).sum()) / n_rejected
                    elif n_rejected > 0 and n_true_null == 0:
                        # 全是 H1, 没有假拒绝
                        fdr_acc[m] += 0.0
                    else:
                        # 无拒绝, 该次贡献 0
                        fdr_acc[m] += 0.0
            for m in methods:
                power_curves[m][i] = power_acc[m] / self.n_simulations
                fdr_curves[m][i] = fdr_acc[m] / self.n_simulations

        self._last_fdr_curves_ = fdr_curves
        return power_curves

    def compute_fdr_vs_power(
        self,
        effect_sizes: np.ndarray,
        n_samples: int,
        n_hypotheses: int,
        true_alt_fraction: float,
        methods: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """同时计算检测力曲线与经验 FDR 曲线

        Returns:
            {'power': {method: np.ndarray}, 'fdr': {method: np.ndarray}}
        """
        power_curves = self.compute_power_curve(
            effect_sizes=effect_sizes,
            n_samples=n_samples,
            n_hypotheses=n_hypotheses,
            true_alt_fraction=true_alt_fraction,
            methods=methods,
        )
        # compute_power_curve 已填充 _last_fdr_curves_
        fdr_curves = self._last_fdr_curves_ or {m: np.zeros_like(arr) for m, arr in power_curves.items()}
        return {"power": power_curves, "fdr": fdr_curves}

    def plot_power_curve(
        self,
        result: Dict[str, np.ndarray],
        save_path: Optional[str] = None,
    ):
        """绘制检测力曲线

        Args:
            result: compute_power_curve 返回的 {method: np.ndarray} 字典
                    (也接受 compute_fdr_vs_power 返回的 {'power': {...}} 嵌套字典)
            save_path: 若给定, 保存到该路径; 否则仅返回 Figure

        Returns:
            matplotlib.figure.Figure
        """
        # 兼容 compute_fdr_vs_power 的嵌套结构
        if "power" in result and isinstance(result["power"], dict):
            curves = result["power"]
        else:
            curves = result

        fig, ax = plt.subplots(figsize=(8, 5))
        # 固定颜色顺序便于对比
        colors = {
            "none": "#1f77b4",
            "benjamini_hochberg": "#2ca02c",
            "bonferroni": "#d62728",
        }
        labels = {
            "none": "No correction",
            "benjamini_hochberg": "BH-FDR",
            "bonferroni": "Bonferroni",
        }
        for m, arr in curves.items():
            xs = np.arange(len(arr))
            ax.plot(
                xs,
                arr,
                marker="o",
                label=labels.get(m, m),
                color=colors.get(m, None),
            )
        ax.set_xlabel("Effect size index")
        ax.set_ylabel("Power")
        ax.set_title("Power Curve: BH-FDR vs Bonferroni vs No correction")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        fig.tight_layout()
        if save_path is not None:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
        return fig


# ============================================================
# E2: Romano-Wolf (2005) k-FWER Bootstrap 校正
# RESEARCH_NOTES §1.4 第二块补强
# ============================================================
# 注意: 严格遵循 task 约束 — 不修改 apply_correction 签名, 不向 method 枚举
# 新增 'romano_wolf'. Romano-Wolf 仅通过独立函数 apply_romano_wolf 接入.
#
# 学术依据: Romano & Wolf (2005) "Stepwise Multiple Testing as Formalized
# Data Snooping"
#
# k-FWER 控制: 至多 k 个假拒绝的概率 ≤ α
#     P(|{i ∈ I0: reject H_i}| ≥ k) ≤ α
# 当 k=1 时等价于强 FWER 控制.
#
# Stepdown 程序:
#   1. 排序 p 值: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
#   2. 对每个 j, 计算 bootstrap 临界值 c_{j,k}:
#        c_{j,k} = Quantile_{1-α}(k-th smallest of {p*_{i,(1)}, ..., p*_{i,(j)}}_{i=1}^B)
#   3. 若 p_(j) ≤ c_{j,k}, 拒绝 H_(1), ..., H_(j); 否则停止


def _romano_wolf_stepdown(
    p_arr: np.ndarray,
    bootstrap_p_values: np.ndarray,
    alpha: float,
    k: int,
) -> Tuple[List[float], List[bool]]:
    """Romano-Wolf stepdown 程序 (更有检测力)

    Args:
        p_arr: 长度 m 的原始 p 值数组
        bootstrap_p_values: (B, m) 的 bootstrap p 值矩阵
        alpha: 显著性水平
        k: k-FWER 中的 k

    Returns:
        (adjusted_p_values, rejected) — 长度均为 m, 顺序与 p_arr 一致

    算法:
        1. 排序 p 值: p_(1) ≤ ... ≤ p_(m)
        2. 对每个 j, 计算调整后 p 值:
              p_adj_(j) = P*(k-th smallest of {p*_(1), ..., p*_(j)} ≤ p_(j))
           即经验 CDF: mean(kth_in_sub ≤ p_(j))
        3. 强制单调 (累积最大): p_adj_(j) = max(p_adj_(1), ..., p_adj_(j))
        4. 拒绝 H_(1), ..., H_(j*) 其中 j* 为最大使 p_adj_(j*) ≤ α 的索引
    """
    m = len(p_arr)
    if m == 0:
        return [], []
    # 排序索引 (稳定排序避免 ties 时顺序跳变)
    order = np.argsort(p_arr, kind="stable")
    sorted_p = p_arr[order]
    # bootstrap 每行排序
    sorted_boot = np.sort(bootstrap_p_values, axis=1)  # (B, m)

    # ---- 调整后 p 值 (经验 CDF) ----
    adjusted_sorted = np.zeros(m)
    for j in range(m):
        # 在每行前 (j+1) 个最小 bootstrap p 值中取第 k 小
        submatrix = sorted_boot[:, : j + 1]  # (B, j+1)
        if submatrix.shape[1] >= k:
            kth_in_sub = np.sort(submatrix, axis=1)[:, k - 1]
        else:
            # 列数 < k, 退化为取该行最大 (第 j+1 小)
            kth_in_sub = submatrix[:, -1]
        # p_adj_(j) = P*(kth_in_sub ≤ p_(j))  (经验 CDF)
        adjusted_sorted[j] = float(np.mean(kth_in_sub <= sorted_p[j]))
    # 累积最大 (stepdown 单调性: p_adj 应非减)
    adjusted_sorted = np.maximum.accumulate(adjusted_sorted)
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)

    # ---- 拒绝判定 (stepdown: 找最大 j* 使 p_adj_(j*) ≤ α, 拒绝 1..j*) ----
    rejected_sorted = np.zeros(m, dtype=bool)
    for j in range(m):
        if adjusted_sorted[j] <= alpha:
            rejected_sorted[j] = True
        else:
            break  # stepdown: 一旦不拒绝, 后续都不拒绝

    # 还原原始顺序
    rejected = np.zeros(m, dtype=bool)
    rejected[order] = rejected_sorted
    adjusted = np.zeros(m)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist(), rejected.tolist()


def apply_romano_wolf(
    p_values: List[float],
    bootstrap_p_values: np.ndarray,
    alpha: float = 0.05,
    k: int = 1,
    method: str = "stepdown",
) -> Tuple[List[float], List[bool]]:
    """Romano-Wolf (2005) k-FWER Bootstrap 校正

    控制弱 FWER (k-FWER): 至多 k 个假拒绝的概率 ≤ α.
    当 k=1 时等价于强 FWER 控制.

    学术依据: Romano & Wolf (2005) "Stepwise Multiple Testing as Formalized
    Data Snooping"

    Args:
        p_values: 长度 m 的原始 p 值列表
        bootstrap_p_values: (B, m) 的 bootstrap p 值矩阵, B = bootstrap 次数
            每行是一次 bootstrap 重抽样下的 p 值 (在 H0 下生成)
        alpha: 显著性水平 (默认 0.05)
        k: k-FWER 中的 k, 默认 1 (强 FWER)
        method: 'stepdown' (默认, 更有检测力) 或 'single_step'

    Returns:
        (adjusted_p_values, rejected) 元组
        adjusted_p_values: 长度 m 的调整后 p 值
        rejected: 长度 m 的布尔列表, True 表示拒绝 H0

    Note:
        本函数为独立入口, 不修改 `apply_correction` 签名, 也不向其 `method`
        枚举新增 'romano_wolf' (因为 RW 需要额外的 bootstrap 数据输入).
    """
    _validate_alpha(alpha)
    p_arr = np.asarray(p_values, dtype=float)
    boot = np.asarray(bootstrap_p_values, dtype=float)
    if boot.ndim != 2:
        raise ValueError(
            f"bootstrap_p_values 必须是 2D (B, m), 实际 ndim={boot.ndim}"
        )
    if boot.shape[1] != len(p_arr):
        raise ValueError(
            f"bootstrap_p_values 列数 ({boot.shape[1]}) ≠ len(p_values) ({len(p_arr)})"
        )
    if k < 1:
        raise ValueError(f"k 必须 ≥ 1, 实际 {k}")
    if len(p_arr) == 0:
        return [], []

    if method == "stepdown":
        return _romano_wolf_stepdown(p_arr, boot, alpha, k)
    elif method == "single_step":
        # single-step: 调整 p 值 p_adj[i] = P*(k-th smallest of bootstrap row ≤ p[i])
        # 拒绝: p_adj[i] ≤ α
        m = len(p_arr)
        k_idx = min(k - 1, m - 1)
        kth_smallest = np.sort(boot, axis=1)[:, k_idx]
        adjusted = np.array(
            [float(np.mean(kth_smallest <= p_arr[i])) for i in range(m)]
        )
        adjusted = np.clip(adjusted, 0.0, 1.0)
        rejected = (adjusted <= alpha).tolist()
        return adjusted.tolist(), rejected
    else:
        raise ValueError(
            f"Unknown method: {method}. Supported: 'stepdown', 'single_step'"
        )


def _generate_bootstrap_p_values_for_ks(
    historical_data: "pd.DataFrame",
    recent_data: "pd.DataFrame",
    n_bootstrap: int = 1000,
    random_state: Optional[int] = None,
) -> np.ndarray:
    """为 KS 迁移检验生成 bootstrap p 值矩阵

    在 H0 (两样本同分布) 假设下, 对合并样本重抽样生成 bootstrap p 值.

    Args:
        historical_data: 历史期数据 (n_hist, K)
        recent_data: 近期数据 (n_recent, K)
        n_bootstrap: bootstrap 次数
        random_state: 随机种子

    Returns:
        (n_bootstrap, K) 的 bootstrap p 值矩阵
    """
    import pandas as pd  # 局部导入, 避免模块顶层依赖
    rng = np.random.default_rng(random_state)
    n_hist = len(historical_data)
    n_recent = len(recent_data)
    common_cols = historical_data.columns.intersection(recent_data.columns)
    pooled = pd.concat(
        [historical_data[common_cols], recent_data[common_cols]], axis=0
    )
    n_pooled = len(pooled)
    K = len(common_cols)
    bootstrap_p = np.zeros((n_bootstrap, K))
    pooled_vals = pooled[common_cols].to_numpy()  # (n_pooled, K) 加速
    for b in range(n_bootstrap):
        idx = rng.integers(0, n_pooled, size=n_pooled)
        boot_sample = pooled_vals[idx]
        boot_hist = boot_sample[:n_hist]
        boot_recent = boot_sample[n_hist : n_hist + n_recent]
        for j in range(K):
            a = boot_hist[:, j]
            b_col = boot_recent[:, j]
            # 过滤 NaN
            a_valid = a[~np.isnan(a)]
            b_valid = b_col[~np.isnan(b_col)]
            if len(a_valid) < 2 or len(b_valid) < 2:
                bootstrap_p[b, j] = 1.0
                continue
            _, p_val = sps.ks_2samp(a_valid, b_valid)
            bootstrap_p[b, j] = p_val
    return bootstrap_p


# ============================================================
# E3: White Reality Check (2000) + Hansen SPA (2005)
# RESEARCH_NOTES §1.4 第三块补强
# ============================================================
# 学术依据:
#   - White (2000) "A Reality Check for Data Snooping"
#   - Hansen (2005) "A Test for Superior Predictive Ability"
#   - Politis & Romano (1994) "The Stationary Bootstrap"
#
# 函数式接口 (per task description):
#   apply_white_reality_check(strategy_returns, benchmark_return, ...)
#       -> Tuple[float, bool]  (p_value, is_significant)
#   apply_hansen_spa(strategy_returns, benchmark_return, ...)
#       -> Tuple[float, bool]
#
# block_size 默认: max(1, int(T**(1/3)))


def _stationary_bootstrap_index(T: int, block_size: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano (1994) stationary bootstrap 索引生成

    每个位置以概率 1/block_size 重新开始新块 (随机选起点), 否则延续上一位置.
    保留序列的弱相依结构. 使用模 T 循环边界.
    """
    idx = np.empty(T, dtype=np.intp)
    idx[0] = int(rng.integers(0, T))
    prob_new = 1.0 / float(block_size)
    # 批量生成 u 以加速
    u = rng.random(T - 1)
    for t in range(1, T):
        if u[t - 1] < prob_new:
            idx[t] = int(rng.integers(0, T))
        else:
            idx[t] = (idx[t - 1] + 1) % T
    return idx


def _auto_block_size(T: int) -> int:
    """自动块大小: max(1, int(T**(1/3)))

    Politis-Romano 经验法则的简化版 (per task description).
    """
    return max(1, int(round(T ** (1.0 / 3.0))))


def _estimate_long_run_var(x: np.ndarray) -> float:
    """长期方差估计 omega^2 = sum_{l=-inf}^{inf} gamma(l)

    用 Newey-West 估计:
        omega^2 = gamma(0) + 2 * sum_{l=1}^{L} (1 - l/(L+1)) * gamma(l)
    滞后阶数 L = max(1, int(floor(4 * (T/100)^(2/9))))
    """
    T = len(x)
    if T < 2:
        return 1e-10
    x_centered = x - x.mean()
    gamma0 = float(np.var(x, ddof=1))
    L = max(1, int(np.floor(4 * (T / 100.0) ** (2.0 / 9.0))))
    L = min(L, T - 1)
    omega_sq = gamma0
    for l in range(1, L + 1):
        gamma_l = float(np.mean(x_centered[l:] * x_centered[:-l]))
        omega_sq += 2.0 * (1.0 - l / (L + 1)) * gamma_l
    return max(omega_sq, 1e-10)


def apply_white_reality_check(
    strategy_returns: np.ndarray,
    benchmark_return: np.ndarray,
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    block_size: Optional[int] = None,
    random_state: Optional[int] = None,
) -> Tuple[float, bool]:
    """White (2000) Reality Check — 策略回测 data snooping 校正

    检验 K 个策略中是否至少有一个显著优于基准, 控制因搜遍 K 个策略而引入的
    data snooping bias. 通过 stationary bootstrap (Politis-Romano 1994) 估计
    最大统计量的零分布.

    数学公式:
        f_bar_k = (1/T) Σ_t (r_{k,t} - r_{b,t})
        V = max_k sqrt(T) * f_bar_k                          (检验统计量)
        V*_b = max_k sqrt(T) * (f*_bar_k - f_bar_k)          (recentered bootstrap)
        p_value = (1/N) Σ_b 1(V*_b >= V)

    Args:
        strategy_returns: (T, K) K 个策略的收益序列
        benchmark_return: (T,) 基准策略收益
        n_bootstrap: bootstrap 次数 (默认 1000)
        alpha: 显著性水平 (默认 0.05)
        block_size: stationary bootstrap 块大小; None 时自动估计 max(1, int(T^(1/3)))
        random_state: 随机种子

    Returns:
        (p_value, is_significant)
        p_value: White RC 校正后 p 值 ∈ [0, 1]
        is_significant: p_value < alpha

    Note:
        向后兼容别名, 内部调用 :class:`WhiteRealityCheck` 类接口.
    """
    _validate_alpha(alpha)
    strat = np.asarray(strategy_returns, dtype=float)
    bench = np.asarray(benchmark_return, dtype=float)
    if strat.ndim != 2:
        raise ValueError(
            f"strategy_returns 必须是 2D (T, K), 实际 ndim={strat.ndim}"
        )
    if bench.ndim != 1:
        raise ValueError(
            f"benchmark_return 必须是 1D (T,), 实际 ndim={bench.ndim}"
        )
    T, K = strat.shape
    if len(bench) != T:
        raise ValueError(
            f"benchmark_return 长度 ({len(bench)}) ≠ strategy_returns 行数 ({T})"
        )
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap 必须 ≥ 1, 实际 {n_bootstrap}")

    # 构造 returns_matrix: 基准作为第 0 列, 策略作为其余列, 委托类接口
    returns_matrix = np.column_stack([bench, strat])  # (T, K+1)
    wrc = WhiteRealityCheck(
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        method='stationary',
        random_state=random_state,
    )
    result = wrc.test(returns_matrix, benchmark_index=0, alpha=alpha)
    p_value = result['rc_p_value']
    return p_value, bool(p_value < alpha)


def apply_hansen_spa(
    strategy_returns: np.ndarray,
    benchmark_return: np.ndarray,
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    block_size: Optional[int] = None,
    random_state: Optional[int] = None,
) -> Tuple[float, bool]:
    """Hansen (2005) Superior Predictive Ability — White RC 的改进版

    通过重新中心化 (recentering) 提升对真正优秀策略的检测力. 区分 H1 集合
    (显著优于基准) 和 H0 集合 (待检验), 仅对 H0 集合施加 data snooping 校正.

    关键改进 (基于 Law of the Iterated Logarithm, LIL):
        若 sqrt(n) * f_bar_k / omega_k <= -sqrt(2 log log n)
        则第 k 个模型被判为"太差", 在构造零分布时被 recentered 到零, 避免拉高
        临界值. 等价地: f_bar_k <= -sqrt(omega^2_k / n) * sqrt(2 log log n)
        为"太差"条件; 其反为"保留 (in H1)"条件.

    三区域 partitioning:
        - lower consistent (lc): 假设所有 H0 都是真 H0 (最保守)
        - consistent: 用阈值重新判定 H1 (默认返回的 p 值)
        - upper consistent (uc): 假设所有 H0 都是真 H1 (最宽松)
        单调性: lc ≤ consistent ≤ uc

    Args:
        strategy_returns: (T, K) K 个策略的收益序列
        benchmark_return: (T,) 基准策略收益
        n_bootstrap: bootstrap 次数 (默认 1000)
        alpha: 显著性水平 (默认 0.05)
        block_size: stationary bootstrap 块大小; None 时自动估计 max(1, int(T^(1/3)))
        random_state: 随机种子

    Returns:
        (p_value, is_significant)
        p_value: Hansen SPA consistent p 值 ∈ [0, 1]
        is_significant: p_value < alpha

    Note:
        向后兼容别名, 内部调用 :class:`HansenSPA` 类接口.
    """
    _validate_alpha(alpha)
    strat = np.asarray(strategy_returns, dtype=float)
    bench = np.asarray(benchmark_return, dtype=float)
    if strat.ndim != 2:
        raise ValueError(
            f"strategy_returns 必须是 2D (T, K), 实际 ndim={strat.ndim}"
        )
    if bench.ndim != 1:
        raise ValueError(
            f"benchmark_return 必须是 1D (T,), 实际 ndim={bench.ndim}"
        )
    T, K = strat.shape
    if len(bench) != T:
        raise ValueError(
            f"benchmark_return 长度 ({len(bench)}) ≠ strategy_returns 行数 ({T})"
        )
    if T < 3:
        raise ValueError(f"Hansen SPA 需 T ≥ 3 (计算 log log T), 实际 {T}")
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap 必须 ≥ 1, 实际 {n_bootstrap}")

    # 构造 returns_matrix: 基准作为第 0 列, 策略作为其余列, 委托类接口
    returns_matrix = np.column_stack([bench, strat])  # (T, K+1)
    spa = HansenSPA(
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        method='stationary',
        random_state=random_state,
    )
    result = spa.test(returns_matrix, benchmark_index=0, alpha=alpha)
    p_value = result['spa_p_value']
    return p_value, bool(p_value < alpha)


# ============================================================
# E3 类接口: WhiteRealityCheck + HansenSPA
# RESEARCH_NOTES §1.4 第三块补强 (spec L566-569)
# ============================================================


class WhiteRealityCheck:
    """White (2000) Reality Check — 类接口 (RESEARCH_NOTES §1.4 E3)

    校正策略回测中的 data snooping bias: 当从 K 个策略中选最佳时,
    最佳策略的表现被向上偏误. White RC 通过 stationary/circular bootstrap
    重估最大统计量分布, 提供 data snooping 校正后的 p 值.

    学术依据: White (2000) "A Reality Check for Data Snooping"
    Bootstrap: Politis & Romano (1994) "The Stationary Bootstrap"

    接口:
        wrc = WhiteRealityCheck(n_bootstrap=1000, method='stationary', random_state=42)
        result = wrc.test(returns_matrix, benchmark_index=0)  # 返回 7 字段 Dict
    """

    def __init__(
        self,
        n_bootstrap: int = 1000,
        block_size: Optional[int] = None,
        method: str = 'stationary',
        random_state: Optional[int] = None,
    ):
        if n_bootstrap < 1:
            raise ValueError(f"n_bootstrap 必须 ≥ 1, 实际 {n_bootstrap}")
        if method not in ('stationary', 'circular'):
            raise ValueError(
                f"method 必须为 'stationary' 或 'circular', 实际 {method}"
            )
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size  # None 时自动估计 (含 rho 的 Politis-Romano 公式)
        self.method = method
        self.rng = np.random.default_rng(random_state)

    def _auto_block_size(self, x: np.ndarray) -> float:
        """Politis-Romano (1994) 自动块大小估计: B = (2T)^(1/3) * rho^(2/3)

        含一阶自相关系数 rho (spec L638-644). 若 rho <= 0 或 NaN (无正自相关),
        返回 2.0 (退化情况, 避免块大小为 0).
        """
        T = len(x)
        if T <= 2:
            return 2.0
        rho = float(np.corrcoef(x[:-1], x[1:])[0, 1])
        if np.isnan(rho) or rho <= 0:
            return 2.0
        B = (2.0 * T) ** (1.0 / 3.0) * rho ** (2.0 / 3.0)
        return float(max(np.ceil(B), 1.0))

    def _circular_block_bootstrap(self, x: np.ndarray, block_size: int) -> np.ndarray:
        """Circular block bootstrap (spec L571)

        将序列划分为固定大小的连续块, 块起点随机, 索引以模 T 环绕.
        保留序列的弱相依结构. 与 stationary bootstrap 不同, 块大小固定.
        """
        T = len(x)
        if T == 0:
            return x
        B = max(int(block_size), 1)
        idx = np.empty(T, dtype=np.intp)
        pos = 0
        while pos < T:
            start = int(self.rng.integers(0, T))
            take = min(B, T - pos)
            for i in range(take):
                idx[pos + i] = (start + i) % T
            pos += take
        return x[idx]

    def _stationary_block_bootstrap(self, x: np.ndarray, block_size: float) -> np.ndarray:
        """Politis-Romano (1994) stationary block bootstrap

        每个位置以概率 1/block_size 重新开始新块 (随机选起点), 否则延续上一位置.
        保留序列的弱相依结构. 使用模 T 循环边界. 块大小几何分布 (期望 = block_size).
        """
        T = len(x)
        if T == 0:
            return x
        idx = np.empty(T, dtype=np.intp)
        idx[0] = int(self.rng.integers(0, T))
        prob_new = 1.0 / float(block_size)
        # 批量生成均匀随机数以加速 (与 _stationary_bootstrap_index 保持一致)
        u = self.rng.random(T - 1)
        for t in range(1, T):
            if u[t - 1] < prob_new:
                idx[t] = int(self.rng.integers(0, T))
            else:
                idx[t] = (idx[t - 1] + 1) % T
        return x[idx]

    def _bootstrap(self, x: np.ndarray, block_size) -> np.ndarray:
        """根据 method 选择 bootstrap 方法 (stationary / circular)"""
        if self.method == 'circular':
            return self._circular_block_bootstrap(x, int(round(float(block_size))))
        return self._stationary_block_bootstrap(x, float(block_size))

    def _estimate_long_run_var(self, x: np.ndarray) -> float:
        """长期方差估计 omega^2 (Newey-West), 复用模块级函数"""
        return _estimate_long_run_var(x)

    def test(
        self,
        returns_matrix: np.ndarray,
        benchmark_index: int = 0,
        alpha: float = 0.05,
    ) -> Dict[str, Any]:
        """执行 White Reality Check

        Args:
            returns_matrix: (T, N) 收益矩阵, 其中一列为基准 (由 benchmark_index 指定),
                            其余 N-1 列为待检验策略.
            benchmark_index: 基准列索引 (默认 0).
            alpha: 显著性水平 (默认 0.05).

        Returns:
            Dict 含 7 字段:
                rc_p_value: float — White RC 校正后 p 值
                rc_rejected: List[bool] — 各策略是否通过 RC 校正 (联合检验)
                max_statistic: float — max_k sqrt(T) * f_bar_k
                bootstrap_max_stats: np.ndarray — (N,) bootstrap 分布
                individual_p_values: List[float] — 各策略单独 p 值 (无校正)
                n_strategies: int — 策略数 K
                block_size: float — 实际使用的块大小
        """
        _validate_alpha(alpha)
        R = np.asarray(returns_matrix, dtype=float)
        if R.ndim != 2:
            raise ValueError(
                f"returns_matrix 必须是 2D (T, N), 实际 ndim={R.ndim}"
            )
        T, N = R.shape
        if T < 2:
            raise ValueError(f"样本量 T 必须 ≥ 2, 实际 {T}")
        if not (0 <= benchmark_index < N):
            raise ValueError(
                f"benchmark_index {benchmark_index} 越界 (N={N})"
            )

        # 提取基准列与策略列 (排除基准列)
        bench = R[:, benchmark_index]
        mask = np.ones(N, dtype=bool)
        mask[benchmark_index] = False
        strat = R[:, mask]  # (T, K)
        if strat.ndim == 1:
            strat = strat.reshape(T, 1)
        K = strat.shape[1]

        excess = strat - bench[:, None]  # (T, K)
        f_bar = excess.mean(axis=0)  # (K,)
        sqrt_T = np.sqrt(T)
        # 检验统计量 V = max_k sqrt(T) * f_bar_k
        V = float(sqrt_T * np.max(f_bar)) if K > 0 else 0.0

        # 块大小: 用户指定或自动估计 (用第 0 个策略的 excess 估计 rho)
        if self.block_size is not None:
            B = float(self.block_size)
        else:
            B = self._auto_block_size(excess[:, 0]) if K > 0 else 2.0

        # Bootstrap 主循环: 在 H0 (无策略优于基准) 下重新中心化为 f_bar
        bootstrap_max_stats = np.zeros(self.n_bootstrap)
        for b in range(self.n_bootstrap):
            boot_excess = np.empty_like(excess)
            for k in range(K):
                boot_excess[:, k] = self._bootstrap(excess[:, k], B)
            f_boot = boot_excess.mean(axis=0)
            # recenter by f_bar (White RC: under H0, f_bar = 0)
            V_boot = float(sqrt_T * np.max(f_boot - f_bar)) if K > 0 else 0.0
            bootstrap_max_stats[b] = V_boot

        rc_p_value = float(np.mean(bootstrap_max_stats >= V))
        rc_p_value = min(max(rc_p_value, 0.0), 1.0)

        # 各策略单独 p 值 (无校正): 单策略 bootstrap 检验
        individual_p: List[float] = []
        for k in range(K):
            f_k = excess[:, k]
            B_k = self.block_size if self.block_size is not None else self._auto_block_size(f_k)
            boot_k = np.array([
                self._bootstrap(f_k, B_k).mean()
                for _ in range(self.n_bootstrap)
            ])
            stat_k = sqrt_T * f_bar[k]
            boot_stat_k = sqrt_T * (boot_k - f_bar[k])
            p_k = float(np.mean(boot_stat_k >= stat_k))
            individual_p.append(min(max(p_k, 0.0), 1.0))

        # 校正后拒绝: White RC 是联合检验, rc_p < alpha 则拒绝 (所有策略一致)
        rc_rejected: List[bool] = [rc_p_value < alpha] * K

        return {
            'rc_p_value': rc_p_value,
            'rc_rejected': rc_rejected,
            'max_statistic': V,
            'bootstrap_max_stats': bootstrap_max_stats,
            'individual_p_values': individual_p,
            'n_strategies': K,
            'block_size': float(B),
        }


class HansenSPA(WhiteRealityCheck):
    """Hansen (2005) Superior Predictive Ability — 类接口 (RESEARCH_NOTES §1.4 E3)

    SPA 是 White RC 的改进版, 通过重新中心化 (recentering) 提升对真正优秀策略的
    检测力. 区分 H1 集合 (显著优于基准, 不需校正) 和 H0 集合 (待检验), 仅对 H0
    集合施加 data snooping 校正.

    三区域 partitioning:
        - lower consistent (lc): 假设所有 H0 都是真 H0 (最保守, p 最大)
        - consistent: 用 LIL 阈值重新判定 H1 (默认返回的 p 值)
        - upper consistent (uc): 假设所有 H0 都是真 H1 (最宽松, p 最小)
        单调性: p_lc ≥ p ≥ p_uc

    学术依据: Hansen (2005) "A Test for Superior Predictive Ability"

    接口:
        spa = HansenSPA(n_bootstrap=1000, method='stationary', random_state=42)
        result = spa.test(returns_matrix, benchmark_index=0)  # 返回 8 字段 Dict
    """

    def test(
        self,
        returns_matrix: np.ndarray,
        benchmark_index: int = 0,
        alpha: float = 0.05,
    ) -> Dict[str, Any]:
        """执行 Hansen SPA 检验

        Args:
            returns_matrix: (T, N) 收益矩阵, 其中一列为基准 (由 benchmark_index 指定),
                            其余 N-1 列为待检验策略.
            benchmark_index: 基准列索引 (默认 0).
            alpha: 显著性水平 (默认 0.05).

        Returns:
            Dict 含 8 字段:
                spa_p_value: float — SPA consistent p 值
                spa_lc_p_value: float — SPA lower consistent p 值 (最保守)
                spa_uc_p_value: float — SPA upper consistent p 值 (最宽松)
                rejected: List[bool] — 各策略是否通过 SPA 校正
                h1_set: List[int] — H1 集合索引 (显著优于基准, 不需校正)
                h0_set: List[int] — H0 集合索引 (待校正)
                max_statistic: float — SPA 检验统计量
                block_size: float — 实际使用的块大小
        """
        _validate_alpha(alpha)
        R = np.asarray(returns_matrix, dtype=float)
        if R.ndim != 2:
            raise ValueError(
                f"returns_matrix 必须是 2D (T, N), 实际 ndim={R.ndim}"
            )
        T, N = R.shape
        if T < 3:
            raise ValueError(
                f"Hansen SPA 需 T ≥ 3 (计算 log log T), 实际 {T}"
            )
        if not (0 <= benchmark_index < N):
            raise ValueError(
                f"benchmark_index {benchmark_index} 越界 (N={N})"
            )

        # 提取基准列与策略列
        bench = R[:, benchmark_index]
        mask = np.ones(N, dtype=bool)
        mask[benchmark_index] = False
        strat = R[:, mask]  # (T, K)
        if strat.ndim == 1:
            strat = strat.reshape(T, 1)
        K = strat.shape[1]

        excess = strat - bench[:, None]  # (T, K)
        f_bar = excess.mean(axis=0)  # (K,)
        sqrt_T = np.sqrt(T)

        # 估计各策略长期方差 omega_k^2 (Newey-West)
        omega_sq = np.array(
            [self._estimate_long_run_var(excess[:, k]) for k in range(K)]
        )

        # Hansen LIL 阈值: f_bar_k > -sqrt(omega^2/T) * sqrt(2 log log T) → 保留 (H1)
        # "太差"模型 (f_bar ≤ -threshold) 在 bootstrap 零分布中被 recenter,
        # 避免拉高临界值. "保留"模型 (f_bar > -threshold) 参与最大统计量.
        log_log_T = float(np.log(np.log(T))) if T > 2 else 0.0
        sqrt_2_log_log = float(np.sqrt(2.0 * max(log_log_T, 0.0)))
        threshold = np.sqrt(omega_sq / T) * sqrt_2_log_log
        # H1 集合 (保留, 显著优于基准, 不需校正); H0 集合 (太差, 待校正)
        in_h1 = f_bar > -threshold
        in_h0 = ~in_h1

        # SPA 统计量: V = max over H1 (保留) of sqrt(T) * f_bar
        # (H0 的 f_bar << 0, 不会是最大; H1 为空时 V = 0)
        def _spa_stat(f_vals: np.ndarray, m: np.ndarray) -> float:
            if not m.any():
                return 0.0
            return float(sqrt_T * np.max(f_vals[m]))

        V_spa = _spa_stat(f_bar, in_h1)

        # 块大小
        if self.block_size is not None:
            B = float(self.block_size)
        else:
            B = self._auto_block_size(excess[:, 0]) if K > 0 else 2.0

        # Bootstrap 三区域:
        # consistent: max over H1 of (f_boot - f_bar)  [H1 重新中心化到 0 under H0]
        # lc (lower, 更保守): max over ALL of (f_boot - f_bar)  [含 H0, H0 中心化后高方差]
        # uc (upper, 更宽松): 空集 → 统计量恒 0 (假设所有 H0 都是真 H1, 无需检验)
        boot_stats = np.zeros(self.n_bootstrap)       # consistent
        boot_stats_lc = np.zeros(self.n_bootstrap)    # lower (更保守)
        boot_stats_uc = np.zeros(self.n_bootstrap)    # upper (更宽松)

        for b in range(self.n_bootstrap):
            boot_excess = np.empty_like(excess)
            for k in range(K):
                boot_excess[:, k] = self._bootstrap(excess[:, k], B)
            f_boot = boot_excess.mean(axis=0)

            # recenter: 所有策略减去 f_bar (consistent 与 lc 用此, 中心化到 0 under H0)
            f_recentered_all = f_boot - f_bar

            # consistent: max over H1 of (f_boot - f_bar)
            boot_stats[b] = _spa_stat(f_recentered_all, in_h1)
            # lower consistent: max over ALL of (f_boot - f_bar) — 包含 H0
            boot_stats_lc[b] = _spa_stat(f_recentered_all, np.ones(K, dtype=bool))
            # upper consistent: 空集 → 统计量恒 0 (所有 H0 视为真 H1, 无待检验模型)
            boot_stats_uc[b] = 0.0

        spa_p = float(np.mean(boot_stats >= V_spa))
        spa_lc_p = float(np.mean(boot_stats_lc >= V_spa))
        spa_uc_p = float(np.mean(boot_stats_uc >= V_spa))

        # 裁剪到 [0, 1]
        spa_p = min(max(spa_p, 0.0), 1.0)
        spa_lc_p = min(max(spa_lc_p, 0.0), 1.0)
        spa_uc_p = min(max(spa_uc_p, 0.0), 1.0)
        # 强制单调 (lc 更保守 → p 更大; uc 更宽松 → p 更小): p_lc ≥ p ≥ p_uc
        spa_p = max(spa_uc_p, spa_p)  # p ≥ p_uc
        spa_p = min(spa_lc_p, spa_p)  # p ≤ p_lc
        # 钳制 lc/uc 到单调区间, 确保返回值满足 p_lc ≥ p ≥ p_uc
        spa_lc_p = max(spa_lc_p, spa_p)
        spa_uc_p = min(spa_uc_p, spa_p)

        return {
            'spa_p_value': spa_p,
            'spa_lc_p_value': spa_lc_p,
            'spa_uc_p_value': spa_uc_p,
            'rejected': [spa_p < alpha] * K,
            'h1_set': np.where(in_h1)[0].tolist(),
            'h0_set': np.where(in_h0)[0].tolist(),
            'max_statistic': float(V_spa),
            'block_size': float(B),
        }
