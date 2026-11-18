# CHECKLIST v3.6.0 治理底座 — 验收清单

> **版本**: v1.0 (2026-11-17) — 步骤 7 产出
> **对应实施**: [EXECUTION_V3.6.0_GOVERNANCE_BASE.md](../EXECUTION_V3.6.0_GOVERNANCE_BASE.md) v1.0
> **对应设计**: `docs/private/DESIGN_GOVERNANCE_BASE.md` v1.2
> **对应调研**: [RESEARCH_GOVERNANCE_BASE.md](../research/RESEARCH_GOVERNANCE_BASE.md) v1.1
> **档位**: T1（完整管线）
> **状态词**: `待验证` / `通过` / `失败` / `阻塞` / `N/A（附理由）`
> **禁止**：无证据的 ✅；统计汇总只能来自逐项核对表（RULE-2）

---

## §1 DoR / DoD 定义

| 术语 | 含义 |
|------|------|
| **DoR**（Definition of Ready） | 该项可以开始验证的前置条件（工件存在 / 依赖就绪 / 环境可用） |
| **DoD**（Definition of Done） | 该项判定通过的**可观察**条件（命令 + 读数 / 文件 + 字段 / 断言） |

> 状态升级规则：`待验证` → `通过` 必须附"证据 + 读数 + 日期"；`失败` 必须附失败行；
> `阻塞` 必须附阻塞原因与解阻触发条件。

---

## §2 E 任务验收清单

| E | 验收项 | DoR | DoD | 测试/证据 | 状态 |
|---|--------|-----|-----|----------|------|
| E0 | 版本与基线冻结 | 仓库可运行；py312 editable 安装 | `tests-fast` exit 0；`unit-tests` exit 0 且读数入流（1864 passed / 7 skipped / 25:16）；5 处版本字面量清单已核（E8 复核为 6 处） | runner gate 事件流（E1） | 通过 |
| E1 | `governance.py` | DESIGN §4 稳定；模块可 import | T1-T10 全绿（11 passed）；`record_id` 1000 次同值；append 幂等；冲突抛错 | `test_governance.py`（E1） | 通过 |
| E2 | `data_contract.py` | E1 不阻塞；合成面板 fixture 就绪 | T11-T15 全绿（5 passed）；mv 5 日缺口 `passed=False` 且 block 含 `freshness`；正常数据 0 block | `test_data_contract.py`（E1） | 通过 |
| E3 | `golden_master.py` + fixture | E1 hash 可用；DuckDB parquet 读写可用 | T16-T20 全绿（5 passed）；同输出 `max_abs_diff=0`；1e-8 差异 FAIL；capture 不覆盖 | `test_golden_master.py`（E1） | 通过（机制 + 提交式 fixture：`tests/golden/govbase_v1_synth` 已入库） |
| E4 | 台账 + 检验注入 | E1 可用；`multiple_testing.py` 可改 | T21-T30 全绿（10 passed；同文件含 T39/T40 后 12 passed）；BH/BY ≤1e-12；RW ≤1e-15（阈值 1e-10）；`bootstrap_indices=None` 原路径逐值不变（既有 58 passed 回归） | `test_multiple_testing_ledger.py`（E1） | 通过 |
| E5 | Stata 对拍 | E4 API 稳定；Stata 路径存在 | `--case all` 退出 0（Stata 18.0）；JSON 含每 case Python/Stata/diff/verdict；Hansen 双口径（studentized 0.548 vs 仓库 0.498） | `out/stata_econ_crosscheck.json`（E2） | 通过 |
| E6 | 管线 hook | E1 契约稳定；全量回归基线可用 | T31/T32 通过；未设 hook 时 golden 1e-10 零差异；事件字段齐全（9 字段） | 全量回归 + `test_pipelines_v2`（E1） | 通过（T31 golden PASS 且 `max_abs_diff<=1e-10`；T32 9 字段；unit-tests 1907 passed / 7 skipped，较基线 +43 = 本批新增用例） |
| E7 | 研究脚本适配 | E2 契约可用 | 容量/多头端入口显式调用契约且报告落盘 | 脚本文档 + 运行日志（E2） | 通过（`--contract`/`--contract-only` 接线；dry-run 正确拦截 mv 5 日缺口 → exit 2；报告落盘 `out/*_contract.{json,md}`；默认路径零变更） |
| E8 | 文档闭环 | E1-E6 完成 | 6 处版本 = 3.6.0；ADR-050~054 落 `DECISIONS.md`；CHANGELOG/PROJECT_STATUS/ARCHITECTURE 同步 | `test_fix3_version_unification` + grep（E1） | 通过（6 锚点均 3.6.0；`gate version-consistency` pass；ADR-050~054 落档；四文档 + README/README.en/CODE_WIKI 同步） |

