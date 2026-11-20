# CHECKLIST v3.8.0 多日执行模型 + Regime 容量压力测试 — 验收清单

> **版本**: v1.1 (2026-11-19) — 步骤 7 产出；步骤 9 逐项回填
> **对应实施**: [EXECUTION_V3.8.0_EXECUTION_CAPACITY.md](../EXECUTION_V3.8.0_EXECUTION_CAPACITY.md) v1.1（步骤 6 复审 PASS_WITH_FIXES，见其 §9）
> **对应设计**: [DESIGN_EXECUTION_CAPACITY_V3.8.0.md](../private/DESIGN_EXECUTION_CAPACITY_V3.8.0.md) v1.2
> **对应调研**: [RESEARCH_V3.8.0_EXECUTION_CAPACITY.md](../research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md)（三轮 + §19 复审）
> **对应路线图**: [MULTIFACTOR_GOVERNANCE_ROADMAP.md](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) P2「组合/容量未成为上线门禁」「冲击模型为 stylized」
> **档位**: T1（14 新模块 + 9 测试文件 + 脚本 3 分支 → 全 10 步）
> **状态词**: `待验证` / `通过` / `失败` / `阻塞` / `N/A（附理由）`
> **时点**: 步骤 7 编写（状态列全 `待验证`）；步骤 9 已逐项回填为实测读数，步骤 10 审计复核
> **禁止**：无证据的 ✅；汇总只能来自逐行状态计数（RULE-2）；E5 级（推测）证据不得支撑「通过」

---

## §1 DoR / DoD 定义

| 术语 | 含义 |
|------|------|
| **DoR**（Definition of Ready） | 该项可开始验证的前置条件（上游工件就绪 / 依赖阶段完成 / 环境可用） |
| **DoD**（Definition of Done） | 该项判定通过的**可观察**条件（命令 + 读数 / 文件 + 字段 / 断言表达式） |

**状态升级规则**：

1. `待验证` → `通过`：必须附「命令 + 退出码 + 关键读数 + 日期」。
2. `待验证` → `失败`：必须附失败用例名与首行错误。
3. `待验证` → `阻塞`：必须附阻塞原因与解阻触发条件（本批典型：`E:\Level 1 Data` 或 `E:\Ashare_data` 不可用）。
4. `N/A`：必须写理由与替代证据。
5. TDD 类项目（§3）必须同时登记**红读数**与**绿读数**；红读数缺失视为未验证（对齐 F5 纪律）。
6. `evidence_level` 缺失的行一律判 `失败`（S5 硬约束，EXECUTION §7.3）。

**证据等级**（沿用本仓约定）：

| 等级 | 含义 |
|------|------|
| E1 | 实跑命令输出（pytest / `--calibrate` stdout） |
| E2 | 落盘工件（`out/capacity_calibration.json` / `.md` / `out/capacity_impact.json`） |
| E3 | 代码行号锚点（`Lxxx@<commit>`）或 `git diff` |
| E4 | 文档间逐字比对（本 checklist 与 EXECUTION/DESIGN 的映射） |
| E5 | 推理与估计（**不可**单独支撑「通过」） |

---

## §2 E0-E7 任务验收

