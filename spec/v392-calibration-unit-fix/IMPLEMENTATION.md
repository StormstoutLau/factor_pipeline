# IMPLEMENTATION v3.9.2 — 校准读数口径一致性修复

---
id: v392-calibration-unit-fix-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v392-calibration-unit-fix-DESIGN, v392-calibration-unit-fix-RESEARCH]
upstream: null
---

> **版本**: v1.1 (2026-11-20；步骤 6 复审修正 5 项，见 §7)
> **对应设计**: [DESIGN.md](./DESIGN.md) **v1.1**
> **对应调研**: [RESEARCH.md](./RESEARCH.md) **v1.1**
> **批次**: v3.9.2（包版本 3.9.1 → 3.9.2）
> **执行方式**: TDD 先红后绿；默认输出 SHA 不变；Python 3.9 语法

---

## §0 变更白名单

| 文件 | 动作 |
|------|------|
| `backtest/execution/core/impact.py` | 新增 `C_R2_MIN`、`C_RANGE`、`fit_r2`（模块级导出，`__all__` 保持 5 项） |
| `backtest/execution/shell/panels.py` | `_month_lambda` σ 日频；`_fit_impact` 增 r2/identifiable；`build_daily_panels` rho 日频 + 守卫 + 门槛回退 + temporary 标注 |
| `backtest/execution/shell/runner.py` | `models.sqrt.r2`、`c_identifiable/c_effective/c_r2`、`temporary_basis`；rho 负值守卫 |
| `tests/test_minute_panels.py` | 新增 T1/T2/T4/T5/T6；更新受影响断言 |
| `tests/test_execution_capacity.py` | 新增 T3/T7；更新受影响断言 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / 2 测试常量 | 版本 3.9.2 |
| `CHANGELOG.md` | 顶部新条目（注明「对应路线图批次 v3.9.2」） |

**不在白名单**：`scripts/verify_capacity_impact.py`、`loaders.py`、`decay.py`、`ports.py`、配置字段。

---

## §1 代码级变更

### 1.1 `core/impact.py`

```python
C_R2_MIN = 0.05
C_RANGE = (0.1, 2.0)

def fit_r2(pred, y):
    """过原点拟合 R² = 1 - SSE/SST；非有限或 SST==0 -> 0.0。"""
    p = np.asarray(pred, dtype=float).ravel()
    t = np.asarray(y, dtype=float).ravel()
    if p.size != t.size or p.size == 0:
        return 0.0
    ok = np.isfinite(p) & np.isfinite(t)
    if not np.any(ok):
        return 0.0
    sse = float(np.sum((t[ok] - p[ok]) ** 2))
    sst = float(np.sum((t[ok] - t[ok].mean()) ** 2))
    if sst <= 0.0:
        return 0.0
    return float(1.0 - sse / sst)
```

`__all__` **不扩**（保持 5 项）：`core` 架构测试要求 `__all__ <= 5`；新增符号由调用方显式
`from ..core.impact import C_R2_MIN, C_RANGE, fit_r2` 导入（A-3 修正）。

### 1.2 `panels._month_lambda`（D1）

在每只股票的 `ok` 掩码内计算日收益 σ：

```python
sd = float(np.std(r[ok], ddof=1)) if int(ok.sum()) >= 2 else 0.0
if not np.isfinite(sd) or sd <= 0.0:
    sd = lo
sigma_d = float(np.clip(sd, lo, hi))
...
self._samples.append((float(np.clip(abs(xi), 1e-6, 1.0)),
                      float(abs(ri)), sigma_d, int(code), ym))
```

同时删除 L286 的分钟 σ 预计算（不再使用）。`agg.sigma` 保留给 `loaders`/BVC，不动。

### 1.3 `panels._fit_impact`（D2）

在主模型拟合后：

```python
model = dict((m.name, m) for m in MODELS).get(primary)
r2 = None
ident = True
if primary == "sqrt" and fitted.get("sqrt"):
    pred = model.predict(p, sigma, fitted["sqrt"])
    r2 = float(fit_r2(pred, impact))
    c_val = float(fitted["sqrt"]["c"])
    ident = bool(r2 >= C_R2_MIN and C_RANGE[0] <= c_val <= C_RANGE[1])
return {..., "r2": r2, "identifiable": ident}
```