---

## §3 测试用例验收（T1-T50）

### 3.1 GR-1（E1）

| 用例 | DoD | 状态 |
|------|-----|------|
| T1 record_id 确定性 | 同输入 1000 次 → 单一值 | 通过 |
| T2 身份敏感性 | 逐字段改 → id 均变（24/24 字段） | 通过 |
| T3 易变字段不影响 | timestamp/reviewer/env 改 → id 同；结果字段改 → payload_hash 变 | 通过 |
| T4 stage 必填 | S3 缺 effect/ci → `ValidationError`；S0 缺 holdout → 同 | 通过 |
| T5 production 门禁 | S5 + production 缺 G4/G5 → `ValidationError`；S5 + research → 拒绝 | 通过 |
| T6 roundtrip | dump→JSON→validate 相等（含 None/NaN 边界） | 通过 |
| T7 幂等 | 同 record 写两次 → 1 行、第二次返回 False | 通过 |
| T7b 批量写入 | `append_many` 批内重复保留首条；只走 INSERT...SELECT | 通过 |
| T8 冲突 | 同 id 不同 payload → `ReproducibilityConflictError`；`keep_first` 保留首条 | 通过 |
| T9 query/latest | 过滤正确；`latest` 取最新；空结果不抛错 | 通过 |
| T10 JSONL fallback | 无 duckdb 环境（monkeypatch）可用；与 DuckDB 语义一致 | 通过 |

### 3.2 GR-2（E2）

| 用例 | DoD | 状态 |
|------|-----|------|
| T11 mv 缺口拦截 | `last_full_date=2026-01-23`、`sample_end=2026-01-30` → `passed=False`，block 含 `freshness` | 通过 |
| T12 正常数据 | 合成面板 → `passed=True`，block 数 0 | 通过 |
| T13 PIT 违规 | 上市日前有值 → block；list_date 缺失 → warn | 通过 |
| T14 可选缺失 | volume/suspend 缺 → warn，不 block | 通过 |
| T15 缓存命中 | 第二次快照 reader 调用次数为 0；mtime 变内容同 → 同 digest + 同 stable_hash | 通过 |

### 3.3 GR-3（E3）

| 用例 | DoD | 状态 |
|------|-----|------|
| T16 完全相同 | PASS，`max_abs_diff=0`，n_common=12 | 通过 |
| T17 容差边界 | 1e-11 差 PASS；1e-8 差 FAIL（12 mismatch） | 通过 |
| T18 参数变更 | percentile 2/98 输出 → FAIL | 通过 |
| T19 缺/多股 | `n_missing=3` / `n_extra=3` | 通过 |
| T20 capture 不覆盖 | 已存在 → `FileExistsError`；force 无 reason/reviewer → `ValueError`；带审计可覆盖 | 通过 |

### 3.4 GR-4（E4）

