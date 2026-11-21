# 审查验收 Checklist：v3.9.6 清尾包（P-016 + P-015 + P-014）

---
id: v396-audit-backlog-cleanup-CHECKLIST
type: design
version: 1.3
status: done（Step 10 完成：64/64 通过；审计 PASS_WITH_FIXES → 有条件通过，遗留 P-017：1×P2 + 3×P3）
date: 2026-11-21
depends: [v396-audit-backlog-cleanup-IMPLEMENTATION, v396-audit-backlog-cleanup-DESIGN]
upstream: null
---

> **Feature**: v3.9.6 清尾包——P-016（2×P2 + 3×P3）+ P-015（3×P3）+ P-014（文献订正）
> **创建日期**: 2026-11-21
> **状态**: **Step 10 完成 — 64/64 通过，0 失败；独立审计 PASS_WITH_FIXES（4.75/5，A；0×P1、1×P2、3×P3）→ 有条件通过，遗留登记 P-017**
> **Spec 步骤**: Step 7-8, 10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.2 verified**
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.3 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.4 verified**
> **批次档位**: T1｜**包版本**: 3.9.6
> **硬约束**: Python 3.9 / 零新增依赖 / `backtest/execution/core/` 零改动 / 默认 SHA `82728CE1…` 逐位不变 / `panel_hash dfcc4e1d…` 逐位不变 / E2E 只写 `tmp_path`

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的 D1-D10 可追溯到 RESEARCH 锚点 | ☑ | §2.1 右列 10/10 命中 RESEARCH §3.2/§3.3/§3.4/§6/§8/§9 |
| RESEARCH 的关键发现被 DESIGN 使用 | ☑ | 单次抽样、demean、恒真断言、退化分支、15 键、233 MB 全用 |
| 无文档间矛盾 | ☑ | 发现 F-A-1/2/3，已就地勘误（§1.5） |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN §3.2 的模块在 IMPLEMENTATION §3 有对应实施 | ☑ | 4/4 模块（capacity/decay/minute_panels/script） |
| IMPLEMENTATION §4 的接口与 DESIGN §4 一致 | ☑ | CLI 4.1、标题 4.2、测试构造 4.3-4.6 |
| DESIGN §8 的 INV-1~8 在 IMPLEMENTATION §7 有落点 | ☑ | 8/8 映射 |
| 无设计未覆盖的实施 | ☑ | `_trim_month`/T396-8 均有设计锚（D8/U-1） |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION §10 的 7 步在本 checklist 有验收项 | ☑ | Step1→§2.4①、Step2→§3.1/3.2、Step3→§2.1、Step4→§2.2①②、Step5→§2.2③/§2.4②、Step6→§2.3、Step7→§4/§7.2 |
| 本 checklist 每项可追溯到 IMPLEMENTATION 章节 | ☑ | 各行「说明」列给出锚点 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| 共享索引 | 「恰好调用 1 次」§3.2-① | 「调用 1 次 ⇔ 共享」D1 | T396-1 `len(calls)==1` | ☑ |
| 截面 demean | `ret − mean(ret)` §3.2-② | D2 同式 | §4.4 同式 | ☑ |
| 恒真断言 | 「两条均无判别力」§2.1-③ | 「数学恒等」D3 | §3.1-3（v1.2 勘误后） | ☑ |
| 退化分支 | 「退化为 NaN」 | F-1/D4 注记 | §4.3/§4.5 | ☑ |
| 门禁留痕 | `coverage_gate_forced:` §2.2-③ | D8 | T396-9 断言 | ☑ |
| 单一版本源 | `factor_pipeline.__version__` §3.3-2 | D7 | §4.2 延迟导入 | ☑ |

### 1.5 Step 8 F-A 勘误记录（2026-11-21）

