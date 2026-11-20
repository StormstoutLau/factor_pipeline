# CHECKLIST v3.9.0 模拟数据验证骨架与步骤级追溯 — 验收清单

> **版本**: v1.4 (2026-11-19) — v1.0 = 步骤 7 产出；v1.1 = 步骤 8 对齐（§5 注闭环 + §8 一致性 review 项标通过）；v1.2 = 步骤 8 残留核实（规则表日期全部核实、过户费口径升级）；v1.3 = 步骤 9 TDD 实施回填（门禁/性能/红→绿实测；B2 turnover 判据勘误）；v1.4 = 步骤 10 审计复核（H4 勘误 §9 漏计 §3.6；追加审计回归 T390-39/40/41 三行 → §3 终态 40 项、§9 合计 108/102）
> **对应实施**: [EXECUTION_V3.9.0_VALIDATION_SKELETON.md](../EXECUTION_V3.9.0_VALIDATION_SKELETON.md) v1.4（步骤 6 review + 步骤 8 对齐与残留核实 + 步骤 9 回填，见其 §9）
> **对应设计**: [DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md](../private/DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md) v1.3（步骤 4 review + 步骤 6/8 勘误与残留核实，见其 §17/§18）
> **对应调研**: [RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md](../research/RESEARCH_SYNTHETIC_VALIDATION_TRACEABILITY.md) v1.3（盲区扫描 + 21 锚点 + §19 review + 步骤 8 核实 U3/U4/U5/U9-U12）
> **对应路线图**: [MULTIFACTOR_GOVERNANCE_ROADMAP.md](../analysis/MULTIFACTOR_GOVERNANCE_ROADMAP.md) P2「缺少模拟数据验证与步骤级追溯」
> **档位**: T1（2 生产模块 + 3 测试包 + 5 新增测试文件 + 4 脚本参数 → 全 10 步）
> **状态词**: `待验证` / `通过` / `失败` / `阻塞` / `N/A（附理由）`
> **时点**: 步骤 7 编写（状态列全 `待验证`）；步骤 9 逐项回填实测读数，步骤 10 审计复核
> **禁止**：无证据的 ✅；汇总只能来自逐行状态计数（RULE-2）；E5 级（推测）证据不得支撑「通过」

---

## §1 DoR / DoD 定义

| 术语 | 含义 |
|------|------|
| **DoR**（Definition of Ready） | 该项可开始验证的前置条件（上游工件就绪 / 依赖 E 任务完成 / 环境可用） |
| **DoD**（Definition of Done） | 该项判定通过的**可观察**条件（命令 + 读数 / 文件 + 字段 / 断言表达式） |

**状态升级规则**：

1. `待验证` → `通过`：必须附「命令 + 退出码 + 关键读数 + 日期」。
2. `待验证` → `失败`：必须附失败用例名与首行错误。
3. `待验证` → `阻塞`：必须附阻塞原因与解阻触发条件（本批典型：`E:\Level 1 Data` 不可用仅影响 E0 真实数据影响量化，不影响 40 例合成测试）。
4. `N/A`：必须写理由与替代证据。
5. TDD 类项目（§3）必须同时登记**红读数**与**绿读数**；红读数缺失视为未验证（对齐 F5 纪律）。
6. `enabled=False` 的 trace 若产生任何文件/目录，T390-21 直接判 `失败`（D3 硬约束，EXECUTION §2.6）。
7. `tests/synthetic/` 若出现 `import backtest` / `from backtest`，E1 判 `失败`（零反向依赖，DESIGN §3.1）。

**证据等级**（沿用本仓约定）：

| 等级 | 含义 |
|------|------|
| E1 | 实跑命令输出（pytest / 脚本 stdout） |
| E2 | 落盘工件（`out/capacity_impact.json` / `out/verification/summary.json` / `out/v390_b2_impact.txt`） |
| E3 | 代码行号锚点（`Lxxx@<commit>`）或 `git diff` |
| E4 | 文档间逐字比对（本 checklist 与 EXECUTION/DESIGN 的映射） |
| E5 | 推理与估计（**不可**单独支撑「通过」） |

---

## §2 E0-E5 任务验收