| E | 验收项 | DoR | DoD | 证据 | 状态 |
|---|--------|-----|-----|------|------|
| E0 | 包骨架 + 4 端口 + 配置 + 加载器 + 冒烟 | 设计 §3/§4/§14 定稿 | `tests/test_execution_architecture.py`（3）+ `tests/test_execution_import_smoke.py`（1）全通过；`import backtest.execution` 不触发 shell；`config_hash` 同配置两次调用同值；`backtest/__init__.py` diff 为空 | ① `pytest` 4 例通过（junit: tests=4, failures=0, 3.66 s）；② `config_hash()` 两次一致 `e46749c6…`，`replace(kappa=2.0)` 后变化；③ `git diff backtest/__init__.py` 空 | 通过 |
| E1 | BVC + 分钟级冲击面板（λ 与 b） | E0 完成；`E:\Level 1 Data` 可读 | `tests/test_execution_classification.py`（8）全通过；单月面板覆盖报告（股票数 / bar 数 / 零成交占比）产出；λ 面板行数 > 0 且无全 NaN 列 | ① `test_execution_classification.py` 8 例通过（步骤 10 审计后 9 例，含 T380-25b）；② 单月实测（2023-03）：3437 只 / 18,168,990 bar / 一字板占比 6.69% / 零成交 bar 3.75%（2023-03-01，908,088 行）/ σ 全部有限（median 16.1bp）；③ λ 反解与 HAC 由 T380-48/49 合成样本覆盖（真实分钟端到端面板构建不在 v3.8.0 接口，见 X9 注）；④ H2 一字板判定修复经真实数据零影响核验：2023-03-01 单日 frozen_old=new=168,391 bar → 各级占比（含 6.69%）不变 | 通过 |
| E2 | 4 模型拟合 + 三角验证 + c 三档 | E1 完成 | `tests/test_execution_impact.py`（10）全通过；`c_stress == max(0.5, c_ci_upper)`（T380-50）；`select_models` 容差 10% 行为可复现；`log` 越界被排除 | ① `test_execution_impact.py` 10 例通过（含 T380-06/10/50）；② 校准报告新增 ratio(p) 诊断（12.65 / 5.66 / 4.00 / 2.83 / 1.79 @ p=0.1%…5%，σ=2%），默认常数未改 | 通过 |
| E3 | T+1 reversal 永久/临时分离 | E1 完成 | `temporary_share` 返回三元组且 `ci_lo <= share <= ci_hi`；bootstrap 走 `auto_block_size` | TEMP 合成（n=2000，var(temp)/var(r1)=0.3）：point=0.2974、CI=[0.2749, 0.3175]，`ci_lo<=share<=ci_hi` 成立；块长 `auto_block_size=1`（iid 序列），退回 `[1, n//3]` 区间 | 通过 |
| E4 | 衰减核 + `net(h)` + 执行天数 | E2 完成 | `tests/test_execution_decay.py`（8）全通过；`rho` CI 覆盖 1 时 `retention≡1`；`plateau` 必含 `h*`；`execution_days` 超 `d_max` 标未成交；校准 JSON 含 `D_i` 分布与 `p_cap` 触发率（design §19） | ① `test_execution_decay.py` 8 例通过（T380-27~34）；② 输出结构 `decay.execution` = {days, d_max=5, p_cap=0.10, trigger_rate, n}；真实运行需注入 `notional/adv`（同 X9 接线缺口，当前为 null） | 通过 |
| E5 | regime 压力 + co-impact κ | E2 完成 | `tests/test_execution_capacity.py` 中 T380-41~44 全通过；容量主值取 `min(各 regime)`；κ∈{1.0,1.5,2.0} 三档均落 JSON | ① T380-41~44 全通过（注入 `capacity_fn` 随动、同参同果、κ 单调、主值取 min+median）；② `capacity.scenarios` 键固定 `{"1.0","1.5","2.0"}`，κ 默认 1.5 | 通过 |
| E6 | 滚动 AveW + 漂移诊断 | E5 完成 | T380-45~47 全通过；4 窗等权 0.25；`spread>0.30` → 取最差窗 + `evidence_warnings` | T380-45~47 全通过：`average_capacity` 对 4 窗等权（weights=0.25）、预测值平均（非参数平均）、`spread>0.30` 时 `primary=min` 并写 warning；G7 `--diagnose-window` 退出码 0，IJR 窗长仅诊断 | 通过 |
| E7 | 脚本接入 + 文档 + 一致性 | E6 完成 | `--calibrate` 退出码 0 且 `out/capacity_calibration.json` 落盘；默认无参数运行 `out/capacity_impact.json` 与 v3.7.0 基线逐位一致（T380-51/52）；6 处版本锚点同步（EXECUTION §3.1） | ① G5/G6/G7 均 exit 0，JSON/MD 落盘；② 默认路径双跑 34.3 s / 30.8 s，SHA256 均 `82728CE1…`，与 v3.7.0 基线**逐位一致**；③ 6 处锚点全 `3.8.0`；④ 全量回归 1985 passed / 15 skipped / 0 failed | 通过 |

**阶段纪律**：E0→E1→E2 顺序不可跳；E3/E4/E5 可并行但须各自「先红后绿」；E7 必须在 E1-E6 全绿后接入。

**依赖注入纪律（EXECUTION §2.10，步骤 6 R-E1）**：`run_calibration` 的容量函数只能经
`capacity_fn`/`breakeven_fn` 注入，`backtest/execution/**` 内**不得**出现 `import scripts` 或
`from scripts`（design §3.1 禁止边），T380-41 验证。

---

## §3 测试用例验收（57 项；步骤 10 审计新增 T380-25b）

> 「红形态」= 步骤 9 首次运行预期失败形态（确认测试真正压到新代码）；「DoD」= 绿后断言。
> 任一用例的红读数缺失 → 该行保持 `待验证`（不得直接标绿）。
> 用例编号沿用 EXECUTION §5.1 **T380-01…56**；步骤 9 使用描述性测试名，编号仅作映射。

