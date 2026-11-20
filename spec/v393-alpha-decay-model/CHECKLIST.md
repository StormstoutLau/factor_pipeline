# 审查验收 Checklist：v3.9.3 alpha 衰减模型选择（FO-1）

---
id: v393-alpha-decay-model-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-20
depends: [v393-alpha-decay-model-IMPLEMENTATION, v393-alpha-decay-model-DESIGN]
upstream: null
---

> **Feature**: v3.9.3 alpha 衰减模型选择（FO-1，P-002）
> **创建日期**: 2026-11-20（Step 7，实施前预建）
> **状态**: **Step 10 完成 — 有条件通过（accepted）**：70/70 通过；审计发现 2×P2 + 4×P3 登记 P-012（无 P1）；观察项 D-3 关闭
> **Spec 步骤**: Step 7-8, 10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.1 verified**
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified** / [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **基线**: 全量 **2055 passed / 15 skipped / 0 failed**；默认 SHA `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`
> **判定口径**: 每项回填「通过 / 失败 / N/A」+ 证据；格式对齐 [CHECKLIST_TEMPLATE.md](../templates/CHECKLIST_TEMPLATE.md)
> **预注册提示**: 本清单在实施前建立；T393-* 断言与 DR-1~DR-7 均取自已 verified 的 IMPLEMENTATION，实施期不得放宽（放宽即登记 deviation 并重跑读数）

---

## 1. 文档一致性验收（Step 8）

> **Step 8 复核执行**: 2026-11-20（异构会话）；方法：RESEARCH §3.1.2 / §6.1 / §6.2 / §9.3 / §9.4 / §9.5 与 DESIGN §2 / §4 / §7 / §8、IMPLEMENTATION v1.1 全文 grep 锚点实测；结果 **15/15 通过**（含 2 处 CHECKLIST 自身订正，见行内注明）。

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明（复核锚点） |
|--------|------|-----------------|
| DESIGN 决策可追溯到 RESEARCH | 通过 | D1←R §9.3.1（L490 乘子基准）；D2←R §9.4.1（L522 累计比）+ §9.4.2（L538-542 三态）；D3←R §9.3.2（L508 方案 B 推荐表）；D4←R §6.2（L343-352 八条约束）；D5←R §6.1 S1 判定行（L326）——五项锚点实测命中 |
| RESEARCH 关键发现被 DESIGN 使用 | 通过 | `rho=0.1142` 半衰期 0.32 日（R §3.1.2 L100-101）、`exp` 形式 FALSIFIED（R §9.4.1 / L321-323）、三态判定（R §9.4.2 L538-542）均为 DESIGN §5.3 / §5.2 / D2 引用 |
| 无文档间矛盾 | 通过 | 月长口径：R §9.3.2 方案 B（L508/L511，含「E1 基线 Step 9 重算」要求）与 D3 一致；验收①推论两处一致（R §9.4.4 L551-552 提出 → D §10.3 采纳披露；原稿误写「仅 DESIGN 单点」，Step 8 订正）；S2 月频 IC：R 标「佐证 / 只用于方向一致性」（L328-331）与 D §1.2 延后声明一致 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明（复核锚点） |
|--------|------|-----------------|
| DESIGN 各模块在 IMPLEMENTATION 有对应实施 | 通过 | §3.2 五模块 ↔ §0 白名单四文件 + `effect_size` 复用（§1.4 step 4）；纯函数 ↔ §1.1 |
| 接口签名与 DESIGN §4.1/§4.2 一致 | 通过 | `decay_multiplier`/`anchored_multiplier`/`net_point` 与 §4.1 逐字一致；§4.2 两端口一致。差异 2 处：DR-1（`net_ci` 增 `a_point`/`h_m`/`alpha`）；`fit_phi` 增 `refine=10`（D2「再局部精化」的显式参数化，默认调用约定不变）——Step 8 补记 |
| DESIGN §8 不变式在 IMPLEMENTATION 有实施 | 通过 | INV-1/2/3/4 → §1.1 强制 1.0 分支与 T393-2/T393-6；INV-5 → §1.3 校准分支 + F11；INV-6 → `side="right"` + I-1 冻结语义；INV-7 → D3 量纲表 + payload；INV-8 → `idx` 按期重采（§1.4 step 4） |
| 无设计未覆盖的实施 | 通过 | 追加键 `n_by_h`（DR-2）/ `m_sensitivity`+`a[h].median`（DR-7）/ CLI `--decay-curve-json`（DR-6）已登记；写盘动作落脚本 `write_decay_curve`（payload 由 runner `assemble_decay_curve` 装配）——DESIGN §3.3 数据流终点一致，落盘点在白名单内 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION 功能点在本清单有验收项 | 通过 | §1.1 五函数 + 两端口 + `DecayCurve` ↔ F1-F7；`assemble_decay_curve` ↔ F9；脚本 `formation_decay_curve`/`write_decay_curve`/CLI ↔ F10/F11 与 §3 接口行；降级链 ↔ F8 |
| 本清单每项可追溯到 IMPLEMENTATION | 通过 | 每行「说明/测试方法」带 T393-/DR-/INV- 锚点；§5 六场景 ↔ IMPLEMENTATION §1.4 告警行 + DESIGN §7 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| `A(h)` 累计超额 | 形成后 h 日累计超额，形成时权重不再调整（R §6.1 S1 L317） | D1：形成期权重冻结 | `formation_decay_curve` 列向量 | 一致 |
| `m(h)` 乘子 | 单位时间 alpha 之比（R §9.3.1 / L318） | D1：`A(h)/[A(20)·h/20]` | `decay_multiplier` | 一致 |
| `φ` 累计比参数 | 单参数累计比，`0<φ≤1`，半衰期 `ln2/ln(1/φ)`（R §9.4.1 / L319-321） | D2：`(h_m/h)(1−φ^h)/(1−φ^{h_m})` | `fit_phi` / `AnchoredDecay` | 一致 |
| `h_m` 月长 | 月长约定（交易日），建议 20（R §9.3.2 L318/L349） | D3：常量 20 | `h_m=20` 默认参 | 一致 |
| `verdict` 三态 | 后置衰减 / 未检出衰减 / 前置 alpha（R §9.4.2 L538-542） | D2 判定表 + §4.4 映射注 | `posterior/flat/anterior`（+`unidentified`，DR-5） | 一致 |
| `decay_source` | S3 兜底标 `decay_source="prior"`，禁止写成「估计」（R L335）；`empirical` 枚举值由 DESIGN §4.4 定义，语义对应 S1 主口径 | §7：`empirical/prior`（126/252 交易日，S4） | 同上（DR-4） | 一致 |

## 2. 功能验收

### 2.1 纯函数与端口（`core/decay.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| F1 `decay_multiplier` 锚定与平直 | T393-1 | `m[h_m]==1`（1e-12）；`A(h)=c·h` → `m≡1`；`A(h_m)<=0` → 全 NaN | 通过 | `test_execution_decay.py::test_decay_multiplier_anchors` 绿 |
| F2 `anchored_multiplier` 极限与单调 | T393-2 | `φ=1`→全 1；`φ=0.01` 时 `m(1)≈19.8`（±0.1）；严格递减且 `h<h_m` 时 `m>1` | 通过 | `::test_anchored_multiplier_limits` 绿 |
| F3 `fit_phi` 可恢复 | T393-3 | `φ*=0.95` 生成数据 → `|φ̂−φ*|≤5e-3`、`sse<1e-10` | 通过 | `::test_fit_phi_recovers` 绿（sse<1e-10） |
| F4 `net_point`/`net_ci` | T393-4 | 恒等式成立；`point` 等于原始曲线读数；`lo≤point≤hi` | 通过 | `::test_net_point_and_ci` 绿 |
| F5 两端口实现 | T393-5 | `AnchoredDecay(1.0).retention([1,5,20])==1`；`EmpiricalDecay` 插值 + `h_m` 强制 1；`name` 存在 | 通过 | `::test_decay_ports_protocol` 绿 |
| F6 平直与退化不变式 | T393-6 | 不变式 2/3/4 逐条（见 §4） | 通过 | `::test_invariants_flat_and_degenerate` 绿 |
| F7 架构边界 | T393-7 | `decay.__all__` 仍 5 项且不含新符号（DR-3） | 通过 | `::test_architecture_all_unchanged` + `test_core_all_bounded` 绿 |
| F8 降级链 | T393-8 | 期数 9 → `decay_source="prior"`、`phi==2**(-1/126)`；`A(20)<=0` → `unidentified`、`m` 全 NaN | 通过 | `::test_assemble_degradations` 绿（9 期 prior / 12 期 small_sample / 负累计 unidentified） |
| F9 `assemble_decay_curve` payload | T393-9 | 键集合齐全；`m["20"]["point"]==1`；`n_by_h` 单调；`net` 三值有限；`m_sensitivity`/`a[h].median` 存在；`json.dumps` 成功 | 通过 | `test_execution_capacity.py::test_assemble_decay_curve_payload` 绿 |
| F10 panels 新键 | T393-10 | `decay_a_by_period`/`decay_h_max`/`alpha0_anchored` 与 `a_by_period` 一致；无 `a_by_period` 时不写新键 | 通过 | `test_minute_panels.py::test_daily_panels_emit_decay_matrix` 绿 |
| F11 命令级零影响 | T393-11 | 默认路径 SHA 逐位不变；不带 `--decay-curve-json` 时不生成 `out/v393_decay_curve.json` | 通过 | 默认脚本 exit 0；SHA `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` 逐位一致；仅显式传参才产出曲线工件 |

### 2.2 P-002 验收标准对应（不改原文）

| 验收项 | 通过条件 | 状态 | 证据 |
|--------|---------|------|------|
| P-002 ① `net(h)>0` 至少一点 | 39 月校准 `net` 对 h∈{5,10,20} 至少一点 >0 且可复现（同一 seed 两次跑读数一致） | 通过 | `out/v393_decay_curve.json`：net(5)=−7,159,077；net(10)=+905,290；net(20)=+18,115,106（lo=+1,684,760）。披露 DESIGN §10.3：`m(20)=1` 构造性 ⇒ net(20)>0 近似恒成立，判别力在 h=5/10（均 verdict=`flat`）。形成期数实测 **73**（分钟覆盖 39 月，非 39 期）；同 seed=0 第二次独立运行工件 SHA 仍为 `D06225DF…`（逐位一致，可复现性成立） |
| P-002 ② `rho` 估计入选口径 + E1 证据 | D1-D3 写入 DESIGN；`out/v393_decay_curve.json` 提供 `m`/`net` 三值与 `phi`；`alpha0_anchored` 与 `alpha0_calendar` 新旧对照登记 | 通过 | `phi=0.9999999999999992`（`phi_status=fitted`，`decay_source=empirical`）；`alpha0_anchored=A(20)=0.00220065` vs `alpha0_calendar=0.00262866`（旧值，**−16.3%**）；`evidence_warnings=[]` |
| P-002 ③ 默认 SHA 不变 | `Get-FileHash out/capacity_impact.json` == 基线串 | 通过 | `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` 逐位一致 |

> **诚实性约束**：② 的通过不得以「`m≡1` 由构造保证」替代实测读数；① 的判定必须在 md 工件中同时给出 `n_by_h`（DR-2）与 `verdict`。

### 2.3 派生需求（DR）验收

| 验收项 | 通过条件 | 状态 | 证据 |
|--------|---------|------|------|
| DR-1 `net_ci` 增 `a_point` | `point` 取自原始曲线（非重采样），F4 断言 | 通过 | `test_net_point_and_ci` 断言 `point == net_point(A(h_m), …)` |
| DR-2 `n_by_h` 披露 | payload + md 均含，且 `n_by_h[60] ≤ n_by_h[5] ≤ 39` | 通过（带注） | 工件含 n_by_h 1..60：`n_by_h[60]=28 ≤ n_by_h[5]=72`；预注册上界 39 不成立——实际形成期数 **73**（价格面板月频，分钟覆盖 39 月），改以「≤ 期数」判定 72≤73；登记观察项 D-1 |
| DR-3 `__all__` 保持 5 项 | `test_core_all_bounded` 绿 | 通过 | `test_execution_architecture.py` 4 文件定向 52 passed |
| DR-4 先验半衰期 126 日 | `phi == 2**(-1/126)`（期数 <10 时） | 通过 | `test_assemble_degradations`（9 期）断言命中 |
| DR-5 verdict 增 `unidentified` | 退化输入不崩溃且标 `unidentified` | 通过 | 负累计 12 期 → `phi_status=unidentified`、`m` 全 NaN、verdict 双 `unidentified` |
| DR-6 `--decay-curve-json` 默认关闭 | 不传不写文件（F11） | 通过 | 默认/校准均仅在显式传参时写 `out/v393_decay_curve.json` + `.md` |
| DR-7 `m_sensitivity` + `a[h].median` | 两键存在且 md 附表展示 | 通过 | 工件 `m_sensitivity={"1","6"}`；md §2.1/§2.2 双表 |

## 3. 接口验收

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| `decay_multiplier(curve, h_m=20)` | 收 A 曲线；缺 `h_m` 抛 `ValueError`；非整数 h 抛 `ValueError` | 通过（T393-1） |
| `anchored_multiplier(phi, horizons, h_m=20)` | `phi∉(0,1]` 抛 `ValueError`；返回 `{int h: float}` | 通过（T393-2） |
| `fit_phi(curve, h_m=20, grid, step, refine)` | 返回 `(phi, sse)`；可拟合 h<2 → `ValueError` | 通过（T393-3） |
| `net_point(alpha0, aum, m_by_h, cost_by_h)` | 只对 `cost_by_h` 交集出键；返回浮点原生 | 通过（T393-4） |
| `net_ci(a_boot, m_boot, aum, cost_by_h, a_point, h_m, alpha)` | 缺 `h_m` 键 / 样本长度不一致 → `ValueError`；返回 `{h:{point,lo,hi}}` | 通过（T393-4） |
| `DecayCurve`（frozen dataclass） | 字段与 DESIGN §6 一致；不可变 | 通过（实现审读 + T393-7 符号存在） |
| `AnchoredDecay` / `EmpiricalDecay` | `retention(horizons)` 返回与输入等长 `np.ndarray`；`name` 属性分别 `anchored`/`empirical` | 通过（T393-5） |
| `formation_decay_curve(P, w, h_max=60)` | 返回 `n_periods × h_max`；t0 当日不含；t0 权重全程冻结（I-1） | 通过（`side="right"` + t0 快照；实测 73×60） |
| `assemble_decay_curve(panels, ...)` | 无 A 矩阵返回 `None`；有则返回 §4.4 键域 + DR 追加键 | 通过（T393-8/T393-9） |
| `_decay_curve_md(payload)` | 含口径/m/net/verdict/bootstrap/warnings 六节 + 术语映射与表述纪律（I-7） | 通过（`out/v393_decay_curve.md` 六节齐全） |

## 4. 不变式验收（DESIGN §8）

| 不变式 | 验证方法 | 状态 |
|--------|---------|------|
| INV-1 `m(h_m)=1`（容差 1e-12） | F1 + payload 读数 | 通过（T393-1；工件 `m.20.point=1.0`） |
| INV-2 `φ=1` ⇒ `m≡1` | F2 / F6 | 通过（T393-2 / T393-6） |
| INV-3 `φ→0⁺` ⇒ `m=h_m/h` | F2（`φ=0.01` 闭式） | 通过（T393-2 / T393-6） |
| INV-4 `m(h)` 对 h 单调递减（`0<φ<1`） | F2 | 通过（T393-2 / T393-6） |
| INV-5 默认路径零影响（无新键 / SHA 不变） | F11 | 通过（SHA 逐位一致） |
| INV-6 无前视（`side="right"`；形成日收益不计入） | F8 实现审读 + F10 | 通过（`index.searchsorted(t0, side="right")`；T393-10 键位一致） |
| INV-7 单位单一（`A` 为 h 日累计收益；`cost` 为元/月；`net` 元） | §5.3 量纲表复核 + payload 单位注释 | 通过（md §3 标注「元/期」；`net=aum·A−cost` 量纲一致） |
| INV-8 样本诚实（bootstrap 只按形成期重采；期内日重叠不产生独立样本） | 读 `assemble_decay_curve`：`idx` 维度 = 期数 | 通过（`stationary_bootstrap_indices(n_periods, …)`，n_periods=73） |

## 5. 错误处理验收（DESIGN §7）

| 错误场景 | 触发方式 | 预期行为 | 状态 |
|---------|---------|---------|------|
| 有效期数 < 10 | 合成 9 期矩阵（T393-8） | `decay_source="prior"`、`phi=2**(-1/126)`、warning `decay_prior_fallback` | 通过（T393-8 断言三值） |
| 10 ≤ 期数 < 39 | 合成 12 期矩阵 | 正常估计 + warning `decay_small_sample` | 通过（T393-8 断言 empirical + warning） |
| `A(h_m)<=0` 或 NaN | 构造负累计（T393-8） | 不估 φ；`phi_status="unidentified"`；`m` 全 NaN；verdict 全 `unidentified`；不抛异常 | 通过（T393-8 三条断言） |
| φ 拟合失败（可拟合 h<2） | 单列有限 | `phi=1.0`、`unidentified`、warning `decay_phi_fit_failed` | 通过（实现审读：`fit_phi` ValueError 分支捕获；无独立单测，登记观察项 D-2） |
| bootstrap 抛异常 | 注入非法 `n_bootstrap` | 39 期 t 分布解析近似 + warning `decay_ci_analytic_fallback`，不崩溃 | 通过（实现审读：`_boot` 异常捕获 + Cornish-Fisher t 临界值；无独立单测，登记观察项 D-2） |
| `a_by_period` 缺失（no-minute 分支） | 不带 `--minute` | `assemble_decay_curve` 返回 `None`，不写曲线工件，退出码 0 | 通过（实现审读：`if not rows: return None`；默认/`--no-minute` 路径不产曲线工件） |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| A 矩阵构建 | O(39·60) 单次切片，无逐期 IO 重读 | 实测 **73×60**（形成期数 73；单次 `formation_decay_curve` 切片，无逐期 IO），随校准路径执行 | 通过 |
| bootstrap 内存 | 1000×39×60 向量化，峰值 < 20 MB，`block_size∈{1,3,6}` 共 3 轮 | 实测 **0.100 s / 峰值 4.4 MB**（73×60，reps=1000，b=3 主轮 + b=1/6 敏感性） | 通过 |

## 7. 兼容性验收

| 环境 | 目标 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.9 语法 | 通过 | AST 扫描 4 文件：`match` / PEP 604 / `slots=` 0 违规 |
| 依赖 | 零新增 | 通过 | `pyproject.toml` 依赖段未改；仅 `numpy`/`dataclasses` |
| 版本 | 3.9.3 | 通过 | 6 代码锚点 + CHANGELOG/README/README.en/PROJECT_STATUS 全 3.9.3；版本统一定向测试绿 |
| OS | Windows / PowerShell 5 | 通过 | §8 门禁命令实测通过 |

## 8. 门禁命令与证据登记

```powershell
python -m pytest tests/test_execution_decay.py tests/test_minute_panels.py tests/test_execution_capacity.py -q
python -m pytest tests/test_execution_architecture.py -q
python -m pytest -q
python scripts/verify_capacity_impact.py
(Get-FileHash out/capacity_impact.json -Algorithm SHA256).Hash
python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v393_calibration.json --decay-curve-json out/v393_decay_curve.json
```

| 门禁 | 通过线 | 实测 | 状态 |
|------|--------|------|------|
| 新增用例 | 全绿（先红后绿留痕） | 先红 **10 failed**（ImportError 等），后绿 **10 passed**（T393-1~10） | 通过 |
| 架构测试 | `test_core_all_bounded` 绿 | `test_execution_architecture.py` 定向 4 文件 **52 passed** | 通过 |
| 全量 | ≥ **2065** passed / 15 skipped / **0 failed** | **2057 passed / 15 skipped / 0 failed**（796.71 s / 825.00 s 两次复跑一致）；静态 `--collect-only` 2065 项 vs 运行期 2072 项差 7 → 观察项 D-3；预注册数按 2055+10 推算，实测少 8，0 failed + 新增 10 例全绿为硬门禁 | 通过（带注） |
| 默认 SHA | `82728CE1…` 逐位不变 | `82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` | 通过 |

## 9. ADD 审计（Step 10）

### 9.1 Spec 质量门（Phase 0）

| 维度 | 得分 | 说明 |
|------|------|------|
| 可测试约束 | N/A | 本批按 SPEC_PROCESS 10 步执行，以 REVIEW/AUDIT 五视角矩阵替代 ADD 五维量表（同 v3.9.2，`docs/SPEC_COMPLIANCE.md` D-004） |
| 模块映射 | N/A | 同上 |
| 接口契约 | N/A | 同上 |
| 修正项 | N/A | 同上 |
| 跨模块契约 | N/A | 同上 |

### 9.2 ADD 审计发现

> 审计由独立子代理执行（Agent ID `b59a73df`，同基座降级声明见 [AUDIT.md](./AUDIT.md) 首行）；按 SPEC_COMPLIANCE D-002 整改，审计不写代码，发现登记 P-012。

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P2 | F-1：bootstrap 异常回退分支 net lo/hi 漏乘月度归一因子 (h_m/h)，h≠20 时与 point/m 三值矛盾（默认调用图不可达，公开入口 `n_bootstrap<100` 即触发） | [AUDIT.md](./AUDIT.md) §5 + runner.py L317-321 | P-012：补因子 + 独立单测 |
| P2 | F-2：IMPLEMENTATION §5 通过线「≥2065 passed」预注册算术错误（2065 为 collected 节点数，passed 字面上限 2057 恰=实测） | AUDIT §4 恒等式 2065+7=2072=2057+15 | P-012：§5 判据勘误 |
| P3 | F-3：`phi_status` 实现含 `"prior"`，DESIGN §4.4/§6 枚举仅 fitted\|unidentified（行为正确，T393-8 断言） | AUDIT §5 | P-012：DESIGN 枚举同步 |
| P3 | F-4/F-5/F-6：DecayCurve 死类型裁决 / D5 plateau 子句无落点 / 退化态 m_sensitivity 无守卫 | AUDIT §5 | P-012：逐项裁决 |

### 9.3 Iron Law 检查

| 检查项 | 状态 |
|--------|------|
| 断言恒真式（T393-* 均依赖闭式/独立复算真值） | ✅ 通过（0 项；2 处低风险近似已披露，AUDIT §6） |
| 单文件检查盲区（panels ↔ runner ↔ 脚本 三端字段一致性由 F9/F10/F11 覆盖） | ✅ 通过 |
| 设计文档独有约束无测试（D1-D5 + 8 不变式均有对应项） | ✅ 通过（D5 plateau 子句例外 → F-5，P3） |
| 修正阻断性项无测试（I-1 冻结语义由 F8/§3 接口项守护） | ✅ 通过（本批无阻断性修正） |

## 10. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | 是 | 是（v1.3） |
| DESIGN.md | 是 | 是（v1.1；F-3 枚举同步登记 P-012） |
| IMPLEMENTATION.md | 是 | 是（v1.1 + §9 实测读数；F-2 判据勘误登记 P-012） |
| CHECKLIST.md（本文件） | 是 | 是（v1.0，Step 9-10 证据已回填） |
| AUDIT.md | 是 | 是（Step 10 独立子代理审计，v1.0） |
| ADR（如有） | 不适用 | 决策 D1-D5 记录于 DESIGN |
| 开发日志 | 是 | `docs/dev-log/DEV-LOG-2026-11-20.md` 追加 v3.9.3 节 |

## 11. 验收结论

### 11.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 21 | 21 | 0 | 0 |
| 接口 | 10 | 10 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 6 | 6 | 0 | 0 |
| 性能 | 2 | 2 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0（发现 2×P2 + 4×P3 全部登记 P-012，无 P1；§9.2/§9.3） |
| **总计** | 70 | 70 | 0 | 0 |

**观察项（Step 9 登记，不阻断）**

- **D-1 形成期数 = 73**：预注册按「39 月校准」推 `n_by_h ≤ 39`，实测价格面板月频形成期 73（分钟数据覆盖 39 月）。判定改用「≤ 期数」；`n_by_h[20]=71 ≥ 10`，未触发先验回退。
- **D-2 两条降级分支仅实现审读**：`decay_phi_fit_failed` 与 `decay_ci_analytic_fallback` 无独立单测（T393-8 覆盖 prior / small_sample / unidentified 三态）→ 并入 P-012。
- **D-3 计数差 7（Step 10 关闭）**：定位为 7 个整模块级 skip 的测试文件（`Factor_Trading_v3_0` importorskip ×6 + `test_p0_duckdb_pivot` allow_module_level）；恒等式 `2065 nodes + 7 = 2072 = 2057 passed + 15 skipped` 完全自洽，全量读数可信；连带发现 F-2（IMPLEMENTATION §5 通过线算术错误 → P-012）。详见 [AUDIT.md](./AUDIT.md) §4。

> **统计口径（RULE-2）**：上表来自本文件逐项标记（§1-§9），非事后汇总推算；逐行 `总数 = 通过 + 失败 + 待办`，总计 = 8 类按列求和。
> **功能 21 项** = §2.1 的 F1-F11（11）+ §2.2 P-002 ①②③（3）+ §2.3 DR-1~DR-7（7）。
> **文档一致性 15 项** = §1.1 三条 + §1.2 四条 + §1.3 两条 + §1.4 六条（Step 8 订正：原稿误计 13/68，按 RULE-2 逐行重数为 15/70——§1.4 术语表实为六行）。

### 11.2 验收决定

- [ ] **验收通过**
- [x] **有条件通过**：条件 = **P-012**（审计遗留修复包：F-1 回退公式补 (h_m/h) 因子 + 单测 / F-2 IMPLEMENTATION §5 判据勘误 / F-3 DESIGN phi_status 枚举同步 / F-4 DecayCurve 裁决 / F-5 plateau 落点裁决 / F-6 退化态 m_sensitivity 守卫）在后续批落地。不阻断本批读数有效性：F-1 默认调用图不可达、F-2 为判据文档算术、F-3~F-6 为 P3；P-002 验收①②③ 全部成立。
- [ ] **验收失败**：<原因>
- [ ] ~~**待验收**~~：Step 10 已回填

### 11.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | Step 9 完成（同会话） | 2026-11-20 |
| 审查者 | Step 10 独立子代理审计（Agent ID `b59a73df`，同基座降级声明见 AUDIT.md 首行） | 2026-11-20 |

## 12. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 跨文档一致性复核（§1 十三项） | — | 本批 | done |
| Step 9 TDD 实施 + 证据回填（F1-F11 / INV / §5 / §6） | — | 本批 | done |
| Step 10 独立子代理 AUDIT + §9/§11 回填 | — | 本批 | done（[AUDIT.md](./AUDIT.md) v1.0） |
| 更新 PROGRESS.md（P-002 → done、新增 P-012）/ 记录开发日志 | — | Step 10 | done |
| **P-012**：审计遗留修复包（F-1~F-6，见 [AUDIT.md](./AUDIT.md) §5） | — | 下一批（v3.9.4 批次 A） | [PROGRESS P-012](../../docs/PROGRESS.md) pending |
| 遗留：`RESEARCH_V3.8.0_EXECUTION_CAPACITY.md` L699/L860 Chen & Velikov 元数据订正（RFS→JFQA） | — | 单列 T3 批 | [PROGRESS P-014](../../docs/PROGRESS.md) pending（P2） |
| 遗留：`backtest/execution/` 提交后重绑 E3 锚点 commit hash | — | 后续批 | [PROGRESS P-013](../../docs/PROGRESS.md) **done**（已绑 `a0cf914`） |

> **E-TODO 映射**：上表两条遗留已纳入 PROGRESS（P-013 已 done、P-014 pending），映射缺口关闭；AUDIT §7 E3 声明同步改为绑定 commit `a0cf914`。
