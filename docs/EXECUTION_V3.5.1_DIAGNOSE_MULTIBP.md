# EXECUTION — v3.5.1 多断点接入 `diagnose` 标签路径

> 步骤 5 产物 | 日期: 2026-11-17 | 依据: [DESIGN_V3.5.1](private/DESIGN_V3.5.1_DIAGNOSE_MULTIBP.md)
> 版本: **3.5.1** | 前置: v3.5.0 (`23e0f33`)

## §1 实施范围

| 文件 | 变更 | 预估 |
|------|------|------|
| `modules/factor_health/__init__.py` | `FactorHealthDiagnoser.__init__` +1 参数; `diagnose` +2 参数 + 分流; 新增 `_resolve_breakpoints` / `_multi_break_materiality`; `_classify_premium_health` 增加 confirmed 分支 | ~+110 行 |
| `tests/unit/test_layer3_factor_health.py` | 新增 `TestDiagnoseMultipleBreakpointMode` (F1-F9) | ~+150 行 |
| 6 处版本锚点 | 3.5.0 → 3.5.1 | 6 行 |
| `DECISIONS.md` | ADR-047 | ~+60 行 |
| `CHANGELOG.md` / `PROJECT_STATUS.md` / `DEV_PROGRESS.md` / `CODE_WIKI.md` | v3.5.1 条目 | 各 1 节 |
| `docs/research|private|audit` | 本套 spec 工件 | 3 文件 |

**不触碰**: `detect()` / `detect_multiple()` / `PremiumEstimator` / `_detect_decay` /
`_combine_label` 数值逻辑; 现有调用点; 缓存代际。

## §2 代码结构

```python
# __init__
def __init__(self, bandwidth=24, alpha=0.05, half_life_threshold=60,
             multi_break_shift_threshold: float = 1.0):
    ...
    self.multi_break_shift_threshold = float(multi_break_shift_threshold)

def diagnose(self, factor, forward_returns, return_type='unknown',
             breakpoint_mode='single', m_max=5):
    if breakpoint_mode not in ('single', 'multiple'):
        raise ValueError(...)
    lambda_hat = self.estimator.estimate(factor, forward_returns)
    beta_raw = getattr(self.estimator, '_beta_raw', lambda_hat)
    bp_view = self._resolve_breakpoints(beta_raw, breakpoint_mode, m_max)
    td_result = self._detect_decay(lambda_hat)
    premium_health = self._classify_premium_health(lambda_hat, bp_view, td_result)
    ...
    return {**原有键, **新增 10 键}
```

`_resolve_breakpoints(beta_raw, mode, m_max) -> Dict` 统一两种模式的断点视图:

- 始终调用 `detect(beta_raw)` (单断点, 既有的存在性检验);
- `mode='multiple'` 时额外调用 `detect_multiple(beta_raw, m_max)`;
- 计算 `breakpoint_confirmed` / `breakpoint_material` / `breakpoint_shift_ratio`;
- 输出 `n_breaks` / `breakpoints` / `segment_means` / `segment_bounds` /
  `pre_mean` / `post_mean` / `breakpoint_idx` / `chow_max_stat` / `best_bic_m` / `best_lwz_m`;
- G6 回退: confirmed 且 BIC m=0 → 用单断点构造分段。

`_multi_break_materiality(multi, beta_raw, threshold) -> (bool, float)`:

```
n = multi['n_breaks']; if n == 0: return False, nan
ssr = multi['ssr'][multi['best_bic_m']]; T = multi['n_valid']
sd_w = sqrt(max(ssr,0)/T); if sd_w <= 0: return False, nan
shift = max(|Δ segment_means|); ratio = shift/sd_w
return ratio >= threshold, ratio
```

`_classify_premium_health` 分支顺序 (G9):

```
confirmed = bp.get('breakpoint_confirmed', bp['has_breakpoint'])
if bp['has_breakpoint'] and confirmed: return 'ES+TD' if td else 'ES'
if td: return 'TD'
if bp['has_breakpoint']: return 'suspect'          # 未确认但材料
... 既有 FM t 路径不变
```

## §3 测试计划 (F1-F9)

