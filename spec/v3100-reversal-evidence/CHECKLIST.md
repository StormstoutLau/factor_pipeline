# 审查验收 Checklist：截面 T+1 reversal 真实现（P-003，口径 A）

---
id: v3100-reversal-evidence-CHECKLIST
type: design
version: 1.2
status: verified
date: 2026-11-21
depends: [v3100-reversal-evidence-IMPLEMENTATION, v3100-reversal-evidence-DESIGN]
upstream: null
---

> **Feature**: P-003「截面 T+1 reversal 真实现」——事件级「交易方向 × 截面价格」已实现反转替代 `temporary_share` 组合 AR(1) 代理。
> **创建日期**: 2026-11-21
> **状态**: **v1.2 verified（Step 7-10 完成，有条件通过）**——§1-§7 全通过（75 项），§8 ADD 审计 **PASS_WITH_FIXES（4.60/5，A；0×P1、2×P2、6×P3）**；2×P2 测试有效性补强登记后续批次，口径 A 结论与工件不变式全部成立
> **Spec 步骤**: Step 7-10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.2 verified**
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.3 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **批次档位**: T1｜**包版本**: 3.9.5｜**代码基线**: `9b09f8c`
> **硬约束**: Python 3.9 / 零新增依赖 / `core/decay.py` 零改动（`__all__` 恒 5 项）/ 默认 SHA `82728CE1…` 逐位不变 / `panel_hash` 逐位不变

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的 12 条决策（D1-D12）可追溯到 RESEARCH §3/§6 | ✅ | DESIGN §2.1 决策表 12 行逐行标注 RESEARCH 锚点；Step 4 复审门禁 a 实核 12/12 命中（DESIGN §12.2） |
| RESEARCH 的 F-1~F-9 与 U-1~U-5 全部被 DESIGN 消费 | ✅ | 逐一映射：F-1/F-2→D1、F-3→D2、F-4→D7、F-5→D4/D8、F-6→D10/D11（影响面声明：report.py 不渲染，证据层读数仅进 JSON+warning）、F-7→D8/INV-1、F-8→D9、F-9→INV-2；U-1~U-5→§11.1 四元块 5/5（Step 4 门禁 c 实核）。主会话 grep 实核 RESEARCH F-1~F-9 总表存在（L75-83） |
| 无文档间矛盾（口径、公式、边界计数） | ✅ | 统计量公式 `-(Σa·y/Σa)×1e4` 与 `share=clip(-Σaxy/Σax²,0,1)` 三文档一致；RESEARCH §3.5「待 E1」占位与 DESIGN「不预设新读数」一致。Step 8 发现并修复 CHECKLIST 自身 2 处缺口（`reversal_counts` 14→15 键；版本号验收项缺失→§2.3 补行），非上游矛盾 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN §3.2 六模块在 IMPLEMENTATION §3 一一对应 | ✅ | IMPL §3.1-§3.6 六小节 ↔ DESIGN §3.2 六行（职责/输入/输出/低效排除逐一对应；Step 6 复审门禁 a 实核） |
| IMPLEMENTATION §4 接口签名与 DESIGN §4.1-§4.4 一致 | ✅ | `cross_section_reversal` 返回七键 + `buy/sell` 扁平四键（Step 6 R-1 补全 return）；`_has_reversal_events` 判定规则（五键齐备且等长）一致；runner 键序一致 |
| DESIGN §8 的 INV-1~INV-10 在 IMPLEMENTATION §7 有实施位置 | ✅ | IMPL §7 表 10 行逐一映射：INV-1/2/3→不改默认路径+payload 未触碰、INV-4→白名单外、INV-5/6/10→端点夹逼+共享重抽样+seed 透传、INV-7→attach_panel_meta 不增键、INV-8→L589 字符串冻结（Step 9 前 L557-558） |
| 无设计未覆盖的实施 | ✅ | `_degraded_reversal` 已声明为 DESIGN §4.1 退化分支内部实现（IMPL §9.3）；Step 6 复审无「设计未覆盖」发现 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION §10 十步实施序每步在本文件有验收项 | ✅ | Step 1（先红）→§2 全部测试行；Step 2→§2.1；Step 3-5→§2.2；Step 6→§2.3/§3.4；Step 7→§3.5；Step 8 版本号→**§2.3 第二行（Step 8 本步补齐缺口）**；Step 9→§2.4/§6；Step 10→§8 |
| 本文件每个验收项可追溯到 IMPLEMENTATION 的 §/T 编号 | ✅ | §2.1-§2.3 每行标注 T3100-x；§3 各接口标注 IMPL §3.x/§4.x；§4 标注 IMPL §7 行；§5 标注 DESIGN §7 行 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| `temporary_share` | 三元组 `[point, lo, hi]` | 同 | 同（真/旧两分支同形） | ✅ |
| `temporary_basis` | `cross_section_t1` / `portfolio_ar1_proxy` | 同 | 同 | ✅ |
| `reversal_bps` | `-(Σa·y/Σa)×1e4` | 同 | 同（`point/lo/hi` 三键） | ✅ |
| `price_basis` | C1 `adj_close_to_close_cs` / C2 `adj_intraday_open_close` | 同 | 同 | ✅ |
| `reversal_counts` | 过滤计数 dict（含 `n_limit_down_unavailable`） | 同 | 同（九步↔键映射） | ✅ |
| `degraded` | 退化标记（`cluster<3` 或 `Σax²=0`） | 同 | 同 | ✅ |

