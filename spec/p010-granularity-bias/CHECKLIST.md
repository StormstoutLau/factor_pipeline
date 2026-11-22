# 审查验收 Checklist：P-010 月聚类 CI + 粒度披露

---
id: p010-granularity-bias-CHECKLIST
type: design
version: 1.3
status: accepted
date: 2026-11-22
depends: [p010-granularity-bias-IMPLEMENTATION, p010-granularity-bias-DESIGN]
upstream: null
---

> **Feature**: 标定系数 `c` / `b` 的 bootstrap 口径由 iid 行抽样改为月聚类整块重采样，并披露粒度、簇数与少簇敏感性
> **创建日期**: 2026-11-22
> **状态**: 已验收（**67/67 通过，0 失败 / 0 待办**；Step 10 ADD 审计 PASS_WITH_FIXES：0×P1 / 1×P2 / 2×P3 已处置，质量门 4.8/5 档位 A；Step 9 红→绿：红 8 failed / 1 passed → 绿 93 passed）
> **Spec 步骤**: Step 7-10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) **v1.3 verified**（含 §14 Step 9、§15 Step 10 记录）
> **基于设计**: [DESIGN.md](./DESIGN.md) **v1.1 verified**
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.3 verified**
> **包版本**: 3.9.7 → **3.9.8** ｜ **档位**: T1

**验收执行顺序**：① Step 8 文档一致性（§1 + §9）→ ② Step 9 TDD 红→绿（§2-§7，逐项回填证据）→ ③ Step 10 ADD 审计（§8）→ ④ §10 统计与决定（整数单元格、算术自洽）。

> **Step 10 记录（2026-11-23，独立只读子代理 ADD 审计）**：判定 **PASS_WITH_FIXES**（0×P1 / 1×P2 / 2×P3）：A-1 P2（INV-3 真子集边界缺测试，C-V3 声称的「构造缺月样本」不存在）→ 已补 `test_month_true_subset_when_adv_missing`；A-2 P3（TP10-6/TP10-10 SHA/hash 仅人工实测）→ 登记披露（IMPLEMENTATION §14.3 V3/V5）；A-3 P3（`length_mismatch` 回退 warning 缺长度差实值）→ 已修复（warning 附 `month=N/样本=M` + mismatch 用例断言加强）。修复后回归：容量+版本 **52 passed**、分钟面板 **42 passed**（41→42）；质量门初评 4.65/5 → 复评 **4.8/5 档位 A**；Iron Law 4 项 PASS（详见 §8 与 IMPLEMENTATION §15）。

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN D1-D7 每条可追溯到 RESEARCH 结论 | ✅ | §2.1 八行映射的章节（§3.4/§4.1/§4.4/§3.3/§3.1/§5.2/§6.2/§3.6）均存在且内容对应 |
| RESEARCH 五项关键发现均在 DESIGN 中被使用 | ✅ | Δc −4.02%（§1.2/§2.1）、CI +83.8%（§1.1/§2.1）、CV ±0.002%（§2.1）、1.677 行/股月（§10.2）、granularity=daily（§2.1） |
| 无文档间矛盾（数值/口径/结论） | ✅ | 全文 grep 复核：`+83.8%` 三文档主口径一致；`+83.9%` 仅存于 RESEARCH §5.3/§5.4 修正记录（合法历史引用）；CV 精确值 +0.0018%/+0.0011% 一致 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN §3.2 四个模块均有实施落点 | ✅ | panels/runner/report → S1-S5；上游文档勘误 → D-10-4/D-10-5（Step 8/9 执行） |
| IMPLEMENTATION 接口签名与 DESIGN §4 一致 | ✅ | `_bootstrap_ci(clusters=None)`、`_wild_sqrt_ci`、build 四键、`c` 块 10 字段逐一对齐；`c_ci_n_clusters` int\|null（DESIGN §4.4 ↔ IMPLEMENTATION F-2 已同步） |
| INV-1~INV-6 均有实施位置 | ✅ | IMPLEMENTATION §7 表逐条对应 |
| 无设计未覆盖的实施 | ✅ | 版本落点（D7）与测试（DESIGN §12）已登记；wild 的 c 由 `SqrtImpact().fit` 求得与 DESIGN §4.2 公式数学等价（IMPLEMENTATION §13 F-3 已留痕） |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION 功能点在本 checklist 均有验收项 | ✅ | S1-S7 ↔ C-F1~C-F14/C-I*/C-V*/C-E*/C-P*/兼容性 |
| 每个验收项可追溯到 IMPLEMENTATION 章节 | ✅ | 每项「测试方法」列已注 TP10-x 或 §x.y |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| CI 口径 token | 方案 C（月聚类） | `month_cluster_pairs` | `month_cluster_pairs` | ✅ |
| 回退 token | —— | `iid_fallback` | `iid_fallback` | ✅ |
| 簇数 | 39 月 | `c_ci_n_clusters`（int\|null） | `c_ci_n_clusters`（回退 null） | ✅ |
| 小样本修正 | group_debias | `sqrt(g/(g−1)·(n−1)/n)` | 同式 + ×1.0131 | ✅ |
| 样本粒度 | 股票×日 | `granularity="daily"` | `granularity="daily"` | ✅ |
| 压力档 | stress = max(0.5, upper) | 公式不变 | 公式不变（仅报告值变化 2.9213→2.9349） | ✅ |
| 月标签 | 39 月窗口 | `month` | `impact_samples["month"]` | ✅ |