| # | 用例 | 断言 |
|---|------|------|
| F1 | 默认 `'single'` 健康面板 | `breakpoint_mode='single'`; 旧键齐全; 新键存在; 标签 ∈ {pricing, suspect} |
| F2 | 强单断点面板 (T=200, N=150) `'multiple'` | confirmed=True; `n_breaks==1`; `breakpoints` 单元素且接近真断点; `premium_health ∈ {ES, ES+TD}`; `segment_means` 长度 2 |
| F3 | 双断点面板 (T=240, N=150, μ=[0.10,-0.10,0.10]) `'multiple'` | confirmed=True; `n_breaks==2`; `breakpoints==[80,160]`; `segment_means` 长度 3; `has_breakpoint=True` |
| F4 | 纯噪声面板 (T=120, N=80) `'multiple'` | `premium_health ∉ {ES, ES+TD}`; 若 `has_breakpoint` 则必为 `'suspect'` |
| F5 | 非法模式 | `pytest.raises(ValueError)` |
| F6 | T=20 短面板 `'multiple'` | 不抛异常; `n_breaks==0`; `breakpoints==[]`; `confirmed=False`; `has_breakpoint=False` |
| F7 | monkeypatch: confirmed=False + BIC n=1 + ratio=1.5 | `premium_health=='suspect'`; `has_breakpoint=True`; `breakpoint_material=True` |
| F8 | monkeypatch: confirmed=False + BIC n=1 + ratio=0.5 | `has_breakpoint=False`; `premium_health != 'suspect'` 由 FM 路径决定; `breakpoint_material=False` |
| F9 | monkeypatch: confirmed=True + BIC n=0 | G6 回退: `n_breaks==1`; `breakpoints==[单断点]`; `premium_health ∈ {ES, ES+TD}` |

复现探针依据: F3 的参数经探针 P-C 实测 (`sup-F F=80.3 > 8.8`, BIC `n=2`, `bp=[80,160]`,
`ratio=49.95`)。

## §4 验收命令

```powershell
# 1) 定向单元测试
python -m pytest tests/unit/test_layer3_factor_health.py -q

# 2) 版本统一 + 手工校验
python -m pytest tests/test_fix3_version_unification.py -q
python tests/test_backtest/verify_fix3_manual.py

# 3) 全量回归
python -m pytest tests -q
```

## §5 步骤 6 review (实施前静态核对 A1-A10)

| # | 检查 | 结论 |
|---|------|------|
| A1 | 默认路径是否真的零变更? | 是: `breakpoint_mode='single'` 只走原 `detect`; 决策树退化为 confirmed=has_bp, material=False; 仅新增键 |
| A2 | 新增键是否与旧键冲突? | 无: 10 个键均不在原 12 键中; `has_breakpoint` 语义在 single 下不变 |
| A3 | `breakpoint_idx` 在 multiple 下是否可为 None? | 无断点时为 None; confirmed 回退时取单断点; 多断点取首个 |
| A4 | NaN 索引映射是否一致? | 复用 `detect_multiple` 的原序列映射; 单断点用 `detect` 已有映射 |
| A5 | 未确认 + TD 是否误标 ES+TD? | 否: 分支先要求 confirmed 才允许 ES/ES+TD (G9) |
| A6 | 材料性阈值是否可能除零? | `sd_within<=0 → (False, nan)`; BIC flat 守卫已使 n=0 |
| A7 | 短样本是否走既有退化? | 是: `detect` T<30 与 `detect_multiple` T<30 均返回退化结果, 不抛异常 |
| A8 | 现有调用点是否兼容? | 是: 新参数均有默认值; 既有脚本不传新参数 |
| A9 | 是否引入新依赖/缓存变更? | 无; 仅 numpy |
| A10 | 标签语义是否有文档依据? | 是: `suspect` 的 borderline 语义在 `BreakpointDetector`/`FactorHealthDiagnoser` docstring 早有定义, 本次首次实现 |

## §6 实施记录

| 项 | 结果 |
|----|------|
| `modules/factor_health/__init__.py` | **+201 / −16 行** (net +185; `__init__` 阈值参数 / `diagnose` 分流 / `_resolve_breakpoints` / `_single_segment_view` / `_multi_break_materiality`); `detect` / `detect_multiple` / Estimator 零改动 |
| TDD Red | F1-F9 **9 failed** (`KeyError: breakpoint_mode` / `TypeError: unexpected keyword`) |
| TDD Green | **9 passed**; layer3 全文件 **40 passed** (31 + 9); 测试新增 **+207 行** |
| 默认路径零变更 | 20 个随机面板: `premium_health` 与旧分类器 **20/20 一致**, 0 mismatch; 旧键 (has_bp / bp_idx / chow / pre / post) 逐位一致 |
| 多断点不变量 | 20 个噪声面板: ES 必 confirmed、has_bp ⇔ confirmed∨material、n_breaks=len(breakpoints)、段均值数=n+1 → **0 违规** |
| 双断点实测 | T=240/N=150: `ES`, `n_breaks=2`, `[80,160]`, `best_bic_m=2`, **`best_lwz_m=3`** (再次印证 H5: LWZ 过选) |
| 版本锚点 | 6 处 → 3.5.1; 版本统一 **7 passed** + 手工 **5/5** |
| 实施期缺陷 | 无 (F9 初版断言写的是 mock 的 pre/post, 而实现按真实 beta 重算; 已修正断言, 非实现缺陷) |
| 复审修正 (H3) | 未确认且不材料分支的 pre/post 改回 NaN (旧键语义不变) + F8 断言; layer3 40 + 版本统一 7 重跑通过; 全量回归重跑见 §8 |
| 全量回归 | **1777 passed / 15 skipped / 0 failed** (1412.29s; = 基线 1768 + 9, 符合预期) |

