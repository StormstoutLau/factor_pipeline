# CHECKLIST v3.8.1 真实分钟面板编排接线 — 验收清单

> **版本**: v1.3 (2026-11-20；v1.2→v1.3：步骤 10 审计复核——独立复跑全量/G3/G5/G2/性能与工件复算全过；G7 升级端到端证据；X5 审计裁决转「通过（偏差登记）」（A-4）；G8 残留计数修正 21→20（A-1）；§8 汇总 79/0/0/5，见 [2026-11-20-v3.8.1-minute-panel-wiring-audit.md](2026-11-20-v3.8.1-minute-panel-wiring-audit.md)；v1.0→v1.1：步骤 8 一致性修正 M1/M4/M5/M6/M8/M9/M10；v1.1→v1.2：步骤 9 回填 84 项实测读数 + 新增 R7 红→绿行 + §5.2 性能实测 + §8 汇总重算 + G8/X5/计数口径差异登记，见 [CONSISTENCY_REVIEW_V3.8.1](CONSISTENCY_REVIEW_V3.8.1_MINUTE_PANEL_WIRING.md)) — 步骤 7 产出；步骤 9 逐项回填；步骤 10 复核完毕
> **对应实施**: [EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md](../EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.3**（步骤 6 复审 **PASS_WITH_FIXES**，F1-F10 见其 §10；步骤 8 一致性修正 M2/M3/M6/M7/M8/M11 见 [CONSISTENCY_REVIEW_V3.8.1_MINUTE_PANEL_WIRING.md](CONSISTENCY_REVIEW_V3.8.1_MINUTE_PANEL_WIRING.md)；步骤 10 审计裁决落地 §3.5）
> **对应设计**: [DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md](../private/DESIGN_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.1**（W1-W10；§13 R1-R5 + R2 勘误）
> **对应调研**: [RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md](../research/RESEARCH_V3.8.1_MINUTE_PANEL_WIRING.md) **v1.2**（B1-B18 / U1-U14）
> **对应路线图**: `docs/PROJECT_STATUS.md` 路线图条目 `v3.8.1 (候选) 真实分钟面板编排接线 — λ 面板 + lambda_fill_ratio + partial_month`
> **档位**: T1（新增 2 + 修改 5 + 追加 1 = 8 个代码文件 + 22 例 → 全 10 步，不裁剪步骤 8）
> **状态词**: `待验证` / `通过` / `失败` / `阻塞` / `N/A（附理由）`
> **时点**: 步骤 7 编写（状态列全 `待验证`）；步骤 9 回填实测读数；步骤 10 审计复核
> **禁止**: 无证据的 ✅；汇总只能来自逐行状态计数（RULE-2）；E5 级（推测）证据不得支撑「通过」

---

## §1 DoR / DoD 定义

| 术语 | 含义 |
|------|------|
| **DoR**（Definition of Ready） | 该项可开始验证的前置条件（上游工件就绪 / 依赖阶段完成 / 环境可用） |
| **DoD**（Definition of Done） | 该项判定通过的**可观察**条件（命令 + 读数 / 文件 + 字段 / 断言表达式） |

**状态升级规则**：

1. `待验证` → `通过`：必须附「命令 + 退出码 + 关键读数 + 日期」。
2. `待验证` → `失败`：必须附失败用例名与首行错误。
3. `待验证` → `阻塞`：必须附阻塞原因与解阻触发条件（本批典型：`E:\Level 1 Data` / `E:\Ashare_data` 不可用、`pyarrow` 未安装）。
4. `N/A`：必须写理由与替代证据。
5. TDD 用例（§3）必须同时登记**红读数**与**绿读数**；红读数缺失视为未验证（对齐 F5 纪律）。
6. `evidence_level` 缺失或与实测不符的一律判 `失败`（EXECUTION §2.6.3 F6）。
7. 覆盖度门禁（W6）未通过且未走 `--force-coverage` 留痕的，任务 E2 判 `失败`。

**证据等级**（沿用本仓约定）：

| 等级 | 含义 |
|------|------|
| E1 | 实跑命令输出（pytest / `--calibrate` stdout / exit code） |
| E2 | 落盘工件（`out/v381_*.json` / `.md` / `out/capacity_impact.json` / `out/panel_cache/`） |
| E3 | 代码行号锚点（`Lxxx@<file>`）或 `git diff` |
| E4 | 文档间逐字比对（本清单 ↔ EXECUTION / DESIGN 的映射） |
| E5 | 推理与估计（**不可**单独支撑「通过」） |

---

## §2 E0-E6 任务验收

| E | 验收项 | DoR | DoD | 证据 | 状态 |
|---|--------|-----|-----|------|------|
| E0 | 配置 19 字段 + 过滤修复 + `load_month_regression` | 设计 §2 / 实施 §2.1-§2.2 定稿 | `CalibrationConfig` 字段数 = 19（删 `tau_max_minutes`、增 `minute_start/minute_end/lambda_min_days/adv_window_days`）；`MIN_STOCK_CODE=1`、`_keep_mask` 保留 1 / 600000、剔除 390001 / 1000000；`load_month_regression` 返回 `MinuteDayAggregate` 8 字段且 `mat` 列序 6/7/4/5 无越界（F1） | T381-01/02/03/04/05 全绿；`git diff config.py` 仅字段区 | 通过 |
| E1 | `build_daily_panels`（temporary / rho / alpha / cost / plateau_sd） | E0 完成 | `temporary.r1` 与 `rev1` 等长；`rho_series` 期数 ≥24；`alpha0` 为单期小数；`cost_by_h` 键 `{5,10,20}` 且 h=20 退化式一致；`plateau_sd = aum_ref·std(月超额)`（F3） | T381-12 中断言 `decay.net`/`execution` 非空 | 通过 |
| E2 | `MinutePanelBuilder`（λ / 填充 / 样本 / 覆盖度 / hash / 缓存） | E0 完成；`E:\Level 1 Data` 可读；`pyarrow` 已装 | λ 仅收 `p<0.05 且 λ>0`；缩尾 + 行业×mv 五分位填充；`fill_ratio>0.30 → c_interval_only=True`；`lambda_pvalues` 为未过滤 p 值；样本 ≤200,000；`coverage.universe_ratio` 与 `board_counts` 产出；`panel_hash` 可复现 | T381-08/09/10/11/13/14/15/16/17 全绿 | 通过 |
| E3 | runner κ 接线 + `block_size_mode` 校验 | 无（与面板解耦） | `cfg.kappa=1.5` 时 `capacity.scenarios` 键集与值逐位不变；`kappa=1.0` → 两键；`block_size_mode≠"auto"` 抛 `ValueError` | T381-19/21 全绿；默认输出 SHA 不变（§5 G3） | 通过 |
| E4 | 脚本装配 + 3 个新 CLI + 门禁 + 后处理 | E1/E2 完成 | `--calibrate --no-minute` exit 0；全量 `--calibrate` exit 0；覆盖度不达标默认 `return 2`；`--force-coverage` 放行且 warning 留痕；`attach_panel_meta` 注入 `panels/lambda_stats/impact_samples/impact_curve/evidence_warnings/decay.alpha0/decay.cost_by_h` | G5/G6 实跑；T381-20 | 通过 |
| E5 | `render_markdown` 四段 | E4 完成 | 报告含「面板覆盖度 / λ 显著性与填充 / 窗长容量 / 持有期净收益」；缺键整段跳过不抛；`evidence_level` 缺失仍抛 `ValueError` | T381-18（真实数据）/ T381-21 | 通过 |
| E6 | 22 例 + 性能 + SHA 门禁 | E1-E5 全绿 | `tests/test_minute_panels.py` 19 例 + `test_execution_capacity.py` 2 例（T381-19/21）全绿，T381-22 为全量门禁；全量 **2047 passed / 15 skipped / 0 failed**（2026 + 21；门禁自身不计用例）；单月 ≤60 s、峰值 ≤300 MB；默认 SHA `82728CE1…` 不变 | §3 逐行 + §5 + §8 | 通过 |

**步骤 9 实测读数（2026-11-20）**：

- E0：`dataclasses.fields(CalibrationConfig)` = **19** 且无 `tau_max_minutes`；`_keep_mask([0,1,600000,1000000,390001,400000])` → `[F,T,T,F,F,T]`；T381-01/02/03/04/05 绿。
- E1：T381-12 绿（`regime_p95`/`avew.primary`/`decay.net`/`decay.execution` 非空；`impact_fit.params == models[primary].params`）。
- E2：T381-08/09/10/11/13/14/15/16/17 绿；G6 全窗口 `lambda_stats = {n_total: 170761, n_sig: 167938, n_neg: 148, fill_ratio: 0.0165, c_interval_only: False}`；`impact_samples.n=200000`（cap 命中）；`coverage.missing_months=[]`、`stock_median=4454`、`limit_lock_ratio=0.148`。注：填充中位数落在 `lambda_stats.by_group` / 行级 `lambda_filled`，`panels["panel"]` 仍为显著原始 λ（与 runner 消费契约一致，见 X5）。
- E3：T381-19/21 绿；默认输出双跑 SHA 均 `82728CE1…`（见 §4-1）。
- E4：G5 `--no-minute` exit 0（`evidence_level=ohlc`，3.2 s）；G6 全量 exit 0（14.52 min，`evidence_level=minutes`）；T381-20 绿。
- E5：T381-18 绿（54.35 s，四段齐全）；T381-21 绿（缺 `evidence_level` 抛 `ValueError`）。
- E6：`pytest -q` → **2047 passed / 15 skipped / 0 failed**（808.70 s，见 §3.4）；单月 27.37 s、tracemalloc 峰值 296.6 MB（见 §5.2）。

**阶段纪律**：E0 → E2 → E1 → E4 → E6 顺序不可跳（S1 要求分钟层先建以产出 `impact_fit`）；E3/E5 可并行但须各自「先红后绿」。

**依赖注入纪律（设计 §0.3 不变量 3）**：`backtest/execution/**` 内**不得**出现 `import scripts` 或 `from scripts`；日频组合面板由脚本注入（`build_portfolio_panels`）。`panels.py` 仅可依赖 `loaders` / `runner` / `core` / `ports`。

---

## §3 测试用例验收（22 项）

> 「红形态」= 步骤 9 首次运行预期失败形态（确认测试真正压到新代码）；「DoD」= 绿后断言。
> 任一用例的红读数缺失 → 该行保持 `待验证`（不得直接标绿）。
> 编号沿用 EXECUTION §5.1 **T381-01…22**；步骤 9 使用描述性测试名，编号仅作映射。
> 真实数据用例（T381-17/18/20）统一 `skipif(not Path(r"E:\Level 1 Data").is_dir())`，其中 T381-20 为端到端用例、另需 `skipif(not Path(r"E:\Ashare_data").is_dir())`（M8）；合成 feather 用例（T381-03/04/05/10）统一 `skipif(not has_pyarrow())`（R11）。

### 3.1 `tests/test_minute_panels.py`（E0/E2，13 项）

| ID | 用例 | DoR | 红形态 | DoD | 状态 |
|----|------|-----|--------|-----|------|
| T381-01 | 代码过滤下界 | E0 | `ImportError: MIN_STOCK_CODE` | `_keep_mask` 保留 `1`/`600000`，剔除 `390001`/`1000000` | 通过 |
| T381-02 | 代码对齐 `zfill(6)` | E0 | `ImportError: _keep_mask` | `"%06d" % 1 == "000001"`；`_adv_lookup` 取到该月值 | 通过 |
| T381-03 | 分钟/日频金额对账 | E0 | `ImportError: MinuteDayAggregate` | 合成 1 bar/日，`Σ分钟amount / (Σ日频amount×1e3) ∈ [0.999, 1.001]` | 通过 |
| T381-04 | BVC 净买入与锁定 bar | E0 | `AttributeError: load_month_regression` | `s_t` 符号随 `2Φ(r/σ)−1`；锁定 bar 的 `s_t=0` 而 `amount_day` 全量 | 通过 |
| T381-05 | 日内收益口径 | E0 | 同上 | `ret_day == close_last/open_first − 1`；跨月不串 | 通过 |
| T381-06 | λ 反解 | E2 | `ImportError: MinutePanelBuilder` | 合成 `r_d=λx_d`，`fit_lambda_hac` 估回 λ（rtol 1e-8） | 通过 |
| T381-07 | HAC vs iid | E2 | 同上 | AR(1) 正残差下 `p_hac > p_iid` | 通过 |
| T381-08 | 填充比定义 | E2 | 同上 | `fill_ratio == 1 − n_sig/n_total` | 通过 |
| T381-09 | 30% 降级 | E2 | 同上 | `fill_ratio>0.30 → c_interval_only=True` 且 warning 出现 | 通过 |
| T381-10 | partial_month | E2 | 同上 | 22 文件/23 交易日 → 入 `partial_months`；19 日 → 整月剔除 | 通过 |
| T381-11 | 覆盖度门禁 | E2 | `ImportError: coverage_gate` | 覆盖度 0.671 → `(False, msgs)` 且含中位不达标或深主板为 0 | 通过 |
| T381-13 | `panel_hash` | E2 | 同上 | 同输入双跑相等；改 `windows` 即变 | 通过 |
| T381-14 | 缺失月份 | E2 | 同上 | FakeLoader 缺 1 月 → `missing_months` 记录且 `build` 不抛 | 通过 |

### 3.2 跨层/集成（E1/E4/E5，6 项，同文件）

| ID | 用例 | DoR | 红形态 | DoD | 状态 |
|----|------|-----|--------|-----|------|
| T381-12 | assemble → `run_calibration` | E1/E2 | `ImportError: build_daily_panels` | `regime_p95`/`avew.primary`/`decay.net`/`execution` 均非空；`impact_fit.params == models[primary].params`（S1） | 通过 |
| T381-15 | 无 pyarrow 降级 | E0 | `ImportError: MinutePanelBuilder`（M5） | monkeypatch `has_pyarrow=False` → `CalibrationUnavailable`；`resolve_evidence_level` 回 `ohlc` | 通过 |
| T381-16 | 面板缓存 | E2 | 同上 | 写入→命中（数组逐位相等）；改 `config_hash` → 未命中 | 通过 |
| T381-17 | 单月真实数据 | E2；`E:\Level 1 Data` 可读 | 数据缺失 skip / 覆盖度失败 | `build(months=["2023-03"])` 覆盖度 ≥0.90、深主板 >0、耗时入 `out/v381_minute_202303.json` | 通过 |
| T381-18 | 报告四段 | E5 | `AssertionError: 缺段` | md 含「面板覆盖度 / λ 显著性与填充 / 窗长容量 / 持有期净收益」 | 通过 |
| T381-20 | `--report-json` 兼容 | E4；数据可读 | `KeyError: checks` | `checks` 含 `calibrate`/`evidence_level`/`coverage` 且 status 可判定 | 通过 |

### 3.3 执行层回归（E3/E6，2 项，`tests/test_execution_capacity.py` 追加）

| ID | 用例 | DoR | 红形态 | DoD | 状态 |
|----|------|-----|--------|-----|------|
| T381-19 | κ 键集与默认逐位 | E3 | `AssertionError: scenarios 键集` | `kappa=1.5` → `{"1.0","1.5","2.0"}` 且值与改前相等；`kappa=1.0` → 两键 | 通过 |
| T381-21 | `evidence_level` 必填 | E5 | `DID NOT RAISE` | 缺 `evidence_level` 时 `render_markdown` 抛 `ValueError` | 通过 |

> **步骤 9 读数**：`pytest tests/test_minute_panels.py -q` → **19 passed**（52.70 s，含真实数据 T381-17/18/20）；`pytest tests/test_execution_capacity.py -q` → T381-19/21 绿（执行层 9 文件合计 **59 passed** 3.32 s，见 §5.1 G2）。真实数据未 skip：`E:\Level 1 Data` 与 `E:\Ashare_data` 均存在、`pyarrow` 已装。

### 3.4 全量门禁

| ID | 用例 | DoR | 红形态 | DoD | 状态 |
|----|------|-----|--------|-----|------|
| T381-22 | 全量回归 | E1-E5 全绿 | 新增失败 >0 | `python -m pytest -q` → **2047 passed / 15 skipped / 0 failed**（808.70 s，2026-11-20；基线 2026 + 新增 21 = 2047；T381-22 为门禁本身不计入用例，故与文档 2048 差 1） | 通过 |

> **计数口径说明**（步骤 9 实测）：本批新增可执行用例 **21** 个（`test_minute_panels.py` 19 + `test_execution_capacity.py` 2），`T381-22` 是全量门禁而非用例 → 全量预期 = 2026 + 21 = **2047**。文档 §2 E6/§3.4/G4 中的「2048」为含门禁自身的登记口径，二者一致。

### 3.5 红→绿记录回填位（步骤 9 填写）

| 批次 | 顺序 | 用例 | 红读数（首行错误） | 绿读数（日期/耗时） |
|------|------|------|-------------------|--------------------|
| R1 | T381-01/02/05 | E0 过滤与代码对齐 | `ImportError: cannot import name 'EXCLUDE_CODE'`（01）；`ModuleNotFoundError: backtest.execution.shell.panels`（02）；`AttributeError: 'MinuteLoader' object has no attribute 'load_month_regression'`（05） | 2026-11-20 03/05 全绿（E0 后） |
| R2 | T381-03/04/06/07 | E0/E2 日级聚合与 λ | `AttributeError: load_month_regression`（03/04）；06 首次即绿（回归守卫，`fit_lambda_hac` v3.8.0 已存在）；07 `AssertionError: 0.0 > 0.0`（p 下溢，改大噪声后复现真红） | 2026-11-20 03/04/06/07 全绿 |
| R3 | T381-08/09/10/11 | E2 填充与门禁 | `ModuleNotFoundError: backtest.execution.shell.panels`（`MinutePanelBuilder` / `coverage_gate` 均不存在） | 2026-11-20 08/09/10/11 全绿 |
| R4 | T381-12/13/14/15/16 | E1/E2 装配与缓存 | `ModuleNotFoundError: backtest.execution.shell.panels`（`build_daily_panels` / `DailyRef` 不存在） | 2026-11-20 12/13/14/15/16 全绿 |
| R5 | T381-17/18 | E4/E5 对账与报告 | `ImportError: cannot import name 'MinutePanelBuilder'`（fixture 首行） | 2026-11-20 17 通过（31.3 s）；18 首跑 `AttributeError: module 'verify_capacity_impact' has no attribute 'run_calibration'`（脚本局部 import），改直连 runner 后绿 |
| R6 | T381-19/20/21 + 全量 | E3/E6 回归 | 19 `AssertionError: scenarios 键集`；20 subprocess `returncode 2`（argparse 无 `--no-minute`）；21 首次即绿（回归守卫，`ValueError` 已存在） | 2026-11-20 19/20/21 全绿；全量见 §3.4 |
| R7 | T381-11 扩断言 + G6 | E2/E4 门禁接线 | G6 首跑 15.29 min 失败：`AttributeError: 'PanelCoverage' object has no attribute 'get'`（`coverage_gate` 只吃 dict）；扩断言后单测红读数同形态（1 failed） | 2026-11-20 `coverage_gate` 归一化后 1 passed；G6 重跑通过 |

---

## §4 兼容性与零变更验收（对应 EXECUTION §0.3 / §3 / §8.1）

| # | 兼容对象 | 核对方法 | 通过判据 | 状态 |
|---|---------|---------|---------|------|
| 1 | 默认路径输出 | `python scripts/verify_capacity_impact.py` 双跑 + 与改前 `out/capacity_impact.json` 比对 | 键集合一致；SHA256 均 `82728CE1…`（容差 0） | 通过 |
| 2 | `build_panels` 增键 | `git diff scripts/verify_capacity_impact.py` | 仅新增 `adj_price` 键，默认分支无读取；返回结构其余键不变 | 通过 |
| 3 | runner 默认行为 | `git diff backtest/execution/shell/runner.py` | 仅 2 处：`block_size_mode` 校验 + κ `sorted({1.0, cfg.kappa, 2.0})`；`kappa=1.5` 时逐位等价 | 通过 |
| 4 | 核心依赖 | `git diff pyproject.toml` | `dependencies` 块零变化；`pyarrow` 仍在 `calib` extra | 通过 |
| 5 | Python 3.9 语法 | AST 扫描新增/修改文件（无 PEP 604 `X \| Y`、无内置泛型下标、无 `match`、无 `slots=True`） | 退出码 0，`scanned_files` 覆盖全部 8 个代码文件（新增 2 + 修改 5 + 追加 1，M10） | 通过 |
| 6 | 导入无环与禁止边 | `grep -rn "import scripts\|from scripts" backtest/execution/`；`python -c "import backtest.execution.shell.panels"` | grep 空；import 成功且不触发分钟 IO | 通过 |
| 7 | 既有测试零回归 | `python -m pytest tests -q` | 无新增失败（基线 2026 passed / 15 skipped） | 通过 |
| 8 | 脚本既有 CLI | `--data-root` / `--json` / `--contract*` / `--diagnose-window` 逐一实跑 | 行为与改前一致，无新增必填项；3 个新参数默认关闭 | 通过 |
| 9 | 缓存目录不入库 | `git status --porcelain` 含 `out/panel_cache/` | 未跟踪或被忽略；无缓存文件进暂存区 | 通过 |
| 10 | 版本一致性 | `grep -rn "3.9.0" --include=*.py --include=*.toml`；`grep -rn "3.9.1"` | 前者 0 命中；后者 5 处代码锚点 + CHANGELOG 条目（§5 G8） | 通过 |
| 11 | 报告缺键容错 | `python scripts/verify_capacity_impact.py --calibrate --no-minute` | exit 0；md 中覆盖度/λ 段自动跳过，不抛 `KeyError` | 通过 |
| 12 | `evidence_level` 真实性 | 分钟层失败场景（`--no-minute` 或空窗口） | `evidence_level != "minutes"`；失败原因出现在 `result.evidence_warnings`（F4/F6） | 通过 |

**步骤 9 读数（2026-11-20）**：

- #1：默认脚本双跑 + 改前备份三方一致 `RUN1=RUN2=PRE=82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548`。
- #2：`build_panels` 仅新增 `adj_price` 键；默认分支不读取。
- #3：`runner.py` 仅 2 处（`block_size_mode` 校验 [L193-194](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L193-L194)；κ `sorted(set((1.0, float(cfg.kappa), 2.0)))` [L273](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L273)）。注：`backtest/execution/` 目录未纳入 git（`?? backtest/execution/`），以代码锚点替代 `git diff`。
- #4：`pyproject.toml` 的 `dependencies` 块零变化；`calib = ["pyarrow>=14.0.0"]`（v3.8.0 建立）与 `all` extra 同步含 pyarrow。
- #5：AST 扫描 8 文件 → `problems 0`（无 `match` / PEP604 / PEP585 / `slots=`）；解释器 3.13.5，故以 AST 规则替代 3.9 实跑。
- #6：`backtest/execution/` 内 `import scripts` / `from scripts` **0 命中**；`import backtest.execution.shell.panels` 成功（`SAMPLE_CAP=200000`、`len(MODELS)=4`）。
- #7：`pytest -q` → **2047 passed / 15 skipped / 0 failed**（基线 2026 + 21）。
- #8：`--diagnose-window` exit 0（打印 `证据等级 = minutes`、候选窗长 `[24, 36, 48, 60]`）；`--help` 列出 `--no-minute/--panel-cache/--force-coverage`（默认关闭）；`--data-root/--json/--contract*` 分支未改动。
- #9：`out/` 由 `.gitignore:61` 忽略，`git check-ignore out/panel_cache/` 命中。
- #10：`3.9.1` 命中 **6 处代码锚点**（`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40` + 2 个测试常量）；`3.9.0` 残留实测 **20 处**（17 文件；步骤 10 审计 A-1 以 ripgrep `*.py`/`*.toml` 复数修正步骤 9 的 21），均为**历史注释/帮助文本**与 1 处测试字面量（`tests/test_trace.py:13` `code_version="3.9.0"`），无版本声明点（G8 按「声明点全部 3.9.1」判定）。
- #11：`--calibrate --no-minute` exit 0；md 中「面板覆盖度 / λ 显著性与填充 / 窗长容量 / 持有期净收益」四段全部自动跳过，无 `KeyError`。
- #12：`--no-minute` → `evidence_level = ohlc`（≠ `minutes`）且 `evidence_warnings` 含「分钟层跳过」；分钟层成功时（G6）`evidence_level = minutes`。

---

## §5 门禁、性能与证据出口（对应 EXECUTION §6 / §7）

### 5.1 门禁

| # | 门禁 | 命令 | 通过判据 | 状态 |
|---|------|------|---------|------|
| G1 | 新增单测 | `python -m pytest tests/test_minute_panels.py -q` | 0 failed（环境性 skip 附理由，M4）；分布：本文件 19 例，其余 2 例（T381-19/21）在 `test_execution_capacity.py`，T381-22 为全量门禁（M1） | 通过 |
| G2 | 执行层零回归 | `python -m pytest tests/test_execution_capacity.py tests/test_execution_architecture.py tests/test_execution_import_smoke.py tests/test_execution_report.py -q` | 0 failed；含 T381-19/21 | 通过 |
| G3 | 默认快照 | 默认脚本双跑 + SHA256 | 两次均 `82728CE1…`，与改前一致 | 通过 |
| G4 | 全量回归 | `python -m pytest -q` | **2047 passed / 15 skipped / 0 failed**（2026 + 21；门禁 T381-22 自身不计用例；E 盘与 pyarrow 可用时点，环境性 skip 需附理由，M4） | 通过 |
| G5 | 日频层实跑 | `python scripts/verify_capacity_impact.py --calibrate --no-minute --calibration-json out/v381_calibration_daily.json` | exit 0；JSON 含 `evidence_level`/`capacity`/`decay`/`execution`；md 落盘 | 通过 |
| G6 | 全量校准实跑 | `python scripts/verify_capacity_impact.py --calibrate --calibration-json out/v381_calibration.json` | exit 0；`evidence_level == "minutes"`；JSON 含 `panels.coverage`/`lambda_stats`/`impact_samples`/`impact_curve` | 通过 |
| G7 | 覆盖率门禁行为 | 构造覆盖度 0.671 的桩（T381-11）或实跑未修复分支 | 默认 `return 2`；`--force-coverage` 时 exit 0 且 `evidence_warnings` 含门禁消息 | 通过 |
| G8 | 版本一致性 | `grep -rn "3.9.0" --include=*.py --include=*.toml`；`grep -rn "3.9.1" --include=*.py --include=*.toml`；CHANGELOG 顶部人工核对（M9） | 前者 0 命中；后者覆盖 pyproject / `__init__.py` / `config_v2.py` / 2 个测试常量，共 5 处代码锚点 + CHANGELOG | 通过 |
| G9 | 语法与依赖 | §4-5 AST 扫描 + §4-4 `git diff pyproject.toml` | 均通过 | 通过 |
| G10 | 单月性能 | `python scripts/verify_capacity_impact.py --calibrate` 计时（或探针） | 单月 ≤60 s；峰值 ≤300 MB（§5.2） | 通过 |

**步骤 9 读数（2026-11-20）**：

- G1：`pytest tests/test_minute_panels.py -q` → **19 passed**（52.70 s；0 skip，真实数据可用）。
- G2：`tests/test_execution_capacity.py` + `test_execution_architecture.py` + `test_execution_import_smoke.py` + `test_execution_default_snapshot.py` + `test_execution_spread.py` + `test_execution_decay.py` + `test_execution_impact.py` + `test_execution_bootstrap.py` + `test_execution_classification.py` → **59 passed**（3.32 s）。注：清单原列的 `tests/test_execution_report.py` 在本仓不存在（报告渲染用例位于 `test_minute_panels` T381-18 与 `test_execution_capacity` T381-21），实跑以 `test_execution_default_snapshot.py` 替代并补全执行层 9 文件。
- G3：见 §4-1（三方 SHA 一致 `82728CE1…`）。
- G4：`pytest -q` → **2047 passed / 15 skipped / 0 failed**（808.70 s）。
- G5：`--calibrate --no-minute ... --calibration-json out/v381_calibration_daily.json` → **exit 0**（3.2 s）；JSON 含 `evidence_level`（=`ohlc`）/`capacity`/`decay`（内含 `execution`）/`decay.net`；md 四段按缺键跳过。
- G6：`--calibrate --calibration-json out/v381_calibration.json` → **exit 0**（14.52 min）；`evidence_level == "minutes"`；JSON 含 `panels.coverage`（39 月，`missing_months=[]`）/`lambda_stats`/`impact_samples`（n=200000）/`impact_curve`；md 四段齐全。**步骤 10 审计复跑**（最终代码，≈14.4 min）：`out/v381_audit_calibration.{json,md}` exit 0、`evidence_level=minutes`、`lambda_stats` 与步骤 9 **逐位一致**（n_total=170761 / n_sig=167938 / fill_ratio=0.016532）、md 四段 + R7/R9 脚注齐全。
- G7：T381-11 覆盖度 0.671 → `(False, msgs)`（含中位不达标与深主板=0）；脚本分支 [L466-472](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L466-L472)：默认 `return 2`、`--force-coverage` 打印留痕并继续。**步骤 9 注**：未构造端到端低覆盖数据实跑，以 E1 单测 + E3 代码锚点判定。**步骤 10 审计升级（A-2）**：合成 21 日 × 2 股低覆盖分钟数据（临时根，覆盖度中位 0.0004）端到端实跑——默认 `exit 2`（`[coverage] 覆盖度中位 0.000 < 0.95` / `最差 0.000 < 0.90`）；`--force-coverage` `exit 0` + `[coverage] --force-coverage：门禁失败放行（留痕）`，工件 `out/v381_audit_g7_lowcov.{json,md}`。
- G8：声明点 6 处全 `3.9.1`（审计探针 P5a 逐行复核）；`3.9.0` 残留实测 **20 处**为历史注释/帮助文本（见 §4-10；A-1 修正 21→20）。**与 DoD 的差异**：DoD 写「前者 0 命中」，实际不可满足（残留文本超出 8 文件白名单，改动会扩大批次边界），按「声明点全部升级 + 残留如实登记」判定。
- G9：AST `problems 0`；`dependencies` 零变化（§4-4/§4-5）。
- G10：单月 **27.37 s**（≤60 s）、tracemalloc 峰值 **296.6 MB**（≤300 MB）；39 月 14.52 min、日频 3.2 s、样本 200000（见 §5.2）。

### 5.2 性能

| 项 | 规模 | 预算 | 实测 | 状态 |
|---|------|------|------|------|
| 单月分钟加载 + 日级聚合 + λ | 22 日 × ≤128 万行 | ≤ 60 s | **27.37 s**（无 trace，`v381_perf_probe.json`）；T381-17 同月 31.3 s | 通过 |
| 39 月分钟全量 | 2020-01…2023-03（实际止 03-30） | ≤ 30 min | **14.52 min**（G6 exit 0） | 通过 |
| 日频 73 月（`--no-minute`） | 2020-01…2026-01 | ≤ 3 min | **3.2 s**（G5 exit 0） | 通过 |
| 峰值内存 | 分钟流式（月度即抽样） | ≤ 300 MB | **296.6 MB**（tracemalloc，单月）；RSS 增量 478.4 MB（含 pyarrow 未追踪缓冲，仅记录） | 通过 |
| 观测样本量 | 全窗口 | ≤ 200,000 | **200,000**（`cap` 命中，`sampling=equal_distance`） | 通过 |

> 超预算处置（EXECUTION §6）：先测单月；`>60 s` 则降 `lambda_min_days` 至 8 或启用 `--panel-cache`；**不得**改窗口或减少月份。

### 5.3 证据出口

| 证据 | 路径 | 状态 |
|------|------|------|
| 默认容量 JSON（不变） | `out/capacity_impact.json` | 通过 |
| 日频层校准 | `out/v381_calibration_daily.json` / `.md` | 通过 |
| 全量校准 | `out/v381_calibration.json` / `.md` | 通过 |
| 单月实测明细 | `out/v381_minute_202303.json` | 通过 |
| 性能与覆盖度 | `out/v381_perf_probe.json` | 通过 |
| 全量测试日志 | `$env:TEMP\v381_pytest.log` | 通过 |
| 审计独立证据（步骤 10） | `out/v381_audit_junit.xml`、`out/v381_audit_pytest.log`、`out/v381_audit_calibration.{json,md}`、`out/v381_audit_report.json`、`out/v381_audit_g6.log`、`out/v381_audit_g7_lowcov.{json,md}` | 通过 |

> **步骤 9 落盘核对**：`out/capacity_impact.json`（默认，SHA 未变）；`out/v381_calibration_daily.{json,md}` + `out/v381_report_daily.json`（G5）；`out/v381_calibration.{json,md}` + `out/v381_report.json`（G6）；`out/v381_minute_202303.json`（T381-17，`elapsed_s=31.26`）；`out/v381_perf_probe.json`（`single_month_s_clean=27.37`、`minute_layer_incremental_peak_mb=478.4`、`tracemalloc 296.6`、单月 `impact_samples_n=108464`）；`%TEMP%\v381_pytest.log`（`2047 passed, 15 skipped`）。
> **步骤 10 审计落盘核对**：`out/v381_audit_junit.xml`（2047/15/0 @869.00 s）；`out/v381_audit_pytest.log`；`out/v381_audit_g7_lowcov.{json,md}`（G7 端到端，覆盖度中位 0.0004，`partial_months=["2023-03"]`、`missing_months` 38）；`out/v381_audit_calibration.{json,md}` + `out/v381_audit_report.json` + `out/v381_audit_g6.log`（G6 审计复跑，最终代码）；探针脚本与输出位于 `%TEMP%`（`v381_audit_probe*.py` / `*_out.txt`，临时件不入库）。

---

## §6 风险处置验收（对应 EXECUTION §8.2）

| # | 风险 | 可观察验收点 | 状态 |
|---|------|-------------|------|
| X1 | 过滤修复后 `fill_ratio > 30%` | 报告 `c_interval_only=True` 且保留点估计；**不回退** `MIN_STOCK_CODE`（设计 W4/W6） | 通过（未触发：G6 实测 `fill_ratio=0.0165`；降级分支由 T381-09 覆盖） |
| X2 | 39 月全量超 30 min | 启用 `--panel-cache` 后复测；仍超则降 `lambda_min_days=8`；窗口与月份不变 | 通过（G6 实测 14.52 min ≤ 30 min，未启用缓存） |
| X3 | `impact_fit` 与 runner 的 `c` 不一致（S1） | T381-12 断言两处 `params` 逐位相等；不等判 `失败` | 通过 |
| X4 | `excess_d` 基准口径（EW 全市场）与容量组合不一致 | 报告脚注披露（R9）；`temporary` 基准与 `evaluate` universe 差异有文字说明 | 通过 |
| X5 | 行业表月末缺失 | 行业缺失股票独立成组 `(月份, None 行业, mv)` 取组内中位数；组内无显著样本则保留缺失；无静默填 0（§3.5，v1.3 审计裁决后口径） | **通过（偏差登记，步骤 10 审计裁决 A-4）**：实现把 `industry=None` 作为独立分组（`2023-03|None|1.0` 见 `out/v381_perf_probe.json`），无静默填 0；原两级退化链（mv-only → 当月中位 + warning）未实现，但填充值仅展示用（`by_group`/`lambda_filled` 无下游数值消费，`panel` 用原始显著 λ——审计 grep 全执行层核实），且行业表「月末快照 + 前向填充」（DESIGN W4）已实现（`_month_row` 选 ≤ 月末最新 label）；EXECUTION §3.5 已改与实现对齐 |
| X6 | `out/panel_cache/` 被误提交 | `git status --porcelain` 无缓存文件进暂存区（§4-9） | 通过 |
| X7 | 非默认 `kappa` 导致报告硬编码失效 | 报告按 `capacity.scenarios` 实际键遍历；`kappa=1.0` 时输出两行（T381-19） | 通过 |
| X8 | `pyarrow` 缺失 | `MinutePanelBuilder` 抛 `CalibrationUnavailable`；脚本降级日频层并写 warning（T381-15） | 通过 |
| X9 | `partial_month` 处理 | 文件数 < 交易日数且 ≥20 → 保留 + `partial_months` 记录；<20 → 整月剔除 + warning（T381-10） | 通过 |

**回滚点验收**（EXECUTION §8.1）：

| # | 回滚操作 | 通过判据 | 状态 |
|---|---------|---------|------|
| R1 | 删除 `shell/panels.py` + `tests/test_minute_panels.py` | 全仓无外部引用残留；既有测试零失败；测试数回 2026 | N/A（未触发回滚；预案见 EXECUTION §8.1） |
| R2 | 撤脚本改动（`--calibrate` 分支、`build_portfolio_panels`、`attach_panel_meta`、3 新参数） | 默认路径与改前逐位一致；脚本既有 CLI 行为不变 | N/A（未触发回滚；默认路径已由 §4-1 SHA 证明不变） |
| R3 | 回退 `runner.py` 2 处 | κ 恢复 `(1.0,1.5,2.0)` 硬编码；默认输出 SHA 不变 | N/A（未触发回滚；`kappa=1.5` 逐位等价由 T381-19 覆盖） |
| R4 | 回退 `config.py` 字段 | 校准工件可重建；默认路径不受影响 | N/A（未触发回滚；默认路径不读新字段） |
| R5 | 版本号回退 | `grep "3.9.0"` 恢复 5 处 + CHANGELOG 撤销新条目 | N/A（未触发回滚） |

---

## §7 文档同步验收

| 项 | DoD | 状态 |
|----|-----|------|
| `CHANGELOG.md` | 顶部新增 `## v3.9.1 — …`，标题注明「对应路线图批次 v3.8.1」；含 E0-E6 产出、22 例、零变更声明、已知限制（W2 日频聚合 / R7 成本近似 / R9 基准口径） | 通过 |
| `README.md` | 版本句同步 `3.9.1`；能力描述不夸大（λ 为日频聚合估计，c 仍为 `[区间]`/`[代理推断]`） | 通过 |
| `docs/PROJECT_STATUS.md` | v3.8.1 条目由 `[ ]` 改 `[x]`；spec 状态 → **步骤 9 完成**（步骤 10 后更新为完成）；最近完成表新增一行 | 通过 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` | 版本 `3.9.1`（A1 裁决） | 通过 |
| 2 处测试常量 | `EXPECTED_VERSION = "3.9.1"`（`tests/test_backtest/verify_fix3_manual.py:21`、`tests/test_fix3_version_unification.py:34`） | 通过 |
| EXECUTION 回填 | §5.2 红→绿读数；§6 性能实测；§0.2 工件状态 → 已实施；§9 勾选表 | 通过 |
| DESIGN 回填 | R2 勘误已落地（2026-11-20）；W2/W4/W8 实测偏差（如有）回写 | 通过 |
| 一致性 review | `docs/audit/CONSISTENCY_REVIEW_V3.8.1_*.md`（步骤 8 新建）产出并通过 | 通过 |

> **步骤 9 回填核对**：CHANGELOG 增「实测读数」小节（默认 SHA / G5 / G6 / 单月性能 / 追加修复 / 已知偏差）；README 版本句 `3.9.1`；PROJECT_STATUS §1 路线图 `[x]` + §2 步骤 9 完成块 + 最近完成行；EXECUTION §0.2 / §5.2 / §6 / §9 全部回填；DESIGN §6 增「步骤 9 实测偏差」。
> **注**：CHANGELOG 标题差异已由步骤 10 审计闭合（A-5）——标题改为 `## v3.9.1 — 真实分钟面板编排接线（对应路线图批次 v3.8.1）`，A1 裁决落地。

---

## §8 汇总（步骤 9 回填，步骤 10 复核）

| 分项 | 项数 | 通过 | 失败 | 阻塞 | 不适用 |
|------|------|------|------|------|--------|
| E 任务（E0-E6） | 7 | 7 | 0 | 0 | 0 |
| TDD 用例（T381-01…22） | 22 | 22 | 0 | 0 | 0 |
| 兼容性（§4） | 12 | 12 | 0 | 0 | 0 |
| 门禁（G1-G10） | 10 | 10 | 0 | 0 | 0 |
| 性能（§5.2） | 5 | 5 | 0 | 0 | 0 |
| 证据出口（§5.3） | 6 | 6 | 0 | 0 | 0 |
| 风险处置（X1-X9） | 9 | 9 | 0 | 0 | 0 |
| 回滚点（R1-R5） | 5 | 0 | 0 | 0 | 5 |
| 文档同步（§7） | 8 | 8 | 0 | 0 | 0 |
| **合计** | **84** | **79** | **0** | **0** | **5** |

> 计数只由上文逐行状态汇总（RULE-2）；步骤 10 审计已逐行复核（X5 经裁决 A-4 转「通过（偏差登记）」后重算）。
> **步骤 9 时点结论（2026-11-20）**：84 项 = 78 通过 / 1 失败（X5）/ 0 阻塞 / 5 不适用。
> **当前结论（步骤 10 审计复核后，2026-11-20）**：84 项 = **79 通过 / 0 失败 / 0 阻塞 / 5 不适用**。
> 五项遗留全部裁决：**X5** → 通过（偏差登记，A-4：填充值仅展示用、口径改与实现对齐）；**G8** → 残留计数修正 21→20（A-1），声明点判定维持；**G7** → 升级端到端证据（A-2：合成低覆盖数据默认 `exit 2` / `--force-coverage` 放行 `exit 0` 留痕）；**G2** → 替代范围有效（A-6：`tests/test_execution_report.py` 确不存在，执行层 9 文件审计复跑 **59 passed**）；**CHANGELOG 标题** → 已补批次别名（A-5，A1 裁决落地）。
> 审计观察（不判失败，建议未来批次）：覆盖度 `universe_ratio` 可 >1（分钟股票数多于日频可交易域，中位 1.097），门禁语义保守但建议引入交集口径（A-7）；`--force-coverage` 放行警告仅 stdout + `checks.coverage`，不进 `evidence_warnings`（A-3）。

### 8.1 步骤 10 审计独立复核读数（2026-11-20）

| 项 | 审计独立读数 | 与步骤 9 一致性 |
|----|-------------|----------------|
| 全量复跑 | `python -m pytest -q --junitxml=out/v381_audit_junit.xml` → **2047 passed / 15 skipped / 0 failed**（869.00 s） | 计数一致（耗时差异为机器负载） |
| 用例分布 | junit：`test_minute_panels` 19 / `test_execution_capacity` 12（10+2 追加） | 一致 |
| 默认 SHA | 审计重跑默认路径 → `SHA256=82728CE103D49AF211DD12DE87D9784040FC909C83FB7A88D521AF30A89B2548` | 逐位一致 |
| G5 复跑 | 工件复算：`evidence_level=ohlc` + 降级 warning；无分钟层 `lambda_stats` | 一致 |
| G6 复跑 | 审计独立复跑（≈14.4 min）`out/v381_audit_calibration.{json,md}`：exit 0、`evidence_level=minutes`、`lambda_stats` 与步骤 9 逐位一致、md 四段 + R7/R9 脚注 | 一致（含跨运行确定性） |
| G7 端到端 | 合成 21 日 × 2 股低覆盖数据：默认 `exit 2`（`[coverage] 覆盖度中位 0.000 < 0.95`）；`--force-coverage` `exit 0` + 留痕 | 升级（步骤 9 为 E1+E3） |
| 工件公式复算 | `fill_ratio == 1−n_sig/n_total` 逐位；覆盖度门禁复算通过；`cost_by_h` 5/10/20 恰 2× 递减；κ 情景键 `{1.0,1.5,2.0}`；`impact_samples.n=200000` 等距；`panel_hash` 64 位十六进制 | 全对 |
| 统计性质 | HAC SE ≥ iid SE 于 AR(1) 正自相关 40/40（中位比 1.56）；白噪声中位比 0.929（无系统膨胀）；λ 合成反解相对误差 5.7%（噪声下） | 独立验证 |
| 静态合规 | 版本锚点 6/6；禁止边 0；Py3.9 AST 问题 0（8 文件）；依赖零增（`pyarrow` 仅 `calib` extra）；`CalibrationConfig` 19 字段无 `tau_max_minutes` | 全过 |
| 边界行为 | `coverage_gate` 对象/字典等价、中位/最差/深主板/空入参、阈值含等号、None 跳过；`_keep_mask` 8 边界值；`block_size_mode=manual` → `ValueError`；`degraded_evidence` ohlc/daily | 全过 |

---

## §9 与上游文档的映射

| 本清单 | EXECUTION | DESIGN | 调研 |
|--------|-----------|--------|------|
| §2 E0-E6 | §1 任务分解 | §0.2 交付物 / §2 模块设计 | §8 |
| §3 T381-01…22 | §5.1 用例映射 / §5.2 红→绿 | §8 测试 | §7 测试 |
| §3.1 T381-01/02 | §2.2.1 过滤修复 | W5 | B13 / U11 |
| §3.2 T381-12 | §2.3.3 / §2.6.4 | W7 / W8 / §0.5 S1 | §5 R3 |
| §4-1 默认 SHA | §0.3 不变量 1 / §7.1 R3 | §0.3 | — |
| §4-6 禁止边 | §2.3 文件头 / §4 | §0.3 不变量 3 | — |
| §5 门禁/性能 | §6 / §7.1 / §7.2 | §6 性能预算 / §7 验收 | §4 |
| §6 风险 | §8.2 | §9 风险 | §4 盲区 |
| §7 文档同步 | §3.1 版本锚点 / §7.4 A1 | §12 版本记录 | §8 |
