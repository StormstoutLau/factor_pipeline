# -*- coding: utf-8 -*-
"""Drift-Aware Bandit Monte Carlo 验证沙箱 (RESEARCH_NOTES §2.3.2 方案 B 决策门)

三方案对比:
- Plan A (静态规则): 固定均匀权重, CUSUM 触发指纹缓存重置
- Plan B (Drift-Aware Bandit): LinUCB + CUSUM 触发遗忘 (先验重置)
- Plan C (朴素 Bandit): 标准 LinUCB, 无漂移感知 (对照组)

决策门: 仅当 Plan B 累计奖励 > Plan A × 1.10 时通过.

学术依据:
- Li, L., Chu, W., Langford, J. & Schapire, R. E. (2010). "A Contextual-Bandit
  Approach to Personalized News Article Recommendation." WWW 2010.
- Page, E. S. (1954). "Continuous Inspection Schemes." Biometrika 41(1/2):100-115.

数学公式 (LinUCB, Li et al. 2010):
    θ̂_a = (X_a^T X_a + λI)^{-1} X_a^T r_a
    UCB_a(x) = θ̂_a^T x + α * sqrt(x^T (X_a^T X_a + λI)^{-1} x)

Drift-Aware 改进: 当 CUSUM 检测到漂移时, 重置 X_a 和 r_a (遗忘历史).

体制条件上下文: x_t = [f_ar1, f_snr, f_gpd_shape, regime_dummy]

重要: 这是离线验证沙箱, 不集成进 PipelineV2Config / FactorProcessingPipelineV2.
决策门通过后才会规划 E6b (Bandit 集成, 本方案不包含).
"""
from typing import Dict, Any, Optional, Tuple
import logging

import numpy as np

from .cusum_drift_monitor import CUSUMDriftMonitor

logger = logging.getLogger(__name__)


