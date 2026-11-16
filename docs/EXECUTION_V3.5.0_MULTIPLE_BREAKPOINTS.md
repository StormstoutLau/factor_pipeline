# EXECUTION — v3.5.0 多断点支持 (Bai-Perron) + Stata 对拍

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 — 大任务全 10 步
> **上游**: [RESEARCH](../research/RESEARCH_V3.5.0_MULTIPLE_BREAKPOINTS.md) /
> [DESIGN](private/DESIGN_V3.5.0_MULTIPLE_BREAKPOINTS.md) (G1-G14)
> **ADR**: ADR-046

---

## §1 实施范围

| 项 | 内容 |
|----|------|
| 修改 | `modules/factor_health/__init__.py` (+~190 行, `detect` 零改动) |
| 修改 | `tests/unit/test_layer3_factor_health.py` (+E1-E8) |
| 新增 | `scripts/stata_breakpoint_crosscheck.py` (~330 行) |
| 新增 | `docs/audit/CHECKLIST_V3.5.0_MULTIPLE_BREAKPOINTS.md` / `CONSISTENCY_REVIEW_...md` / 审计 |
| 修改 | 6 处版本锚点 → **3.5.0** |
| 修改 | DECISIONS (ADR-046) / CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI |
| 不动 | `detect` / `diagnose` / 管线 / 缓存代际 |

---

## §2 代码结构

```python
# ── 公开入口 ──────────────────────────────────────────────
def detect_multiple(self, lambda_hat: np.ndarray, m_max: int = None) -> Dict:
    """Bai-Perron 多断点: 全局最小 SSR + BIC/LWZ 选段数 (只读诊断)."""
    y_all = np.asarray(lambda_hat, dtype=float).ravel()
    valid = ~np.isnan(y_all)
    y = y_all[valid]
    T = len(y)
    m_max = 5 if m_max is None else max(int(m_max), 0)

    if T < 30:
        return self._multiple_no_breakpoint_result(T, m_max)

    h = max(5, int(T * self.min_segment))
    m_cap = min(m_max, T // h - 1)
    if m_cap < 0:
        return self._multiple_no_breakpoint_result(T, m_max)

    cs, cs2 = self._ssr_prefix(y)
    ssr_mat = self._build_ssr_matrix(cs, cs2, T, h)

    ssr_by_m, brk_by_m = {0: float(ssr_mat[0, T])}, {0: []}
    for k in range(1, m_cap + 1):
        v, b = self._dp_breaks(ssr_mat, T, h, k)
        ssr_by_m[k], brk_by_m[k] = v, b

    # 常数序列守卫: SSR≈0 → 准则无定义
    flat = ssr_by_m[0] < 1e-12
    bic = {k: (float('nan') if flat else self._bic(v, T, k)) for k, v in ssr_by_m.items()}
    lwz = {k: (float('nan') if flat else self._lwz(v, T, k)) for k, v in ssr_by_m.items()}
    best_bic = 0 if flat else min(bic, key=lambda k: bic[k])
    best_lwz = 0 if flat else min(lwz, key=lambda k: lwz[k])

    idx_map = np.where(valid)[0]
    breaks = brk_by_m[best_bic]
    bounds = [0] + breaks + [T]
    seg_means = [float(np.mean(y[a:b])) for a, b in zip(bounds[:-1], bounds[1:])]
    seg_bounds = [(int(idx_map[a]), int(idx_map[b - 1]) + 1)
                  for a, b in zip(bounds[:-1], bounds[1:])]
    return {
        'has_breakpoint': bool(best_bic > 0),
        'n_breaks': int(best_bic),
        'breakpoints': [int(idx_map[b]) for b in breaks],
        'segment_means': seg_means,
        'segment_bounds': seg_bounds,
        'ssr': ssr_by_m, 'bic': bic, 'lwz': lwz,
        'best_bic_m': int(best_bic), 'best_lwz_m': int(best_lwz),
        'trimming': int(h), 'm_max': int(m_max), 'n_valid': int(T),
    }

# ── 私有 ──────────────────────────────────────────────────
def _ssr_prefix(y) -> (cs, cs2)          # 长度 T+1, 首元素 0
def _build_ssr_matrix(cs, cs2, T, h)     # (T+1, T+1), 长度<h 为 inf, 负数截 0
def _dp_breaks(ssr_mat, T, h, k)         # 返回 (min_ssr, breaks[1-based 段结束])
def _bic(ssr, T, k)                      # ln(ssr/T) + (k+1)*ln(T)/T
def _lwz(ssr, T, k)                      # ... + (k+1)*0.1*ln(T)^2.1/T
def _multiple_no_breakpoint_result(T, m_max)  # 12 键退化
```