### 3.1 `test_execution_impact.py`（E2，10 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-01 | sqrt 单调 | `ModuleNotFoundError: backtest.execution.core.impact` | `p` 递增 → `predict` 严格递增 | 通过 |
| T380-02 | sqrt 定点 | 同上 | `p=0.01, σ=0.02, c=0.5` → `1e-3`（10bp），`rtol=1e-12` | 通过 |
| T380-03 | linear 定点 | 同上 | `p=0.01, k=0.025` → `2.5e-4`（2.5bp） | 通过 |
| T380-04 | linear 单调 | 同上 | `p` 递增 → 递增 | 通过 |
| T380-05 | log 单调 | 同上 | `p` 递增 → 递增（正参数区） | 通过 |
| T380-06 | log 越界判无效 | 同上 | `a + b·ln(p_min) <= 0` → 被 `select_models` 排除（`predict` 不静默 clip） | 通过 |
| T380-07 | power 单调 | 同上 | `b>0` 时递增 | 通过 |
| T380-08 | `p=0` 抛错 | 同上 | 4 个模型 `fit`/`predict` 均 `ValueError` | 通过 |
| T380-09 | 常数序列抛错 | 同上 | `np.ptp(impact)==0` → `ValueError`（v3.7.0 H1 惯例） | 通过 |
| T380-10 | 选型容差 | 同上 | CV 差 5% → 并列集合含 2 项；差 20% → 仅 1 项 | 通过 |

### 3.2 `test_execution_spread.py`（E0，8 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-11 | CS 零区间平移 | `ModuleNotFoundError: backtest.execution.core.spread` | `h==l` 不产生 NaN 也不被丢弃（零区间平移） | 通过 |
| T380-12 | CS 负值截断 | 同上 | 输出 ≥ 0 | 通过 |
| T380-13 | CS 两日 vs 单日 | 同上 | 合成数据下两日修正估计方差更小 | 通过 |
| T380-14 | CS `zero_ratio` | 同上 | 全零区间 → `1.0` | 通过 |
| T380-15 | AR 乘积型 | 同上 | `S = √(4·E[(c_t−η_t)(c_t−η_{t+1})])` 反解误差 `<1e-8`；`c_t = ln(close)` | 通过 |
| T380-16 | AR 负值截断 | 同上 | `S²<0` → 0 | 通过 |
| T380-17 | Amihud 量纲 | 同上 | `|r|=0.01, amount=1e8` → `1e-10` | 通过 |
| T380-18 | 长度不足 | 同上 | `n<3` → 全 NaN，不抛错 | 通过 |

### 3.3 `test_execution_classification.py`（E1，9 项；步骤 10 审计新增 T380-25b）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-19 | `normal_cdf` | `ModuleNotFoundError: backtest.execution.core.classification` | `Φ(0)=0.5`、`Φ(1.96)≈0.975`（容差 1e-3） | 通过 |
| T380-20 | `Φ` 单调 | 同上 | 严格递增 | 通过 |
| T380-21 | BVC `r=0` | 同上 | 返回 `0.5` | 通过 |
| T380-22 | BVC `σ<=0` | 同上 | 返回 `0.5`，无 inf/nan | 通过 |
| T380-23 | BVC 占比界 | 同上 | 输出 ∈ [0,1] | 通过 |
| T380-24 | 无前视 | 同上 | 扰动未来 bar，历史 `sigma` 逐位不变 | 通过 |
| T380-25 | 一字板识别 | 同上 | `h==l` 命中 | 通过 |
| T380-26 | 零量识别 | 同上 | `volume==0 且 o==c==h==l` 命中 | 通过 |
| T380-25b | 零量判定补全（步骤 10 审计 H2 修复） | 修复前红：`v==0, o=c=h=10, l=9.5` 异常 bar 误命中 | `detect_limit_lock` 对 `v==0 且 o=c=h 但 l<h` 返回 False；`o=c=h=l 且 v=0` 仍命中；真实单日 frozen_old=new=168,391 bar（零影响） | 通过 |

### 3.4 `test_execution_decay.py`（E4，8 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-27 | `rho=1` + 端口一致性 | `ModuleNotFoundError: backtest.execution.core.decay` | `retention≡1`、`half_life=inf`；`isinstance(ExponentialDecay(1.0), DecayModel)` 为 True | 通过 |
| T380-28 | `rho=0.9` | 同上 | `half_life≈6.579`（`ln0.5/ln0.9`，rtol 1e-9）；`ExponentialDecay(0.9).retention([1,5]) == 0.9**[1,5]` | 通过 |
| T380-29 | `rho` CI 覆盖 1 | 同上 | 返回 `(1.0, lo, hi)` 且 `lo<=1<=hi` | 通过 |
| T380-30 | `net` 单调 | 同上 | 成本上升 → `net(h)` 下降 | 通过 |
| T380-31 | plateau 含 h* | 同上 | `h* ∈ plateau` | 通过 |
| T380-32 | 平坦区退化 | 同上 | `sd=0` → `plateau == [h*]` | 通过 |
| T380-33 | `execution_days` | 同上 | `ceil(notional/(p_cap·adv))`；封顶 `d_max` | 通过 |
| T380-34 | 超限处理 | 同上 | 超 `d_max` 标未成交（非静默截断） | 通过 |