## 2. 功能验收

### 2.1 core 统计量（`cross_section_reversal`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 买入 + 次日跌 → 正反转 | `pytest -k T3100_1` | `reversal_bps.point > 0` | ✅ | T3100_1 passed（`test_execution_capacity.py` L268） |
| 卖出 + 次日涨 → 正反转 | `pytest -k T3100_2` | `point > 0`；符号反向时 `< 0` | ✅ | T3100_2 passed（L281） |
| 全体 t+1 收益平移不变 | `pytest -k T3100_3` | 平移前后 `point` 差 < 1e-12（demean 前置） | ✅ | T3100_3 passed（L293） |
| 退化：`Σ a x² = 0` / `n < 3` | `pytest -k T3100_8` | `temporary_share == [0,0,0]`、`degraded is True`、`reversal_bps` 三值 NaN | ✅ | T3100_8 passed（L325） |
| 聚类 bootstrap 端点与复现性 | `pytest -k T3100_9` | `point ∈ [lo, hi]`；同 seed 双跑逐位一致 | ✅ | T3100_9 passed（L350）；39 月 C1 双跑 JSON 逐键相等 |

> 组级证据：`python -m pytest -q tests/test_execution_capacity.py tests/test_minute_panels.py -k "T3100 or reversal_branch"` → **11 passed / 45 deselected**（0.34 s）。

### 2.2 事件构造（脚本层）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 停牌 t / t+1 剔除 + 计数 | `pytest -k T3100_4` | 对应事件不入样本；`n_suspended_t` / `n_suspended_t1` 递增 | ✅ | T3100_4 passed（L424）：8→7→6 |
| 涨跌停与 `limit_down` 镜像 | `pytest -k T3100_5` | 买入涨停 / 卖出跌停 / t+1 涨跌停均剔除；`limit_down` 缺失时 `n_limit_down_unavailable is True` | ✅ | T3100_5 passed（L442）：`n_limit_up_t=1 / n_limit_down_t=1 / n_limit_t1=1`；注入 None 后 `unavailable=True` |
| 首期建仓打标 | `pytest -k T3100_6` | `n_first_period > 0` 且该事件不剔除 | ✅ | T3100_6 passed（L463）：`n_first_period=2`、`n_events=8` |
| 除权日无假反转 | `pytest -k T3100_7` | `adj_price` 连续；构造除权日 `reversal_bps` 未异常放大 | ✅ | T3100_7 passed（L472）：原始价减半后 `rt/rt1` 逐位不变；C2 复权因子 ×137 后 `|rt|<0.5`、`n_extreme=0`（E-3 回归） |