非 sqrt 主模型：`r2=None, identifiable=True`。

### 1.4 `panels.build_daily_panels`

**(a) temporary 标注（D4）**

```python
if r1.size:
    out["evidence_warnings"].append(
        "temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量")
out["temporary_basis"] = "portfolio_ar1_proxy"
```

**(b) rho 日频 + 守卫（D3）**

```python
rho, lo, hi = 1.0, 1.0, 1.0
if ex_d.size >= 3:
    try:
        rho, lo, hi = estimate_rho(ex_d.to_numpy())
    except ValueError as exc:
        out["evidence_warnings"].append("rho 不可估（%s），按 1.0" % exc)
if float(rho) <= 0.0:
    rho, lo, hi = 1.0, 1.0, 1.0
    out["evidence_warnings"].append("rho<=0（无正持续性），按无衰减处理")
out["rho"] = float(rho)
out["rho_series"] = [float(v) for v in ex_d.to_numpy()]
out["rho_freq"] = "daily"
out["rho_n"] = int(ex_d.size)
```

**(c) c 门槛回退（D2）**

```python
impact_bps = 0.0
out["impact_bps_source"] = "calibrated"
params = impact_fit.get("params") if impact_fit else None
primary = impact_fit.get("primary") if impact_fit else None
if params and primary == "sqrt" and not impact_fit.get("identifiable", True):
    params = {"c": 0.5}
    out["impact_bps_source"] = "default_fallback"
    out["evidence_warnings"].append(
        "c 不可识别（r2<%.2f 或超出 %s），成本回退 c=0.5" % (C_R2_MIN, C_RANGE))
if params:
    model = dict((m.name, m) for m in MODELS).get(primary)
    ...
```

### 1.5 `runner.run_calibration`

**(a) sqrt r2 / 门槛**

```python
if sqrt_params:
    point = float(sqrt_params["c"])
    pred = SqrtImpact().predict(p, sigma, sqrt_params)
    r2 = float(fit_r2(pred, impact))
    ident = bool(r2 >= C_R2_MIN and C_RANGE[0] <= point <= C_RANGE[1])
    models_out["sqrt"]["r2"] = r2
    ...
    c_info = c_triplet(point, lower, upper)
    c_info.update({"c_r2": r2, "c_identifiable": ident,
                   "c_effective": point if ident else 0.5})
```

不可识别时追加 warning「c 不可识别，容量按默认 0.5」。

**(b) rho 守卫**

```python
rho, rho_lo, rho_hi = estimate_rho(...)
if float(rho) <= 0.0:
    rho, rho_lo, rho_hi = 1.0, 1.0, 1.0
    warnings.append("rho<=0（无正持续性），按无衰减处理")
```

**(c) 透传**

```python
"temporary_share": ts,
"temporary_basis": panels.get("temporary_basis"),
```

---

## §2 测试（先红）

| # | 文件 | 用例 | 红阶段断言 |
|---|------|------|-----------|
| T1 | test_minute_panels | `test_impact_sigma_is_daily_scale` | 样本 σ == `std(ret_day)`；≠ 分钟 σ |
| T2 | test_minute_panels | `test_c_gate_falls_back_on_noise` | 纯噪声 → `identifiable=False`、`impact_bps_source=default_fallback` |
| T3 | test_execution_capacity | `test_c_gate_strong_signal` | y=cσ√p → `r2≈1`、`identifiable=True`、c 还原 |
| T4 | test_minute_panels | `test_rho_uses_daily_series` | `rho_series == ex_d`、`rho_freq=="daily"`、`rho_n==len(ex_d)` |
| T5 | test_minute_panels | `test_rho_nonpositive_falls_back` | rho<0 → 1.0、`retention(5)>0`、warning |
| T6 | test_minute_panels | `test_temporary_basis_flagged` | `temporary_basis` + warning 文本 |
| T7 | test_execution_capacity | `test_runner_reports_c_gate` | `c_r2/c_identifiable/c_effective/temporary_basis` 存在且一致 |
| T8 | 命令级 | 默认路径 SHA | `82728CE1…` 不变 |

