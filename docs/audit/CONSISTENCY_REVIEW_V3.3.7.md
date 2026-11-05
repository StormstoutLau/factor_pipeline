# v3.3.7 PL-08 AR 阶数选择 hold_back 可比性修复 — 步骤 8 文档一致性 review

**版本**: v1.0 (2026-11-04)
**缺陷**: DEFECT-PL-08
**规范依据**: [WORKFLOW_METHODOLOGY.md](../WORKFLOW_METHODOLOGY.md) v1.3 §13 (步骤 8: 四文档交叉对齐)
**对象与版本流转**:

| 文档 | review 前 | review 后 |
|------|----------|----------|
| 调研 [PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md](../analysis/PL08_AR_ORDER_AIC_COMPARABILITY_RESEARCH.md) | v1.2 | **v1.2 (无修订)** |
| 设计 [PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md](../analysis/PL08_AR_ORDER_AIC_COMPARABILITY_DESIGN.md) | v1.1 | **v1.2** (M3) |
| 实施 [EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md](../EXECUTION_V3.3.7_PL08_AR_ORDER_HOLDBACK.md) | v1.1 | **v1.2** (M1/M2/M4, 附录 D) |
| checklist [CHECKLIST_V3.3.7_PL08.md](CHECKLIST_V3.3.7_PL08.md) | v1.0 | **v1.1** (G0-4/G4-2/G6-7 口径) |

**方法**: (1) 四文档两两交叉对账 (版本/缓存/ADR 链、接口签名、TDD 用例计数与断言、数值锚点、§编号引用、文件变更清单、Gate 期望); (2) 全部声明逐项回源 (源码 grep + 读码 / 测试锚点 / 版本文件 / `git log`); (3) 数值锚点逐项回源调研 v1.2。未新造任何实测数字。

---

## §1 核对通过项 (C1-C12)

| # | 类别 | 检查项 | 方法 | 结果 |
|---|------|--------|------|------|
| C1 | 接口 | `_fit_ar(self, series: pd.Series, order: int) -> ARModelResult` (ar_model.py L139); `AROrderSelector.__init__` / `ARDecoupler.__init__` 默认值; `ARModelResult` 10 字段 | 读码 | 四文档声明一致, 与源码吻合 |
| C2 | 调用点 | `_fit_ar` 全集 L117/L132/L379; `dual_neutralizer.py` `def fit` L384 + `ARDecoupler(` L413 (关键字, L413-L417); `unified_decoupler.py` L162 / L375; `optimized.py` L221-L222 白名单 (V12) | grep | 设计 §2.1/§4.4 ↔ 实施 §3.6 一致且与源码吻合 |
| C3 | 版本字面量 | `pyproject.toml` L7 / `__init__.py` L58 / `config_v2.py` L371 / `reporting.py` L40 (现值 3.3.6, 每文件各 1 处); test_fix3 L33 (值) + L12/L40/L48/L57 (docstring); verify_fix3 L21 + L5 | grep | 实施 §5.1 清单与实际完全吻合 |
| C4 | 缓存字面量 | `cache_manager.py` L58 (值); test_fix3 L96/L112 (值) + L14/L80/L87 (docstring) — **另发现 L97 漏列 (M1)** | grep | 见 §3 |
| C5 | TDD 对账 | 10 函数 / 22 用例 (1+5+3+1+1+1+1+3+1+5); Red 13 failed = T1+T2(4)+T3(3)+T4+T5+T6+T7+T9; 9 passed = T2 p=5 + T8(3) + T10(5); checklist Gate 1 期望与实施 §4.2 一致 | 对账 + 步骤 5 预演 | 一致 |
| C6 | 断言锚点 | T2 `AutoReg(lags=p, hold_back=5, trend='c')` + `atol=1e-10` + AIC 差 -2; T5 ≤2.0 / T6 [1.8,3.2] / T7 [2.4,3.8]; T8 `atol=0` 手写旧公式; T9 无退化警告 + `t<12` identity; T10 参数化 {7,8,9,10,12} + 既有 7 点 = 11 截断点 | 设计 §6.1 ↔ 实施 §4.1 ↔ checklist Gate 2 | 三方一致; 守卫文案 `'有效样本不足'` 与测试 `match` 串一致 |
| C7 | 数值锚点 | `n_obs` 99/98/97/96/95 → 95×5; 4.800/2.200/3.867 → 1.233/1.000/1.000; 4.867→1.600; 4.87→2.53; 4.97→3.23; 2790 (6.9968) / 14410 (4.6718); MSE 1.067782→1.048759; 性能 2.76→2.72; 退化 322.68 / 5.3131 | 逐项回源调研 v1.2 §6 / 附录 A | 四文档无转抄漂移 (T=100 的 `max_abs=6.9968` 确认出自方案 C 探针, 非初版 5.7503) |
| C8 | ADR 链 | `DECISIONS.md` L43 (ADR-040) / L44 (ADR-041 起 未占用); 实施 §5.3 占用表+正文; 设计 §10; checklist G4-5/G4-6 | 读码 | 一致; 实施前写「待实施」、步骤 9 后改「已实施」的时序在两文档中口径一致 |
| C9 | 文档锚点 | README L1029/L1032/L1035/L1059 (恰 4 处 v3.3.6); ARCHITECTURE L17/L20; pyproject L10/L27/L28/L32/L33 (约束行) | grep + 读码 | 实施 §5.1/§5.5 与 checklist Gate 6 清单吻合 |
| C10 | §编号引用 | 实施 §0.3 引 RESEARCH §0/§2.2/§3.1/§3.4/§5.4/§5.5/§6.1–§6.5/§6.7/§6.8/§7.1/§7.2 与 DESIGN 各节; checklist G0-8/G0-9/G0-10 引调研 §6.2/§6.7/§6.3 | 打开小节标题 | 全部存在且内容对应 |
| C11 | 环境与工作树 | Git HEAD `34c2713`; 未跟踪 = research/design/execution/checklist 4 份文档; `ar_model.py` 未改; duckdb 缺包例外在实施 §1.1 与 checklist 头部口径一致 (基线与实施后均失败, 不计入验收) | git + 实测 | 一致 |
| C12 | 失败模式速查 | checklist §2 T1–T10 处置行与实施 §3.1/§4.1 逐条对应 (守卫文案/索引/hold_back/`transform` 回滚) | 对账 | 一致 |