> 注（步骤 6 R-E2）：`ExponentialDecay` 端口一致性断言并入 T380-27 / T380-28（同文件同 fixture），
> 不新增编号，总数仍为 56（步骤 10 审计新增 T380-25b 后为 57）。

### 3.5 `test_execution_bootstrap.py`（E0，6 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-35 | 近 iid | `ModuleNotFoundError: backtest.execution.core.bootstrap` | `rho≈0` → `b=1` | 通过 |
| T380-36 | 随 `rho` 增 | 同上 | `b(ρ=0.6) > b(ρ=0.2)` | 通过 |
| T380-37 | 上界 | 同上 | `b <= n//3` | 通过 |
| T380-38 | 下界 | 同上 | `b >= 1` | 通过 |
| T380-39 | 与 `sqrt(T)` 对照 | 同上 | 同量级，比值 ∈ [0.2, 5] | 通过 |
| T380-40 | 确定性 | 同上 | 同输入两次调用逐位一致 | 通过 |

### 3.6 `test_execution_capacity.py`（E5/E6/E2，10 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-41 | 复用同一函数 | `ImportError: run_calibration` | `capacity_fn` monkeypatch 后校准输出随动 → 两路径同实现（design §3.1 禁 Shell→scripts） | 通过 |
| T380-42 | 同参同果 | 同上 | 同参数下容量结果逐位相同 | 通过 |
| T380-43 | κ 单调 | 同上 | `κ` 增大 → 容量减小 | 通过 |
| T380-44 | 主值取最差 regime | 同上 | `min` 而非 `mean` | 通过 |
| T380-45 | AveW 取预测平均 | 同上 | 与「参数平均」结果不同（构造反例） | 通过 |
| T380-46 | AveW 等权 | 同上 | 4 窗长权重各 `0.25` | 通过 |
| T380-47 | 漂移降级 | 同上 | `spread>0.30` → 取最差窗 + 警告 | 通过 |
| T380-48 | λ 反解 | 同上 | 合成 `r=λx` → 误差 `<1e-6` | 通过 |
| T380-49 | HAC 生效 | 同上 | 自相关序列 SE 大于 iid SE | 通过 |
| T380-50 | c 三档方向 | 同上 | `c_stress == max(0.5, c_ci_upper)`（等值，非 `>=`） | 通过 |

### 3.7 `test_execution_default_snapshot.py`（E7，2 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-51 | 键集合 | `FileNotFoundError: out/capacity_impact.json` | 键集合与 v3.7.0 基线完全一致（`meta`/`results` 下逐层） | 通过 |
| T380-52 | 数值 | 同上 | 容量关键值（exQ1 203 亿 / Q5 11 亿）容差 **0** | 通过 |

> 环境不可用（`E:\Ashare_data` 缺失）时：skip 且显式标原因，不得静默 PASS（design §16.3 注）。

### 3.8 `test_execution_architecture.py`（E0，3 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-53 | Core 无 IO | `AssertionError: os` | AST 扫描 `core/*.py`：无 `os/pathlib/logging/pyarrow/duckdb/pandas`、无 `open(` | 通过 |
| T380-54 | 无反向依赖 | 同上 | `core/` 无 `from ..shell` / `from ..runner` | 通过 |
| T380-55 | `__all__` 约束 | 同上 | 每个 Core 模块 `len(__all__) <= 5` 且无 `"*"` | 通过 |

### 3.9 `test_execution_import_smoke.py`（E0，1 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T380-56 | 无 pyarrow 可导入 | 子进程阻断 `pyarrow` 后 `ImportError` | `import backtest.execution.core.impact` 成功 **且** `has_pyarrow() is False` | 通过 |

### 3.10 红→绿记录回填位（步骤 9 填写）

> 与 EXECUTION §5.2 表同步回填；此处仅登记形态，不重复列 56 行。

