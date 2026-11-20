# v3.9.3 alpha 衰减模型选择 — 步骤 10 审计复审报告

---
id: v393-alpha-decay-model-AUDIT
type: design
version: 1.0
status: verified
date: 2026-11-20
depends: [v393-alpha-decay-model-CHECKLIST, v393-alpha-decay-model-IMPLEMENTATION, v393-alpha-decay-model-DESIGN]
upstream: null
---

> **审计日期**: 2026-11-20　**审计方法**: audit-driven-development（SPEC_PROCESS Step 10）
> **异构性声明（RULE-5 / SPEC_COMPLIANCE D-001 整改）**: 审计由**独立子代理**执行（Agent ID `b59a73df`，独立上下文，不复用实施会话判断）；**同基座降级**——子代理与实施同为 GLM 基座，仅上下文隔离，结论以 E1/E2 可重放证据与独立复算重建，E5（推测）不单独支撑任何「通过」。
> **审计纪律（D-002 整改）**: 本审计**不修改任何代码/测试**；发现以「问题 + 复现命令」列出，修复另立 P 行（P-012）。
> **审计对象**: 批次 v3.9.3（包版本 **3.9.3**）— 累计 alpha 曲线 `A(h)` + 单参数累计比 `φ` + 形成期 bootstrap
> **结论**: **PASS（本批范围，有条件）** — P1 阻断 0；P2 应修 2（F-1 默认调用图不可达、F-2 判据文档算术）；P3 提示 4（F-3~F-6）；观察项 D-1/D-3 **关闭**（D-3 完整定位，见 §4）；Iron Law 恒真式 **0 项**。遗留修复统一登记 **P-012**。

---

## §1 审计范围与方法

1. 白名单 5 代码文件 + 3 测试文件（12 用例）+ `out/` 三工件 + DESIGN §2/§4/§6/§7/§8/§10.3 逐条映射；
2. CHECKLIST v1.0 §1-§8 全部回填项抽查复核（含 RULE-2 逐行计数）；
3. 独立复跑：全量 `pytest -q` 第 3 次（E1）+ 校准复跑 SHA（E1）+ 数学闭式独立复算（E2）；
4. 四阶段：完整性（design→code）/ 忠实度（双向）/ 必要性（code→design）/ 语义（意图层）。

## §2 门禁独立复验（审计独立读数）

| 门禁 | 审计读数 | 判定 |
|------|---------|------|
| G1 默认 SHA | `Get-FileHash out/capacity_impact.json` = `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`；顶层键仅 `[meta, results]`，零 decay/alpha0 键 | 通过（INV-5） |
| G2 全量（第 3 次独立复跑） | `python -m pytest -q` → **2057 passed / 15 skipped / 0 failed**（1025.25 s；与 Step 9 两次 796.71/825.00 s 读数一致） | 通过（0 failed 硬门禁） |
| G3 曲线工件可复现 | 校准复跑 exit 0，`out/v393_decay_curve.json` SHA 仍 `D06225DF0BBC78584B55E6930E5B3A9B4524A749FFDEB72B8E8AE009FC9E78A4`（两次独立运行逐位一致） | 通过（P-002① 可复现性） |
| G4 工件复算 | `net(20) = 1e10 × 0.00220065 − cost_by_h[20](3,891,383.10) = +18,115,106` 与 payload 一致；`a[20].point == alpha0_anchored`；`m[20]=1/1/1`；verdict(5/10)=flat 与 lo/hi 覆盖 1 一致；`n_by_h` 单调不增 | 通过 |
| G5 md↔json 一致 | `out/v393_decay_curve.md` 12 处抽查（m/a/net/verdict/n_h/敏感性/口径）逐值一致（%.6g 展示舍入；md「phi = 1」系 0.9999999999999992 舍入，展示级） | 通过 |
| G6 版本锚点 | 6 锚点全 `3.9.3`（pyproject L7 / `__init__.py` L58 / config_v2 L371 / reporting L40 / test_fix3 L34 / verify_fix3_manual L21） | 通过 |
| G7 架构与语法 | `decay.__all__` 仍 5 项且不含新符号（T393-7）；5 文件 AST 解析通过（无 match/PEP604/slots） | 通过 |

## §3 探针读数（P1-P4）

### P1 数学/口径（E2，独立参考实现复算）

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P1-1 | `m(h)=A(h)/[A(h_m)·h/h_m]` 独立复算 | 与 `decay_multiplier` 输出逐位相等（max err=0.0） | 通过 |
| P1-2 | `m(h;φ)` 独立复算（φ=0.95） | 逐位相等；m(1)=1.5588 / m(5)=1.4105 与 RESEARCH 复算一致 | 通过 |
| P1-3 | INV-3 退化极限 | φ=1e-12 → m={20,4,2,1}=h_m/h（err 2e-11）；INV-2 φ=1 → 全 1（T393-2/T393-6） | 通过 |
| P1-4 | `fit_phi` 恢复 | φ*=0.95 生成 → \|φ̂−φ*\\|≤5e-3、sse<1e-10（T393-3） | 通过 |
| P1-5 | `phi≈1.0` 语义 | fitted（非平直假设的先验），`m(5)=0.382` 点估计 <1 但 CI 覆盖 1 → 判 `flat` 而非「无衰减」（I-7 表述纪律在 md 固定文案） | 通过（语义层） |

