# CONSISTENCY REVIEW v3.4.8 — 消融臂 trivial 判定口径

> **日期**: 2026-11-15
> **审查对象**: RESEARCH v1.1 / DESIGN v1.1 / EXECUTION v1.1 / CHECKLIST v1.0
> **方法**: 四维 (数字 / 符号 / 语义 / 引用) 两两对齐

## §1 数字一致性

| 数字 | RESEARCH | DESIGN | EXECUTION | CHECKLIST | 一致 |
|------|----------|--------|-----------|-----------|------|
| L4 臂总数 | 8 | 8 | 8 | — | ✅ |
| 无市值 trivial / 非平凡 | 3 / 5 (推论) | 3 / 5 (G2) | 3 / 5 (A1) | 3 / 5 (B1/B2) | ✅ |
| 有市值 trivial / 非平凡 | — | 2 / 6 (G1) | 2 / 6 (A2) | 2 / 6 (B1/B2 对照) | ✅ |
| 结果总数 (B3 + 臂) | — | 9 | 9 | — | ✅ |
| 退化告警条数 | — | 1 (G5) | 1 (A3) | 1 (A4/B5) | ✅ |
| 新增用例 | — | 5 (E1-E5 中 3 例可自动化 + 2 例覆盖既有) | 4 (T1-T4) | 4 (B4-B6 + B8) | ✅ 见 §3 说明 |
| 既有用例更新 | — | 1 (R1) | 3 (E2) | 3 (B1-B3) | ⚠️ 已对齐见 §4 |

## §2 符号一致性

| 符号 | 定义位置 | 各处使用 | 一致 |
|------|---------|---------|------|
| `market_cap_available` | EXECUTION §3.1 | DESIGN §4.1 (`market_cap_available`) | ✅ |
| `effective_option` | DESIGN §4.1 / EXECUTION §3.1 | 两处同名 | ✅ |
| `_is_trivial` | RESEARCH §3 / DESIGN §2 | 未改名、未改语义 | ✅ |
| `_wiring_status` | 未被本版触碰 | EXECUTION §3.3 明示不动 | ✅ |
| `industry+mktcap` | 臂名原值 | DESIGN G4 / EXECUTION A5 | ✅ |

## §3 语义一致性

| 语义 | 对齐结果 |
|------|---------|
| 「trivial = 与 baseline 实跑口径相同」 | RESEARCH §3 / DESIGN §1 / EXECUTION §3.1 表述一致 |
| 「退化 ≠ 未接线」 | RESEARCH §5 处置方向; DESIGN 未把该臂标 `diagnostic` (仅 trivial), 与 v3.4.7 `_wiring_status` 语义不冲突 |
| 「臂集合稳定」 | DESIGN 方案 B 否决理由 (9→8 漂移) 与 EXECUTION §2 兼容性 (臂数 9) 一致 |
| 「生产零改动」 | DESIGN G3 / EXECUTION §0 / §2 / CHECKLIST A7 一致 |

**§1 新增用例数差异说明**: DESIGN §4.3 列出 E1-E5 五个测试点, 其中 E1/E2 合并为 T1 (同一次调用可同时断言), E3→T2, E4/E5 合并为 T3, 故落地为 3 个测试函数; 覆盖面无缺失。

## §4 引用一致性

| 引用 | 落点 | 状态 |
|------|------|------|
| `ablation_runner.py` L1098-1101 / L1129-1133 / L1137 / L1145-L1149 / L1339-L1364 | RESEARCH §3 / DESIGN §1 / EXECUTION §3 | ✅ 一致 |
| `pipelines_v2.py` L1431-L1440 | RESEARCH §3 / DESIGN §1 | ✅ 一致 |
| BH (1995) DOI 10.1111/j.2517-6161.1995.tb02031.x | RESEARCH §2 | ✅ |
| Bourgon et al. (2010) PNAS 107(21):9546-9551, DOI 10.1073/pnas.0914005107 | RESEARCH §2 | ✅ |
| v3.4.7 审计 P2-1 | EXECUTION 上游 (间接) | ✅ 与审计 §6 原条目一致 |

## §5 结论

**PASS**。四维一致; 唯一需要说明的是「DESIGN 测试点 5 项 → 落地 4 个测试函数」的合并关系, 已在 §3 记录, 不构成不一致。

**回填 (步骤 9-10 + 独立复审后)**: 实现与实测 — Red 5 failed / 107 passed; Green 112 passed;
T4 于独立复审后追加 (外部 B3 口径提示分支), 3 个消融测试文件复跑 113 passed;
定向回归 580 passed / 8 skipped; 版本统一 7 passed + 手工 6/6;
全量回归数字见 CHECKLIST C2 (复审后复跑)。
上述数字与 EXECUTION §5 / CHECKLIST C1-C2 / CHANGELOG 实测矩阵一致。