## 2. 功能验收

### 2.1 `panels.py`（月标签与 meta）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| C-F1 月标签与样本对齐 | TP10-5 | `len(month)==len(p)==len(impact)==len(sigma)` 且逐行对应同一样本 | ✅ | `test_impact_samples_month_meta` 通过；真实 39 月 `n=200000` |
| C-F2 meta 四键正确 | TP10-5 | `cluster=="month"`、`n_clusters==39`（真实窗口）、`ci=="month_cluster_pairs"`、`granularity=="daily"` | ✅ | 校准工件：`n_clusters=39, granularity=daily, cluster=month, ci=month_cluster_pairs` |
| C-F3 全局 cap 后仍对齐 | 真实 39 月（200031 → 200000） | 截断到 `SAMPLE_CAP` 后四数组等长，且 `month` 随同索引变化（抽样后 month 集合仍 ⊆ 原集合） | ✅ | 生产 `n=200000`、`n_clusters=39`；`set(month) ⊆ coverage.months` |
| C-F4 旧函数已删除且无悬空引用 | `grep -rn "_stratified_sample" backtest/ tests/` | 仅 docs 提及（D-10-4 待改），代码/测试 0 命中 | ✅ | 代码/测试 0 命中；WIRING 文档已改（D-10-4） |

### 2.2 `runner.py`（聚类 bootstrap）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| C-F5 iid 路径逐位不变 | TP10-2 + 既有 `test_same_params_same_result` | 与 v3.9.7 输出（同 panels/seed）`json.dumps(sort_keys=True)` 相等 | ✅ | 回退用例 `c_calib_lower == c_calib_lower_iid`；确定性测试通过 |
| C-F6 聚类 CI 比 iid 宽 | TP10-1 | 10 簇强相关构造下，聚类宽度 > iid 宽度（同 seed） | ✅ | `test_bootstrap_cluster_wider_than_iid` 通过（实测 ≈3.6×） |
| C-F7 聚类结果可重放 | TP10-3 | 两次 `run_calibration` 输出逐位相等 | ✅ | `test_bootstrap_cluster_reproducible` 通过 |
| C-F8 簇数报告正确 | TP10-4 | `c_ci_n_clusters == len(np.unique(month)) == 39` | ✅ | 合成 39 簇与真实 39 月均通过 |

