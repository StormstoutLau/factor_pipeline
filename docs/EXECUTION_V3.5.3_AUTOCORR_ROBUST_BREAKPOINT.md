# EXECUTION V3.5.3 — sup-F 自相关稳健临界值 (AR(1) sieve)

> **版本**: v3.5.3 (2026-11-17)
> **状态**: 已实施
> **上游**: [RESEARCH](research/RESEARCH_V3.5.3_AUTOCORR_ROBUST_BREAKPOINT.md) / ADR-049 / ADR-048
> **设计**: private (`docs/private/DESIGN_V3.5.3_AUTOCORR_ROBUST_BREAKPOINT.md`, 未提交)

---

## §1 目标

修复 `BreakpointDetector` 的 `sup_f_method='bootstrap'` 实现缺陷, 并为 `diagnose`
提供可选的**自相关稳健** sup-F 临界值:

1. `bootstrap` 从 iid 高斯改为 **AR(1) sieve 残差自助** (真正保留一阶自相关);
2. `FactorHealthDiagnoser` 透传方法/次数/随机种子;
3. `diagnose` 暴露 `breakpoint_sup_f_method` 与 `chow_critical`;
4. 默认 `asymptotic` 路径逐位不变。

---

## §2 变更清单

| 文件 | 变更 | 规模 |
|------|------|------|
| `modules/factor_health/__init__.py` | `BreakpointDetector.__init__` +`random_state` / 参数校验; `detect` +`critical_method` 并传 `y`; `_no_breakpoint_result` +1 键; `_sup_f_critical_value` +`y`; `_bootstrap_sup_f_crit` 重写为 AR(1) sieve; 新增 `_sup_f_batch`; `FactorHealthDiagnoser` +3 参数并透传; `_single_segment_view` / 多断点视图 +`critical`; `diagnose` +2 键 | ~+95/-45 行 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestAutocorrRobustSupF` F1-F11 | +129 行 |
| 版本锚点 6 处 | 3.5.2 → 3.5.3 | — |
| 文档 | RESEARCH / EXECUTION / 审计 / ADR-049 / CHANGELOG / README / README.en / ARCHITECTURE / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | — |

---

## §3 API 与契约

### §3.1 `BreakpointDetector` 构造参数

```python
BreakpointDetector(
    alpha=0.05, min_segment=0.15,
    sup_f_method='asymptotic',   # {'asymptotic', 'bootstrap'}
    n_bootstrap=1000,            # bootstrap 次数; bootstrap 下要求 >= 50
    random_state=42,             # bootstrap RNG
)
```

校验:
- 未知 `sup_f_method` → `ValueError`;
- `sup_f_method='bootstrap'` 且 `n_bootstrap < 50` → `ValueError`;
- `asymptotic` 下 `n_bootstrap` 不校验 (向后兼容)。

### §3.2 `detect` 输出 (6 → 7 键)

新增 `critical_method: str` (`'asymptotic' | 'bootstrap'`)。
`_no_breakpoint_result` (T<30) 同步 +1 键, `critical` 仍为 NaN。

> **语义** (复审 P6 澄清): `critical_method` 报告**配置**方法。退化回退
> (T<5 / 残差标准差 0 / 全 NaN) 时实际按 Andrews 渐近值或 NaN 计算,
> 标签不随之变化; `has_breakpoint` 判定不受影响 (回退只发生在
> `chow_max_stat=0` 或无有效样本的场景)。

### §3.3 `FactorHealthDiagnoser` 构造参数

```python
FactorHealthDiagnoser(..., sup_f_method='asymptotic',
                      n_bootstrap=1000, random_state=42)
