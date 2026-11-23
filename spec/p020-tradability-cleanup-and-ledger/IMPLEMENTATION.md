# 实施文档：P-020 tradability 小口径收尾 + 台账同步

---
id: p020-tradability-cleanup-and-ledger-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-23
depends: [p020-tradability-cleanup-and-ledger-DESIGN, p020-tradability-cleanup-and-ledger-RESEARCH]
upstream: null
---

> **Feature**: P-020（A 台账同步 + B 三项小口径收尾）
> **创建日期**: 2026-11-23
> **状态**: verified（Step 5-9 完成；Step 9 读数见 §7）
> **Spec 步骤**: Step 5-6（+§7 Step 9 回填）
> **基于设计**: [DESIGN.md](./DESIGN.md)
> **档位**: **T1** ｜ **包版本**: 3.9.9 → **3.9.10** ｜ **新依赖**: 无

---

## 1. 实施概述

两处生产代码改动集中在**单文件** `backtest/tradability_inputs.py`：D1（eps 取源改为 policy）与 D2（`_norm_code` 归一化 + 精确优先回退）。D3/D4 只加测试。D5/D6 是版本与台账。`backtest/tradability.py`、`backtest/engine.py`、`TradabilityInputs` 字段集合**零改动**。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|---|---|---|---|
| 语言 | Python | 3.9+（仓内约束） | ✅ 既有 |
| 依赖 | numpy / pandas / pytest | 现有版本 | ✅ 不新增 |
| 版本字段 | `pyproject.toml` | 3.9.10 | ✅ 本批写入 |

### 2.2 依赖版本验证（Step 6）

| 依赖 | 声明版本 | 核验 | 结论 |
|---|---|---|---|
| numpy / pandas / pytest | 既有锁文件 | 本批未新增、未改约束 | ✅ 无需外部查询 |
| `TradabilityPolicy` | 仓内类（`tradability.py:194-199`） | 读源码确认字段 `eps: float = _EPS` | ✅ 可实例化 |

**结论**：零新增依赖 → 依赖版本存在性核验 **N/A（理由：无新增）**。

### 2.3 文件结构（改动面）

```
backtest/tradability_inputs.py     # 生产：D1 + D2（唯一生产文件）
tests/test_tradability.py          # 测试：T020-1 / T020-2
tests/test_tradability_inputs.py   # 测试：T020-3 / T020-4 / T020-5
pyproject.toml                     # 3.9.10（L7）
__init__.py                        # 3.9.10（L58）
config_v2.py                       # 3.9.10（L371）
reporting.py                       # 3.9.10（L40）
tests/test_fix3_version_unification.py   # EXPECTED_VERSION（L34）
tests/test_backtest/verify_fix3_manual.py# EXPECTED_VERSION（L21）
CHANGELOG.md                       # 顶部新条目
docs/PROJECT_STATUS.md             # D6 台账
docs/PROGRESS.md                   # P-020 done
spec/p020-tradability-cleanup-and-ledger/*.md
```

## 3. 模块实施

### 3.1 `_norm_code`（新增，D2）

```python
def _norm_code(code):
    """代码键归一：剥离交易所后缀并补齐 6 位。"""
    return str(code).split(".")[0].zfill(6)
```

- 实施要点：纯字符串函数，无 IO、无异常分支（`str(None)` → `"None"` 也不抛）。
- 复用：`st_overrides` 的两处内联表达式替换为 `_norm_code`（**行为等价**，`str(c).split(".")[0].zfill(6)` 逐字相同）。
- 低效排除：不建 DataFrame、不 `iterrows` 新增；归一化映射仅 O(K) 一次构建。

### 3.2 `build_tradability_inputs`（D1 + D2）

#### 接口签名（不变）

```python
def build_tradability_inputs(close, high, low, open_, volume, suspend, name,
                             adj, list_date=None, policy=None,
                             st_overrides=None):
```

#### 实施要点

1. **D1**：
   ```python
   from .tradability import (TradabilityInputs, TradabilityPolicy, board_of,
                             compute_limits, _pct_matrix, _ref_from_adj)
   ...
   eps = (policy if policy is not None else TradabilityPolicy()).eps
   ```
   `_EPS` 从导入列表移除（构建器不再直接引用常量）。`inputs.policy` **仍写原 `policy`**（可为 None）。
