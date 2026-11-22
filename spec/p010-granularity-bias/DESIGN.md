# 设计文档：P-010 粒度偏差 — 月聚类 CI + 现状披露

---
id: p010-granularity-bias-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-22
depends: [p010-granularity-bias-RESEARCH]
upstream: [v392-calibration-unit-fix-DESIGN]
---

> **Feature**: 修正标定系数 `c` 与 `b` 的 bootstrap 推断口径（iid → 月聚类），并显式披露「股票×日」粒度限制
> **创建日期**: 2026-11-22
> **状态**: verified（Step 3-4 完成；v1.1 = Step 4 异构复审 PASS_WITH_FIXES：视角 A 锚点 14/14 + 1×P2 + 7×P3 已处置，见 §15）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.2 verified**
> **档位**: **T1**（改动 `backtest/execution/shell/` + `tests/` → Layer-1；且校准工件 `capacity_calibration.json` 的 `c` 区间语义变更，属契约变更）
> **包版本**: **3.9.8**（patch；默认工件零变更，理由见 D7）

---

## 1. 设计目标

1. **修推断**：把 `c`（以及 `b`）的 bootstrap 置信区间从 iid 行抽样改为**按月整块重采样**，使 CI 反映「月内日观测不独立」这一事实（E1：D 口径宽度 0.0242 → 0.0445，+83.8%）。
2. **不改点估计**：`c_calib_point`、`cost_by_h`、容量公式与样本粒度（股票×日）全部保持不变；E1 显示点估计差 −4.02% 未达 10% 门槛，重采样方案 B 被否决。
3. **可审计披露**：`granularity=daily`、簇数、CI 口径、iid 对照与少簇敏感性全部进入工件与报告，使读者无法把「窄 CI」误读为「高精度」。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| 月聚类 CI 宽度 +83.8%（D）/+40.8%（M），iid 显著低估不确定性 | **D2** 主 CI 改月聚类 pairs bootstrap | RESEARCH §3.4/§4.1 |
| 点估计 `|Δc|/c = 4.02% < 10%`；CV 切折差异 ±0.002% 内且行序略高 | **D6** 不采纳方案 B；不强制按月 CV | RESEARCH §4.1/§4.4 |
| 39 个时间簇属少簇区间，需报告簇数并用 t(38)/小样本修正 | **D3** group_debias 敏感性 + wild cluster bootstrap 附表 | RESEARCH §3.3（Cameron & Miller 2015；MacKinnon & Webb 2018） |
| 现行样本上限 200k、等距抽样、1.677 行/股票×月 | **D1** 月标签随样本同索引切片，禁止二次重排 | RESEARCH §3.1/§3.4 |
| `granularity="daily"` 已写入 `panel_hash` 与 meta | **D4** 保持 daily；不解除 v392 DESIGN §1.2 的 B9 非目标 | RESEARCH §3.1/§5.2 |
| 默认 `capacity_impact.json` SHA `82728CE1…` 为基线 | **D5** 默认路径零改动（不进入 `--calibrate` 分支） | RESEARCH §6.2 |
| Qlib / Zipline 用固定参数、不拟合样本 | **D4** 披露优先于重构；不引入新的成本函数形式 | RESEARCH §3.6 |

### 2.2 相关 ADR

仓内 ADR 文件未落盘（`spec/adr/` 不存在），本设计直接遵循 `SPEC_PROCESS.md` Step 4 内联的两条教训：
ADR-0001（不得为论证强度裁剪证据形态）与 ADR-0002（显式声明职责外 / 能力边界）——见 §2.3。

### 2.3 职责边界

**职责内**：`c` / `b` 的区间估计口径（重采样单位、簇数、小样本修正、敏感性附表）与披露字段。

**职责外（不回答）**：
- 不重估模型族（`sqrt/linear/log/power` 的选型与函数形式）；
- 不改变容量/成本公式与 `c_calib_stress` 的定义（`max(0.5, upper)`）；
- 不做逐笔方向冲击（BVC 数据无方向，需独立数据范式）。