### P2 确定性（E1）

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P2-1 | 全量三次一致 | 796.71 s / 825.00 s / 1025.25 s 三次读数计数一致 | 通过 |
| P2-2 | 曲线工件两次逐位 | SHA `D06225DF…` 一致（seed=0） | 通过 |
| P2-3 | bootstrap 锚定 | `stationary_bootstrap_indices(n_periods, reps, block, seed)` 返回 (B, n) 矩阵；CI 仅按形成期重采（INV-8） | 通过 |

### P3 边界与降级（E3 静态 + E2）

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P3-1 | 降级三态 | prior（9 期）/ small_sample（12 期）/ unidentified（负累计）由 T393-8 断言；`decay_phi_fit_failed` 与 `decay_ci_analytic_fallback` 仅实现审读（D-2） | 通过（D-2 遗留 P-012） |
| P3-2 | no-minute 路径 | `assemble_decay_curve` 无 `decay_a_by_period` → None，不写曲线工件 | 通过 |
| P3-3 | 退化态 m_sensitivity | **发现 F-6**：degenerate 时敏感性循环无守卫（见 §5） | P3 |

### P4 结论有效性与文档合规

| # | 探针 | 读数 | 判定 |
|---|------|------|------|
| P4-1 | D5 披露 | md L4-6 显式披露「m(20)=1 构造性 ⇒ net(20)>0 近似恒成立，判别力在 h=5/10」 | 通过（§10.3） |
| P4-2 | E1 基线对照 | `alpha0_anchored=0.00220065` vs `alpha0_calendar=0.00262866`（−16.3%），两口径并列且 calendar 标注「不作主值」 | 通过 |
| P4-3 | 判读纪律 | 三文档（AUDIT/CHECKLIST/PROJECT_STATUS）均按预注册表述「未检出衰减 ≠ 无衰减」 | 通过 |

## §4 D-3 定位关闭（观察项）

`pytest --collect-only -q` = **2065 nodes**（141 个文件）；`tests/` 下实际 148 个 `test_*.py`，其中 **7 个整模块级跳过**（`test_data_bridge` / `test_e2e_cached_pipeline` / `test_engine` / `test_p1_adaptive_min_dates` / `test_p0_parallel` / `test_pipeline_integration`：模块级 `pytest.importorskip("Factor_Trading_v3_0")`；`test_p0_duckdb_pivot`：L26 `pytest.skip(allow_module_level=True)`）。collect-only 不产生节点，运行期每模块产出 1 个 skipped outcome：

```
2065 nodes + 7 module-level skips = 2072 = 2057 passed + 15 skipped
```

完全自洽（15 skipped 含 7 个模块级 + 8 个常规 skip）。**D-3 关闭**：全量读数可信，无测试丢失。连带发现 **F-2**：IMPLEMENTATION §5 通过线「≥2065 passed」的预注册算术错误（2065 是 collected 数，其 passed 上限恰为 2057）。

## §5 发现清单（审计不修复，登记 P-012）

| ID | 级别 | 位置 | 缺陷 | 设计条文 | 复现命令 |
|----|------|------|------|---------|---------|
| F-1 | **P2** | `backtest/execution/shell/runner.py` L317-321 | bootstrap 异常回退分支的 net lo/hi 按裸 `aum·(a_mean[h]±t·se_a)−cost` 计算，**漏乘月度归一因子 (h_m/h)**：h≠20 时与 point（=aum·a_mean[h]·h_m/h−cost）及 m 三值（L322-323 已正确缩放）互相矛盾，可出现 point∉[lo,hi]。当前默认调用图 `_boot` 不抛错、分支近乎不可达，但 `assemble_decay_curve` 为公开入口且 `n_bootstrap<100` 即触发 | DESIGN §7 行5 + §2 D5 | monkeypatch `stationary_bootstrap_indices` 抛错后比较 net 三值 |
| F-2 | **P2** | `spec/v393-alpha-decay-model/IMPLEMENTATION.md` §5 | 通过线「≥2055+10=**2065 passed**」算术错误：2065 实为 collected 节点数（含静态 skip），passed 字面上限 2057（恰=实测）；§9 读数本身自洽 | §5 / D-3 | 见 §4 计数恒等式 |
| F-3 | P3 | `runner.py` L340 ↔ DESIGN §4.4/§6 | `phi_status` 实现含 `"prior"`（n_anchor<10 分支），DESIGN 枚举仅 `fitted\|unidentified`；行为正确（T393-8 断言）但 schema 枚举未同步 | DESIGN §4.4 / §6 | grep `phi_status` runner.py |
| F-4 | P3 | `decay.py` L257-268 | `DecayCurve` 无调用方（DESIGN §3.2 称 runner「装配 DecayCurve」，实现返回 dict payload；仅 T393-7 hasattr 检查）——接口先行的死类型，需裁决（保留/接线/删除） | DESIGN §3.2 / §6 | grep `DecayCurve` 全仓 |
| F-5 | P3 | 全局 | DESIGN D5「plateau 用 net 的 bootstrap 标准差」无实现落点：§4.4 schema 无 plateau 字段，默认路径 plateau 仍走 rho 口径（INV-5 约束下本批不可改默认路径，属设计-实施范围错位） | DESIGN §2 D5 | grep `plateau` payload/§4.4 |
| F-6 | P3 | `runner.py` L354-365 vs L267-272 | 退化态（A(20)≤0）下 `m_sensitivity` 仍执行 `_boot`：重采均值部分>0 时可产出有限敏感性 CI，与主 CI（NaN）/verdict=unidentified 口径不一致；设计未定义该组合行为 | DESIGN §7 行3 | 合成负累计矩阵后读 `m_sensitivity` |