### 2.3 装配层、兼容回退与版本号

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 无事件字段 → 回退旧代理 | `pytest -k T3100_10` | `temporary_basis == "portfolio_ar1_proxy"`；`temporary == {"r1","rev1"}`；warning 逐字等于 L589 原文（Step 9 前 L557-558） | ✅ | T3100_10 passed（`test_minute_panels.py` L659）：warning 以字面量断言（非引用常量），`temporary_keys={r1,rev1}` |
| 版本号 5 处更新为 3.9.5 | `pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` | `__version__ == "3.9.5"`（config_v2 L371 / __init__ L58 / reporting L40）+ 2 处测试断言一致（IMPL §10 Step 8 / E-1 口径） | ✅ | 两文件 **12 passed**（8.84 s，含 `test_execution_architecture.py`）；`git diff` 仅版本行变更（config_v2/`__init__`/reporting/pyproject 各 1 行 + 2 测试断言） |

### 2.4 Step 9 校准实测（39 月）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| C1 主口径产出 | `verify_capacity_impact.py --calibrate` | `reversal_price_basis == "adj_close_to_close_cs"`；`reversal_bps.point` 有限 | ✅ | `out/v3100_calibration.json`：basis `adj_close_to_close_cs`、point **−2.842**、CI `[−14.974, +10.366]`、n=251 678、n_months=72 |
| C2 稳健性对照产出 | 同命令切 C2 | `reversal_price_basis == "adj_intraday_open_close"`；两口径均已记录 | ✅ | `out/v3100_calibration_c2.json`：basis `adj_intraday_open_close`、point **−2.420**、CI `[−11.810, +5.938]`、n=251 744（E-3 修正后重跑） |
| U-1 主口径判据 | 两口径对照表 | 同号且量级差异 ≤50%，或分歧有书面裁决 | ✅ | 同号（均 <0）；量级差 point **14.8%** / buy **12.9%** / sell **13.5%**，均 ≤50% → **自动通过**，无需书面例外 |
| 新旧读数对照表 | 真实现 vs `temporary_proxy_ar1` | 表落 RESEARCH §3.5（替换「待 E1」），含 `share` 与 `reversal_bps` 双列 | ✅ | RESEARCH §3.5 已替换为 C1/C2 × 新/旧对照表（`share` 与 `reversal_bps` 双列） |
| `limit_down` 计数或退化披露 | 读 `reversal_counts` | `n_limit_down_t > 0` 且买卖对称，或 `n_limit_down_unavailable is True` + warning | ✅ | C1 `n_limit_down_t=595`（卖出侧）、`n_limit_down_unavailable=false`；`n_limit_up_t=0` 属预期（形成日持仓取自 `tradable`，已剔除涨停，买入侧无涨停事件），与卖出跌停侧镜像 |
| 39 月重跑逐位一致 | 同参数跑两次 | `reversal_bps` / `share` 两次逐位相同（INV-10） | ✅ | `out/v3100_calibration.json` 与 `%TEMP%\v3100_c1_rerun.json` **JSON 逐键相等**（含 `reversal_bps`/`temporary_share`/`reversal_counts`） |

> **勘误 E-2（覆盖月数口径）**：DESIGN/CHECKLIST 原写「39 月」，39 为**分钟层**覆盖；证据层锚定月频形成日全集，实测 **73 个形成月 / 72 个有效聚类**。二者与旧代理同域、可比性更强；不改代码，登记为文档勘误（IMPLEMENTATION §11 / RESEARCH §3.5 同步）。

## 3. 接口验收

### 3.1 `core/impact.py::cross_section_reversal`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名与 DESIGN §4.1 一致 | `(rt, rt1, side, weight, month, n_bootstrap=1000, seed=20261121)` 完全一致 | ✅ |
| 返回键完整 | `temporary_share` / `reversal_bps` / `buy` / `sell` / `n` / `n_months` / `degraded` 七键齐备 | ✅ |
| `buy` / `sell` 结构 | 扁平四键 `{'point','lo','hi','n'}`，与 DESIGN §4.1 v1.1 一致 | ✅ |
| 退化输入不抛异常 | 空数组 / 长度不一致 → 返回 `degraded=True`，无 `raise` | ✅ |

### 3.2 `scripts/verify_capacity_impact.py::build_reversal_events`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名与 DESIGN §3.3 约定一致 | `(P, w, price_basis='adj_close_to_close_cs')` | ✅ |
| 返回六键 | `rt / rt1 / side / weight / month / price_basis` 齐备且等长 | ✅ |
| 无事件返回 `None` | 空 `w` 或全过滤 → 返回 `None`（不抛） | ✅ |