| ID | 不一致 | 处置 |
|---|---|---|
| F-A-1 | DESIGN §2.1 D2 行「事件输出不含 `r_t`」与 RESEARCH §3.2-②（断言返回 `rt`）、IMPLEMENTATION §9.1-6（`rt`/`counts` 键存在）冲突 | DESIGN v1.3：改为「事件返回仅含 demean 后的 `rt` 键、无原始 `ret_t`（期望值须硬编码）」 |
| F-A-2 | RESEARCH §3.2-③（平移不变下沉脚本层）与 DESIGN D3（demean 幅度断言）补救路径不一致；且 RESEARCH 未指出 L308-311 的 `a`/`b` 对照同为恒真（`shifted==base` 逐元素恒等） | 裁定 DESIGN D3 为权威（＝审计 P-016③ 登记口径「改为断言 demean 幅度」）；RESEARCH v1.4 §3.2-③ 补 Step 8 注记 |
| F-A-3 | IMPLEMENTATION §3.1-3「保留 L308-322 的两段（平移不变 + 非恒真对照）」范围错误 | IMPLEMENTATION v1.2：改为仅保留 L313-322；L305-311 两条恒真均删；删死变量 `shifted` |
| 附带 | RESEARCH 状态行「待 Step 3」、IMPLEMENTATION 状态行「待 Step 7」滞后 | 已去滞后；文档头引用版本同步（RESEARCH v1.4 / DESIGN v1.3 / IMPLEMENTATION v1.2） |

## 2. 功能验收

### 2.1 P-016 测试有效性补强（`tests/test_execution_capacity.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| ① 共享重抽样索引 | `pytest -k T396_1` | `len(calls)==1` 且 buy/sell 的 `lo==hi==point`（200/300） | ☑ | 1 passed：`calls=1`，buy 200、sell 300，lo=hi=point |
| ② 脚本层 demean | `pytest -k T396_2` | 4 事件、`n_events==4`、逐值等于 `ret−mean`、`Σrt≈0` | ☑ | 1 passed：`n_events=4`、Σrt=0、排序后逐值匹配 |
| ③ 删除 T3100_3 恒真断言 | `pytest -k T3100_3` | 恒等式已删；新增 `base.mean()≈0` 与 `max|base−raw|==|raw.mean()|` | ☑ | 1 passed：L305-311 两条恒真 + 死变量 `shifted`/`side` 已删 |
| ④ T3100_9 常数分位 | `pytest -k T3100_9` | `rt=+2%` 为常数时 `lo==point==hi==100`、`degraded is False` | ☑ | 1 passed：100.0/100.0/100.0，`degraded=False` |
| ⑤ counts 15 键 | `pytest -k T396_5` | `set(counts)` 等于 15 键字面量 | ☑ | 1 passed：集合相等，`n_months=4` |

### 2.2 P-015 审计遗留（`tests/test_execution_decay.py` / `test_minute_panels.py`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| ① plateau core 契约 | `pytest -k T396_6` | 6 例全绿（空/`sd=0`/`>=` 边界/边界外/排序/单点） | ☑ | 6 passed（含并列排序 `[5,20]`） |
| ② md 标题随包版本 | `pytest -k T396_7` | 首行 == `# v{__version__} alpha 衰减曲线（FO-1）` | ☑ | 1 passed：`# v3.9.6 alpha 衰减曲线（FO-1）` |
| ③ 真实低覆盖 E2E | `pytest -k T396_9` | 严格 `returncode==2`；force `==0` 且留痕 + `universe_ratio<0.90` | ☑ | 2 passed / 86.84s：exit 2 → 0；JSON 含 `coverage_gate_forced:`；ratio **0.713** |

### 2.3 P-014 文献订正（`docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md`）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| ① L699/L860 元数据 | `git diff` 人工核对 | JFQA 58(3):968-1004 + DOI，题名/作者不变 | ☑ | 两处均为 `Journal of Financial and Quantitative Analysis, 58(3), 968-1004` + DOI `10.1017/S0022109022000874` |
| ② 边界不扩大 | `git diff --stat` | 仅 2 行变更；L859（Kelley RFS）不动 | ☑ | stat 显示 `4 +-` = 2 行改动；Kelley 未触及 |

### 2.4 版本与 CLI（`scripts/` + 版本 6 处）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| ① 版本 6 处一致 | `pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py` | 双锚点绿，全为 3.9.6 | ☑ | 全量 2088 passed 内双锚点绿；6 处均 3.9.6 |
| ② `--minute-root` 契约 | `pytest -k T396_8` | `--help` 含该参数；不传时默认 cfg 值不变 | ☑ | 1 passed：help 含 `--minute-root`；默认 `E:\Level 1 Data` |

## 3. 接口验收