**诚实结果列**：扫描范围为白名单全部代码 + 12 用例逐断言 + 三工件 + DESIGN §2/§4/§6/§7/§8/§10.3 逐条映射；未发现其他 P1/P2 级问题。

## §6 Iron Law 扫描

**发现 0 项断言恒真式**。扫描范围：`test_execution_decay.py` 全部 8 例 + `test_assemble_decay_curve_payload` + `test_daily_panels_emit_decay_matrix`，逐断言核对期望值来源。2 处低风险近似（非违规，披露）：T393-4 的 `point == expected[h]` 两侧同为 `net_point` 装配（接线级检查；同用例已含手算独立期望 `net[20]≈aum·0.04−4e5`）；T393-1/T393-8 的 `m[20]==1`、`phi==2**(-1/126)` 属构造性分支/登记常数验证（INV-1 本即构造性）。独立真值断言充足：19.8 闭式、线性插值手算、`alpha0_anchored==0.03` 手算、φ*=0.95 恢复、`n_by_h==38/39` 推导。

## §7 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| 第 3 次全量 `pytest -q`（E1） | G2 全量门禁 / 0 failed 硬门禁 | ✅ 2057/15/0（1025.25 s） |
| `pytest --collect-only` + 148 文件分解（E1） | D-3 计数差 | **发现 7 项模块级 skip** → 恒等式闭合，D-3 关闭 |
| 校准复跑 SHA（E1） | P-002① 可复现性 | ✅ `D06225DF…` 两次逐位一致 |
| 数学独立参考实现复算（E2，含 φ→0⁺ 对抗场景） | P1-1~P1-4 / INV-1~4 | ✅ 逐位一致（max err 2e-11） |
| json↔md 交叉比对（E1） | G4/G5 工件一致性 | ✅ 12 处抽查一致 |
| 静态读码（E3；锚点绑定 commit `a0cf914`，2026-11-20 提交） | Phase 1-3 全部映射 + F-1~F-6 | **发现 6 项**（2×P2 / 4×P3） |
| 默认路径隔离探针（E1） | INV-5 | ✅ 顶层键零污染 + SHA 逐位一致 |
| 盲区扫描：T393-* 逐断言真值来源（E4） | Iron Law | **发现 0 项**（范围：12 用例；2 处低风险近似已披露） |

## §8 结论与遗留处置

- **本批目标（FO-1：衰减模型选择落地）PASS**：`A(h)` 曲线 / 非参乘子 / `φ` 拟合 / 三态 verdict / net 三值 / bootstrap CI 全部按预注册落地；实测工件可复现、可独立复算；
- **P-002 验收①②③ 全部成立**（net(10)=+905,290>0 且两次逐位可复现；rho→期限结构口径有 E1 证据；默认 SHA 逐位不变）；
- **P1 阻断 0**；2 项 P2 + 4 项 P3 **不在本批修复**（D-002 整改：审计不写代码），统一登记 **P-012**（修复包：F-1 回退公式补 `h_m/h` 因子 + 独立单测；F-2 IMPLEMENTATION §5 判据勘误；F-3 DESIGN 枚举同步；F-4/F-5 裁决；F-6 退化态口径守卫）；
- 观察项 D-1（形成期 73 期，口径改判已登记）、D-2（两降级分支单测缺口 → 并入 P-012）、D-3（**关闭**，见 §4）；
- **E3 锚点已重绑（P-013 done）**：§7 静态读码行改为绑定 commit `a0cf914`（`backtest/execution/` 随之入库）；两条遗留（E3 重绑 / Chen & Velikov 元数据）已纳入 PROGRESS 映射（P-013 / P-014），CHECKLIST §12 同步；
- 判读纪律：`verdict={5:flat, 10:flat}` 按预注册判「未检出衰减」，**不得表述为「无衰减」**；`net(20)>0` 由构造性归一保证，判别力在 h=5/10。