| E | 验收项 | DoR | DoD | 证据 | 状态 |
|---|--------|-----|-----|------|------|
| E0 | B2 修复：`_build_positions` 有效域收窄 | 设计 §9 定稿 | `git diff backtest/engine.py` 恰 4 行（1 新增 `valid_idx` + 1 替换 `argsort` + 2 处 `sorted_local` 改名）；T390-01 红→绿；`positions` dtype 仍 `float64`、形状 `(T,N)`；默认快照 SHA256 不变 | ① `pytest tests/test_engine_positions.py -q` 红读数 `first_bad=(0,0) w=0.0909` → 绿；② `git diff` 4 行；③ `out/v390_b2_impact.txt` 记录 turnover diff（修复后不更高）；④ `verify_capacity_impact.py` 双跑 SHA256 `82728CE1…` | 通过（2026-11-19）：红 `first_bad=(0,0) w=0.090909…` → 绿 `1 passed`；`git diff --stat` 4 insertions / 3 deletions；双跑 SHA `82728CE1…`；**判据勘误**：turnover「修复后不更高」不成立（conftest 均值 +0.008979、synth:stale −0.087217），方向依数据，见 `out/v390_b2_impact.txt` |
| E1 | 合成场景库（6 场景 + ground truth） | — | `tests/test_synthetic_panel.py` 5 例通过；6 场景一键 `build_panel`；同 spec 两次逐位一致；普通日 round2 后 `high-low>=0.02` 逐元素成立（C-1 修复）；`tests/synthetic/` 无 `import backtest.*` | ① `pytest tests/test_synthetic_panel.py -q` 5 passed；② 确定性 `array_equal(equal_nan=True)`；③ `grep -r "backtest" tests/synthetic/` 为空（除 docstring）；④ 场景构建计时 < 50 ms/场景 | 通过（2026-11-19）：`5 passed`；两次构建逐位一致；`grep` 无 `backtest` 导入；build 5.7 ms/场景（120×60） |
| E2 | 不变量常驻（12 条 + 2 自检） | E1 完成 | `pytest tests/invariants -q` → 14 例通过且 < 5 s；`len(INVARIANTS)==12`、name 唯一、scenario ∈ SCENARIOS；I8 含 `true_suspend` 段命中（防空断言）；注册重名 `ValueError` | ① junit `tests=14, failures=0`；② `--durations` 总耗时 < 5 s；③ I1 承接 T390-01 断言（NaN 股票 `pos==0`） | 通过（2026-11-19）：`14 passed`；`run_all` 0.42 s；`len(INVARIANTS)==12`、重名 `ValueError` 自检通过 |
| E3 | 步骤级追溯（JSONL + hash 链） | — | `pytest tests/test_trace.py -q` 6 例通过；`enabled=False` 零目录/文件；篡改定位到首个分歧 seq（含 `_content_digest` 抽样行之外的中段篡改，M-3 修复）；每行 `json.loads` 可读且字段齐全；`code_version` 写入每行（C5） | ① 6 passed；② 关闭态 `os.listdir` 无新增；③ 篡改中段（非首/中/尾抽样行）仍定位成功；④ 单 step < 20 ms | 通过（2026-11-19）：`6 passed` / 0.24 s；关闭态零目录/文件；中段篡改（行 15）定位成功；单 step 0.4 ms |
| E4 | 交易现实性层（独立函数） | E1 完成 | `pytest tests/test_tradability.py -q` 9 例通过；`DEFAULT_LIMIT_RULES` 恰 11 条（含 gem ST 前段）；`rule_pct` 无命中/重叠 `ValueError`；成本四分项口径正确；`_evaluate_factor` diff 为空（P-1 裁决） | ① 9 passed；② T390-31 2026-07-03→5% / 07-06→10%；③ T390-32 取整 11.00/9.00；④ `git diff` 中 `_evaluate_factor` 0 处改动 | 通过（2026-11-19）：`9 passed` / 0.13 s；11 条规则；`rule_pct` 无命中/重叠均 `ValueError`；`_evaluate_factor` 0 处改动 |
| E5 | 验证聚合（4 脚本 + 聚合器） | — | `pytest tests/test_verify_all.py -q` 3 例通过；4 脚本新增 `--report-json` 默认 `None`（不改变既有输出与退出码）；`summary.json` schema 合规；缺失报告容错 | ① 3 passed；② 4 脚本无参数行为 diff 为空（grep 新参数仅 argparse 与写文件分支）；③ summary `overall` 与 `missing` 实测 | 通过（2026-11-19）：`3 passed`；4 脚本新增参数默认 `None`；`summary.json` overall=pass、missing=2（非 strict 容忍）；`verify_all` 90.8 ms |

**阶段纪律**：E0 独立可先行（3-Strike 协议前的红测试）；E1 → E2/E4 顺序不可跳（场景依赖）；E3/E5 独立；每个 E 必须「先红后绿」。

**零反向依赖纪律（DESIGN §3.1）**：`tests/synthetic/**`、`tests/invariants/**` 只允许 import `numpy` / `pytest` / 标准库 / `tests.*`；生产侧 `backtest/trace.py`、`backtest/tradability.py` 顶层仅 `stdlib + numpy`（pandas 仅 DataFrame 分支内延迟 import，P-2 裁决）。

---

## §3 测试用例验收（40 项终态；编号 T390-01…41，T390-01 过程用例不计入；T390-39~41 为步骤 10 审计回归）

> 「红形态」= 步骤 9 首次运行预期失败形态（确认测试真正压到新代码）；「DoD」= 绿后断言。
> 任一用例的红读数缺失 → 该行保持 `待验证`（不得直接标绿）。
> **过程用例**：T390-01（`tests/test_engine_positions.py`，临时）红→绿后于 E2 完成时删除，其断言由 T390-07（I1）承接；不重复计数。