2. **D2**：
   ```python
   ld = pd.Series(list_date)
   norm = {}
   for k, v in ld.items():
       norm.setdefault(_norm_code(k), v)      # 首见优先
   for j, code in enumerate(columns):
       if code in ld.index:                   # 精确优先（INV-4）
           value = ld.loc[code]
       else:
           nk = _norm_code(code)
           if nk not in norm:                 # 缺失判定与取值为两步，避免 None 值误判
               continue
           value = norm[nk]
       ...
   ```
   注意：缺失判定用 `nk not in norm` 而非 `norm.get(nk) is None`（后者会把合法的 `None` 值误当缺失）；`NaN` 值仍由既有 `pd.isna(value)` 分支跳过。
3. **回退点**：整文件单独 revert 即可回到 v3.9.9；无跨文件耦合。
4. **低效排除表**：

| 潜在低效 | 排除措施 |
|---|---|
| 每列重建归一化键 | `norm` 只建一次 |
| 归一化映射覆盖精确键 | 精确优先分支先返回，映射只兜底 |
| 新增 pandas 逐行操作 | 仍为 `for j in range(N)`，与 v3.9.9 同阶 |

### 3.3 测试实施（T020-1a ~ T020-6）

| 用例 | 文件 | 构造 | 断言 | 预期红/绿 |
|---|---|---|---|---|
| **T020-1a** | `tests/test_tradability.py` | `_case(T=2,N=1)`：仅 t=1 `high=low=11.0`（一字涨停，prev=10） | `one_word_up==1` 且 `one_word_down==0` | 绿（覆盖既有行为） |
| **T020-1b** | 同上 | `_case(T=2,N=1)`：prev=10、仅 t=1 `high=low=9.0`（一字跌停） | `one_word_down==1` 且 `one_word_up==0` | 绿（覆盖既有行为） |
| **T020-2** | 同上 | `adj=None`，直接传 `ref=np.array([[nan],[5.0]])`，`prev_close=10`，t=1 `high=5.50/low=4.50`，`target_w[1]=0.5` | `blocked_buy==1`、`limit_unknown==0`、`eff[1]==0`（与 `test_tp6_6` 经 adj 派生**同结果**） | 绿（覆盖既有行为） |
| **T020-3** | `tests/test_tradability_inputs.py` | 列 `600000.SH`，`close[0]=10`、t=1 `high=low=11.000000005`（与涨停价差 5e-9）；分别用 `policy=None` 与 `TradabilityPolicy(eps=0.0)` 构建 | 默认 `one_word_up_cells==1`；`eps=0.0` 时 **==0** | **红 → 绿** |
| **T020-4** | 同上 | 列名**裸代码** `["600000","000001"]`，`list_date` 索引**带后缀** `["600000.SH","000001.SZ"]`（值为 dates[2] / dates[3]） | `no_limit_source=="list_date"`；列 0 `no_limit[2:7].all()` 且 `no_limit[7]` 为假；列 1 `no_limit[3:8].all()` | **红 → 绿** |
| **T020-5** | 同上 | `list_date` 用 **dict 且「600000」先插入**（dates[3]）、「600000.SH」后插入（dates[0]），列名 `"600000.SH"` | 精确命中 → 豁免从 dates[0] 起（`no_limit[0]` 为真）；若实现误用「归一化优先」会取到 dates[3] → 该断言失败 | 绿（INV-4 护栏；按构造**具备判别力**，设计上非红） |
| **T020-6** | 同上 | 列名**整数裸代码** `[600000]`，`list_date` dict 同时含 `"600000"`（dates[2]）与 `"600000.SH"`（dates[5]） | `no_limit[2:7].all()`、`no_limit[5]` 仍为真（首见优先 = dates[2]） | 绿（覆盖 `_norm_code` 整数键 + 归一化映射「首见优先」） |

> **T020-1 拆分为两个单事件用例**：`report` 只有聚合计数、无逐日明细，「同报告不串扰」不可直接断言；单事件用例下 `up==1/down==0`（及反向）即可证明方向未翻转（Step 6 复审 P2-1 处置）。