**能力边界（回答不了）**：
- 39 簇下任何 CI 方法都不完美（wild bootstrap 只是缓解，不是消除）；
- 200k 等距抽样后的 bootstrap 是**固定样本内的条件推断**，不覆盖抽样本身的不确定性；
- 不做「股票×月」重采样的新旧成本曲线对照（方案 B 未采纳，见 §5.2）。

## 3. 架构设计

### 3.1 整体架构

```
panels.build()                         runner.run_calibration()
├─ _samples: (p, |impact|, σ, code, ym)   ├─ samples = panels["impact_samples"]
├─ 逐月 cap → 全局 cap（同索引切片）      ├─ c 点估计（不变）
└─ 输出 impact_samples{                ├─ _bootstrap_ci(clusters=month)   ← 新增主口径
      p, impact, sigma, month}          ├─ _bootstrap_ci()                  ← iid 对照
   + impact_samples_meta{               ├─ group_debias 宽度缩放           ← 敏感性
      cluster, n_clusters, ci}          └─ _wild_sqrt_ci()                 ← 少簇敏感性
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| [panels.py](../../backtest/execution/shell/panels.py) | 样本与月标签对齐；meta 披露 | `self._samples` | `impact_samples["month"]` + meta 三键 | `_sample_indices` |
| [runner.py](../../backtest/execution/shell/runner.py) | 聚类 bootstrap、debias、wild、`c` 块字段 | `impact_samples` | `c` / `b` 新键 + warning | numpy |
| [report.py](../../backtest/execution/shell/report.py) | Markdown 披露 | `payload["c"]` | 2 行口径说明 | 无 |
| [DESIGN.md](../v392-calibration-unit-fix/DESIGN.md) | 上游口径勘误指针 | —— | §5.2 一行 superseded 注记 | 无 |

### 3.3 数据流

1. `_month_lambda` 已把 `ym` 写入样本元组第 5 位（[panels.py L480-L483](../../backtest/execution/shell/panels.py#L480-L483)）；
2. 逐月 cap（L630-L634）现状已按索引切片元组（`ym` 天然保留）；全局 cap（L639-L641）现状经 `_stratified_sample` **丢弃 `code`/`ym`**——按 D1 改造为 `_sample_indices` + 四数组同索引切片后，`month` 与 `p/impact/sigma` 同索引对齐（F-5）；
3. `assemble_panels` 透传 `impact_samples` 全键（L830-L839），`month` 进入 `runner`；
4. `runner` 用 `np.unique(month)` 建簇索引，重采样整块，产出 CI 与敏感性字段。

### 3.4 控制流

`run_calibration` 中 `c` 分支顺序：点估计 → 聚类 CI（主）→ iid CI（对照）→ debias 缩放 → wild CI（仅 sqrt，失败记 `None` 不阻断）→ 写 `c_info`。`b` 分支沿用聚类 CI（无 iid 对照，避免字段膨胀）。

## 4. 接口定义

### 4.1 `_bootstrap_ci`（扩展，向后兼容）

```python
def _bootstrap_ci(fit_fn, p, impact, sigma, seed, n_boot=200, clusters=None):
    """样本行重采样的 5%/95% 分位。

    clusters is None -> iid 行抽样（与 v3.9.7 逐位一致）；
    clusters 为逐行簇标签 -> 按簇整块重采样（月聚类 pairs bootstrap）。
    有效重抽样 < 20 次返回 (None, None)（沿用现规则）。
    """
```

- 簇实现：`order = np.argsort(clusters, kind="stable")` 分组 → 每次 `rng.integers(0, g, size=g)` 抽簇 → `np.concatenate` 块索引 → 复用现有 `fit_fn`；
- 簇标签长度 ≠ 样本长度、或簇数 < 2 → **调用方**先判定、回退传 `clusters=None` 并登记 warning（本函数保持二元组返回契约不变，供 c/b 两个调用点复用，F-7）；
- `seed` / `n_boot` 语义不变。

### 4.2 `_wild_sqrt_ci`（新增，仅 sqrt）

```python
def _wild_sqrt_ci(p, impact, sigma, clusters, seed, n_boot=200):
    """少簇敏感性：Rademacher wild cluster bootstrap 的 c 分布分位。

    模型 c = Σx·y / Σx²，x = σ√p；簇得分 s_g = Σ_{i∈g} x_i (y_i - c x_i)；
    每次重抽 w_g ∈ {−1, +1}，c* = c + Σ_g w_g s_g / Σ x²。
    簇数 < 2 或 n_boot < 20 返回 (None, None)。
    """