---

## §2 分级结论

**CRITICAL 0 / MAJOR 0 / MINOR 4** (M1–M4, 全部已修复)。

无阻塞项: 4 处 MINOR 均为字面量清单 / 版本口径 / 行号锚点级别, 不触及方案 C 的算法、验收标准与 Gate 结构。**放行进入步骤 9 (TDD 实现)**。

---

## §3 发现并已修复 (M1-M4)

| # | 严重度 | 位置 | 问题 | 修复 |
|---|--------|------|------|------|
| M1 | MINOR | 实施 §5.2 | 漏列 `tests/test_fix3_version_unification.py` **L97** 断言失败消息中的 `'v2.2.4-cache'` 字面量 (`f"缓存 code_version 应为 'v2.2.4-cache', ..."`); 漏改后 (a) 失败消息与断言值不一致 (误导, 仅失败时可见), (b) checklist G4-2 的 grep "默认值/断言 0 命中" 判定歧义 (L97 既非默认值/断言比较值也非历史注释) | §5.2 补第 3 行 (L97 随 L96 同步为 `'v2.2.5-cache'`); checklist G4-2 期望列改为 "默认值/断言/失败消息 0 命中" |
| M2 | MINOR | 实施 §5.2 row 4 | 将 test_fix3 **L14** (当前统一目标描述行, `= "v2.2.4-cache"`) 与 L80/L87 (历史行) 合并处置为 "追加 v3.3.7 行"; L14 若只追加不改值将残留旧代号, 触发与 M1 相同的 G4-2 歧义 | 拆为 row 5 (L14 改值 `v2.2.5-cache`) / row 6 (L80/L87 追加历史) |
| M3 | MINOR | 设计 §2.1 / §12 P1 | `_get_ar_phi_for_diagnosis` 行号锚点写 **L308-L339**; 实际函数体止于 **L308-L330** (L332-L339 为 `_predict_one_step`); 步骤 4 review P1 对该行的"全部吻合"判定有误 | §2.1 改 L308-L330; §12 P1 加勘误注记; 设计文档升 v1.2 |
| M4 | MINOR | 实施 §6.1 | 步骤映射表第 3 行设计版本写 "v1.0" (初稿), 而第 1 行调研引用最终版 "v1.2" — 同表口径不一致 | 改为 "v1.2 (v1.0 初稿 → 步骤 4 review v1.1 → 步骤 8 勘误 v1.2)"; row 5 同步引用 v1.2 |

**备忘 (随 M1/M2 一并处理, 不单独计)**: checklist G0-4 "实际"列的 "3 份文档未跟踪" 为撰写时点值 (checklist 自身即第 4 份), 已加注 "步骤 9 复跑以 `git status` 为准"。

---

## §4 修复后状态

| 文档 | 版本 | 本步变更 |
|------|------|---------|
| 调研 | v1.2 | 无修订 (全部数值/结论/引用对上) |
| 设计 | **v1.2** | M3: §2.1 φ 钩子行号 L308-L330; §12 P1 勘误注记; 尾部完成行更新 |
| 实施 | **v1.2** | M1/M2: §5.2 补 L97、拆 L14 与 L80/L87; M4: §6.1 版本口径; 头部 v1.2 + 附录 D; §6.1 步骤 7/8 状态置 ✅ |
| checklist | **v1.1** | 头部引用升版 (实施 v1.2 / 设计 v1.2); G4-2 期望列口径; G0-4 复跑注记; G6-7 设计版本号; 尾部完成行 |

**实施文档 §5.2 修复后缓存字面量全景** (test_fix3 共 6 处旧代号: L14/L80/L87/L96/L97/L112 — 全部入清单, 步骤 9 实施后 `git grep "v2.2.4-cache"` 仅剩 L80/L87 历史 docstring, 与 G4-2 期望一致)。

---

## §5 结论与放行

- 四方文档在**版本链** (v3.3.7 / `v2.2.5-cache` / ADR-041)、**接口签名**、**TDD 契约** (10 函数/22 用例, Red 13/9 → Green 22)、**数值锚点**、**文件变更清单** (13 文件) 上互相一致且可回源。
- 无幻觉级错误; 4 处 MINOR 已全部修复并留痕 (实施附录 D / 设计 §12 P1 / checklist v1.1 / 本文件 §3)。
- **放行**: 进入步骤 9 (TDD 实现): Red `tests/unit/test_ar_order_holdback.py` → Green `_fit_ar` → 靶向回归 72/1 → 性能/偏移复测 → 版本/缓存/ADR-041/CHANGELOG/状态文档 → 回填 checklist Gate 1–7 与实施 §7.2。

---

**Review 完成**: 2026-11-04 (v1.0); 下一步为步骤 9 (TDD 实现)。
