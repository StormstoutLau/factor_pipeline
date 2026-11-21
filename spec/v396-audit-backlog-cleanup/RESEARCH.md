# 调研：v3.9.6 清尾包（P-016 / P-015 / P-014）

---
id: v396-audit-backlog-cleanup-RESEARCH
type: research
version: 1.4
status: verified（Step 2 复审 PASS；v1.4 Step 8 一致性审查勘误，见修订）
date: 2026-11-21
depends: [v3100-reversal-evidence-CHECKLIST, v394-audit-coverage-fix-CHECKLIST, v393-alpha-decay-model-RESEARCH]
upstream: null
---

> **Feature**: v3.9.6「清尾包」——一次性关闭 P-016（P-003 审计遗留 2×P2 + 3×P3）、P-015（v3.9.4 审计遗留 3×P3）、P-014（Chen & Velikov 元数据订正）。
> **创建日期**: 2026-11-21
> **状态**: v1.4 verified（Step 1 调研 + U-1/U-2/U-3 裁决 + Step 2 复审 PASS；Step 8 勘误见修订）
> **修订**: v1.4（2026-11-21）Step 8 一致性审查：状态行去滞后；§3.2-③ 补 DESIGN D3 refinement 注记（幅度断言为审计 P-016③ 登记口径，平移不变不下沉）；v1.3（2026-11-21）Step 2 复审：新增 §9 幻觉抑制审查（F4 引用验证表 9 条 + 技术声明 16 项 E1 + 门禁 a-d + F1-F5）；**修正一处 FALSIFIED 估计**——E2E 月度 feather 体积实测 2020-02 = 20 文件 / 233 MB（§3.3、§5 原写 7.7 MB / 170 MB 偏低）；v1.2 U-1/U-2/U-3 裁决为 **A**；v1.1 新增 §8 社区案例；v1.0 初稿。
> **Spec 步骤**: Step 1
> **包版本**: **3.9.6**（patch；零生产逻辑变更、零工件变更）
> **硬约束**: 默认 `out/capacity_impact.json` SHA `82728CE1…`、`panel_hash dfcc4e1d…` 逐位不变；`core/decay.py` 仅允许新增测试、不得改实现；零新增依赖；Python 3.9 语法。

---

## 1. 调研背景与边界

v3.9.5（P-003）Step 10 审计结论 **PASS_WITH_FIXES**（4.60/5，A；0×P1、2×P2、6×P3），其中 3×P3 文档类已就地关闭，剩余 2×P2 + 3×P3 登记为 P-016；v3.9.4 另遗留 3×P3（P-015）；v3.9.3 调研发现仓内两处 Chen & Velikov 期刊元数据错配（P-014）。

三项共同特征：**只动测试/文档，不动生产逻辑与工件**，故合并为单批 patch，共用一次全量回归与同一组不变式锚点。

**本批职责内**：补测试、参数化标题、增加 opt-in CLI 覆盖入口、订正两条文献元数据、回填三份 CHECKLIST 的遗留行。
**本批职责外**：不改 `cross_section_reversal` / `build_reversal_events` / `plateau` 实现；不改任何成本/容量口径；不重跑 39 月校准（仅跑 E2E 小样本）。

## 2. 现状核查

### 2.1 P-016（P-003 审计遗留）