### 2.1 DP 递推与回溯

```
cost[0, j] = ssr_mat[0, j]
cost[k, j] = min_{i ∈ [k*h, j-h]} ( cost[k-1, i] + ssr_mat[i, j] )
arg[k, j]  = argmin 的 i
回溯: j = T; for k down to 1: i = arg[k, j]; breaks.append(i); j = i
```

### 2.2 索引语义

- `_dp_breaks` 内的断点为 **1-based 段结束位置**（`y[a:b]` 的 `b`）。
- 对外 `breakpoints` 映射到**原序列索引**（`idx_map[b]`），与 `detect` 的 `breakpoint_idx` 同义。
- `segment_bounds` 为原序列半开区间 `[start, end)`。

---

## §3 测试计划 (E1-E8)

| # | 测试 | 断言 |
|---|------|------|
| E1 | 单断点 T=120 (bp=50) | `n_breaks == 1`; `breakpoints[0]` 距 50 ≤ 3 |
| E2 | 两断点 T=120 (bp=40/80) | `n_breaks == 2`; 两个断点各距真值 ≤ 4 |
| E3 | 纯噪声 T=120 | `n_breaks == 0`; `has_breakpoint is False` |
| E4 | 准则一致性 | `ssr` 随 m 单调非增; `bic/lwz` 字典覆盖 m=0..m_cap; `best_*_m` 在范围内 |
| E5 | DP vs 穷举 (T=40, m≤2) | 全局 SSR 与断点集**逐位相同** |
| E6 | T<30 退化 | T=20: `n_breaks==0`、`breakpoints==[]`、`segment_means==[nan]`、不抛异常 |
| E7 | NaN 映射 | 60 个含 10 NaN (有效 50): 断点索引为**原序列**位置; `n_valid==50` |
| E8 | 与 `detect` 可比 | 同序列 m=1: 两者断点差 ≤ 1; `ssr[1]` 与 `detect` 的 SSR_split 相对误差 < 1e-8 |

---

## §4 Stata 对拍脚本

```
scripts/stata_breakpoint_crosscheck.py
  --stata-path <default: C:\Program Files\Stata18\StataMP-64.exe>
  --data-root / --converted-root
  --skip-real          # 只跑 3 个合成样本
  流程:
    1. build_samples()  -> syn0/syn1/syn2 (numpy) + real (PremiumEstimator β_t)
    2. write_csv()      -> %TEMP%/stata_bp_crosscheck/*.csv
    3. write_do()       -> 逐样本 .do (L1 单点 F / L2 循环 regress / L3 BIC·LWZ)
    4. run_stata()      -> Start-Process /e do; 读 .log
    5. parse_log()      -> KEY= value
    6. compare()        -> 断言并打印 PASS/FAIL 表
```

Stata 侧 `.do` 关键片段（由 Python 生成，m ≤ 2）：