### 2.3 少簇敏感性（debias / wild）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| C-F9 debias 宽度比例正确 | TP10-7 | `(debias_hi−debias_lo)/(upper−lower) == sqrt(g/(g−1)·(n−1)/n)`，容差 1e-12；g=39、n≈200k 时 ≈1.01307 | ✅ | `test_debias_width_scaling` 通过；报告 `×1.0131` |
| C-F10 wild CI 可用 | TP10-8 | 两端有限、包含点估计；`c_ci_wild_lower < c_ci_wild_upper` | ✅ | 合成 `[3.905, 5.600]` 含 4.695；真实 `[2.887, 2.933]` |
| C-F11 单簇 wild 降级 | TP10-8（参数化） | 簇数 <2 → 回退 iid、wild 字段 `None` + warning `c_ci_fallback_iid`；wild 自身失败时 warning `c_ci_wild_unavailable`（C-E5） | ✅ | `test_ci_fallback_without_month[single]` + monkeypatch 用例 |

### 2.4 `report.py`（披露）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| C-F12 新 payload 渲染披露 | TP10-9 | 含 `` `month_cluster_pairs` ``、簇数 `39`、`iid 对照`、`group_debias`/`wild` 行 | ✅ | `test_report_disclosure`；真实 md 三行齐备 |
| C-F13 旧 payload 逐字不变 | TP10-9 | 无新键的 payload 渲染结果与 v3.9.7 基线完全相同 | ✅ | 旧 payload 无「CI 口径」行，`c_calib_stress` 行保留 |
| C-F14 回退不打印簇数 | TP10-2 | `c_ci_method=="iid_fallback"` 时输出含「iid_fallback」且不含「簇数 39」 | ✅ | `test_report_disclosure` 回退分支断言通过 |

## 3. 接口验收

### 3.1 `_bootstrap_ci`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| C-I1 签名与 DESIGN §4.1 一致 | 参数顺序 `(fit_fn,p,impact,sigma,seed,n_boot=200,clusters=None)`、返回二元组 | ✅ |
| C-I2 正常输入 | 返回 `(p5, p95)` 且 `p5 <= p95` | ✅ |
| C-I3 有效重抽 <20 | 返回 `(None, None)`（沿用现规则） | ✅ |
| C-I4 簇标签长度错误 | 调用方判定回退，函数不抛异常 | ✅ |

### 3.2 `_cluster_blocks` / `_cluster_labels`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| C-I5 块覆盖完整 | 所有块索引拼接排序后 == `arange(n)`，无重复无遗漏 | ✅ |
| C-I6 块内原序 | 每块索引严格递增 | ✅ |
| C-I7 标签缺失 | 返回 `(None, "missing")` | ✅ |
| C-I8 单簇 | 返回 `(None, "too_few")` | ✅ |

### 3.3 `_wild_sqrt_ci`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| C-I9 签名与 DESIGN §4.2 一致 | `(p, impact, sigma, clusters, seed, n_boot=200)` → 二元组；c 由 `SqrtImpact().fit` 求得 | ✅ |
| C-I10 退化输入 | `denom<=0` 或 `n_boot<20` 或 `g<2` → `(None, None)` | ✅ |

### 3.4 `build()` 输出

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| C-I11 `impact_samples` 新键 | `month` 为 object 数组、等长、元素形如 `YYYY-MM` | ✅ |
| C-I12 meta 新键类型 | `cluster:str`、`n_clusters:int`、`ci:str`；JSON 可序列化（`_jsonable`） | ✅ |

## 4. 不变式验收