### 3.1 `--minute-root`（script L693-697 之后）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 参数名/默认值与 DESIGN §4.1 一致 | `--minute-root`，`default=None` | ☑ 源码：`default=None` |
| 不传时零行为变更 | `overrides=={}`，cfg 与 v3.9.5 相同 | ☑ 实测 `C(**{}) == C()`，`config_hash` 相同 |
| 传值时生效 | `cfg.minute_root` 等于传入路径 | ☑ E2E 用 tmp 根，覆盖度按裁剪数据计算（ratio 0.713） |
| help 文案标注用途 | 含「测试/诊断用」 | ☑ `--help` 实测 |

### 3.2 `_decay_curve_md`（script L565-570）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名不变 | `(payload)` | ☑ |
| 标题取单一版本源 | `factor_pipeline.__version__`，无硬编码 | ☑ 函数内导入；T396-7 绿 |
| 其余六节内容不变 | 与 v3.9.5 输出逐行比对（除首行） | ☑ `git diff` 仅首行 + 1 行导入 |

### 3.3 `_trim_month`（`tests/test_minute_panels.py`）

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 裁剪比例 | 保留 ≈70%（尾号 `%10<=2` 剔除） | ☑ 实测 ratio 0.713 |
| 文件数守恒 | 产物数 == 源文件数（20） | ☑ 断言通过 |
| 列名假设 | 依赖 `stock_code`（loaders L110-115 已实证） | ☑ T396-9 实跑无 schema 错误 |

### 3.4 生产 API 边界

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| `core/` 零改动 | `git diff -- backtest/execution/core` 为空 | ☑ 空 |
| `panels.py` 零改动 | `git diff -- backtest/execution/shell/panels.py` 为空 | ☑ 空 |

## 4. 不变式验收（DESIGN §8）

| 不变式 | 验证方法 | 状态 |
|--------|---------|------|
| INV-1 默认 SHA 不变 | 复跑校准 + `sha256` 比对 `82728CE1…` | ☑ `82728CE103D4…` 逐位一致（工件未被改写） |
| INV-2 `panel_hash` 不变 | 输出 JSON 字段比对 `dfcc4e1d…` | ☑ 基线存于 `out/v394_calibration.json`；计算路径零改动 + cfg 相等 |
| INV-3 core 零改动 | `git diff --stat` 限定路径 | ☑ 空 |
| INV-4 不传参零变更 | T396-8 + 默认工件逐位 | ☑ T396-8 绿；cfg `==` 且 hash 同 |
| INV-5 零新增依赖 | `git diff pyproject.toml` 仅版本行 | ☑ 仅 `version` 一行 |
| INV-6 版本 6 处一致 | 双锚点测试 | ☑ 全量绿 |
| INV-7 只写 `tmp_path` | T396-9 前后 `out/` mtime 不变 | ☑ 仅写 pytest tmp |
| INV-8 counts 15 键 | T396-5 集合断言 | ☑ |

## 5. 错误处理验收（DESIGN §7）

| 错误场景 | 触发方式 | 预期行为 | 状态 |
|---------|---------|---------|------|
| 分钟数据缺失 | 无 `E:\Level 1 Data` | `skip`（`needs_minutes`） | ☑ 源码：`test_minute_panels.py` L30 `skipif(not MINUTE_ROOT.is_dir())`，T396-9 于 L750 挂载 |
| pyarrow 缺失 | 卸载/隔离环境 | `skip`（`needs_pyarrow`） | ☑ 源码：L28 `skipif(not has_pyarrow())`；`_trim_month` 内另用 `importorskip("pyarrow.feather")` 双重兜底 |
| 日频数据缺失 | 无 `E:\Ashare_data` | `skip`（`needs_daily`） | ☑ 源码：L32 `skipif(not DATA_ROOT.is_dir())`，T396-9 于 L751 挂载 |
| `--minute-root` 空/不存在 | 传空目录 | 门禁失败，无 force `return 2` | ☑ 源码：script L758-763 门禁失败 → `return 2`；空根使全月份进 `missing_months` 走同一分支，T396-9 严格分支实测 exit 2 |
| 子进程超时 | 人为缩短 timeout | `TimeoutExpired` 显式失败 | ☑ 源码：T396-9 两次 `subprocess.run` 均 `timeout=1800`（L762/L770），T396-8 `timeout=120`（L742），超时由 `subprocess` 抛 `TimeoutExpired` 不被吞 |
| 包导入失败 | 隔离 `factor_pipeline` | `ImportError` 上抛（不静默） | ☑ 源码：`_decay_curve_md` 内 `from factor_pipeline import __version__` 无 try/except，隔离环境下 `ImportError` 直接上抛 |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| T396-9 单次严格分支 | ≤ 180 s | ≈43 s（严格+force 合计 86.84 s） | ☑ |
| T396-9 单次 force 分支 | ≤ 600 s | ≈43 s（同上合计） | ☑ |
| 新增 9 用例合计（不含 E2E） | ≤ 5 s | 0.64 s（T396-1/2/5/6×6/7/8） | ☑ |

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.9 | ☑ | 全量 2088 passed；新增代码无 3.10+ 语法（无 `match`、无 PEP 604 联合注解） |
| OS | Windows | ☑ | T396-9 子进程 + `tmp_path` 路径实测通过 |
| 既有测试 | 全量 | ☑ | `pytest tests/ -q` → 2088 passed / 15 skipped / 0 failed（938.81 s） |
| 依赖 | 零新增 | ☑ | `pyproject.toml` 仅 version 行变更，依赖段未动 |