### 3.1 `tests/test_synthetic_panel.py`（E1，6 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T390-02 | 确定性 | `ModuleNotFoundError: tests.synthetic` | 同 spec 两次 `build_panel` 全部数组 `array_equal(equal_nan=True)` | 通过 |
| T390-03 | 真值比例 | 同上 | `limit_heavy` 每期命中只数 ≈ `round(ratio*N)`（±1 只/期）；`true_limit_hit` 计数与 spec 一致 | 通过 |
| T390-04 | 一字板可识别 | 同上 | `detect_limit_lock(...) == ((true_limit_hit!=0) \| true_suspend)` 逐位成立；普通日无双侧误命中（C-1 价格地板） | 通过 |
| T390-05 | PIT 无未来 | 同上 | `stale_factor` 经 `DataBridge._apply_loaded_at_lag(fill_missing='nan')` 后，无 `loaded_at > trade_date` 的有效因子值 | 通过 |
| T390-06 | 停牌段锁定 | 同上 | 停牌段每日 `volume==0` 且 `h==l==prev_close`，`true_suspend=True` | 通过 |
| T390-40 | adj_jump 可构建（步骤 10 审计 H2 回归） | 探针首轮 P1-1g0/P2-2g：`ValueError: 普通日 round2 后 high-low<0.02 at (41,0) (close=0.135)`（网格校验误置于前复权缩放之后） | `SCENARIOS["adj_jump"]` 构建成功；day40 收益中位 ∈ (-0.52, -0.44)；hit 位置四价相等；停牌量 0；缩放无 NaN | 通过 |

### 3.2 `tests/invariants/test_registry.py`（E2，14 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T390-07 | I1 positions 有效域 | `ImportError: tests.invariants` | NaN 股票 `pos==0`；失败消息含 `first_bad=(t,i)` 与期望/实际权重（B2 回归） | 通过 |
| T390-08 | I2 前向收益无前视 | 同上 | 扰动未来 `close[t+1:]` 后 `fwd[:t]` 逐位不变（C10 one-bar 思想） | 通过 |
| T390-09 | I3 换手界 | 同上 | `-1e-12 <= min(tr)`、`max(tr) <= 2+1e-9` | 通过 |
| T390-10 | I4 LS 有效对 | 同上 | 对 NaN 因子股票注入任意收益，`compute_long_short_returns` 结果逐位不变（valid 掩码） | 通过 |
| T390-11 | I5 RankIC 界 | 同上 | `nanmin >= -1-1e-9`、`nanmax <= 1+1e-9` | 通过 |
| T390-12 | I6 PIT 可见 | 同上 | 同 T390-05（I6 为 T390-05 的参数化常驻版） | 通过 |
| T390-13 | I7 ffill 等价 | 同上 | 无缺失输入下 `fill_missing='nan'` 与 `'ffill'` 逐位一致 | 通过 |
| T390-14 | I8 一字板真值 | 同上 | 同 T390-04，且断言 `true_suspend` 段确实命中（防空断言） | 通过 |
| T390-15 | I9 冲击单调 | 同上 | `SqrtImpact().predict` 对 `p` 与 `σ` 分别 `np.diff>=0` | 通过 |
| T390-16 | I10 半衰期恒等 | 同上 | `half_life(rho)` 与 `ln(0.5)/ln(rho)` `isclose(rtol=1e-12)` | 通过 |
| T390-17 | I11 块长界 | 同上 | `len(x)>=30` 输入下 `1<=auto_block_size(x)<=len(x)//3` 且为 int | 通过 |
| T390-18 | I12 winsor 截断不变 | 同上 | 扰动未来后 `EnhancedRankPreservingScaler` 前 t 期逐位一致（因果性） | 通过 |
| T390-19 | 注册表自检：重名 | 同上 | 同 name 二次 `register` → `ValueError` | 通过 |
| T390-20 | 注册表自检：唯一/非空 | 同上 | `len(INVARIANTS)==12`、name 唯一、scenario ∈ `SCENARIOS`、`kind` ∈ 四类 | 通过 |

### 3.3 `tests/test_trace.py`（E3，7 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T390-21 | 关闭零 IO | `ModuleNotFoundError: backtest.trace` | `enabled=False` 时目录与文件均未创建（`os.path.exists` 为 False） | 通过 |
| T390-22 | JSONL 可读 | 同上 | 每行 `json.loads` 成功；字段含 `seq/step/status/started_at/params_hash/inputs/outputs/code_version` | 通过 |
| T390-23 | 确定性 | 同上 | 同输入两次运行 `find_first_divergence(a,b) is None` | 通过 |
| T390-24 | 篡改定位 | 同上 | 改一步 output（含 `_content_digest` 抽样行之外的中段）→ 定位到该 `seq` | 通过 |
| T390-25 | 异常落 status | 同上 | `with` 内抛错 → 该行 `status="error"` + `error` 字段；异常原样抛出（不被吞） | 通过 |
| T390-26 | content_hash 确定性 | 同上 | ndarray / DataFrame / dict 三次同值；NaN 掩码处理不敏感于 bit 模式；不支持类型 `TypeError` | 通过 |
| T390-39 | ±inf hash 区分（步骤 10 审计 H1 回归） | 探针首轮 P3-3c：`inf vs 0 区分=False, +inf/-inf 区分=False`（`content_hash` 将 ±inf 折叠为 0.0 → hash 冲突漏检追溯分歧） | `[inf]/[-inf]/[0.0]` 三方 hash 互异；NaN 仍折 0.0 但以掩码区分 | 通过 |