| # | 级别 | 现状与缺陷证据 |
|---|---|---|
| ① | P2 | **共享重抽样索引无独立断言**。实现只在 [impact.py L313-314](file:///f:/Coding/factor_pipeline/backtest/execution/core/impact.py#L313-L314) 抽一次 `idx`，随后 `all/buy/sell` 三组共用（L316-321）；但 [T3100_9 L350-370](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L350-L370) 只验「可复现 + 端点夹逼」。若改成 buy 用 `seed`、sell 用 `seed+1`，现有测试仍全绿 → 契约未被锁定。 |
| ② | P2 | **脚本层截面 demean 无测试**。`build_reversal_events` 用 `r.sub(r.where(ub).mean(axis=1), axis=0)`（[verify_capacity_impact.py L192](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L192)）；T3100_4~7 只断言过滤与计数，删除该行不会有测试失败。 |
| ③ | P3 | **T3100_3 前半段恒真**。[L305-311](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L305-L311)：`base` 与 `shifted` 都是「原数组 − 自身均值」，必然逐元素相等；`side=[1,-1]*30` 严格平衡，即使不 demean，常数平移对 `Σa·y` 的贡献也被平衡抵消 → 两条断言均无判别力。后半段 L313-322 的全 1 方向对照**有效**（Δ>1.0），应保留。 |
| ④ | P3 | **T3100_9 端点断言半同义反复**。`_interval` 用 `min(lo,point)/max(hi,point)` 强制夹逼，故 `lo<=point<=hi` 由构造保证；需补「已知分位」用例（如常数输入 `lo=hi=point`、单月退化前的边界）才有判别力。 |
| ⑤ | P3 | **`reversal_counts` 缺整体键集断言**。现仅逐字段断言（T3100_4~6），若实现新增/删除键而旧断言不覆盖该键，不会被发现；需 `set(counts) == {15 键字面量}`。 |

**既有可用测试基座**：`_event_panel()`（[L382-417](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L382-L417)）提供 4 只股票 × 4 个形成日、`mask` 全 True、已知 `ret_t/ret_t1` 与 `Δw`；这使「脚本层 demean 的期望值可手算」成为可能（第 m 月事件 `rt_expected = ret_t[code] − mean(ret_t.values())`）。

### 2.2 P-015（v3.9.4 审计遗留）

| # | 级别 | 现状与缺陷证据 |
|---|---|---|
| ① | P3 | **`decay.plateau` 无 core 直接契约单测**。实现见 [decay.py L92-98](file:///f:/Coding/factor_pipeline/backtest/execution/core/decay.py#L92-L98)：空 dict → `[]`；`h* = argmax`；阈值 `net[h*] − sd`；返回 `>=` 阈值且排序。现仅 T394-4（[test_execution_decay.py L266-277](file:///f:/Coding/factor_pipeline/tests/test_execution_decay.py#L266-L277)）经 `payload["plateau"]` 间接覆盖，且断言 `set(plateau) ⊆ {5,10,20}` 与「含 h*」均无法区分 `max−sd` 的边界语义。 |
| ② | P3 | **衰减曲线 md 标题硬编码旧版本**。[verify_capacity_impact.py L570](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L570) 写死 `'# v3.9.3 alpha 衰减曲线（FO-1）'`；v3.9.4/v3.9.5 生成的 md 标题仍显示 v3.9.3。 |
| ③ | P3 | **`--force-coverage` 无真实低覆盖 E2E**。门禁 [panels.py L712-734](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L712-L734)：月中位 <0.95、最差 <0.90、深主板 ≤0 即失败；CLI 失败默认 `return 2`，`--force-coverage` 则追加 `coverage_gate_forced: …` 并继续（[L751-759](file:///f:/Coding/factor_pipeline/scripts/verify_capacity_impact.py#L751-L759)）。现仅字符串契约单测（[test_execution_capacity.py L247-254](file:///f:/Coding/factor_pipeline/tests/test_execution_capacity.py#L247-L254)），无「真跑 → exit 2 → 放行留痕」链路证据。 |

### 2.3 P-014（文献元数据）

- 错配点 1：[RESEARCH_V3.8.0_EXECUTION_CAPACITY.md L699](file:///f:/Coding/factor_pipeline/docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md#L699) 写「*Zeroing In on the Expected Returns of Anomalies*（RFS 2023）」。
- 错配点 2：[同文件 L860](file:///f:/Coding/factor_pipeline/docs/research/RESEARCH_V3.8.0_EXECUTION_CAPACITY.md#L860) 参考文献第 38 条写「Review of Financial Studies (2023)」。
- **已核对正确元数据**（v393 RESEARCH L269-270 / L403 已用 Crossref DOI 解析验证）：**Chen, A. Y., & Velikov, M. (2023). *Zeroing In on the Expected Returns of Anomalies*. Journal of Financial and Quantitative Analysis, 58(3), 968-1004. DOI: 10.1017/S0022109022000874.** 本批只需改这两处，不引入新文献。

## 3. 方案与裁决

### 3.1 批形态：单批 3-in-1（patch v3.9.6）

| 选项 | 结论 |
|---|---|
| A. 三项各开 spec 批 | 开销过大（3×10 步，收益仅测试/文档） |
| **B. 合并单批（选定）** | 三项互不冲突、均零工件影响；共用一次全量回归与 SHA/`panel_hash` 锚点；CHECKLIST 逐项映射各自遗留行 |
| C. 并回 P-006（引擎批） | 会混淆「零行为变更」与「引擎行为变更」，污染回归基线，拒绝 |

### 3.2 P-016 测试设计（选定）

1. **① 共享索引**：monkeypatch `backtest.effect_size.stationary_bootstrap_indices`（impact 在函数内 `from ...effect_size import`，L269/L219，故运行期解析模块属性），包一层计数；断言普通事件样本 **恰好调用 1 次**。再加判别性用例：让 stub 返回**固定索引矩阵**（如全 0 → 只重抽第 0 月），若 buy/sell 各自重抽，其 CI 将偏离全样本点估计；断言 `buy/sell` 的 `lo/hi` 与单索引解析值一致。
2. **② 脚本层 demean**：基于 `_event_panel()`，第 m 个形成日的期望事件收益 `ret_t[code] − mean(ret_t.values())`；断言返回 `rt` 逐事件 `allclose`（1e-12）。该断言在删除 demean 行后必失败。
3. **③ 退回非恒真**：删除 L305-307 的 `allclose(base, shifted)`；把「平移不变」下沉到脚本层（与 ② 合并：对同一面板给所有股票加常数 `c`，事件 `rt` 不变），保留 L313-322 的全 1 方向对照。（**Step 8 注记**：DESIGN D3 refinement 裁定——T3100_3 本体改「demean 幅度」断言＝审计 P-016③ 登记口径；L305-311 **两条**恒真（allclose 与同输入 `a`/`b` 对照，因 `shifted==base` 逐元素恒等）均删；「平移不变下沉脚本层」不采用，生产 demean 行保护由 ②/T396-2 承担。）
4. **④ 已知分位**：新增常数 `rt1`（如全部 −0.01）用例，断言 `lo == point == hi`（无截面离散 → 重抽样无变异），并保留随机用例的 `point ∈ [lo,hi]`。
5. **⑤ 键集**：在 T3100_4 或新用例中断言 `set(ev["counts"]) == {"n_events", …15 键…}`，同时断言 `n_months == len(w.index)`。

### 3.3 P-015 设计（选定）

1. **plateau 边界表**（core 直接调用，`net={1:0.1,5:0.2,10:0.18,20:0.05}`）：
   - `sd=0` → 仅 `[5]`；
   - `sd=0.05`（阈值 0.15）→ `[5,10]`（含 `>=` 边界）；
   - `sd=1.0` → 全部 horizons；
   - `{}` → `[]`；
   - 重复最大值（`{1:0.2,5:0.2}`）→ 含全部并列项。
   - 契约边界：`net` 值为有限数、`sd >= 0`；**不**为 NaN/负 `sd` 增加防御分支（避免过度设计）。
2. **标题参数化**：`_decay_curve_md` 改从包单一版本源取版本（`backtest.execution.__version__`，与 3.9.5 五处落点同源），标题格式 `'# v%s alpha 衰减曲线（FO-1）'`；新增断言：`payload` 生成文本以 `v{__version__}` 开头。
3. **force-coverage E2E**：
   - 新增 **`--minute-root`** 覆盖参数（默认 `None` → 沿用 `CalibrationConfig.minute_root='E:\Level 1 Data'`），仅用于测试可达性，默认路径零变更。
   - 用真实数据构造低覆盖子集：取分钟窗口内一个月（`2020-01`…`2023-03`，文件为 `YYYY-MM-DD.feather`；**2020-02 实测 20 个文件共 233 MB，单文件约 12 MB**）复制到临时目录，**按代码列裁掉约 30%** 后写回 → `universe_ratio ≈ 0.7`。
   - E2E：`--calibrate --minute-root <temp> --calibration-json <temp>/x.json` → **exit 2**；加 `--force-coverage` → **exit 0** 且 JSON `evidence_warnings` 含 `coverage_gate_forced:`。
   - 需真实分钟根存在；不存在时 `pytest.mark.skipif` 跳过（与既有真实数据测试一致）。

### 3.4 P-014 订正文本（选定）

- L699：`（RFS 2023）` → `（JFQA 2023, 58(3):968-1004）`。
- L860：改为 `38. Chen, A. Y. & Velikov, M. (2023), *Zeroing In on the Expected Returns of Anomalies*, Journal of Financial and Quantitative Analysis 58(3):968-1004, doi:10.1017/S0022109022000874 — 降低再平衡频率作为净收益改进手段`。
- 同步 v393 `CHECKLIST.md L270` 与 `RESEARCH.md L300` 的「未修」标记 → **done（v3.9.6）**。

## 4. 验收基准（可测）

| # | 验收 | 判据 |
|---|---|---|
| A1 | ① 共享索引 | monkeypatch 计数 == 1；且固定索引 stub 下 buy/sell CI 与解析值一致 |
| A2 | ②/③ 脚本 demean | 事件 `rt` 与手算 `raw − 截面均值` 逐事件相等（1e-12）；删除 demean 行则失败 |
| A3 | ④ 已知分位 | 常数输入 `lo == point == hi` |
| A4 | ⑤ 键集 | `set(counts)` 恰为 15 键字面量 |
| A5 | plateau | 5 组边界全绿；`sd=0.05` 含 `>=` 边界 |
| A6 | 标题 | 生成 md 首行等于 `# v{__version__} alpha 衰减曲线（FO-1）` |
| A7 | force-coverage | 低覆盖 → exit 2；`--force-coverage` → exit 0 + `coverage_gate_forced:` |
| A8 | 元数据 | 两处文本含 `JFQA` 与 DOI，且不含 `RFS 2023` |
| A9 | 回归 | 全量 `pytest -q` 0 failed；默认 SHA `82728CE1…` / `panel_hash dfcc4e1d…` 不变 |
| A10 | 兼容 | `ast.parse(feature_version=(3,9))` 通过；`requirements*.txt` 零 diff |

## 5. 风险与边界

| 风险 | 评估 | 缓解 |
|---|---|---|
| E2E 复制一个月 feather 到临时目录 | 2020-02 实测 233 MB 磁盘；构建时长仍为估计值 [估计-Step 9 实测回填] | 仅测试内临时目录，结束清理；`skipif` 数据缺失 |
| 新增 `--minute-root` 被误用 | 低 | 帮助文案标「测试/诊断用」；默认 `None` 不改变路径；不写工件到 `out/` |
| 标题参数化改到 `__version__` 后旧工件标题变化 | 无影响 | 仅 md 首行文本；JSON schema 不变 |
| plateau 边界被过度扩展 | 中 | 只锁 5 组契约内用例，不为 NaN/负 sd 增加防御 |
| 测试改动触及 v3.9.5 断言 | 低 | 只改 T3100_3/9 与新增用例，不改已通过的 T3100_1/2/4~8/10 |

## 6. 未决项与裁决（2026-11-21 已裁）

| ID | 问题 | 选项 A / B | 裁决 | 落地位置 | 依据 |
|---|---|---|---|---|---|
| U-1 | E2E 是否入 pytest | A. 入 pytest（缺真实数据 `skipif`）／B. 仅手工验证留痕 | **A**（用户，2026-11-21） | §3.3 第 3 条；§4 A7 | §8.1 |
| U-2 | 是否允许新增 `--minute-root` | A. 允许（opt-in，默认零变更）／B. 进程内 monkeypatch 构造 cfg | **A**（用户，2026-11-21） | §3.3 第 3 条；§4 A7 | §8.2 |
| U-3 | 版本号 | A. 3.9.6（patch）／B. 并入 3.10.0 | **A**（用户，2026-11-21） | §3.1；§4 A10 | §8.3 |

裁决后**无残留未决项**。若 Step 2 复审发现新问题，另开 U-4 起编号，不回改本节历史裁决。

## 7. 参考锚点

- P-016 来源：[v3100 CHECKLIST §8.2](file:///f:/Coding/factor_pipeline/spec/v3100-reversal-evidence/CHECKLIST.md)（审计 2×P2 + 6×P3）；[PROGRESS P-016](file:///f:/Coding/factor_pipeline/docs/PROGRESS.md)
- P-015 来源：[PROGRESS P-015](file:///f:/Coding/factor_pipeline/docs/PROGRESS.md)；v3.9.4 [CHECKLIST §8.2](file:///f:/Coding/factor_pipeline/spec/v394-audit-coverage-fix/CHECKLIST.md)
- P-014 来源：[v393 RESEARCH L269-270/L300/L403](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/RESEARCH.md#L269-L270)；[v393 CHECKLIST L270](file:///f:/Coding/factor_pipeline/spec/v393-alpha-decay-model/CHECKLIST.md#L270)
- 代码锚点：`impact.py` L269/L313；`verify_capacity_impact.py` L570/L751-759；`panels.py` L712-734；`config.py` L23/L26-27；`decay.py` L92-98。

## 8. 社区案例与资料（U-1 ~ U-3 补充调研）

> **调研日期**：2026-11-21。**筛选原则**：优先官方文档/标准原文与仓内既有先例；社区与书籍材料仅作「惯例证据」，不改变 §3 的技术方案。下列链接均为本次实际访问可读的页面。

### 8.1 U-1：真实数据 E2E 是否入 pytest

| 来源 | 关键结论 | 对本批的适用性 | 局限 |
|---|---|---|---|
| pytest 官方《How to use skip and xfail…》<br>https://docs.pytest.org/en/stable/how-to/skipping.html | skip 的典型场景明确包含「依赖当前不可用的外部资源（例如数据库）」，目的正是让套件保持 green；`skipif` 可用于函数、类、模块（`pytestmark`）。 | 直接支持 **A：入 pytest + `skipif`**，即缺 `E:\Level 1 Data` 时跳过而非失败。 | 官方未规定 E2E 必须进默认套件；CI 无数据时该用例会 skip，形成覆盖盲区。 |
| pytest 官方《How to mark test functions with attributes》<br>https://docs.pytest.org/en/stable/how-to/mark.html<br>《Working with custom markers》<br>https://docs.pytest.org/en/stable/example/markers.html | 自定义标记须在配置中登记（`markers = [...]`），登记后可用 `-m "not slow"` 选择；未登记标记会告警，开启 `--strict-markers` 则直接报错。官方示例即以 `slow` 为示范标记。 | 若 E2E 时长明显，可加 `@pytest.mark.slow` 并允许快跑；**但本仓 [pyproject.toml L74-82](file:///f:/Coding/factor_pipeline/pyproject.toml#L74-L82) 当前未登记任何 markers**，需同步登记才不产生告警。 | 引入标记属测试基础设施新增，会增加一处配置改动；非必需。 |
| pytest-test-categories 标记参考<br>https://pytest-test-categories.readthedocs.io/en/latest/api-reference/markers.html | 依 Google《Software Engineering at Google》分四档：small（1 s，禁网络/文件/子进程）、medium（300 s，仅 localhost，允许子进程）、large（900 s，允许外部网络与子进程）；目标分布 ~80% / ~15% / ~2.5-5%。 | 本批 E2E（起子进程、读真实磁盘、约 30-60 s）属 **large**，不应混入 small；用 `skipif` 保证缺数据不红，符合「大测试少而精」。 | 该插件是第三方库；本批**不引入依赖**，仅借其分级口径做判断。 |
| Google《Software Engineering at Google》第 11 章（Testing Overview）<br>https://abseil.io/resources/swe-book/html/ch11.html | 缺陷发现越晚成本越高；自动化测试的核心价值之一是「支持变更」；高成本的大粒度测试应少。 | 支持「1 条 E2E + 其余 core 单测锁契约」的配比（见 §3.2 / §3.3）。 | 属工程原则，不是「必须入 pytest」的硬规范。 |
| **仓内先例（最强）** [test_minute_panels.py L28-33](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L28-L33) / [L541-551](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py#L541-L551) | 已有 `needs_pyarrow` / `needs_minutes` / `needs_daily` 三个 `skipif` 守卫；T381-20 已用 `subprocess.run(..., timeout=1800)` 跑真实 CLI 并断言 `returncode == 0`。 | 本批沿用同一模式即可，零新惯例；建议复用 `needs_minutes` 的判定与命名。 | 无。 |

**结论**：U-1 = **A**。不新增 `slow` 标记（避免 `pyproject.toml` 改动），仅用 `skipif` 延续仓内先例。

### 8.2 U-2：是否新增 `--minute-root`

| 来源 | 关键结论 | 对本批的适用性 | 局限 |
|---|---|---|---|
| Python 官方 argparse<br>https://docs.python.org/3/library/argparse.html | 可选参数支持 `default=None`；未传入时行为与新增参数前完全一致。 | 支持 **A：opt-in 覆盖**；默认 `None` → 沿用 `CalibrationConfig.minute_root`，默认路径零变更。 | argparse 本身无「测试专用参数」语义，需靠 help 文案约束用途。 |
| pytest monkeypatch 官方文档<br>https://docs.pytest.org/en/stable/how-to/monkeypatch.html | 用于在当前测试进程内安全地 set/delete 属性、字典项、环境变量或改 `sys.path`，测试结束自动回滚。 | 说明 **B（进程内 monkeypatch 构造 cfg）只在同进程生效**；本批要验的正是 `subprocess.run([sys.executable, script, ...])` 的「exit 2 → 0」，monkeypatch 不跨进程，无法替代 CLI 接缝。 | 若把 E2E 降级为函数级调用可绕开 CLI，但会失去「真实入口 + 真实退出码」证据。 |
| 测试缝（seam）工程实践：Michael Feathers《Working Effectively with Legacy Code》(2004) 第 4 章 | seam = 不修改该处代码即可改变行为的位置；把可替换点放在组合根是通行做法。 | `--minute-root` 属 pre-emptive seam：仅测试/诊断注入数据根，生产默认不变。 | 书籍经验非规范；新增参数会扩大 CLI 表面。 |
| **仓内设计意图** [config.py L23](file:///f:/Coding/factor_pipeline/backtest/execution/config.py#L23)、[panels.py L164-176](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L164-L176) | `minute_root` 已是配置字段；`MinutePanelBuilder.__init__` 已支持 `loader` 注入，并在 `minute_root` 为空时抛 `CalibrationUnavailable`。 | 说明「可替换数据源」在本模块是既有设计，CLI 暴露只是补上缺失的组合根入口，不是为测试新造例外。 | 无。 |

**结论**：U-2 = **A**。默认 `None`、help 标「测试/诊断用」、不写入任何工件。

### 8.3 U-3：3.9.6（patch）vs 并入 3.10.0

| 来源 | 关键结论 | 对本批的适用性 | 局限 |
|---|---|---|---|
| SemVer 2.0.0 官方摘要<br>https://semver.org/ | PATCH = 向下兼容的 **bug fix**；MINOR = 向下兼容地 **新增功能**。 | P-016（测试有效性）、P-015（标题版本 + `plateau` 单测 + E2E）、P-014（文献元数据错误订正，属 bug fix）→ 主体为 patch。 | **诚实披露**：新增 `--minute-root` 按字面属「新增功能」；若它被视为对外公共 API，则应走 MINOR。 |
| 项目版本惯例 [CHANGELOG.md](file:///f:/Coding/factor_pipeline/CHANGELOG.md) | v3.9.1 / v3.9.2 / v3.9.3 / v3.9.4 / v3.9.5 连续五个 patch，其中 v3.9.2 亦为口径 bug 修复。 | 一致性优先，取 **3.9.6**。 | 惯例不是规范；Step 2 复审若有异议可改判。 |

**结论**：U-3 = **A（3.9.6 patch）**。**改判触发条件**：若复审认定 `--minute-root` 构成对外 API 扩张 → 改判 B（并入 3.10.0），并同步调整 §4 A10 与版本落点。

### 8.4 对 §3 方案的影响

**无影响**。三项结论与既有设计一致，仅补证据：

- U-1 → §3.3 第 3 条已写明 `pytest.mark.skipif`；
- U-2 → §3.3 第 3 条已写明 `--minute-root` 默认 `None`；
- U-3 → §3.1 已写明 patch v3.9.6。

### 8.5 资料清单（实访 2026-11-21）

1. pytest — How to use skip and xfail to deal with tests that cannot succeed：https://docs.pytest.org/en/stable/how-to/skipping.html
2. pytest — How to mark test functions with attributes：https://docs.pytest.org/en/stable/how-to/mark.html
3. pytest — Working with custom markers：https://docs.pytest.org/en/stable/example/markers.html
4. pytest — How to monkeypatch/mock modules and environments：https://docs.pytest.org/en/stable/how-to/monkeypatch.html
5. pytest-test-categories — Markers Reference：https://pytest-test-categories.readthedocs.io/en/latest/api-reference/markers.html
6. Google — Software Engineering at Google, Ch.11 Testing Overview：https://abseil.io/resources/swe-book/html/ch11.html
7. Semantic Versioning 2.0.0：https://semver.org/
8. Python — argparse：https://docs.python.org/3/library/argparse.html
9. 仓内先例：[tests/test_minute_panels.py](file:///f:/Coding/factor_pipeline/tests/test_minute_panels.py)（L28-33 skipif、L541-551 CLI E2E）；[backtest/execution/config.py L23](file:///f:/Coding/factor_pipeline/backtest/execution/config.py#L23)；[backtest/execution/shell/panels.py L164-176](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L164-L176)；[pyproject.toml L74-82](file:///f:/Coding/factor_pipeline/pyproject.toml#L74-L82)

## 9. 幻觉抑制审查（Step 2 Review，2026-11-21，自查·单视角）

> RULE-4 声明：本文档作者与复审者为同一 agent，本节全部结论标 `自查（单视角）`；仓内锚点为 T1 文件本体 E1 读数且经双 pass 复读（Step 1 初读 + Step 2 复读），外部引用按「引用核验四步」逐条解析。用户对 Step 2 产出的确认构成第二确认点。

### 9.1 文献验证表（F4：外部引用 9 条 ≥3 ⇒ 建表）

| # | 引用 | ID | 验证方式 | 状态 | 命中或差异 |
|---|---|---|---|---|---|
| 1 | pytest skipping | docs.pytest.org/en/stable/how-to/skipping.html | WebFetch 2026-11-21 | 已验证 | 命中：skip 典型场景含「外部资源（数据库）不可用」；skipif 支持函数/类/pytestmark |
| 2 | pytest mark | docs.pytest.org/en/stable/how-to/mark.html | WebFetch 2026-11-21 | 已验证 | 命中：登记 markers / `-m` 选择 / strict-markers |
| 3 | pytest custom markers | docs.pytest.org/en/stable/example/markers.html | WebFetch 2026-11-21 | 已验证 | 命中：`slow` 示例标记；模块级 pytestmark |
| 4 | pytest monkeypatch | docs.pytest.org/en/stable/how-to/monkeypatch.html | WebFetch 2026-11-21 | 已验证 | 命中：进程内 set/delete + 测试后回滚（支撑 U-2 选项 B 不可跨进程的判断） |
| 5 | pytest-test-categories markers | pytest-test-categories.readthedocs.io/en/latest/api-reference/markers.html | WebFetch 2026-11-21 | 已验证 [单源-待二核] | 命中：small 1s / medium 300s / large 900s + 目标分布 ~80/15/2.5-5%；单源（第三方插件自身文档），仅用于 U-1 分级判断，非阻断 |
| 6 | Google SWE at Google Ch.11 | abseil.io/resources/swe-book/html/ch11.html | WebFetch 2026-11-21 | 已验证 | 命中：Testing Overview；缺陷晚发现成本高；支持变更 |
| 7 | SemVer 2.0.0 | semver.org | WebFetch 2026-11-21 | 已验证 | 命中：PATCH=向下兼容 bug fix、MINOR=向下兼容新增功能（标准本体，权威单源） |
| 8 | Python argparse | docs.python.org/3/library/argparse.html | WebFetch（Step 2 复验） | 已验证 | 命中：3.15.2 官方 API 参考；optional 参数 default 语义 |
| 9 | Chen & Velikov 2023 | DOI 10.1017/S0022109022000874 | Crossref API（Step 2 复验） | 已验证 | **命中且逐字段一致**：题名 *Zeroing In on the Expected Returns of Anomalies*；作者 Andrew Y. Chen / Mihail Velikov；CUP；short-container-title "J. Financ. Quant. Anal."；58(3):968-1004；published-print 2023-05。与 v393 RESEARCH L182/L269 既有验证一致 |

仓内引用（非外部，F2 形态 = 文件 + 行号）：`RESEARCH_V3.8.0` L699/L860、v393 RESEARCH L269-270/L300/L403、v393 CHECKLIST L270 —— E1 逐字命中（见 9.2）。

### 9.2 技术声明验证表（仓内，E1 本会话双 pass）

| # | 声明 | 来源锚点 | 状态 | 置信度 |
|---|---|---|---|---|
| 1 | 只抽一次 `idx`，all/buy/sell 三组共用 | impact.py L313-314 + L316-321 | ✅ | ★★★★★ |
| 2 | 函数内 import（monkeypatch 运行期解析有效） | impact.py L219 / L269 | ✅ | ★★★★★ |
| 3 | 脚本层截面 demean | verify_capacity_impact.py L192 | ✅ | ★★★★★ |
| 4 | T3100_3 前半段恒真（base/shifted 同构 + side 平衡） | tests L293-311（L301 平衡 side） | ✅ | ★★★★★ |
| 5 | T3100_3 全 1 方向对照有效 | tests L313-322 | ✅ | ★★★★★ |
| 6 | T3100_9 夹逼由构造保证、缺常数输入用例 | tests L350-370 | ✅ | ★★★★★ |
| 7 | force-coverage 现仅字符串契约测试 | tests L247-254 | ✅ | ★★★★★ |
| 8 | `_event_panel` 期望可手算 | tests L382-417 | ✅ | ★★★★★ |
| 9 | plateau 契约（空/argmax/阈值/>=排序） | decay.py L92-98 | ✅ | ★★★★★ |
| 10 | md 标题硬编码 v3.9.3 | verify_capacity_impact.py L570 | ✅ | ★★★★★ |
| 11 | 门禁三判据 + 阈值常量 | panels.py L712-734 + L35-36 | ✅ | ★★★★★ |
| 12 | 门禁失败 exit 2 / force 留痕分支 | verify_capacity_impact.py L751-759 | ✅ | ★★★★★ |
| 13 | CLI 现状无 `--minute-root` | verify_capacity_impact.py 全文 grep：仅 L743 读 `cfg.minute_root`，无对应 add_argument | ✅ | ★★★★★ |
| 14 | `minute_root` 默认值与分钟窗口 | config.py L23 / L26-27 | ✅ | ★★★★★ |
| 15 | L859 为另一篇真 RFS 论文（Kelley 29(5)），不在订正范围 | RESEARCH_V3.8.0 L859 vs L860 | ✅ | ★★★★★ |
| 16 | v393「未修」标记待同步 | v393 RESEARCH L300 + CHECKLIST L270 | ✅ | ★★★★★ |
| 17 | E2E 数据可行性（月度文件数/体积/命名） | `E:\Level 1 Data` 实测：2020-02 = 20 个 `YYYY-MM-DD.feather`，共 244,296,616 B ≈ 233 MB | ✅（并修正 §3.3/§5 原估计 7.7 MB / 170 MB → FALSIFIED 已改写） | ★★★★★ |

### 9.3 Step 2 Review 清单 + 门禁 a-d

- [x] 所有 arXiv 编号已验证 — **N/A**（无 arXiv 引用）
- [x] 所有作者、年份、标题已验证 — §9.1 行 9（Crossref 逐字段）
- [x] 所有技术声明有支撑 — §9.2 全表 E1
- [x] 无未标注的推测 — 1 项估计已实测（§9.2 行 17）；剩余唯一估计「构建时长 30-60 s」已显式标 [估计-Step 9 实测回填]
- [x] 置信度标注完整 — §9.2 逐行 ★

**门禁**：
- (a) FALSIFIED 已改写并记入修订记录 ✅（E2E 体积估计，§3.3/§5/修订行三处）
- (b) CONFLICT / STEP_GAP_OPEN — **无**
- (c) 阻断性断言双源 ✅ — 仓内 17 项锚点均为 T1 文件本体 E1 且双 pass 复读；两项单源（§9.1 行 5 插件分级、行 7 SemVer 本体）均**非阻断**（前者仅支撑 U-1 判断、后者为标准本体且 U-3 已由用户裁决）
- (d) 假设区 — 唯一潜在假设「`--minute-root` 是否对外 API」已显式携带为 §6 U-3 改判触发条件；无其他未验证假设 ✅

### 9.4 契约取证字段（F1-F5）出具状态

| 字段 | 状态 | 说明 |
|---|---|---|
| F1 来源日期 | ✅ | §8.5 / §9.1 均标 2026-11-21（读取日） |
| F2 来源版本 | ✅（2 项「无版本」如实标注） | 官方文档为 en/stable 站点，无固定版本号 → 按 F2 缺项处置写「无版本」而非留空；DOI 有 Crossref 记录（indexed 2026-10-30）；仓内来源 = 文件 + 行号 |
| F3 降级链 | ✅（一次真实降级） | Step 1：`WebSearch`（结果偏泛、权威性不足）→ `WebFetch` 官方文档原文 → 命中；未静默跳过 |
| F4 引用验证表 | ✅ | 外部引用 9 条 ≥3 ⇒ 建表 §9.1 |
| F5 先失败记录 | N/A | 本步无代码 / fixture 改动；Step 9 出具 |

### 9.5 复审结论

**PASS（自查·单视角）**。发现并修正 1 项 FALSIFIED 估计（E2E 体积），无 CONFLICT、无未决残留；三项设计（§3.2 / §3.3 / §3.4）与裁决（§6）在证据层全部落锚。可进入 Step 3（DESIGN）。