```

### 4.3 `build()` 输出新增

| 键 | 类型 | 说明 |
|---|---|---|
| `impact_samples["month"]` | `np.ndarray[object]` | 逐行月份标签（`YYYY-MM`），与 `p` 等长同序 |
| `impact_samples_meta["cluster"]` | `str` | 固定 `"month"` |
| `impact_samples_meta["n_clusters"]` | `int` | `len(np.unique(month))` |
| `impact_samples_meta["ci"]` | `str` | 固定 `"month_cluster_pairs"`（与 `c_ci_method` 同 token，F-4） |

`granularity` 仍为 `"daily"`（**不**改为 `"month"`）；`panel_hash` 的 payload 与算法零改动。

### 4.4 `c` 块新增字段（`capacity_calibration.json`）

| 键 | 类型 | 说明 |
|---|---|---|
| `c_calib_lower` / `c_calib_upper` | float | **语义变更**：改为月聚类 CI（原为 iid） |
| `c_ci_method` | str | `"month_cluster_pairs"` / `"iid_fallback"` |
| `c_ci_n_clusters` | int\|null | 簇数（39）；iid 回退为 `null`（实施 F-2：回退不报簇数） |
| `c_calib_lower_iid` / `c_calib_upper_iid` | float | iid 对照（保留旧口径可追溯） |
| `c_ci_debias_lower` / `c_ci_debias_upper` | float | `点估计 ± 半宽 × sqrt(g/(g−1)·(n−1)/n)` |
| `c_ci_wild_lower` / `c_ci_wild_upper` | float\|None | wild cluster bootstrap 分位 |

`c_default` / `c_calib_point` / `c_calib_stress` 语义与计算**不变**；`c_calib_stress` 随 `upper` 变宽而单调不减（预期上升），其公式不改。

### 4.5 报告披露（`render_markdown`）

在「c 三档」表后追加（仅当键存在，向后兼容）：

```
- c CI 口径: `month_cluster_pairs`，簇数 39（iid 对照 [a, b]）
- 少簇敏感性: group_debias 宽度 ×1.0131（`sqrt(g/(g−1)·(n−1)/n)`，g=39）；wild cluster CI [lo, hi]
```

## 5. 替代方案

### 5.1 方案 C：仅换 bootstrap 口径 + 披露（**选择**）

- 描述：保留股票×日样本与点估计，`c`/`b` 的 CI 改月聚类；补 debias 与 wild 敏感性；报告与 meta 披露粒度/簇数。
- 优点：兑现 E1 唯一显著偏差（CI +83.8%）；`panel_hash` 与默认工件不变；改动集中在 `runner.py` 两个函数与 `panels.py` 一处切片。
- 缺点：CI 变宽 → `c_calib_stress` 上升，容量读数更保守；39 簇下仍不完美。
- 选择理由：RESEARCH §4.2 的 E1 倾向；满足 U-4 的机械门槛（CI 变化 >20%）。

### 5.2 方案 B：改股票×月等权重采样（**否决**）

- 描述：月内 `(p, impact, σ)` 取均值，重新拟合 c，CI 与 CV 均按月。
- 优点：与执行计划 `EXECUTION_V3.8.0` 的 `cross_val_rmse` docstring（L219，字面写「股票×月」）一致；Fama-MacBeth 式月度单位。
- 缺点：`panel_hash` 变更、`cost_by_h`/容量需全面重算并做新旧对照；加权/末值聚合算子未测（U-1 未闭合）。
- 否决理由：E1 `|Δc|/c = 4.02% < 10%` 门槛未触发（RESEARCH §4.1/§6.4 U-4）；Gormley & Matsa (2014) 提示聚合非无条件更优。

### 5.3 方案 A：保持 iid + 仅披露（**否决**）

- 描述：零代码，只在报告标注 `granularity=daily`。
- 优点：零风险、零变更。
- 缺点：CI 仍窄 83.8%，把不确定性系统性隐藏；与 Petersen (2009) 的结论直接冲突。
- 否决理由：E1 CI 宽度变化 +83.8% > 20% 修复门槛；「仅披露」不能修复推断。

### 5.4 方案 D：双向聚类（月 × 股票）（**否决，登记为备选**）

- 描述：Thompson (2011) 双向聚类或 Driscoll-Kraay。
- 优点：同时覆盖个股与时间依赖。
- 缺点：5,000 股票簇 + 39 月簇的非平衡结构；解释与实现成本高，且 E1 未显示个股维度是主要偏差来源。
- 否决理由：无证据支持第二维必需；月聚类已捕获 E1 的 +83.8%。若未来个股相关成为瓶颈，再以独立批次启动。

## 6. 数据结构

### 6.1 `impact_samples`（panels.build 输出，扩展）

```python
{
    "p": np.ndarray[float],       # 参与率（clip 1e-6..1.0）
    "impact": np.ndarray[float],  # |ret_day|
    "sigma": np.ndarray[float],   # 月内日收益标准差（clip）
    "month": np.ndarray[object],  # 新增：YYYY-MM，逐行对齐
}
```

### 6.2 `c_info`（runner 输出，扩展）

```python
{
    "c_default": 0.5,
    "c_calib_point": float,
    "c_calib_lower": float,        # 月聚类
    "c_calib_upper": float,
    "c_calib_stress": float,       # max(0.5, upper)，公式不变
    "c_ci_method": str,
    "c_ci_n_clusters": int,
    "c_calib_lower_iid": float,
    "c_calib_upper_iid": float,
    "c_ci_debias_lower": float,
    "c_ci_debias_upper": float,
    "c_ci_wild_lower": float | None,
    "c_ci_wild_upper": float | None,
}
```

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---|---|---|
| `impact_samples` 无 `month` 键（合成面板/旧工件） | 主 CI 回退 iid；`c_ci_method="iid_fallback"` | warning `c_ci_fallback_iid: 样本缺少月簇标签` |
| `month` 长度 ≠ 样本长度 | 同上回退，不抛异常 | 同上（含长度差） |
| 簇数 < 2 | 同上回退 | warning `c_ci_fallback_iid: 簇数 < 2` |
| 有效重抽样 < 20 | 沿用现规则：CI = (point, point) | warning `c 的 bootstrap CI 不足 20 次有效重抽样` |
| wild 计算异常（NaN/空簇） | `c_ci_wild_* = None`，不阻断 | warning `c_ci_wild_unavailable` |
| `b` 分支同样缺簇标签 | `b` CI 回退 iid | 不新增 warning（避免噪声），字段语义同 `c_ci_method` 已披露 |

## 8. 不变式（Invariants）

1. **INV-1**：默认路径（不传 `--calibrate`）的 `out/capacity_impact.json` SHA256 仍为 `82728CE1…`，逐位不变。
2. **INV-2**：`clusters=None` 时 `_bootstrap_ci` 与 v3.9.7 逐位一致（同 `seed`/`n_boot`）——合成 panels 的旧测试无需改期望。
3. **INV-3**：`len(month) == len(p) == len(impact) == len(sigma)`，且 `set(month) ⊆ set(panel.months)`（等式在正常 39 月全样本下成立；某月全部股票缺 ADV/λ 样本时允许真子集，F-3）。
4. **INV-4**：`impact_samples_meta.granularity == "daily"`；`panel_hash` 输入的 `granularity` 仍为 `"daily"`（B9 非目标未解除）。
5. **INV-5**：`c_ci_n_clusters == len(np.unique(month))`；报告中的簇数与该字段同源。
6. **INV-6**：`c` 块只增键不改键名；`c_default` / `c_calib_point` / `c_calib_stress` 的公式与语义不变。

## 9. 幻觉抑制审查（Step 4 Review，自检）

### 9.1 设计基于已验证的调研结论

- [x] 全部设计决策可追溯到 RESEARCH v1.2（§2.1 表逐条映射）
- [x] 无未经验证的假设（CI 幅度、点估计差、CV 差异均引 E1 读数）
- [x] 无论证驱动的归因扭曲：未把「CI 变宽」简化为单一原因，明确区分「月内相关」与「cap 抽样」两种机制（§2.3 能力边界）

### 9.2 替代方案审查

- [x] 列出 4 个方案（C 选择；A/B/D 否决），每个有否决理由
- [x] 每个否决理由绑定 E1 或文献锚点，而非偏好

### 9.3 职责边界审查

- [x] 区分职责外（模型族/成本公式/逐笔）与能力边界（39 簇、条件推断）
- [x] 不越界吞并「股票×月重采样」的研究范式

> 本节勾选为设计者自检；Step 4 异构复审结论见 §15（PASS_WITH_FIXES，已闭环）。

## 10. 对实施的输入

### 10.1 关键工程约束

- 只改 `panels.py` 的 cap 切片（L639-L641 附近）与 `runner.py` 的 CI 函数；`core/` 零改动；
- `_stratified_sample` 仅一个调用点（panels L640），改为 `_sample_indices` + 四元组同索引切片后删除，防止「重排导致标签错位」；
- 不得在 `panel_hash` payload 中新增键；
- 所有新字段经 `_jsonable` 输出；`None` 必须落为 `null` 而非 `NaN`；
- 报告行只在字段存在时渲染，保证旧工件可读。

### 10.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| CI 变宽 → 报告值 `c_calib_stress` 上升（E1：2.9213 → 2.9349），可能被误读为「回归」；**容量读数不变**（容量由 `c_effective`（点估计/回退 0.5）驱动、不消费 CI——F-1 复审证实） | 报告双列（主 CI + iid 对照）；CHANGELOG 写明「`c_calib_stress` 为报告值变化，`c_effective` 与容量读数不变，非模型变更」 |
| 39 簇下 CI 仍不稳健 | debias + wild 两档敏感性同表输出；报告注明簇数 |
| 200k 等距抽样使簇内行数不均（1.677 行/股月） | 在设计/报告中声明为条件推断；不宣称覆盖抽样不确定性 |
| 合成 panels 缺 `month` 静默回退 iid | 强制 warning + 测试断言 `c_ci_method` |
| 下游按位置解析 `c` 表 | 只增字段；`render_markdown` 的表头与 5 行不变 |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**

- **U-1 月度聚合算子** —— **关闭（不适用）**
  - 判据：已判定——不采纳方案 B，故不需要定义月内聚合算子
  - 触发条件：若未来启动方案 B（月度重采样），立即重开，并补测「均值 / 成交额加权 / 末值」三口径
  - 当前倾向：不做
  - 证据等级：E1（RESEARCH §6.4 U-4 判定，F-6）
- **U-2 默认路径影响** —— **关闭**
  - 判据：INV-1 在 Step 9 以 SHA 实测验证
  - 触发条件：若 Step 9 出现 `capacity_impact.json` SHA 变化 → 停止并定位
  - 当前倾向：零变更
  - 证据等级：E1（SHA 基线 `82728CE1…`）
- **U-3 聚类口径** —— **关闭**
  - 判据：主口径 = 月聚类 pairs bootstrap；debias 与 wild 为敏感性；簇数 39 入工件
  - 触发条件：若生产 39 月读数与 E1 偏差 > 5%（CI 端点），复审聚类实现
  - 当前倾向：见 D2/D3
  - 证据等级：E1（探针）+ T1（官方文档）
- **U-4 采纳门槛** —— **关闭（已判定）**
  - 判据：`|Δc|/c = 4.02% < 10%` → 不采纳 B；CI 宽度 `+83.8% > 20%` → 采纳 C
  - 触发条件：已触发并判定
  - 当前倾向：C + A 披露
  - 证据等级：E1

**11.2 决策矩阵**：不启用（本批为 Type-2 可逆改动 + U-4 已完成机械判定；无不可逆选择）。

## 12. 测试矩阵（供 Step 9 TDD 预注册）

| # | 用例 | 断言 |
|---|---|---|
| TP10-1 | 10 簇 × 20 行、簇内强相关 | 聚类 CI 宽度 > iid CI 宽度（同 seed） |
| TP10-2 | 合成 panels 无 `month` | `c_ci_method=="iid_fallback"`；CI 与 v3.9.7 期望逐位一致；warning 存在 |
| TP10-3 | 同 seed 两次调用 | 聚类 CI 逐位可重放 |
| TP10-4 | 39 月合成标签 | `c_ci_n_clusters == 39`，且 == `len(unique(month))` |
| TP10-5 | `build()` meta | `cluster=="month"`、`n_clusters>0`、`ci=="month_cluster_pairs"`、`granularity=="daily"` |
| TP10-6 | 默认路径 | `capacity_impact.json` SHA = `82728CE1…`（E1 重放） |
| TP10-7 | debias 缩放 | 宽度 = 聚类宽度 × `sqrt(g/(g−1)·(n−1)/n)`（数值断言，容差 1e-12） |
| TP10-8 | wild CI | 有限且包含点估计；簇数 < 2 时为 `None` |
| TP10-9 | 报告渲染 | markdown 含 `month_cluster_pairs` 与簇数；旧 payload（无新键）不报错 |
| TP10-10 | 真实 39 月（needs_minutes） | `--calibrate` 输出新字段齐全；`data_alignment`/`panel_hash` 与 v3.9.7 一致 |

## 13. 版本与落点（D7）

包版本 **3.9.7 → 3.9.8**，共 7 个落点：`pyproject.toml:7`、`__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、`tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`、`CHANGELOG.md` 顶部新条目。