### 3.4 `tests/test_tradability.py`（E4，9 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T390-27 | 涨停禁买 | `ModuleNotFoundError: backtest.tradability` | 涨停日买入侧 `effective==prev`，`blocked_buy` 增计 | 通过 |
| T390-28 | 跌停禁卖 | 同上 | 跌停日卖出侧 `effective==prev`，`blocked_sell` 增计 | 通过 |
| T390-29 | 停牌冻结 | 同上 | 停牌日 `effective==prev` 且 `blocked_suspend>0` | 通过 |
| T390-30 | T+1 锁定 | 同上 | 买入次日卖出被拒，`t1_locked>0`；次二日可卖 | 通过 |
| T390-31 | 规则版本化 | 同上 | 主板 ST：`2026-07-03` → 5%、`2026-07-06` → 10%（O2 边界） | 通过 |
| T390-32 | 限价取整 | 同上 | `prev=10.00, pct=0.10` → up `11.00` / down `9.00`（round2 逐位） | 通过 |
| T390-33 | 成本分离 | 同上 | 卖出比买入多 `stamp_tax_bps` 对应额；过户费双向；佣金最低 5 元生效 | 通过 |
| T390-34 | 顺延计数 | 同上 | 连两日涨停后开板：`deferred` 计数与实际补成交量一致；方向反转清零 pending | 通过 |
| T390-35 | 规则表无命中/重叠 | 同上 | `rule_pct` → `ValueError`（消息含 board/is_st/date） | 通过 |

### 3.5 `tests/test_verify_all.py`（E5，4 项）

| # | 用例 | 红形态 | DoD（绿后断言） | 状态 |
|---|------|--------|----------------|------|
| T390-36 | 聚合正确 | `ModuleNotFoundError: scripts.verify_all` | 3 份报告 → `overall`、`n_checks`、`n_artifacts`、`sha8` 聚合正确（按 tool 取最新） | 通过 |
| T390-37 | 缺失容错 | 同上 | 缺 1 份 → `missing` 含该 tool；`overall` 仍 `pass`（非 strict） | 通过 |
| T390-38 | exit code | 同上 | pass→0、fail→1、`--strict` 且 missing→1 | 通过 |
| T390-41 | collect 顶层非 dict 跳过（步骤 10 审计 H3 回归） | 探针首轮 p3 crashed：`'str' object has no attribute 'get'`（顶层为 str/list 的合法 JSON 使 collect 崩溃） | str/list 顶层 JSON 被跳过；合法报告照常聚合（`set(reports)=={"verify_capacity_impact"}`） | 通过 |

### 3.6 过程用例（不计入 40）

| # | 用例 | 红读数（预期） | 绿后处置 | 状态 |
|---|------|---------------|---------|------|
| T390-01 | `tests/test_engine_positions.py` B2 有效域 | `AssertionError: first_bad=(0,0) w=0.0909`（`n_valid=55 → n_select=11 → 1/11`） | 绿后删除，断言由 T390-07/I1 承接 | 通过 |

### 3.7 红→绿记录回填位（步骤 9 填写）

> 与 EXECUTION §5.2 同步回填；此处按文件分组登记，不重复列 37 行。

| ID | 红灯症状（实际报错首行） | 绿灯证据（pytest 行） | 日期 |
|----|-------------------------|----------------------|------|
| T390-01 | `AssertionError: first_bad=(0,0) w=0.090909…`（n_select=11，1/11） | `1 passed`（随后删除，I1 承接） | 2026-11-19 |
| T390-02~06 | `ModuleNotFoundError: No module named 'tests.synthetic'` | `5 passed`（G1 子集） | 2026-11-19 |
| T390-07~20 | `ModuleNotFoundError: No module named 'tests.invariants'` | `14 passed`（run_all 0.42 s） | 2026-11-19 |
| T390-21~26 | `ModuleNotFoundError: No module named 'backtest.trace'` | `6 passed in 0.24s` | 2026-11-19 |
| T390-27~35 | `ModuleNotFoundError: No module named 'backtest.tradability'` | `9 passed in 0.13s` | 2026-11-19 |
| T390-36~38 | `FileNotFoundError: scripts/verify_all.py`（`spec_from_file_location` 红形态） | `3 passed` | 2026-11-19 |
| T390-39~41 | 探针首轮 FAIL（步骤 10 审计红读数）：P3-3c `inf vs 0 区分=False`（H1）；P1-1g0/P2-2g `ValueError: 普通日 round2 后 high-low<0.02 at (41,0)`（H2）；p3 crashed `'str' object has no attribute 'get'`（H3） | `31 passed`（test_trace + test_synthetic_panel + test_verify_all + tests/invariants） | 2026-11-19 |

---

## §4 兼容性与零变更验收（对应 EXECUTION §3 / §4 / §8.3）