| 用例 | DoD | 状态 |
|------|-----|------|
| T21 未预注册拒绝 | 未注册 family/variant → 异常；exploratory 允许 | 通过 |
| T22 时序 | `created_at < registered_at` → `PreregistrationError` | 通过 |
| T23 BH 参考 | q/掩码与 `apply_bh_fdr` ≤1e-12 | 通过 |
| T24 BY 参考 | 同上 ≤1e-12 | 通过 |
| T25 `<= α` 边界 | q==α 判显著 | 通过 |
| T26 RW 参考 | 同 t* 矩阵 → p_adj ≤1e-10 | 通过 |
| T27 RW 快速核 | 与原实现 ≤1e-15；k=1 快速、k>1 回退 | 通过 |
| T28 White/SPA joint | 同索引矩阵 → p ≤1e-10；lc≥consistent≥uc | 通过 |
| T29 三分母 | `n_trials ≥ n_testable ≥ n_hypotheses`；含失败/重复/exploratory | 通过 |
| T30 轨不匹配 | FDR+Bonferroni / FWER+BH → `TrackMismatchError` | 通过 |

### 3.5 hook / 补充用例 / 研究入口（E6-E7 + 全覆盖）

| 用例 | DoD | 状态 |
|------|-----|------|
| T31 未设 hook | 输出与基线 1e-10 一致 | 通过 |
| T32 事件字段 | 每因子一条 dict；9 字段齐全（EXECUTION §2.6） | 通过 |
| T33 模块隔离 | AST 扫描四模块互不 import | 通过（表征测试，先绿） |
| T34 旧 schema | 更旧补默认 + `legacy=True`；更新原样 dict + warning；不丢记录 | 通过 |
| T35 content_digest | mtime 变内容同 → 同 hash；内容变 → hash 变 | 通过（表征测试，先绿） |
| T36 cache 防陈旧 | `copy2` 恢复（mtime 保留）后仍能识别内容一致；同 size 同 mtime 首 64KB 变 → 失效 | 通过 |
| T37 expected_missing_tail | forward return 末行缺失不算 freshness 缺口（`lag` 扣除、`raw_lag` 保留） | 通过 |
| T38 NaN 率守卫 | actual 比 baseline 多 2% → FAIL（`nan_rate_guard_triggered=True`） | 通过 |
| T39 backfill 隔离 | backfill trial 不进 confirmatory 主分析（`n_hypotheses` 不变、`n_trials` +1） | 通过 |
| T40 result_id 稳定 | 新增 exploratory trial 不改变主 `result_id` | 通过 |
| T41 ancestors 循环 | 循环 → 异常；断链 → `broken_link` 标注（`AncestorEntry`） | 通过 |
| T42 gate_status 键 | 未知键 → 拒绝 | 通过 |
| T43 时区 | 全部时间字段为带时区 UTC ISO | 通过 |
| T44 jsonl 锁 | `lock_path` 获取/释放；并发线程无交错 | 通过 |
| T45 签名稳定 | `bootstrap_indices` 默认 None | 通过 |
| T46 env_fingerprint | 含 python/numpy/pandas/BLAS/线程；可 JSON 序列化 | 通过（表征测试，先绿） |
| T47 hfq 锁定 | production/golden 拒绝 `qfq`；research 允许并原样写入；非法枚举拒绝 | 通过（红：`extra_forbidden` → 绿） |
| T48 tradable 代理 | `st_source`/`suspend_source` 默认补全并写入 record；非法取值拒绝 | 通过（红：`KeyError 'st_source'` → 绿） |
| T48b 口径进 ID | 不同 `st_source` → 不同 `record_id` | 通过（表征测试，先绿；DR-25） |
| T49 known_gap 码名 | `barra_stale`/`industry_stale` 对齐设计 §5.7.4，不误判 block | 通过（红：`barra_missing` → 绿） |
| T50 adj_alignment 严重度 | research=warn（默认）/ production=block；非法 `mode` 拒绝 | 通过（红：`TypeError: unexpected keyword 'mode'` → 绿；DR-26） |

---

## §4 兼容性与零变更验收