```stata
import delimited "syn2.csv", clear
gen byte d1 = 0
gen byte d2 = 0
local bestSSR = 1e300
local T = _N
forvalues b1 = 18/68 {
    quietly replace d1 = t > `b1'
    forvalues b2 = `=`b1'+18'/102 {
        quietly replace d2 = t > `b2'
        quietly regress y d1 d2
        if e(rss) < `bestSSR' {
            local bestSSR = e(rss)
            local bestB1 = `b1'
            local bestB2 = `b2'
        }
    }
}
display "L2_SSR_2=" %20.12f `bestSSR'
display "L2_BRK_2=" `bestB1' "," `bestB2'
forvalues m = 0/2 { ... display "BIC_`m'=" ... }
```

---

## §5 验收命令

```powershell
# 1) 单元测试
python -m pytest tests/unit/test_layer3_factor_health.py -q

# 2) Stata 对拍 (含真实数据)
python scripts/stata_breakpoint_crosscheck.py

# 3) 版本统一 + 手工校验
python -m pytest tests/test_fix3_version_unification.py -q
python tests/test_backtest/verify_fix3_manual.py

# 4) 全量回归
python -m pytest -q
```

**判据**: E1-E8 全绿; 对拍 L1-L3 全 PASS; 版本 7 passed + 手工 6/6; 全量 = 1760 + 新增。

---

## §6 步骤 6 review (实施前静态核对)

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | G1-G14 与 §2 代码结构一一对应 | ✅ |
| A2 | `detect` / `diagnose` 未被修改 | ✅ 仅新增方法 |
| A3 | DP 可行域 `j ∈ [(k+1)h, T]` 与 `i ∈ [kh, j-h]` 正确 | ✅ 与 Bai-Perron 1998 §3.2 一致 |
| A4 | 断点索引映射 (valid → 原序列) 与 `detect` 同义 | ✅ `np.where(valid)[0]` |
| A5 | `ssr_mat` 长度 < h 置 inf, 避免非法段 | ✅ |
| A6 | 常数序列 / SSR=0 有显式守卫 | ✅ `flat` 分支 |
| A7 | BIC/LWZ 参数个数 = k+1 | ✅ 每段 1 均值 |
| A8 | Stata 侧全部走官方 `regress` | ✅ 无 Mata 自写 SSR |
| A9 | 核实的 Stata 事实 (F3/F4: 无官方 breakpoints) 已写入文档 | ✅ RESEARCH §2 |
| A10 | 版本 3.5.0 六锚点 + 缓存代际不变 | ✅ |

**review 结论**: PASS (实施前)。

---

## §7 实施记录

| 项 | 结果 |
|----|------|
| `factor_health/__init__.py` | **+176 行** (`detect_multiple` + 6 私有方法); `detect` / `diagnose` 未触碰 |
| TDD Red | 8 failed (`AttributeError`), 23 deselected |
| TDD Green (首轮) | 6 passed / 2 failed (E2 统计精度、E7 索引期望+bic) |
| TDD Green (修正测试) | **8 passed**; layer3 全文件 **31 passed** |
| 版本锚点 | 6 处 → 3.5.0; 版本统一 **7 passed** + 手工 **5/5** |
| Stata 对拍 (合成) | **35 项 PASS / 0 FAIL** (syn0/syn1/syn2) |
| Stata 对拍 (含真实 β_t) | **46 项 PASS / 0 FAIL**; real T=72, BIC/LWZ 均选 **m=0 (无断点)**; [19, 37] 为强制 m=2 的最优位置 (异构复审 H4 已更正初版「检出 2 断点」误读) |
| 对拍误差 | 断点集逐点相同; SSR rel ≤ 8.5e-9; BIC/LWZ abs ≤ 8.5e-9; L1_F rel 1.06e-8 |
| 实施期缺陷 | D1 解析正则跨行 / D2-D3 判据 (相对→绝对) / D4-D5 测试自身 / D11 `m_max` 输出改生效上界 → 全部修复 |
| 新增脚本 | `scripts/stata_breakpoint_crosscheck.py` (**384 行**) |
| 全量回归 | **1768 passed / 15 skipped / 0 failed** (1131.57s; = 基线 1760 + 8, 符合预期) |

### 7.1 真实数据结果 (描述性)

`turnover_1m` 的 β_t (T=72, 2020-02 → 2025-12) BIC/LWZ 均选 **m=0 即无断点**
(BIC_0=-8.207 < BIC_1=-8.162 < BIC_2=-8.118); [19, 37] 是**强制 m=2** 时的
最优两断点位置 (L2 对拍项), 并非「检出」的断点。异构复审 H4 已更正初版
「BIC/LWZ 均选 m=2 → 检出 2 断点 [19,37]」的文档误读 (实现正确, 无代码缺陷;
crosscheck 脚本 L2 输出的强制位置被误读为选定结果, 原日期对应描述随之删除)。
两侧实现逐点一致; 多断点 **未接入** `diagnose` 标签路径 (G10)。

---

## §8 异构独立复审 (2026-11-17)

5 视角 (计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性) + 攻击式探针 P1-P8
(临时脚本用后删除; 证据并入本文档与审计 Phase 8, 不新建文件)。

### 8.1 探针结果

| 探针 | 攻击面 | 结果 |
|------|--------|------|
| P1 | DP vs `detect` SSR 语义一致性 (边界 bp=h/T-h) | rel ≤ 5.4e-16, 逐位一致 |
| P2 | 常数/近常数序列 flat 守卫 (原无测试覆盖的缺口) | 生效 (bic/lwz 全 NaN, best=0) |
| P3 | T=29..36 边界 + m_max=0/-3 退化 | 正确, 13 键完整 |
| P4 | 蒙特卡洛假阳性 (200 次/配置, 纯噪声) | BIC 44% (T=72) / 36% (T=120); LWZ 89% / 75% → H5/H6 |
| P5 | NaN 间隙 (两段同分布被 NaN 隔开) | 54% 假断点 → H7 |
| P6 | `detect` vs `detect_multiple` 单断点一致性 | 20/20 (最大差 0) |
| P7 | list / pd.Series / float32 输入 | 兼容 |
| P8 | 真实 β_t 复跑 | n_breaks=0 → H4 |

### 8.2 发现与处置

| # | 发现 | 定性 | 处置 |
|---|------|------|------|
| H1 | DP 与 detect 的 SSR 语义一致 | 确认 | — |
| H2 | 常数序列 flat 守卫生效但无测试覆盖 | 确认+补缺 | 探针证据存档 (EXECUTION §8.1 + 审计 Phase 8) |
| H3 | 边界/T<30/m_max 退化正确 | 确认 | — |
| H4 | 真实数据「检出 2 断点 [19,37]」为误读: 实际 BIC/LWZ 均选 m=0 (BIC_0=-8.207 最小); [19,37] 是强制 m=2 的位置 | **文档误读** (实现正确, 无代码缺陷) | 全量更正: CHANGELOG / ADR-046 / 本文 §7+§7.1 / 审计 D10+Phase 7 / PROJECT_STATUS / CODE_WIKI |
| H5 | LWZ (c0=0.1) 假阳性 89% (T=72) / 75% (T=120), 与「保守」预期相反 (惩罚 0.0287 < BIC 0.0594) | 方法学局限 | 降级「仅对照, 不可单独引用」; 披露于 ADR-046 后果 + CHANGELOG 遗留 |
| H6 | BIC 假阳性 44% (T=72) / 36% (T=120) | 方法学局限 | 短样本 n_breaks>0 不可直接解读; 披露于 ADR-046 + CHANGELOG |
| H7 | NaN 间隙: 同分布两段被 NaN 隔开 → 54% 假断点 | 语义风险 | 披露于 CHANGELOG 遗留段; 断续 β_t 需先检查连续性 |
| H8 | detect 与 detect_multiple 一致 20/20; 输入类型兼容 | 确认 | — |

### 8.3 复审结论

**PASS 维持** — 实现与 Stata 对拍全部存活 (P1 语义一致 / P2-P3 守卫与退化 / P6 一致 20/20 / P7 兼容);
1 项文档误读全量更正 (H4, 无代码缺陷); 2 项方法学局限披露 (H5/H6);
1 项语义风险披露 (H7)。
