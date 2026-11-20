# v3.9.2 校准读数口径一致性修复 — 步骤 10 审计复审报告

---
id: v392-calibration-unit-fix-AUDIT
type: design
version: 1.0
status: verified
date: 2026-11-20
depends: [v392-calibration-unit-fix-CHECKLIST, v392-calibration-unit-fix-IMPLEMENTATION, v392-calibration-unit-fix-DESIGN]
upstream: null
---

> **审计日期**: 2026-11-20　**审计方法**: audit-driven-development（异构复审，RULE-5）
> **审计对象**: 批次 v3.9.2（包版本 **3.9.2**）— c/rho/temporary 三项校准读数口径修复
> **对应清单**: [CHECKLIST.md](./CHECKLIST.md) **v1.1**（模板化后 42 项）
> **对应实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.1**
> **对应设计**: [DESIGN.md](./DESIGN.md) v1.1 / [RESEARCH.md](./RESEARCH.md) v1.1 / [CONSISTENCY_REVIEW.md](./CONSISTENCY_REVIEW.md) v1.1
> **结论**: **PASS（本批范围）** — CRITICAL 0 / MAJOR 1（A-3，已当场修复）/ MINOR 1（A-1，已当场修复）/ 文档勘误 1（A-2，已修正）/ 范围外失败 1（G5 → FO-1，移交 v3.9.3 P0）

---

## §1 审计范围与方法

**异构性声明（RULE-5）**：步骤 9 实施与步骤 10 审计为不同会话；审计不复用实施会话的判断，
结论只由独立复跑（E1）、落盘工件（E2）、代码锚点（E3）、文档比对（E4）重建，E5（推测）不单独支撑「通过」。

**范围**：

1. 5 文件白名单（`core/impact.py`、`shell/panels.py`、`shell/runner.py`、`tests/test_minute_panels.py`、`tests/test_execution_capacity.py`）+ 6 处版本锚点 + 3 份文档（CHANGELOG / PROJECT_STATUS / README）；
2. CHECKLIST v1.1 共 42 项逐行复核（RULE-2：汇总只来自逐行计数；原 41 项 + OS 兼容性 1 项）；
3. 39 月校准工件 `out/v392_calibration.{json,md}` 的字段与数值复算；
4. 默认路径隔离与 SHA 冻结。

**探针矩阵（4 视角）**：P1 数学/口径正确性、P2 确定性复现、P3 边界与降级、P4 结论有效性与文档合规。

---

## §2 门禁独立复验

| 门禁 | 审计独立读数 | 判定 |
|------|-------------|------|
| G1 默认 SHA | `(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash` = `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` | 通过（逐位一致） |
| G2 retention 非负 | `retention={1:0.11417, 5:1.9399e-05, 20:1.4161e-19}` | 通过（无负值/无符号翻转） |
| G3 新字段 | JSON 含 `c_r2=0.56061 / c_identifiable=false / c_effective=0.5 / temporary_basis="portfolio_ar1_proxy"`；`rho_freq/rho_n/impact_bps_source` 为 panels 内部字段（DESIGN §3 的 runner 契约未含），不进最终 JSON | 通过（口径勘误 A-2） |
| G4 c 回退留痕 | `evidence_warnings` 含「c 不可识别（r2<0.05 或超出 (0.1, 2.0)），容量按默认 0.5」；`c_effective=0.5` | 通过（panels 层 `impact_bps_source=default_fallback` 由 T2 覆盖） |
| G5 net(h) 脱钩 | `net={5:-15,565,022, 10:-7,782,766, 20:-3,891,383}` ≈ `−cost`（差 < 0.03%） | **失败（范围外 FO-1）**，见 §5 |
| G6 版本 | 6 锚点全 `3.9.2`（`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`）+ CHANGELOG 条目 | 通过 |
| G7 旧测试语义 | 旧断言未改语义；新增用例全为追加函数 | 通过 |
| T8 全量 | `python -m pytest -q --junitxml=out/v392_junit.xml` → **2055 passed / 15 skipped / 0 failed**（772.15 s）；首跑 `1 failed / 2054 passed`（A-3）修复后复跑全绿 | 通过 |

**默认路径隔离（E1）**：`out/capacity_impact.json` 顶层键仅 `['meta', 'results']`，无 `decay/temporary_share/impact_curve`，与 DESIGN D5 一致。

---

## §3 探针读数（P1-P4）

### P1 数学/口径

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P1-1 | `fit_r2` 边界 | `([],[])=0.0`；常数序列 `=0.0`；完美拟合 `=1.0` | 通过 |
| P1-2 | σ 同尺度（读码） | `_month_lambda` L335-338：`sd=std(r[ok], ddof=1)` → `clip([0.005,0.20])`，样本元组写 `sigma_d`；分钟 `agg.sigma` 不再进冲击样本 | 通过 |
| P1-3 | c 反算 | `c_calib_point=2.91069`，CI `2.8959–2.9221`，`r2=0.56061`；c>2.0 → `c_identifiable=false` | 通过（门槛按设计生效） |
| P1-4 | cost 传递 | `cost_by_h={5:15.5655M, 10:7.7828M, 20:3.8914M}`，与 `impact_bps_source=default_fallback` 一致；比修复前 ↓5.9× | 通过 |
| P1-5 | rho 频率 | `rho=0.11417`、`rho_ci=[-0.01988, 0.24822]`、`half_life=0.31941`；与 `rho_freq="daily"` 口径一致 | 通过 |
| P1-6 | retention | `rho**h`：0.11417 / 1.94e-5 / 1.42e-19；`retention(1.0)=[1,1,1]` | 通过 |

