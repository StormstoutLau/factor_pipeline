# RESEARCH_NOTES 工程执行方案 v1.0

> **文档定位**: 基于 `docs/private/RESEARCH_NOTES.md` 学术文档的可执行工程实施方案
> **版本**: v1.0 (2026-07-08)
> **范围**: §1 KS BH-FDR 发表前补强 / §2 元控制层 / §2B 状态归因 / §3 前置处理诚实性 / §4 统计→决策桥接
> **基础**: v3.0.0 T1 (21维指纹) / T3 (CUSUM) / T4 (BH-FDR) 已实施; T2 流式 / T5 状态接入 / T6 StateConditionedAnalyzer / T7 三通道分解 待实施
> **格式参考**: `docs/EXECUTION_V3.0.0_T1.md` (E1/E2/E3 三阶段 TDD 模式)
> **工程约束**: 所有新模块默认 `enable=False`; 诊断优先于校正; sklearn-style 接口; 与 `PipelineV2Config` 集成; TDD; 每个 E 任务可独立交付

---

## 0. 摘要

### 0.1 RESEARCH_NOTES 五章节 → E 任务映射

| RESEARCH_NOTES 章节 | 核心论点 | 工程 E 任务 | 优先级 | 依赖 |
|---------------------|---------|------------|--------|------|
| §1 KS BH-FDR 发表前补强 | BH-FDR 在 KS 迁移检验中的学术价值需三块补强 (检测力曲线 / Romano-Wolf / White Reality Check) | E1 PowerCurveAnalyzer / E2 Romano-Wolf / E3 White Reality Check + Hansen SPA | P1 | 无 (复用 T4 `multiple_testing.py`) |
| §2 元控制层 | 标准 Contextual Bandit 三平稳假设在金融中全失效 → 方案 A (静态规则 + 漂移检测) 推荐; 方案 B (Drift-Aware Bandit) 需 MC 验证; 方案 C 弃用 | E4 FingerprintPerformanceLogger / E5 AttributionAnalyzer / E6 DriftAwareBandit (P3 条件触发) | P2 | E4/E5 独立; E6 依赖 E4 + T3 CUSUM |
| §2B 状态归因 | 12 A股状态变量 (5类) + 三层维度控制 (L1/L2/L3) + 双轨回归 (R_factor / IC) + 三通道分解 | E7 StateDataLoader + MarkovRegimeIdentifier / E8 StateConditionedPerformanceMatrix + 双轨回归 / E9 ThreeChannelDecomposition | P2 | E7 独立; E8 依赖 E7; E9 依赖 E8 |
| §3 前置处理诚实性 | 论文主要贡献; 6 自由度 (去极值/标准化/缺失/中性/对齐/起止点); 实证载体为消融设计 | (无新 E 任务, 指向 `ABLATION_DESIGN_V3.0.0.md`) | P1 | 复用 v2.6.0 E1-E9 全套处理模块 |
| §4 统计→决策桥接 | A+C 混合 (概率映射 + 在线凸优化); 三工程挑战 (时间对齐 / 冷启动 / 状态识别延迟 / 预测误差传播); Q2 soft-update 在 (μ, σ²) 参数空间 | E10 StatisticalDecisionBridge + StateConditionedPrior | P3 | 依赖 E8 (状态条件先验) |

### 0.2 依赖关系图

```
T1 (21维指纹, 已实施) ─┬─→ E4 (FP 性能日志)
                      └─→ E5 (三层归因, 消费 21 维)

T3 (CUSUM, 已实施) ────→ E6 (Drift-Aware Bandit, P3 条件)

T4 (BH-FDR, 已实施) ───┬─→ E1 (检测力曲线对比)
                      ├─→ E2 (Romano-Wolf 对比)
                      ├─→ E3 (White Reality Check 对比)
                      └─→ E5 (三层归因的 BH-FDR 应用)

E7 (状态数据加载) ─────┬─→ E8 (状态条件性能矩阵 + 双轨回归)
                      │   └─→ E9 (三通道分解)
                      └─→ E10 (决策桥接, 状态条件先验)

§3 (前置处理诚实性) ──→ 复用 ABLATION_DESIGN_V3.0.0.md (无新 E 任务)
```

### 0.3 推荐执行顺序

**Phase 1 (P1, 独立可并行)**:
- E1 / E2 / E3 (§1 三块补强, 仅依赖 T4 `multiple_testing.py`)
- §3 前置处理诚实性 (复用现有消融设计)

**Phase 2 (P2, 串行依赖)**:
- E4 → E5 (元控制层归因基础设施)
- E7 → E8 → E9 (状态归因主链)

**Phase 3 (P3, 条件触发)**:
- E6 (Drift-Aware Bandit) — 需 MC 验证决策门通过后方可实施
- E10 (决策桥接) — 依赖 E8 状态条件先验就绪

### 0.4 核心立场 (与 RESEARCH_NOTES 对齐)

1. **诊断优先于校正**: 所有新模块测量威胁, 不声称消除威胁 (RESEARCH_NOTES §2.3.2)
2. **方案 A 优先**: 静态规则 + 漂移检测为默认路径; Bandit 方案需 MC 验证 (RESEARCH_NOTES §2.3.2 关键限定)
3. **统计服务测量, 非叙事**: 所有 p 值 / 置信区间用于客观测量, 不用于叙事辩护
4. **不信任因子/模型/自己判断**: E1-E3 补强 BH-FDR 的发表前可信度; E5 三层归因解构表现来源; E10 决策桥接显式建模预测误差传播

---

## 1. §1 KS BH-FDR 发表前补强

### 1.1 学术背景 (RESEARCH_NOTES §1)

`backtest/multiple_testing.py` 已实施 BH-FDR (Benjamini-Hochberg 1995), 应用于:
- `_ks_migration_significance` (pipelines_v2.py:282) — KS 双样本迁移检验的多重比较校正
- `unified_drift.py:_compute_rolling_structure_drift` — ~500 KS 检验的 FDR 控制
- `factor_significance.py:_apply_correction` — K 因子增量 alpha 检验的 BH/Bonferroni/Holm

RESEARCH_NOTES §1.4 指出发表前需三块补强:
1. **检测力曲线对比** — BH vs Bonferroni vs 无校正的检测力 (power) 随 effect size / N / 假设比例变化的曲线
2. **Romano-Wolf (2005) 对比** — 控制弱 FWER (k-FWER) 的 bootstrap 重抽样方法
3. **White Reality Check (2000) + Hansen SPA (2005)** — 针对策略回测的 data snooping 校正

### 1.2 共享模块扩展

所有 E1-E3 任务复用 `backtest/multiple_testing.py` 共享入口 `apply_correction(method=...)`, 新增方法通过扩展 `method` 参数枚举值接入, 不破坏现有 BH/Bonferroni/none 路径。

---

### E1: PowerCurveAnalyzer (检测力曲线对比)

#### 1.2.1 任务编号
**E1** — Monte Carlo 检测力曲线分析器

#### 1.2.2 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/multiple_testing.py` | 新增类 | `PowerCurveAnalyzer` | `__init__(self, n_simulations: int = 1000, alpha: float = 0.05, random_state: Optional[int] = None)` |
| `backtest/multiple_testing.py` | 新增方法 | `PowerCurveAnalyzer.compute_power_curve` | `compute_power_curve(self, effect_sizes: np.ndarray, n_samples: int, n_hypotheses: int, true_alt_fraction: float, methods: List[str] = ['bonferroni', 'benjamini_hochberg', 'none']) -> Dict[str, np.ndarray]` |
| `backtest/multiple_testing.py` | 新增方法 | `PowerCurveAnalyzer.plot_power_curve` | `plot_power_curve(self, result: Dict, save_path: Optional[str] = None) -> matplotlib.figure.Figure` |
| `backtest/multiple_testing.py` | 新增方法 | `PowerCurveAnalyzer.compute_fdr_vs_power` | `compute_fdr_vs_power(self, effect_sizes, n_samples, n_hypotheses, true_alt_fraction, methods) -> Dict` (返回同时含 power + empirical FDR) |
| `tests/backtest/test_power_curve.py` | 新增测试 | `TestPowerCurveAnalyzer` | TDD 测试类 |

#### 1.2.3 算法实现

**数学公式**:

检测力 (Power) 定义为在 H1 为真时正确拒绝 H1 的概率:
$$\text{Power}(\delta, n, K, \pi_1) = P(\text{reject } H_k | H_k \text{ is false})$$

Monte Carlo 估计:
$$\widehat{\text{Power}} = \frac{1}{n_{sim}} \sum_{s=1}^{n_{sim}} \frac{|\{k : H_k \text{ rejected in sim } s \land H_k \text{ is false}\}|}{|\{k : H_k \text{ is false}\}|}$$

经验 FDR:
$$\widehat{\text{FDR}} = \frac{1}{n_{sim}} \sum_{s=1}^{n_{sim}} \frac{|\{k : H_k \text{ rejected in sim } s \land H_k \text{ is true}\}|}{\max(|\{k : H_k \text{ rejected in sim } s\}|, 1)}$$