| 不变式（来自 DESIGN.md §8） | 验证方法 | 状态 |
|---------------------------|---------|------|
| C-V1 INV-1 默认路径 SHA `82728CE1…` 不变 | TP10-6：跑前落盘 → 跑默认脚本 → `hexdigest` 全等（或 `.upper().startswith("82728CE1")`） | ✅ |
| C-V2 INV-2 `clusters=None` 与 v3.9.7 逐位一致 | TP10-2 + 既有确定性测试 | ✅ |
| C-V3 INV-3 四数组等长且 `set(month) ⊆ set(panel.months)` | TP10-5 + 构造缺月样本（允许真子集，不报错）；Step 10 A-1 补测 `test_month_true_subset_when_adv_missing`（2023-02 ADV 缺 → 真子集且不报错） | ✅ |
| C-V4 INV-4 `granularity=="daily"` 且 `panel_hash` 不变 | TP10-5 + TP10-10（hash 与 P-008 基线 `dfcc4e1d…` 一致） | ✅ |
| C-V5 INV-5 `c_ci_n_clusters` 与 `len(unique(month))` 同源 | TP10-4；检查报告簇数与 JSON 同值 | ✅ |
| C-V6 INV-6 `c` 块只增不改 | 既有 `test_c_triplet` 通过；`c_default/c_calib_point/c_calib_stress` 公式未改（grep diff） | ✅ |

## 5. 错误处理验收

| 错误场景（来自 DESIGN.md §7） | 触发方式 | 预期行为 | 状态 |
|------------------------------|---------|---------|------|
| C-E1 `month` 缺失 | `_panels()` 不含 `month` | iid 回退 + `c_ci_method=="iid_fallback"` + warning `c_ci_fallback_iid` | ✅ |
| C-E2 `month` 长度不一致 | 传入长度错标签 | 同上回退，不抛异常；warning 注明长度差 | ✅ |
| C-E3 簇数 <2 | 全部行同一 month | 同上回退；`c_ci_n_clusters is None` | ✅ |
| C-E4 有效重抽 <20 | monkeypatch `_bootstrap_ci` 返回 `(None,None)` | CI = `(point, point)` + warning（沿用） | ✅ |
| C-E5 wild 不可用 | monkeypatch `_wild_sqrt_ci` 返回 `(None,None)` | 字段 `None` + warning `c_ci_wild_unavailable`，不阻断 | ✅ |
| C-E6 p/sigma 退化（denom ≤ 0） | 全零 sigma / `n_boot=10` | wild 返回 `(None, None)`，其余字段正常 | ✅ |
| C-E7 sqrt 拟合失败 | sigma=0（sqrt 需 σ>0，其他模型可拟合） | `sqrt_params=None` → 既有 warning；`c_info` 保持默认三档，不新增崩溃 | ✅ |

> Step 10 A-3：C-E2 的「warning 注明长度差」在 Step 9 时仅含 reason token，审计发现后已补实值（`month=N/样本=M`），断言见 `test_ci_fallback_without_month[mismatch]`（`month=195`/`样本=200`，非恒真）。

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| C-P1 聚类 bootstrap 增量耗时 | 39 月 / ≈200k 样本下，相对 v3.9.7 增量 ≤ 3 s | iid 1.222 s / 聚类 1.016 s（200 次，n=200031）；含 iid 对照 + wild 总增量 ≈1.05 s | ✅ |
| C-P2 分组复杂度 | `_cluster_blocks` 单次 `argsort`，O(n log n)，循环内无重排 | 结构化检查通过 | ✅ |
| C-P3 无簇标签时零额外开销 | `labels is None` 时不算 debias/wild，仅 iid + iid 对照（对照本身 200 次） | 代码路径检查通过 | ✅ |