| 项 | DoD | 状态 |
|----|-----|------|
| 不新增第三方依赖 | `pyproject.toml` dependencies 无新增行 | 通过（diff 仅 `version` 行） |
| 不改变导入面 | `backtest/__init__.py` 无 diff | 通过（空 diff） |
| `pipelines_v2` 默认零变更 | 未设 hook 时全量回归 + golden 1e-10 零差异 | 通过（T31 golden PASS；`test_pipelines_v2` 13 passed；全量 1920 passed / 0 失败） |
| `bootstrap_indices=None` | 原 `WhiteRealityCheck`/`HansenSPA` 测试全绿 | 通过（T45 签名断言 + T28 注入路径；既有 58 passed） |
| Python 3.9 语法 | 无 PEP 604 / 内置泛型下标 | 通过（AST 扫描 5 模块，0 违规） |
| 缓存代际不变 | 仍为 `v2.3.0-cache` | 通过（`cache_manager.py` 提取值 = `v2.3.0-cache`） |
| 版本一致性 | 6 处字面量 = 3.6.0；`test_fix3_version_unification` 通过 | 通过（`gate version-consistency` pass；手工 6/6） |

---

## §5 性能验收（承接 EXECUTION §6）

| 环节 | DoD（预算） | 测量方式 | 测量读数 | 状态 |
|------|------------|---------|---------|------|
| 契约冷启动 7 字段 | <10s | `perf_counter` | **0.090s** | 通过 |
| 契约缓存命中 | <0.1s | 第二次调用 | **0.0021s** | 通过 |
| 记录写入 10k | <0.1s（**重估 1.0s**） | `append_many` | **0.724s**（性能包复测；原 4.442s） | 通过（重估预算内，[PERF_PACK DR-P1](../EXECUTION_V3.6.0_PERF_PACK.md)） |
| BH 10 万假设 | <0.05s | 合成 p 向量 | **0.0156s**（原 0.081s） | 通过（性能包 O2） |
| RW m=1000,B=1000 | <0.5s | 合成 t* 矩阵 | **0.0071s**（原 3.203s） | 通过（性能包 O3） |
| White/SPA T=1000,K=100,B=1000 | <10s，<1GB | `tracemalloc` | **White 7.56s / SPA 3.89s**（原 >300s 未完成）；峰值内存 **170.9 / 170.2 MB** | 通过（性能包 O4） |
| golden 比较 24×300×4 | <0.1s | 计时（含 parquet 读写） | **0.0586s**（原 0.140s） | 通过（性能包 O5） |
| 全量测试耗时 | 不劣化 >20% | 与 E0 基线对比 | **742.43s vs 1516.82s（ratio 0.49）** | 通过 |

> 超预算 → P2 问题；须登记原因与后续优化项，不阻断功能验收。
> 本批 8 项中 3 项达标（含全量耗时比 0.49）、5 项超预算（P2-1）；证据 `out/govbase_perf.json`（E2）。
> **2026-11-18 性能包关闭 P2-1**：5 项全部复测达标（O1 预算按序列化下界重估 0.1→1.0s），读数见 [PERF_PACK §5](../EXECUTION_V3.6.0_PERF_PACK.md) 与 `out/perf_profile.py`。

---

## §6 数据与口径验收

| 项 | DoD | 状态 |
|----|-----|------|
| mv 5 日缺口 | 契约拦截（block），报告含 `freshness` 与 lag=5 | 通过（两次 dry-run exit 2；BLOCK `mv` lag=5，`last_full=2026-01-23, end=2026-01-30`） |
| adj 行数不对齐（81 日） | `adj_alignment` 检查可见；research=warn、production=block；披露入 `known_gaps` | 通过（dry-run WARN 缺 81 日；T50 mode 升级） |
| hfq 锁定 | `price_convention='qfq'` + production/golden → 拒绝 | 通过（T47：production/G4 拒绝，research 允许并写入） |
| 幸存者偏差 | `universe_bias` 写入 record；`ContractReport` 不承诺检测 | 通过（`DataSnapshot.universe_bias` 默认 `unknown`；`to_record_fields` 落 record；不承诺检测） |
| ST/停牌代理口径 | `tradable_convention.st_source/suspend_source` 必填且可追溯 | 通过（T48/T48b：默认 `name_proxy`/`event_rebuild`，进 record 与 `record_id`） |
| 交易日历 | `calendar_hash` 入快照；bdate 兜底时 `calendar_source='bdate_fallback'` + warn | 通过（`calendar_hash` 入 `data_snapshot_hash`；fallback warn 见 `data_contract.py` L800-805；本次 dry-run `injected`） |
| barra/行业断档 | `known_gaps` 含 `barra_stale`/`industry_stale`；不 block | 通过（T49 + 重新生成报告 `industry_stale`；INFO 不 block） |