### P2 确定性

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P2-1 | 默认 SHA 重跑 | 与基线逐位一致（§2 G1） | 通过 |
| P2-2 | 校准工件 | 39 月 exit 0、`evidence_level=minutes`、`missing_months=[]` | 通过 |
| P2-3 | 代码确定性 | `fit_r2`/门槛/守卫均为纯函数，无随机源 | 通过 |

### P3 边界与降级

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P3-1 | rho 非正 | `rho<=0 → 1.0` + warning（panels / runner 各一处） | 通过 |
| P3-2 | rho 序列 <3 或常数 | panels 已兜底；**runner 原缺失** → A-1，已修复（T9） | 修复后通过 |
| P3-3 | 无 params | `impact_bps_source="unavailable"` + `cost_impact_unavailable`（F1 保留） | 通过（读码） |
| P3-4 | Python 3.9 | 5 文件 AST 解析通过；无 `match` / PEP604 / PEP585 / `slots=True` | 通过 |
| P3-4b | core 架构约束 | `impact.py __all__` 首跑 9 项 → 违反 ≤5；回退后 5 项，架构测试 3 passed | 修复后通过（A-3） |
| P3-5 | 零新增依赖 | `pyproject` dependencies 未变（`pyarrow` 仍仅在 `calib` extra） | 通过 |

### P4 结论有效性

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P4-1 | 三文档计数一致 | CHANGELOG 8 例 / CHECKLIST 42 项（41 通过 + 1 失败）/ PROJECT_STATUS 状态块 互一致 | 通过 |
| P4-2 | 未过度声称 | 报告写 `c_effective=0.5` 与 `default_fallback`，未称「校准值」；temporary 明示非 T+1 | 通过 |
| P4-3 | G5 披露 | 摘要、CHANGELOG、IMPLEMENTATION §8、PROJECT_STATUS 均披露 net(h) 仍负 → FO-1 | 通过 |

---

## §4 三项裁决复核

| 读数 | 审计复核 | 分类 |
|------|---------|------|
| `c=15.07` | σ 反解恰为 `0.005`（clip 下界），`sqrt(240)≈15.49` 同量级 → 分钟 bar σ 与日收益 y 尺度错配，过原点拟合把噪声底折入 c；修复后 `c=2.91`、`r2=0.56`，仍超 `[0.1,2.0]` → 按设计回退 0.5 | **实现缺陷 + 识别规则缺失**（已修口径，识别门限生效） |
| `rho=-0.147` | 原实现用月频 `excess_m` 估 AR(1) 后当日频 `rho**h` 用，且无负值守卫；日频重估 `+0.114`（CI 覆盖 0，经济上「无正持续性」），retention 无负值 | **频率错配 + 守卫缺失**（已修） |
| `temporary≈0.4%` | 实为 `clip(-AR1(ex_d),0,1)`，无交易方向、无截面价格 → 非设计 §10 的 T+1 反转；已标 `portfolio_ar1_proxy` 且不入容量 | **口径说明（代理偏离设计）+ 数据限制**（已标注，未伪造修复） |

---

## §5 范围外发现（G5 / FO-1）

- `net(h)` 仍 ≈ `−cost(h)`：日频 `rho=0.1142`（半衰期 0.32 个交易日）使 `alpha0·rho**h` 在 h≥5 坍缩至 ~0；
- 若仅将 rho 置 1.0，`net(20)=26.29M−3.89M=+22.4M` → 负值由 rho 主导，成本已非主因；
- 根因：以「已实现组合收益 AR(1)」代理「alpha 信号衰减」，经济含义不成立（半衰期不足 1 日）；
- 处置：本批白名单不含衰减模型替换，**不伪称已修**；登记 **v3.9.3 P0（FO-1：rho 改由 IC / alpha 期限结构估计）**，并复核 DESIGN §7「组合收益序列」选项。

---

## §6 审计期间修复

| # | 级别 | 问题 | 处置 |
|---|------|------|------|
| A-1 | MINOR | `runner` 重估 rho 未捕获 `estimate_rho` 的 `ValueError`（序列 <3 / 常数），`panels` 已回退而 runner 会崩 | `runner.py` 加 try/except；新增 T9（`[]` / `[0.1,0.2]` / `[0.05]*10` 均回退 1.0）；定向 39 passed |
| A-2 | 文档 | CHECKLIST G3/G4 原写「最终 JSON 含 `rho_freq/impact_bps_source`」，与 DESIGN §3 契约不符 | 修正为 panels 内部字段；证据改引 T2/T4 与 JSON warning |
| A-3 | MAJOR | `impact.py` 的 `__all__` 扩到 9 项，违反 core 架构约束 `__all__<=5` → 全量首跑 1 failed / 2054 passed（`test_core_all_bounded`） | `__all__` 回退为原 5 项，新符号保持模块级显式导入；`test_execution_architecture.py` 3 passed；全量重跑 |

---

## §7 结论

- **本批目标（c/rho/temporary 三项读数口径）PASS**：c 尺度修正生效（15.07→2.91）、门槛回退生效（0.5）、rho 日频化且非负、temporary 如实标注；
- **默认路径零影响**：SHA `82728CE1…` 逐位不变；
- **失败项 G5 属范围外（FO-1）**，移交 v3.9.3 P0，不作为本批回归；
- 审计后代码状态：MAJOR 1（`__all__` 越界回归）+ MINOR 1（rho 守卫）已修复，文档 1 处已勘误，全量重跑后无遗留阻塞。
