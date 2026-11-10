# v3.4.0 因子路由统一化治理 — 步骤 8 文档一致性 review

**版本**: v1.0 (2026-11-10)
**变更主题**: 统一横截面秩管道替代三路指纹路由; 配置面删 5 字段; 新增诊断/断点监控
**规范依据**: [WORKFLOW_METHODOLOGY.md](../WORKFLOW_METHODOLOGY.md) v1.3 §13 (步骤 8: 四文档交叉对齐)
**对象与版本流转**:

| 文档 | review 前 | review 后 |
|------|----------|----------|
| 调研 [FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md](../analysis/FACTOR_ROUTING_OVERENGINEERING_RESEARCH.md) | v1.1 | **v1.1 (尾部勘误注, 不升版)** (M-6) |
| 设计 [FACTOR_ROUTING_OVERENGINEERING_DESIGN.md](../analysis/FACTOR_ROUTING_OVERENGINEERING_DESIGN.md) | v1.1 | **v1.2** (C-2/C-3/C-4/m-2/m-3/m-4) |
| 实施 [EXECUTION_V3.4.0_UNIFIED_ROUTING.md](../EXECUTION_V3.4.0_UNIFIED_ROUTING.md) | v1.1 | **v1.2** (C-1/C-4/m-5/m-6/m-7/m-9) |
| checklist [CHECKLIST_V3.4.0_UNIFIED_ROUTING.md](CHECKLIST_V3.4.0_UNIFIED_ROUTING.md) | v1.0 | **v1.1** (C-1/C-4/m-1/m-7/m-8 口径) |

**方法**: (1) 双轨并行 review — 轨道 A (引用/数值锚点/ADR 链四方对账) + 轨道 B (接口签名/验收标准/Gate 对账回源); (2) 约 60 处行号/签名/计数锚点逐一 grep/读码实测; (3) 数值锚点逐项回源调研 v1.1 (0.999998 / 0.308 / 49.5% / −37.6% / 2σ→0.4041 / 62↔T=1472 / T=750→26 点)。未新造任何实测数字。

---

## §1 核对通过项

| # | 类别 | 检查项 | 方法 | 结果 |
|---|------|--------|------|------|
| P1 | 数值锚点 | 0.999998 (含 1−ρ 中位 ≈2e-6 / 范围 1e-6~4e-6)、0.308、49.5%、−37.6% (0.1156→0.0721, 比值 0.567)、2σ→AR1=0.4041 | 逐项回源调研 §3.3/§4.3/§4.4/§5.3/§6.1 | 四文档无转抄漂移 |
| P2 | 断点账目 | ⌊(1472−250)/20⌋+1 = 62 (调研 §5.4 / 设计 §3.7.3 / 实施 §5.3+§10.2 B1 / checklist G2-22/G2-29/G5-9); 调研 §5.3 场景 T=750→26 点对照注算术正确; 驼峰注记两文档一致 | 算术复核 | 一致 |
| P3 | 基线 | 106 passed / 1 env-fail; 107 = 13+14+12+13+15+20+20; fix1 3 passed / 1 skipped | 实施 §1.2 ↔ checklist G0-5/G0-6/G0-7 | 一致 |
| P4 | 用例账目 | 删 46 = multi_dim 20 + p0_fixes 8 + p3_phase2 8 + ablation 8 + task1 净删 2; 改写 17 = ablation 9 + task1 3 + fix2 5; 新增 20 = T1–T14 + B1–B6; Gate 3 期望 (12+1 / 6 / 4 / 13 / 15 / 20 / 3+1 / 12 / 53 / 6 / 5) 逐一实数核对 | 对账 + grep 实数 | 实施↔checklist 一致 |
| P5 | 版本链 4 处代码锚 | pyproject L7 / `__init__` L58 / config_v2 L371 / reporting L40 = 3.3.7; cache_manager L58 = `v2.2.5-cache`; test_fix3 L33 | grep 实测 | 命中 (第 6 处路径错误见 C-1) |
| P6 | 接口签名 | `PipelineV2Config` 5 待删字段 L706-709/L724 及默认值; config_v2 5 个 Pydantic 字段 L405-424 + `extra="ignore"` L437 + 桥接 4 行 L531-534; optimizer 空间 8 键 L47-56 + 双向映射 L161-164/L173-180/L213-224 + **无 `import warnings`**; `FingerprintMeta`/`FactorRoutingRecord` 字段与 frozen; 频率阈值链 <1/≤2/≤8/≤20/≤45/≤135/≤400 三处一致; `BreakMonitorConfig` 8 字段; `_log_spec` 12 键; spec_log L32-34 构造即 makedirs | 设计 §3 ↔ 实施 §3-§7 ↔ 读码 | 约 24 处全中, 行号零漂移 |
| P7 | 消融锚点 | routing_mode 5 值 L326; L531 deepcopy / L552 构造 / L558-559 调用; `_override_routing` L575-630; run_l2 四臂 L994-999 + b3_full_result L1011-1022; TestL2Ablation **9 方法** L1094-1214 全部精确; TestRoutingOverride 5 方法 L1826-1930; `_capture_pipeline_configs` L871-893 捕获 `AblationConfig` (docstring L875 证实); task1 5 用例 L38/52/66/80/94 | grep/读码 | 14+ 处全中 |
| P8 | 学术引用 | Andrews 1993 (trim=0.15 / Π=[0.15,0.85]) 与 Inclán-Tiao 1994 ((y−ȳ)² 工程化变体) 四方一致; BH 1995 归属 (设计新增) 在实施 §0.3 与 checklist §2 标注正确; AR(1) 代理自助 = 设计 m10 三方一致; 实施 §0.3 全部 11 行 RESEARCH § 真实存在且内容匹配 | 打开小节标题 | 一致 |
| P9 | ADR 链 (占用现状) | DECISIONS.md L43-L45: ADR-041 (v3.3.7) 已占用 / "ADR-042 起 未占用" — checklist G0-9 与现状一致 (预指定编号的治理问题见 C-4) | 读码 | 现状一致 |
| P10 | §编号/文件路径 | 13 个回归命令文件全部存在 (2 个新测试文件确认尚不存在 = 符合"待新增"); 9 个手工脚本/关联测试存在; p0_fixes L808 / p3_phase2 L281-282 注册行精确; README L52/L1060/L1063/L1091 版本行 | Glob/grep | 命中 |
| P11 | A1–A17 映射 | checklist §1 十七条逐条过: 判据与实施 §11 原文一致、Gate 编号全部真实存在且语义正确 | 对账 | 一致 (A9 补 G2-44, 见 m-8) |
| P12 | 失败模式速查 | checklist §4 抽查 9 行处置与实施文档逐条对应 | 对账 | 一致 |