### 3.3 `shell/panels.py::_has_reversal_events`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 五键齐备且等长 → `True` | 正常事件 dict | ✅ |
| 任一键缺失 → `False` | 旧代理 dict（`r1/rev1`） | ✅ |
| 长度不一致 → `False` | 人为截断一个数组 | ✅ |

### 3.4 `panels.build_daily_panels` 输出契约

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 真实现四键 | `temporary` / `temporary_basis` / `temporary_proxy_ar1` / `reversal_counts` 齐备 | ✅ |
| 回退两键 | `temporary={"r1","rev1"}` + `temporary_basis="portfolio_ar1_proxy"` | ✅ |
| `reversal_counts` 键集 | 含 DESIGN §4.2 全部 **15 键**（n_events/n_months/n_buy/n_sell/n_first_period/n_suspended_t/n_suspended_t1/n_limit_up_t/n_limit_down_t/n_limit_t1/n_st/n_tiny/n_extreme/n_missing/n_limit_down_unavailable），值为 `int`/`bool` | ✅ |
| `cost_by_h` 段零改动 | `git diff` 仅触及 temporary 装配区，L684-689 未变 | ✅ |

### 3.5 `shell/runner.py` 结果键

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| `temporary_share` 形态不变 | 真实现取 `cross_section_reversal['temporary_share']`；回退取旧三元组 | ✅ |
| `reversal_bps` 仅真实现 | 含 `point/lo/hi/buy/sell/n/n_months/price_basis` | ✅ |
| `reversal_price_basis` | 真实现为 `price_basis` 值；回退为 `None` | ✅ |
| 旧路径逐字保留 | L524-541 回退分支代码与基线一致 | ✅ |

## 4. 不变式验收

| 不变式（DESIGN §8） | 验证方法 | 状态 |
|---------------------|---------|------|
| INV-1 默认 SHA 不变 | `sha256sum out/capacity_impact.json` before/after | ✅ |
| INV-2 `panel_hash` 不变 | before/after 逐位比对 | ✅ |
| INV-3 成本/容量不变 | JSON 中 `cost_by_h`/`net`/`rho`/`alpha0`/`capacity` 子对象逐位比对 | ✅ |
| INV-4 `core/decay.py` 零改动 | `git diff backtest/execution/core/decay.py` 空 + `__all__` 5 项 | ✅ |
| INV-5 `point ∈ [lo, hi]` | T3100-9 + 39 月读数抽查 | ✅ |
| INV-6 两读数共享重抽样 | 代码读 + T3100-9（同 seed 下两读数同源派生） | ✅ |
| INV-7 事件数组不落盘 | 工件键扫描无 `rt/rt1/side/weight/month`；工件大小 < 基线 +2 MB | ✅ |
| INV-8 回退 warning 逐字 | T3100-10 字符串相等断言 | ✅ |
| INV-9 零新增依赖 / Python 3.9 | `git diff requirements*.txt` 空；AST 扫描无 3.10+ 语法 | ✅ |
| INV-10 固定 seed 可复现 | 39 月双跑逐位一致（§2.4 末项） | ✅ |

> 逐项证据：INV-1 默认工件重跑与 `out/capacity_impact.json` 逐键相等，SHA `82728CE103D49AF2…`；INV-2 三份工件 `panels.panel_hash = dfcc4e1d…` 全等；INV-3 `out/v3100_calibration.json` vs `out/v394_calibration.json` 的 `panels/capacity/decay/models/impact_curve/impact_samples/config_hash` 全部 `==`；INV-4 `git diff` 空且 `impact.__all__` 恰 5 项（decay 未触及）；INV-5 C1 `[-14.974, −2.842, +10.366]`、C2 `[-11.810, −2.420, +5.938]`、buy/sell 同；INV-6 代码单次 `stationary_bootstrap_indices` 派生；INV-7 工件 5.15 MB = 基线 5.15 MB、无事件数组键；INV-8 断言为字面量；INV-9 `requirements*.txt` 无 diff，7 个改动文件 `ast.parse(feature_version=(3,9))` 全部通过（无 3.10+ 语法）；INV-10 C1 双跑 JSON 全等。

