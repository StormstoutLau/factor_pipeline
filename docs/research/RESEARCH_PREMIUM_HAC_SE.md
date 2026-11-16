# RESEARCH 面板 HAC / Premium 标准误 (PREMIUM_HAC_SE)

> **版本**: v1.0 (2026-11-16)
> **调研工具**: `mcp_paper-search` (Crossref) + 源码静态核对
> **上游**: [PROJECT_STATUS §2 P2](../PROJECT_STATUS.md) /
> [DESIGN_DISCUSSION_V3.3.0 §6.3](../private/DESIGN_DISCUSSION_V3.3.0.md)
> **范围**: `modules/factor_health.PremiumEstimator` 的点估计补标准误;
> 不改变 `estimate` 数值, 不改变 `FactorHealthDiagnoser` 标签逻辑。

## §1 调研问题清单

- **Q1**: Fama-MacBeth 溢价的 HAC 标准误如何定义?
- **Q2**: 核平滑后的 λ̂(t) 是加权平均, 其方差如何用 HAC 近似?
- **Q3**: 每期 β_t 的横截面 OLS 标准误如何得到?
- **Q4**: 缺失期 (β_t=NaN) 如何处理?
- **Q5**: 置信区间用 t 分布还是正态近似?
- **Q6**: 滞后阶数如何选?
- **Q7**: 该改动是否影响现有 `estimate` / `diagnose` 行为?

## §2 学术文献调研

| 引用 | 标识 | 关键结论 | 状态 |
|------|------|---------|------|
| Fama & MacBeth (1973), JPE 81(3):607-636 | DOI: 10.1086/260061 | 逐期横截面回归得 β_t, 以时间序列均值作为溢价估计 λ̂ = (1/T)Σβ_t | ✅ VERIFIED |
| Newey & West (1987), Econometrica 55(3):703 | DOI: 10.2307/1913610 | HAC 长期方差 `Ω = γ0 + 2Σ ω_l γ_l`, Bartlett 核 `ω_l = 1 − l/(q+1)`, 使 SE(λ̂)=√(Ω/T) 对自相关/异方差稳健 | ✅ VERIFIED |
| Newey & West (1994), RES 61(4):631-653 | DOI: 10.2307/2297912 | 自动滞后阶数选择 (本实现复用仓内规则 `q = max(1, int(4·(T/100)^(2/9)))`) | ✅ VERIFIED |
| Epanechnikov (1969) | 仓内既有引用 | 局部常数核权重 `K(u)=0.75(1−u²)` | ✅ 沿用 |

**Q1/Q6 结论**: 溢价均值用 FM 时间序列均值; 其 HAC SE 用 Newey-West (1987) 长期方差除以有效期数;
带宽沿用仓内自动规则 (Newey-West 1994 形式)。

## §3 工程事实 (F1-F9)