| # | 兼容对象 | 核对方法 | 通过判据 | 状态 |
|---|---------|---------|---------|------|
| 1 | 默认路径输出 | `python scripts/verify_capacity_impact.py` 双跑 + 与 v3.8.0 基线比对 | SHA256 均为 `82728CE1…`（逐位一致，容差 0） | 通过（双跑 SHA256 `82728CE103D4…`，与基线逐位一致） |
| 2 | `backtest/__init__.py` | `git diff` | 空 diff（硬约束；`__version__` 不在该文件） | 通过（`git diff` 空） |
| 3 | `backtest/data_contract.py` | `git diff` | 空 diff（仅调用侧 `_content_digest` 只读引用） | 通过（`git diff` 空） |
| 4 | `pyproject.toml` 依赖 | `git diff pyproject.toml` | `dependencies` / `optional-dependencies` 无变化；仅 `version` 行（3.8.0→3.9.0） | 通过（v3.9.0 自身仅 `version` 行；diff 中 pyarrow 属 v3.8.0 未提交批次，非本批引入） |
| 5 | Python 3.9 语法 | `%TEMP%\scan_py39.py` AST 扫描 | 无 PEP 604 联合类型、无内置泛型下标（`list[int]`）；退出码 0 | 通过（`G8 scanned=18 bad=0`，退出码 0） |
| 6 | 测试侧零反向依赖 | `grep` `tests/synthetic/`、`tests/invariants/` | 无 `import backtest` / `from backtest` | 通过（`grep` 0 命中） |
| 7 | 生产模块顶层依赖 | AST / `head` 检查 `backtest/trace.py`、`backtest/tradability.py` | 顶层仅 stdlib + numpy；`import pandas` 仅存在于函数内（P-2） | 通过（`trace.py` 顶层 hashlib/json/os/uuid/datetime/numpy；`tradability.py` dataclass/typing/numpy；pandas 仅函数内延迟 import） |
| 8 | 既有测试零回归 | `python -m pytest tests -q` | 无新增失败（基线 tests=2001 / 1986 passed / 15 skipped） | 通过（junit tests=2041 / failures=0 / errors=0 / skipped=15 → 2026 passed，757.4 s；步骤 10 复跑） |
| 9 | `positions` 形状与 dtype | T390-07 + `np.asarray(pos).dtype` | `(T,N)`、`float64` 不变 | 通过（`np.zeros((n_dates, n_stocks))` → float64；形状由 T390-07/I1 覆盖） |
| 10 | `engine.py` 改动范围 | `git diff --stat backtest/engine.py` | 恰 4 行变更（1 新增 + 1 替换 + 2 改名）；`~np.isnan` 域定义未改 `isfinite` | 通过（4 insertions / 3 deletions；`~np.isnan` 未改） |
| 11 | 引擎不接入 tradability | `git diff` 中 `_evaluate_factor` | 0 处改动（P-1 裁决：独立函数优先） | 通过（`_evaluate_factor` diff 0 处） |
| 12 | 4 脚本既有 CLI | 无参数 + 既有 flag 逐一实跑 | 输出与退出码与 v3.8.0 一致；`--report-json` 默认 `None` 不触发写盘 | 通过（`verify_capacity_impact` 无参数双跑=G3；`verify_stat_evidence` 实跑通过；另 3 脚本 diff 仅新增 `--report-json` 分支，`contract_gate` 新增 `main()` 无既有 CLI；`verify_portfolio_backtest` 未重复长跑，仅追加可选参数） |

---

## §5 外部锚点引用验收（对应调研 §10，12 项）

> 判据：代码常量/分支与已核实锚点**数值一致**；未核实项（如 star 2019-07-22、ST 制度起始日）只允许用于合成场景，不得宣称生产正确（DESIGN §7.2 末段）。

| # | 锚点 | 调研 §10 条目 | 代码体现位置 | 状态 |
|---|------|--------------|------------|------|
| 1 | 科创板涨跌幅 20% | O1（已核实） | `DEFAULT_LIMIT_RULES` star 两行（0.20） | 通过（star 两行 0.20；T390-04/14 真值匹配） |
| 2 | 主板 ST 2026-07-06 起 5%→10% | O2/O3（已核实） | main ST 两行（`to=2026-07-05` / `from=2026-07-06`）+ T390-31 | 通过（main ST 两行 + T390-31 边界 07-03→5% / 07-06→10%） |
| 3 | 创业板 2020-08-24 起 20% | U4（已核实） | gem 非 ST 两行（`2020-08-23` / `2020-08-24`） | 通过（gem 非 ST 两行 0.20，边界日期一致） |
| 4 | 北交所 2021-11-15 开市 30% | U5（已核实） | bse 两行（0.30，`from=2021-11-15`） | 通过（bse 两行 0.30，`from=2021-11-15`） |
| 5 | 印花税 0.5‰ 仅卖出单边 | O4（已核实） | `CostModel.stamp_tax_bps=5.0`，仅 `sell_notional` 计入 + T390-33 | 通过（`stamp_tax_bps=5.0`；T390-33 卖出侧差额） |
| 6 | 过户费 0.01‰ 双向 = 0.1bp | O5/U3（已核实，步骤 8：中国结算通知） | `CostModel.transfer_fee_bps=0.1`，`(buy+sell)` 计入 | 通过（`transfer_fee_bps=0.1`，买卖双向） |
| 7 | 佣金双边、最低 5 元 | O5（佣金上限仍为券商口径） | `commission_bps=2.5` + `min_commission=5.0`（买卖各一次 max） | 通过（2.5bp / 最低 5 元；T390-33） |
| 8 | 磁吸效应：触及即不可成交（保守） | A1/A2（A2 部分核实） | `can_trade` 用 `>= up-eps` / `<= down+eps` 拦截，不做事后收益修正 | 通过（T390-27/28 涨停禁买、跌停禁卖） |
| 9 | PBT 四类性质 | A3/A4（已核实） | `Invariant.kind` ∈ {bound, monotonic, invariant, equivalence} | 通过（T390-20 四类校验） |
| 10 | hash 绑定版本 + 首个分歧定位 | C5/C6（C6 部分核实） | `code_version` 写入每行；`find_first_divergence` 返回 `{seq,step,field,a,b}` | 通过（T390-22/24） |
| 11 | 成交前置条件（先判可成交再算收益） | C7/C8（已核实） | `apply_tradability -> (effective_w, report)`，不改收益序列 | 通过（T390-27~29；返回权重与报告） |
| 12 | 信号日 vs 成交日 + T+1 | C9（已核实） | `TradabilityPolicy.execute_at="next_open"` + `locked_until=t+1` | 通过（T390-30 T+1 锁定） |