## 5. 错误处理验收

| 错误场景（DESIGN §7） | 触发方式 | 预期行为 | 状态 |
|----------------------|---------|---------|------|
| 事件 < 3 或 `Σ a x² = 0` | 合成退化输入 | `share=[0,0,0]`、`bps=NaN`、`degraded=True`；warning `cross_section_reversal_degraded` | ✅ |
| `n_months < 3` | 2 个月事件 | 同上 | ✅ |
| 五键长度不一致 | 截断一个数组 | `_has_reversal_events=False` → 回退 | ✅ |
| 长度不一致到达 core | 直接调用新函数 | 返回退化结构，不抛 | ✅ |
| `stock_low.pkl` 缺失/单位不符 | 临时改名或注入空 | `limit_down=None` → `n_limit_down_unavailable=True` + warning | ✅ |
| `t+1` 超出面板末端 | 末月事件 | 剔除 + `n_missing` 递增 | ✅ |
| `temporary` 空 | 最小测试面板 | `temporary_share=None`（与今日一致） | ✅ |

> 证据：前 4 行由 T3100_8 覆盖（`Σax²=0` / 2 个月 / 长度 4 vs 3 / 全空四例均 `degraded=True` 且不抛）；第 5 行 T3100_5 注入 `limit_down=None` 后 `unavailable=True`，`load_implementability` 读失败分支见 `verify_long_side_research.py` 的 `(OSError, ValueError, KeyError, TypeError) → None`；第 6 行静态核验 `build_reversal_events` 的 `pos + 1 >= len(dates)` → `n_missing`；第 7 行静态核验 `temporary={}` → runner `elif temp` 不成立 → `ts=None`。

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| 39 月校准总耗时 | 相对 v3.9.4 基线劣化 ≤20% | **16 min 06 s**（17:47:02→18:03:08）vs 基线 ≈14.5 min → **+11%** | ✅ |
| 分钟层峰值内存 | ≤ 300 MB（v3.8.1 既有约束） | 分钟层未改动，v3.8.1 实测 296.6 MB 维持；本批新增日频矩阵另计（见下行） | ✅ |
| 日频矩阵增量内存 | < 100 MB（`open_adj` + 4 个 bool 矩阵） | **96.0 MB**（`open_adj` 64.0 + `impl_daily` 32.0；矩阵 1475×5688） | ✅ |
| bootstrap 复杂度 | `O(n_bootstrap × n_months)`，1000×39 单次 < 50 ms | **2.4 ms**（n=4000、39 个月、1000 reps） | ✅ |