---

## §2 分级结论

**CRITICAL 0 / MAJOR 4 / MINOR 9** (C-1~C-4 + m-1~m-9, 全部已修复)。

无阻塞项: 4 项 MAJOR 均为路径/账目/治理措辞级, 不触及统一管道方案主体、TDD 契约与 Gate 结构。**放行进入步骤 9 (TDD 实现)**。

---

## §3 发现并已修复

| # | 严重度 | 位置 | 问题 | 修复 |
|---|--------|------|------|------|
| C-1 | MAJOR | 实施 §2/§3.4/§8.3 + checklist G4-1/G4-4 | 版本链第 6 处写作 `tests/manual/verify_fix3_manual.py`, 实测该文件在 **`tests/test_backtest/`** (tests/manual/ 下无此文件); G4-4 命令按原路径直接报错 | 两文档 3 处路径改为 `tests/test_backtest/verify_fix3_manual.py`; "6 处"计数不变 |
| C-2 | MAJOR | 设计 §5.1-E6/§5.3/§6.2/§7-R3 | 设计称 p0_fixes 删 11 (`TestSoftRouting` 8 + `TestGetPipelineWeightsHardRouting` 3); 实测该文件仅 14 用例 = TestSoftRouting 8 + TestThresholdCalibration 6, **无** TestGetPipelineWeightsHardRouting — 该类实居 test_p3_phase2 L80; 且"加权混合 test_04/05/06"中 test_06 实为单管道路由 | 设计四处勘误: 11→8、类归属改注、加权混合改 test_04/05 (升 v1.2) |
| C-3 | MAJOR | 设计 §8 锚点表 | BH 1995 行标"调研 §8.3" — 实测调研全文无 Benjamini/BH 条目 (BH 为设计新增引用; 实施 §0.3 与 checklist §2 均已正确标注, 唯设计自身未同步) | 该行改为"— (设计新增引用; 调研无 BH 条目, 调研 §6.6 仅含 OOS/DSR)" |
| C-4 | MAJOR | 设计头部/§0.1-D11/§5.2/§11 + 实施 §0/§8.3/§11-A16/§13.2/§13.3 + checklist G4-5/A16 | 三方工件全链预指定 "ADR-042"; DECISIONS.md 登记规则 2 (2026-10-21, L20) 明文: 规划文档记录待实施决策"须写「ADR 编号待分配」, 不得自行指定编号; 实施完成后回本文档取号" | 三文档全部改为"ADR 编号待分配 (当前空闲号 ADR-042, 全文暂以其指代, 实施落库时回 DECISIONS.md 取号)"; checklist G4-5 判据同步为"取号落位" |
| m-1 | MINOR | checklist §2 | Bai & Perron 与 Perron 两行调研指针写 §5.4, 实测两文献在 §5.2/§5.3; "已在设计 §3.7 说明"过强 | 指针改 §5.2 (§5.2/§5.3); 措辞改"方法集合隐含不实施" |
| m-2 | MINOR | 设计 §6.1 B1/B3 | B1 仍引"调研 §5.3 场景…62 点" (实施 v1.1 C2 已勘明该场景仅 26 点)、B3 仍 ×2 (实施 m9 已改 ×4) — 实施修复未回port 设计 | 设计 §6.1 同步勘误 (T=1472 显式 + 驼峰注记 + ×4), 升 v1.2 |
| m-3 | MINOR | 设计 §5.3 | 类名 "TestOverrideRouting" 实测为 **TestRoutingOverride** (L1826); TestL2Ablation 记 4 臂断言, 实测 9 方法 (实施 M2 已改, 设计未同步) | 类名与 9 方法口径勘误 |
| m-4 | MINOR | 设计 §5.3/§6.2 task1 行 | "删 5 新增 2" (净 −3) vs 实施 "5→3 净删 2" — 同链口径不一 | 设计注明"以实施 §8.2/§9.5 为权威口径", 行文统一为 5→3 净删 2 |
| m-5 | MINOR | 实施 §14 v1.0 行 | "31 个删除用例"与同版 §0.2 的 36 及 v1.1 m4 的 46 不衔接 | v1.0 行加口径注 (31 初稿 → 同版 §0.2 36 → v1.1 m4 勘 46) |
| m-6 | MINOR | 调研尾部 + 实施 §14 结论 | 修订计数与列举不对齐: 调研 v1.1 称 MINOR 12 仅列 m1–m9; 实施 v1.1 结论援引 m1-m4+m10 共 5 条目却记 MINOR 4 | 两处补"条目号≠发现数"勘误注 (调研尾部注 + 实施结论括注); 调研不升版 |
| m-7 | MINOR | 实施 §9.4 + checklist G2-41 | run_l2 docstring 除 L983 "5 配置" 外 L985 还有"返回 5 个 AblationResult", 不在 G2-41 的 grep `"5 配置"` 覆盖内 | §9.4 改为 3 处 (L983/L985/L1410); G2-41 grep 模式扩为 `"5 配置\|5 个 AblationResult"` |
| m-8 | MINOR | checklist §1 A9 行 | 判据"可检出 B1/B3"仅映射 G2-27/G2-29, B3 无专属行 | 补 G2-44 (B 系用例全绿) |
| m-9 | MINOR | 实施 §8.2 | "含 test_04/05/06 加权混合"表述不准 (test_06 为单管道路由; 删除范围 8 用例不受影响) | 改"加权混合 test_04/05; test_06 为单管道路由" |