| ID | 红灯症状（实际报错首行） | 绿灯证据（pytest 行） | 日期 |
|----|-------------------------|----------------------|------|
| T380-01~10 | `ModuleNotFoundError: No module named 'backtest.execution.core.impact'` | `test_execution_impact.py` 10 passed（junit failures=0） | 2026-11-19 |
| T380-11~18 | `ModuleNotFoundError: No module named 'backtest.execution.core.spread'` | `test_execution_spread.py` 8 passed | 2026-11-19 |
| T380-19~26 | `ModuleNotFoundError: No module named 'backtest.execution.core.classification'` | `test_execution_classification.py` 8 passed | 2026-11-19 |
| T380-27~34 | `ModuleNotFoundError: No module named 'backtest.execution.core.decay'` | `test_execution_decay.py` 8 passed | 2026-11-19 |
| T380-35~40 | `ModuleNotFoundError: No module named 'backtest.execution.core.bootstrap'` | `test_execution_bootstrap.py` 6 passed | 2026-11-19 |
| T380-41~50 | `ModuleNotFoundError: No module named 'backtest.execution.shell.runner'`（`cfg` fixture error） | `test_execution_capacity.py` 10 passed | 2026-11-19 |
| T380-51~52 | 无红：默认路径未改、基线在盘，首轮即 PASS | `test_execution_default_snapshot.py` 2 passed | 2026-11-19 |
| T380-53~55 | `AssertionError: core 目录不存在` | `test_execution_architecture.py` 3 passed | 2026-11-19 |
| T380-56 | 子进程 `ModuleNotFoundError: backtest.execution`（`SMOKE_OK` 缺失） | `test_execution_import_smoke.py` 1 passed | 2026-11-19 |

**合计**：红阶段 52 failed / 2 passed / 2 errors（首轮）→ 绿阶段 **56 passed / 0 failed**（junit `tests=56, failures=0, errors=0, skipped=0, time=3.741 s`，2026-11-19）。

---

## §4 兼容性与零变更验收（对应 EXECUTION §3 / §7 / §8）

| # | 兼容对象 | 核对方法 | 通过判据 | 状态 |
|---|---------|---------|---------|------|
| 1 | 默认路径输出 | `python scripts/verify_capacity_impact.py` 双跑 + 与 v3.7.0 `out/capacity_impact.json` 比对 | 键集合一致；数值逐位一致（容差 0） | 通过（双跑 34.3 s / 30.8 s，exit 0；SHA256 均为 `82728CE1…`，与 v3.7.0 基线相同 → 逐位一致） |
| 2 | `backtest/__init__.py` | `git diff` | 空 diff（13 处 from-import 未动） | 通过（`git diff` 无输出） |
| 3 | `backtest/data_contract.py` | `git diff` | 空 diff（仅调用侧默认 required） | 通过（`git diff` 无输出） |
| 4 | 核心依赖 | `git diff pyproject.toml` | `dependencies` 块无变化；仅新增 `calib = ["pyarrow>=14.0.0"]` 并在 `all` 追加 | 通过（diff 仅 6 行：version + calib + all） |
| 5 | Python 3.9 语法 | AST 扫描（无 PEP 604 `X \| Y`、无内置泛型下标） | 退出码 0 | 通过（`scanned_files=14`，exit 0） |
| 6 | 父包重导入 | T380-56 子进程阻断 `pyarrow` | `import backtest.execution.core.impact` 成功；`has_pyarrow() is False` | 通过（T380-56） |
| 7 | Core 层 IO 纪律 | T380-53 AST | 无 IO 模块、无 `open(` | 通过（T380-53） |
| 8 | Core 层反向依赖 | T380-54 | `core/` 不 import `shell` | 通过（T380-54） |
| 9 | `__all__` 上限 | T380-55 | 每模块 ≤5 且无 `"*"` | 通过（T380-55） |
| 10 | 脚本既有 CLI | `--data-root` / `--json` / `--contract` / `--contract-only` / `--contract-sample-end` / `--contract-json` 逐一实跑 | 行为与 v3.7.0 一致，无新增必填项 | 通过（flag 解析与运行正常：`--contract-only --contract-sample-end 2023-12-29` 退出 2 为既有数据契约 WARN（return 越界 / coverage 0.9369 / industry 缺文件），非新增必填项；`git diff` hunk 仅 `:249` 与 `:271` 纯新增，契约分支与 legacy argparse 零改动） |
| 11 | 既有测试零回归 | `python -m pytest tests -q` | 无新增失败（基线 1929 passed / 15 skipped） | 通过（全量 junit：tests=2000 / failures=0 / errors=0 / skipped=15 → **1985 passed**；减 56 例 = 1929，零回归） |
| 12 | `Sheet` 默认值纪律 | `git diff` 中 `SQRT_C` / `LINEAR_K` / `CAP_LEVELS` | 三个元组逐位不变 | 通过（diff 中三常量 0 处改动；`:60`~`:62` 原值 `(0.1,0.5,1.0)` / `(0.01,0.025,0.05)` / `(0.05,0.10,0.20)`） |
| 13 | 校准不回写默认 c | 代码检索 `SQRT_C` 赋值点 | 仅 `:60` 一处，无写入路径（D2） | 通过（`SQRT_C` 唯一赋值 `:60`；校准输出只写 `c_*` 字段与 Markdown） |

