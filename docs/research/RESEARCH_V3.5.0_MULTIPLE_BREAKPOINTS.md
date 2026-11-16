# RESEARCH — v3.5.0 多断点支持 (Bai-Perron) + Stata 对拍校验

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 — 大任务 (新算法模块 + 新 ADR-046) → 全 10 步
> **目标**: 为 `BreakpointDetector` 增加 Bai-Perron 多断点检测能力（全局最小 SSR + 信息准则
> 选段数），并以主控站 Stata 18.0 MP 为独立实现做**逐值对拍校验**。

---

## §1 目标与问题

| # | 问题 | 判定标准 |
|---|------|---------|
| Q1 | 多断点全局最小 SSR 的断点集与 Stata 独立实现是否一致? | 断点位置逐点相同; SSR 相对误差 < 1e-6 |
| Q2 | 单断点 sup-F 公式是否与 Stata `regress + test` 一致? | F 值相对误差 < 1e-8 (仅浮点往返) |
| Q3 | BIC / LWZ 选段数是否与 Stata 端计算结果一致? | 准则值相对误差 < 1e-8; 选出的 m 相同 |
| Q4 | 新增能力是否保持 v3.4.13 的 `detect()` 零改动? | 旧测试全绿; 逐位不变 |
| Q5 | 真实 A 股 β_t 序列上的断点是否可复现? | 与 Stata 对同一序列的结果一致 |

**非目标**: 不改 `detect()` 单断点默认路径；不替换 `diagnose()` 的断点消费逻辑（默认仍单断点）；
不做面板断点（`xtbreak` 场景）；不引入新依赖。

---

## §2 环境与数据事实 (2026-11-16 实测)