**备忘 (随 C-1 一并处理, 不单独计)**: checklist G2-10 期望列"仅 typing/logging/numpy/pandas/scipy 导入"不完整 (另有 optuna try-import 与 factor_pipeline 内部导入); 承重结论"无 warnings"属实, 已改注。

---

## §4 修复后状态

| 文档 | 版本 | 本步变更 |
|------|------|---------|
| 调研 | v1.1 | 尾部"步骤 8 勘误注" (m-6 计数口径 + 数值锚点复核结论); 正文无改动 |
| 设计 | **v1.2** | C-2 (4 处) / C-3 / C-4 (4 处) / m-2 / m-3 / m-4; §12 补 v1.2 修订行 |
| 实施 | **v1.2** | C-1 (3 处) / C-4 (5 处) / m-5 / m-6 / m-7 / m-9; §14 补 v1.2 修订行; 头部引用升版 |
| checklist | **v1.1** | C-1 (G4-1/G4-4) / C-4 (G4-5/A16) / m-1 (§2) / m-7 (G2-41) / m-8 (A9) / G2-10 备忘; 头部引用升版 (实施 v1.2 / 设计 v1.2); 尾部完成行 |

---

## §5 结论与放行

- 四方文档在**版本链** (v3.4.0 / `v2.3.0-cache` / ADR 待分配)、**数值锚点** (0.999998 / 0.308 / 49.5% / −37.6% / 2σ→0.4041 / 62↔T=1472)、**接口签名** (8 加 5 删字段、数据类、公式阈值链)、**TDD 契约** (20 新增 / 46 删除 / 17 改写)、**文件变更清单**与 **A1–A17 ↔ Gate 映射**上互相一致且可回源。
- 无幻觉级错误; 4 项 MAJOR + 9 项 MINOR 已全部修复并留痕 (设计 §12 v1.2 / 实施 §14 v1.2 / checklist v1.1 / 本文件 §3 / 调研尾部勘误注)。
- **放行**: 进入步骤 9 (TDD 实现)。执行顺序: Red (`tests/test_unified_routing.py` 14 例 + `tests/test_structural_break_monitor.py` 6 例, 对照 checklist Gate 1) → Green (E1–E5) → E6 清理 (符号删除 + 46 用例处置 + 4 关联文件) → E7 消融 (duckdb 可用则动态验证, 否则按 G2-43 静态核对) → 靶向回归 (Gate 3, 13 文件) → 版本/缓存/取号/CHANGELOG (Gate 4) → 性能与低效排除 (Gate 5) → 文档同步 (Gate 6) → 回填 checklist "实际"列与实施 §14。

---

**Review 完成**: 2026-11-10 (v1.0); 下一步为步骤 9 (TDD 实现)。