| # | 事实 | 证据 |
|---|------|------|
| F1 | `estimate()` 只返回 `lambda_hat`, 并把未平滑的 β_t 存入 `_beta_raw` | [factor_health/__init__.py L48-L78](../../modules/factor_health/__init__.py#L48-L78) |
| F2 | `_cross_sectional_betas` 逐期计算单因子 OLS 斜率, 但**不保留残差**, 无法直接得到 SE | [L80-L108](../../modules/factor_health/__init__.py#L80-L108) |
| F3 | `_epanechnikov` 返回**归一化**权重 (sum=1) | [L110-L115](../../modules/factor_health/__init__.py#L110-L115) |
| F4 | `FactorHealthDiagnoser._classify_premium_health` 用朴素 `mean/(std/√T)` 作 FM t 值 | [L423-L435](../../modules/factor_health/__init__.py#L423-L435) |
| F5 | 模块内已有 `_newey_west_se` (用于衰减斜率), 但其 bread 是单变量 OLS, 不适用加权均值 | [L489-L523](../../modules/factor_health/__init__.py#L489-L523) |
| F6 | 现有测试只调用 `estimate()`, 未直接调用 `_cross_sectional_betas` | [test_layer3_factor_health.py L66-L107](../../tests/unit/test_layer3_factor_health.py#L66-L107) |
| F7 | §6.3 目标接口: `estimate_with_errors()` 返回 `λ̂(t) ± 1.96×SE` | [DESIGN_DISCUSSION_V3.3.0 L235-L244](../private/DESIGN_DISCUSSION_V3.3.0.md#L235-L244) |
| F8 | 混合数据可能含 NaN (因子/收益缺失), β_t 在有效股票 < min_stocks 时为 NaN | [L89-L95](../../modules/factor_health/__init__.py#L89-L95) |
| F9 | 模块无外部数据依赖, 合成面板即可验证 | 测试夹具 L14-L63 |

## §4 方法推导

### 4.1 每期 β_t 的 OLS 标准误 (Q3)

单因子横截面回归 `r_i = α + β f_i + ε_i`:
`Var(β̂_t) = σ²_ε,t / Σ_i (f_i − f̄)²`, 其中 `σ²_ε,t = Σ ε̂_i²/(n_t − 2)`。
本实现采用同方差 OLS SE (时间维 HAC 是主方差来源; 横截面异方差 robust 不在本次范围)。

### 4.2 λ̂(t) 的 HAC 方差 (Q2)

设归一化权重 `w_s` (sum=1), `λ̂_t = Σ_s w_s β_s`。在局部平稳近似下:

```
Var(λ̂_t) ≈ Ω_t · Σ_s w_s²
```

`Ω_t` 为窗口内 β 相对局部拟合的残差 `u_s = β_s − λ̂_s` 的 Newey-West 长期方差。
理由: 独立同方差时 `Var(Σwβ)=σ²Σw²`; 存在自相关时用 `Ω` 替代 `σ²`。
`Σw² = 1/n_eff` 是有效样本量倒数。

### 4.3 溢价均值的 HAC 标准误 (Q1)

```
λ̄ = mean(β_t, 有效期)
SE(λ̄) = sqrt( Ω_β / T_valid )
Ω_β = γ0 + 2 Σ_{l=1}^{q} (1 − l/(q+1)) γ_l
```

### 4.4 缺失处理 (Q4)

窗口内 `β_s` 与残差 `u_s` 按**有限值成对**过滤; 有效点 < 3 → `SE=NaN`。
均值 SE 使用全部有限 β_t; 有效期 < 3 → `NaN`。

### 4.5 置信区间 (Q5)

正态近似 `λ̂ ± z_{1−α/2}·SE`, `z = norm.ppf(1−α/2)` (α=0.05 → 1.96)。
不加 t 分布修正: 核平滑后有效样本量不整数, 且 T 通常 ≥ 30。

### 4.6 兼容性 (Q7)

- `estimate()` 数值与返回类型不变;
- 新增方法独立, `diagnose()` 不调用 → 标签零变化;
- 无新增依赖 (`numpy` / `scipy.stats.norm` 已在模块内)。

## §5 调研结论

- **可直接引用**: Fama & MacBeth (1973) / Newey & West (1987, 1994), 三条 DOI 均经 Crossref 核实。
- **实现口径**: FM 均值 HAC SE + 局部常数核的 `Ω·Σw²` 近似 + 逐期 OLS SE。
- **不可引用 (已避免)**: 把 `_newey_west_se` 直接用于 λ̂(t) — 其 bread 假设单变量 OLS, 与加权平均不匹配。
- **范围外**: 横截面异方差 robust SE、t 分布小样本修正、Bai-Perron 多断点。

## §6 步骤 2 review 记录

| # | 检查项 | 结论 |
|---|--------|------|
| R1 | 三条引用卷期页与 Crossref 一致 | ✅ |
| R2 | F1-F9 行号与当前源码一致 | ✅ |
| R3 | `Var(λ̂)=ΩΣw²` 在独立同方差时退化为 `σ²Σw²` | ✅ 推导正确 |
| R4 | 未把 F5 的 `_newey_west_se` 误作可直接复用 | ✅ 已列为反例 |
| R5 | 缺失处理与 v3.4.10/v3.4.11 口径一致 (有限值过滤) | ✅ |

**review 结论**: PASS。