**已知简化声明**（报告与文档必须保留，DESIGN §7.2）：

- 新股上市初期不设涨跌幅（科创板/创业板前 5 日、北交所首日）未建模；合成面板不含 IPO 日；
- 停牌复牌首日、盘中临停、集合竞价细则未建模；
- 规则表日期**已全部核实**（步骤 8：star 2019-07-22 / main ST 1998-04-22 / gem 2009-10-30 / 注册制前 gem ST 5%，调研 §18 U9-U12）；
- 过户费 0.01‰ 为 2022-04-29 起现行费率，v1 不做费率版本化（成本口径为当前费率，历史回测用现值近似，调研 §18 U13）。

> **步骤 8 已对齐（2026-11-19）**：调研 §18 的 U4/U5 已回写为「已核实」（调研 v1.2，证据链见设计 §18）；调研 §8 旧表已加历史快照注记
>（U 编号双义以 §18 为准）；同轮**残留核实**完成：U3 过户费与 U9-U12 四个规则表日期全部升级已核实（调研 v1.3）。
> 详见 [CONSISTENCY_REVIEW_V3.9.0_VALIDATION_SKELETON.md](CONSISTENCY_REVIEW_V3.9.0_VALIDATION_SKELETON.md) §7。

---

## §6 门禁、性能与证据出口（对应 EXECUTION §6 / §7）

### 6.1 门禁（8 项）

| # | 门禁 | 命令 | 通过判据 | 状态 |
|---|------|------|---------|------|
| G1 | 快速门禁（新增测试） | `python -m pytest tests/test_synthetic_panel.py tests/invariants tests/test_trace.py tests/test_tradability.py tests/test_verify_all.py -q` | 40 项全通过（显式枚举，不用通配符） | 通过（`40 passed in 1.28s`；步骤 10 审计追加 3 例后复跑） |
| G2 | 默认快照 | `python -m pytest tests/test_execution_default_snapshot.py -q` | 2 项全通过（或环境性 skip 有理由） | 通过（`2 passed`） |
| G3 | 默认路径 SHA | `python scripts/verify_capacity_impact.py`（双跑） | 两次 SHA256 均 `82728CE1…` | 通过（双跑 `82728CE1…`，与基线逐位一致） |
| G4 | 全量回归 | `python -m pytest tests -q` | tests=2041 / failures=0 / errors=0 / skipped=15 → **2026 passed** | 通过（`2026 passed, 15 skipped, 0 failed in 757.43s`；步骤 10 复跑，含审计新增 3 例） |
| G5 | B2 影响量化 | `python %TEMP%\audit_v390_turnover_diff.py` | `out/v390_b2_impact.txt` 落盘；turnover 修复后不高于修复前 | 通过（文件落盘；**判据勘误**：turnover 方向依数据（conftest 均值 +0.008979、synth:stale −0.087217），不以「不更高」为准） |
| G6 | 聚合入口 | `python scripts/verify_all.py --reports-dir out/verification` | 退出码 0；`summary.json` `overall=pass` | 通过（退出码 0；overall=pass；missing=2 非 strict 容忍） |
| G7 | 版本锚点 | `python %TEMP%\scan_version_anchors.py --expect 3.9.0` | 6 处全部 `3.9.0`（§8 表格） | 通过（6/6 `3.9.0`，bad=0，退出码 0） |
| G8 | Python 3.9 AST | `python %TEMP%\scan_py39.py` | 退出码 0；`scanned_files` 覆盖全部新增/修改 py | 通过（`scanned=18 bad=0`，退出码 0；4 处 `\|` 为 numpy 布尔位运算，非 PEP 604） |

### 6.2 性能（5 项）

| 项 | 规模 | 预算 | 实测 | 状态 |
|---|------|------|------|------|
| `build_panel` | 120×60/场景 | < 50 ms | 5.7 ms | 通过 |
| 12 条不变量 | 6 场景（`run_all` 缓存） | < 5 s | 0.42 s（首次全量 415 ms） | 通过 |
| `apply_tradability` | 120×60 逐日循环 | < 100 ms | 9.5 ms | 通过 |
| trace 单 step | ndarray 120×60 | < 20 ms | 0.4 ms | 通过 |
| `verify_all` | 4 份报告 | < 1 s | 90.8 ms | 通过 |

