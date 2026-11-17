# CONSISTENCY REVIEW v3.6.0 治理底座 — 四文档一致性

> **版本**: v1.0 (2026-11-17) — 步骤 8 产出
> **范围**: RESEARCH v1.1 ↔ DESIGN v1.2 ↔ EXECUTION v1.0 ↔ CHECKLIST v1.0
> **性质**: `自查（单视角，同基座）`；RULE-5 异构审查未满足
> **机械读数**: 2026-11-17 本机执行（脚本见 §6）

---

## §1 结论摘要

| 项 | 结果 |
|----|------|
| 结论 | **PASS_WITH_FIXES** |
| P1（阻断） | 0 |
| P2（应修） | 2（ADR-050~054 未落档；PROJECT_STATUS 4 处历史断链） |
| P3（提示） | 1（编号零填充不一致，已修） |
| 可进入步骤 9 | **是**（P2 均不阻断测试先行） |

---

## §2 四文档版本与工件状态

| 文档 | 路径 | 版本 | 入库 | 状态 |
|------|------|------|------|------|
| 调研 | `docs/research/RESEARCH_GOVERNANCE_BASE.md` | v1.1 | ✅ | 定稿 |
| 设计 | `docs/private/DESIGN_GOVERNANCE_BASE.md` | v1.2 | ❌ gitignored | 定稿（证据降级已登记） |
| 实施 | `docs/EXECUTION_V3.6.0_GOVERNANCE_BASE.md` | v1.0 | ✅ | 定稿（§9 已复核） |
| 清单 | `docs/audit/CHECKLIST_V3.6.0_GOVERNANCE_BASE.md` | v1.0 | ✅ | 定稿（待执行） |

---

## §3 三对文档对齐

### 3.1 RESEARCH → DESIGN

| 检查 | 读数 | 状态 |
|------|------|------|
| 设计引用调研结论均有 § 锚点 | DESIGN §17 映射表 9/9（D1-D12 → 调研 §2/§3/§4/§5） | 通过 |
| FALSIFIED 断言已改写 | 调研 §8 F1/F2/F3 + §9.1(a) | 通过 |
| 阻断性断言双源 | 调研 §9.1(c)：Hansen/DSR/PBO/RW 均 T1+T1/T2 | 通过 |
| 假设转 [待定] | 调研 §9.1(d) 三项 | 通过 |
| 设计未引入未经调研的外部事实 | 抽查 D4（DuckDB 写入）、D6（max_lag）、D11（Stata）→ 均有调研锚点 | 通过 |

### 3.2 DESIGN → EXECUTION

| 检查 | 读数 | 状态 |
|------|------|------|
| §10.1 公共符号全部出现 | 32/32（机械比对） | 通过 |
| §12 测试 T1-T32 全部映射 | 32/32（机械比对） | 通过 |
| §13 实施顺序对应 E0-E8 | E1→E2∥E3→E4→E5→E6→E7→E8 | 通过 |
| §14 风险 R1-R12 承接 | EXECUTION §8.2 R1-R12 + R13-R15 | 通过 |
| §18 修正 F-A~F-H/B* 有落点 | F-A→T35、F-D→T39、F-E→T40、F-F→T41、F-G→E5、F-H→T44、B5→T43、B6→T34、B7→T46、B12→T36、B13→T37、B16→T38、B29→T42 | 通过 |
| 接口签名可实现 | EXECUTION §9.2 逐项 | 通过 |

### 3.3 EXECUTION → CHECKLIST

| 检查 | 读数 | 状态 |
|------|------|------|
| E0-E8 均有验收项 | 9/9（CHECKLIST §2） | 通过 |
| T1-T46 均有 DoD | 46/46（CHECKLIST §3） | 通过 |
| 性能预算一致 | EXECUTION §6 8 项 = CHECKLIST §5 8 项 | 通过 |
| 数据口径一致 | EXECUTION §2.2/§6 = CHECKLIST §6 7 项 | 通过 |
| 每项有 DoR/DoD | CHECKLIST §1 定义 + §2-§7 逐行 | 通过 |

---

## §4 机械读数（E1）