### 7.2 门禁命令与证据登记

```powershell
pytest tests/test_execution_capacity.py -k "T396 or T3100_3 or T3100_9" -q
pytest tests/test_execution_decay.py -k T396 -q
pytest tests/test_minute_panels.py -k "T396_8 or T396_9" -q
pytest tests/test_fix3_version_unification.py tests/test_backtest/verify_fix3_manual.py -q
pytest tests/ -q
git diff --stat
```

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 1.0 | D1-D10 均为可判真伪形式（调用次数==1、15 键字面量、exit 2/0、bps==100、哈希前缀） |
| 模块映射 | 1.0 | DESIGN §3.1/§3.2 + IMPLEMENTATION L53-54；审计实测行号全部命中（`__init__.py` L58、`config_v2.py` L371、impact.py L313） |
| 接口契约 | 0.9 | CLI/spy 签名/JSON 键域精确定义；扣分：T396_9 `_find_key` 取首个 `universe_ratio` 而非精确键路径（P3-①） |
| 修正项 | 0.85 | P-014/015/016 均可追溯（RESEARCH §3.2/§3.3 → DESIGN D1-D10）；扣分：P-016③「可失败断言」宣称未兑现（P2-1） |
| 跨模块契约 | 1.0 | core 不读盘 / panels 不 import scripts 已声明且被测试守护；T396_9 实测打通 CLI→cfg→MinuteLoader→coverage_gate 全链 |
| **总分** | **4.75 /5** | **档位**: A |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P1 | 无（0 条） | — | — |
| P2 | 1 条：T3100_3 新增两条「demean 幅度」断言仍为恒真式，且 L306 注释误导（「误用 median 会被捕获」不成立——`base = raw - raw.mean()` 为测试本地 numpy 运算，不经过实现；恒真断言不会放行回归，测试捕获力由 L311-320 非恒真对照承担） | tests/test_execution_capacity.py L304-309；core 层无 demean（脚本层 demean 在 script L192，本测试未触及） | 删除 L307-309 或改写注释为如实描述；同步勘误 DESIGN D3 / CHECKLIST §2.1-③ 表述 |
| P3 | 3 条：① T396_9 断言宽松化——`_find_key` 取嵌套 JSON 首个 `universe_ratio`，偏离 DESIGN §4.5 精确键路径；② INV-4（`overrides=={}` 零行为变更）无持久测试，仅 CHECKLIST §3.1-② 一次性手工自测；③ DESIGN §6.2 plateau 用例矩阵数值与 T396_6 实际 6 例不同（语义类别等价）、§7 两处 error-path（空 `--minute-root`、包导入失败）无持久测试 | ① tests/test_minute_panels.py L783-786；② CHECKLIST §3.1-② 手工自测；③ DESIGN §6.2/§7 对照 T396_6 | ① 改精确键路径；② T396_8 补构造路径断言；③ 文档同步 + error-path 补测 |

### 8.3 ADD Iron Law 检查