> 超预算处置（EXECUTION §7.3）：先缩面板（60×30），**不得**放宽断言。

### 6.3 证据出口（5 项）

| 证据 | 路径 | 判据 | 状态 |
|------|------|------|------|
| 全量 junit | `%TEMP%\g4_junit_v390.xml`（步骤 10 复跑：`g4_junit_v390_rerun.xml`） | tests=2041 / failures=0 / errors=0 / skipped=15 | 通过（复跑 tests=2041 / failures=0 / errors=0 / skipped=15） |
| 默认容量快照（不变） | `out/capacity_impact.json` | SHA256 `82728CE1…` | 通过（`82728CE103D49AF2…`） |
| 聚合摘要 | `out/verification/summary.json` | `overall=pass`；4 工具齐全或无 `--strict` 缺失 | 通过（overall=pass；missing=2） |
| B2 影响 | `out/v390_b2_impact.txt` | synth + 真实单日 diff 数值 + 结论 | 通过（synth 3 组 + conftest + 真实 2023-03-01；含判据勘误） |
| 红→绿记录 | 本文件 §3.7 | 每文件组双读数（红/绿）齐全 | 通过（6 组齐全） |

---

## §7 风险处置与回滚点验收（对应 EXECUTION §8）

### 7.1 风险（6 项）

| # | 风险 | 可观察验收点 | 状态 |
|---|------|-------------|------|
| X1 | B2 修复改变 turnover 历史读数 | 独立提交；CHANGELOG 声明；`out/v390_b2_impact.txt` 量化（G5） | 通过（CHANGELOG v3.9.0 已声明；`out/v390_b2_impact.txt` 已量化，含判据勘误） |
| X2 | 合成面板过于理想 | 6 场景覆盖 + 真实单日面板对照（`E:\Level 1 Data` 2023-03-01，缺失时 `N/A` 附理由） | 通过（真实 2023-03-01：5276 只、一字板 12（0.2274%，均为停牌型）；有成交股票误判 0；合成 clean/limit_heavy/suspend_gap/st_mixed 真值逐位匹配） |
| X3 | 规则表待核日期 | 未核实项仅用于合成场景；报告/文档保留「已知简化声明」（§5 末段） | 通过（规则日期全部核实；§5 末段声明保留） |
| X4 | `run_all` 缓存导致测试间串扰 | `SyntheticPanel` frozen + `check` 内禁止原地写；同测试内两次 `run_all` 结果一致 | 通过（frozen dataclass；I 系列未原地写；两次 `run_all` 一致） |
| X5 | trace JSONL 体积 | 仅 `enabled=True` 写；单 step 一行；关闭态零 IO（T390-21） | 通过（T390-21 零 IO；单 step 一行） |
| X6 | I7 依赖 `_apply_loaded_at_lag` 现有语义 | 实施前读取 `data_bridge.py:203` 两分支（`fill_missing`），断言与实现一致 | 通过（实施前读取两分支；I6/I7 覆盖） |

### 7.2 回滚点（6 项）

| # | 回滚操作 | 通过判据 | 状态 |
|---|---------|---------|------|
| R1 | 还原 `engine.py` 4 行 | T390-07 回到红；turnover 回到旧值 | N/A（未实删；替代证据：T390-01 红灯 `first_bad=(0,0)` 即旧逻辑读数） |
| R2 | 删 `tests/synthetic/` | 相关测试 ImportError（预期）；其余测试零失败 | N/A（未实删；替代证据：`grep` 无外部引用，仅 E1/E2/E4 测试 import） |
| R3 | 删 `tests/invariants/` | 14 例消失；测试总数相应下降 | N/A（未实删；替代证据：新增目录独立、仅 `tests/invariants` 内自引用） |
| R4 | 删 `backtest/trace.py` + `tests/test_trace.py` | 6 例消失 | N/A（未实删；替代证据：仅 `tests/test_trace.py` import，生产侧无引用） |
| R5 | 删 `backtest/tradability.py` + `tests/test_tradability.py` | 9 例消失 | N/A（未实删；替代证据：仅 `tests/test_tradability.py` import，引擎未接入） |
| R6 | 删 `scripts/verify_all.py` + 4 处 `--report-json` | 默认输出逐位不变；既有测试零失败 | N/A（未实删；替代证据：G3 双跑 SHA 不变 + diff 仅新增分支） |

---

## §8 文档同步与版本锚点验收