> **披露（口径边界）**：`build_panels` 全量装载的 tracemalloc 峰值为 **2942.8 MB**、稳态 273.9 MB。该峰值属于既有「日频全市场装载」口径（含 close/adj/amount/mv 等多张 1475×5688 矩阵），与 v3.8.1 的「单月分钟层峰值」不是同一度量；本批仅新增上表 96.0 MB，未改分钟层路径。

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.9 | ✅ | 7 个改动文件 `ast.parse(feature_version=(3,9))` 全部通过 |
| Python | 3.10+ | ✅ | 本机 3.13.5 全量 `pytest` 2076 passed / 15 skipped / 0 failed |
| OS | Windows | ✅ | 主环境（Windows / PowerShell） |
| 依赖 | 零新增 | ✅ | `git diff requirements*.txt` 空；仅用 numpy/pandas 既有依赖 |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 0.90 | 公式/读数/15 键计数可精确断言；扣分：INV-6/INV-7 测试映射不实、T3100_3/9 部分恒真 |
| 模块映射 | 1.00 | DESIGN §3.2 六模块与代码逐一命中（impact L261 / script L174 / panels L543 / runner L527） |
| 接口契约 | 0.95 | 键结构、签名、默认 `seed=20261121` 精确；扣分：`n_months` 同名异义（73 形成月 vs 72 聚类） |
| 修正项 | 0.85 | E-1/E-3 闭环；E-2 原未进 DESIGN（本轮已补 §12.4）；锚点原未刷新（本轮已刷新） |
| 跨模块契约 | 0.90 | script→panels→runner→工件链闭合；INV-1/2/3/7 实证；INV-6 缺独立测试 |
| **总分** | **4.60/5** | **档位: 优秀（A）** |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P2 | INV-6「买卖共享同一组重抽样索引」无有效测试；原以 T3100-9 覆盖的说法不成立 | `impact.py` 单 `idx` 实现正确；T3100_9 仅断言可复现/端点，若 buy/sell 各抽 `seed`/`seed+1` 仍会通过 | monkeypatch `stationary_bootstrap_indices`，断言仅调用 1 次且 buy/sell 取同一 idx |
| P2 | 脚本层截面 demean 无测试 | `verify_capacity_impact.py` L192；T3100_3 输入已 demean 且 side 平衡，删除该行测试仍过 | 在 `_event_panel` 断言形成日 demean 后截面均值 ≈0 |
| P3 | T3100_3 `allclose(base, shifted)` 为恒真式；平移不变由 side 平衡导致 | `test_execution_capacity.py` L307-311 | 删除恒真断言，改为直接断言 demean 幅度 |
| P3 | T3100_9 端点断言半同义反复（`_interval` 以 min/max 强制夹逼） | `impact.py` L258；`test_execution_capacity.py` L365-368 | 增加已知分位断言（如常数输入 lo=hi=point） |
| P3 | 文档锚点漂移 | DESIGN L203、IMPL L155/L300 原称 panels L557-558（实际 L589）；IMPL L295 原称 L647-652（实际 L684-689）；runner 回退实为 L524-541 | **本轮已修复**（DESIGN v1.3 §12.4 / IMPL v1.2） |
| P3 | DESIGN 仍写「39 月」且无 E-2 登记 | DESIGN L124/L133/L358/L377 | **本轮已修复**：DESIGN §12.4 登记 E-2 |
| P3 | CHECKLIST 头部版本过期 | L17 写 IMPL v1.1（实际 v1.2）、L19 写 RESEARCH v1.2（实际 v1.3） | **本轮已修复** |
| P3 | counts 15 键维度无整体断言 | tests 仅逐字段断言，无 `len(counts)==15` | 补字面量集合断言 |

> **裁决**：**PASS_WITH_FIXES**，0×P1（无阻塞）。2×P2 属测试有效性补强，不影响口径 A 结论；P3 中 3 项文档类已在本轮回填关闭，剩余 3 项测试类登记为后续批次。

### 8.3 ADD Iron Law 检查

- [x] 测试通过的 4 类盲区已检查：
  - **断言恒真式**：**有**。`test_T3100_3` L307 恒真；`test_T3100_9` L366-368 端点夹逼由构造保证。T3100_1/2/4/5/6/7 断言强（精确值、8→7→6、复权 ×137 不变）。
  - **单文件检查盲区**：**无**。core（T3100_1/2/3/8/9）、脚本（T3100_4/5/6/7）、装配（T3100_10）、runner（`test_runner_reversal_branch`）四层独立断言齐备。
  - **设计独有约束无测试**：**有**。INV-6、INV-7 仅静态核验/工件扫描（INV-7 实扫无数组键，实现正确但无回归测试）。
  - **修正阻断性项无测试**：**无**。E-1 五处版本均有断言（`test_fix3_version_unification.py` 01/02/03/06 + `verify_fix3_manual.py` 子进程）。
- [x] 未发现 P1 阻塞项。

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md（v1.3 verified） | ✅ | ✅ |
| DESIGN.md（v1.3 verified） | ✅ | ✅ |
| IMPLEMENTATION.md（v1.2 verified） | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR（本批无结构变更，N/A 需显式登记） | ✅ N/A | N/A |
| 开发日志（`CHANGELOG.md` v3.9.5 条目） | ✅ | ✅ |

> **统计口径说明**：本节 6 项为文档存在性检查，按模板口径不并入 §10.1 八类统计。

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 17 | 17 | 0 | 0 |
| 接口 | 18 | 18 | 0 | 0 |
| 不变式 | 10 | 10 | 0 | 0 |
| 错误处理 | 7 | 7 | 0 | 0 |
| 性能 | 4 | 4 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 6 | 5 | 0 | 1 |
| **总计** | 81 | 80 | 0 | 1 |