**patch 级理由**：只改 `--calibrate` 分支的 CI 语义与披露字段；默认工件、`panel_hash`、容量公式、公开函数签名（`_bootstrap_ci` 为新增可选参数）均不变。

## 14. 回滚

代码回退到 `v3.9.7` 标签即可；本批不迁移数据、不删除字段、不改配置默认值。新字段对旧工件读者无害（只增）。

## 15. Step 4 异构复审记录（2026-11-22）

**复审方式**：双视角异构——视角 A 逐条锚点核查（DESIGN 引用的代码行/API/数值 vs 仓内现状，Grep/Read/数值复算复验）；视角 B 可实施性与正确性（决策映射真实签名、公式推导复算、不变式可测性）。发现登记于本节，修正以 v1.0 → v1.1 落盘。

### 15.1 视角 A：锚点核查（14/14 PASS）

| # | 锚点 | 复验结果 |
|---|---|---|
| A1 | 样本元组 5 元含 `ym`（panels L480-L483） | ✅ `(p, \|impact\|, sigma_d, code, ym)` |
| A2 | 逐月 cap 元组级切片（L630-L634） | ✅ `ym` 保留 |
| A3 | 全局 cap 现状（L636-L641） | ✅ `_stratified_sample` 仅提取 3 数组——证实 §3.3 原措辞不准确（F-5） |
| A4 | `assemble_panels` 逐键透传（L830-L839） | ✅ 新键 `month` 无需改动 |
| A5 | `_bootstrap_ci` 现签名与 rng 顺序（runner L161-L176） | ✅ `clusters=None` 走原代码路径 → INV-2 成立 |
| A6 | `c_triplet` stress 公式（L92-L99） | ✅ `max(0.5, upper)` |
| A7 | c/b 两调用点消费二元组（L486-L488 / L509-L511） | ✅ 支持 F-7（契约不变） |
| A8 | `SqrtImpact.fit` 公式（impact.py） | ✅ `x=σ√p`、`c=Σxy/Σx²`——§4.2 wild 推导与实现一致 |
| A9 | report.py c 表键（L57-L58） | ✅ 固定 5 键循环，新增披露走 §4.5 行 |
| A10 | 版本 7 落点均现值 3.9.7 | ✅ pyproject L7 / `__init__` L58 / config_v2 L371 / reporting L40 / 两处测试锚点 |
| A11 | 合成 panels 无 `month`（test_execution_capacity L179-L182） | ✅ INV-2「旧测试免改期望」成立 |
| A12 | `_jsonable`（runner L179-L190） | ✅ None 透传、NaN→null |
| A13 | `c_calib_stress` 消费面（全仓 grep） | ✅ 仅 runner 定义/回退（L99/L461）+ report 打印（L58）+ 单元测试；capacity 由 `c_effective` 驱动（L499）——证实 F-1 |
| A14 | 默认 SHA 基线 `82728CE1…` | ✅ 既有批次基线（v3.9.2 T8 / P-008 INV-1） |