## §7 版本与文档

- 版本 3.5.1: `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` /
  `tests/test_fix3_version_unification.py` / `tests/test_backtest/verify_fix3_manual.py`
- 文档: ADR-047 / CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI / 审计

---

## §8 异构独立复审 (2026-11-17)

5 视角 (计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性) + 攻击式探针 P1-P7
(临时脚本用后删除; 证据并入本文档与审计 Phase 8, 不新建文件)。

### 8.1 探针结果

| 探针 | 攻击面 | 结果 |
|------|--------|------|
| P1 | 默认 single 模式等价性 (60 随机面板, 5 类形状, T=60-240, N=40-150) | 标签 **60/60 一致**; 旧键 (has_bp / bp_idx / chow / pre / post / half_life / premium_*) 逐位一致; 新键自洽 |
| P2 | 纯噪声面板 FP (multiple, 100 次/配置, T=72/120/240, N=80) | ES 3%/4%/3% (= sup-F 名义 size); materiality 驱动 suspect ≈ 23%/6%/0%; confirmed 3%/4%/3% |
| P3 | 功效与定位 (单/双断点, 60 次/配置, N=120 高信噪比) | confirmed 与 ES **60/60**; 断点定位 med=0 max=0; BIC 过分段 (单断点面板选 2-3 段) 最高 37% |
| P4 | NaN 间隙 (白盒 wiring, 200 次/间隙长度 g=3/5/10) | 裸 BIC 64-70% → **has_bp 8.5-12%** (confirmed 3-6% ≈ size, material 6-7%) — 两级门控压制 5-6 倍 |
| P5 | 阈值敏感性 (面板级, θ=0.5..2.0) | 噪声 T=120 material@1.0=3% (@0.75=11%, @0.5=31%); 双断点 d=1.0 T=240 全阈值 100%; 默认 1.0 成立 |
| P6 | 真实 β_t (turnover_1m, T=72) | sup-F 不显著 (F=1.0 < 8.8) + BIC m=0 + material=False → **无告警**; G6 未触发; 与 v3.5.0 结论一致 |
| P7 | 契约边界 (22 键 / T=10 / 全 NaN / m_max=0 / 非法模式 / ratio 语义) | 全部正确; T=10 与全 NaN 不抛异常; m_max=0 + confirmed → G6 回退 n=1 |

### 8.2 发现与处置

| # | 发现 | 定性 | 处置 |
|---|------|------|------|
| H1 | 默认模式等价性扩样 20→60 面板 (5 类形状) | 确认 | — |
| H2 | 「纯噪声 ES 0%」表述错误: ES 率 = sup-F 名义 size (面板级 3-4%), 门控不改变 ES | **文档误述** | CHANGELOG 门控证据表更正 + 注释; RESEARCH §4 加注 |
| H3 | 「未确认且不材料」分支把 BIC 段均值回填 `mean_premium_pre_bp/post_bp` (has_breakpoint=False), 违反 DESIGN §4「保留键 (语义不变)」 | **代码缺陷** | 修正为 NaN (2 行) + F8 断言 (idx/pre/post); layer3 40 + 版本统一 7 重跑通过; 全量回归重跑 (结果回填于下) |
| H4 | 面板级 suspect 触发率与序列级不同 (24%/6%/0% vs 19.3%/4.0% @T=72/120) | 披露补充 | CHANGELOG 表双列标注 + ADR-047 复审小节 |
| H5 | NaN 间隙假断点被两级门控压制 5-6 倍 (64-70% → 8.5-12%) | 确认+量化 | CHANGELOG 局限 + ADR-047; 继承 v3.5.0 H7 的「先检查连续性」建议仍有效 |
| H6 | BIC 高信噪比过分段 (单断点面板选 2-3 段最高 37%), 定位无偏 (med=0) | 观察披露 | CHANGELOG 局限; 仅影响分段描述键, 不影响标签 |
| H7 | 真实数据无告警, 与 v3.5.0 一致 | 确认 | — |
| H8 | 输出契约 22 键完整, 边界全部正确 | 确认 | — |

### 8.3 复审结论

**PASS 维持** — 实现 6 项存活 (H1/H4-H8); 1 项文档误述更正 (H2, CHANGELOG + RESEARCH);
1 项代码缺陷修正 (H3, pre/post 语义, 2 行 + F8 断言); 面板级量化披露 (H4-H6)。
复审修正后 layer3 **40 passed** + 版本统一 **7 passed** 重跑通过;
全量回归重跑: **1777 passed / 15 skipped / 0 failed** (1134.45s, 2026-11-17, 最终代码)。