> **统计口径（RULE-2）**：上表来自本文件逐项核对（§1-§8 每行一个 ☐/✅），非事后汇总推算。逐行 `总数 = 通过 + 失败 + 待办` 恒成立；总计行 = 八类按列求和（15+17+18+10+7+4+4+6 = 81）。
> **Step 10 时点说明**：ADD 6 项中 Phase 0 五维全部通过（4.60/5，A 档）；第 6 项「Iron Law 盲区闭合」因 2×P2 测试有效性缺口记为**待办**（§8.2），不计失败。

### 10.2 验收决定

- [ ] **验收通过**：所有 P1 项通过，无阻塞性问题
- [x] **有条件通过**：0×P1、2×P2（测试有效性补强）+ 3×P3（测试类）待后续批次；口径 A 结论与工件不变式全部成立
- [ ] **验收失败**：—

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | 主会话（P-003 Step 1-9） | 2026-11-21 |
| 审查者（Step 10 独立子代理） | 独立只读审计子代理（d06e1d61） | 2026-11-21 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 文档一致性逐项核（§1） | 实施者 | Step 8 | ✅ |
| Step 9 实测回填（§2.4/§4/§6 证据列） | 实施者 | Step 9 | ✅ |
| Step 10 ADD 审计（§8） | 独立子代理 | Step 10 | ✅ |
| P2 测试有效性补强（INV-6 monkeypatch 共享索引 + 脚本层 demean 断言） | 实施者 | 后续批次 | ☐ |
| P3 测试类补强（T3100_3 恒真断言、T3100_9 已知分位、counts 15 键整体断言） | 实施者 | 后续批次 | ☐ |
| 更新 PROGRESS.md（P-003 → done；新增 P-016） | 实施者 | 批次收尾 | ✅ |
| 记录开发日志 + CHANGELOG（v3.9.5 条目） | 实施者 | 批次收尾 | ✅ |
| E-TODO 出口门禁（SPEC_COMPLIANCE §7 映射率 100%） | 实施者 | 批次收尾 | ☐ |

### 11.1 偏差与裁决登记（Step 9）

| # | 项 | 结论 | 处置 |
|---|---|---|---|
| U-1 | C1 vs C2 口径一致性 | **自动通过**：同号（均 <0），相对差 14.8% / 12.9% / 13.5%（≤50%）。C2 首轮异常（`n_extreme=36 445`、buy +773.9 bps）已定位为公式 bug 并修复（E-3） | C1 主口径、C2 稳健性对照，均入工件 |
| U-3 | bootstrap 次数/种子敏感性 | **通过**：9 组（1000/2000/5000 reps × 3 seeds）share 端点极差 lo 0.000000 / hi 0.005508（≤0.01） | 固定 `n_bootstrap=1000, seed=20261121` |
| U-5 | 截面基准敏感性 | **部分通过**：外部基准（全市场 vs 可投资域）相对差 **0.2%**；事件样本等权相对差 **33.3%** | 「事件自身等权」是自指基准（用被度量样本自身的截面均值），必然压低事件加权均值，不构成独立基准；判据只对**外部基准**生效，登记为已知口径性质，不视为回归 |
| E-2 | 覆盖月数 | 73 形成月 / 72 有效聚类（文档原写 39 月为分钟层） | 登记勘误，不改代码 |
| MEM | 内存口径 | 分钟层未改（v3.8.1 296.6 MB 维持）；本批日频增量 96.0 MB；`build_panels` 全量峰值 2942.8 MB 属既有日频装载口径 | 已在 §6 披露，避免与分钟层约束混用 |

---

**Step 8 结论**：文档一致性 **15/15 通过**。核验过程中发现并修复 CHECKLIST 自身 2 处缺口（均非上游文档矛盾）：① §3.4 `reversal_counts` 键数 14→**15**（DESIGN §4.2 实数 15 键）；② IMPLEMENTATION §10 Step 8（版本号 5 处）缺直接验收项 → §2.3 补行，功能类 16→17、总计 80→81。等价性依据：D1-D12/F-1~F-9/U-1~U-5 映射（§1.1）、六模块/四接口/INV-10（§1.2）、十步序全覆盖（§1.3）、六术语三文档一致（§1.4）。