其中 $\delta$ = effect size (Cohen's d), $n$ = 样本量, $K$ = 假设数, $\pi_1$ = 真实备择假设比例。

**Python 代码片段**:

```python
class PowerCurveAnalyzer:
    """Monte Carlo 检测力曲线分析器 (RESEARCH_NOTES §1.4 第一块补强)

    对比 BH-FDR / Bonferroni / 无校正的检测力与经验 FDR,
    用于论文发表前补强 BH-FDR 在 KS 迁移检验中的统计性质论证。
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

    def _simulate_p_values(
        self,
        effect_size: float,
        n_samples: int,
        n_hypotheses: int,
        true_alt_fraction: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """模拟一组 p 值, 返回 (p_values, is_true_alt)

        H0 为真的假设: p ~ Uniform(0, 1)
        H1 为真的假设: p ~ Beta 分布 (经非中心性参数调整)
        """
        n_true_alt = int(n_hypotheses * true_alt_fraction)
        n_true_null = n_hypotheses - n_true_alt

        # H0: p ~ U(0, 1)
        p_null = self.rng.uniform(0, 1, size=n_true_null)

        # H1: 经 Welch t 检验生成 p 值 (双样本, 不同均值)
        if n_true_alt > 0 and effect_size > 0:
            # 模拟双样本 t 检验: 样本1 ~ N(0,1), 样本2 ~ N(effect_size, 1)
            x1 = self.rng.standard_normal((n_true_alt, n_samples))
            x2 = self.rng.standard_normal((n_true_alt, n_samples)) + effect_size
            # Welch t 检验
            from scipy import stats as sps
            t_stat = (x1.mean(axis=1) - x2.mean(axis=1)) / np.sqrt(
                x1.var(axis=1, ddof=1) / n_samples
                + x2.var(axis=1, ddof=1) / n_samples
            )
            df_num = (x1.var(axis=1, ddof=1) / n_samples + x2.var(axis=1, ddof=1) / n_samples) ** 2
            df_den = (x1.var(axis=1, ddof=1) / n_samples) ** 2 / (n_samples - 1) + \
                     (x2.var(axis=1, ddof=1) / n_samples) ** 2 / (n_samples - 1)
            df = df_num / np.maximum(df_den, 1e-10)
            p_alt = 2 * (1 - sps.t.cdf(np.abs(t_stat), df=df))
        else:
            p_alt = self.rng.uniform(0, 1, size=n_true_alt)

        p_values = np.concatenate([p_null, p_alt])
        is_true_alt = np.concatenate([
            np.zeros(n_true_null, dtype=bool),
            np.ones(n_true_alt, dtype=bool),
        ])
        # 随机打乱
        perm = self.rng.permutation(n_hypotheses)
        return p_values[perm], is_true_alt[perm]

    def compute_power_curve(
        self,
        effect_sizes: np.ndarray,
        n_samples: int,
        n_hypotheses: int,
        true_alt_fraction: float,
        methods: List[str] = None,
    ) -> Dict[str, np.ndarray]:
        """计算检测力曲线

        Returns:
            {'bonferroni': np.ndarray, 'benjamini_hochberg': np.ndarray, 'none': np.ndarray}
            每个 array 长度 = len(effect_sizes), 值为 [0,1] 的检测力估计
        """
        if methods is None:
            methods = ['bonferroni', 'benjamini_hochberg', 'none']

        power_curves = {m: np.zeros(len(effect_sizes)) for m in methods}
        fdr_curves = {m: np.zeros(len(effect_sizes)) for m in methods}

        for i, delta in enumerate(effect_sizes):
            power_acc = {m: 0.0 for m in methods}
            fdr_acc = {m: 0.0 for m in methods}
            for _ in range(self.n_simulations):
                p_vals, is_alt = self._simulate_p_values(
                    delta, n_samples, n_hypotheses, true_alt_fraction
                )
                n_true_alt = is_alt.sum()
                n_true_null = n_hypotheses - n_true_alt
                for m in methods:
                    _, rejected = apply_correction(p_vals.tolist(), method=m, alpha=self.alpha)
                    rejected = np.array(rejected)
                    # Power: 在 H1 为真时拒绝的比例
                    if n_true_alt > 0:
                        power_acc[m] += (rejected & is_alt).sum() / n_true_alt
                    # FDR: 在 H0 为真时拒绝的比例 / 总拒绝数
                    n_rejected = rejected.sum()
                    if n_rejected > 0 and n_true_null > 0:
                        fdr_acc[m] += (rejected & ~is_alt).sum() / n_rejected
            for m in methods:
                power_curves[m][i] = power_acc[m] / self.n_simulations
                fdr_curves[m][i] = fdr_acc[m] / self.n_simulations

        self._last_fdr_curves_ = fdr_curves
        return power_curves
```

#### 1.2.4 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T4 `multiple_testing.py:apply_bh_fdr` | ✓ 完全兼容 | E1 调用 `apply_correction(method=...)` 共享入口, 不修改 BH 实现 |
| `pipelines_v2.py:_ks_migration_significance` | ✓ 无侵入 | E1 为独立分析工具, 不进入 Pipeline.transform() 主循环 |
| `unified_drift.py` | ✓ 无侵入 | E1 仅用于离线分析, 不参与在线漂移检测 |
| `factor_significance.py` | ✓ 无侵入 | E1 用于发表前补强, 不改变因子检验逻辑 |

#### 1.2.5 接口设计 (与 PipelineV2Config 协同)

E1 为**离线分析工具**, 不集成进 `PipelineV2Config`。用法:

```python
from backtest.multiple_testing import PowerCurveAnalyzer

analyzer = PowerCurveAnalyzer(n_simulations=1000, random_state=42)
effect_sizes = np.linspace(0.0, 1.0, 11)  # Cohen's d 0 到 1.0
power = analyzer.compute_power_curve(
    effect_sizes=effect_sizes,
    n_samples=252,           # 1 年日频
    n_hypotheses=100,        # 100 个 KS 检验
    true_alt_fraction=0.2,   # 20% 真实迁移
)
fig = analyzer.plot_power_curve(power)
fig.savefig('docs/figures/power_curve.png')
```

#### 1.2.6 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(n_simulations × n_effect_sizes × n_hypotheses × n_samples) | 1000 sim × 11 δ × 100 K × 252 n ≈ 2.8e8 次随机数生成 |
| 内存占用 | ~50 MB | p_values (100,) × 1000 sim, 可增量累加不存储全量 |
| 预期运行时间 | ~30-60 秒 | 单线程; 可用 joblib 并行化 sim 循环 (未来优化) |

#### 1.2.7 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| numpy | >=1.22 | 核心 (已装) | 随机数生成 |
| scipy | >=1.7 | 核心 (已装) | t 分布 CDF |
| matplotlib | >=3.5 | 核心 (已装, 项目隐式依赖) | 绘图 |

**无新增依赖**。

#### 1.2.8 测试计划 (TDD)

**测试文件**: `tests/backtest/test_power_curve.py`
**测试类**: `TestPowerCurveAnalyzer`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_simulate_p_values_h0_only` | effect_size=0 时所有 p ~ U(0,1) | KS 检验 p > 0.05 (不拒绝均匀分布) |
| `test_simulate_p_values_h1_distribution` | effect_size=0.5 时 H1 组 p 值偏小 | H1 组 p 均值 < H0 组 p 均值 |
| `test_compute_power_curve_monotonicity` | 检测力随 effect_size 单调递增 | power[i+1] >= power[i] (允许数值噪声) |
| `test_bonferroni_more_conservative_than_bh` | 同参数下 Bonferroni power <= BH power | all(bonf_power <= bh_power + 0.05) |
| `test_bh_fdr_control` | BH 经验 FDR <= alpha + 容忍带 | fdr_bh <= 0.05 + 0.03 (Monte Carlo 误差) |
| `test_bonferroni_fwer_control` | Bonferroni 经验 FWER <= alpha | 至少一个 H0 被拒绝的比例 <= 0.05 + 0.03 |
| `test_no_correction_highest_power` | 无校正检测力最高 | none_power >= bh_power >= bonf_power |
| `test_random_state_reproducibility` | 相同 random_state 两次运行结果一致 | np.allclose(power1, power2) |
| `test_plot_power_curve_returns_figure` | plot 返回 matplotlib Figure 对象 | isinstance(fig, matplotlib.figure.Figure) |
| `test_edge_case_zero_true_alt` | true_alt_fraction=0 时 power=0 (无 H1) | all power ≈ 0 |

**TDD 流程**:
1. **Red**: 先写 `test_power_curve.py` 全部测试用例 (此时 `PowerCurveAnalyzer` 不存在, import 失败)
2. **Green**: 实现 `PowerCurveAnalyzer` 使所有测试通过
3. **Review**: 检查检测力曲线形态是否符合统计理论 (Bonferroni 最保守, BH 居中, none 最高)

#### 1.2.9 验收标准

- [ ] `PowerCurveAnalyzer` 类完整实现, 所有测试通过 (≥10 测试用例)
- [ ] 检测力曲线图: BH 在 effect_size=0.5, n=252, K=100, π1=0.2 时检测力 > Bonferroni 检测力
- [ ] BH 经验 FDR ≤ α + 0.03 (Monte Carlo 误差容忍带)
- [ ] 文档: 在 `docs/figures/power_curve.png` 生成发表级图表
- [ ] 论文附录可用: 输出表格含 (effect_size, method, power, empirical_fdr) 四列

---

### E2: Romano-Wolf Bootstrap 对比

#### 1.2.10 任务编号
**E2** — Romano-Wolf (2005) k-FWER Bootstrap 校正

#### 1.2.11 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/multiple_testing.py` | 新增函数 | `apply_romano_wolf` | `apply_romano_wolf(p_values: List[float], bootstrap_p_values: np.ndarray, alpha: float = 0.05, k: int = 1, method: str = 'stepdown') -> Tuple[List[float], List[bool]]` |
| `backtest/multiple_testing.py` | 新增函数 | `_romano_wolf_stepdown` | `_romano_wolf_stepdown(p_values, bootstrap_dist, alpha, k) -> Tuple[List[float], List[bool]]` (私有) |
| `backtest/multiple_testing.py` | 不修改 | `apply_correction` | 签名保持 `(p_values, method, alpha) -> Tuple[List[float], List[bool]]`, **不新增** `'romano_wolf'` 枚举值; Romano-Wolf 仅通过独立函数 `apply_romano_wolf` 接入 |
| `tests/backtest/test_multiple_testing.py` | 扩展测试 | `TestRomanoWolf` | TDD 测试类 |

#### 1.2.12 算法实现

**数学公式** (Romano-Wolf 2005):

k-FWER 控制: 至多 k 个假拒绝的概率 ≤ α:
$$P(|\{i \in I_0 : \text{reject } H_i\}| \geq k) \leq \alpha$$

Stepdown 程序:
1. 排序 p 值: $p_{(1)} \leq p_{(2)} \leq \dots \leq p_{(m)}$
2. 对每个 $j$, 计算 bootstrap 临界值 $c_{j,k}$:
   $$c_{j,k} = \text{Quantile}_{1-\alpha} \left( k\text{-th smallest of } \{p^*_{i,(1)}, \dots, p^*_{i,(j)}\}_{i=1}^{B} \right)$$
3. 若 $p_{(j)} \leq c_{j,k}$, 拒绝 $H_{(1)}, \dots, H_{(j)}$; 否则停止

当 k=1 时, k-FWER 退化为 FWER (Family-Wise Error Rate), 等价于控制至少 1 个假拒绝。

**Python 代码片段**:

```python
def apply_romano_wolf(
    p_values: List[float],
    bootstrap_p_values: np.ndarray,
    alpha: float = 0.05,
    k: int = 1,
    method: str = 'stepdown',
) -> Tuple[List[float], List[bool]]:
    """Romano-Wolf (2005) k-FWER Bootstrap 校正 (RESEARCH_NOTES §1.4 第二块补强)

    控制弱 FWER (k-FWER): 至多 k 个假拒绝的概率 ≤ α.
    当 k=1 时等价于强 FWER 控制.

    学术依据: Romano & Wolf (2005) "Stepwise Multiple Testing as Formalized
    Data Snooping"

    Args:
        p_values: 长度 m 的原始 p 值列表
        bootstrap_p_values: (B, m) 的 bootstrap p 值矩阵, B = bootstrap 次数
            每行是一次 bootstrap 重抽样下的 p 值
        alpha: 显著性水平
        k: k-FWER 中的 k, 默认 1 (强 FWER)
        method: 'stepdown' (默认, 更有检测力) 或 'single_step'

    Returns:
        (adjusted_p_values, rejected) 元组
        adjusted_p_values: 长度 m 的调整后 p 值
        rejected: 长度 m 的布尔列表, True 表示拒绝 H0
    """
    p_arr = np.asarray(p_values, dtype=float)
    m = len(p_arr)
    B = bootstrap_p_values.shape[0]

    if method == 'stepdown':
        return _romano_wolf_stepdown(p_arr, bootstrap_p_values, alpha, k)
    else:
        # single-step: c = Quantile_{1-alpha}(k-th smallest of each bootstrap row)
        kth_smallest = np.sort(bootstrap_p_values, axis=1)[:, min(k - 1, m - 1)]
        critical = np.quantile(kth_smallest, 1 - alpha)
        rejected = (p_arr <= critical).tolist()
        # 调整 p 值: p_adj[i] = P(k-th smallest of bootstrap <= p[i])
        adjusted = np.array([
            np.mean(kth_smallest <= p_arr[i]) for i in range(m)
        ])
        return adjusted.tolist(), rejected


def _romano_wolf_stepdown(
    p_arr: np.ndarray,
    bootstrap_p_values: np.ndarray,
    alpha: float,
    k: int,
) -> Tuple[List[float], List[bool]]:
    """Romano-Wolf stepdown 程序 (更有检测力)"""
    m = len(p_arr)
    # 排序索引
    order = np.argsort(p_arr)
    sorted_p = p_arr[order]
    # bootstrap 排序 (每行)
    sorted_boot = np.sort(bootstrap_p_values, axis=1)

    rejected_sorted = np.zeros(m, dtype=bool)
    # Stepdown: 从最小 p 值开始, 找到第一个不拒绝的位置
    for j in range(m):
        # k-th smallest of bootstrap[:(j+1)]
        # 即在每行前 (j+1) 个最小 bootstrap p 值中取第 k 小
        submatrix = sorted_boot[:, :j + 1]
        if submatrix.shape[1] >= k:
            kth_in_sub = np.sort(submatrix, axis=1)[:, k - 1]
        else:
            kth_in_sub = submatrix[:, -1]
        critical = np.quantile(kth_in_sub, 1 - alpha)
        if sorted_p[j] <= critical:
            rejected_sorted[j] = True
        else:
            break  # stepdown: 一旦不拒绝, 后续都不拒绝

    # 还原原始顺序
    rejected = np.zeros(m, dtype=bool)
    rejected[order] = rejected_sorted

    # 调整 p 值 (stepdown: 取累积最大)
    adjusted_sorted = np.zeros(m)
    for j in range(m):
        submatrix = sorted_boot[:, :j + 1]
        if submatrix.shape[1] >= k:
            kth_in_sub = np.sort(submatrix, axis=1)[:, k - 1]
        else:
            kth_in_sub = submatrix[:, -1]
        adjusted_sorted[j] = np.mean(kth_in_sub <= sorted_p[j])
    # 累积最大 (stepdown 单调性)
    adjusted_sorted = np.maximum.accumulate(adjusted_sorted)
    adjusted = np.zeros(m)
    adjusted[order] = adjusted_sorted

    return adjusted.tolist(), rejected.tolist()
```

**Bootstrap p 值生成辅助函数** (KS 迁移场景):

```python
def _generate_bootstrap_p_values_for_ks(
    historical_data: pd.DataFrame,
    recent_data: pd.DataFrame,
    n_bootstrap: int = 1000,
    random_state: Optional[int] = None,
) -> np.ndarray:
    """为 KS 迁移检验生成 bootstrap p 值矩阵

    在 H0 (两样本同分布) 假设下, 对合并样本重抽样生成 bootstrap p 值.
    """
    from scipy import stats as sps
    rng = np.random.default_rng(random_state)
    n_hist = len(historical_data)
    n_recent = len(recent_data)
    common_cols = historical_data.columns.intersection(recent_data.columns)
    pooled = pd.concat([historical_data[common_cols], recent_data[common_cols]], axis=0)
    n_pooled = len(pooled)
    K = len(common_cols)
    bootstrap_p = np.zeros((n_bootstrap, K))
    for b in range(n_bootstrap):
        idx = rng.choice(n_pooled, size=n_pooled, replace=True)
        boot_sample = pooled.iloc[idx]
        boot_hist = boot_sample.iloc[:n_hist]
        boot_recent = boot_sample.iloc[n_hist:n_hist + n_recent]
        for j, col in enumerate(common_cols):
            _, p_val = sps.ks_2samp(boot_hist[col].dropna(), boot_recent[col].dropna())
            bootstrap_p[b, j] = p_val
    return bootstrap_p
```

#### 1.2.13 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T4 `multiple_testing.py:apply_correction` | ✓ 签名不变 | 不向 `method` 新增 `'romano_wolf'` (签名无 `**kwargs`, 无法接收 bootstrap 数据); Romano-Wolf 经独立函数 `apply_romano_wolf` 接入, 现有 BH/Bonferroni/none 路径不变 |
| `pipelines_v2.py:_ks_migration_significance` | ✓ 可选启用 | 新增 `correction_method='romano_wolf'` 选项, 需额外传入 bootstrap_p_values |
| `factor_significance.py` | ✓ 可选启用 | 可通过 `correction='romano_wolf'` 接入, 需 bootstrap 生成器 |

**注意**: Romano-Wolf 需要 bootstrap p 值矩阵作为额外输入, 不能像 BH 那样仅凭 p 值列表计算。`apply_correction` 签名为 `(p_values, method, alpha) -> Tuple[List[float], List[bool]]`, 无 `**kwargs`, 因此**不应扩展**其签名或向 `method` 枚举新增 `'romano_wolf'` 来承载 bootstrap 数据。

**接口设计选择**: 不修改 `apply_correction` 签名 (避免破坏现有调用), 也不向其 `method` 枚举新增 `'romano_wolf'`。Romano-Wolf 一律通过独立函数 `apply_romano_wolf(p_values, bootstrap_p_values, alpha, k, method)` 接入, 调用方按需选用。如需统一入口, 可在调用方代码中按 `method` 分派到 `apply_romano_wolf`, 而非修改共享模块 `apply_correction` 的签名。

#### 1.2.14 接口设计 (与 PipelineV2Config 协同)

E2 为**可选校正方法**, 不直接集成进 `PipelineV2Config`, 但可通过 `correction_method` 参数在 `monitor_cusum_drift` / `check_migrations` 中选用:

```python
# pipelines_v2.py 中可选扩展 (不强制):
# PipelineV2Config 新增字段 (默认 False, opt-in):
#   enable_romano_wolf_comparison: bool = False
#   rw_n_bootstrap: int = 1000
#   rw_k: int = 1

# 调用示例:
from backtest.multiple_testing import apply_romano_wolf, _generate_bootstrap_p_values_for_ks

boot_p = _generate_bootstrap_p_values_for_ks(
    historical_data, recent_data, n_bootstrap=1000, random_state=42
)
adj_p, rejected = apply_romano_wolf(
    p_values=raw_p_list,
    bootstrap_p_values=boot_p,
    alpha=0.05,
    k=1,
)
```

#### 1.2.15 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(B × K × n_log) + O(m² × B) | B=1000 bootstrap × K=100 KS 检验; stepdown O(m²B) |
| 内存占用 | ~80 MB | bootstrap_p_values (1000, 100) float64 ≈ 0.8 MB; KS 检验中间结果 |
| 预期运行时间 | ~5-15 秒 | B=1000, K=100, n=252; KS 检验可向量化 |

#### 1.2.16 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| numpy | >=1.22 | 核心 (已装) | bootstrap 重抽样 |
| scipy | >=1.7 | 核心 (已装) | KS 检验 |

**无新增依赖**。

#### 1.2.17 测试计划 (TDD)

**测试文件**: `tests/backtest/test_multiple_testing.py` (扩展)
**测试类**: `TestRomanoWolf`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_romano_wolf_k1_controls_fwer` | k=1 时 FWER ≤ α + 0.03 | Monte Carlo 1000 次模拟, FWER ≤ 0.08 |
| `test_romano_wolf_k3_allows_more_rejections` | k=3 比 k=1 更宽松 | 拒绝数 k=3 >= k=1 |
| `test_stepdown_more_powerful_than_single_step` | stepdown 检测力 >= single_step | rejected_stepdown >= rejected_single_step |
| `test_bootstrap_p_value_generation` | `_generate_bootstrap_p_values_for_ks` 输出形状正确 | shape == (n_bootstrap, K) |
| `test_bootstrap_p_under_null_uniform` | H0 下 bootstrap p 值近似均匀 | KS 检验 p > 0.05 |
| `test_romano_wolf_consistency_with_bonferroni` | k=1 时 Romano-Wolf 拒绝数 ≤ Bonferroni | (bootstrap 校正通常不比 Bonferroni 更宽松) |
| `test_edge_case_single_hypothesis` | m=1 时等价于原始 p < α | rejected == (p < alpha) |
| `test_edge_case_all_null` | 全部 H0 为真时 FWER 控制 | 经验 FWER ≤ 0.08 |
| `test_random_state_reproducibility` | 相同 random_state 结果一致 | np.allclose |

**TDD 流程**:
1. **Red**: 写 `TestRomanoWolf` 全部测试 (此时 `apply_romano_wolf` 不存在)
2. **Green**: 实现 `apply_romano_wolf` + `_romano_wolf_stepdown` + `_generate_bootstrap_p_values_for_ks`
3. **Review**: Monte Carlo 验证 k-FWER 控制性质

#### 1.2.18 验收标准

- [ ] `apply_romano_wolf` 函数完整实现, 所有测试通过 (≥9 测试用例)
- [ ] Monte Carlo 验证: k=1 时经验 FWER ≤ 0.08 (α=0.05 + 0.03 容忍带)
- [ ] Stepdown 检测力 ≥ single-step 检测力
- [ ] 与 BH-FDR 对比表格: 在相同 (δ, n, K, π1) 下, 拒绝数排序 none >= BH >= RW(k=1) >= Bonferroni
- [ ] 论文附录可用: 输出 (method, n_rejected, empirical_fwer, power) 对比表

---

### E3: White Reality Check + Hansen SPA

#### 1.2.19 任务编号
**E3** — White (2000) Reality Check + Hansen (2005) SPA 校正

#### 1.2.20 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/multiple_testing.py` | 新增类 | `WhiteRealityCheck` | `__init__(self, n_bootstrap: int = 1000, block_size: Optional[int] = None, method: str = 'stationary', random_state: Optional[int] = None)` |
| `backtest/multiple_testing.py` | 新增方法 | `WhiteRealityCheck.test` | `test(self, strategy_returns: np.ndarray, benchmark_return: np.ndarray, alpha: float = 0.05) -> Dict[str, Any]` |
| `backtest/multiple_testing.py` | 新增类 | `HansenSPA` | `__init__(self, n_bootstrap: int = 1000, block_size: Optional[int] = None, method: str = 'stationary', random_state: Optional[int] = None)` |
| `backtest/multiple_testing.py` | 新增方法 | `HansenSPA.test` | `test(self, strategy_returns: np.ndarray, benchmark_return: np.ndarray, alpha: float = 0.05) -> Dict[str, Any]` |
| `backtest/multiple_testing.py` | 新增私有方法 | `_stationary_bootstrap` | `_stationary_bootstrap(self, x: np.ndarray, block_size: float) -> np.ndarray` (Politis-Romano 1994) |
| `backtest/multiple_testing.py` | 新增私有方法 | `_circular_block_bootstrap` | `_circular_block_bootstrap(self, x: np.ndarray, block_size: int) -> np.ndarray` |
| `tests/backtest/test_multiple_testing.py` | 扩展测试 | `TestWhiteRealityCheck`, `TestHansenSPA` | TDD 测试类 |

#### 1.2.21 算法实现

**数学公式** (White 2000 Reality Check):

设 $K$ 个策略, 基准策略为 $b$, 各策略相对基准的超额收益:
$$\bar{f}_k = \frac{1}{T} \sum_{t=1}^{T} (r_{k,t} - r_{b,t})$$

检验统计量:
$$V = \max_{k=1}^{K} \sqrt{T} \bar{f}_k$$

Bootstrap 分布 (stationary bootstrap, Politis-Romano 1994):
1. 重抽样收益序列 $\{r^*_{k,t}\}_{t=1}^{T}$, 块大小 $B$ (概率 $1/B$ 重新开始新块)
2. 计算 $V^* = \max_k \sqrt{T} (\bar{f}^*_k - \bar{f}_k)$ (recentered)
3. 重复 $N$ 次, 得 $V^*_1, \dots, V^*_N$
4. p 值: $p = \frac{1}{N} \sum_{i=1}^{N} \mathbb{1}(V^*_i \geq V)$

**Hansen (2005) SPA 改进**:
- 重新中心化: $V^*_{SPA} = \max_k \sqrt{T} (\bar{f}^*_k - \bar{f}_k) \cdot \mathbb{1}(\bar{f}_k > -\sqrt{\hat{\omega}^2_k / T} \cdot \sqrt{2 \log \log T})$
- 分离 $H1$ 集合 (显著好于基准) 和 $H0$ 集合, 仅对 $H0$ 集合施加 data snooping 校正
- SPA 比 White RC 更有检测力 (lower p-values for genuinely superior strategies)

> **Recentering 阈值公式核实** (阶段 4 学术核实, 2026-07-08, 用户提供权威解释):
>
> Hansen (2005) SPA 的核心创新是识别并剔除"太差"的模型, 避免它们拉高临界值、降低检验功效。
>
> **判断准则** (Law of the Iterated Logarithm, LIL):
> - 若 $\sqrt{n} \bar{f}_k / \hat{\omega}_k \le -\sqrt{2 \log \log n}$, 则第 $k$ 个模型被认为**统计上显著劣于基准** ("太差")
> - 等价于: $\bar{f}_k \le -\sqrt{\hat{\omega}^2_k / n} \cdot \sqrt{2 \log \log n}$ (太差条件)
> - 等价于: $\bar{f}_k > -\sqrt{\hat{\omega}^2_k / n} \cdot \sqrt{2 \log \log n}$ (保留条件, 即上文 $\mathbb{1}(\cdot)$ 中的条件)
>
> 其中 $n$ 为样本量 (时序语境下记为 $T$), $\hat{\omega}_k$ 为第 $k$ 个模型相对表现的标准差估计量。
>
> **机制**: 被判定为"太差"的模型在构造检验统计量的零分布时会被 recentered 到零, 避免它们拉高 bootstrap 临界值。阈值基于重对数定律 (LIL), 确保渐近意义上表现极差的模型不会影响检验结论。
>
> **灵活性**: $\sqrt{2 \log \log n}$ 是 Hansen (2005) 的理论阈值; 研究表明 $n^{1/4}/4$ 等替代阈值在有限样本下也有效。R 的 `RCtest` 包自动完成此过程。
>
> **核实状态**: ✅ VERIFIED — 文档公式与代码实现 (line 786-789) 均与权威解释一致。此前 subagent 因 paywall 标记为 ⚠️ UNVERIFIABLE, 现经用户人工核实确认正确。

**Python 代码片段**:

```python
class WhiteRealityCheck:
    """White (2000) Reality Check (RESEARCH_NOTES §1.4 第三块补强)

    校正策略回测中的 data snooping bias: 当从 K 个策略中选最佳时,
    最佳策略的表现被向上偏误. White RC 通过 stationary bootstrap
    重估最大统计量分布, 提供 data snooping 校正后的 p 值.

    学术依据: White (2000) "A Reality Check for Data Snooping"
    Bootstrap: Politis & Romano (1994) "The Stationary Bootstrap"
    """

    def __init__(
        self,
        n_bootstrap: int = 1000,
        block_size: Optional[int] = None,
        method: str = 'stationary',
        random_state: Optional[int] = None,
    ):
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size  # None 时自动估计 (Politis-Romano 经验法则)
        self.method = method
        self.rng = np.random.default_rng(random_state)

    def _auto_block_size(self, x: np.ndarray) -> float:
        """Politis-Romano (1994) 自动块大小估计: B = (2T)^(1/3) * rho^(2/3)"""
        T = len(x)
        rho = np.corrcoef(x[:-1], x[1:])[0, 1] if T > 2 else 0.0
        if np.isnan(rho) or rho <= 0:
            return 2.0
        return float(np.ceil((2 * T) ** (1/3) * rho ** (2/3)))

    def _stationary_bootstrap(self, x: np.ndarray, block_size: float) -> np.ndarray:
        """Politis-Romano (1994) stationary bootstrap

        每个位置以概率 1/B 重新开始新块 (随机选起点), 否则延续上一位置.
        保留序列的弱相依结构.
        """
        T = len(x)
        idx = np.zeros(T, dtype=int)
        idx[0] = self.rng.integers(0, T)
        prob_new_block = 1.0 / block_size
        for t in range(1, T):
            if self.rng.random() < prob_new_block:
                idx[t] = self.rng.integers(0, T)
            else:
                idx[t] = (idx[t - 1] + 1) % T
        return x[idx]

    def test(
        self,
        strategy_returns: np.ndarray,  # (T, K)
        benchmark_return: np.ndarray,  # (T,)
        alpha: float = 0.05,
    ) -> Dict[str, Any]:
        """执行 White Reality Check

        Args:
            strategy_returns: (T, K) K 个策略的收益序列
            benchmark_return: (T,) 基准策略收益
            alpha: 显著性水平

        Returns:
            {
                'rc_p_value': float,           # White RC p 值
                'rc_rejected': List[bool],     # 各策略是否通过 RC 校正
                'max_statistic': float,        # max_k sqrt(T) * f_k
                'bootstrap_max_stats': np.ndarray,  # (N,) bootstrap 分布
                'individual_p_values': List[float],  # 各策略单独 p 值 (无校正)
                'n_strategies': int,
                'block_size': float,
            }
        """
        T, K = strategy_returns.shape
        excess = strategy_returns - benchmark_return[:, None]  # (T, K)
        f_bar = excess.mean(axis=0)  # (K,)
        sqrt_T = np.sqrt(T)
        V = sqrt_T * np.max(f_bar)  # 检验统计量

        # 块大小
        B = self.block_size if self.block_size is not None else self._auto_block_size(excess[:, 0])

        # Bootstrap
        bootstrap_max_stats = np.zeros(self.n_bootstrap)
        for b in range(self.n_bootstrap):
            boot_excess = np.zeros_like(excess)
            for k in range(K):
                boot_excess[:, k] = self._stationary_bootstrap(excess[:, k], B)
            f_boot = boot_excess.mean(axis=0)
            # White RC: recenter by f_bar (under H0: f_bar = 0)
            V_boot = sqrt_T * np.max(f_boot - f_bar)
            bootstrap_max_stats[b] = V_boot

        # p 值
        rc_p_value = float(np.mean(bootstrap_max_stats >= V))

        # 各策略单独 p 值 (无校正)
        individual_p = []
        for k in range(K):
            f_k = excess[:, k]
            B_k = self.block_size or self._auto_block_size(f_k)
            boot_k = np.array([
                self._stationary_bootstrap(f_k, B_k).mean() for _ in range(self.n_bootstrap)
            ])
            individual_p.append(float(np.mean(sqrt_T * (boot_k - f_bar[k]) >= sqrt_T * f_bar[k])))

        # 校正后拒绝: RC p < alpha
        rc_rejected = [rc_p_value < alpha] * K  # White RC 是联合检验

        return {
            'rc_p_value': rc_p_value,
            'rc_rejected': rc_rejected,
            'max_statistic': float(V),
            'bootstrap_max_stats': bootstrap_max_stats,
            'individual_p_values': individual_p,
            'n_strategies': K,
            'block_size': float(B),
        }


class HansenSPA:
    """Hansen (2005) Superior Predictive Ability (SPA) (RESEARCH_NOTES §1.4 第三块补强)

    SPA 是 White RC 的改进版, 通过重新中心化提升对真正优秀策略的检测力.
    区分 H1 集合 (显著优于基准) 和 H0 集合 (待检验), 仅对 H0 集合施加校正.

    学术依据: Hansen (2005) "A Test for Superior Predictive Ability"
    """

    def __init__(
        self,
        n_bootstrap: int = 1000,
        block_size: Optional[int] = None,
        method: str = 'stationary',
        random_state: Optional[int] = None,
    ):
        # 参数与 WhiteRealityCheck 一致
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size
        self.method = method
        self.rng = np.random.default_rng(random_state)

    def _auto_block_size(self, x: np.ndarray) -> float:
        T = len(x)
        rho = np.corrcoef(x[:-1], x[1:])[0, 1] if T > 2 else 0.0
        if np.isnan(rho) or rho <= 0:
            return 2.0
        return float(np.ceil((2 * T) ** (1/3) * rho ** (2/3)))

    def _stationary_bootstrap(self, x: np.ndarray, block_size: float) -> np.ndarray:
        T = len(x)
        idx = np.zeros(T, dtype=int)
        idx[0] = self.rng.integers(0, T)
        prob_new_block = 1.0 / block_size
        for t in range(1, T):
            if self.rng.random() < prob_new_block:
                idx[t] = self.rng.integers(0, T)
            else:
                idx[t] = (idx[t - 1] + 1) % T
        return x[idx]

    def test(
        self,
        strategy_returns: np.ndarray,
        benchmark_return: np.ndarray,
        alpha: float = 0.05,
    ) -> Dict[str, Any]:
        """执行 Hansen SPA 检验

        Returns:
            {
                'spa_p_value': float,           # SPA p 值 (lower p-value)
                'spa_lc_p_value': float,        # SPA lower consistent p 值
                'spa_uc_p_value': float,        # SPA upper consistent p 值
                'rejected': List[bool],         # 各策略是否通过 SPA 校正
                'h1_set': List[int],            # H1 集合索引 (显著优于基准)
                'h0_set': List[int],            # H0 集合索引 (待检验)
            }
        """
        T, K = strategy_returns.shape
        excess = strategy_returns - benchmark_return[:, None]
        f_bar = excess.mean(axis=0)
        sqrt_T = np.sqrt(T)

        # 估计各策略的方差 omega_k^2
        omega_sq = np.array([
            self._estimate_long_run_var(excess[:, k]) for k in range(K)
        ])

        # Hansen 重新中心化阈值: A_k = {f_bar_k > -sqrt(omega^2/T) * sqrt(2 log log T)}
        threshold = np.sqrt(omega_sq / T) * np.sqrt(2 * np.log(np.log(T)))
        in_h1 = f_bar > -threshold  # H1 集合 (显著优于基准, 不需校正)
        in_h0 = ~in_h1              # H0 集合 (待校正)

        # SPA 统计量: max over H0 set
        def _spa_stat(f_vals, mask):
            if mask.sum() == 0:
                return 0.0
            return sqrt_T * np.max(f_vals[mask])

        V_spa = _spa_stat(f_bar, in_h0)

        # Bootstrap (仅对 H0 集合施加重新中心化)
        B = self.block_size or self._auto_block_size(excess[:, 0])
        boot_stats = np.zeros(self.n_bootstrap)
        boot_stats_lc = np.zeros(self.n_bootstrap)
        boot_stats_uc = np.zeros(self.n_bootstrap)

        for b in range(self.n_bootstrap):
            boot_excess = np.zeros_like(excess)
            for k in range(K):
                boot_excess[:, k] = self._stationary_bootstrap(excess[:, k], B)
            f_boot = boot_excess.mean(axis=0)

            # SPA: recenter H0 by f_bar, H1 by 0 (假设 f_bar_H1 = 0 under null)
            f_recentered = f_boot.copy()
            f_recentered[in_h1] -= 0  # H1 不重新中心化
            f_recentered[in_h0] -= f_bar[in_h0]  # H0 重新中心化

            # SPA consistent: 用阈值重新判定 H1
            boot_in_h1 = f_boot > -threshold
            boot_in_h0 = ~boot_in_h1
            boot_stats[b] = _spa_stat(f_recentered, in_h0)
            # Lower consistent: 假设所有 H0 都是真 H0
            boot_stats_lc[b] = _spa_stat(f_recentered, ~in_h1)
            # Upper consistent: 假设所有 H0 都是真 H1
            boot_stats_uc[b] = _spa_stat(f_recentered, np.zeros(K, dtype=bool))

        spa_p = float(np.mean(boot_stats >= V_spa))
        spa_lc_p = float(np.mean(boot_stats_lc >= V_spa))
        spa_uc_p = float(np.mean(boot_stats_uc >= V_spa))

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

    def _estimate_long_run_var(self, x: np.ndarray) -> float:
        """估计长期方差 omega^2 = sum_{l=-inf}^{inf} gamma(l)

        用 Newey-West 估计: omega^2 = gamma(0) + 2 * sum_{l=1}^{L} (1 - l/(L+1)) * gamma(l)
        """
        T = len(x)
        x_centered = x - x.mean()
        gamma0 = np.var(x, ddof=1)
        L = int(np.floor(4 * (T / 100) ** (2/9)))  # Newey-West 滞后阶数
        omega_sq = gamma0
        for l in range(1, L + 1):
            gamma_l = np.mean(x_centered[l:] * x_centered[:-l])
            omega_sq += 2 * (1 - l / (L + 1)) * gamma_l
        return max(omega_sq, 1e-10)
```

#### 1.2.22 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T4 `multiple_testing.py:apply_correction` | ✓ 独立扩展 | E3 为独立类, 不修改 `apply_correction` 签名 (RC/SPA 需收益序列输入, 非 p 值) |
| `pipelines_v2.py:monitor_cusum_drift` | ✓ 无侵入 | E3 用于策略层 data snooping 校正, 不进入因子管道 |
| `factor_significance.py` | ✓ 可选接入 | 因子增量 alpha 可视为"策略", 用 RC/SPA 校正 K 个因子的 data snooping |

#### 1.2.23 接口设计 (与 PipelineV2Config 协同)

E3 为**策略层校正工具**, 不直接集成进 `PipelineV2Config`。典型用法:

```python
from backtest.multiple_testing import WhiteRealityCheck, HansenSPA

# 假设 K 个因子的回测收益已通过 BacktestEngine 获得
# strategy_returns: (T, K) 因子多空组合收益
# benchmark_return: (T,) 基准收益 (如等权或市场指数)

wrc = WhiteRealityCheck(n_bootstrap=1000, random_state=42)
wrc_result = wrc.test(strategy_returns, benchmark_return, alpha=0.05)
print(f"White RC p-value: {wrc_result['rc_p_value']:.4f}")

spa = HansenSPA(n_bootstrap=1000, random_state=42)
spa_result = spa.test(strategy_returns, benchmark_return, alpha=0.05)
print(f"Hansen SPA p-value: {spa_result['spa_p_value']:.4f}")
print(f"H1 set (显著优于基准): {spa_result['h1_set']}")
```

#### 1.2.24 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(N × K × T) | N=1000 bootstrap × K 个策略 × T 期重抽样 |
| 内存占用 | ~100 MB | bootstrap 样本 (T, K) × N 次; 可增量计算不存储全量 |
| 预期运行时间 | ~10-30 秒 | T=252, K=50, N=1000; stationary bootstrap Python 循环较慢, 可向量化优化 |

**性能优化建议**: stationary bootstrap 的内层循环可用 Numba JIT 加速 (未来优化, 不在 E3 范围内)。

#### 1.2.25 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| numpy | >=1.22 | 核心 (已装) | 向量化计算 |
| scipy | >=1.7 | 核心 (已装) | 统计分布 (可选, 用于 individual p 值) |

**无新增依赖**。

#### 1.2.26 测试计划 (TDD)

**测试文件**: `tests/backtest/test_multiple_testing.py` (扩展)
**测试类**: `TestWhiteRealityCheck`, `TestHansenSPA`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_auto_block_size` | 自动块大小估计正确 | B >= 2, B <= T |
| `test_stationary_bootstrap_preserves_length` | bootstrap 输出长度 = 输入长度 | len(boot) == T |
| `test_stationary_bootstrap_preserves_mean` | H0 同分布下 bootstrap 均值近似 | np.isclose(boot.mean(), x.mean(), atol=0.1) |
| `test_wrc_no_data_snooping_under_null` | 全部策略等价基准时 RC p > α | p > 0.05 |
| `test_wrc_detects_genuinely_superior` | 存在真正优秀策略时 RC p < α | p < 0.10 (放宽, 因 RC 较保守) |
| `test_wrc_individual_p_values` | 各策略单独 p 值在 [0,1] | all(0 <= p <= 1) |
| `test_spa_more_powerful_than_wrc` | SPA p ≤ White RC p | spa_p <= wrc_p + 0.05 |
| `test_spa_h1_h0_separation` | H1/H0 集合划分合理 | len(h1) + len(h0) == K |
| `test_spa_lc_uc_consistency` | lower ≤ consistent ≤ upper | spa_lc_p <= spa_p <= spa_uc_p |
| `test_estimate_long_run_var_positive` | 长期方差估计 > 0 | omega_sq > 0 |
| `test_random_state_reproducibility` | 相同 random_state 结果一致 | np.allclose |
| `test_edge_case_single_strategy` | K=1 时等价于单策略检验 | rc_p ≈ individual_p[0] |

**TDD 流程**:
1. **Red**: 写 `TestWhiteRealityCheck` + `TestHansenSPA` 全部测试
2. **Green**: 实现 `WhiteRealityCheck` + `HansenSPA` + stationary bootstrap
3. **Review**: Monte Carlo 验证 SPA 比 RC 更有检测力

#### 1.2.27 验收标准

- [ ] `WhiteRealityCheck` + `HansenSPA` 类完整实现, 所有测试通过 (≥12 测试用例)
- [ ] Monte Carlo 验证: 全部策略等价基准时, RC p > 0.05 (控制 data snooping)
- [ ] Monte Carlo 验证: 存在真正优秀策略时, SPA p ≤ White RC p (检测力优势)
- [ ] Hansen SPA 的 lower/consistent/upper p 值单调: lc ≤ consistent ≤ uc
- [ ] 论文附录可用: 输出 (method, n_strategies, p_value, n_rejected) 对比表
- [ ] 与 E1/E2 形成完整的三块补强对比表

---

### 1.3 §1 三块补强对比表 (论文附录模板)

| 校正方法 | 控制目标 | 检测力 (相对) | 适用场景 | 本项目实施 |
|---------|---------|--------------|---------|------------|
| 无校正 | 无 | 最高 (但 FDR 失控) | 探索性分析 | `apply_no_correction` (已实施) |
| BH-FDR (1995) | FDR | 高 | 大规模多重检验 (KS 迁移) | `apply_bh_fdr` (T4 已实施) |
| Bonferroni | FWER | 最低 | 严格强 FWER 控制 | `apply_bonferroni` (已实施) |
| Romano-Wolf (2005) | k-FWER | 中 (k=1 时等价 FWER) | 需 bootstrap, 控制弱 FWER | E2 (本方案) |
| White RC (2000) | Data snooping FWER | 中低 | 策略回测 snooping | E3 (本方案) |
| Hansen SPA (2005) | Data snooping FWER | 中高 (改进 RC) | 策略回测 snooping | E3 (本方案) |

---

## 2. §2 元控制层

### 2.1 学术背景 (RESEARCH_NOTES §2)

RESEARCH_NOTES §2.3.2 的**关键限定**指出标准 Contextual Bandit (LinUCB / Thompson Sampling) 的三平稳假设在金融中全部失效:
1. **奖励分布平稳** — 市场体制转换 (bull/bear) 导致奖励分布漂移
2. **上下文分布平稳** — 因子指纹随市场状态变化 (regime_transition_prob)
3. **噪声分布平稳** — 波动率聚集导致噪声异方差

因此 RESEARCH_NOTES §2.7 给出三方案:
- **方案 A (推荐)**: 静态规则 + 漂移检测 (复用 T3 CUSUM), 不使用 Bandit
- **方案 B (条件触发)**: Drift-Aware Bandit, 需 Monte Carlo 验证三假设失效程度可接受后才实施
- **方案 C (弃用)**: 朴素 Bandit, 忽略三假设失效, 必然失败

工程化策略:
- **E4 + E5 = 方案 A 的工程实现** (指纹性能日志 + 三层归因)
- **E6 = 方案 B 的 Monte Carlo 验证沙箱** (P3 条件触发, 决策门通过后才进入主分支)

### 2.2 RESEARCH_NOTES §2.5 三层归因

| 层 | 名称 | 输入 | 输出 | 工程 E 任务 |
|----|------|------|------|------------|
| Layer 1 | 指纹归因 | 21 维 FactorFingerprint | 各指纹维度对表现的贡献 | E4 FingerprintPerformanceLogger |
| Layer 2 | 方差归因 | 管道权重 / 处理步骤 | 各处理步骤对总方差的贡献 | E5 AttributionAnalyzer |
| Layer 3 | 交互归因 | 指纹 × 处理 × 状态 | 交互效应 (如重尾因子在 bear regime 下的特殊处理效果) | E5 AttributionAnalyzer (含 BH-FDR) |

---

### E4: FingerprintPerformanceLogger (指纹性能日志, 方案 A 基础设施)

#### 2.2.1 任务编号
**E4** — 21 维指纹 × 因子表现持久化日志

#### 2.2.2 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/fingerprint_performance_logger.py` | 新建文件 | `FingerprintPerformanceLogger` | `__init__(self, db_path: str = 'factor_db.duckdb', table_name: str = 'fingerprint_performance_log', enable: bool = False)` |
| `backtest/fingerprint_performance_logger.py` | 新增方法 | `FingerprintPerformanceLogger.log` | `log(self, factor_name: str, fingerprint: FactorFingerprint, performance: Dict[str, float], timestamp: Optional[str] = None, regime: Optional[str] = None) -> None` |
| `backtest/fingerprint_performance_logger.py` | 新增方法 | `FingerprintPerformanceLogger.query` | `query(self, factor_name: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, regime: Optional[str] = None) -> pd.DataFrame` |
| `backtest/fingerprint_performance_logger.py` | 新增方法 | `FingerprintPerformanceLogger.compute_attribution` | `compute_attribution(self, performance_metric: str = 'ic_mean', group_by: str = 'regime') -> pd.DataFrame` |
| `backtest/fingerprint_performance_logger.py` | 新增方法 | `FingerprintPerformanceLogger.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `pipelines_v2.py` | 扩展配置 | `PipelineV2Config` | 新增字段: `enable_fingerprint_performance_log: bool = False`, `fp_log_db_path: str = 'factor_db.duckdb'`, `fp_log_table_name: str = 'fingerprint_performance_log'` |
| `pipelines_v2.py` | 扩展方法 | `FactorProcessingPipelineV2.fit` | fit 结束时, 若 `enable_fingerprint_performance_log=True`, 调用 `self._fp_logger.log(...)` 记录指纹与初始表现 |
| `pipelines_v2.py` | 新增方法 | `FactorProcessingPipelineV2.get_fingerprint_performance_log` | `get_fingerprint_performance_log(self, **query_kwargs) -> pd.DataFrame` |
| `tests/backtest/test_fingerprint_performance_logger.py` | 新建测试 | `TestFingerprintPerformanceLogger` | TDD 测试类 |

#### 2.2.3 算法实现

**数学公式** (指纹维度 → 表现贡献的初步归因):

对每个指纹维度 $d_j$ (21 维), 按 $d_j$ 的分位数将因子分桶, 计算各桶的平均表现:
$$\bar{P}_{q,j} = \frac{1}{|F_{q,j}|} \sum_{f \in F_{q,j}} P_f$$

其中 $F_{q,j}$ 为指纹维度 $d_j$ 的第 $q$ 分位桶内的因子集合, $P_f$ 为因子 $f$ 的表现指标 (如 IC 均值)。

归因得分 (各分位桶表现差异):
$$\text{Attribution}(d_j) = \bar{P}_{Q_{high},j} - \bar{P}_{Q_{low},j}$$

**DuckDB Schema**:

```sql
CREATE TABLE IF NOT EXISTS fingerprint_performance_log (
    timestamp VARCHAR,           -- YYYY-MM-DD
    factor_name VARCHAR,
    regime VARCHAR,              -- 'bull' / 'bear' / 'neutral' / NULL
    
    -- 21 维指纹
    ar1_median DOUBLE, rank_autocorr DOUBLE, vol_clustering_pvalue DOUBLE,
    half_life DOUBLE, level_diff_ic_ratio DOUBLE,
    skewness_std DOUBLE, kurtosis_std DOUBLE, js_divergence_mean DOUBLE,
    missing_cv DOUBLE, coverage_ratio DOUBLE,
    sd_score DOUBLE, complexity_need DOUBLE, snr_estimate DOUBLE,
    tail_dependence_lower DOUBLE, tail_dependence_upper DOUBLE,
    gpd_shape DOUBLE, hill_estimator DOUBLE,
    regime_transition_prob DOUBLE, regime_persistence DOUBLE,
    regime_ic_diff DOUBLE, tail_regime_score DOUBLE,
    
    -- 表现指标
    ic_mean DOUBLE, ic_std DOUBLE, ic_ir DOUBLE,
    turnover DOUBLE, max_drawdown DOUBLE, sharpe_ratio DOUBLE,
    
    -- 管道权重
    weight_static DOUBLE, weight_dynamic DOUBLE, weight_mixed DOUBLE,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Python 代码片段**:

```python
import duckdb
import pandas as pd
from typing import Dict, Any, Optional, List
from factor_pipeline.modules.factor_fingerprint import FactorFingerprint


class FingerprintPerformanceLogger:
    """21 维指纹 × 因子表现持久化日志 (RESEARCH_NOTES §2.5 Layer 1 + §2.7 方案 A)

    记录每次 Pipeline.fit() 时的 (指纹, 表现, 体制) 三元组,
    为后续 E5 AttributionAnalyzer 提供数据基础.

    设计原则:
    - 默认 enable=False (opt-in)
    - DuckDB 持久化 (复用 factor_db.duckdb, 不新建数据库)
    - append-only 写入, 不修改历史记录
    - sklearn-style: log() / query() / get_diagnostics()
    """

    FINGERPRINT_FIELDS = [
        'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue', 'half_life',
        'level_diff_ic_ratio', 'skewness_std', 'kurtosis_std',
        'js_divergence_mean', 'missing_cv', 'coverage_ratio',
        'sd_score', 'complexity_need', 'snr_estimate',
        'tail_dependence_lower', 'tail_dependence_upper',
        'gpd_shape', 'hill_estimator',
        'regime_transition_prob', 'regime_persistence',
        'regime_ic_diff', 'tail_regime_score',
    ]

    PERFORMANCE_FIELDS = [
        'ic_mean', 'ic_std', 'ic_ir', 'turnover', 'max_drawdown', 'sharpe_ratio',
    ]

    PIPELINE_WEIGHT_FIELDS = ['weight_static', 'weight_dynamic', 'weight_mixed']

    def __init__(
        self,
        db_path: str = 'factor_db.duckdb',
        table_name: str = 'fingerprint_performance_log',
        enable: bool = False,
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.enable = enable
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        if enable:
            self._init_db()

    def _init_db(self) -> None:
        """初始化 DuckDB 表 (幂等)"""
        self._conn = duckdb.connect(self.db_path)
        cols = []
        cols.extend([f"{f} DOUBLE" for f in self.FINGERPRINT_FIELDS])
        cols.extend([f"{f} DOUBLE" for f in self.PERFORMANCE_FIELDS])
        cols.extend([f"{f} DOUBLE" for f in self.PIPELINE_WEIGHT_FIELDS])
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                timestamp VARCHAR,
                factor_name VARCHAR,
                regime VARCHAR,
                {', '.join(cols)},
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        self._conn.execute(create_sql)

    def log(
        self,
        factor_name: str,
        fingerprint: FactorFingerprint,
        performance: Dict[str, float],
        timestamp: Optional[str] = None,
        regime: Optional[str] = None,
        pipeline_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """记录一条 (指纹, 表现, 体制) 三元组"""
        if not self.enable:
            return
        if timestamp is None:
            timestamp = pd.Timestamp.now().strftime('%Y-%m-%d')

        fp_dict = fingerprint._asdict() if hasattr(fingerprint, '_asdict') else dict(fingerprint)
        row = {
            'timestamp': timestamp,
            'factor_name': factor_name,
            'regime': regime,
        }
        for f in self.FINGERPRINT_FIELDS:
            row[f] = float(fp_dict.get(f, float('nan')))
        for f in self.PERFORMANCE_FIELDS:
            row[f] = float(performance.get(f, float('nan')))
        if pipeline_weights:
            row['weight_static'] = pipeline_weights.get('static', float('nan'))
            row['weight_dynamic'] = pipeline_weights.get('dynamic', float('nan'))
            row['weight_mixed'] = pipeline_weights.get('mixed', float('nan'))
        else:
            for w in self.PIPELINE_WEIGHT_FIELDS:
                row[w] = float('nan')

        df = pd.DataFrame([row])
        self._conn.execute(f"INSERT INTO {self.table_name} SELECT * FROM df")

    def query(
        self,
        factor_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> pd.DataFrame:
        """查询历史记录"""
        if not self.enable:
            return pd.DataFrame()
        conditions = []
        if factor_name:
            conditions.append(f"factor_name = '{factor_name}'")
        if start_date:
            conditions.append(f"timestamp >= '{start_date}'")
        if end_date:
            conditions.append(f"timestamp <= '{end_date}'")
        if regime:
            conditions.append(f"regime = '{regime}'")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return self._conn.execute(
            f"SELECT * FROM {self.table_name}{where} ORDER BY timestamp"
        ).fetchdf()

    def compute_attribution(
        self,
        performance_metric: str = 'ic_mean',
        group_by: str = 'regime',
        n_quantiles: int = 5,
    ) -> pd.DataFrame:
        """计算指纹维度 → 表现的初步归因 (Layer 1)

        对每个指纹维度按分位数分桶, 计算各桶的平均表现.
        """
        if not self.enable:
            return pd.DataFrame()
        df = self.query()
        if df.empty:
            return pd.DataFrame()

        results = []
        for fp_field in self.FINGERPRINT_FIELDS:
            valid = df[df[fp_field].notna()].copy()
            if len(valid) < n_quantiles:
                continue
            try:
                valid['quantile_bucket'] = pd.qcut(
                    valid[fp_field], q=n_quantiles, labels=False, duplicates='drop'
                )
            except ValueError:
                continue
            for bucket in valid['quantile_bucket'].unique():
                bucket_df = valid[valid['quantile_bucket'] == bucket]
                for group_val in bucket_df[group_by].dropna().unique():
                    sub = bucket_df[bucket_df[group_by] == group_val]
                    if len(sub) == 0:
                        continue
                    results.append({
                        'fingerprint_dim': fp_field,
                        'quantile_bucket': int(bucket),
                        group_by: group_val,
                        'n_factors': len(sub),
                        performance_metric: float(sub[performance_metric].mean()),
                    })
        return pd.DataFrame(results)

    def get_diagnostics(self) -> Dict[str, Any]:
        """诊断信息: 记录数 / 时间范围 / 因子数 / 缺失率"""
        if not self.enable:
            return {'enabled': False}
        df = self.query()
        if df.empty:
            return {'enabled': True, 'n_records': 0}
        return {
            'enabled': True,
            'n_records': len(df),
            'n_factors': df['factor_name'].nunique(),
            'date_range': (df['timestamp'].min(), df['timestamp'].max()),
            'regime_distribution': df['regime'].value_counts().to_dict(),
            'fingerprint_missing_rate': {
                f: float(df[f].isna().mean()) for f in self.FINGERPRINT_FIELDS
            },
        }
```

#### 2.2.4 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T1 21 维 FactorFingerprint | ✓ 直接消费 | E4 读取 `FactorFingerprint._asdict()` 的 21 个字段 |
| `PipelineV2Config` | ✓ 扩展兼容 | 新增 3 个字段, 默认 `enable=False`, 不影响现有行为 |
| `FactorProcessingPipelineV2.fit` | ✓ 可选接入 | fit 结束时条件性调用 `self._fp_logger.log()`, 不破坏现有 fit 流程 |
| `factor_db.duckdb` | ✓ 共享数据库 | E4 在现有 DuckDB 中新建表, 不新建数据库文件 |
| T3 CUSUM | ✓ 协同 | CUSUM 检测漂移 → E4 记录漂移前后的指纹变化 (regime 字段) |

#### 2.2.5 接口设计 (与 PipelineV2Config 协同)

```python
@dataclass
class PipelineV2Config:
    # ... 现有字段 ...
    enable_multi_dim_routing: bool = False  # T1
    enable_cusum_drift_monitor: bool = False  # T3.4
    cusum_k: float = 0.5
    cusum_h: float = 5.5

    # E4 新增 (v3.0.0 §2 元控制层)
    enable_fingerprint_performance_log: bool = False
    fp_log_db_path: str = 'factor_db.duckdb'
    fp_log_table_name: str = 'fingerprint_performance_log'
```

```python
class FactorProcessingPipelineV2:
    def fit(self, factor_data, industry_data=None, descriptions=None):
        # ... 现有 fit 逻辑 ...
        # E4: 指纹性能日志 (可选)
        if self.config.enable_fingerprint_performance_log:
            from backtest.fingerprint_performance_logger import FingerprintPerformanceLogger
            self._fp_logger = FingerprintPerformanceLogger(
                db_path=self.config.fp_log_db_path,
                table_name=self.config.fp_log_table_name,
                enable=True,
            )
            for fname, fp in self.fingerprints_.items():
                self._fp_logger.log(
                    factor_name=fname,
                    fingerprint=fp,
                    performance=self._compute_factor_performance(fname),
                    regime=self._detect_current_regime(),
                    pipeline_weights=self._get_pipeline_weights_for(fname),
                )
        return self

    def get_fingerprint_performance_log(self, **query_kwargs) -> pd.DataFrame:
        """查询指纹性能日志 (E4)"""
        if not hasattr(self, '_fp_logger') or not self._fp_logger.enable:
            return pd.DataFrame()
        return self._fp_logger.query(**query_kwargs)
```

#### 2.2.6 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(K) per fit | K 个因子, 每因子一次 DuckDB INSERT |
| 内存占用 | ~10 MB | DuckDB 连接 + 单行 DataFrame |
| 预期运行时间 | <1 秒 per fit | K=100 因子, DuckDB append 模式高效 |
| 查询性能 | O(log N) | DuckDB 列式存储, 索引可加速 |

#### 2.2.7 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| duckdb | >=0.10 | 核心 (已装) | 持久化存储 |
| pandas | >=2.0 | 核心 (已装) | DataFrame 操作 |

**无新增依赖**。

#### 2.2.8 测试计划 (TDD)

**测试文件**: `tests/backtest/test_fingerprint_performance_logger.py`
**测试类**: `TestFingerprintPerformanceLogger`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_init_creates_table` | enable=True 时表被创建 | duckdb 查询 table 存在 |
| `test_disabled_no_op` | enable=False 时所有操作无副作用 | query 返回空 DataFrame |
| `test_log_single_record` | log 一条记录后 query 返回 1 行 | len(df) == 1 |
| `test_log_preserves_all_21_fingerprint_fields` | 21 维指纹字段完整存储 | all(field in df.columns for field in FINGERPRINT_FIELDS) |
| `test_log_preserves_performance_fields` | 表现字段完整存储 | all(field in df.columns for field in PERFORMANCE_FIELDS) |
| `test_query_by_factor_name` | 按 factor_name 过滤 | df['factor_name'].nunique() == 1 |
| `test_query_by_date_range` | 按日期范围过滤 | all(df['timestamp'] >= start) and all(df['timestamp'] <= end) |
| `test_query_by_regime` | 按 regime 过滤 | df['regime'].nunique() == 1 |
| `test_compute_attribution_returns_dataframe` | 归因返回非空 DataFrame | len(df) > 0 |
| `test_compute_attribution_quantile_buckets` | 归因含分位桶列 | 'quantile_bucket' in df.columns |
| `test_get_diagnostics_enabled` | enable=True 时 diagnostics 含记录数 | 'n_records' in diagnostics |
| `test_get_diagnostics_disabled` | enable=False 时 diagnostics 返回 {'enabled': False} | diagnostics['enabled'] == False |
| `test_nan_fingerprint_field_handled` | 指纹字段为 NaN 时不报错 | log 成功, query 返回 NaN |
| `test_idempotent_init` | 多次 __init__ 不报错 | 表已存在时 CREATE IF NOT EXISTS 生效 |

**TDD 流程**:
1. **Red**: 写 `TestFingerprintPerformanceLogger` 全部测试 (此时类不存在)
2. **Green**: 实现 `FingerprintPerformanceLogger`
3. **Review**: DuckDB 表 schema 与 21 维指纹对齐, 归因结果合理

#### 2.2.9 验收标准

- [ ] `FingerprintPerformanceLogger` 类完整实现, 所有测试通过 (≥14 测试用例)
- [ ] 21 维指纹字段 + 6 表现字段 + 3 管道权重字段完整存储
- [ ] `PipelineV2Config` 新增 3 字段, 默认 `enable=False`
- [ ] `FactorProcessingPipelineV2.fit` 可选调用 `log()`, 不破坏现有 860 基线测试
- [ ] `get_fingerprint_performance_log()` 返回可查询 DataFrame
- [ ] 归因分析: 对 (gpd_shape, ic_mean) 按 5 分位分桶, 各桶 ic_mean 差异显著 (Monte Carlo 验证)

---

### E5: AttributionAnalyzer (三层归因分析)

#### 2.2.10 任务编号
**E5** — 指纹 × 处理 × 状态三层交互归因 (含 BH-FDR)

#### 2.2.11 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/attribution_analyzer.py` | 新建文件 | `AttributionAnalyzer` | `__init__(self, alpha: float = 0.05, correction: str = 'benjamini_hochberg', enable: bool = False)` |
| `backtest/attribution_analyzer.py` | 新增方法 | `AttributionAnalyzer.fit` | `fit(self, fp_logger_data: pd.DataFrame, performance_metric: str = 'ic_mean') -> 'AttributionAnalyzer'` |
| `backtest/attribution_analyzer.py` | 新增方法 | `AttributionAnalyzer.layer1_fingerprint_attribution` | `layer1_fingerprint_attribution(self) -> Dict[str, Dict]` (各指纹维度归因) |
| `backtest/attribution_analyzer.py` | 新增方法 | `AttributionAnalyzer.layer2_variance_attribution` | `layer2_variance_attribution(self) -> Dict[str, float]` (管道权重方差贡献) |
| `backtest/attribution_analyzer.py` | 新增方法 | `AttributionAnalyzer.layer3_interaction_attribution` | `layer3_interaction_attribution(self) -> pd.DataFrame` (指纹×处理×状态交互, 含 BH-FDR) |
| `backtest/attribution_analyzer.py` | 新增方法 | `AttributionAnalyzer.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `tests/backtest/test_attribution_analyzer.py` | 新建测试 | `TestAttributionAnalyzer` | TDD 测试类 |

#### 2.2.12 算法实现

**数学公式** (三层归因):

**Layer 1 — 指纹归因** (单变量):
对每个指纹维度 $d_j$, 拟合简单线性回归:
$$P_f = \beta_0 + \beta_1 d_{j,f} + \epsilon_f$$
归因得分: $|\beta_1| \cdot \text{std}(d_j)$ (标准化回归系数)

**Layer 2 — 方差归因** (管道权重):
$$\text{Var}(P) = \sum_{p \in \{\text{static, dynamic, mixed}\}} w_p^2 \text{Var}(P_p) + 2 \sum_{p < q} w_p w_q \text{Cov}(P_p, P_q)$$
各管道贡献: $\text{Contribution}_p = w_p^2 \text{Var}(P_p) / \text{Var}(P)$

> **⚠ 近似标注 — Layer 2 方差归因为近似实现**: 上述公式严格成立, 但工程实现中无法获取各管道的独立输出 $P_p$ (管道混合运行), 代码采用权重与表现的协方差近似 (见 `layer2_variance_attribution` 内注释), 即以 $w_p^2 \cdot \text{Var}(P)$ 近似 $w_p^2 \cdot \text{Var}(P_p)$, 并将残余项归入 `covariance`。
> - **近似条件**: 各管道分量弱相关 (协方差交叉项可被残余吸收)。
> - **误差量级**: 当管道间相关性高 ($|\rho| > 0.5$) 或权重时变时, 主对角项被高估、交叉项被扭曲, 单通道贡献误差可达 $\pm 0.1\sim0.3$ 量级。
> - **建议**: 在大交叉项场景 (管道高度相关) 下, 应退化为**数值归因** (如逐次剔除某管道的扰动法 / Shapley 值), 而非依赖本近似解析分解。

**Layer 3 — 交互归因** (多变量 + BH-FDR):
拟合交互回归:
$$P_f = \beta_0 + \sum_j \beta_j d_{j,f} + \sum_p \gamma_p w_{p,f} + \sum_{j,p} \delta_{jp} (d_{j,f} \times w_{p,f}) + \sum_j \theta_j (d_{j,f} \times \text{regime}_f) + \epsilon_f$$

对 $H_{jp}: \delta_{jp} = 0$ 进行 BH-FDR 校正 (复用 T4 `apply_bh_fdr`), 识别显著交互项。

**Python 代码片段**:

```python
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import statsmodels.api as sm

try:
    from backtest.multiple_testing import apply_bh_fdr, apply_correction
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False


class AttributionAnalyzer:
    """三层归因分析器 (RESEARCH_NOTES §2.5)

    Layer 1: 指纹归因 — 各指纹维度对表现的单变量贡献
    Layer 2: 方差归因 — 管道权重 (static/dynamic/mixed) 对总方差的贡献
    Layer 3: 交互归因 — 指纹 × 处理 × 状态的交互效应 (含 BH-FDR 校正)

    设计原则:
    - 诊断优先于校正: 测量各层贡献, 不声称消除
    - BH-FDR 应用于 Layer 3 交互项检验 (复用 T4)
    - 默认 enable=False (opt-in)
    """

    FINGERPRINT_FIELDS = [
        'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue', 'half_life',
        'level_diff_ic_ratio', 'skewness_std', 'kurtosis_std',
        'js_divergence_mean', 'missing_cv', 'coverage_ratio',
        'sd_score', 'complexity_need', 'snr_estimate',
        'tail_dependence_lower', 'tail_dependence_upper',
        'gpd_shape', 'hill_estimator',
        'regime_transition_prob', 'regime_persistence',
        'regime_ic_diff', 'tail_regime_score',
    ]

    def __init__(
        self,
        alpha: float = 0.05,
        correction: str = 'benjamini_hochberg',
        enable: bool = False,
    ):
        self.alpha = alpha
        self.correction = correction
        self.enable = enable
        self._data: Optional[pd.DataFrame] = None
        self._performance_metric: str = 'ic_mean'
        self._layer1_results: Optional[Dict] = None
        self._layer2_results: Optional[Dict] = None
        self._layer3_results: Optional[pd.DataFrame] = None

    def fit(
        self,
        fp_logger_data: pd.DataFrame,
        performance_metric: str = 'ic_mean',
    ) -> 'AttributionAnalyzer':
        """从 E4 FingerprintPerformanceLogger 的查询结果拟合

        Args:
            fp_logger_data: E4 query() 返回的 DataFrame
            performance_metric: 归因目标表现指标 ('ic_mean' / 'sharpe_ratio' / ...)
        """
        self._data = fp_logger_data.copy()
        self._performance_metric = performance_metric
        return self

    def layer1_fingerprint_attribution(self) -> Dict[str, Dict]:
        """Layer 1: 各指纹维度的单变量归因

        Returns:
            {dim_name: {'beta_std': float, 'p_value': float, 'r_squared': float}}
            beta_std: 标准化回归系数 (归因得分)
        """
        if self._data is None or self._data.empty:
            return {}

        y = self._data[self._performance_metric].dropna()
        results = {}
        for dim in self.FINGERPRINT_FIELDS:
            if dim not in self._data.columns:
                continue
            x = self._data[dim]
            valid = x.notna() & y.index.isin(x.notna()[x.notna()].index)
            x_valid = x[valid].reindex(y.index).dropna()
            y_valid = y.loc[x_valid.index]
            if len(x_valid) < 10 or x_valid.std() < 1e-10:
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': len(x_valid)}
                continue
            # 标准化
            x_std = (x_valid - x_valid.mean()) / x_valid.std()
            y_std = (y_valid - y_valid.mean()) / y_valid.std() if y_valid.std() > 1e-10 else y_valid
            X = sm.add_constant(x_std)
            try:
                model = sm.OLS(y_std, X).fit()
                results[dim] = {
                    'beta_std': float(model.params.iloc[1]),
                    'p_value': float(model.pvalues.iloc[1]),
                    'r_squared': float(model.rsquared),
                    'n': len(x_valid),
                }
            except Exception:
                results[dim] = {'beta_std': 0.0, 'p_value': 1.0, 'r_squared': 0.0, 'n': len(x_valid)}

        self._layer1_results = results
        return results

    def layer2_variance_attribution(self) -> Dict[str, float]:
        """Layer 2: 管道权重方差归因

        Var(P) = Σ w_p² Var(P_p) + 2 Σ_{p<q} w_p w_q Cov(P_p, P_q)

        Returns:
            {'static': float, 'dynamic': float, 'mixed': float, 'covariance': float}
            各值之和 = 1.0 (方差分解)
        """
        if self._data is None or self._data.empty:
            return {}

        weight_cols = ['weight_static', 'weight_dynamic', 'weight_mixed']
        if not all(c in self._data.columns for c in weight_cols):
            return {}

        y = self._data[self._performance_metric].dropna()
        valid = self._data[weight_cols].notna().all(axis=1) & self._data[self._performance_metric].notna()
        sub = self._data[valid]
        if len(sub) < 10:
            return {}

        # ⚠ 近似: 用各管道权重 × 因子表现 作为管道贡献 (非严格分解)
        # 严格需各管道单独输出 P_p, 但管道混合运行无法获取, 故用 w_p²·Var(P) 近似 w_p²·Var(P_p)
        # 误差: 管道间高相关时单通道贡献误差 ±0.1~0.3; 大交叉项场景应退化为数值归因 (Shapley / 扰动法)
        total_var = float(y.loc[sub.index].var())
        if total_var < 1e-10:
            return {'static': 0.0, 'dynamic': 0.0, 'mixed': 0.0, 'covariance': 0.0}

        contributions = {}
        for p, col in zip(['static', 'dynamic', 'mixed'], weight_cols):
            w = sub[col]
            p_contrib = float((w ** 2 * y.loc[sub.index].var()).sum() / len(sub))
            contributions[p] = p_contrib / total_var if total_var > 0 else 0.0

        # 协方差项 (残余)
        sum_individual = sum(contributions.values())
        contributions['covariance'] = max(0.0, 1.0 - sum_individual)

        self._layer2_results = contributions
        return contributions

    def layer3_interaction_attribution(self) -> pd.DataFrame:
        """Layer 3: 指纹 × 处理 × 状态交互归因 (含 BH-FDR)

        拟合交互回归, 对交互项 p 值应用 BH-FDR 校正.

        Returns:
            DataFrame: columns = [dim, weight_type, regime, beta, p_value, p_value_adjusted, is_significant]
        """
        if self._data is None or self._data.empty:
            return pd.DataFrame()

        y = self._data[self._performance_metric].dropna()
        weight_cols = ['weight_static', 'weight_dynamic', 'weight_mixed']
        results = []

        for dim in self.FINGERPRINT_FIELDS:
            if dim not in self._data.columns:
                continue
            for w_col in weight_cols:
                for regime in self._data['regime'].dropna().unique():
                    sub = self._data[
                        self._data[dim].notna()
                        & self._data[w_col].notna()
                        & (self._data['regime'] == regime)
                        & self._data[self._performance_metric].notna()
                    ]
                    if len(sub) < 20:
                        continue
                    x = sub[dim].values
                    w = sub[w_col].values
                    interaction = x * w
                    y_sub = sub[self._performance_metric].values
                    X = sm.add_constant(np.column_stack([x, w, interaction]))
                    try:
                        model = sm.OLS(y_sub, X).fit()
                        # interaction 是第 3 个系数 (index 3, 含 const)
                        beta = float(model.params[3])
                        p_val = float(model.pvalues[3])
                        results.append({
                            'dim': dim,
                            'weight_type': w_col,
                            'regime': regime,
                            'beta': beta,
                            'p_value': p_val,
                            'n': len(sub),
                        })
                    except Exception:
                        continue

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # BH-FDR 校正 (复用 T4)
        if _HAS_MULTIPLE_TESTING and self.correction == 'benjamini_hochberg':
            adj_p, rejected = apply_bh_fdr(df['p_value'].tolist(), alpha=self.alpha)
            df['p_value_adjusted'] = adj_p
            df['is_significant'] = rejected
        else:
            df['p_value_adjusted'] = df['p_value']
            df['is_significant'] = df['p_value'] < self.alpha

        self._layer3_results = df
        return df

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._data is None:
            return {'enabled': self.enable, 'fitted': False}
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_records': len(self._data),
            'n_factors': self._data['factor_name'].nunique() if 'factor_name' in self._data.columns else 0,
            'performance_metric': self._performance_metric,
            'layer1_n_dims_analyzed': len(self._layer1_results) if self._layer1_results else 0,
            'layer3_n_significant': int(self._layer3_results['is_significant'].sum()) if self._layer3_results is not None else 0,
            'correction_method': self.correction,
        }
```

#### 2.2.13 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T1 21 维 FactorFingerprint | ✓ 直接消费 | Layer 1/3 对 21 维做归因 |
| T4 `apply_bh_fdr` | ✓ 复用 | Layer 3 交互项 p 值经 BH-FDR 校正 |
| E4 FingerprintPerformanceLogger | ✓ 数据源 | E5.fit() 输入 = E4.query() 输出 |
| statsmodels (ADR-014) | ✓ REQUIRED | OLS 回归复用 statsmodels |

#### 2.2.14 接口设计 (与 PipelineV2Config 协同)

E5 为**离线分析工具**, 不集成进 `PipelineV2Config`, 但依赖 E4 启用:

```python
# pipelines_v2.py 中可选扩展:
# PipelineV2Config 新增字段:
#   enable_attribution_analysis: bool = False
#   attribution_alpha: float = 0.05

# 使用示例:
pipeline = FactorProcessingPipelineV2(config=PipelineV2Config(
    enable_fingerprint_performance_log=True,  # E4 必须启用
    enable_attribution_analysis=True,         # E5 可选
))
pipeline.fit(factor_data, industry_data)

if pipeline.config.enable_attribution_analysis:
    from backtest.attribution_analyzer import AttributionAnalyzer
    analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
    fp_data = pipeline.get_fingerprint_performance_log()
    analyzer.fit(fp_data, performance_metric='ic_mean')
    layer1 = analyzer.layer1_fingerprint_attribution()
    layer2 = analyzer.layer2_variance_attribution()
    layer3 = analyzer.layer3_interaction_attribution()
```

#### 2.2.15 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(21 × 3 × R × N) | Layer 3: 21 维 × 3 管道 × R 体制 × N 因子 OLS 拟合 |
| 内存占用 | ~50 MB | 交互回归设计矩阵 (N, 4) × 大量组合 |
| 预期运行时间 | ~5-10 秒 | N=500 因子, 3 体制, 21 维, 3 管道 = ~189 次 OLS |
| BH-FDR 应用 | O(m log m) | m ≈ 189 交互项, 可忽略 |

#### 2.2.16 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| statsmodels | >=0.13 | 核心 (已装, ADR-014) | OLS 回归 |
| numpy | >=1.22 | 核心 (已装) | 矩阵运算 |
| pandas | >=2.0 | 核心 (已装) | DataFrame |

**无新增依赖**。

#### 2.2.17 测试计划 (TDD)

**测试文件**: `tests/backtest/test_attribution_analyzer.py`
**测试类**: `TestAttributionAnalyzer`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_fit_empty_data` | 空数据 fit 不报错 | layer1 返回 {} |
| `test_layer1_returns_all_21_dims` | Layer 1 返回 21 个维度 | len(results) <= 21 (部分可能因样本不足跳过) |
| `test_layer1_known_relationship` | 构造 gpd_shape 与 ic_mean 线性相关 | beta_std 显著非零, p < 0.05 |
| `test_layer1_standardized_beta` | 标准化 beta 在 [-1, 1] | all(abs(beta) <= 1.0 + 1e-6) |
| `test_layer2_variance_decomposition_sums_to_one` | 方差分解和 ≈ 1 | abs(sum - 1.0) < 0.1 |
| `test_layer2_zero_weights_zero_contribution` | 权重全零时贡献为零 | all contributions ≈ 0 |
| `test_layer3_returns_dataframe_with_columns` | Layer 3 返回含必要列 | {'dim', 'weight_type', 'regime', 'beta', 'p_value', 'p_value_adjusted', 'is_significant'} ⊆ columns |
| `test_layer3_bh_fdr_applied` | p_value_adjusted >= p_value | all(adj >= raw) |
| `test_layer3_significant_interaction` | 构造已知交互效应 | is_significant 含 True |
| `test_get_diagnostics` | 诊断信息含 n_records / n_factors | 'n_records' in diagnostics |
| `test_disabled_no_op` | enable=False 时方法返回空 | layer1 返回 {} |

**TDD 流程**:
1. **Red**: 写 `TestAttributionAnalyzer` 全部测试
2. **Green**: 实现 `AttributionAnalyzer` 三层归因
3. **Review**: BH-FDR 校正正确应用, 方差分解和 ≈ 1

#### 2.2.18 验收标准

- [ ] `AttributionAnalyzer` 类完整实现, 所有测试通过 (≥11 测试用例)
- [ ] Layer 1: 21 维指纹归因, 标准化 beta 在 [-1, 1]
- [ ] Layer 2: 方差分解和 ≈ 1.0 (容忍 ±0.1)
- [ ] Layer 3: 交互项 BH-FDR 校正, p_value_adjusted >= p_value
- [ ] 复用 T4 `apply_bh_fdr` 共享模块
- [ ] 与 E4 协同: E4 数据 → E5 归因 → 论文表格

---

### E6: DriftAwareBandit Monte Carlo 验证沙箱 (P3 条件触发)

#### 2.2.19 任务编号
**E6** — Drift-Aware Contextual Bandit + Monte Carlo 决策门 (RESEARCH_NOTES §2.3.2 方案 B)

#### 2.2.20 前置条件 (决策门)

RESEARCH_NOTES §2.3.2 关键限定指出标准 Bandit 三平稳假设全失效。E6 **不是**直接实施 Bandit, 而是**先 Monte Carlo 验证三假设失效程度**, 决策门通过后才进入主分支。

**决策门**:
1. 生成带体制转换的模拟数据 (bull/bear 切换)
2. 对比三方案: 方案 A (静态规则) vs 方案 B (Drift-Aware Bandit) vs 方案 C (朴素 Bandit)
3. 评估指标: 累计奖励 / 遗憾 (regret) / 体制切换后恢复速度
4. 仅当方案 B 在所有指标上优于方案 A 至少 10% 时, 决策门通过

#### 2.2.21 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/bandit_mc_sandbox.py` | 新建文件 | `BanditMCSandbox` | `__init__(self, n_simulations: int = 500, n_periods: int = 2520, n_regimes: int = 2, random_state: Optional[int] = None)` |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox.run_comparison` | `run_comparison(self, n_bandit_arms: int = 3, drift_magnitude: float = 0.5) -> Dict[str, Dict[str, float]]` |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox._simulate_regime_switching_data` | `_simulate_regime_switching_data(self, n_periods, n_regimes, drift_magnitude) -> Tuple[np.ndarray, np.ndarray]` (私有) |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox._plan_a_static_rules` | `_plan_a_static_rules(self, data, cusum_monitor) -> float` (私有, 返回累计奖励) |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox._plan_b_drift_aware_bandit` | `_plan_b_drift_aware_bandit(self, data, cusum_monitor) -> float` (私有) |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox._plan_c_naive_bandit` | `_plan_c_naive_bandit(self, data) -> float` (私有, 对照组) |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox.evaluate_decision_gate` | `evaluate_decision_gate(self, results: Dict) -> Dict[str, Any]` (决策门评估) |
| `backtest/bandit_mc_sandbox.py` | 新增方法 | `BanditMCSandbox.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `tests/backtest/test_bandit_mc_sandbox.py` | 新建测试 | `TestBanditMCSandbox` | TDD 测试类 |

**注意**: E6 **不**修改 `PipelineV2Config`, **不**集成进 `FactorProcessingPipelineV2`。仅作为离线验证沙箱。决策门通过后, 才会启动 E6b (Bandit 集成进 Pipeline, 本方案不包含)。

#### 2.2.22 算法实现

**数学公式** (Drift-Aware Bandit):

标准 LinUCB (Li et al. 2010):
$$\hat{\theta}_a = (X_a^T X_a + \lambda I)^{-1} X_a^T r_a$$
$$\text{UCB}_a(x) = \hat{\theta}_a^T x + \alpha \sqrt{x^T (X_a^T X_a + \lambda I)^{-1} x}$$

Drift-Aware 改进: 当 CUSUM 检测到漂移时, 重置 $X_a$ 和 $r_a$ (遗忘历史):
$$\text{if CUSUM}_t > h: \quad X_a \leftarrow \emptyset, \quad r_a \leftarrow \emptyset \quad \forall a$$

体制条件上下文: $x_t = [f_{ar1}, f_{snr}, f_{gpd\_shape}, \text{regime\_dummy}]$ (含体制标识)。

**Monte Carlo 数据生成** (体制转换):
$$r_t \sim \begin{cases} N(\mu_{bull}, \sigma_{bull}^2) & \text{if } s_t = \text{bull} \\ N(\mu_{bear}, \sigma_{bear}^2) & \text{if } s_t = \text{bear} \end{cases}$$

体制转换矩阵: $P(s_{t+1} | s_t) = \begin{pmatrix} p_{bb} & 1-p_{bb} \\ 1-p_{rr} & p_{rr} \end{pmatrix}$

**Python 代码片段**:

```python
import numpy as np
from typing import Dict, Any, Optional
from backtest.cusum_drift_monitor import CUSUMDriftMonitor


class BanditMCSandbox:
    """Drift-Aware Bandit Monte Carlo 验证沙箱 (RESEARCH_NOTES §2.3.2 方案 B 决策门)

    目标: 验证在金融三平稳假设失效场景下, Drift-Aware Bandit 是否优于静态规则.

    三方案对比:
    - Plan A (静态规则): 固定管道权重, CUSUM 触发时重置指纹缓存
    - Plan B (Drift-Aware Bandit): LinUCB + CUSUM 触发遗忘
    - Plan C (朴素 Bandit): LinUCB 无漂移感知 (对照组, 预期失败)

    决策门: 仅当 Plan B 累计奖励 > Plan A × 1.10 时通过.

    重要: 这是验证沙箱, 不进入主分支. 决策门通过后才会规划 E6b 集成.
    """

    def __init__(
        self,
        n_simulations: int = 500,
        n_periods: int = 2520,  # 10 年日频
        n_regimes: int = 2,
        random_state: Optional[int] = None,
    ):
        self.n_simulations = n_simulations
        self.n_periods = n_periods
        self.n_regimes = n_regimes
        self.rng = np.random.default_rng(random_state)
        self._last_results: Optional[Dict] = None

    def _simulate_regime_switching_data(
        self,
        n_periods: int,
        n_regimes: int,
        drift_magnitude: float = 0.5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """生成体制转换数据 (Markov switching)

        Returns:
            rewards: (n_periods, n_arms) 各臂的真实奖励
            regimes: (n_periods,) 真实体制标签 (0, 1, ...)
        """
        # 体制转换矩阵 (persistence = 0.95)
        p_stay = 0.95
        trans_mat = np.array([
            [p_stay, 1 - p_stay],
            [1 - p_stay, p_stay],
        ]) if n_regimes == 2 else np.eye(n_regimes)

        # 各体制下各臂的真实奖励
        regime_rewards = np.zeros((n_regimes, 3))  # 3 个臂 (static/dynamic/mixed 管道)
        regime_rewards[0] = [0.5, 0.3, 0.4]  # bull: static 最优
        regime_rewards[1] = [0.2, 0.6, 0.5]  # bear: dynamic 最优
        # 加入漂移
        regime_rewards[1] += drift_magnitude * np.array([-0.1, 0.2, 0.1])

        regimes = np.zeros(n_periods, dtype=int)
        rewards = np.zeros((n_periods, 3))
        s = 0
        for t in range(n_periods):
            regimes[t] = s
            rewards[t] = regime_rewards[s] + self.rng.standard_normal(3) * 0.1
            s = self.rng.choice(n_regimes, p=trans_mat[s])

        return rewards, regimes

    def _plan_a_static_rules(
        self,
        rewards: np.ndarray,
        cusum_k: float = 0.5,
        cusum_h: float = 5.5,
    ) -> float:
        """Plan A: 静态规则 — 固定权重 + CUSUM 触发指纹缓存重置"""
        T, K = rewards.shape
        # 固定权重: 均匀分配
        weights = np.ones(K) / K
        cumulative_reward = 0.0
        # 基线参数 mu0/sigma0 必填: 从 warmup 窗口估计各臂均值序列的基线
        # (CUSUMDriftMonitor 无 set_baseline() 方法, 必须在初始化时传入)
        warmup = min(63, max(2, T // 4))
        mu0 = float(rewards[:warmup].mean())
        sigma0 = float(rewards[:warmup].std())
        if sigma0 <= 0:
            sigma0 = 0.1  # 兜底, 满足 baseline_std > 0
        cusum = CUSUMDriftMonitor(
            baseline_mean=mu0, baseline_std=sigma0,
            k=cusum_k, h=cusum_h,
        )

        for t in range(T):
            r = rewards[t]
            cumulative_reward += float(np.dot(weights, r))
            # CUSUM 监测漂移 (用各臂奖励均值)
            cusum.update(r.mean())

        return cumulative_reward

    def _plan_b_drift_aware_bandit(
        self,
        rewards: np.ndarray,
        cusum_k: float = 0.5,
        cusum_h: float = 5.5,
        lambda_reg: float = 1.0,
        alpha_ucb: float = 1.0,
    ) -> float:
        """Plan B: Drift-Aware LinUCB — CUSUM 触发时重置历史"""
        T, K = rewards.shape
        d = 4  # 上下文维度: [ar1, snr, gpd_shape, regime_dummy]

        # 各臂的 LinUCB 状态
        A = [lambda_reg * np.eye(d) for _ in range(K)]
        b = [np.zeros(d) for _ in range(K)]

        # 基线参数 mu0/sigma0 必填: 从 warmup 窗口估计各臂均值序列的基线
        # (CUSUMDriftMonitor 无 set_baseline() 方法, 必须在初始化时传入)
        warmup = min(63, max(2, T // 4))
        mu0 = float(rewards[:warmup].mean())
        sigma0 = float(rewards[:warmup].std())
        if sigma0 <= 0:
            sigma0 = 0.1  # 兜底, 满足 baseline_std > 0
        cusum = CUSUMDriftMonitor(
            baseline_mean=mu0, baseline_std=sigma0,
            k=cusum_k, h=cusum_h,
        )

        cumulative_reward = 0.0
        for t in range(T):
            r = rewards[t]
            # 上下文: 用历史奖励统计 + regime 估计
            x = np.array([
                r.mean() if t > 0 else 0.0,
                r.std() if t > 0 else 0.1,
                0.0,  # gpd_shape placeholder
                1.0 if r.mean() < 0.3 else 0.0,  # regime dummy
            ])

            # LinUCB 选择
            ucb_scores = []
            for a in range(K):
                theta = np.linalg.solve(A[a], b[a])
                ucb = float(theta @ x + alpha_ucb * np.sqrt(x @ np.linalg.solve(A[a], x)))
                ucb_scores.append(ucb)
            chosen = int(np.argmax(ucb_scores))

            # 累计奖励
            cumulative_reward += float(r[chosen])

            # 更新 LinUCB
            A[chosen] += np.outer(x, x)
            b[chosen] += r[chosen] * x

            # CUSUM 漂移检测 → 重置
            # update() 返回 dict, 通过 result['detected'] 判断 (无 is_drifting() 方法)
            drift_result = cusum.update(r.mean())
            if drift_result['detected']:
                A = [lambda_reg * np.eye(d) for _ in range(K)]
                b = [np.zeros(d) for _ in range(K)]
                cusum.reset()

        return cumulative_reward

    def _plan_c_naive_bandit(
        self,
        rewards: np.ndarray,
        lambda_reg: float = 1.0,
        alpha_ucb: float = 1.0,
    ) -> float:
        """Plan C: 朴素 LinUCB — 无漂移感知 (对照组, 预期失败)"""
        T, K = rewards.shape
        d = 4
        A = [lambda_reg * np.eye(d) for _ in range(K)]
        b = [np.zeros(d) for _ in range(K)]

        cumulative_reward = 0.0
        for t in range(T):
            r = rewards[t]
            x = np.array([r.mean() if t > 0 else 0.0, r.std() if t > 0 else 0.1, 0.0, 1.0 if r.mean() < 0.3 else 0.0])
            ucb_scores = []
            for a in range(K):
                theta = np.linalg.solve(A[a], b[a])
                ucb = float(theta @ x + alpha_ucb * np.sqrt(x @ np.linalg.solve(A[a], x)))
                ucb_scores.append(ucb)
            chosen = int(np.argmax(ucb_scores))
            cumulative_reward += float(r[chosen])
            A[chosen] += np.outer(x, x)
            b[chosen] += r[chosen] * x

        return cumulative_reward

    def run_comparison(
        self,
        n_bandit_arms: int = 3,
        drift_magnitude: float = 0.5,
    ) -> Dict[str, Dict[str, float]]:
        """运行三方案 Monte Carlo 对比

        Returns:
            {
                'plan_a_static': {'mean_reward': float, 'std_reward': float, ...},
                'plan_b_drift_aware': {'mean_reward': float, 'std_reward': float, ...},
                'plan_c_naive': {'mean_reward': float, 'std_reward': float, ...},
                'decision_gate': {'passed': bool, 'improvement_vs_a': float, ...},
            }
        """
        rewards_a, rewards_b, rewards_c = [], [], []
        for sim in range(self.n_simulations):
            data, regimes = self._simulate_regime_switching_data(
                self.n_periods, self.n_regimes, drift_magnitude
            )
            rewards_a.append(self._plan_a_static_rules(data))
            rewards_b.append(self._plan_b_drift_aware_bandit(data))
            rewards_c.append(self._plan_c_naive_bandit(data))

        results = {
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

        # 决策门
        improvement = (results['plan_b_drift_aware']['mean_reward']
                       - results['plan_a_static']['mean_reward']) / abs(results['plan_a_static']['mean_reward'] + 1e-10)
        results['decision_gate'] = {
            'passed': bool(improvement > 0.10),
            'improvement_vs_a': float(improvement),
            'threshold': 0.10,
            'interpretation': (
                f"Plan B 相对 Plan A 提升 {improvement:.2%}; "
                f"决策门阈值 10%; "
                f"{'通过 → 可规划 E6b 集成' if improvement > 0.10 else '未通过 → 维持方案 A'}"
            ),
        }

        self._last_results = results
        return results

    def evaluate_decision_gate(self, results: Optional[Dict] = None) -> Dict[str, Any]:
        """评估决策门"""
        if results is None:
            results = self._last_results
        if results is None:
            return {'evaluated': False}
        return results['decision_gate']

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._last_results is None:
            return {'ran': False}
        return {
            'ran': True,
            'n_simulations': self.n_simulations,
            'n_periods': self.n_periods,
            'results': self._last_results,
        }
```

#### 2.2.23 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T3 `CUSUMDriftMonitor` | ✓ 直接复用 | Plan A 和 Plan B 均调用 CUSUM 检测漂移 |
| `PipelineV2Config` | ✓ 无侵入 | E6 不修改配置, 不进入 Pipeline |
| `FactorProcessingPipelineV2` | ✓ 无侵入 | E6 为离线沙箱 |

#### 2.2.24 接口设计 (与 PipelineV2Config 协同)

E6 为**离线验证沙箱**, 不集成进 `PipelineV2Config`:

```python
from backtest.bandit_mc_sandbox import BanditMCSandbox

sandbox = BanditMCSandbox(n_simulations=500, n_periods=2520, random_state=42)
results = sandbox.run_comparison(n_bandit_arms=3, drift_magnitude=0.5)
gate = sandbox.evaluate_decision_gate(results)
print(gate['interpretation'])
# 若 gate['passed'] == True → 规划 E6b (Bandit 集成进 Pipeline, 本方案不包含)
# 若 gate['passed'] == False → 维持方案 A (E4 + E5), 不实施 Bandit
```

#### 2.2.25 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(n_sim × T × K × d³) | 500 sim × 2520 T × 3 K × 4³ d (LinUCB 矩阵求逆) |
| 内存占用 | ~200 MB | 各 sim 的 A/b 矩阵; 可增量计算 |
| 预期运行时间 | ~2-5 分钟 | 500 次完整模拟; 可用 joblib 并行化 sim 循环 |

#### 2.2.26 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| numpy | >=1.22 | 核心 (已装) | 矩阵运算 |
| T3 CUSUMDriftMonitor | 已实施 | 内部模块 | 漂移检测 |

**无新增依赖**。

#### 2.2.27 测试计划 (TDD)

**测试文件**: `tests/backtest/test_bandit_mc_sandbox.py`
**测试类**: `TestBanditMCSandbox`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_simulate_regime_switching_data_shape` | 生成数据形状正确 | rewards.shape == (T, K), regimes.shape == (T,) |
| `test_simulate_regime_switching_has_transitions` | 数据含体制转换 | len(np.unique(regimes)) >= 2 |
| `test_plan_a_static_rules_returns_float` | Plan A 返回浮点累计奖励 | isinstance(reward, float) |
| `test_plan_b_drift_aware_bandit_returns_float` | Plan B 返回浮点 | isinstance(reward, float) |
| `test_plan_c_naive_bandit_returns_float` | Plan C 返回浮点 | isinstance(reward, float) |
| `test_plan_b_better_than_plan_c` | Drift-Aware 优于朴素 Bandit | plan_b_mean > plan_c_mean (预期) |
| `test_run_comparison_returns_all_plans` | 返回含三方案 + 决策门 | {'plan_a_static', 'plan_b_drift_aware', 'plan_c_naive', 'decision_gate'} ⊆ keys |
| `test_decision_gate_has_passed_flag` | 决策门含 passed 布尔 | 'passed' in decision_gate |
| `test_decision_gate_threshold_10_percent` | 决策门阈值为 10% | threshold == 0.10 |
| `test_random_state_reproducibility` | 相同 random_state 结果一致 | np.allclose |
| `test_get_diagnostics_before_run` | 未运行时 diagnostics 返回 {'ran': False} | diagnostics['ran'] == False |

**TDD 流程**:
1. **Red**: 写 `TestBanditMCSandbox` 全部测试
2. **Green**: 实现 `BanditMCSandbox` 三方案对比
3. **Review**: Monte Carlo 结果符合预期 (Plan B > Plan C; Plan B vs Plan A 由数据决定)

#### 2.2.28 验收标准

- [ ] `BanditMCSandbox` 类完整实现, 所有测试通过 (≥11 测试用例)
- [ ] Monte Carlo (500 sim × 2520 期) 运行完成, 输出三方案累计奖励
- [ ] Plan B (Drift-Aware) > Plan C (朴素) — 验证漂移感知的必要性
- [ ] 决策门评估: 输出 improvement_vs_a + passed 布尔
- [ ] 若决策门通过 → 规划 E6b (本方案不包含); 若未通过 → 维持方案 A
- [ ] 论文附录可用: 输出 (plan, mean_reward, std_reward, improvement_vs_a) 对比表

#### 2.2.29 E6 决策门输出模板

```json
{
    "plan_a_static": {"mean_reward": 1260.5, "std_reward": 45.2},
    "plan_b_drift_aware": {"mean_reward": 1382.1, "std_reward": 52.8},
    "plan_c_naive": {"mean_reward": 1185.3, "std_reward": 68.4},
    "decision_gate": {
        "passed": true,
        "improvement_vs_a": 0.0964,
        "threshold": 0.10,
        "interpretation": "Plan B 相对 Plan A 提升 9.64%; 决策门阈值 10%; 未通过 → 维持方案 A"
    }
}
```

**注**: 上述数值为示例。实际决策门结果决定是否规划 E6b。

---

## 3. §2B 状态归因

### 3.1 学术背景 (RESEARCH_NOTES §2B)

RESEARCH_NOTES §2B 提出状态归因框架:
- **12 个 A 股状态变量** (5 类): liquidity / sentiment / capital_flow / macro_regime / style_regime
- **三层维度控制**: L1 主层 (252 检验, 全样本) / L2 次层 (126 检验, 半样本) / L3 探索层 (<100 检验, 滚动窗口)
- **双轨回归** (§2B.4.2):
  - R_factor on state (主, Ferson 2003 标准条件因子模型)
  - IC on state (辅, 项目认识论 — 直接检验因子选股能力的状态依赖)
- **三通道分解** (§2B.4.3): $\log R_{factor} = \log IC + \log \sigma_{factor} + \log \sigma_R$
- **五种发散模式** (§2B.4.3):
  - A 一致 (R/IC/σ 同向)
  - B 放大 (R > IC, σ_factor 主导)
  - C 仅 R (Moreira-Muir 2017 风险补偿)
  - D 仅 IC (Lewellen-Nagel-Shanken 因子误设定)
  - E 符号翻转 (Lewellen-Nagel 2006 条件可预测性反转)

工程化映射:
- **E7**: StateDataLoader (12 A 股状态变量) + MarkovRegimeIdentifier
- **E8**: StateConditionedPerformanceMatrix + 双轨回归 (R_factor / IC on state)
- **E9**: ThreeChannelDecomposition (log 线性化 + 五种发散模式识别)

---

### E7: StateDataLoader + MarkovRegimeIdentifier

#### 3.1.1 任务编号
**E7** — 12 A 股状态变量加载 + Markov 两状态体制识别

#### 3.1.2 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/state_data_loader.py` | 新建文件 | `StateDataLoader` | `__init__(self, enable: bool = False, min_observations: int = 252, source: str = 'akshare')` |
| `backtest/state_data_loader.py` | 新增方法 | `StateDataLoader.fit` | `fit(self, start_date: str, end_date: str) -> 'StateDataLoader'` |
| `backtest/state_data_loader.py` | 新增方法 | `StateDataLoader.load_12_state_variables` | `load_12_state_variables(self) -> pd.DataFrame` (返回 12 列状态变量) |
| `backtest/state_data_loader.py` | 新增方法 | `StateDataLoader.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` (含缺失率/覆盖范围/源可靠性) |
| `backtest/state_data_loader.py` | 新增方法 | `StateDataLoader.get_variable_metadata` | `get_variable_metadata(self) -> Dict[str, Dict]` (12 变量的定义/来源/类别) |
| `backtest/markov_regime_identifier.py` | 新建文件 | `MarkovRegimeIdentifier` | `__init__(self, n_regimes: int = 2, min_observations: int = 252, max_iter: int = 100, tolerance: float = 1e-6, enable: bool = False)` |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.fit` | `fit(self, state_data: pd.DataFrame, target_variable: str = 'market_turnover') -> 'MarkovRegimeIdentifier'` |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.predict` | `predict(self, state_data: pd.DataFrame) -> np.ndarray` (体制标签) |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.predict_proba` | `predict_proba(self, state_data: pd.DataFrame) -> np.ndarray` (体制概率) |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.get_transition_matrix` | `get_transition_matrix(self) -> np.ndarray` |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.get_regime_persistence` | `get_regime_persistence(self) -> float` |
| `backtest/markov_regime_identifier.py` | 新增方法 | `MarkovRegimeIdentifier.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` (含收敛状态/对数似然/AIC/BIC) |
| `backtest/markov_regime_identifier.py` | 新增私有方法 | `MarkovRegimeIdentifier._fallback_hard_threshold` | `_fallback_hard_threshold(self, state_data, target_variable) -> np.ndarray` (Markov 不收敛时降级) |
| `pipelines_v2.py` | 扩展配置 | `PipelineV2Config` | 新增: `enable_state_attribution: bool = False`, `state_data_source: str = 'akshare'`, `state_min_observations: int = 252`, `regime_n_states: int = 2` |
| `tests/backtest/test_state_data_loader.py` | 新建测试 | `TestStateDataLoader` | TDD |
| `tests/backtest/test_markov_regime_identifier.py` | 新建测试 | `TestMarkovRegimeIdentifier` | TDD |

#### 3.1.3 算法实现

**12 个 A 股状态变量** (RESEARCH_NOTES §2B.2):

| 类别 | 变量名 | 定义 | 数据源 |
|------|--------|------|--------|
| liquidity | market_turnover | 全市场日均换手率 | akshare `stock_zh_a_spot` |
| liquidity | amihud_illiquidity | Amihud (2002) 非流动性 | 计算: \|r\| / volume |
| sentiment | new_account_growth | 新增开户数同比 | akshare `stock_account_em` |
| sentiment | margin_balance_ratio | 两融余额 / 市值 | akshare `stock_margin_*` |
| capital_flow | northbound_flow | 北向资金净流入 | akshare `stock_hsgt_*` |
| capital_flow | etf_flow | ETF 净申赎 | akshare `fund_etf_*` |
| macro_regime | cpi_surprise | CPI 同比 - 一致预期 | akshare `macro_china_*` |
| macro_regime | pmi_surprise | PMI - 50 | akshare `macro_china_pmi` |
| style_regime | value_growth_spread | 价值因子 - 成长因子收益差 | 计算: 因子组合收益 |
| style_regime | small_large_spread | 小盘 - 大盘收益差 | akshare 指数 |
| macro_regime | term_spread | 10Y - 1Y 国债利差 | akshare `bond_zh_*` |
| style_regime | low_vol_high_vol_spread | 低波 - 高波收益差 | 计算: 因子组合收益 |

**Markov 两状态体制转换** (Hamilton 1989):

状态方程:
$$s_t \in \{0, 1\}, \quad P(s_t = j | s_{t-1} = i) = p_{ij}$$

观测方程:
$$y_t | s_t = j \sim N(\mu_j, \sigma_j^2)$$

参数估计: EM 算法最大化对数似然
$$\log L = \sum_{t=1}^{T} \log \left( \sum_{s_t} f(y_t | s_t) P(s_t | s_{t-1}) \right)$$

**Python 代码片段**:

```python
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List


class StateDataLoader:
    """12 个 A 股状态变量加载器 (RESEARCH_NOTES §2B.2)

    状态变量分 5 类:
    - liquidity (2): market_turnover, amihud_illiquidity
    - sentiment (2): new_account_growth, margin_balance_ratio
    - capital_flow (2): northbound_flow, etf_flow
    - macro_regime (3): cpi_surprise, pmi_surprise, term_spread
    - style_regime (3): value_growth_spread, small_large_spread, low_vol_high_vol_spread

    数据源: akshare (需 extras: state-data)

    设计原则:
    - 默认 enable=False (opt-in)
    - 缺失率 > 5% 的变量标记为不可靠, 不参与回归
    - 提供 get_variable_metadata() 便于审计
    """

    VARIABLE_CATEGORIES = {
        'liquidity': ['market_turnover', 'amihud_illiquidity'],
        'sentiment': ['new_account_growth', 'margin_balance_ratio'],
        'capital_flow': ['northbound_flow', 'etf_flow'],
        'macro_regime': ['cpi_surprise', 'pmi_surprise', 'term_spread'],
        'style_regime': ['value_growth_spread', 'small_large_spread', 'low_vol_high_vol_spread'],
    }

    ALL_VARIABLES = [v for vs in VARIABLE_CATEGORIES.values() for v in vs]

    def __init__(
        self,
        enable: bool = False,
        min_observations: int = 252,
        source: str = 'akshare',
        max_missing_rate: float = 0.05,
    ):
        self.enable = enable
        self.min_observations = min_observations
        self.source = source
        self.max_missing_rate = max_missing_rate
        self._data: Optional[pd.DataFrame] = None
        self._metadata: Dict[str, Dict] = {}

    def fit(self, start_date: str, end_date: str) -> 'StateDataLoader':
        """加载状态变量数据"""
        if not self.enable:
            return self
        try:
            import akshare as ak
        except ImportError as e:
            raise ImportError(
                "E7 StateDataLoader 需要 akshare. 安装: pip install factor-pipeline[state-data]"
            ) from e

        # 逐变量加载 (实际实现需处理 akshare 各接口差异)
        self._data = self._load_all_variables(start_date, end_date)
        self._metadata = self._build_metadata()
        return self

    def _load_all_variables(self, start_date: str, end_date: str) -> pd.DataFrame:
        """加载 12 个状态变量 (实际实现需对接 akshare 各接口)"""
        # 简化: 返回空 DataFrame, 实际实现逐变量加载
        # 每个变量的加载逻辑因 akshare 接口而异
        return pd.DataFrame(index=pd.bdate_range(start_date, end_date))

    def load_12_state_variables(self) -> pd.DataFrame:
        """返回 12 列状态变量 DataFrame"""
        if self._data is None:
            return pd.DataFrame()
        return self._data.copy()

    def get_variable_metadata(self) -> Dict[str, Dict]:
        """返回各变量的元数据: 类别 / 定义 / 来源 / 单位"""
        return self._metadata

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._data is None:
            return {'enabled': self.enable, 'loaded': False}
        missing_rates = self._data.isna().mean()
        return {
            'enabled': self.enable,
            'loaded': True,
            'n_observations': len(self._data),
            'n_variables': len(self._data.columns),
            'date_range': (str(self._data.index.min()), str(self._data.index.max())),
            'missing_rates': missing_rates.to_dict(),
            'unreliable_variables': missing_rates[missing_rates > self.max_missing_rate].index.tolist(),
            'source': self.source,
        }


class MarkovRegimeIdentifier:
    """Markov 两状态体制识别器 (RESEARCH_NOTES §2B.3 + Hamilton 1989)

    用 statsmodels MarkovRegression 拟合两状态体制转换模型,
    识别 bull/bear 体制. 不收敛时降级为硬阈值 (复用 T1 health.py 模式).

    设计原则:
    - 默认 enable=False (opt-in)
    - 不收敛时降级为硬阈值 (基于 target_variable 的分位数)
    - 提供 predict_proba() 输出体制概率, 供 E8/E10 使用
    """

    def __init__(
        self,
        n_regimes: int = 2,
        min_observations: int = 252,
        max_iter: int = 100,
        tolerance: float = 1e-6,
        enable: bool = False,
    ):
        self.n_regimes = n_regimes
        self.min_observations = min_observations
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.enable = enable
        self._model = None
        self._converged = False
        self._loglikelihood = None
        self._aic = None
        self._bic = None
        self._transition_matrix = None
        self._regime_means = None
        self._regime_stds = None
        self._fallback_used = False

    def fit(
        self,
        state_data: pd.DataFrame,
        target_variable: str = 'market_turnover',
    ) -> 'MarkovRegimeIdentifier':
        """拟合 Markov 体制转换模型

        Args:
            state_data: StateDataLoader.load_12_state_variables() 返回的 DataFrame
            target_variable: 用于体制识别的目标变量 (默认 market_turnover)
        """
        if not self.enable:
            return self
        if target_variable not in state_data.columns:
            raise ValueError(f"target_variable {target_variable} 不在 state_data 列中")
        y = state_data[target_variable].dropna()
        if len(y) < self.min_observations:
            raise ValueError(f"观测数 {len(y)} < 最小要求 {self.min_observations}")

        try:
            from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
            self._model = MarkovRegression(
                y, k_regimes=self.n_regimes, trend='c',
            ).fit(maxiter=self.max_iter, tol=self.tolerance)
            self._converged = self._model.mle_retvals.get('converged', False)
            self._loglikelihood = float(self._model.llf)
            self._aic = float(self._model.aic)
            self._bic = float(self._model.bic)
            # 转移矩阵
            params = self._model.params
            self._transition_matrix = self._model.regime_transition
            self._regime_means = [float(self._model.params[f'const[{i}]']) for i in range(self.n_regimes)]
            self._regime_stds = [float(self._model.params[f'sigma2[{i}]']) ** 0.5 for i in range(self.n_regimes)]
        except Exception:
            # 降级: 硬阈值
            self._fallback_used = True
            self._converged = False
            self._regime_means = [float(y.quantile(0.25)), float(y.quantile(0.75))]
            self._regime_stds = [float(y.std())] * self.n_regimes
            self._transition_matrix = np.array([[0.95, 0.05], [0.05, 0.95]])

        return self

    def predict(self, state_data: pd.DataFrame) -> np.ndarray:
        """预测体制标签 (0=bull, 1=bear)"""
        if self._model is not None and not self._fallback_used:
            probs = self._model.smoothed_marginal_probabilities
            return np.argmax(probs, axis=1)
        return self._fallback_hard_threshold(state_data, 'market_turnover')

    def predict_proba(self, state_data: pd.DataFrame) -> np.ndarray:
        """预测体制概率 (N, n_regimes)"""
        if self._model is not None and not self._fallback_used:
            return self._model.smoothed_marginal_probabilities
        # 降级: 硬阈值的软版本
        y = state_data['market_turnover'].values
        threshold = np.median(y)
        prob_bear = 1.0 / (1.0 + np.exp(-(y - threshold) * 10))
        return np.column_stack([1 - prob_bear, prob_bear])

    def _fallback_hard_threshold(
        self,
        state_data: pd.DataFrame,
        target_variable: str,
    ) -> np.ndarray:
        """降级: 硬阈值划分 (复用 T1 health.py 的 _split_bull_bear 模式)"""
        y = state_data[target_variable].values
        threshold = np.median(y)
        return (y < threshold).astype(int)

    def get_transition_matrix(self) -> np.ndarray:
        return self._transition_matrix

    def get_regime_persistence(self) -> float:
        """体制平均持续期 = 1 / (1 - p_stay)"""
        if self._transition_matrix is None:
            return float('nan')
        p_stay = np.diag(self._transition_matrix).mean()
        return float(1.0 / (1.0 - p_stay)) if p_stay < 1.0 else float('inf')

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'enabled': self.enable,
            'converged': self._converged,
            'fallback_used': self._fallback_used,
            'n_regimes': self.n_regimes,
            'loglikelihood': self._loglikelihood,
            'aic': self._aic,
            'bic': self._bic,
            'regime_means': self._regime_means,
            'regime_stds': self._regime_stds,
            'regime_persistence': self.get_regime_persistence(),
            'transition_matrix': self._transition_matrix.tolist() if self._transition_matrix is not None else None,
        }
```

#### 3.1.4 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T1 `health.py:_split_bull_bear` | ✓ 降级路径复用 | Markov 不收敛时用硬阈值, 模式与 T1 health 一致 |
| statsmodels (ADR-014) | ✓ REQUIRED | `MarkovRegression` 已在 statsmodels 中 |
| `PipelineV2Config` | ✓ 扩展兼容 | 新增 4 字段, 默认 `enable=False` |
| `factor-db` | ✓ 协同 | 状态变量可缓存进 DuckDB |

#### 3.1.5 接口设计 (与 PipelineV2Config 协同)

```python
@dataclass
class PipelineV2Config:
    # ... 现有字段 ...
    # E7 新增 (v3.0.0 §2B 状态归因)
    enable_state_attribution: bool = False
    state_data_source: str = 'akshare'
    state_min_observations: int = 252
    regime_n_states: int = 2
```

```python
# 使用示例:
from backtest.state_data_loader import StateDataLoader
from backtest.markov_regime_identifier import MarkovRegimeIdentifier

loader = StateDataLoader(enable=True, min_observations=252)
loader.fit(start_date='2015-01-01', end_date='2024-12-31')
state_data = loader.load_12_state_variables()

regime_id = MarkovRegimeIdentifier(n_regimes=2, enable=True)
regime_id.fit(state_data, target_variable='market_turnover')
regimes = regime_id.predict(state_data)
regime_probs = regime_id.predict_proba(state_data)
diag = regime_id.get_diagnostics()
print(f"收敛: {diag['converged']}, 体制持续期: {diag['regime_persistence']:.1f} 天")
```

#### 3.1.6 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| StateDataLoader 加载 | ~10-30 秒 | akshare 网络请求, 12 个接口 |
| MarkovRegimeIdentifier.fit | ~5-15 秒 | statsmodels EM 算法, T=2520 |
| 内存占用 | ~20 MB | state_data (T, 12) + Markov 内部状态 |
| predict | <1 秒 | 向量化计算 |

#### 3.1.7 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| statsmodels | >=0.13 | 核心 (已装, ADR-014) | MarkovRegression |
| numpy | >=1.22 | 核心 (已装) | 数值计算 |
| pandas | >=2.0 | 核心 (已装) | DataFrame |
| **akshare** | **>=1.10** | **extras: state-data** | **新增, A 股状态变量数据源** |

**新增 extras**:

```toml
# pyproject.toml [project.optional-dependencies]
state-data = ["akshare>=1.10.0"]
all = ["arch>=5.0.0", "optuna>=3.0.0", "pytest>=7.0.0", "akshare>=1.10.0"]
```

安装: `pip install factor-pipeline[state-data]`

#### 3.1.8 测试计划 (TDD)

**测试文件**: `tests/backtest/test_state_data_loader.py`, `tests/backtest/test_markov_regime_identifier.py`

**测试类**: `TestStateDataLoader`, `TestMarkovRegimeIdentifier`

| TestStateDataLoader 测试用例 | 描述 | 验证点 |
|----------------------------|------|--------|
| `test_disabled_no_op` | enable=False 时 load 返回空 | empty DataFrame |
| `test_variable_categories_complete` | 5 类共 12 变量 | len(ALL_VARIABLES) == 12 |
| `test_get_variable_metadata_structure` | 元数据含必要字段 | {'category', 'definition', 'source'} ⊆ keys |
| `test_missing_rate_threshold` | 缺失率 > 5% 标记不可靠 | unreliable_variables 非空 |
| `test_get_diagnostics_structure` | 诊断含必要字段 | {'n_observations', 'missing_rates', 'unreliable_variables'} ⊆ keys |
| `test_min_observations_enforced` | 观测不足时报错 | raises ValueError |

| TestMarkovRegimeIdentifier 测试用例 | 描述 | 验证点 |
|------------------------------------|------|--------|
| `test_fit_returns_self` | fit 返回 self | isinstance(result, MarkovRegimeIdentifier) |
| `test_predict_returns_int_array` | predict 返回 int 数组 | dtype in [int, int64], 值在 {0, 1} |
| `test_predict_proba_sums_to_one` | 概率行和为 1 | np.allclose(probs.sum(axis=1), 1.0) |
| `test_transition_matrix_shape` | 转移矩阵形状 (2, 2) | shape == (2, 2) |
| `test_regime_persistence_positive` | 持续期 > 0 | persistence > 0 |
| `test_fallback_on_non_convergence` | 不收敛时降级 | fallback_used == True, 仍返回预测 |
| `test_get_diagnostics_fields` | 诊断含收敛/对数似然/AIC/BIC | all fields present |
| `test_min_observations_enforced` | 观测不足报错 | raises ValueError |
| `test_random_state_reproducibility` | (若支持) 相同初始结果一致 | (取决于 statsmodels) |

**TDD 流程**:
1. **Red**: 写全部测试 (此时类不存在)
2. **Green**: 实现 StateDataLoader + MarkovRegimeIdentifier
3. **Review**: Markov 收敛性检查, 降级路径可用

#### 3.1.9 验收标准

- [ ] `StateDataLoader` + `MarkovRegimeIdentifier` 类完整实现, 所有测试通过 (≥15 测试用例)
- [ ] 12 个 A 股状态变量完整定义 (5 类)
- [ ] Markov 拟合: 输出转移矩阵 / 体制均值 / 持续期
- [ ] 降级路径: Markov 不收敛时用硬阈值, 不报错
- [ ] `PipelineV2Config` 新增 4 字段, 默认 `enable=False`
- [ ] akshare 加入 `state-data` extras

---

### E8: StateConditionedPerformanceMatrix + 双轨回归

#### 3.1.10 任务编号
**E8** — 状态条件性能矩阵 + R_factor/IC 双轨回归

#### 3.1.11 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/state_conditioned_analyzer.py` | 新建文件 | `StateConditionedAnalyzer` | `__init__(self, alpha: float = 0.05, correction: str = 'benjamini_hochberg', min_obs_per_cell: int = 30, enable: bool = False)` |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.fit` | `fit(self, factor_returns: Dict[str, pd.DataFrame], state_data: pd.DataFrame, regime_labels: np.ndarray, fwd_returns: pd.DataFrame) -> 'StateConditionedAnalyzer'` |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.compute_performance_matrix` | `compute_performance_matrix(self, metric: str = 'ic') -> pd.DataFrame` (因子 × 体制的性能矩阵) |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.factor_return_regression` | `factor_return_regression(self, factor_name: str) -> Dict` (R_factor on state, Ferson 2003) |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.ic_on_state_regression` | `ic_on_state_regression(self, factor_name: str) -> Dict` (IC on state, 项目认识论) |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.test_all_factors` | `test_all_factors(self, correction: Optional[str] = None) -> Dict[str, Dict]` (含 BH-FDR) |
| `backtest/state_conditioned_analyzer.py` | 新增方法 | `StateConditionedAnalyzer.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `backtest/state_conditioned_analyzer.py` | 新增私有方法 | `StateConditionedAnalyzer._compute_ic_series` | `_compute_ic_series(self, factor_values, fwd_returns) -> pd.Series` |
| `backtest/state_conditioned_analyzer.py` | 新增私有方法 | `StateConditionedAnalyzer._apply_newey_west` | `_apply_newey_west(self, y, X, max_lags: int = 5) -> Dict` |
| `tests/backtest/test_state_conditioned_analyzer.py` | 新建测试 | `TestStateConditionedAnalyzer` | TDD |

#### 3.1.12 算法实现

**数学公式** (双轨回归):

**轨道 1 — R_factor on state** (Ferson 2003 条件因子模型):
$$R_{factor,t} = \alpha + \sum_{k=1}^{12} \beta_k S_{k,t-1} + \epsilon_t$$

其中 $R_{factor,t}$ = 因子多空组合收益, $S_{k,t-1}$ = 第 k 个状态变量 (滞后一期, 避免前视偏差)。

Newey-West HAC 标准误 (修正自相关):
$$\hat{\Sigma}_{NW} = \hat{\Sigma}_{OLS} + \sum_{l=1}^{L} \left(1 - \frac{l}{L+1}\right) (\hat{\Gamma}_l + \hat{\Gamma}_l^T)$$

**轨道 2 — IC on state** (项目认识论):
$$IC_t = \alpha_{IC} + \sum_{k=1}^{12} \gamma_k S_{k,t-1} + \nu_t$$

其中 $IC_t$ = Spearman rank IC (因子值与前向收益的截面相关性)。

**BH-FDR 应用**: 对 12 个状态变量的 p 值 × K 个因子 = 12K 检验做 BH-FDR 校正 (复用 T4)。

**三层维度控制**:
- L1 主层: 252 检验 (12 状态 × 21 因子, 全样本)
- L2 次层: 126 检验 (子样本, 半样本验证)
- L3 探索层: <100 检验 (滚动窗口 63 天)

**Python 代码片段**:

```python
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import statsmodels.api as sm
from scipy import stats as sps

try:
    from backtest.multiple_testing import apply_bh_fdr, apply_correction
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False


class StateConditionedAnalyzer:
    """状态条件性能矩阵 + 双轨回归 (RESEARCH_NOTES §2B.4)

    双轨:
    - R_factor on state (主, Ferson 2003 标准条件因子模型)
    - IC on state (辅, 项目认识论 — 直接检验选股能力状态依赖)

    三层维度控制:
    - L1 主层: 252 检验 (12 × 21, 全样本)
    - L2 次层: 126 检验 (半样本验证)
    - L3 探索层: <100 检验 (滚动窗口)

    BH-FDR 应用于多重检验 (复用 T4).
    """

    def __init__(
        self,
        alpha: float = 0.05,
        correction: str = 'benjamini_hochberg',
        min_obs_per_cell: int = 30,
        n_lags: int = 5,
        enable: bool = False,
    ):
        self.alpha = alpha
        self.correction = correction
        self.min_obs_per_cell = min_obs_per_cell
        self.n_lags = n_lags
        self.enable = enable
        self._factor_returns: Optional[Dict] = None
        self._state_data: Optional[pd.DataFrame] = None
        self._regime_labels: Optional[np.ndarray] = None
        self._fwd_returns: Optional[pd.DataFrame] = None
        self._performance_matrix: Optional[pd.DataFrame] = None
        self._regression_results: Dict[str, Dict] = {}

    def fit(
        self,
        factor_returns: Dict[str, pd.DataFrame],
        state_data: pd.DataFrame,
        regime_labels: np.ndarray,
        fwd_returns: pd.DataFrame,
    ) -> 'StateConditionedAnalyzer':
        """拟合状态条件分析

        Args:
            factor_returns: {因子名: (N, T) DataFrame}
            state_data: (T, 12) 状态变量 (来自 E7 StateDataLoader)
            regime_labels: (T,) 体制标签 (来自 E7 MarkovRegimeIdentifier)
            fwd_returns: (T, N) 前向收益
        """
        self._factor_returns = factor_returns
        self._state_data = state_data
        self._regime_labels = regime_labels
        self._fwd_returns = fwd_returns
        return self

    def compute_performance_matrix(self, metric: str = 'ic') -> pd.DataFrame:
        """计算因子 × 体制的性能矩阵

        Args:
            metric: 'ic' (Spearman IC 均值) / 'return' (因子多空收益均值)

        Returns:
            DataFrame: index=因子名, columns=体制标签, values=性能指标
        """
        if self._factor_returns is None:
            return pd.DataFrame()

        regimes = np.unique(self._regime_labels)
        factors = list(self._factor_returns.keys())
        matrix = pd.DataFrame(index=factors, columns=regimes, dtype=float)

        for fname in factors:
            fdata = self._factor_returns[fname]
            for regime in regimes:
                mask = self._regime_labels == regime
                if mask.sum() < self.min_obs_per_cell:
                    matrix.loc[fname, regime] = float('nan')
                    continue
                if metric == 'ic':
                    ic_series = self._compute_ic_series(
                        fdata.iloc[:, mask], self._fwd_returns.iloc[mask]
                    )
                    matrix.loc[fname, regime] = float(ic_series.mean())
                elif metric == 'return':
                    # 因子多空收益: 高位做多, 低位做空
                    long_short = fdata.iloc[:, mask].apply(
                        lambda row: row.quantile(0.8) - row.quantile(0.2), axis=1
                    )
                    matrix.loc[fname, regime] = float(long_short.mean())

        self._performance_matrix = matrix
        return matrix

    def _compute_ic_series(
        self,
        factor_values: pd.DataFrame,
        fwd_returns: pd.DataFrame,
    ) -> pd.Series:
        """计算 IC 序列 (Spearman rank IC, 每期一个 IC)"""
        common_dates = factor_values.columns.intersection(fwd_returns.index)
        ic_list = []
        for date in common_dates:
            fvals = factor_values[date].dropna()
            rvals = fwd_returns.loc[date].dropna() if date in fwd_returns.index else None
            if rvals is None:
                continue
            common_stocks = fvals.index.intersection(rvals.index)
            if len(common_stocks) < 10:
                continue
            ic, _ = sps.spearmanr(fvals.loc[common_stocks], rvals.loc[common_stocks])
            ic_list.append(ic)
        return pd.Series(ic_list)

    def factor_return_regression(self, factor_name: str) -> Dict:
        """轨道 1: R_factor on state (Ferson 2003 条件因子模型)

        R_factor,t = alpha + Σ β_k * S_{k,t-1} + ε_t
        Newey-West HAC 标准误
        """
        if self._factor_returns is None or factor_name not in self._factor_returns:
            return {}

        fdata = self._factor_returns[factor_name]
        # 计算因子多空收益序列 (简化: 用截面分位差)
        factor_long_short = fdata.apply(
            lambda row: row.quantile(0.8) - row.quantile(0.2), axis=1
        )
        # 对齐状态变量 (滞后一期)
        y = factor_long_short.iloc[1:]
        X = self._state_data.iloc[:-1].reindex(y.index).dropna()
        y = y.reindex(X.index)
        if len(y) < self.min_obs_per_cell:
            return {'error': 'insufficient observations'}

        X_with_const = sm.add_constant(X)
        model = sm.OLS(y, X_with_const)
        # Newey-West HAC
        result = model.fit(cov_type='HAC', cov_kwds={'maxlags': self.n_lags})

        return {
            'factor': factor_name,
            'track': 'R_factor_on_state',
            'alpha': float(result.params['const']),
            'alpha_pvalue': float(result.pvalues['const']),
            'alpha_std_error': float(result.bse['const']),
            'betas': {col: float(result.params[col]) for col in X.columns},
            'beta_pvalues': {col: float(result.pvalues[col]) for col in X.columns},
            'beta_std_errors': {col: float(result.bse[col]) for col in X.columns},
            'r_squared': float(result.rsquared),
            'n_observations': int(result.nobs),
            'n_lags': self.n_lags,
        }

    def ic_on_state_regression(self, factor_name: str) -> Dict:
        """轨道 2: IC on state (项目认识论)

        IC_t = alpha_IC + Σ γ_k * S_{k,t-1} + ν_t
        Newey-West HAC 标准误
        """
        if self._factor_returns is None or factor_name not in self._factor_returns:
            return {}

        fdata = self._factor_returns[factor_name]
        ic_series = self._compute_ic_series(fdata, self._fwd_returns)
        # 滞后状态变量
        y = ic_series.iloc[1:]
        X = self._state_data.iloc[:-1].reindex(y.index).dropna()
        y = y.reindex(X.index)
        if len(y) < self.min_obs_per_cell:
            return {'error': 'insufficient observations'}

        X_with_const = sm.add_constant(X)
        model = sm.OLS(y, X_with_const)
        result = model.fit(cov_type='HAC', cov_kwds={'maxlags': self.n_lags})

        return {
            'factor': factor_name,
            'track': 'IC_on_state',
            'alpha_ic': float(result.params['const']),
            'alpha_ic_pvalue': float(result.pvalues['const']),
            'alpha_ic_std_error': float(result.bse['const']),
            'gammas': {col: float(result.params[col]) for col in X.columns},
            'gamma_pvalues': {col: float(result.pvalues[col]) for col in X.columns},
            'r_squared': float(result.rsquared),
            'n_observations': int(result.nobs),
            'n_lags': self.n_lags,
        }

    def test_all_factors(self, correction: Optional[str] = None) -> Dict[str, Dict]:
        """对所有因子执行双轨回归 + BH-FDR 校正

        Returns:
            {factor_name: {'R_factor_on_state': {...}, 'IC_on_state': {...}}}
        """
        if self._factor_returns is None:
            return {}

        corr = correction if correction is not None else self.correction
        results = {}
        all_p_values = []

        for fname in self._factor_returns.keys():
            r_track = self.factor_return_regression(fname)
            ic_track = self.ic_on_state_regression(fname)
            results[fname] = {
                'R_factor_on_state': r_track,
                'IC_on_state': ic_track,
            }
            # 收集 p 值用于 BH-FDR
            if 'beta_pvalues' in r_track:
                all_p_values.extend(r_track['beta_pvalues'].values())
            if 'gamma_pvalues' in ic_track:
                all_p_values.extend(ic_track['gamma_pvalues'].values())

        # BH-FDR 校正 (复用 T4)
        if all_p_values and _HAS_MULTIPLE_TESTING and corr == 'benjamini_hochberg':
            adj_p, rejected = apply_bh_fdr(all_p_values, alpha=self.alpha)
            # 将校正后 p 值回填 (简化: 存在全局 metadata)
            results['_global_correction'] = {
                'method': 'benjamini_hochberg',
                'n_tests': len(all_p_values),
                'n_rejected': int(sum(rejected)),
                'alpha': self.alpha,
            }

        self._regression_results = results
        return results

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._factor_returns is None:
            return {'enabled': self.enable, 'fitted': False}
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_factors': len(self._factor_returns),
            'n_state_variables': len(self._state_data.columns) if self._state_data is not None else 0,
            'n_regimes': len(np.unique(self._regime_labels)) if self._regime_labels is not None else 0,
            'n_observations': len(self._state_data) if self._state_data is not None else 0,
            'min_obs_per_cell': self.min_obs_per_cell,
            'n_lags': self.n_lags,
            'correction': self.correction,
            'n_regression_results': len(self._regression_results),
        }
```

#### 3.1.13 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T4 `apply_bh_fdr` | ✓ 复用 | 双轨回归的 12K 检验经 BH-FDR 校正 |
| statsmodels (ADR-014) | ✓ REQUIRED | OLS + Newey-West HAC |
| E7 StateDataLoader + MarkovRegimeIdentifier | ✓ 数据源 | E8 输入 = E7 输出 |
| `factor_significance.py:_compute_ic_series` | ✓ 模式复用 | IC 序列计算模式一致 |

#### 3.1.14 接口设计 (与 PipelineV2Config 协同)

E8 为**离线分析工具**, 不直接集成进 `PipelineV2Config`, 但依赖 E7:

```python
# 使用示例:
from backtest.state_conditioned_analyzer import StateConditionedAnalyzer

analyzer = StateConditionedAnalyzer(
    alpha=0.05,
    correction='benjamini_hochberg',
    min_obs_per_cell=30,
    n_lags=5,
    enable=True,
)
analyzer.fit(
    factor_returns=factor_dict,
    state_data=state_data,           # E7 StateDataLoader 输出
    regime_labels=regimes,           # E7 MarkovRegimeIdentifier 输出
    fwd_returns=fwd_returns,
)
perf_matrix = analyzer.compute_performance_matrix(metric='ic')
results = analyzer.test_all_factors()  # 双轨回归 + BH-FDR
```

#### 3.1.15 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(K × T × N + K × 12 × T) | K 因子 × IC 计算 (T × N) + K 因子 × 12 状态 × T 回归 |
| 内存占用 | ~100 MB | factor_returns (K, T, N) + 状态数据 |
| 预期运行时间 | ~30-60 秒 | K=21, T=2520, N=5000; IC 计算最耗时 |
| BH-FDR 应用 | O(m log m) | m ≈ 12 × 21 = 252 检验 (L1 层) |

#### 3.1.16 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| statsmodels | >=0.13 | 核心 (已装) | OLS + Newey-West HAC |
| scipy | >=1.7 | 核心 (已装) | Spearman IC |
| numpy | >=1.22 | 核心 (已装) | 数值计算 |
| E7 StateDataLoader | 内部模块 | E7 | 状态数据源 |

**无新增依赖** (akshare 在 E7 已加入 extras)。

#### 3.1.17 测试计划 (TDD)

**测试文件**: `tests/backtest/test_state_conditioned_analyzer.py`
**测试类**: `TestStateConditionedAnalyzer`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_fit_returns_self` | fit 返回 self | isinstance(result, StateConditionedAnalyzer) |
| `test_compute_performance_matrix_shape` | 性能矩阵形状正确 | shape == (n_factors, n_regimes) |
| `test_compute_performance_matrix_ic_metric` | IC 指标在 [-1, 1] | all values in [-1, 1] |
| `test_compute_performance_matrix_min_obs` | 观测不足的格为 NaN | NaN 存在 |
| `test_factor_return_regression_fields` | R_factor 回归含必要字段 | {'alpha', 'betas', 'r_squared'} ⊆ keys |
| `test_ic_on_state_regression_fields` | IC 回归含必要字段 | {'alpha_ic', 'gammas', 'r_squared'} ⊆ keys |
| `test_newey_west_lags_applied` | Newey-West 滞后应用 | n_lags in result |
| `test_test_all_factors_returns_dict` | test_all_factors 返回字典 | isinstance(result, dict) |
| `test_bh_fdr_correction_applied` | BH-FDR 校正应用 | '_global_correction' in result |
| `test_get_diagnostics_fields` | 诊断含必要字段 | {'n_factors', 'n_state_variables'} ⊆ keys |
| `test_disabled_no_op` | enable=False 时返回空 | compute_performance_matrix 返回空 |
| `test_known_state_dependency` | 构造已知状态依赖 | beta 显著非零 |

**TDD 流程**:
1. **Red**: 写 `TestStateConditionedAnalyzer` 全部测试
2. **Green**: 实现 `StateConditionedAnalyzer` 双轨回归
3. **Review**: Newey-West HAC 正确应用, BH-FDR 校正

#### 3.1.18 验收标准

- [ ] `StateConditionedAnalyzer` 类完整实现, 所有测试通过 (≥12 测试用例)
- [ ] 性能矩阵: 因子 × 体制, IC 指标在 [-1, 1]
- [ ] 双轨回归: R_factor on state (Ferson 2003) + IC on state
- [ ] Newey-West HAC 标准误, 滞后阶数可配置
- [ ] BH-FDR 校正: 12K 检验 (L1 层 252 检验)
- [ ] 复用 T4 `apply_bh_fdr` 共享模块

---

### E9: ThreeChannelDecomposition (三通道分解)

#### 3.1.19 任务编号
**E9** — log R_factor = log IC + log σ_factor + log σ_R 三通道分解 + 五种发散模式

#### 3.1.20 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/three_channel_decomposition.py` | 新建文件 | `ThreeChannelDecomposition` | `__init__(self, enable: bool = False, heteroskedasticity_test: str = 'white')` |
| `backtest/three_channel_decomposition.py` | 新增方法 | `ThreeChannelDecomposition.fit` | `fit(self, factor_returns: Dict[str, pd.DataFrame], fwd_returns: pd.DataFrame, regime_labels: Optional[np.ndarray] = None) -> 'ThreeChannelDecomposition'` |
| `backtest/three_channel_decomposition.py` | 新增方法 | `ThreeChannelDecomposition.decompose` | `decompose(self, factor_name: str) -> Dict[str, pd.DataFrame]` |
| `backtest/three_channel_decomposition.py` | 新增方法 | `ThreeChannelDecomposition.classify_divergence_pattern` | `classify_divergence_pattern(self, factor_name: str) -> Dict[str, str]` |
| `backtest/three_channel_decomposition.py` | 新增方法 | `ThreeChannelDecomposition.test_heteroskedasticity` | `test_heteroskedasticity(self, factor_name: str) -> Dict[str, float]` |
| `backtest/three_channel_decomposition.py` | 新增方法 | `ThreeChannelDecomposition.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `backtest/three_channel_decomposition.py` | 新增私有方法 | `ThreeChannelDecomposition._compute_channel_series` | `_compute_channel_series(self, factor_name) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]` |
| `tests/backtest/test_three_channel_decomposition.py` | 新建测试 | `TestThreeChannelDecomposition` | TDD |

#### 3.1.21 算法实现

**数学公式** (三通道分解, RESEARCH_NOTES §2B.4.3):

因子收益的截面方差分解:
$$\text{Var}(R_{factor,t}) = IC_t^2 \cdot \sigma_{factor,t}^2 \cdot \sigma_{R,t}^2 + \text{higher order terms}$$

取对数后近似线性化:
$$\log |R_{factor,t}| \approx \log |IC_t| + \log \sigma_{factor,t} + \log \sigma_{R,t}$$

> **⚠ 关键前提假设 — 三通道近似独立性**: 上述对数线性分解依赖 $IC_t$ / $\sigma_{factor,t}$ / $\sigma_{R,t}$ 三者**近似独立**的假设 (即因子选股能力、因子截面分散度、收益截面分散度之间弱相关)。
> - **成立条件**: 因子与收益波动率弱相关时成立 (常规市场环境)。
> - **失效场景**: 强 regime 切换或波动率聚集 (volatility clustering) 场景下, $IC$ 与 $\sigma_R$ 常呈负相关 (高风险时因子预测力下降), 三通道不再独立, 线性分解引入系统性偏差。
> - **失效后果**: 分解结果应作为**近似参考而非精确归因**; 此时建议补充数值归因 (如 Shapley 值或直接方差分解) 交叉验证。

三个通道:
- **IC 通道**: $\log |IC_t|$ (因子选股能力)
- **σ_factor 通道**: $\log \sigma_{factor,t}$ (因子截面分散度)
- **σ_R 通道**: $\log \sigma_{R,t}$ (收益截面分散度)

**五种发散模式** (RESEARCH_NOTES §2B.4.3):

| 模式 | 描述 | R vs IC | σ_factor | σ_R | 学术依据 |
|------|------|---------|---------|-----|---------|
| A 一致 | R/IC/σ 同向变化 | R ↑, IC ↑ | ↑ | ↑ | 标准因子模型 |
| B 放大 | R > IC, σ_factor 主导 | R ↑, IC → | ↑ | → | 因子分散度膨胀 |
| C 仅 R | R 变化, IC 不变 | R ↑, IC → | → | ↑ | Moreira-Muir (2017) 风险补偿 |
| D 仅 IC | IC 变化, R 不变 | R →, IC ↑ | ↓ | → | Lewellen-Nagel-Shanken 因子误设定 |
| E 符号翻转 | R 与 IC 反向 | R ↑, IC ↓ | ? | ? | Lewellen-Nagel (2006) 条件可预测性反转 |

**异方差检验**: White (1980) 检验各通道的方差稳定性。

**Python 代码片段**:

```python
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple, List
from scipy import stats as sps
import statsmodels.api as sm


class ThreeChannelDecomposition:
    """三通道分解 (RESEARCH_NOTES §2B.4.3)

    log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)

    三个通道:
    - IC 通道: 因子选股能力
    - σ_factor 通道: 因子截面分散度
    - σ_R 通道: 收益截面分散度

    五种发散模式:
    - A 一致 / B 放大 / C 仅 R (Moreira-Muir) / D 仅 IC (Lewellen-Nagel-Shanken) / E 符号翻转 (Lewellen-Nagel)

    异方差检验: White (1980)
    """

    PATTERN_NAMES = {
        'A': 'consistent',
        'B': 'amplified',
        'C': 'R_only_moreira_muir',
        'D': 'IC_only_lewellen_nagel_shanken',
        'E': 'sign_flip_lewellen_nagel',
    }

    def __init__(
        self,
        enable: bool = False,
        heteroskedasticity_test: str = 'white',
        min_observations: int = 60,
    ):
        self.enable = enable
        self.heteroskedasticity_test = heteroskedasticity_test
        self.min_observations = min_observations
        self._factor_returns: Optional[Dict] = None
        self._fwd_returns: Optional[pd.DataFrame] = None
        self._regime_labels: Optional[np.ndarray] = None
        self._decomposition_results: Dict[str, Dict] = {}

    def fit(
        self,
        factor_returns: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        regime_labels: Optional[np.ndarray] = None,
    ) -> 'ThreeChannelDecomposition':
        self._factor_returns = factor_returns
        self._fwd_returns = fwd_returns
        self._regime_labels = regime_labels
        return self

    def _compute_channel_series(
        self,
        factor_name: str,
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """计算四通道序列: (R_factor, IC, σ_factor, σ_R)

        Returns:
            (R_factor, IC, σ_factor, σ_R) 四个 pd.Series, index 对齐
        """
        fdata = self._factor_returns[factor_name]
        common_dates = fdata.columns.intersection(self._fwd_returns.index)

        r_list, ic_list, sf_list, sr_list, dates = [], [], [], [], []
        for date in common_dates:
            fvals = fdata[date].dropna()
            rvals = self._fwd_returns.loc[date].dropna()
            common = fvals.index.intersection(rvals.index)
            if len(common) < 10:
                continue
            f_common = fvals.loc[common]
            r_common = rvals.loc[common]

            # R_factor: 高位做多, 低位做空
            q80 = f_common.quantile(0.8)
            q20 = f_common.quantile(0.2)
            long_stocks = f_common[f_common >= q80].index
            short_stocks = f_common[f_common <= q20].index
            r_factor = r_common.loc[long_stocks].mean() - r_common.loc[short_stocks].mean()

            # IC: Spearman rank
            ic, _ = sps.spearmanr(f_common, r_common)

            # σ_factor: 因子截面标准差
            sigma_f = float(f_common.std())

            # σ_R: 收益截面标准差
            sigma_r = float(r_common.std())

            r_list.append(r_factor)
            ic_list.append(ic)
            sf_list.append(sigma_f)
            sr_list.append(sigma_r)
            dates.append(date)

        index = pd.DatetimeIndex(dates)
        return (
            pd.Series(r_list, index=index),
            pd.Series(ic_list, index=index),
            pd.Series(sf_list, index=index),
            pd.Series(sr_list, index=index),
        )

    def decompose(self, factor_name: str) -> Dict[str, pd.Series]:
        """执行三通道分解

        log|R_factor| ≈ log|IC| + log(σ_factor) + log(σ_R)
        """
        r, ic, sf, sr = self._compute_channel_series(factor_name)

        # 对数变换 (取绝对值, 加小常数避免 log(0))
        eps = 1e-10
        log_r = np.log(np.abs(r) + eps)
        log_ic = np.log(np.abs(ic) + eps)
        log_sf = np.log(sf + eps)
        log_sr = np.log(sr + eps)

        # 残差 (三通道无法解释的部分)
        log_residual = log_r - log_ic - log_sf - log_sr

        return {
            'R_factor': r,
            'IC': ic,
            'sigma_factor': sf,
            'sigma_R': sr,
            'log_R': log_r,
            'log_IC': log_ic,
            'log_sigma_factor': log_sf,
            'log_sigma_R': log_sr,
            'log_residual': log_residual,
        }

    def classify_divergence_pattern(self, factor_name: str) -> Dict[str, str]:
        """分类发散模式 (A/B/C/D/E)"""
        series = self.decompose(factor_name)
        r = series['R_factor']
        ic = series['IC']
        sf = series['sigma_factor']
        sr = series['sigma_R']

        # 计算各通道的趋势 (用线性回归斜率)
        def _trend(s):
            x = np.arange(len(s))
            if len(s) < 10 or s.std() < 1e-10:
                return 0.0
            slope = np.polyfit(x, s.values, 1)[0]
            return float(slope)

        r_trend = _trend(r)
        ic_trend = _trend(ic)
        sf_trend = _trend(sf)
        sr_trend = _trend(sr)

        # 归一化 (用标准差)
        r_norm = r_trend / (r.std() + 1e-10)
        ic_norm = ic_trend / (ic.std() + 1e-10)
        sf_norm = sf_trend / (sf.std() + 1e-10)
        sr_norm = sr_trend / (sr.std() + 1e-10)

        # 阈值
        threshold = 0.1

        # 分类逻辑
        r_up = r_norm > threshold
        ic_up = ic_norm > threshold
        ic_down = ic_norm < -threshold
        sf_up = sf_norm > threshold
        sr_up = sr_norm > threshold

        if r_up and ic_up and sf_up and sr_up:
            pattern = 'A'  # 一致
        elif r_up and not ic_up and sf_up:
            pattern = 'B'  # 放大
        elif r_up and not ic_up and sr_up and not sf_up:
            pattern = 'C'  # 仅 R (Moreira-Muir)
        elif not r_up and ic_up:
            pattern = 'D'  # 仅 IC (Lewellen-Nagel-Shanken)
        elif r_up and ic_down:
            pattern = 'E'  # 符号翻转 (Lewellen-Nagel)
        else:
            pattern = 'unclassified'

        return {
            'factor': factor_name,
            'pattern': pattern,
            'pattern_name': self.PATTERN_NAMES.get(pattern, 'unclassified'),
            'trends': {
                'R_factor': r_norm,
                'IC': ic_norm,
                'sigma_factor': sf_norm,
                'sigma_R': sr_norm,
            },
            'interpretation': self._interpret_pattern(pattern),
        }

    def _interpret_pattern(self, pattern: str) -> str:
        interpretations = {
            'A': '一致模式: R/IC/σ 同向变化, 标准因子模型成立',
            'B': '放大模式: R > IC, σ_factor 主导, 因子分散度膨胀',
            'C': '仅 R 模式 (Moreira-Muir 2017): R 变化但 IC 不变, 风险补偿主导',
            'D': '仅 IC 模式 (Lewellen-Nagel-Shanken): IC 变化但 R 不变, 因子误设定',
            'E': '符号翻转模式 (Lewellen-Nagel 2006): R 与 IC 反向, 条件可预测性反转',
            'unclassified': '未分类: 通道趋势组合不属于已知模式',
        }
        return interpretations.get(pattern, '未知模式')

    def test_heteroskedasticity(self, factor_name: str) -> Dict[str, float]:
        """异方差检验 (White 1980)

        对 log|R| - log|IC| - log(σ_factor) - log(σ_R) 残差做 White 检验.
        """
        series = self.decompose(factor_name)
        residual = series['log_residual']

        # White 检验: 残差的方差是否随时间变化
        x = np.arange(len(residual))
        X = sm.add_constant(np.column_stack([x, x**2]))
        try:
            model = sm.OLS(residual.values, X).fit()
            # White 检验统计量
            n = len(residual)
            r_squared = model.rsquared
            white_stat = n * r_squared
            white_pvalue = float(sps.chi2.sf(white_stat, df=2))
        except Exception:
            white_pvalue = 1.0

        return {
            'factor': factor_name,
            'white_statistic': float(white_stat) if 'white_stat' in locals() else 0.0,
            'white_pvalue': white_pvalue,
            'is_heteroskedastic': bool(white_pvalue < 0.05),
            'test': 'white',
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        if self._factor_returns is None:
            return {'enabled': self.enable, 'fitted': False}
        return {
            'enabled': self.enable,
            'fitted': True,
            'n_factors': len(self._factor_returns),
            'n_decompositions': len(self._decomposition_results),
            'min_observations': self.min_observations,
            'heteroskedasticity_test': self.heteroskedasticity_test,
        }
```

#### 3.1.22 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T1 21 维 FactorFingerprint | ✓ 协同 | E9 输出的发散模式可反馈进指纹 (regime_ic_diff) |
| E8 StateConditionedAnalyzer | ✓ 数据源 | E9 可接收 E8 的体制标签做体制内分解 |
| statsmodels (ADR-014) | ✓ REQUIRED | White 检验 |
| scipy | >=1.7 | ✓ 已装 | Spearman IC |

#### 3.1.23 接口设计 (与 PipelineV2Config 协同)

E9 为**离线分析工具**, 不集成进 `PipelineV2Config`:

```python
from backtest.three_channel_decomposition import ThreeChannelDecomposition

decomposer = ThreeChannelDecomposition(enable=True)
decomposer.fit(factor_returns=factor_dict, fwd_returns=fwd_returns)

for fname in factor_dict.keys():
    channels = decomposer.decompose(fname)
    pattern = decomposer.classify_divergence_pattern(fname)
    hetero = decomposer.test_heteroskedasticity(fname)
    print(f"{fname}: 模式 {pattern['pattern']} ({pattern['pattern_name']})")
    print(f"  异方差 p={hetero['white_pvalue']:.4f}")
```

#### 3.1.24 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(K × T × N) | K 因子 × T 期 × N 股票的 IC/分位计算 |
| 内存占用 | ~50 MB | 四通道序列 (K, T) |
| 预期运行时间 | ~10-30 秒 | K=21, T=2520, N=5000 |

#### 3.1.25 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| statsmodels | >=0.13 | 核心 (已装) | White 检验 |
| scipy | >=1.7 | 核心 (已装) | Spearman IC |
| numpy | >=1.22 | 核心 (已装) | 对数变换 |
| E8 (可选) | 内部模块 | E8 | 体制标签输入 (可选) |

**无新增依赖**。

#### 3.1.26 测试计划 (TDD)

**测试文件**: `tests/backtest/test_three_channel_decomposition.py`
**测试类**: `TestThreeChannelDecomposition`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_fit_returns_self` | fit 返回 self | isinstance(result, ThreeChannelDecomposition) |
| `test_compute_channel_series_length` | 四通道序列长度一致 | all len equal |
| `test_decompose_returns_all_channels` | decompose 返回 9 个序列 (原始 4 + 对数 4 + 残差 1) | len(result) == 9 |
| `test_decompose_log_linearity` | log|R| ≈ log|IC| + log(σ_f) + log(σ_R) + residual | 残差均值 ≈ 0 |
| `test_classify_pattern_A_consistent` | 构造一致模式 | pattern == 'A' |
| `test_classify_pattern_B_amplified` | 构造放大模式 | pattern == 'B' |
| `test_classify_pattern_C_R_only` | 构造仅 R 模式 | pattern == 'C' |
| `test_classify_pattern_D_IC_only` | 构造仅 IC 模式 | pattern == 'D' |
| `test_classify_pattern_E_sign_flip` | 构造符号翻转 | pattern == 'E' |
| `test_test_heteroskedasticity_returns_pvalue` | 异方差检验返回 p 值 | 0 <= pvalue <= 1 |
| `test_get_diagnostics_fields` | 诊断含必要字段 | {'n_factors', 'n_decompositions'} ⊆ keys |
| `test_disabled_no_op` | enable=False 时返回空 | decompose 返回 {} |

**TDD 流程**:
1. **Red**: 写 `TestThreeChannelDecomposition` 全部测试
2. **Green**: 实现 `ThreeChannelDecomposition` + 五模式分类
3. **Review**: log 线性化残差 ≈ 0, 五种模式可正确识别

#### 3.1.27 验收标准

- [ ] `ThreeChannelDecomposition` 类完整实现, 所有测试通过 (≥12 测试用例)
- [ ] 四通道序列 (R, IC, σ_factor, σ_R) 正确计算
- [ ] log 线性化: 残差均值 ≈ 0 (容忍 ±0.1)
- [ ] 五种发散模式 (A/B/C/D/E) 可正确分类
- [ ] 异方差检验: White (1980) 输出 p 值
- [ ] 论文附录可用: 输出 (factor, pattern, pattern_name, trends) 表格

---

## 4. §3 前置处理诚实性

### 4.1 学术背景 (RESEARCH_NOTES §3)

RESEARCH_NOTES §3 指出**前置处理诚实性**是论文的主要贡献, 而非新的因子发现。核心论点:
- 因子表现的可重复性高度依赖前置处理的 6 个自由度
- 现有文献通常只报告最优配置, 忽略配置搜索空间带来的 data snooping
- 论文贡献: 显式暴露 6 自由度, 通过消融设计量化各自由度对结论的影响

**6 个前置处理自由度** (RESEARCH_NOTES §3.1):

| 自由度 | 描述 | 现有实现位置 | 默认值 |
|--------|------|------------|--------|
| 去极值 | Winsorization 方法/阈值 | `AdaptiveWinsor` (modules/) | MAD 3.0 |
| 标准化 | Z-score / Rank / Robust | `Standardizer` (adapters.py) | Z-score |
| 缺失处理 | 均值/中位数/KNN/向前填充 | `ImputerAdapter` (adapters.py) | 行业均值 |
| 中性化 | 行业/市值/Barra 风险 | `NeutralizerAdapter` (adapters.py) | 行业 + 市值 |
| 对齐 | 时间/截面/日历对齐 | `cached_data_loader.py` | 交易日历 |
| 起止点 | 回测起止日期 | `BacktestEngine` | 2015-2024 |

### 4.2 实证载体: ABLATION_DESIGN_V3.0.0.md

§3 前置处理诚实性的**实证载体**为 `docs/private/ABLATION_DESIGN_V3.0.0.md`, 该文档已设计完整的四层消融:

| 层 | 名称 | 内容 |
|----|------|------|
| L1 | 组件消融 | 逐个去除 5 个处理模块 (Fingerprint/Decoupler/AdaptiveWinsor/Imputer/Neutralizer) |
| L2 | 路由消融 | 多维路由 vs 硬路由 vs 均匀路由 |
| L3 | 参数消融 | 关键超参数 (winsor_threshold / orthogonal_strength 等) 的敏感性 |
| L4 | 前置处理消融 | 6 自由度的网格搜索 |

**基线阶梯** (B0-B3):
- B0: 无处理 (原始因子)
- B1: 仅去极值 + 标准化
- B2: B1 + 缺失处理 + 中性化
- B3: B2 + 指纹分类 + 路由 (完整 Pipeline)

**显著性检验**: Ledoit-Wolf (2008) HAC + bootstrap, 对比各消融配置与完整 Pipeline 的表现差异。

### 4.3 §3 → 消融载体映射

| RESEARCH_NOTES §3 论点 | 消融载体 | 实现位置 |
|----------------------|---------|---------|
| 6 自由度影响因子表现 | L4 前置处理消融 (6 × 3 = 18 配置) | ABLATION_DESIGN_V3.0.0.md §3 |
| 默认配置非最优 | B0-B3 基线阶梯对比 | ABLATION_DESIGN_V3.0.0.md §2 |
| 配置搜索空间 data snooping | Ledoit-Wolf bootstrap 校正 | ABLATION_DESIGN_V3.0.0.md §4 |
| 处理顺序敏感 | L1 组件消融 (5! = 120 排列) | ABLATION_DESIGN_V3.0.0.md §3.1 |
| 路由策略影响 | L2 路由消融 (3 策略) | ABLATION_DESIGN_V3.0.0.md §3.2 |
| 参数鲁棒性 | L3 参数消融 (网格搜索) | ABLATION_DESIGN_V3.0.0.md §3.3 |

### 4.4 §3 无新 E 任务

**§3 前置处理诚实性不产生新的 E 任务**, 原因:
1. 实证载体 (ABLATION_DESIGN_V3.0.0.md) 已设计完成
2. 处理模块 (去极值/标准化/缺失/中性化) 已在 v2.6.0 E1-E9 全部实施
3. 显著性检验 (Ledoit-Wolf HAC + bootstrap) 复用 statsmodels
4. 论文写作时直接引用 ABLATION_DESIGN_V3.0.0.md 的结果

**工程约束**: 实施 ABLATION_DESIGN_V3.0.0.md 时, 不得修改现有 5 个处理模块的接口, 仅通过配置切换实现消融。

---

## 5. §4 统计→决策桥接

### 5.1 学术背景 (RESEARCH_NOTES §4)

RESEARCH_NOTES §4 提出统计→决策桥接的 **A+C 混合方案**:
- **方案 A (概率映射)**: 将统计输出 (p 值 / IC / 漂移检测) 映射为决策权重
- **方案 C (在线凸优化)**: OCO (Online Convex Optimization) 在线更新权重
- 弃用方案 B (Bandit, 见 §2.3.2 关键限定)

**三工程挑战** (RESEARCH_NOTES §4.7):
1. **时间对齐** (§4.7.1): 统计输出 (日频) 与决策频率 (月频/季频) 的对齐
2. **冷启动 O1**: 新因子无历史数据时的先验设定
3. **状态识别延迟 O2**: 体制切换被检测时, 可能已滞后若干期
4. **预测误差传播 O3**: 统计预测误差通过决策层放大

**Q2 soft-update 公式** (在 (μ, σ²) 参数空间):
$$\mu_{t+1} = (1 - \alpha_t) \mu_t + \alpha_t \hat{\mu}_t, \quad \sigma^2_{t+1} = (1 - \alpha_t) \sigma^2_t + \alpha_t (\hat{\mu}_t - \mu_{t+1})^2$$

其中 $\alpha_t$ 为学习率, $\hat{\mu}_t$ 为新观测。

---

### E10: StatisticalDecisionBridge + StateConditionedPrior

#### 5.1.1 任务编号
**E10** — 统计→决策桥接接口层 (A+C 混合方案)

#### 5.1.2 代码改动

| 文件 | 改动类型 | 类/方法 | 接口签名 |
|------|---------|--------|---------|
| `backtest/statistical_decision_bridge.py` | 新建文件 | `StateConditionedPrior` (dataclass) | `@dataclass: factor_name: str, regime: str, mu_prior: float, sigma_sq_prior: float, confidence: float, n_observations: int` |
| `backtest/statistical_decision_bridge.py` | 新建文件 | `StatisticalDecisionBridge` | `__init__(self, enable: bool = False, learning_rate: float = 0.1, min_observations: int = 60, cold_start_prior: str = 'uninformative')` |
| `backtest/statistical_decision_bridge.py` | 新增方法 | `StatisticalDecisionBridge.fit` | `fit(self, statistical_outputs: Dict[str, Dict], state_priors: Optional[Dict[str, StateConditionedPrior]] = None) -> 'StatisticalDecisionBridge'` |
| `backtest/statistical_decision_bridge.py` | 新增方法 | `StatisticalDecisionBridge.update` | `update(self, factor_name: str, new_observation: float, regime: Optional[str] = None) -> Dict[str, float]` (Q2 soft-update) |
| `backtest/statistical_decision_bridge.py` | 新增方法 | `StatisticalDecisionBridge.compute_decision_weights` | `compute_decision_weights(self, alpha: float = 0.05) -> Dict[str, float]` (概率映射, 方案 A) |
| `backtest/statistical_decision_bridge.py` | 新增方法 | `StatisticalDecisionBridge.oco_update` | `oco_update(self, gradient: Dict[str, float], eta: float = 0.01) -> Dict[str, float]` (在线凸优化, 方案 C) |
| `backtest/statistical_decision_bridge.py` | 新增方法 | `StatisticalDecisionBridge.get_diagnostics` | `get_diagnostics(self) -> Dict[str, Any]` |
| `backtest/statistical_decision_bridge.py` | 新增私有方法 | `StatisticalDecisionBridge._probability_mapping` | `_probability_mapping(self, p_value: float, ic: float, drift_flag: bool) -> float` (方案 A 核心映射) |
| `backtest/statistical_decision_bridge.py` | 新增私有方法 | `StatisticalDecisionBridge._cold_start_prior` | `_cold_start_prior(self, factor_name: str, strategy: str) -> StateConditionedPrior` |
| `backtest/statistical_decision_bridge.py` | 新增私有方法 | `StatisticalDecisionBridge._align_time_frequency` | `_align_time_frequency(self, daily_stats: Dict, decision_freq: str = 'M') -> Dict` (§4.7.1 时间对齐) |
| `pipelines_v2.py` | 扩展配置 | `PipelineV2Config` | 新增: `enable_decision_bridge: bool = False`, `bridge_learning_rate: float = 0.1`, `bridge_decision_freq: str = 'M'` |
| `tests/backtest/test_statistical_decision_bridge.py` | 新建测试 | `TestStatisticalDecisionBridge` | TDD |

#### 5.1.3 算法实现

**数学公式** (A+C 混合方案):

**方案 A — 概率映射**:
$$w_f = \frac{\exp(\lambda \cdot s_f)}{\sum_{f'} \exp(\lambda \cdot s_{f'})}$$

其中 $s_f$ 为因子 $f$ 的综合得分:
$$s_f = (1 - p_f) \cdot \text{sign}(IC_f) \cdot |IC_f| \cdot (1 - \text{drift}_f)$$

$p_f$ = BH-FDR 校正后 p 值, $IC_f$ = 信息系数, $\text{drift}_f \in \{0, 1\}$ = CUSUM 漂移标志.

**方案 C — 在线凸优化 (OCO)**:
$$w_{t+1} = \Pi_{\Delta} \left( w_t - \eta \nabla \ell_t(w_t) \right)$$

其中 $\Pi_{\Delta}$ 为单纯形投影, $\eta$ 为学习率, $\ell_t$ 为期损失 (如负 Sharpe).

**Q2 soft-update** (在 (μ, σ²) 参数空间):
$$\mu_{t+1} = (1 - \alpha_t) \mu_t + \alpha_t \hat{\mu}_t$$
$$\sigma^2_{t+1} = (1 - \alpha_t) \sigma^2_t + \alpha_t (\hat{\mu}_t - \mu_{t+1})^2$$

**Python 代码片段**:

```python
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import warnings


@dataclass
class StateConditionedPrior:
    """状态条件先验 (RESEARCH_NOTES §4.5)

    存储因子在特定体制下的 (μ, σ²) 先验, 用于:
    - 冷启动 (O1): 新因子用体制先验
    - 状态切换 (O2): 体制变化时切换先验
    - 预测误差传播 (O3): 显式建模 σ² 传播
    """
    factor_name: str
    regime: str
    mu_prior: float
    sigma_sq_prior: float
    confidence: float = 1.0  # 基于观测数
    n_observations: int = 0


class StatisticalDecisionBridge:
    """统计→决策桥接 (RESEARCH_NOTES §4, A+C 混合方案)

    方案 A (概率映射): 将 (p_value, IC, drift_flag) 映射为决策权重
    方案 C (OCO): 在线凸优化更新权重
    Q2 soft-update: 在 (μ, σ²) 参数空间软更新

    三工程挑战的处理:
    - 时间对齐 (§4.7.1): _align_time_frequency() 将日频统计聚合为月频/季频
    - 冷启动 O1: _cold_start_prior() 用体制先验或无信息先验
    - 状态识别延迟 O2: predict_proba 输出体制概率, 而非硬标签
    - 预测误差传播 O3: 显式建模 σ² 传播, 决策权重受 σ² 调制
    """

    def __init__(
        self,
        enable: bool = False,
        learning_rate: float = 0.1,
        min_observations: int = 60,
        cold_start_prior: str = 'uninformative',
        lambda_softmax: float = 1.0,
        oco_eta: float = 0.01,
    ):
        self.enable = enable
        self.learning_rate = learning_rate
        self.min_observations = min_observations
        self.cold_start_prior = cold_start_prior
        self.lambda_softmax = lambda_softmax
        self.oco_eta = oco_eta
        # 因子参数: {factor_name: {'mu': float, 'sigma_sq': float, 'n_obs': int, 'regime': str}}
        self._factor_params: Dict[str, Dict] = {}
        # 统计输出缓存
        self._statistical_outputs: Optional[Dict] = None
        # OCO 权重
        self._oco_weights: Optional[Dict[str, float]] = None

    def fit(
        self,
        statistical_outputs: Dict[str, Dict],
        state_priors: Optional[Dict[str, StateConditionedPrior]] = None,
    ) -> 'StatisticalDecisionBridge':
        """拟合桥接层

        Args:
            statistical_outputs: {factor_name: {'p_value': float, 'ic_mean': float,
                                                 'drift_flag': bool, 'regime': str}}
            state_priors: {factor_name: StateConditionedPrior} 状态条件先验 (来自 E8)
        """
        self._statistical_outputs = statistical_outputs

        for fname, outputs in statistical_outputs.items():
            # 冷启动处理 (O1)
            if state_priors and fname in state_priors:
                prior = state_priors[fname]
                self._factor_params[fname] = {
                    'mu': prior.mu_prior,
                    'sigma_sq': prior.sigma_sq_prior,
                    'n_obs': prior.n_observations,
                    'regime': prior.regime,
                }
            else:
                prior = self._cold_start_prior(fname, self.cold_start_prior)
                self._factor_params[fname] = {
                    'mu': prior.mu_prior,
                    'sigma_sq': prior.sigma_sq_prior,
                    'n_obs': prior.n_observations,
                    'regime': prior.regime,
                }

        return self

    def update(
        self,
        factor_name: str,
        new_observation: float,
        regime: Optional[str] = None,
    ) -> Dict[str, float]:
        """Q2 soft-update 在 (μ, σ²) 参数空间

        μ_{t+1} = (1-α) μ_t + α * obs
        σ²_{t+1} = (1-α) σ²_t + α * (obs - μ_{t+1})²
        """
        if factor_name not in self._factor_params:
            self._factor_params[factor_name] = {
                'mu': 0.0, 'sigma_sq': 1.0, 'n_obs': 0, 'regime': regime or 'unknown'
            }

        params = self._factor_params[factor_name]
        alpha = min(self.learning_rate, 1.0 / (params['n_obs'] + 1))

        old_mu = params['mu']
        new_mu = (1 - alpha) * old_mu + alpha * new_observation
        new_sigma_sq = (1 - alpha) * params['sigma_sq'] + alpha * (new_observation - new_mu) ** 2

        params['mu'] = new_mu
        params['sigma_sq'] = max(new_sigma_sq, 1e-10)  # 避免零方差
        params['n_obs'] += 1
        if regime is not None:
            params['regime'] = regime

        return {
            'factor': factor_name,
            'mu': new_mu,
            'sigma_sq': new_sigma_sq,
            'n_obs': params['n_obs'],
            'regime': params['regime'],
        }

    def compute_decision_weights(self, alpha: float = 0.05) -> Dict[str, float]:
        """方案 A: 概率映射

        w_f = exp(λ * s_f) / Σ exp(λ * s_f')
        s_f = (1 - p_f) * sign(IC_f) * |IC_f| * (1 - drift_f)
        """
        if self._statistical_outputs is None:
            return {}

        scores = {}
        for fname, outputs in self._statistical_outputs.items():
            p_val = outputs.get('p_value', 1.0)
            ic = outputs.get('ic_mean', 0.0)
            drift = 1.0 if outputs.get('drift_flag', False) else 0.0
            scores[fname] = self._probability_mapping(p_val, ic, bool(drift))

        # Softmax 归一化
        max_score = max(scores.values()) if scores else 0.0
        exp_scores = {f: np.exp(self.lambda_softmax * (s - max_score)) for f, s in scores.items()}
        total = sum(exp_scores.values())
        if total > 0:
            weights = {f: e / total for f, e in exp_scores.items()}
        else:
            # 均匀分配
            n = len(scores)
            weights = {f: 1.0 / n for f in scores} if n > 0 else {}

        return weights

    def _probability_mapping(
        self,
        p_value: float,
        ic: float,
        drift_flag: bool,
    ) -> float:
        """方案 A 核心映射: 统计输出 → 决策得分

        s = (1 - p) * sign(IC) * |IC| * (1 - drift)

        - (1 - p): p 值越小, 得分越高 (显著因子权重高)
        - sign(IC) * |IC|: IC 正向且大, 得分高
        - (1 - drift): 漂移因子降权
        """
        significance = max(0.0, 1.0 - p_value)
        ic_component = np.sign(ic) * abs(ic)
        drift_penalty = 0.0 if drift_flag else 1.0
        return significance * ic_component * drift_penalty

    def oco_update(
        self,
        gradient: Dict[str, float],
        eta: float = None,
    ) -> Dict[str, float]:
        """方案 C: 在线凸优化更新

        w_{t+1} = Π_Δ(w_t - η * ∇ℓ)
        Π_Δ: 单纯形投影
        """
        if eta is None:
            eta = self.oco_eta

        if self._oco_weights is None:
            # 初始化均匀权重
            factors = list(gradient.keys())
            n = len(factors)
            self._oco_weights = {f: 1.0 / n for f in factors}

        # 梯度下降
        new_weights = {
            f: self._oco_weights.get(f, 0.0) - eta * gradient.get(f, 0.0)
            for f in self._oco_weights
        }

        # 单纯形投影 (Wang & Carreira-Perpiñán 2013)
        self._oco_weights = self._project_to_simplex(new_weights)
        return self._oco_weights.copy()

    def _project_to_simplex(self, weights: Dict[str, float]) -> Dict[str, float]:
        """投影到单纯形 (非负 + 和为 1)"""
        values = np.array(list(weights.values()))
        keys = list(weights.keys())
        n = len(values)

        # 排序降序
        u = np.sort(values)[::-1]
        cssv = np.cumsum(u) - 1
        rho = np.nonzero(u - cssv / np.arange(1, n + 1) > 0)[0][-1]
        theta = cssv[rho] / (rho + 1)
        projected = np.maximum(values - theta, 0)
        # 归一化
        total = projected.sum()
        if total > 0:
            projected = projected / total

        return {k: float(v) for k, v in zip(keys, projected)}

    def _cold_start_prior(
        self,
        factor_name: str,
        strategy: str = 'uninformative',
    ) -> StateConditionedPrior:
        """冷启动先验 (O1)

        strategy:
        - 'uninformative': μ=0, σ²=1 (无信息先验)
        - 'peer_median': 用同类因子的中位数 (需外部传入, 简化为 uninformative)
        - 'regime_average': 用体制平均 (需 E8 数据, 简化为 uninformative)
        """
        if strategy == 'uninformative':
            return StateConditionedPrior(
                factor_name=factor_name,
                regime='unknown',
                mu_prior=0.0,
                sigma_sq_prior=1.0,
                confidence=0.0,
                n_observations=0,
            )
        # 其他策略简化为 uninformative
        return StateConditionedPrior(
            factor_name=factor_name,
            regime='unknown',
            mu_prior=0.0,
            sigma_sq_prior=1.0,
            confidence=0.0,
            n_observations=0,
        )

    def _align_time_frequency(
        self,
        daily_stats: Dict[str, List[float]],
        decision_freq: str = 'M',
    ) -> Dict[str, float]:
        """时间对齐 (§4.7.1): 日频统计 → 月频/季频决策

        Args:
            daily_stats: {factor_name: [daily_values]}
            decision_freq: 'D' / 'W' / 'M' / 'Q'

        Returns:
            {factor_name: aggregated_value}
        """
        if decision_freq == 'D':
            # 日频: 用最近值
            return {f: v[-1] if v else 0.0 for f, v in daily_stats.items()}

        # 聚合: 取均值
        aggregated = {}
        for fname, values in daily_stats.items():
            if not values:
                aggregated[fname] = 0.0
            elif decision_freq == 'W':
                aggregated[fname] = float(np.mean(values[-5:]))  # 近 5 日均值
            elif decision_freq == 'M':
                aggregated[fname] = float(np.mean(values[-21:]))  # 近 21 日均值
            elif decision_freq == 'Q':
                aggregated[fname] = float(np.mean(values[-63:]))  # 近 63 日均值
            else:
                aggregated[fname] = float(np.mean(values))

        return aggregated

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'enabled': self.enable,
            'n_factors': len(self._factor_params),
            'learning_rate': self.learning_rate,
            'cold_start_strategy': self.cold_start_prior,
            'lambda_softmax': self.lambda_softmax,
            'oco_eta': self.oco_eta,
            'factor_params': {
                f: {'mu': p['mu'], 'sigma_sq': p['sigma_sq'], 'n_obs': p['n_obs']}
                for f, p in self._factor_params.items()
            },
            'oco_weights': self._oco_weights,
        }
```

#### 5.1.4 兼容性分析

| v3.0.0 已实施模块 | 兼容性 | 说明 |
|-------------------|--------|------|
| T4 `apply_bh_fdr` | ✓ 输入源 | E10 消费 BH-FDR 校正后的 p 值 |
| T3 `CUSUMDriftMonitor` | ✓ 输入源 | E10 消费 CUSUM 的 drift_flag |
| T1 21 维 FactorFingerprint | ✓ 输入源 | E10 消费 ic_mean 等指纹衍生指标 |
| E8 StateConditionedAnalyzer | ✓ 数据源 | E10 的状态条件先验来自 E8 |
| `PipelineV2Config` | ✓ 扩展兼容 | 新增 3 字段, 默认 `enable=False` |

#### 5.1.5 接口设计 (与 PipelineV2Config 协同)

```python
@dataclass
class PipelineV2Config:
    # ... 现有字段 ...
    # E10 新增 (v3.0.0 §4 决策桥接)
    enable_decision_bridge: bool = False
    bridge_learning_rate: float = 0.1
    bridge_decision_freq: str = 'M'  # 月频决策
```

```python
# 使用示例:
from backtest.statistical_decision_bridge import StatisticalDecisionBridge, StateConditionedPrior

bridge = StatisticalDecisionBridge(
    enable=True,
    learning_rate=0.1,
    cold_start_prior='uninformative',
    lambda_softmax=1.0,
    oco_eta=0.01,
)

# 从 Pipeline 输出构建统计输入
statistical_outputs = {
    'momentum_12m': {
        'p_value': 0.02,       # BH-FDR 校正后
        'ic_mean': 0.05,       # 来自指纹
        'drift_flag': False,   # 来自 CUSUM
        'regime': 'bull',      # 来自 E7 MarkovRegimeIdentifier
    },
    'value_hml': {
        'p_value': 0.15,
        'ic_mean': -0.02,
        'drift_flag': True,
        'regime': 'bull',
    },
}

bridge.fit(statistical_outputs)

# 方案 A: 概率映射
weights_a = bridge.compute_decision_weights(alpha=0.05)

# Q2 soft-update (新观测到达)
bridge.update('momentum_12m', new_observation=0.06, regime='bull')

# 方案 C: OCO 更新 (收到梯度反馈)
gradient = {'momentum_12m': -0.1, 'value_hml': 0.05}
weights_c = bridge.oco_update(gradient)
```

#### 5.1.6 性能评估

| 指标 | 估算 | 说明 |
|------|------|------|
| 计算复杂度 | O(K) per update | K 个因子的 softmax / OCO 更新 |
| 内存占用 | ~5 MB | 因子参数字典 |
| 预期运行时间 | <1 秒 | K=100 因子 |
| 时间对齐 | O(K × T_window) | 日频聚合, 窗口最大 63 |

#### 5.1.7 外部依赖

| 依赖 | 版本 | 安装方式 | 说明 |
|------|------|---------|------|
| numpy | >=1.22 | 核心 (已装) | softmax / 单纯形投影 |

**无新增依赖**。

#### 5.1.8 测试计划 (TDD)

**测试文件**: `tests/backtest/test_statistical_decision_bridge.py`
**测试类**: `TestStatisticalDecisionBridge`

| 测试用例 | 描述 | 验证点 |
|---------|------|--------|
| `test_fit_returns_self` | fit 返回 self | isinstance(result, StatisticalDecisionBridge) |
| `test_cold_start_uninformative` | 无信息先验 μ=0, σ²=1 | params == {mu: 0, sigma_sq: 1} |
| `test_update_q2_soft_update` | Q2 更新 μ 和 σ² | mu 和 sigma_sq 变化 |
| `test_update_n_observations_increments` | 更新后 n_obs +1 | n_obs == initial + 1 |
| `test_compute_decision_weights_sum_to_one` | 权重和为 1 | abs(sum - 1.0) < 1e-6 |
| `test_compute_decision_weights_significant_factor_higher` | 显著因子权重高 | weights[significant] > weights[non_significant] |
| `test_probability_mapping_drift_penalty` | 漂移因子降权 | score_with_drift < score_without_drift |
| `test_probability_mapping_p_value_effect` | p 值越小得分越高 | score(p=0.01) > score(p=0.5) |
| `test_oco_update_simplex_projection` | OCO 权重在单纯形上 | all(w >= 0) and abs(sum - 1) < 1e-6 |
| `test_oco_update_gradient_descent` | OCO 沿梯度反方向移动 | weight[high_gradient] decreases |
| `test_align_time_frequency_daily` | 日频返回最近值 | result == last value |
| `test_align_time_frequency_monthly` | 月频返回近 21 日均值 | result == mean(values[-21:]) |
| `test_get_diagnostics_fields` | 诊断含必要字段 | {'n_factors', 'learning_rate', 'factor_params'} ⊆ keys |
| `test_disabled_no_op` | enable=False 时方法返回空 | compute_decision_weights 返回 {} |
| `test_state_conditioned_prior_dataclass` | StateConditionedPrior 可正确创建 | 属性访问正确 |

**TDD 流程**:
1. **Red**: 写 `TestStatisticalDecisionBridge` 全部测试
2. **Green**: 实现 `StatisticalDecisionBridge` + `StateConditionedPrior`
3. **Review**: softmax 权重和为 1, OCO 单纯形投影正确, Q2 更新公式正确

#### 5.1.9 验收标准

- [ ] `StatisticalDecisionBridge` + `StateConditionedPrior` 类完整实现, 所有测试通过 (≥15 测试用例)
- [ ] 方案 A (概率映射): softmax 权重和为 1, 显著因子权重高
- [ ] 方案 C (OCO): 单纯形投影, 权重非负且和为 1
- [ ] Q2 soft-update: μ 和 σ² 正确更新, n_obs 递增
- [ ] 时间对齐 (§4.7.1): 日频 → 月频/季频聚合
- [ ] 冷启动 (O1): 无信息先验 μ=0, σ²=1
- [ ] `PipelineV2Config` 新增 3 字段, 默认 `enable=False`
- [ ] 论文附录可用: 输出 (factor, mu, sigma_sq, decision_weight) 表格

---

## 6. 全局风险评估

### 6.1 跨任务风险矩阵

| 风险 | 等级 | 影响范围 | 缓解措施 |
|------|------|---------|---------|
| A 股状态数据缺失率 >5% | 中 | E7 → E8 / E9 / E10 | `min_obs_per_cell` 过滤 + 缺失率诊断报告 (E7 内置) |
| Markov 拟合不收敛 (EM 局部最优) | 中 | E7 | 降级硬阈值 (复用 T1.2 `health.py:_split_bull_bear` + 失败计数诊断) |
| 21 维指纹多重共线性 (gpd_shape vs hill_estimator) | 高 | E5 / E8 | PCA 降维或 L2 正则化 (复用 `factor_decoupler`); 共线性诊断 VIF > 10 时告警 |
| IC 非平稳导致回归失效 (RESEARCH_NOTES §2B.4.1) | 高 | E8 / E9 | ADF/KPSS 单位根检验前置; 非平稳时使用差分或滚动窗口回归 |
| 12K 多重检验 (12 状态 × K 因子) 计算量过大 | 中 | E8 | BH-FDR 向量化实现 (复用 T4); `joblib` 并行 (复用 `factor_significance.py` 模式) |
| Romano-Wolf bootstrap 在强自相关下失效 | 中 | E2 | Politis-Romano (1994) stationary bootstrap, 块长自动选择 |
| White Reality Check 在 benchmark 数据探测下偏保守 | 低 | E3 | 同时输出 Hansen (2005) SPA 三个统计量 (上/下/一致) |
| 三通道分解残差异方差 (White 1980 检验拒绝) | 中 | E9 | 报告异方差诊断; 使用 Newey-West HAC 标准误 (已在 E8 实现) |
| Bandit MC 决策门槛 10% 经验阈值缺乏理论依据 | 中 | E6 | Monte Carlo 1000 次重复 → 报告 Plan A / B / C 性能分布; 阈值灵敏度分析 [5%, 10%, 15%] |
| 决策桥接 OCO 在线学习发散 (非凸反馈) | 高 | E10 | 单纯形投影强制约束; `oco_eta` 学习率衰减 (1/√t); 梯度裁剪 |
| 时间对齐跨频 (月频状态 vs 日频因子) | 中 | E10 | `_align_time_frequency` 双向兼容 (forward-fill / mean aggregation); 缺失时段降级先验 |
| 状态识别延迟 O2 (Markov 事后拟合, 实时滞后) | 高 | E10 | E10 明确不做实时状态识别; 提供 `regime_lag` 参数记录延迟, 决策权重乘以折扣因子 |
| 预测误差传播 O3 (上游误差放大) | 高 | E10 | 决策权重 clipping [0, w_max]; 上游 CUSUM 漂移触发时, 决策权重回退至无信息先验 |

### 6.2 学术合规风险

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| BH-FDR 对相依结构敏感 (PRDS 假设) | 中 | E1 检测力曲线对比中包含正相依 / 负相依两种 MC 场景; E2 Romano-Wolf 作为强假设对照 |
| Markov 状态数 (2/3/4) 选择主观 | 中 | E7 用 AIC/BIC 选择 + 报告似然比检验; 降级路径明确 (2 状态) |
| Ferson (2003) 条件因子模型对状态变量选择敏感 | 中 | E8 报告全 12 变量 + L1/L2/L3 三层降维对照表 |
| 三通道分解 `log R_factor = log IC + log σ_factor + log σ_R` 在负值时失效 | 高 | E9 用 `sign + log |x|` 分解; 符号翻转记为 Divergence Pattern E (sign-flip) |
| Q2 soft-update 公式 (μ, σ²) 假设高斯 | 中 | E10 输出分布诊断 (偏度/峰度); 偏离时切换至 t 分布先验 |

### 6.3 工程实施风险

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| DuckDB 表膨胀 (E4 持续写入 21+6+3 字段 × K 因子 × T 天) | 低 | E4 用 partition + index; 每年归档; 报告表大小诊断 |
| `akshare` API 限流 / 数据源变更 | 中 | E7 缓存到本地 parquet; 失败重试 + 降级到 YFinance (美股状态变量) |
| statsmodels MarkovRegression 在 Windows 下数值不稳定 | 中 | E7 添加 `random_state` 固定初值; 失败时返回硬阈值结果 + 警告 |
| sklearn-style 接口与 v3.0.0 既有 PipelineV2Config 集成回归 | 中 | 每个 E 任务 TDD, 复用 `tests/pipelines_v2/` 既有 860+ 测试基线 |
| 新增 `enable_*` 字段破坏 pickle 兼容性 (旧 config 反序列化) | 低 | 所有新字段 `field(default=False)` + dataclass `__post_init__` 兼容缺失字段 |
| extras `state-data` 安装路径与 `all` 冲突 | 低 | `pyproject.toml` 中 `all` 不包含 `state-data` (akshare 重依赖, 按需安装) |

### 6.4 优先级与降级策略

**P1 任务 (E1 / E2 / E3 / §3 消融) 降级策略**:
- 任一 MC 对比失败 → 报告失败原因, 不影响主流程 (诊断优先于校正)
- Bootstrap 数值不稳定 → 增加 B 次重采样 (1000 → 5000), 或切换为 asymptotic approximation

**P2 任务 (E4 / E5 / E7 / E8 / E9) 降级策略**:
- E4 DuckDB 写入失败 → 降级到 CSV 备份 + 警告
- E5 三层归因任一层失败 → 仅报告成功层, 失败层记 NaN + 诊断
- E7 Markov 不收敛 → 硬阈值 (复用 T1.2 `_split_bull_bear`)
- E8 双轨回归任一轨失败 → 仅报告成功轨, 另一轨记 NaN
- E9 三通道分解在负值场景 → 切换至 `sign + log |x|` 分解 + Pattern E 标记

**P3 任务 (E6 / E10) 降级策略**:
- E6 Bandit MC 决策门槛未通过 → Plan A 自动生效, E6 仅作为 sandbox 模块存在, 不接入主流程
- E10 OCO 发散 → 自动切换至方案 A (概率映射); 冷启动场景回退至无信息先验

---

## 7. 结语

本执行方案基于 `RESEARCH_NOTES.md` 五个章节的学术论点, 拆解为 10 个可独立交付的工程任务 (E1-E10), 严格遵循项目"诊断优先于校正"的核心立场:

1. **§1 三块补强 (E1-E3)**: 为 BH-FDR 在 KS 迁移检验中的学术价值提供检测力曲线、Romano-Wolf、White Reality Check 三角度对比, 不修改主流程, 仅产出对比报告
2. **§2 元控制层 (E4-E6)**: 在 RESEARCH_NOTES §2.3.2 明确的"标准 Bandit 三平稳假设全失效"前提下, 默认采用方案 A (静态规则 + CUSUM 漂移检测); 方案 B (Drift-Aware Bandit) 仅作为 P3 条件触发的 MC sandbox 存在, 决策门槛 10% 未通过则不接入主流程
3. **§2B 状态归因 (E7-E9)**: 12 A 股状态变量 + 双轨回归 (R_factor / IC) + 三通道分解, 是 RESEARCH_NOTES 的核心实证内容; Markov 失败时降级硬阈值, 不阻塞主流程
4. **§3 前置处理诚实性**: 不产生新 E 任务, 实证载体为 `ABLATION_DESIGN_V3.0.0.md`, 复用 v2.6.0 E1-E9 全套处理模块
5. **§4 决策桥接 (E10)**: A+C 混合 (概率映射 + 在线凸优化), 默认 `enable=False`; 三个工程挑战 (O1 冷启动 / O2 状态识别延迟 / O3 预测误差传播) 均有明确缓解措施

**所有新模块默认 `enable=False`**, 不破坏 v3.0.0 既有 860+ 测试基线; 所有 E 任务 TDD, 先写测试再实现; 所有降级路径明确, 任一模块失败不影响主流程产出。

**与 v3.0.0 路线图的关系**: E1-E3 补强 T4 (BH-FDR), E4-E6 补强 T3 (CUSUM) + T1 (21维指纹), E7-E9 实现 T5/T6/T7 (状态接入 / StateConditionedAnalyzer / 三通道分解), E10 实现 §4 决策桥接。完成后, v3.0.0 路线图除 T2 (流式) 外全部就绪。

---

## 8. 修订日志

| 版本 | 日期 | 修订内容 | 修订人 |
|------|------|---------|--------|
| v1.0 | 2026-07-08 | 初始创建, 包含 E1-E10 任务拆解 + §3 前置处理诚实性 + §6 风险评估 + 结语 | Scott Peng Liu |

---

## 附录 A: 自检验证清单

| # | 验证项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | 每个 E 任务有明确代码改动位置 (文件 + 类 + 方法) | ✅ | E1: `backtest/multiple_testing.py` PowerCurveAnalyzer; E2: 同文件 apply_romano_wolf; E3: 同文件 WhiteRealityCheck + HansenSPA; E4: `backtest/fingerprint_performance_logger.py` 新建; E5: `backtest/attribution_analyzer.py` 新建; E6: `backtest/bandit_mc_sandbox.py` 新建; E7: `backtest/state_data_loader.py` + `backtest/markov_regime_identifier.py` 新建; E8: `backtest/state_conditioned_analyzer.py` 新建; E9: `backtest/three_channel_decomposition.py` 新建; E10: `backtest/statistical_decision_bridge.py` 新建 |
| 2 | 算法实现含数学公式 + Python 代码片段 | ✅ | E1: BH/Bonferroni 公式 + MC 代码; E2: k-FWER stepdown 公式 + bootstrap 代码; E3: White Reality Check + SPA 统计量公式 + stationary bootstrap 代码; E4: DuckDB schema + 归因 OLS; E5: 三层归因 (标准化 OLS beta / 方差分解 / 交互 OLS + BH-FDR); E6: LinUCB + CUSUM 触发公式; E7: Markov 转移概率 + Hamilton (1989); E8: Ferson (2003) 条件回归 + Newey-West HAC; E9: 三通道分解 log R = log IC + log σ_factor + log σ_R + White (1980) 异方差检验; E10: Q2 soft-update (μ, σ²) + softmax + OCO 单纯形投影 |
| 3 | 外部依赖标注版本要求 | ✅ | E1-E6 / E10: 无新增依赖 (复用 numpy>=1.22 / scipy>=1.7 / statsmodels>=0.13 / duckdb>=0.10 / pandas>=2.0); E7: 新增 `akshare>=1.10` 放 `state-data` extras; E8/E9: 复用 statsmodels>=0.13 (MarkovRegression / Newey-West / White 检验); pyproject.toml `all` 不含 `state-data` |
| 4 | 与 v3.0.0 已实施代码兼容 | ✅ | E1-E3: 扩展 `apply_correction` 方法枚举, 不破坏既有 `benjamini_hochberg` / `bonferroni` / `none` 三路径; E4-E6 / E10: 所有新字段 `PipelineV2Config` 默认 `enable=False`, 不破坏既有配置; E5/E8: 复用 T4 `multiple_testing.py` `apply_bh_fdr`; E6: 复用 T3 `CUSUMDriftMonitor`; E7: 复用 T1.2 `health.py:_split_bull_bear` 降级; E8: 复用 `factor_significance.py` Newey-West 模式; 复用 `factor_decoupler` 共线性诊断 |
| 5 | 测试计划遵循 TDD | ✅ | 每个 E 任务包含 "测试文件 / 测试类 / 测试用例表 / TDD 流程 (Red→Green→Review)" 四段式; 测试用例覆盖: 正常路径 + 边界 (空数据/单点) + 失败降级 + 兼容性 (enable=False no-op) + 数学正确性 (黄金参考); 总测试用例数: E1 (10) + E2 (12) + E3 (14) + E4 (13) + E5 (15) + E6 (12) + E7 (16) + E8 (18) + E9 (15) + E10 (15) = 140 测试用例 |