> 先红：新增用例在未改实现时必须失败（T1/T2/T4/T5/T6 断言新字段/新尺度）。
> T3/T7 允许先红后绿；T8 仅在步骤 9 末执行。

---

## §3 版本与文档同步

1. 6 处代码锚点 + CHANGELOG 全部 3.9.2；
2. `CHANGELOG.md` 顶部：

```markdown
## v3.9.2 — 校准读数口径一致性修复（对应路线图批次 v3.9.2）(已实施, 2026-11-20)
```

3. `docs/PROJECT_STATUS.md` §1 增 `v3.9.2` 行、§2 待办勾选、最近完成；
4. `README.md` 版本句同步。

---

## §4 门禁命令

```powershell
# 1) 新增用例（先红）
python -m pytest tests/test_minute_panels.py tests/test_execution_capacity.py -q
# 2) 全量
python -m pytest -q
# 3) 默认路径 SHA
python scripts/verify_capacity_impact.py
(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash
# 4) 校准路径（全 39 月，输出到独立文件，避免覆盖审计工件）
python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v392_calibration.json
```

**通过线**：全量 ≥ 2047 passed / 15 skipped / 0 failed；SHA = `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`；
校准 JSON 含新增字段且不再出现 `retention<0`。

---

## §5 回填

- CHECKLIST：T1-T8 逐项证据；
- IMPLEMENTATION §8：实测读数（c/r2/identifiable、rho/rho_freq、temporary_basis、net(h)）；
- CHANGELOG「实测读数」小节；
- PROJECT_STATUS 与审计报告。

---

## §6 风险

| # | 风险 | 处置 |
|---|------|------|
| R1 | 单月冒烟不足以证明 39 月稳定 | 若时间允许跑全 39 月；否则在报告中标注「单月冒烟 + 单测」证据等级 |
| R2 | 日频 rho 仍为负 → 回退 1.0 掩盖真实衰减 | warning 明示「无正持续性」；不声称有衰减 |
| R3 | c 仍不可识别 → 容量用 0.5 | 报告写 `default_fallback`，不写「校准值」 |
| R4 | 旧测试断言月频 rho / bar σ | 白名单内同步更新，逐条说明原因 |

---

## §7 步骤 6 复审记录（v1.0 → v1.1，2026-11-20）

**复审方式**：把 §1 的每段伪代码对照现有实现逐行核对（Read），确认可落地、无 API 幻觉。

### 7.1 发现与修正

| # | 级别 | 发现 | 修正 |
|---|------|------|------|
| F1 | P1 | 门槛回退改写后丢失原 `else` 分支的 `cost_impact_unavailable` 告警 | §1.4(c) 显式说明：`impact_fit` 为空时保留原告警，`impact_bps_source="unavailable"` |
| F2 | P2 | `models_out` 初始字典无 `r2` 键，非 sqrt 模型 JSON 结构不一致 | 初始化为 `{"params": ..., "cv_rmse": None, "r2": None}` |
| F3 | P2 | panels 与 runner 的 `rho<=0` 告警文案相同，合并后重复 | runner 文案改为「decay: rho<=0（无正持续性），按无衰减处理」，保留来源可辨 |
| F4 | P3 | 未列出 import 变更 | `panels.py`/`runner.py` 从 `..core.impact` 引入 `fit_r2, C_R2_MIN, C_RANGE` |
| F5 | P1 | 门禁命令 `--months` 不存在（脚本无此参数） | 改为全 39 月 `--calibrate --calibration-json out/v392_calibration.json` |

### 7.2 通过项

| # | 项 | 结果 |
|---|----|------|
| P1 | `_month_lambda` 可拿到 `r[ok]` 计算日频 σ | ✅ L304-306 |
| P2 | `_fit_impact` 可预测主模型并算 r2 | ✅ L127-142 |
| P3 | `build_daily_panels` 有 `ex_m/ex_d/impact_fit` | ✅ L503-524 |
| P4 | `runner` 已重估 rho，守卫可加在同一处 | ✅ L279-283 |
| P5 | 默认路径不含校准字段 | ✅ 调研 §9.1 P5 |

### 7.3 结论