```

### §3.4 `diagnose` 输出 (28 → 30 键)

| 键 | 类型 | 语义 |
|----|------|------|
| `breakpoint_sup_f_method` | str | 单断点 sup-F 临界值方法 |
| `chow_critical` | float | sup-F 临界值; T<30 退化时为 NaN |

原有 28 键语义不变; `detect_multiple` 的 BIC 路径不受影响。

### §3.5 `bootstrap` 语义修正

| 项 | 旧 (v3.5.2-) | 新 (v3.5.3) |
|----|--------------|-------------|
| 零分布生成 | `rng.randn(B, T)` (iid 高斯) | OLS AR(1) + 残差重采样递归 |
| 是否使用观测序列 | 否 | 是 |
| AR(1) φ=0.5 size | ~49% | 4.7% (实测) |
| 默认 | `asymptotic` | `asymptotic` (不变) |

---

## §4 实现要点

1. **AR(1) 代理**: `y_t = c + φ y_{t-1} + e_t`, OLS 估计 `(c, φ)`,
   `φ` 截断到 `[-0.99, 0.99]`, 残差中心化后**有放回重采样**;
2. **递归生成**: burn-in 50, 平稳初值 `c/(1-φ) + e*_0`, 生成长度 `T+burn`,
   丢弃前 50 期;
3. **向量化**: 一次生成 `(B, T+burn)`, sup-F 用累积和 `_sup_f_batch`, 复杂度 O(B·T);
4. **临界值**: `quantile(sup-F*, 1-alpha)`, 保持 `critical` 标量契约;
5. **退化**: `T<5` / 残差标准差为 0 / 残差长度 <2 → 回退 Andrews 渐近值;
6. **可复现**: `np.random.default_rng(self.random_state)`, 同 seed 同输入逐位一致;
7. **与既有实现一致**: 与 `StructuralBreakMonitor._bootstrap_pvalue` (设计 m10)
   采用相同的 AR(1) 代理、φ 截断与 burn-in 约定;
8. **单个断点存在性**: `detect` 始终是 `diagnose` 的存在性判定; `bootstrap`
   只替换临界值, 不改 sup-F 统计量与断点位置。

---

## §5 测试

| 文件 | 结果 |
|------|------|
| `tests/unit/test_layer3_factor_health.py` | **60 passed** (49 旧 + 11 新) |
| `tests/test_fix3_version_unification.py` | **7 passed** |
| `tests/test_backtest/verify_fix3_manual.py` | **5/5** (6 锚点一致, 缓存独立) |

F1-F11 覆盖: 默认零变更、AR(1) 临界值上移、iid 同阶、真实断点检出、
同 seed 复现、跨 seed 稳定、diagnoser 透传、30 键契约、参数校验、
短样本退化、向量化与标量 sup-F 一致。

---

## §6 端到端验证

### 6.1 实现口径 size/power (T=240, B=300, R=150, α=0.05)

| φ | 场景 | asymptotic | bootstrap |
|---|------|-----------|-----------|
| 0.0 | size | 4.7% | **4.0%** |
| 0.0 | power (Δ=1σ) | 100% | 100% |
| 0.5 | size | 48.7% | **4.7%** |
| 0.5 | power (Δ=1σ) | 100% | **96.0%** |

### 6.2 真实 β_t (4 因子, T=68-70)

| 因子 | φ | sup-F | asymptotic | bootstrap(AR1) | 判定 |
|------|---|-------|-----------|----------------|------|
| momentum_1m | -0.070 | 1.74 | 8.85 | 7.94 | 无断点 |
| reversal_1w | -0.069 | 1.82 | 8.85 | 7.43 | 无断点 |
| volatility_1m | -0.141 | 3.08 | 8.85 | 6.10 | 无断点 |
| amihud_1m | +0.208 | 2.67 | 8.85 | 12.22 | 无断点 |

真实数据标签不变; 正相关因子临界值上移 (12.22), 负相关因子下移 (6.10-7.94),
方向符合预期。

---

## §7 全量回归

| 指标 | 结果 |
|------|------|
| 命令 | `python -m pytest tests -q` |
| 结果 | **1797 passed / 15 skipped / 0 failed** (1027.28s, exit 0) |
| 基线 (v3.5.2) | 1786 passed / 15 skipped / 0 failed (1160.73s) |
| 增量 | +11 (F1-F11), 0 新增失败 |

---

## §8 限制

| 项 | 说明 |
|----|------|
| 自相关阶数 | 仅校正 AR(1); 高阶依赖 (AR(2+)) 可能仍有余留过度拒绝 |
| 高持续 | φ=0.8 时 size 约 8.7% (名义 5%), power 44% — 低信息下的诚实代价 |
| 短样本 | T<50 时 AR(1) 参数估计噪声大; T<30 仍走退化路径 |
| 确定性趋势 | AR(1) 代理无趋势项; β_t 含线性趋势时 asymptotic 与 bootstrap 均 ~100% 拒绝 (复审 P4) — 属 sup-F「H0=常数均值」既有语义, 趋势会被报告为断点 |
| 近单位根 | φ̂≈0.97 时 bootstrap 临界值发散 (>430), 检验失效 (复审 P3); OLS φ̂ 下偏 ≈ −(1+3φ)/T, clip ±0.99 在 T=240 实际难触发 |
| `critical_method` 语义 | 报告**配置**方法; 退化回退 (常数序列 / 全 NaN / T<5) 实际按渐近值/NaN 计算, 标签不变 (复审 P6) |
| 多重断点 | `detect_multiple` 走 BIC, 不使用 sup-F 临界值, 本版本不影响 |
| 真实数据 | 仅 4 因子验证; 更多因子/市场未逐一核对 |

---

## §9 交付物

- 生产: `modules/factor_health/__init__.py` (detector + diagnoser + 2 诊断键);
- 测试: `tests/unit/test_layer3_factor_health.py::TestAutocorrRobustSupF`;
- 版本: 6 锚点 3.5.3; 缓存代际 `v2.3.0-cache` 不变;
- 文档: RESEARCH / DESIGN (private) / 本文件 / 审计 / ADR-049 / CHANGELOG /
  README / README.en / ARCHITECTURE / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI。