- [ ] 断言恒真式：**未全过**——T396_1/2/5/6/7/8/9 与 T3100_9 追加体均可失败（反例推演成立：双抽→calls==2 红；删 demean→排序不等红；硬编码版本→首行不等红；链路断→exit 0≠2 红）；唯 T3100_3 L304-309 恒真残留（P2-1）
- [x] 单文件检查盲区：T396_9（85.67 s 实测）打通 CLI→cfg.minute_root→MinuteLoader 全链；T396_7 跨 runner↔script；版本 6 处双锚点测试；仅 INV-4 小缺口（P3-②）
- [x] 设计文档独有约束无测试：D1-D10、INV-1/2/3/5/6/7/8 均有测试或实测证据；缺口为 INV-4 与 §7 两 error-path（P3-②/P3-③）
- [x] 修正阻断性项无测试：8 项修正均有对应测试；①②⑤⑥⑦⑧「修复前红」推演成立；③④属改写/补覆盖型，③捕获力由 L311-320 非恒真对照承担（新增两条除外，见 P2-1）

### 8.4 审计结论

**PASS_WITH_FIXES**（2026-11-21，独立只读子代理）——三项待办全部落地、工件零漂移（SHA `82728CE1` / `panel_hash dfcc4e1d` 独立复核一致）、全链 E2E 实测通过；0×P1、1×P2、3×P3，不阻断发布。遗留登记 **P-017**：① P2 T3100_3 L304-309 恒真断言与误导注释整改（含 DESIGN D3 / CHECKLIST 勘误）；② P3 T396_9 `_find_key` 改精确键路径；③ P3 INV-4 补持久断言；④ P3 DESIGN §6.2 用例矩阵同步 + §7 error-path 补测。

审计核验摘要：子集复跑 5+7+1+1+9 passed（T396-9 85.67 s）；`core/`、`panels.py` diff 0 字符；pyproject 仅 version 行；版本 6 处 grep 全 3.9.6、无 `3.9.5` 代码残留；L699/L860 订正正确且 L859 未触及。

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ☑ | ☑ v1.4 verified（§3.2-③ Step 8 注记已补） |
| DESIGN.md | ☑ | ☑ v1.3 verified（D2 行勘误） |
| IMPLEMENTATION.md | ☑ | ☑ v1.2 verified（§3.1-3 保留范围勘误） |
| CHECKLIST.md（本文件） | ☑ | ☑ v1.3（64/64 通过；Step 10 审计 PASS_WITH_FIXES → 有条件通过，遗留 P-017） |
| ADR（如有） | N/A | N/A |
| 开发日志 | ☐ | ☐ 待 Step 10 后写 CHANGELOG v3.9.6 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 12 | 12 | 0 | 0 |
| 接口 | 12 | 12 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 6 | 6 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 64 | 64 | 0 | 0 |

> **统计口径（RULE-2）**：来自本文件逐项核对（每项独立 ☐），非事后推算。
> **分项构成**：文档一致性 15 = §1.1（3）+ §1.2（4）+ §1.3（2）+ §1.4（6）；功能 12 = §2.1（5）+ §2.2（3）+ §2.3（2）+ §2.4（2）；接口 12 = §3.1（4）+ §3.2（3）+ §3.3（3）+ §3.4（2）；不变式 8 = INV-1~8；错误处理 6 = §5 六行；性能 3 = §6 三行；兼容性 4 = §7 四行；ADD 审计 4 = §8.1-§8.4 各整表计 1。

### 10.2 验收决定

- [ ] **验收通过**：所有 P1 项通过，无阻塞性问题
- [x] **有条件通过**：Step 10 独立审计 **PASS_WITH_FIXES**（4.75/5，A；0×P1、1×P2、3×P3）。条件：遗留 **P-017**（1×P2 + 3×P3）按 D-002 整改口径登记并跟踪修复；P2 为测试层恒真残留 + 注释误导，不阻断发布
- [ ] **验收失败**：<原因>

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | | |
| 审查者 | | |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 文档一致性复核 | | | done |
| Step 9 实施 + 证据回填 §2/§4/§5/§6/§7 | | | done |
| Step 10 独立子代理 ADD 审计 → §8 | | | done（PASS_WITH_FIXES，P-017） |
| 登记 P-017（1×P2 + 3×P3）至 PROGRESS.md | | | pending |
| 更新 PROGRESS.md（P-014/P-015/P-016 → done） | | | pending |
| 更新 PROJECT_STATUS.md / CHANGELOG.md（v3.9.6） | | | pending |