| # | 事实 | 证据 |
|---|------|------|
| F1 | Stata **18.0 MP (2-core, perpetual)** 安装于 `C:\Program Files\Stata18\StataMP-64.exe` | 批处理日志版本行 |
| F2 | 批处理可用: `Start-Process ... -ArgumentList "/e","do","x.do"` → 生成 `x.log`; 退出码 0 | 实测 4 次 |
| F3 | **该安装不支持** `regress y x, breakpoints(3)` → `option breakpoints() not allowed` **r(198)**; 加 `tsset` / `vce(ols)` 同样失败 | 实测 (probe/probe2/probe3) |
| F4 | **该安装无** `estat breakpoints` → **r(301)** (command not found) | 实测 probe3 |
| F5 | 无 `pystata` / `stata_setup` Python 集成包 | 实测 ImportError |
| F6 | **`regress y d1; test d1` 可精确复现本项目 Chow F 公式**: Python `31.1981209617` vs Stata `31.1981208732` (相对误差 **2.8e-9**); SSR 相对误差 5.8e-9 | 实测 chow.do |
| F7 | 现有 `BreakpointDetector.detect` 为**纯均值断点** (非回归斜率): `ssr_full = Σ(y-ȳ)²`, `F = (SSR_pooled-SSR_split)/(SSR_split/(T-2))` | [factor_health L296-L313](../../modules/factor_health/__init__.py#L296-L313) |
| F8 | 现有 `detect` 返回 6 键 (无断点) / 7 键 (有断点, 多 `breakpoint_idx`); `diagnose` 用 `.get('breakpoint_idx')` | L318-L333 / L538 |
| F9 | 现有 `_sup_f_critical_value` 用 Andrews (1993) Table 1 插值 (ε ∈ [0.05, 0.25]) | L355-L409 |
| F10 | 现有测试覆盖 T=200 单断点 / T<30 退化 (E1-E5), **无多断点用例** | tests/unit/test_layer3_factor_health.py |
| F11 | `FactorHealthDiagnoser.diagnose` 仅消费 `has_breakpoint` / `breakpoint_idx` / `chow_max_stat` | L519-L545 |
| F12 | 版本 6 锚点: `__init__.py` / `pyproject.toml` / `config_v2.py` / `reporting.py` / `test_fix3_version_unification.py` / `verify_fix3_manual.py` | 既有规范 |
| F13 | ADR 编号已用到 **045** → 本任务用 **ADR-046** | DECISIONS.md |
| F14 | 设计史: v3.3.0 §3.4 曾明确**不选** Bai-Perron (理由: BIC 过拟合 + 单断点够用) | [DESIGN_DISCUSSION_V3.3.0 §3.4](../private/DESIGN_DISCUSSION_V3.3.0.md) |

**关键推论**:
- Stata 侧**无官方 Bai-Perron 命令** (F3/F4) → 对拍必须用「**Stata 内置 `regress`+`test` (官方数值库)
  + Mata 独立实现全局搜索**」的组合 (F6 已验证单点公式一致);
- 现有 `detect` 是均值断点 → 多断点应保持同一模型族 (`y_t = μ_j + ε_t`), 与 Stata
  `regress y, breakpoints(m)` 的无协变量场景对应, 可直接逐值对拍;
- F14 的「不选 Bai-Perron」理由需在 ADR-046 中正面回应 (为何现在做: 用户显式需求 + 输出为
  **只读诊断**, 不改 `detect` 默认路径, 不改变 `diagnose` 标签)。

---

## §3 算法口径

### 3.1 模型

```
y_t = μ_j + ε_t,   t ∈ (T_{j-1}, T_j],   j = 1..m+1,   T_0 = 0, T_{m+1} = T
```

纯均值分段模型（与现有 `detect` 同一族）。`m` = 断点数，段数 = m+1。

### 3.2 估计: 全局最小 SSR (Bai-Perron 1998)

给定 `m` 与 trimming `ε`（最小段长 `h = max(5, int(εT))`），求解

```
SSR(m) = min_{T_1<...<T_m}  Σ_{j=1..m+1} SSR_j
s.t.  T_j - T_{j-1} ≥ h,  T_{m+1} - T_m ≥ h
```

**动态规划**（Bai & Perron 1998, §3.2）: 
`SSR(j,k)` = 用 j 个断点覆盖前 k 个观测的最小 SSR；
`SSR(j,k) = min_{h ≤ i ≤ k-h} [ SSR(j-1,i) + ssr(i+1,k) ]`，复杂度 O(m·T²)。

### 3.3 选段数

| 准则 | 公式 | 倾向 |
|------|------|------|
| BIC (Yao 1988) | `ln(SSR_m/T) + (m+1)·ln(T)/T` | 偏高估 |
| LWZ (Liu-Wu-Zidek 1997) | `ln(SSR_m/T) + (m+1)·c0·ln(T)^(2+δ0)/T`, `c0=0.1, δ0=0.1` | 偏低估 (Bai-Perron 2003 推荐) |
| sup-F(m) | 与 bootstrap 临界值比较（不硬编码未核实表值） | 显著性 |

`m_max` 默认 5（Bai-Perron 2003 常用上界），可由调用方覆盖。

### 3.4 与现有 `detect` 的关系

| 维度 | `detect` (保留) | `detect_multiple` (新增) |
|------|----------------|------------------------|
| 断点数 | 1 | 0..m_max |
| 搜索 | 逐点网格 | 动态规划全局最优 |
| 输出 | 6/7 键 | 新 dict (含 `breakpoints` / `ssr` / `bic` / `lwz` / `n_breaks`) |
| `diagnose` 消费 | ✅ 不变 | ❌ 默认不接入 |

---

## §4 Stata 对拍方案 (三级)

| 级 | 内容 | Stata 实现 | 判据 |
|----|------|-----------|------|
| L1 | 单点 Chow F / SSR / 段均值 | `regress y d1; test d1` (官方) | 相对误差 < 1e-8 |
| L2 | m=0/1/2 的**全局最小 SSR 与断点集** | Stata **循环 `regress y d1 [d2]`** 读 `e(rss)` 取最小 (全部走官方 OLS) | 断点逐点相同; SSR 相对误差 < 1e-6 |
| L3 | BIC / LWZ / 选出的 m | 用 Stata 侧 SSR(m) 按 §3.3 公式计算 (`display`) | 准则相对误差 < 1e-8; m 相同 |

**为什么用循环 `regress` 而非 Mata**: Stata 侧全程调用**官方 OLS 数值库**（`e(rss)`），
独立性最强；m≤2 的候选数在 T≤120 时约 2.3k，循环耗时 ~3s，可接受。Mata 自写 DP 只能证明
「转写无误」，而官方 `regress` 能同时锚定 SSR 数值与段均值。

**对拍样本**:
1. `syn0`: T=120, 纯噪声 (m*=0)
2. `syn1`: T=120, 断点 t=50, 段均值 0 → +0.8
3. `syn2`: T=120, 断点 t=40/80, 段均值 0 → +0.5 → -0.3
4. `real`: C 任务 `turnover_1m` 的 β_t 序列 (71 期, 来自真实 A 股面板)

**独立性边界 (必须声明)**: Stata 官方 `regress` 锚定的是**单点/给定断点组合的 SSR 与 F 公式**；
「全局搜索哪组断点 SSR 最小」在两侧都是搜索逻辑（Python DP vs Stata 循环穷举）。
因此 L2 证明的是「Python DP 找到的确实是全局最优 + SSR 计算与官方一致」，
对 m≥3 的 DP 正确性由 Python 内部穷举测试 (E5) 补足。

---

## §5 学术依据

| 主题 | 文献 |
|------|------|
| 多断点估计与检验 | Bai & Perron (1998), *Econometrica* 66(1):47-78 |
| 应用与准则推荐 | Bai & Perron (2003), *Journal of Applied Econometrics* 18(1):1-22 |
| 信息准则 | Yao (1988), *JRSS-B*; Liu, Wu & Zidek (1997), *Statistica Sinica* |
| 单断点 sup-F 与 trimming | Andrews (1993), *Econometrica* 61(4):821-856 |
| 序贯检验 | Bai (1997), *Review of Economics and Statistics* |

> **不硬编码 Bai-Perron 临界值表**: 本次未取得可逐一核实的表值副本，采用 bootstrap 临界值
> （可复现、无查表风险）；BIC/LWZ 作为主选段数依据。此取舍写入 ADR-046「替代方案」。

---

## §6 待验证假设与风险

| # | 假设/风险 | 验证 |
|---|----------|------|
| H1 | DP 与穷举一致 | 小 T (T=40, m≤2) 穷举对拍 |
| H2 | Mata 与 Python 实现独立 | 断点集逐点相同 |
| H3 | BIC 在 m=0 时退化正确 | 纯噪声样本选出 m=0 |
| H4 | trimming 边界 (h=max(5,int(εT))) 两侧一致 | T=40/120 各测 |
| H5 | 与现有 `detect` 单断点结果可比 | 同一序列的 m=1 断点位置一致 (允许 1 格差, 因 DP 与网格目标函数相同但搜索路径不同) |
| H6 | 真实数据 λ̂ 噪音导致多断点不稳定 | 报 BIC/LWZ + 各段均值; 不宣称因果 |
| H7 | Stata Mata 与 Stata 官方 regress 口径差 | L1 锚定官方; L2 仅比 SSR/断点 |

---

## §7 交付物

| # | 文件 | 内容 |
|---|------|------|
| 1 | `modules/factor_health/__init__.py` | 新增 `detect_multiple()` + DP/SSR/信息准则私有方法 (约 +180 行); `detect` 零改动 |
| 2 | `tests/unit/test_layer3_factor_health.py` | 新增 `TestBreakpointDetectorMultiple` (E1-E8) |
| 3 | `scripts/stata_breakpoint_crosscheck.py` + `scripts/stata/multiple_breakpoints.do` | 生成 4 个对拍样本 → 调 Stata → 解析 log → 逐值对比 |
| 4 | `docs/EXECUTION_V3.5.0_MULTIPLE_BREAKPOINTS.md` | 实施文档 (10 步中的步骤 5) |
| 5 | `docs/audit/CHECKLIST_V3.5.0_MULTIPLE_BREAKPOINTS.md` / `CONSISTENCY_REVIEW_V3.5.0_MULTIPLE_BREAKPOINTS.md` | 步骤 7-8 |
| 6 | `docs/audit/2026-11-16-v3.5.0-multiple-breakpoints-audit.md` | 步骤 10 |
| 7 | `DECISIONS.md` ADR-046 / CHANGELOG / PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | 发版同步 |

**版本**: 3.5.0（6 锚点）；缓存代际 `v2.3.0-cache` 不变（不触及管线中间产物）。