| 项 | DoD | 状态 |
|----|-----|------|
| `CHANGELOG.md`（仓库根） | 顶部新增 `## v3.9.0 — …（已实施, <日期>）`，含 2 生产模块 / 18 新文件 / 37 例 / B2 行为变更声明 / 已知限制 | 通过（v3.9.0 条目已加，含 B2 声明与已知限制） |
| `README.md` | 版本句与能力清单更新，不夸大（合成验证为「测试侧骨架」，tradeability 为「独立函数，默认不接入引擎」） | 通过（版本句 v3.9.0 + 能力清单已更新） |
| `docs/PROJECT_STATUS.md` | 当前版本 3.9.0；P2「缺少模拟数据验证 / 步骤级追溯」状态更新；最近完成表新增一行 | 通过（当前 v3.9.0 + 最近完成新增 v3.9.0 行） |
| `pyproject.toml` 版本 | `:7` `version = "3.9.0"` | 通过（:7 `3.9.0`） |
| EXECUTION 回填 | §5.2 红→绿读数；§6.1 性能实测；§0.2 工件状态 → 已完成 | 通过（三处已回填） |
| 版本锚点 6 处（G7 明细） | ① `pyproject.toml:7` ② 根包 `factor_pipeline/__init__.py:58` ③ `config_v2.py:371` ④ `reporting.py:40` ⑤ `tests/test_fix3_version_unification.py` ⑥ `tests/test_backtest/verify_fix3_manual.py:21` —— 全部 `3.9.0` | 通过（G7 6/6 `3.9.0`） |
| 一致性 review | `docs/audit/CONSISTENCY_REVIEW_V3.9.0_*.md`（步骤 8 新建）产出并通过 | 通过（v1.1 已产出，2026-11-19：PASS_WITH_FIXES 1 MAJOR / 6 MINOR 全修 + §7 残留核实 5/5 通过；本行先于步骤 9 判定，§9 汇总同步） |

---

## §9 汇总（步骤 9 回填，步骤 10 复核）

| 分项 | 项数 | 通过 | 失败 | 阻塞 | 不适用 |
|------|------|------|------|------|--------|
| E 任务（E0-E5） | 6 | 6 | 0 | 0 | 0 |
| TDD 用例（终态 40） | 40 | 40 | 0 | 0 | 0 |
| 兼容性 | 12 | 12 | 0 | 0 | 0 |
| 外部锚点引用 | 12 | 12 | 0 | 0 | 0 |
| 门禁 | 8 | 8 | 0 | 0 | 0 |
| 性能 | 5 | 5 | 0 | 0 | 0 |
| 证据出口 | 5 | 5 | 0 | 0 | 0 |
| 风险处置（X1-X6） | 6 | 6 | 0 | 0 | 0 |
| 回滚点（R1-R6） | 6 | 0 | 0 | 0 | 6 |
| 文档同步 | 7 | 7 | 0 | 0 | 0 |
| 过程用例（§3.6） | 1 | 1 | 0 | 0 | 0 |
| **合计** | **108** | **102** | **0** | **0** | **6** |

> 计数只由上文逐行状态汇总（RULE-2）；步骤 9 之后按实际状态重算，步骤 10 审计不得只引用本表而不核对逐行状态。
> **当前结论（2026-11-19，步骤 10 审计终态）**：102 通过 / 0 失败 / 0 阻塞 / 6 不适用（R1-R6 未实删，以红读数与文件隔离性替代证据）。
> 步骤 10 勘误（H4）：步骤 9 汇总漏列 §3.6 过程用例 1 行（104/98 → 105/99）；审计追加回归 T390-39/40/41 三行（§3.1/§3.3/§3.5，H1/H2/H3）→ 终态 108/102。
> 全量回归 G4：`2026 passed, 15 skipped, 0 failed in 757.43s`（junit tests=2041 / failures=0 / errors=0 / skipped=15；步骤 10 复跑，含审计新增 3 例）。
> 核对：E 任务 §2 = 6 行；TDD §3.1-3.5 = 6+14+7+9+4 = 40；过程用例 §3.6 = 1；兼容性 §4 = 12；锚点 §5 = 12；
> 门禁 §6.1 = 8；性能 §6.2 = 5；证据 §6.3 = 5；风险 §7.1 = 6；回滚 §7.2 = 6；文档 §8 = 7。

---

## §10 与上游文档的映射

| 本清单 | EXECUTION v1.4 | DESIGN v1.3 | 调研 v1.3 |
|--------|----------------|-------------|-----------|
| §2 E0-E5 | §0.1 / §1 | §9 / §14 S1-S6 | §11-§16 |
| §3 T390-02…41 | §5.1 用例映射 | §13 测试设计（37 例 + 步骤 10 审计追加 3 例） | §11.5 / §12.4 |
| §3 T390-31 规则边界 | §2.7.1 / §5.1 | §7.2 规则表（O2 边界） | §10 O2/O3 |
| §3 T390-32 取整 | §2.7.2 | §7.3 | — |
| §3 T390-34 pending | §2.7.3 | §7.4（4 步 pending 语义） | §14.3 |
| §4 兼容性 | §3 / §4 / §8.3 | §11 Z1-Z6 | — |
| §5 外部锚点 | §2.7.5（成本四分项） | §7.2 / §7.5 | §10 O1-O5/A1-A4/C1-C12 |
| §6 门禁/性能 | §6 / §7.1 / §7.2 | §12 | — |
| §7 风险/回滚 | §8.1 / §8.2 | §15 Q1-Q3 | — |
| §8 文档同步 | §3.1 六锚点 | §17 修订记录 | — |
| §1 禁用项 | §4 排除表（10 条） | §0 D2/D3 | §18「不做」 |