> 说明：iid 对照为契约要求（`c_calib_*_iid`），即使在回退路径也会执行一次，属预期成本而非退化。

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.9（`requires-python` 下限） | ✅ | 未新增语法/API；`requires-python` 未变 |
| Python | 运行环境实际版本 | ✅ | **3.13.5**，定向 93 passed |
| OS | Windows（本地） | ✅ | 默认脚本 + 校准 + 全部 pytest 实测 |
| 工件兼容 | 旧 `capacity_calibration.json` / 旧 payload | ✅ | report 不渲染新键；`run_calibration` 接受无 `month` 面板 |
| 版本一致性 | 7 个落点 | ✅ | 6 代码锚点 + CHANGELOG 均为 3.9.8；版本测试 9 passed |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 0.90 | TP10-1~10 + C-* 均可机械断言；Step 10 A-1 补 INV-3 真子集边界；SHA/hash 为登记的人工实测口径（A-2，读数见 IMPLEMENTATION §14.3） |
| 模块映射 | 1.0 | DESIGN §3.2 四模块 ↔ S1-S7 |
| 接口契约 | 1.0 | 签名、返回、字段类型已锁定 |
| 修正项 | 1.0 | Step 4/6 共 15 项发现均已落盘并有验收项 |
| 跨模块契约 | 0.9 | panels→runner→report 键名与语义一致 |
| **总分** | 4.8/5（初评 4.65） | **档位**: A |

> 初评（审计时）：可测试约束 0.75（INV-3 真子集边界缺测试、SHA/hash 仅人工实测）；A-1 修复后复评 0.90，总分 4.8/5 档位 A（A-2 维持人工实测为登记决策，故不满分）。

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P2×1（A-1） | INV-3 真子集边界（某月 ADV 缺失 → `set(month) ⊊ coverage.months`）无测试；C-V3 声称的「构造缺月样本」不存在，既有 ⊆ 断言跑在等值场景 | `test_impact_samples_month_meta` 既有断言跑在 4 码×3 月全有 ADV 的 fixture；CHECKLIST C-V3 行 | ✅ 已补 `test_month_true_subset_when_adv_missing`（2023-02 行 ADV 置 NaN → 真子集且 build 不报错）；IMPLEMENTATION §15 A-1 |
| P3×1（A-2） | TP10-6 / TP10-10 默认 SHA 与 `panel_hash` 断言未落为自动化测试，仅人工实测 | tests 内无 `82728CE1` / SHA 守卫用例；读数仅见 IMPLEMENTATION §14.3 V3/V5 | 登记披露：SHA/hash 属 E2E 级验证，维持人工实测口径，不补守卫测试（先例：P-008 ⑫ 同口径） |
| P3×2（A-3） | `length_mismatch` 回退 warning 未含长度差实值（DESIGN §7 要求「含长度差」），仅含 reason token | runner.py 回退 warning 分支 | ✅ 已修复：warning 附 `month=N/样本=M`；`test_ci_fallback_without_month[mismatch]` 加强断言 `month=195`/`样本=200`（红 1 failed → 绿，IMPLEMENTATION §15 A-3） |

### 8.3 ADD Iron Law 检查

- [x] 测试通过的 4 类盲区已检查（2026-11-23 独立审计，四类均 PASS）：
  - 断言恒真式（如 `assert x == x`、仅断言类型）：**无**——13 项新增测试逐条审读（宽度比 >2×、debias 公式复算容差 1e-12、块索引拼接 == [0..4]、回退分支 `c_ci_debias_lower` 键缺失等），全部有语义判别力
  - 单文件检查盲区（panels 改了但 runner 未测，反之亦然）：**无**——panels 月标签+meta（`test_impact_samples_month_meta` + A-1 边界例）、runner 聚类消费（TP10-1/2/3/4/7/8）、report 三分支（新键/回退/旧 payload）齐备
  - 设计文档独有约束无测试（INV-3 的 `⊆` 边界、F-2 的 null 语义）：**已闭环**——INV-3 真子集边界由 A-1 补测；F-2 回退簇数 null、INV-2 逐位一致、INV-5 同源均有测试
  - 修正阻断性项无测试（Step 4 F-1 容量归因、Step 6 F-2 回退簇数）：**无**——F-2 null 断言在位（`assert c["c_ci_n_clusters"] is None`）；F-1 属文档归因订正，`c_effective` 路径由既有 c 三档测试守卫

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ✅ | ✅（v1.3；§3.1 勘误 F-9-1 与文档链一致） |
| DESIGN.md | ✅ | ✅（v1.1；§5.2 优点表述改引 `EXECUTION_V3.8.0` L219） |
| IMPLEMENTATION.md | ✅ | ✅（v1.3；§14 Step 9 实施记录 + §15 Step 10 ADD 审计记录与代码一致） |
| CHECKLIST.md（本文件） | ✅ | ✅（v1.3 accepted） |
| ADR（如有） | N/A | N/A |
| 开发日志（`docs/DEV_PROGRESS.md`） | ✅ | ✅（记录见本文件头部 Step 9/10 记录 + IMPLEMENTATION §14/§15；git 提交待用户指令） |
| 上游勘误（`spec/v392-calibration-unit-fix/DESIGN.md` L39 / `RESEARCH.md` L50） | ✅ | ✅（D-10-5：两处加勘误标记，指向 `EXECUTION_V3.8.0` L219 docstring） |
| WIRING 文档（`docs/EXECUTION_V3.8.1_MINUTE_PANEL_WIRING.md` L494-L511） | ✅ | ✅（D-10-4：改写为 `_sample_indices` + 四数组同索引切片，注明 `_stratified_sample` 已删） |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 16 | 16 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 12 | 12 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 7 | 7 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 5 | 5 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 67 | 67 | 0 | 0 |