---

## §7 文档一致性验收（步骤 8 输入）

| 检查 | DoD | 状态 |
|------|-----|------|
| RESEARCH → DESIGN | 设计引用的调研结论均有 § 锚点；FALSIFIED 已改写 | **通过**（CONSISTENCY_REVIEW §3.1，5/5） |
| DESIGN → EXECUTION | §10.1 公共符号 32/32 出现；§12 测试 T1-T32 全映射 | **通过**（机械读数 32/32、32/32） |
| EXECUTION → CHECKLIST | §2 E0-E8 与 §3 T1-T50 均有验收项 | **通过**（本文覆盖） |
| 双向引用 | 四文档 + ADR-050~054 互引存在 | **通过**（E8：ADR 落档，反向引用闭合） |
| 断言延续 | 设计 §18 F-A~F-H/B* 在实施中有落点 | **通过**（CONSISTENCY_REVIEW §3.2，13/13） |
| 类型替换登记 | `known_gaps` 取 §5.7.4 结构（取代 §5.1 字符串）已登记 | **通过**（DR-4 / C2 / EXECUTION §9.6 F6） |
| 版本一致 | RESEARCH v1.1 / DESIGN v1.2 / EXECUTION v1.0 / CHECKLIST v1.0 | **通过** |

---

## §8 证据出口清单

| 验收范围 | 证据 | 等级 | 状态 |
|---------|------|------|------|
| E1-E7 测试 | runner gate 事件流 + pytest 退出码 | E1 | 通过（E1：11；E2：5→7；E3：5；E4：10→12；E5/T31-T35：6；E6：T36-T40 联合 22；E7：T41-T45 11 + contract_gate 2；本批 +T46-T50 6 → 本批新增 56 例（54 条 §3 用例 + contract_gate 2，分布于七文件）） |
| 零变更 | 全量回归 + golden 报告 | E1 | 通过（unit-tests **1920 passed / 7 skipped / 13 subtests / 742.43s**；基线 1864/7，+56 全为本批新增用例（E7 收尾 1914 → E8 +6：T46/T47/T48/T48b/T49/T50），0 失败 0 新增 skip；T31 golden `max_abs_diff<=1e-10`） |
| E7 契约门禁 | `out/*_contract.json` + dry-run 退出码 | E2 | 通过（两脚本 `--contract-only` → exit 2，BLOCK mv lag=5；`test_contract_gate.py` 2 passed） |
| 异构复审 | `out/review_govbase_results.txt` + `out/probe_review_govbase.py` | E2 | 通过（P1-P8；0 推翻 / 0 重大 / 0 中等；F1/F2 已披露入 EXECUTION §2.1/§2.5/§9.8） |
| 模块隔离 | AST 测试 + `git diff --stat` | E1 | 通过（T33；四模块 AST 无互 import） |
| 版本一致性 | 版本测试 + 6 处 grep | E1 | 通过（`gate version-consistency` pass；6/6 锚点 3.6.0；缓存独立） |
| E8 文档闭环 | `gate version-consistency` + ADR 索引 + 四文档/README/CODE_WIKI | E1 | 通过（6 锚点 3.6.0；ADR-050~054 落档；双向引用闭合） |
| 性能 | `out/govbase_perf.json` + `out/perf_profile.py` | E2 | 通过（初始取证 2/8 达标、5/8 超预算 → P2-1；性能包 O1-O5 复测 **5/5 达标**，O1 预算重估 0.1→1.0s） |
| ADD 审计 | `docs/audit/2026-11-18-v3.6.0-governance-base-audit.md` | E2/E3 | 通过（Phase 0-4 + 取证矩阵；P1 0 / P2 5（4 处置 + P2-5 落档）/ P3 7 披露） |
| 独立复审（批次收尾，RULE-5） | `out/review_v360_t46_e8_results.txt` | E2 | 通过（4 项发现：1 major R1 + 3 minor R2-R4，双验证器 2/2 确认、0 误报；R1 实测 `same id: False`；用户裁决落档不修码 → P2-5/P3-5~P3-7；R1-R4 已入 EXECUTION §9.9） |
| Stata 对拍 | `out/stata_econ_crosscheck.json` | E2 | 通过（Stata 18.0；`--case all` exit 0；bh/by/bonf/holm/RW/White/SPA PASS；dsr/pbo SKIP-P1） |
| 设计落地 | 行号 `Lxxx@commit` | E3 | 通过（ADD 审计 Phase 1 16/16；`@64e4053` + `@9221e7a`，P3-1 已回填） |
| 盲区扫描 | EXECUTION §9（E4，发现 7 项：2 MAJOR + 5 MINOR） | E4 | 通过（发现 7 项） |