class BanditMCSandbox:
    """Drift-Aware Bandit Monte Carlo 验证沙箱 (RESEARCH_NOTES §2.3.2 方案 B 决策门)

    目标: 验证在金融三平稳假设失效场景下, Drift-Aware Bandit (LinUCB) 是否优于静态规则.

    三方案对比:
    - Plan A (静态规则): 固定均匀权重, CUSUM 触发指纹缓存重置
    - Plan B (Drift-Aware Bandit): LinUCB + CUSUM 触发遗忘 (先验重置)
    - Plan C (朴素 Bandit): 标准 LinUCB, 无漂移感知 (对照组, 预期失败)

    决策门: 仅当 Plan B 累计奖励 > Plan A × 1.10 时通过.

    Usage::

        sandbox = BanditMCSandbox(n_simulations=500, n_periods=2520, random_state=42)
        results = sandbox.run_comparison(n_bandit_arms=3, drift_magnitude=0.5)
        gate = sandbox.evaluate_decision_gate(results)
        if gate['passed']:
            # 规划 E6b 集成
            ...
        else:
            # 维持方案 A
            ...
    """

    # 体制转换矩阵 persistence (p_stay = 0.95)
    _P_STAY: float = 0.95
    # CUSUM 参数 (h = 5.5)
    _CUSUM_K: float = 0.5
    _CUSUM_H: float = 5.5
    # LinUCB 参数 (Li et al. 2010)
    _LAMBDA_REG: float = 1.0   # 正则化参数 λ
    _ALPHA_UCB: float = 1.0    # 探索系数 α
    # 上下文维度: [f_ar1, f_snr, f_gpd_shape, regime_dummy]
    _CONTEXT_DIM: int = 4
    # 数据生成噪声标准差
    _OBS_SIGMA: float = 0.1
    # 上下文滚动窗口大小
    _CONTEXT_WINDOW: int = 20

    def __init__(
        self,
        n_simulations: int = 500,
        n_periods: int = 2520,
        n_regimes: int = 2,
        random_state: Optional[int] = None,
    ):
        """初始化 Monte Carlo 验证沙箱

        Args:
            n_simulations: Monte Carlo 模拟次数
            n_periods: 每次模拟的时间步数 (2520 ≈ 10 年日频)
            n_regimes: 体制数 (默认 2: bull/bear)
            random_state: 随机种子 (None = 不固定)
        """
        self.n_simulations = int(n_simulations)
        self.n_periods = int(n_periods)
        self.n_regimes = int(n_regimes)
        self.rng = np.random.default_rng(random_state)
        self._last_results: Optional[Dict[str, Any]] = None

    # ==========================================================
    # 数据生成: Markov 体制转换
    # ==========================================================

    def _simulate_regime_switching_data(
        self,
        n_periods: int,
        n_regimes: int,
        drift_magnitude: float = 0.5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """生成体制转换数据 (Markov switching)

        生成 bull/bear 两体制, 各体制下各臂真实奖励不同:
        - Regime 0 (bull): arm 0 最优, 奖励 [0.5, 0.3, 0.4]
        - Regime 1 (bear): arm 1 最优, 奖励 [0.2, 0.6, 0.5] + drift

        Returns:
            rewards: (n_periods, 3) 各臂的真实奖励 (含噪声)
            regimes: (n_periods,) 真实体制标签 (0=bull, 1=bear)
        """
        K = 3  # 固定 3 臂 (static/dynamic/mixed 管道)
        # 体制转换矩阵 (persistence = 0.95)
        p_stay = self._P_STAY
        if n_regimes == 2:
            trans_mat = np.array([
                [p_stay, 1.0 - p_stay],
                [1.0 - p_stay, p_stay],
            ])
        else:
            trans_mat = np.eye(n_regimes)

        # 各体制下各臂的真实奖励均值
        regime_rewards = np.zeros((n_regimes, K))
        regime_rewards[0] = [0.5, 0.3, 0.4]  # bull: static 最优
        if n_regimes >= 2:
            regime_rewards[1] = [0.2, 0.6, 0.5]  # bear: dynamic 最优
            # 加入漂移
            regime_rewards[1] += drift_magnitude * np.array([-0.1, 0.2, 0.1])

        # 生成序列
        regimes = np.zeros(n_periods, dtype=int)
        rewards = np.zeros((n_periods, K))
        s = 0  # 起始于 bull
        for t in range(n_periods):
            regimes[t] = s
            rewards[t] = regime_rewards[s] + self.rng.standard_normal(K) * self._OBS_SIGMA
            s = int(self.rng.choice(n_regimes, p=trans_mat[s]))

        return rewards, regimes

    # ==========================================================
    # 上下文向量计算
    # ==========================================================

    def _compute_context(
        self,
        rewards: np.ndarray,
        t: int,
        window: Optional[int] = None,
    ) -> np.ndarray:
        """计算上下文向量 x_t = [f_ar1, f_snr, f_gpd_shape, regime_dummy]

        从历史奖励统计中提取体制条件上下文特征.
        使用滚动窗口 (lagged), 模拟真实场景中特征计算的延迟.

        Args:
            rewards: (T, K) 奖励序列
            t: 当前时间步
            window: 滚动窗口大小 (None = 使用默认值)

        Returns:
            x: (4,) 上下文向量 [f_ar1, f_snr, f_gpd_shape, regime_dummy]
        """
        d = self._CONTEXT_DIM
        if window is None:
            window = self._CONTEXT_WINDOW

        if t == 0:
            return np.zeros(d)

        start = max(0, t - window)
        recent = rewards[start:t]  # (window, K) 过去 window 步的奖励
        arm_means = recent.mean(axis=0)  # 各臂近期平均

        # f_ar1: 近期总均值 (AR1 信号 proxy)
        f_ar1 = float(recent.mean())
        # f_snr: 信噪比 (均值 / 标准差)
        recent_std = float(recent.std())
        f_snr = f_ar1 / (recent_std + 1e-6)
        # f_gpd_shape: GPD 形状参数 (placeholder, 模拟中不可直接计算)
        f_gpd_shape = 0.0
        # regime_dummy: 若 arm 1 (dynamic) 表现优于 arm 0 (static) → bear regime
        regime_dummy = 1.0 if arm_means[1] > arm_means[0] else 0.0

        return np.array([f_ar1, f_snr, f_gpd_shape, regime_dummy])

    # ==========================================================
    # CUSUM 监测器构建
    # ==========================================================

    def _build_cusum(self, rewards: np.ndarray) -> CUSUMDriftMonitor:
        """从 warmup 窗口估计基线, 构建 CUSUM 监测器

        使用短 warmup (5-10 步), 确保基线来自单一体制 (模拟起始于 bull).
        baseline_std 取各步均值序列的 std (与 CUSUM 监测信号 r.mean() 一致),
        而非所有臂所有步的 pooled std (后者包含跨臂方差, 会膨胀 baseline_std).

        Args:
            rewards: (T, K) 奖励序列

        Returns:
            CUSUMDriftMonitor 实例 (k=0.5, h=5.5)
        """
        T = rewards.shape[0]
        # 短 warmup: 确保基线来自单一体制 (起始 bull, p_stay=0.95 → 5 步内 77% 不切换)
        warmup = min(10, max(5, T // 20))
        # CUSUM 监测信号为 r.mean() (各臂均值), baseline_std 须与之一致
        step_means = rewards[:warmup].mean(axis=1)  # (warmup,) 各步均值
        mu0 = float(step_means.mean())
        sigma0 = float(step_means.std())
        # 兜底: 确保 baseline_std > 0 且不过小 (避免 CUSUM 过度敏感)
        if sigma0 < 0.03:
            sigma0 = 0.03
        return CUSUMDriftMonitor(
            baseline_mean=mu0, baseline_std=sigma0,
            k=self._CUSUM_K, h=self._CUSUM_H,
        )

    # ==========================================================
    # Plan A: 静态规则 (固定均匀权重 + CUSUM 触发指纹缓存重置)
    # ==========================================================

    def _plan_a_static_rules(
        self,
        data: np.ndarray,
        cusum_monitor: CUSUMDriftMonitor,
    ) -> float:
        """Plan A: 静态规则 — 固定均匀权重, CUSUM 触发指纹缓存重置

        使用固定均匀权重计算累计奖励, CUSUM 监测漂移并触发指纹缓存重置
        (静态方案中重置不影响权重, 仅记录漂移事件).

        Args:
            data: (T, K) 奖励序列
            cusum_monitor: CUSUM 漂移监测器

        Returns:
            cumulative_reward: 累计奖励 (float)
        """
        T, K = data.shape
        # 固定权重: 均匀分配
        weights = np.ones(K) / K
        cumulative_reward = 0.0
        # 重置 CUSUM (确保每次调用从干净状态开始)
        cusum_monitor.reset()

        for t in range(T):
            r = data[t]
            cumulative_reward += float(np.dot(weights, r))
            # CUSUM 监测漂移 (用各臂奖励均值) — 触发指纹缓存重置
            cusum_monitor.update(float(r.mean()))

        return cumulative_reward

    # ==========================================================
    # Plan B: Drift-Aware LinUCB (CUSUM 触发先验重置)
    # ==========================================================

    def _plan_b_drift_aware_bandit(
        self,
        data: np.ndarray,
        cusum_monitor: CUSUMDriftMonitor,
    ) -> float:
        """Plan B: Drift-Aware LinUCB — CUSUM 触发时重置历史 (先验重置)

        LinUCB (Li et al. 2010):
            θ̂_a = (X_a^T X_a + λI)^{-1} X_a^T r_a
            UCB_a(x) = θ̂_a^T x + α * sqrt(x^T (X_a^T X_a + λI)^{-1} x)

        当 CUSUM 检测到漂移时, 重置 A_a 和 b_a (遗忘历史), 使 bandit 快速适应新体制.
        同时重新估计 CUSUM 基线, 避免在新体制中持续误报.

        Args:
            data: (T, K) 奖励序列
            cusum_monitor: CUSUM 漂移监测器

        Returns:
            cumulative_reward: 累计奖励 (float)
        """
        T, K = data.shape
        d = self._CONTEXT_DIM
        lambda_reg = self._LAMBDA_REG
        alpha_ucb = self._ALPHA_UCB

        # 重置 CUSUM (确保每次调用从干净状态开始)
        cusum_monitor.reset()

        # 各臂的 LinUCB 状态:
        # A_a = X_a^T X_a + λI  (d×d 正则化 Gram 矩阵)
        # b_a = X_a^T r_a        (d 维奖励向量)
        A = [lambda_reg * np.eye(d) for _ in range(K)]
        b = [np.zeros(d) for _ in range(K)]

        cumulative_reward = 0.0
        for t in range(T):
            r = data[t]
            # 上下文向量 x_t = [f_ar1, f_snr, f_gpd_shape, regime_dummy]
            x = self._compute_context(data, t)

            # LinUCB 选择: 计算各臂 UCB 分数, 选最高
            ucb_scores = []
            for a in range(K):
                # θ̂_a = A_a^{-1} b_a
                theta = np.linalg.solve(A[a], b[a])
                # UCB = θ̂_a^T x + α * sqrt(x^T A_a^{-1} x)
                A_inv_x = np.linalg.solve(A[a], x)
                exploit = float(theta @ x)
                explore = alpha_ucb * np.sqrt(max(0.0, float(x @ A_inv_x)))
                ucb_scores.append(exploit + explore)
            chosen = int(np.argmax(ucb_scores))

            # 累计奖励 (仅观测选中臂的奖励)
            cumulative_reward += float(r[chosen])

            # 更新 LinUCB: A_a += x x^T, b_a += r_a * x
            A[chosen] += np.outer(x, x)
            b[chosen] += r[chosen] * x

            # CUSUM 漂移检测 → 重置 LinUCB 先验 (遗忘历史)
            drift_result = cusum_monitor.update(float(r.mean()))
            if drift_result['detected']:
                # 重置 LinUCB 状态 (先验重置)
                A = [lambda_reg * np.eye(d) for _ in range(K)]
                b = [np.zeros(d) for _ in range(K)]
                # 重新估计 CUSUM 基线 (适应新体制, 避免在新体制中持续误报)
                lookback = min(5, t + 1)
                recent = data[t + 1 - lookback: t + 1]
                new_mu0 = float(recent.mean())
                new_sigma0 = float(recent.std())
                cusum_monitor.baseline_mean = new_mu0
                cusum_monitor.baseline_std = new_sigma0 if new_sigma0 > 0 else 0.1
                # S_pos/S_neg 已由 CUSUMDriftMonitor.update() 自动重置

        return cumulative_reward

    # ==========================================================
    # Plan C: 朴素 LinUCB (无漂移感知, 对照组)
    # ==========================================================

    def _plan_c_naive_bandit(self, data: np.ndarray) -> float:
        """Plan C: 朴素 LinUCB — 无漂移感知 (对照组, 预期失败)

        标准 LinUCB (Li et al. 2010), 不使用 CUSUM, 不重置历史.
        跨体制累积数据导致模型污染, 在体制切换后适应缓慢.

        Args:
            data: (T, K) 奖励序列

        Returns:
            cumulative_reward: 累计奖励 (float)
        """
        T, K = data.shape
        d = self._CONTEXT_DIM
        lambda_reg = self._LAMBDA_REG
        alpha_ucb = self._ALPHA_UCB

        A = [lambda_reg * np.eye(d) for _ in range(K)]
        b = [np.zeros(d) for _ in range(K)]

        cumulative_reward = 0.0
        for t in range(T):
            r = data[t]
            x = self._compute_context(data, t)

            ucb_scores = []
            for a in range(K):
                theta = np.linalg.solve(A[a], b[a])
                A_inv_x = np.linalg.solve(A[a], x)
                exploit = float(theta @ x)
                explore = alpha_ucb * np.sqrt(max(0.0, float(x @ A_inv_x)))
                ucb_scores.append(exploit + explore)
            chosen = int(np.argmax(ucb_scores))

            cumulative_reward += float(r[chosen])
            A[chosen] += np.outer(x, x)
            b[chosen] += r[chosen] * x

        return cumulative_reward

    # ==========================================================
    # 三方案对比 + 决策门
    # ==========================================================

    def run_comparison(
        self,
        n_bandit_arms: int = 3,
        drift_magnitude: float = 0.5,
    ) -> Dict[str, Any]:
        """运行三方案 Monte Carlo 对比 + 决策门评估

        每次模拟生成相同数据, 三方案分别运行, 汇总 mean_reward / std_reward.

        Args:
            n_bandit_arms: bandit 臂数 (默认 3: static/dynamic/mixed 管道)
            drift_magnitude: 漂移幅度 (影响 regime 1 的奖励偏移)

        Returns:
            {
                'plan_a_static': {'mean_reward': float, 'std_reward': float},
                'plan_b_drift_aware': {'mean_reward': float, 'std_reward': float},
                'plan_c_naive': {'mean_reward': float, 'std_reward': float},
                'decision_gate': {
                    'passed': bool,
                    'improvement_vs_a': float,
                    'threshold': 0.10,
                    'interpretation': str,
                },
            }
        """
        rewards_a, rewards_b, rewards_c = [], [], []
        for _ in range(self.n_simulations):
            data, _ = self._simulate_regime_switching_data(
                self.n_periods, self.n_regimes, drift_magnitude
            )
            # 每个方案使用独立的 CUSUM 监测器 (避免状态污染)
            cusum_a = self._build_cusum(data)
            cusum_b = self._build_cusum(data)
            rewards_a.append(self._plan_a_static_rules(data, cusum_a))
            rewards_b.append(self._plan_b_drift_aware_bandit(data, cusum_b))
            rewards_c.append(self._plan_c_naive_bandit(data))

        results: Dict[str, Any] = {
            'plan_a_static': {
                'mean_reward': float(np.mean(rewards_a)),
                'std_reward': float(np.std(rewards_a)),
            },
            'plan_b_drift_aware': {
                'mean_reward': float(np.mean(rewards_b)),
                'std_reward': float(np.std(rewards_b)),
            },
            'plan_c_naive': {
                'mean_reward': float(np.mean(rewards_c)),
                'std_reward': float(np.std(rewards_c)),
            },
        }

        # 决策门: Plan B 相对 Plan A 提升须 ≥ 10%
        plan_a_mean = results['plan_a_static']['mean_reward']
        plan_b_mean = results['plan_b_drift_aware']['mean_reward']
        improvement = (plan_b_mean - plan_a_mean) / abs(plan_a_mean + 1e-10)
        threshold = 0.10
        passed = bool(improvement > threshold)
        results['decision_gate'] = {
            'passed': passed,
            'improvement_vs_a': float(improvement),
            'threshold': threshold,
            'interpretation': (
                f"Plan B 相对 Plan A 提升 {improvement:.2%}; "
                f"决策门阈值 10%; "
                f"{'通过 → 可规划 E6b 集成' if passed else '未通过 → 维持方案 A'}"
            ),
        }

        self._last_results = results
        return results

    # ==========================================================
    # 决策门评估
    # ==========================================================

    def evaluate_decision_gate(self, results: Optional[Dict] = None) -> Dict[str, Any]:
        """评估决策门

        Args:
            results: run_comparison 的返回值 (None = 使用上次结果)

        Returns:
            决策门评估字典, 含 passed / improvement_vs_a / threshold / interpretation.
            若无可用结果, 返回 {'evaluated': False}.
        """
        if results is None:
            results = self._last_results
        if results is None or 'decision_gate' not in results:
            return {'evaluated': False}
        return results['decision_gate']

    # ==========================================================
    # 诊断
    # ==========================================================

    def get_diagnostics(self) -> Dict[str, Any]:
        """获取沙箱诊断信息

        Returns:
            {'ran': False} 若未运行 run_comparison;
            否则返回 {'ran': True, 'n_simulations': int, 'n_periods': int, 'results': dict}
        """
        if self._last_results is None:
            return {'ran': False}
        return {
            'ran': True,
            'n_simulations': self.n_simulations,
            'n_periods': self.n_periods,
            'results': self._last_results,
        }