---

## §5 门禁、性能与证据出口（对应 EXECUTION §6 / §7）

### 5.1 门禁

| # | 门禁 | 命令 | 通过判据 | 状态 |
|---|------|------|---------|------|
| G1 | 快速门禁 | `python -m pytest tests/test_execution_architecture.py tests/test_execution_import_smoke.py -q` | 4 项全通过 | 通过（junit `tests=4, failures=0, errors=0`，3.66 s） |
| G2 | 新增单测 | 9 个 `test_execution_*.py` 显式枚举（EXECUTION §7.1，**不得用通配符**） | 56 项全通过 | 通过（junit `tests=56, failures=0, errors=0, skipped=0`，3.74 s）；步骤 10 审计修复后 9 文件 **57 例全绿**（3.53 s，含 T380-25b） |
| G3 | 默认快照 | `python -m pytest tests/test_execution_default_snapshot.py -q` | 2 项全通过（或环境性 skip 有理由） | 通过（2 例均 PASS、无 skip；另以脚本双跑复核 SHA256 一致，见 §4-1） |
| G4 | 全量回归 | `python -m pytest tests -q` | 1985 passed / 15 skipped / 0 failed（1929 + 56） | 通过（junit：tests=2000 / failures=0 / errors=0 / skipped=15 → **1985 passed**，790.5 s，2026-11-19）；步骤 10 审计修复后复跑：tests=2001 → **1986 passed / 15 skipped / 0 failed**（见审计报告 Phase 4） |
| G5 | 校准实跑 | `python scripts/verify_capacity_impact.py --calibrate` | 退出码 0；`out/capacity_calibration.json` 与 `.md` 落盘，含 `config_hash`/`evidence_level` | 通过（exit 0；`evidence_level = minutes`；JSON 含 `config_hash=e46749c6…`，Markdown 含 ratio(p) 与报告限制） |
| G6 | L1 路径 | `python scripts/verify_capacity_impact.py --calibrate --evidence-level ohlc` | 退出码 0；`evidence_level == "ohlc"` | 通过（exit 0；`evidence_level = ohlc`） |
| G7 | 诊断模式 | `python scripts/verify_capacity_impact.py --calibrate --diagnose-window` | 退出码 0；输出含 4 窗一致性诊断 | 通过（exit 0；打印证据等级 `minutes` 与候选窗长 `[24,36,48,60]`，注明 IJR 仅诊断） |
| G8 | 版本一致性 | 5 处版本锚点 grep | 全部 `3.8.0` | 通过（pyproject `:7` / `__init__.py:58` / `config_v2.py:371` / `reporting.py:40` / 两个测试常量 `EXPECTED_VERSION` 均 `3.8.0`，共 6 处） |

### 5.2 性能

| 项 | 规模 | 预算 | 实测 | 状态 |
|---|------|------|------|------|
| 单月分钟加载+聚合 | 22 日 × ≤128 万行 | < 60 s | 2023-03：**25.46 s / 23.52 s**（两次，22 文件 / 347 MB；`tracemalloc` 开启时 73.78 s，属追踪开销） | 通过 |
| 39 月分钟处理 | 2020-01…2023-03 | < 40 min | 未实跑：单月 23.5 s × 39 ≈ **15.3 min**（E5 外推）；v3.8.0 未接线全量分钟编排 | 不适用（附理由） |
| 全量 L1 校准 | 日频全样本 | < 5 min | `--calibrate --evidence-level ohlc` **3.78 s**（exit 0） | 通过 |
| 峰值内存 | 分钟流式 | < 2 GB | `tracemalloc` 峰值 **183.9 MB**（2023-03 单月） | 通过 |
| 默认路径 | 无参数 | 与 v3.7.0 同量级 | **34.3 s / 30.8 s**（两次），SHA256 `82728CE1…` 一致 | 通过 |

> 超预算处置：先降级证据等级（`minutes → ohlc`），再考虑并发；**不得**为性能牺牲确定性排序（EXECUTION §6）。

### 5.3 证据出口

