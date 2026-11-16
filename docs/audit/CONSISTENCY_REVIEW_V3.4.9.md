# CONSISTENCY REVIEW v3.4.9 — L1/L2 消融臂 trivial 判定口径

> **日期**: 2026-11-16
> **审查对象**: RESEARCH v1.0 / DESIGN v1.0 / EXECUTION v1.0 / CHECKLIST v1.0
> **方法**: 四维 (数字 / 符号 / 语义 / 引用) 两两对齐

## §1 数字一致性

| 数字 | RESEARCH | DESIGN | EXECUTION | CHECKLIST | 一致 |
|------|----------|--------|-----------|-----------|------|
| L1 结果 / 臂 | 6 / 5 (§4.2) | 6 / 5 (G1/G5) | 6 / 5 (§2) | — | ✅ |
| L2 结果 / 臂 | 2 / 2 (§4.1) | 2 / 2 (G1/G5) | 2 / 2 (§2) | — | ✅ |
| L1 trivial / 非平凡 | 1 / 4 (§4.2) | 1 / 4 (G2) | 1 / 4 (§4 E1) | 1 / 4 (B1) | ✅ |
| L2 trivial / 非平凡 | 1 / 1 (§4.1) | 1 / 1 (G2) | 1 / 1 (§4 E2) | 1 / 1 (B2) | ✅ |
| L1 退化告警条数 | — | 1 (§4.1) | 1 (§3.2) | 1 (A5/B3) | ✅ |
| 外部 B3 提示条数 | — | 2 (§4.2) | 2 (§3.2/§3.3) | 2 (A6/A8) | ✅ |
| 新增用例 | — | 7 (E1-E7) | 7 (E1-E7) | 7 (B1-B7) | ✅ |
| 既有用例更新 | 0 (F13) | 0 (§5) | 0 (§4 末) | — | ✅ |

## §2 符号一致性

| 符号 | 定义位置 | 各处使用 | 一致 |
|------|---------|---------|------|
| `_base_module_switches` | DESIGN §3.4 | EXECUTION §3.1 同名同签名 | ✅ |
| `_base_ortho_active` | DESIGN §3.4 | EXECUTION §3.1 同名同签名 | ✅ |
| `base_modules` | DESIGN §3.2 | EXECUTION §3.2 | ✅ |
| `base_ortho` | DESIGN §3.3 | EXECUTION §3.2 | ✅ |
| `degraded_arms` | — (DESIGN 未命名) | EXECUTION §3.2 局部变量 | ✅ 仅实现细节 |
| `_is_trivial` | 既有字段 | 未改名、未改语义 | ✅ |
| `module_enabled` | 既有字段 | 语义由「整体替换」改为「合并覆盖」 | ✅ 已在 G4 声明 |

> `arm_modules` (DESIGN §3.2 伪代码) 与 EXECUTION 的内联 `{**base_modules, module: False}` 为同一表达式, 不构成不一致。

## §3 语义一致性

| 语义 | 对齐结果 |
|------|---------|
| 「trivial = 与 baseline 实跑口径相同」 | RESEARCH §6 / DESIGN §1 / EXECUTION §1 表述一致 |
| 「退化 ≠ 未接线」 | DESIGN N4 明确不新增 `Wiring='default'`, 与 v3.4.7 的 `wired`/`diagnostic` 两值不冲突 |
| 「外部 B3 只提示不反推」 | RESEARCH §4.3 / DESIGN N5 / EXECUTION §3.2-§3.3 一致 |
| 「默认 base 输出零变更」 | DESIGN G1 / EXECUTION §6 / CHECKLIST A9 一致 |
| 「非默认 module_enabled 行为变更」 | DESIGN G4 + §7 风险 / EXECUTION §6 兼容性 / CHANGELOG 待写入项一致 |
| 「臂数/臂名稳定」 | DESIGN G5 / EXECUTION §2 / CHECKLIST A9 一致 |

## §4 引用一致性

| 引用 | 落点 | 状态 |
|------|------|------|
| `ablation_runner.py` L326 / L549-575 / L915-939 / L1011-1037 / L1367-1391 / L1516-1536 | RESEARCH §3 / DESIGN §3 / EXECUTION §3 | ✅ 一致 |
| `pipelines_v2.py` L492-494 / L520-522 / L801-804 / L1088-1094 | RESEARCH §3 / DESIGN §3.1 | ✅ 一致 |
| `config_v2.py` L258 `OrthogonalizationConfig` | EXECUTION §8 | ✅ 一致 |
| BH (1995) DOI 10.1111/j.2517-6161.1995.tb02031.x | RESEARCH §2 | ✅ 沿用 v3.4.8 |
| Bourgon et al. (2010) PNAS 107(21):9546-9551, DOI 10.1073/pnas.0914005107 | RESEARCH §2 | ✅ 沿用 v3.4.8 |

## §5 结论

**PASS**。四维一致; 无数字冲突、无符号漂移、无语义歧义。
唯一行为变更 (非默认 `module_enabled` 的合并语义) 已在 DESIGN G4/§7、EXECUTION §6、CHECKLIST A2 三处显式声明。

**回填 (步骤 9-10 后)**: 实现与实测 — Red 6 failed / 1 passed (E4 为防回归, 预先通过);
Green 7 passed; 4 个消融测试文件 133 passed (11.57s);
`tests/test_backtest` **588 passed / 8 skipped** (837.23s);
版本统一 7 passed + 手工 6/6;
全量回归 **1735 passed / 15 skipped / 0 failed** (1559.39s)。
上述数字与 EXECUTION §5 / CHECKLIST C1-C2 / CHANGELOG 实测矩阵一致。