> E5（推测/未执行）不得出现在验收结论中；仅可列入"未覆盖项"。

---

## §9 未覆盖项与豁免

| 项 | 理由 | 处置 |
|----|------|------|
| DSR / PBO 实装 | P1；本批只留接口 | 不验收 |
| Stata SSC `rwolf2`/`multproc` | 未安装 | 可选第二参照；不阻塞 |
| 真实 A 股 size/power（U1） | 依赖实施后 MC | E5 已提供 `--mc` 轻量自检（200 reps）；U1 1000 reps 待补 |
| `docs/private/` 设计文档入库 | 仓库策略（gitignored） | E3 证据降级；DESIGN §19.4 登记 |
| 4 处 PROJECT_STATUS 历史链接 | 本批前已失效 | 不在本批范围；单独登记 |

---

## §10 验收汇总模板（RULE-2：逐项核对，禁止推算）

| 分项 | 通过项 | 失败项 | 阻塞项 | 证据行号 |
|------|-------|-------|-------|---------|
| E 任务（9） | 9（E0-E8） | 0 | 0 | §2 |
| GR-1（10） | 10（另 T7b 烟测 1） | 0 | 0 | §3.1 |
| GR-2（5） | 5 | 0 | 0 | §3.2 |
| GR-3（5） | 5 | 0 | 0 | §3.3 |
| GR-4（10） | 10 | 0 | 0 | §3.4 |
| hook + 补充（21） | 21（T31-T50 + T48b） | 0 | 0 | §3.5 |
| 兼容性（7） | 7 | 0 | 0 | §4 |
| 性能（8） | 8 | 0（原 5 项超预算 P2-1 由性能包 O1-O5 关闭） | 0 | §5 |
| 数据口径（7） | 7 | 0 | 0 | §6 |
| 文档一致性（7） | 7 | 0 | 0 | §7 |

> 汇总数**只能**由逐行状态计数得出；每行必须有证据引用。空表在步骤 9 完成后填写。

---

## §11 下一步

1. 步骤 8 已完成：[CONSISTENCY_REVIEW v1.0](CONSISTENCY_REVIEW_V3.6.0_GOVERNANCE_BASE.md)（PASS_WITH_FIXES，P1=0）；
2. 步骤 9：按 §2 E1 → E2 ∥ E3 → E4 → E5 → E6 → E7 实施，红→绿两读数入档（E1-E7 已完成；E7 dry-run 正确拦截 mv 5 日缺口）；
3. 步骤 10：按 §8 取证矩阵执行 ADD 四阶段审计。