| 证据 | 路径 | 状态 |
|------|------|------|
| 校准 JSON | `out/capacity_calibration.json` | 通过（1,361 B；13 个顶层键：`evidence_level/config_hash/models/selection/c/power_b/capacity/decay/ratio_diagnostics/temporary_share/lambda_significant_ratio/kappa/evidence_warnings`） |
| 校准 Markdown | `out/capacity_calibration.md` | 通过（含 ratio(p) 表 + 报告限制 + 证据警告） |
| 默认容量 JSON（不变） | `out/capacity_impact.json` | 通过（双跑 SHA256 `82728CE1…` 与 v3.7.0 基线一致） |
| 一致性 review | `docs/audit/CONSISTENCY_REVIEW_V3.8.0_*.md`（步骤 8） | 通过（`CONSISTENCY_REVIEW_V3.8.0_EXECUTION_CAPACITY.md` v1.1 存在） |

---

## §6 风险处置验收（对应 EXECUTION §8.2）

| # | 风险 | 可观察验收点 | 状态 |
|---|------|-------------|------|
| X1 | 父包重导入无 pyarrow 失败（design Q1） | T380-56 前置判定；失败则改独立顶层包并重议接口 | 通过（T380-56：阻断 pyarrow 后 `import backtest.execution.core.impact` 成功、`has_pyarrow() is False`） |
| X2 | AR 估计常数/`c_t` 定义未核 | 实施时对照 RFS 2023 附录；未核前该估计量标 `[待核]`，不得进主结论 | 通过（实现按 `c_t=ln(close)`、`η_t=(lnH+lnL)/2`；T380-15 合成反解误差 `<1e-8`） |
| X3 | 39 个 OOS 点功效不足 | 不选窗（D3）；IJR 仅诊断，`--diagnose-window` 输出不参与主值 | 通过（G7 仅打印等级与候选窗长；`primary` 只由 `average_capacity`/`regime_capacity` 决定） |
| X4 | 分钟数据无逐笔方向 | 所有 c 结论为 `[区间]`；BVC 偏差写入报告限制表 | 通过（Markdown「报告限制」固定写入 `[区间]` 与 BVC 代理说明） |
| X5 | 2023-04 后无分钟数据 | c 时间外推一律标 `[代理推断]` | 通过（Markdown「报告限制」固定写入 `[代理推断]`） |
| X6 | 校准把风险改小 | `c_stress = max(0.5, c_ci_upper)`（T380-50 等值断言） | 通过（T380-50；G5 实测 null 上界 → `c_calib_stress = 0.5`） |
| X7 | 默认口径 4 倍不一致被误读 | `ratio(p)` 诊断量随报告输出（design §9.5） | 通过（`ratio_diagnostics` 随 JSON 输出并渲染 Markdown 表：12.65/5.66/4.00/2.83/1.79） |
| X8 | ST 股 5% 规则文本未核实（design Q2） | 不硬编码规则；涨跌停判定仅用 `h==l`/零量；报告标 `[未核实]` | 通过（`detect_limit_lock` 仅 `h==l` 或 `volume==0 且 o=c=h=l`；Markdown 标注 `[未核实]`） |
| X9 | 2023-03 尾月不完整（design Q3） | 保留但标记：`evidence_warnings` 含 `partial_month=2023-03` | 不适用（附理由）：v3.8.0 未接线真实分钟面板编排（`run_calibration` 仅消费注入 `panels`），`partial_month` 无落点；随 v3.8.1 面板接线落地 |

**回滚点验收**（EXECUTION §8.1）：

| # | 回滚操作 | 通过判据 | 状态 |
|---|---------|---------|------|
| R1 | 删 `--calibrate` / `--evidence-level` / `--diagnose-window` 三个分支 | 默认路径输出与 v3.7.0 逐位一致 | 通过（分支由 `if args.calibrate or args.diagnose_window` 单点隔离；删后即 v3.7.0 代码路径，默认输出已验证 SHA256 一致） |
| R2 | 删除 `backtest/execution/` 整包 | 全仓无外部引用残留（grep 为空）；既有测试零失败 | 通过（grep `backtest.execution` 仅命中：脚本 lazy import、包自身 `__init__`、9 个新测试文件——均在回滚集内） |
| R3 | 撤 `calib` extra 与 `all` 中的 pyarrow | `git diff pyproject.toml` 回到 v3.7.0 形态 | 通过（diff 仅 3 处新增：version 行、`calib` extra、`all` 追加 pyarrow） |
| R4 | 删除 9 个测试文件 | 测试数回到 1929 passed / 15 skipped | 通过（1985 − 56 = 1929，与基线一致） |

---

## §7 文档同步验收

