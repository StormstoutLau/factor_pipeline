# 验收 Checklist：P-025 `stock_return` 百分数契约口径

---
id: p025-stock-return-unit-contract-CHECKLIST
type: design
version: 1.1
status: done
date: 2026-11-24
depends: [p025-stock-return-unit-contract-DESIGN]
upstream: null
---

> **Feature**: P-025（`stock_return` 百分数 vs `data_contract` decimal 一致性检查）
> **档位**: **T2 小流程**（DESIGN + CHECKLIST；裁剪理由见 [DESIGN.md](./DESIGN.md) 首部）
> **状态**: Step 7 产出 v1.0；Step 9 回填 §2-§7；Step 10 回填 §8；v1.1 回填全量回归 **2269 passed / 36 skipped / 0 failed**（1479.41 s）
> **包版本**: 3.11.0 → **3.11.1**

---

## 1. 文档一致性

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| C-1 | DESIGN 与代码落点一致 | DESIGN §4 列两文件 | 实际 diff 仅 `backtest/data_contract.py` + `tests/test_backtest/test_data_contract.py`（另版本 6 锚点 / CHANGELOG / 台账） | `git diff --stat` | ✅ PASS |
| C-2 | DESIGN 与测试矩阵一致 | DESIGN §3 列 T16-T19 | 四个用例名/断言可在测试文件中检索到 | `grep -n "def test_t1[6-9]"` | ✅ PASS |
| C-3 | 版本口径一致 | DESIGN 声明 3.11.1 | 6 锚点 + CHANGELOG + 版本测试全部 3.11.1 | 版本锚点 grep + 版本测试 9 passed | ✅ PASS |

---

## 2. 功能

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| F-1 | 默认 `return` 声明 percent | `FieldSpec.unit` 已存在 | `default_fields()` 中 `return.unit == "%"` | T19 | ✅ PASS |
| F-2 | percent 正常区间通过 | D2 等价界 `[-100,1000]` | `{-30,-20,-10,-5,0,5,10,20,30,100,-100,1000}` 全部 `consistency.passed` | T16 | ✅ PASS |
| F-3 | percent 脏值仍告警 | 同 D2 | `200400.0` → `consistency.passed is False`、`severity="warn"`、message 含「越界」 | T17 | ✅ PASS |
| F-4 | decimal 行为不变 | D2 回退分支 | `FieldSpec(unit=None)` 与 `unit="decimal"`：`0.2/-0.2` 通过、`20.0` warn | T18[None] / T18[decimal] | ✅ PASS |
| F-5 | 未知 unit 不抛异常 | D2 回退 decimal | `unit="ratio"` + `20.0` → warn（decimal 口径），无异常 | T19 | ✅ PASS |

---

## 3. 接口 / 兼容性

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| I-1 | `FieldSpec` schema 不变 | D1 仅补默认值 | `FieldSpec` 字段集合与签名零变更 | 读码 | ✅ PASS |
| I-2 | `CheckResult` schema 不变 | D3 details 仅 additive | `CheckResult` 五字段不变；details 追加 `unit`/`bounds` 不参与 snapshot hash | 读码 + T16-T19 | ✅ PASS |
| I-3 | 其他字段零变更 | D4 限定 `return` | `default_fields()` 其余字段 `unit` 与检查行为不变 | 读码 + 契约文件 13 passed | ✅ PASS |
| I-4 | 零新增依赖 / 3.9 语法 | 仅用既有 numpy/pandas | `git diff` 无 import 新增；Python 3.9 可导入 | `git diff` + 导入测试 | ✅ PASS |

---

## 4. 不变式

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| N-1 | INV-1 默认声明 | D1 | `return.unit == "%"` | T19 | ✅ PASS |
| N-2 | INV-2 正常/脏值判定 | D2/D5 | T16 全过 + T17 告警 | T16/T17 | ✅ PASS |
| N-3 | INV-3 decimal 逐位不变 | D2 | T18 全过；原 `[-1,10]` 判定不变 | T18 | ✅ PASS |
| N-4 | INV-4 snapshot 摘要不变 | D4 | `DataSnapshot.stable_hash()` 不含 `CheckResult.details`；面板 content_digest 不变 | 读码 + 既有缓存测试 | ✅ PASS |

---

## 5. 错误处理

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| E-1 | 空面板/全 NaN | 既有 `finite.size` 守卫 | 不抛异常、无 consistency 失败 | 读码 + 既有测试 | ✅ PASS |
| E-2 | 未知 unit | D2 回退 | 不抛 `KeyError`/`ValueError`；按 decimal 判 | T19 | ✅ PASS |

---

## 6. 性能

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| P-1 | 检查复杂度不变 | 仍为一次 `to_numpy` + `isfinite` | 无新增面板拷贝；O(n) 不变 | 读码 | ✅ PASS |
| P-2 | 契约门禁耗时无显著变化 | 真实数据根 `stock_return` 1475×5688 | 定向契约测试耗时与改前同量级 | `test_data_contract.py` 13 passed in 0.31 s；合并定向 33 passed in 17.26 s | ✅ PASS |

---

## 7. 测试与回归

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| T-1 | T16-T19 红→绿 | 先写测试 | 改前 5 failed；改后 5 passed | 定向 pytest：红 `5 failed, 8 deselected` → 绿 `5 passed, 8 deselected` | ✅ PASS |
| T-2 | 既有契约测试零回归 | TDD | `tests/test_backtest/test_data_contract.py` 全部通过 | **13 passed**（8 既有 + 5 新增） | ✅ PASS |
| T-3 | 版本测试 | 6 锚点 3.11.1 | `tests/test_fix3_version_unification.py` 9 passed | 合并定向 **33 passed**（契约 13 + 治理底座 11 + 版本 9） | ✅ PASS |
| T-4 | 全量回归 | 最终代码状态 | `pytest -q` 0 failed，passed = 基线 2264 + 新增 5 | 首跑 **2268 passed / 36 skipped / 1 failed**：`test_T396_9_force_coverage_e2e` 子进程 `read_pickle` `MemoryError`（与 P-025 无关）；隔离重跑 **1 passed in 84.80 s**；最终全量重跑 **2269 passed / 36 skipped / 0 failed**（1479.41 s） | ✅ PASS |

---

## 8. ADD 审计

| # | 项 | DoR | DoD（可观察） | 证据出口 | 结果 |
|---|---|---|---|---|---|
| A-1 | 设计→代码→测试追溯 | DESIGN §2-§3 | D1-D5 均有代码落点；T16-T19 覆盖 INV-1~4 | 本表 §2-§4 | ✅ PASS |
| A-2 | 反向核对 | diff | 每处代码改动有 CHECKLIST 项承接；无未登记改动 | `git diff` | ✅ PASS |
| A-3 | 独立只读审计 | 最终代码 | 0×P1 / 0×P2；P3 若出现登记不修 | 独立只读子代理 **PASS：0×P1 / 0×P2 / 0×P3** | ✅ PASS |

---

## 9. 回退点

- 代码：还原 `backtest/data_contract.py` 与 `tests/test_backtest/test_data_contract.py`。
- 版本：6 锚点回 3.11.0，删除 CHANGELOG v3.11.1 条目。
- 行为：移除 `return` 的 `unit="%"` 即回 decimal 口径；无缓存/数据格式变更。