| 检查 | 命令/方法 | 读数 |
|------|----------|------|
| 内部链接可解析 | 正则抽取 + `os.path.exists` | EXECUTION 4/4、RESEARCH 5/5、DESIGN 9/9、CHECKLIST 2/2；PROJECT_STATUS 4 处历史断链（非本批） |
| 代码围栏配对 | 统计 ``` 行数 | 5 文档均偶数 |
| 表格列数一致 | 去行内代码后计 `\|` | 本批 5 文档 0 失配；PROJECT_STATUS L79 1 处历史失配（非本批） |
| 公共符号覆盖 | DESIGN §10.1 → EXECUTION | 32/32 |
| 测试项覆盖 | DESIGN §12 T-id → EXECUTION | 32/32 |
| 版本锚点 | grep 5 处 | 均 `3.5.3`（当前基线；E8 改 3.6.0） |

---

## §5 派生需求登记（Step 8 硬约束）

> 派生需求 = 未在 DESIGN 显式声明、在实施文档中自行产生的设计决策；无上游追溯链，须单独验收。

| # | 派生需求 | 来源 | 验收 |
|---|---------|------|------|
| DR-1 | `scripts/spec_runner_adapter.py`（流程工具，非治理功能） | 本批按 SPEC_PROCESS + Spec_Runner 接入 | `probe` exit 0 + 事件流存在 |
| DR-2 | 异常基类改为**模块内局部定义**（局部 `Exception` 子类） | DESIGN §10.3 与 D1 冲突 | T33 模块隔离 + 各模块异常测试 |
| DR-3 | `ContractReport.calendar_source` 字段（`injected`/`bdate_fallback`） | DESIGN §5.4 要求披露，但数据模型未列 | T12/T15 + 报告字段断言 |
| DR-4 | `ContractReport.known_gaps` 取结构化 `KnownGap`（覆盖 §5.1 字符串类型） | DESIGN §5.7.4 升级 | T12 + known_gaps 序列化 |
| DR-5 | `FieldSpec.expected_missing_tail` 参数 | DESIGN §5.2 B13 注释 | T37 |
| DR-6 | `GovernanceStore(lock_path=...)` | DESIGN R4 要求，但接口未列 | T44 |
| DR-7 | `GoldenMaster.capture(reason=..., reviewer=...)` | DESIGN §6.3 要求，但签名未列 | T20 |
| DR-8 | `DataSnapshot.calendar_hash` 默认 `None`（dataclass 顺序修正） | DESIGN §5.1 字段顺序非法 | T15/T46 |
| DR-9 | `evidence_uri` 轻/重证据分层（≤1MB 复制入 `evidence/`） | DESIGN §4.1 B32 已有描述，实施需落地 | E1 记录写入路径断言 |
| DR-10 | `compute_payload_hash` 在 `timestamp` 补全后计算 | EXECUTION §9.6 F3 | T7/T8 |
| DR-11 | `FieldSpec.column`（`list_date_df.pkl` 取 `list_date` 列） | 默认字段表要求 `list_date_df.pkl['list_date']`，原签名无列选择器 | T13（list_date 传入）/ E2 默认字段冒烟 |
| DR-12 | `ContractCache` key 增加 `sample_end + calendar_hash` | `coverage_last`/`last_full_date` 依赖样本末与日历；原 key 仅文件元数据会误命中 | T15（同样本末）+ 换 sample_end 的负例（后续补） |
| DR-13 | 缓存命中路径跳过跨字段 `adj_alignment`/`adj_monotonic` | 命中不保留 frame；`FieldSnapshot` 无 `index_digest` | 已知限制；T41/E3 评估是否补 |
| DR-14 | `GoldenManifest.reason/reviewer` 可选字段；`factor_ids/periods/n_stocks` 由 outputs 计算 | DESIGN §6.3 要求 force 审计，但 manifest 字段表未列 reason/reviewer | T20 |
| DR-15 | Romano-Wolf 快速核（`_romano_wolf_fast`，k=1 时 `searchsorted` 向量化；k>1 回退逐次实现）仅位于台账模块，不下沉 `multiple_testing.py` | D-2 决策：原模块无 RW 实现，下沉会扩大改动面 | T27（≤1e-15）+ 原路径 58 passed |
| DR-16 | `GovernanceStore.get/query_records/latest` 返回类型扩展为 `Union[GovernanceRecord, Dict]`；更新 schema 原样 dict（DESIGN §4.3 B6） | EXECUTION §2.1 签名仅写 `Optional[GovernanceRecord]`，未覆盖未来 schema 分支 | T34 |
| DR-17 | T32 事件字段数按 EXECUTION §2.6 为 **9**（event/factor_id/stage/arm/pipeline_version/config_hash/routing/sample_window/env_fingerprint） | CHECKLIST 原文写"8 个字段"，与 §2.6 列举冲突 | T32（字段集合断言） |
| DR-18 | E5 对拍脚本复用台账私有 `_holm_adjusted`（无公共 Holm 入口） | DESIGN §8.2 仅写"台账"，EXECUTION §10.1 未列公共 Holm 函数 | E5 `--case all`（holm diff 1.110e-16） |
| DR-19 | freshness 的 `expected_missing_tail` 采用**lag 扣减**（`lag=max(0, raw_lag-tail)`），`last_full_date`/`effective_end` 保持原始快照值，`raw_lag` 写入 `details` | F4 原表述"`last_full_date` 计算前剥离尾部"会丢失原始满覆盖日；实测等价且更可追溯 | T37（`lag==0`、`raw_lag==1`） |
| DR-20 | golden 基线 `tests/golden/govbase_v1_synth` 在 E6 hook 实施后采集（`seed=20261117`），作为**后续**回归锁；不回溯证明 E6 改动行为中性 | E3 fixture 依赖 E6 收尾；"hook 默认 None"的行为中性由 `test_pipelines_v2` 13 passed + 代码审查承担 | T31（每次运行的 no-hook golden ≤1e-10） |
| DR-21 | `ancestors()` 返回 `List[AncestorEntry]`（`record`/`broken_link`/`reason`），而非 `List[GovernanceRecord]` | DESIGN §4.4/F-F 只要求"断链标注 broken_link"，未定返回形态；决策锚点：git `rev-list --missing=print`（缺失对象以 `?` 标记不中断）、GraphQL 部分成功（data+errors） | T41（红→绿；断链 `reason=missing`、跨 schema `reason=schema_mismatch`） |
| DR-22 | E7 组合层 `market_fields()` 排除 `list_date`/`calendar`/`barra`，并以参数注入 + pkl 字符串日期归一化 | 真实目录字段位于 `market_data/`；`list_date` 为代码索引、`all_dates` 为 list、`barra` 为 dict-Series，均非日期面板；核心 `default_fields()` 保持不动（D-5） | E7 dry-run（BLOCK mv lag=5；`test_contract_gate.py` 2 passed） |
| DR-23 | `_file_lock` 跨平台等待语义不一致（Windows `LK_LOCK` 约 10 s 后抛 `OSError`；POSIX `flock` 阻塞至获得），仅影响 JSONL fallback 极端跨进程竞争 | 异构复审 F1（2026-11-18）；进程内另有线程锁，默认单写者路径无影响 | EXECUTION §2.1 要点 5 + §9.8；P3 并发 40 行 0 异常 |
| DR-24 | 注入 `bootstrap_indices` 时 `individual_p_values` 为联合重抽样边际 p，与 `None` 路径逐列独立 block bootstrap 口径不同 | 异构复审 F2；同一 (B,T) 索引矩阵供台账复现，主 `rc_p_value`/SPA 口径不变 | EXECUTION §2.5 + §9.8；P5 两次注入 rc_p 确定 |

> 以上 24 项均已在 EXECUTION 正文或 §9.6/§9.8 登记；步骤 9 实施时逐项验收。

---

## §6 本 review 的复现方式

```bash
# 公共符号 / 测试项覆盖（E1）
python - <<'PY'
import io, re
...
PY
```

脚本口径（与执行时一致）：

1. 抽取 `DESIGN §10.1` 表内反引号标识符 → 在 EXECUTION 全文做子串匹配；
2. 抽取 `DESIGN §12` 的 `T\d+` → 在 EXECUTION 以非数字边界匹配；
3. 抽取四文档 Markdown 链接 → 相对路径 `os.path.exists`；
4. 表格列数：去除行内代码跨度后统计 `|` 数量，与表头比较。

---

## §7 双向引用与断言延续

| 检查 | 读数 | 状态 |
|------|------|------|
| RESEARCH 引用 DESIGN / ROADMAP | 调研头部引路线图；DESIGN 头部引调研 | 通过 |
| DESIGN 引用 RESEARCH / 路线图 / PROJECT_STATUS | 头部 3 条 | 通过 |
| EXECUTION 引用 DESIGN / RESEARCH / 路线图 / PROJECT_STATUS | 头部 4 条 | 通过 |
| CHECKLIST 引用 EXECUTION / RESEARCH / DESIGN | 头部 3 条（DESIGN 为路径声明） | 通过 |
| ADR-050~054 反向引用本 feature | **ADR 未落档** | **P2 未通过**（E8 补） |
| RESEARCH B 类断言状态延续 | 调研 §9 门禁表 → DESIGN §19 → EXECUTION §11 | 通过 |

---

## §8 发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| C1 | P3 | EXECUTION 用 `T01` 零填充，DESIGN 用 `T1`，机械比对误报 5 项缺失 | 已统一为非填充 `T1-T46` |
| C2 | P2 | DESIGN §5.1 `known_gaps: Tuple[str,...]` 与 §5.7.4 结构化 `KnownGap` 冲突 | EXECUTION 取 §5.7.4（DR-4）；本表登记替换 |
| C3 | P2 | DESIGN §10.3 异常继承与 D1 模块隔离冲突 | EXECUTION §3.5 局部基类（DR-2）；F1 登记 |
| C4 | P2 | DESIGN §5.1 `DataSnapshot` 字段顺序违反 dataclass 默认值规则 | EXECUTION §9.6 F7；`calendar_hash=None`（DR-8） |
| C5 | P2 | ADR-050~054 被四文档引用但 `DECISIONS.md` 尚无对应条目 | 不阻断步骤 9；E8 必须落档（否则双向引用检查失败） |
| C6 | P3 | `PROJECT_STATUS` L79 表格列数失配 + 4 处历史断链（`../EXECUTION_V3.3.0.md` 等） | 非本批引入；登记，不在本批修 |
| C7 | P3 | `F:\Spec_Runner` 为 v1.0.0 冻结存档，但路径仍存在于环境 | WORKFLOW §14.1 明示不再使用；adapter 指向 v1.11.0 |

---

## §9 下一步

- **不阻断**步骤 9：按 CHECKLIST 顺序 E1 → E2 ∥ E3 → E4 → E5 → E6；
- E8 必须完成 ADR-050~054 落档，否则本 review 的 P2 保持开放；
- 步骤 10 审计时，本 review 的机械读数按 E1 登记，判断项按 E4 登记。