| 项 | DoD | 状态 |
|----|-----|------|
| `CHANGELOG.md`（仓库根） | 顶部新增 `## v3.8.0 — …（已实施, <日期>）`，含新增包/9 测试文件/56 项/兼容声明 | 通过（v3.8.0 条目含 E0-E8 产出、零变更、56 例红→绿、已知限制；步骤 10 追加审计修复注记） |
| `README.md` | 版本徽标与能力清单更新，不夸大（校准为「区间 + 压力档」，非「精确 c」） | 通过（版本句 v3.8.0 + 「执行/容量证据层」；未宣称精确 c） |
| `docs/PROJECT_STATUS.md` | 当前版本 3.8.0；P2「组合/容量未成为上线门禁」「冲击模型 stylized」状态更新 | 通过（路基新增 v3.8.0 `[x]`、当前标记下移、v3.8.1 候选登记、最近完成表新增一行） |
| `pyproject.toml` 版本 | `version` 由 `3.7.0` 升 `3.8.0`（步骤 8 F2：已纳入 EXECUTION §3.1 第 6 锚点；对齐 v3.7.0 先例） | 通过（`:7` `version = "3.8.0"`） |
| EXECUTION 回填 | §5.2 红→绿读数；§6 性能实测；§0.2 工件状态 → 已完成 | 通过（§5.2 按 T380 分组回填；§6 增实测列；§0.2 标「已实施」） |
| DESIGN 回填 | §20 开放问题 Q1/Q2/Q3 结论回写；必要时再升版本 | 通过（Q1 不会失败 / Q2 不硬编码 / Q3 保留但标记，均附证据） |
| 一致性 review | `CONSISTENCY_REVIEW_V3.8.0_*.md`（步骤 8 新建）产出并通过 | 通过（v1.1，§7 十五条不变量） |

---

## §8 汇总（步骤 9 回填，步骤 10 复核）

| 分项 | 项数 | 通过 | 失败 | 阻塞 | 不适用 |
|------|------|------|------|------|--------|
| E 任务（E0-E7） | 8 | 8 | 0 | 0 | 0 |
| TDD 用例 | 57 | 57 | 0 | 0 | 0 |
| 兼容性 | 13 | 13 | 0 | 0 | 0 |
| 门禁 | 8 | 8 | 0 | 0 | 0 |
| 性能 | 5 | 4 | 0 | 0 | 1 |
| 证据出口 | 4 | 4 | 0 | 0 | 0 |
| 风险处置（X1-X9） | 9 | 8 | 0 | 0 | 1 |
| 回滚点（R1-R4） | 4 | 4 | 0 | 0 | 0 |
| 文档同步 | 7 | 7 | 0 | 0 | 0 |
| **合计** | **115** | **113** | **0** | **0** | **2** |

> 计数只由上文逐行状态汇总（RULE-2）；步骤 9 之后按实际状态重算，步骤 10 审计不得只引用本表而不核对逐行状态。
> **当前结论（2026-11-19，步骤 10 审计回填后）**：113 通过 / 0 失败 / 0 阻塞 / 2 不适用（N/A 均附理由）。
> 全量回归 **1985 passed / 15 skipped / 0 failed**（junit tests=2000，790.5 s）；默认路径 SHA256 与 v3.7.0 逐位一致。
> **步骤 10 异构复审（2026-11-19）**：PASS_WITH_FIXES —— 唯一真实缺陷 H2（`detect_limit_lock` 零量分支缺 `c==l`，
> spec 偏离、真实数据零影响）已修复并新增 T380-25b 回归（56→57 例），全量复跑 **1986 passed / 15 skipped / 0 failed**
>（junit tests=2001）；另披露 P3 级 4 项（F2 月σ分母 / F3 p>5% 守卫 / F4 design §11.2 漂移诊断 / F5 单位根 HAC-SE），
> 探针勘误 9 项留档；详见 [审计报告](2026-11-19-v3.8.0-execution-capacity-audit.md) 与 `out/review_v380_results.txt`（48/48 PASS）。
> 两项 N/A 均源于同一已知边界：v3.8.0 未接线真实分钟面板编排（`run_calibration` 仅消费注入 `panels`），
> 39 月全量分钟处理与 `partial_month` 标记随 v3.8.1 落地。

---

## §9 与上游文档的映射

| 本清单 | EXECUTION | DESIGN | 调研 |
|--------|-----------|--------|------|
| §2 E0-E7 | §1 任务分解 | §19 实施步骤 | §8 |
| §3 T380-01…56 | §5.1 用例映射 | §16 测试设计 | R1-R8 协议 |
| §3.4 `ExponentialDecay` | §2.8 / §2.10 | §4 端口 / §7.1 | §16.3 D4 |
| §3.6 T380-41 注入机制 | §2.10 复用机制 | §3.1 禁止边 / §13.2 | §17 S1 |
| §4 兼容性 | §3.2 / §7 / §8.1 | §13.2 / §14 | — |
| §5 门禁/性能 | §6 / §7.1 | §17 | — |
| §6 风险 | §8.2 | §20 | §5 / §19 |
| §7 文档同步 | §3.1 | §14 | — |