## 4. 接口实施与回退点

| 接口 | 变更 | 回退点 |
|---|---|---|
| `_norm_code(code)` | 新增私有函数 | 删除函数 + 恢复内联 |
| `build_tradability_inputs(...)` | 签名不变；内部两处逻辑 | 单文件 revert |
| `TradabilityInputs` | 无 | — |
| `apply_tradability(...)` | 无 | — |
| `FactorBacktestEngine.__init__` | 无 | — |

## 5. 版本与文档落点（D5/D6）

### 5.1 版本 3.9.10 落 7 处

`pyproject.toml:7` / `__init__.py:58` / `config_v2.py:371` / `reporting.py:40` / `tests/test_fix3_version_unification.py:34` / `tests/test_backtest/verify_fix3_manual.py:21` / `CHANGELOG.md` 顶部。

核验命令：`Grep "3\.9\.9"`（排除 `spec/` 历史文档）应 0 命中；`Grep "3\.9\.10"` 应命中上述 6 个代码/配置锚点 + CHANGELOG。

### 5.2 CHANGELOG 必含三要点

1. eps 单源（meta 计数随 `policy.eps` 变化——**启用态行为变更，显式披露**）；
2. `list_date` 键归一化（**启用态行为变更**：此前静默跳过的 IPO 豁免现在生效）；
3. `ref=` 直传用例 + 一字板正/负向计数用例（测试有效性）。

### 5.3 台账（A）

- `PROJECT_STATUS.md` §1：v3.9.9 行（P-006）+ 本批发布后 v3.9.10 行；指针移到 v3.9.10。
- `PROJECT_STATUS.md` §2：`P2 =（无）`；`P3 = P-009 / P-018 / P-020`。
- `PROGRESS.md`：P-020 → `done`（附四件套链接 + 验收读数）。

## 6. Step 6 独立复审记录

- 方式：独立只读子代理（`general-purpose`，仅读 DESIGN/IMPLEMENTATION + `tradability_inputs.py`），要求只出裁决。
- 结论：**PASS_WITH_FIXES**（0×P1 / 2×P2 / 2×P3）；默认路径经复审核安全（精确键命中与 eps 默认值行为均不变）。
  - **P2-1**（已处置）：T020-1 原设计想断言「同一报告内上下方向不串扰」，但 `report` 只有聚合计数、无逐日明细 → 不可达。**改为 T020-1a / T020-1b 两个单事件用例**（见 §3.3）。
  - **P2-2**（已处置）：§3.2 伪代码仍写 `norm.get(...) is None`，与 `not in norm` 的定稿写法矛盾 → 已同步为 `nk not in norm` + `norm[nk]`。
  - **P3-1**（已处置）：T020-5 未指定 dict 插入顺序，若「带后缀键」先插入则错误实现也能通过 → 已改为「裸代码先插入」以恢复判别力。
  - **P3-2**（已处置）：§7 红→绿仍为占位符而 front-matter 标 verified → 本文件状态先置 `draft`，Step 9 回填后升 `verified`。

## 7. Step 9 TDD 记录

- **红**（先写测试，未改生产代码）：`python -m pytest -q tests/test_tradability.py tests/test_tradability_inputs.py -k t020` → **2 failed / 4 passed / 32 deselected**；失败项 = `test_t020_3_one_word_eps_follows_policy`（`eps=0.0` 仍计 1）与 `test_t020_4_list_date_key_normalized`（`no_limit_source` 仍 `delisting_only`）。
- **绿**（改生产代码后）：同一命令 **7 passed / 32 deselected**（含审计后补测的 T020-6；补测前读数为 6 passed）；定向套件（+ TP6-11 + 版本测试）**49 passed, 3.77 s**。
- **逐例覆盖缺口**：T020-6 为审计后补测（覆盖 `_norm_code` 整数键 + 归一映射首见优先），按构造直接绿，属覆盖补强而非红→绿。
- 全量回归读数见 [CHECKLIST.md](./CHECKLIST.md) §10.2。

---

**Review 签字**: Step 6 独立只读复审（PASS_WITH_FIXES，见 §6） 日期: 2026-11-23