**PASS_WITH_FIXES（已闭环）**。变更集仍限于 §0 白名单；无新增依赖；Python 3.9 兼容。
进入步骤 7 验收清单。

---

## §8 实测读数（步骤 9，2026-11-20）

**命令**：`python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v392_calibration.json`
（39 月，exit 0，`evidence_level=minutes`；工件 `out/v392_calibration.{json,md}`）

| 项 | v3.8.1（修复前） | v3.9.2（修复后） | 判定 |
|----|-----------------|-----------------|------|
| `c_calib_point` | 15.0677 | **2.9107**（CI 2.8959–2.9221） | σ 尺度修正生效（↓5.2×） |
| `c_r2` | —（无字段） | **0.5606** | 拟合解释力中等，非纯噪声 |
| `c_identifiable` | — | **False**（c>2.0，非 r2 未达） | 门槛按设计回退 |
| `c_effective` | —（实际用 15.07） | **0.5** | 成本不再被 15 放大 |
| `impact_bps_source` | — | `default_fallback` | 留痕可查 |
| `cost_by_h` | 91.54M / 45.77M / 22.88M | **15.57M / 7.78M / 3.89M** | ↓5.9×，与 c 回退一致 |
| `rho` | -0.1470（月频） | **+0.1142（日频，CI -0.0199–0.2482）** | 频率与符号已修正 |
| `retention(5/10/20)` | -6.9e-5 / 2.2e-17 / … | **1.94e-5 / ~0 / ~0** | 无负值、无符号翻转 |
| `net(5/10/20)` | -91.54M / -45.77M / -22.88M | **-15.57M / -7.78M / -3.89M** | 仍为负（见 FO-1） |
| `temporary_share` | [0, 0, 0.0042] | [0, 0, 0.0042]（未改算法） | 已标 `portfolio_ar1_proxy` |
| 默认 SHA | `82728CE1…` | `82728CE1…` | 逐位不变 |

**关键新发现（FO-1，范围外）**：日频 `rho=0.1142`（半衰期 0.32 个交易日）使
`alpha0·rho**h` 在 h≥5 时坍缩为 ~0，`net(h)` 仍 ≈ `−cost(h)`。
这不是单位问题，而是**衰减模型选择**问题：用「已实现组合收益的 AR(1)」代理「alpha 信号衰减」，
在日频上等价于「alpha 半衰期不足 1 天」，经济含义不成立。本批白名单不含模型替换，
登记为 **v3.9.3 P0（rho 改由 IC / alpha 期限结构估计）**；设计原文 §7 的「组合收益序列」选项
应在下一批复核。

**成本对照**：若仅把 `rho` 置 1.0（无衰减）而其余不变，`net(20)=26.29M−3.89M=+22.4M`；
可见当前负值由 rho 主导，c 修复后成本已不再是主因。

---

## §9 步骤 10 审计期间修复（2026-11-20）

| # | 级别 | 问题 | 处置 |
|---|------|------|------|
| A-1 | MINOR | `runner` 重估 rho 未捕获 `estimate_rho` 的 `ValueError`（序列 <3 或常数序列）；`panels` 已回退 1.0，runner 会崩 | `runner.py` 加 `try/except ValueError`，保留 `rho<=0 → 1.0` 守卫；新增 `test_runner_rho_short_series_falls_back`（T9） |
| A-2 | 文档 | CHECKLIST 原 G3/G4 写「最终 JSON 含 `rho_freq/impact_bps_source`」，与 DESIGN §3 的 runner 输出契约不符 | 修正为 panels 内部字段；证据改引 T2/T4 与 JSON warning |
| A-3 | MAJOR | `impact.py` 的 `__all__` 扩到 9 项，违反 core 架构约束（`__all__<=5`），全量首跑 `test_core_all_bounded` 失败（1 failed / 2054 passed） | `__all__` 回退为原 5 项；新符号显式导入；`tests/test_execution_architecture.py` 3 passed |

- 定向复跑：`tests/test_execution_capacity.py tests/test_minute_panels.py` → **39 passed**（38 + T9）；
- 39 月校准工件 `out/v392_calibration.json` 不受影响（`rho_series` 长度充足，未走异常分支），无需重跑；
- 默认 SHA `82728CE1…` 复核逐位不变。