### 15.2 视角 B：发现与修正（1×P2 + 7×P3，均已落 v1.1）

| # | 级别 | 发现 | 修正 |
|---|---|---|---|
| F-1 | P2 | §10.2 R1「CI 变宽 → 容量读数下调」为归因错误：容量由 `c_effective`（ident=False→0.5）驱动、不消费 CI；仅报告值 `c_calib_stress` 上升（E1 复算：2.9213 → 2.9349） | R1 重写：明确容量读数不变，CHANGELOG 指引改为 stress 报告值口径 |
| F-2 | P3 | debias 因子误写 ×1.0132；复算 `sqrt(39/38 × (n−1)/n)`（g=39、n=200031）= **1.01307** → 应为 ×1.0131 | §4.5 改 ×1.0131 并附公式 |
| F-3 | P3 | INV-3 `set(month) == set(panel.months)` 过强：某月全部股票缺 ADV/λ 样本时为真子集 | 改为 `⊆` + 边界注明 |
| F-4 | P3 | §4.3 `meta["ci"]="month_pairs_bootstrap"` 与 §4.4 `c_ci_method="month_cluster_pairs"` 命名不一致（Step 8 术语一致风险） | 统一为 `month_cluster_pairs`（§4.3 + TP10-5） |
| F-5 | P3 | §3.3 第 2 点把「全局 cap 同索引切片」写成现状——现状经 `_stratified_sample` 丢弃 `code`/`ym` | 补注现状与 D1 改造点 |
| F-6 | P3 | §11.1 U-1 证据引用误写 RESEARCH §3.4（U-4 实际位于 §6.4） | 改 §6.4 |
| F-7 | P3 | §4.1 fallback「返回 iid 结果并写 warning」与二元组契约表述含糊（b 分支复用需明确） | 明确 fallback 判定在调用方、函数保持二元组返回 |
| F-8 | P3 | 复审记录插入为第二个 §12，与「§12 测试矩阵」编号冲突 | 本节改编号 §15，全部引用（header/§9/PROGRESS）同步 |

### 15.3 Step 4 Review 清单

- [x] 设计基于已验证的调研结论（§2.1 逐条映射 RESEARCH v1.2）
- [x] 无未经验证的假设（CI/Δc/CV 均引 E1 读数；debias 因子数值复算 1.01307）
- [x] 无论证驱动的归因扭曲（F-1 即此类风险——容量影响被夸大表述，已修正）
- [x] 替代方案 ≥2 且被否决（A/B/D 均附 E1/文献绑定理由）
- [x] 职责边界清晰（§2.3 区分职责外与能力边界）

### 15.4 结论

**PASS_WITH_FIXES（已闭环）**——视角 A 锚点 14/14；视角 B 8 项发现（1×P2 + 7×P3）全部修正。门禁复核：RESEARCH v1.2 无 FALSIFIED/CONFLICT 未决项、关键断言双源（E1 探针 + T1 文献）、无携带假设。进入 Step 5-6。

---

**Review 签字**: _________ 日期: _________
