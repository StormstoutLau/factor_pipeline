# 设计：P-025 `stock_return` 百分数契约口径

---
id: p025-stock-return-unit-contract-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [p024-ledger-contract-cleanup-SESSION]
upstream: null
---

> **Feature**: P-025（`stock_return` 百分数 vs `data_contract` decimal 一致性检查）
> **档位**: **T2 小流程**（Layer-1 可逆小补；先例 P-016，DESIGN + CHECKLIST 两件套）
> **裁剪理由**: 单点 warn 级一致性检查 + 测试；不新增 / 删除接口，不改 schema / 门禁判据，不改真值源定义；`FieldSpec.unit` 字段已存在，仅补默认声明与检查分支。若后续发现需要改变 `CheckResult` schema 或门禁严重度，升级 T1。
> **包版本**: 3.11.0 → **3.11.1**（patch：修正 `return` 字段的 warn 口径）
> **新依赖**: 无

---

## 1. 问题与 E1 证据

### 1.1 现状

`stock_return.pkl` 是**百分数**日收益（`10` 表示 +10%），但 `backtest/data_contract.py` 的 `return` 一致性检查按 **decimal** 口径 `[-1, 10]` 判断。

| 锚点 | 事实 |
|---|---|
| [data_contract.py L74](../../backtest/data_contract.py#L74) | `FieldSpec.unit: Optional[str] = None` 已存在，但 `return` 默认字段未声明 |
| [data_contract.py L250](../../backtest/data_contract.py#L250) | `FieldSpec("return", "stock_return.pkl", ..., semantic_type="return", expected_missing_tail=1)` |
| [data_contract.py L657-L671](../../backtest/data_contract.py#L657-L671) | `_consistency_check` 固定 `finite.min() < -1.0 or finite.max() > 10.0` |
| [data_contract.py L870](../../backtest/data_contract.py#L870) | 该检查随 `check_data_contract` 的字段循环执行 |
| [scripts/contract_gate.py L36-L43](../../scripts/contract_gate.py#L36-L43) | 研究入口使用 `default_fields()`，因此真实数据根会读入 `stock_return.pkl` |

### 1.2 E1 实测（2026-11-24，`E:\Ashare_data\market_data\stock_return.pkl`）

| 读数 | 值 |
|---|---|
| 形状 | 1475 × 5688 |
| 有限格 | 7,204,340 |
| min / max | **−96.4431 / 200,400.0** |
| 分位（0.1 / 1 / 50 / 99 / 99.9） | −14.3352 / −8.4286 / 0 / 10.0125 / 20.0072 |
| 按 decimal `[-1,10]` 越界 | **2,305,246**（<−1）+ **81,972**（>10）= **2,387,218** 格（占有限格 **33.1%**） |
| 按 percent `[-100,1000]` 越界 | **0**（<−100）+ **15**（>1000）= **15** 格 |
| 补充 | >30% 为 2,262 格、>100% 为 683 格；这些落在 percent 等价界内，属粗粒度 sanity 检查的有意容忍范围 |

来源：[P-021 RESEARCH §3.3](../p021-tradability-production-enablement/RESEARCH.md#L108-L128)（形状/百分数口径）；[决策锚点 §3.2](../../docs/research/RESEARCH_TRADABILITY_DECISION_ANCHORS.md#L129)（百分数与 decimal 冲突的原始发现）。

**判读**：decimal 口径会对约 1/3 的正常百分数收益产生 warn（含创业板/科创板 ±20%、北交所 ±30%），同时对 15 个 >1000% 的脏值仍能告警。修复方向明确：**按 `unit` 选择等价区间**。

---

## 2. 决策（D1-D5）

| # | 决策 | 说明 |
|---|---|---|
| **D1** | 默认 `return` 字段声明 `unit="%"` | 只改 `default_fields()` 中 `return` 一行；`FieldSpec.unit` 已存在，无 schema 变更 |
| **D2** | `_consistency_check` 按 `unit` 选界 | `"%"` → `[-100.0, 1000.0]`；`None` / `"decimal"` → `[-1.0, 10.0]`（保持原行为）；其他未知 unit → 回退 decimal 并在 details 记录 unit，不抛异常 |
| **D3** | 消息与 details | 消息显示有效区间；`details` 在保留 `field` 的基础上追加 `unit` 与 `bounds`（additive；不参与 snapshot hash） |
| **D4** | 严重度与范围 | 保持 `warn`；不改其他字段、其他检查、freshness/coverage/PIT 逻辑；不改 reader 与面板内容 |
| **D5** | 边界语义 | percent 界由 decimal 界 ×100 得到：`-1 × 100 = -100`、`10 × 100 = 1000`。边界值本身通过（`<=` / `>=`），仅越界才 warn |

### 2.1 被拒备选

| 方案 | 描述 | 裁决 |
|---|---|---|
| A | 在 reader 中把 `stock_return` 除以 100 转 decimal | 否决：会改变缓存内容摘要与字段语义，且其他消费方可能仍期望百分数 |
| B | 删除 `return` 一致性检查 | 否决：丢失对 200400% 级脏值的唯一粗粒度告警 |
| C | 仅文档披露，不改检查 | 否决：真实数据根约 33.1% 有限格持续误告警，`contract_gate` 报告不可用 |

### 2.2 不变式（INV）

- **INV-1**：`default_fields()` 中 `return` 的 `unit == "%"`。
- **INV-2**：percent 口径下，正常 A 股日收益（含 ±20% / ±30%）与边界值 `[-100, 1000]` 通过；`200400` 必须 warn。
- **INV-3**：decimal / `None` unit 的自定义 `FieldSpec` 行为逐位不变（原 `[-1,10]` 判定）。
- **INV-4**：其他字段与其他检查零变更；report / snapshot 的字段摘要不因本改动变化（`details` 不参与 `DataSnapshot.stable_hash()`）。
- **INV-5**：零新增运行时依赖；Python ≥3.9 语法；包版本 **3.11.1** + 6 锚点 + CHANGELOG。

---

## 3. 测试矩阵（T16-T19）

| 用例 | 输入 | 断言 |
|---|---|---|
| **T16 percent 正常区间** | `FieldSpec(..., unit="%")`，值 `{-30, -20, -10, -5, 0, 5, 10, 20, 30, 100, -100, 1000}` | `consistency` 全部 passed；无「越界」warn |
| **T17 percent 脏值** | 同上 + `200400.0` | `consistency` failed、severity=`warn`、message 含「越界」；details `unit="%"`、`bounds=[-100,1000]` |
| **T18 decimal 兼容** | `FieldSpec(..., unit=None)` 与 `unit="decimal"`，值 `{0.2, -0.2, 20.0}` | `0.2/-0.2` 通过；`20.0` warn（>10）；与改前行为一致 |
| **T19 默认字段/未知 unit** | `default_fields()` 的 `return`；`unit="ratio"` 的自定义字段 | `return.unit == "%"`；未知 unit 回退 decimal（`20.0` warn），不抛异常 |

文件名：`tests/test_backtest/test_data_contract.py`（追加，不改既有用例）。

---

## 4. 实施落点

| 文件 | 改动 |
|---|---|
| `backtest/data_contract.py` | `default_fields()` 的 `return` 加 `unit="%"`；`_consistency_check` 按 unit 选界并补 details |
| `tests/test_backtest/test_data_contract.py` | 追加 T16-T19 |
| `pyproject.toml` / `__init__.py` / `config_v2.py` / `reporting.py` / 两个版本测试 | 3.11.0 → **3.11.1** |
| `CHANGELOG.md` | v3.11.1 条目 |
| `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` | P-025 → done；路线图/当前版本刷新 |

---

## 5. 回退点

- 代码回退：还原 `backtest/data_contract.py` 与 `tests/test_backtest/test_data_contract.py` 两文件；版本 6 锚点回 3.11.0；删除 CHANGELOG v3.11.1 条目。
- 行为回退：`return` 字段去掉 `unit="%"` 即回到 decimal 口径；无数据写入、无缓存格式变更。