> **统计口径（RULE-2）**：上表来自本文件**逐项核对**（每一项均有独立标记），非事后汇总推算。当前态：Step 8 完成（16/16 ✅）→ Step 9 完成（红 8 failed / 1 passed → 绿 93 passed，§2-§7 回填）→ Step 10 完成（ADD 审计 **PASS_WITH_FIXES**：0×P1 / 1×P2 / 2×P3；A-1/A-3 已修复、A-2 登记披露；质量门复评 4.8/5 档位 A；Iron Law 4 项 PASS）。每行满足「总数 = 通过 + 失败 + 待办」，总计为 8 类行**按列求和**（67 = 67 + 0 + 0 ✓）。

### 10.2 验收决定

- [x] **验收通过**：所有 P1 项通过，无阻塞性问题 —— Step 10 独立 ADD 审计 **PASS_WITH_FIXES**（0×P1 / 1×P2 / 2×P3，初评 4.65/5 档位 A）；A-1（INV-3 真子集边界补测）+ A-3（warning 长度差实值）已修复，A-2 登记披露；修复后复评 **4.8/5 档位 A**；**67/67 通过 / 0 失败 / 0 待办**；默认 SHA `82728CE1…` 与 `panel_hash dfcc4e1d…` 逐位不变
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | Trae（AI agent） | 2026-11-23 |
| 审查者 | 独立只读子代理（Step 10 ADD 审计） | 2026-11-23 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| Step 8 文档一致性（§1 + §9） | —— | 2026-11-22 | ✅ 16/16 PASS、0 修正 |
| Step 9 TDD 红→绿（§2-§7） | —— | 2026-11-23 | ✅ 红 8 failed / 1 passed → 绿 93 passed（容量 43 / 分钟面板 41 / 版本 9）；默认 SHA `82728CE1…`、`panel_hash dfcc4e1d…` 逐位不变；39 月校准 `c=2.910690`、`n_clusters=39`、宽度比 1.8095 |
| Step 10 ADD 审计（§8）+ 回填 §10.1 | —— | 2026-11-23 | ✅ PASS_WITH_FIXES：0×P1 / 1×P2 / 2×P3（A-1/A-3 修复、A-2 登记）；质量门 4.8/5 档位 A；修复后回归 52 + 42 passed；67/67 |
| 更新 PROGRESS.md | —— | 2026-11-23 | ✅（P-010 行 ⑪⑫ 回填，状态 → done） |
| 记录开发日志 | —— | 2026-11-23 | ✅（本文件头部 Step 9/10 记录 + IMPLEMENTATION §14/§15） |
| git 提交 | 待用户指令 | 提交时 | 待办 |
