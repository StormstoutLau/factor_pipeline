# 设计文档：v3.9.4 审计遗留修复 + 覆盖度口径收口（批次 A）

---
id: v394-audit-coverage-fix-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v394-audit-coverage-fix-RESEARCH]
upstream: null
---

> **Feature**: 批次 A「口径收口包」——P-012（F-1~F-6）+ P-004（覆盖度交集口径）+ P-005（强制放行留痕）
> **创建日期**: 2026-11-20
> **状态**: verified（Step 4 异构复审 PASS_WITH_FIXES；S1-S9 修复已落盘，见 §12）
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md) **v1.1 verified**
> **包版本**: 3.9.4
> **批次档位**: **T1**（改动命中 `backtest/` + `scripts/` + `tests/`，无架构级决策；与 v3.9.2 同档）

---

## 1. 设计目标

在**不改默认路径输出**的前提下，消除 v3.9.3 审计遗留的 6 项实现-文档落差，并把覆盖度指标从「分子分母异源」改为「交集口径」，同时让 `--force-coverage` 的放行行为在校准工件中留痕。本批不改变任何研究结论（`phi` / `m` / `net` 点估计口径不变）。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---------|---------|------|
| F-1：回退分支 `net` lo/hi 缺 `h_m/h`，与 `point`/`m` 三条路径并存 | **D1**：回退区间改用 m 形式 `aum·A(h_m)·(m ∓ t·m_se) − cost`，复用 `scale`/`m_se` | RESEARCH §3.1 |
| F-1′：`n_bootstrap=50` 可稳定进入回退分支 | **D2**：单测以 `n_bootstrap=50` 触发，不 monkeypatch | RESEARCH §3.1 |
| F-2：通过线 2065 为 collected 数 | **D3**：v3.9.3 IMPLEMENTATION §5 改为 `≥2057 passed / 15 skipped / 0 failed` + 恒等式注记 | RESEARCH §3.2 |
| F-3：`phi_status` 缺 `prior` | **D4**：v3.9.3 DESIGN 升 v1.2，枚举补 `"prior"`（L222/L278 + §7 行） | RESEARCH §3.2 |
| F-4：`DecayCurve` 零调用方 | **D5**：**内部接线**——`assemble_decay_curve` 构造 `DecayCurve` 并由其字段组装 payload | RESEARCH §6.1 |
| F-5：D5 plateau 无落点 | **D6**：payload 的 `net[h]` 增 `sd`，顶层增 `plateau`（仅校准工件；默认 `plateau()` 不动） | RESEARCH §3.2 |
| F-6：退化态仍跑敏感性 | **D7**：`m_sensitivity` 加 `if not degenerate` 守卫，退化态输出 `{}` | RESEARCH §3.2 |
| P-004：ratio 分子分母异源；`panel_hash` 不含 counts | **D8**：仅在 ratio 层做交集（`|M∩U|/|U|`），`counts` 保持原值，新增 `ratio_raw` 披露；`panel_hash` 不动 | RESEARCH §3.3 |
| P-005：强制放行仅 stdout；合并通道已存在 | **D9**：token 化文案 `coverage_gate_forced: …` 追加进 `minute["evidence_warnings"]`，复用既有合并通道 | RESEARCH §3.4 |
| U-1：交集后阈值可能失效 | **D10**：阈值**维持 0.95 / 0.90 不放宽**；首跑失败 → 留痕 + 登记定标项（U-6），不在本批静默调整 | RESEARCH §6.4 |
| R-1：`stock_median` 同源 `counts` | **D11**：`counts` 语义冻结（仍为分钟 uniq 码数），交接集仅在 ratio 装配处 | RESEARCH §8.2 |

### 2.2 相关 ADR

| ADR | 决策 | 对本设计的影响 |
|-----|------|--------------|
| ADR-0001（论证驱动） | 禁止无证据归因 | 每条决策绑定 RESEARCH 锚点；阈值不放宽即此原则 |
| ADR-0002（职责边界） | 明确职责内/外 | `coverage_gate` 保持纯函数（只判定），「强制放行」属调用方策略 → 放 script 层 |

### 2.3 职责边界

- **职责内**：校准分支的净收益区间、覆盖度指标、放行留痕、审计遗留的文档同步；
- **职责外**：默认回测路径（零改动）、成本口径重构（P-003）、样本粒度（P-010）、阈值定标本体（U-6）、外部文献。

## 3. 架构设计

### 3.1 变更面

```
scripts/verify_capacity_impact.py ──(force 留痕)──► minute["evidence_warnings"]
        │                                              │
        ├─► panels.coverage_gate（语义不变，输入 ratio 已改交集）
        └─► runner.assemble_decay_curve
                 ├─ net 区间（F-1 修）  ├─ DecayCurve 接线（F-4）
                 ├─ net.sd / plateau（F-5） ├─ 退化守卫（F-6）
```

- `backtest/execution/core/decay.py` **零改动**（复用既有 `DecayCurve` / `plateau`）→ `__all__` 恒为 5 项；
- 默认路径（`run_calibration` 之外）**零改动**。

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|------|------|------|------|------|
| `shell/panels.py::MinutePanelBuilder._coverage` | 覆盖度装配（交集 ratio + 原值披露） | `counts`、日频域码集 | `PanelCoverage` | 新增 `_universe_codes` |
| `shell/panels.py::force_coverage_warning` | 放行留痕文案（纯函数） | gate messages | token 字符串 | — |
| `shell/panels.py::coverage_gate` | 门禁判定 | `coverage` dict（交集 ratio） | `(ok, messages)` | 不改 |
| `shell/runner.py::assemble_decay_curve` | 曲线装配 | panels | payload（含 sd/plateau） | `DecayCurve` / `plateau` |
| `scripts/verify_capacity_impact.py` | 放行策略落点 | `args.force_coverage` | `minute` 警告 | 上述 helper |

### 3.3 数据流

1. 分钟聚合产出每月 `codes`（既有 `_month_codes`，int64 ndarray）→ `counts[ym]`（分钟 uniq 码数，语义冻结 D11）
2. 新增 `_universe_codes(ym)`：日频域行 → 归一化整数集 `U`
3. `ratio[ym] = |codes ∩ U| / |U|`；`ratio_raw[ym] = counts[ym] / |U|`（原式，可 >1）
4. `PanelCoverage.as_dict` 输出两键（新增 `ratio_raw`）；`coverage_gate` 只读 `universe_ratio`
5. 校准 payload：`net[h].sd` 由 bootstrap 重采样 `net_b` 的样本标准差（ddof=1）；`plateau` = `[max(point)−sd(h*), max(point)]` 内的 h 集合

### 3.4 控制流

`--calibrate` → builder.build → `coverage_gate` →（失败且 force：追加 token 警告）→ `assemble_panels` → `run_calibration` → `assemble_decay_curve` → `write_decay_curve`。

## 4. 接口定义

### 4.1 F-1 回退区间（runner.py L316-321 替换）

```python
            # net 区间复用 m 的缩放（scale = A(h_m)·h/h_m），与 point 同一条代数路径
            base_net = float(aum) * float(a_mean[hm])
            net_out[str(h)] = {
                "point": float(point[h]),
                "lo": float(base_net * (m_point[h] - t_crit * m_se)
                            - cost_by_h[h]),
                "hi": float(base_net * (m_point[h] + t_crit * m_se)
                            - cost_by_h[h])}
```

- `m_se` 为 NaN 时 `lo/hi` 自动 NaN（无需额外守卫，与 `m_out` 一致）；
- 数值等价：`base_net·m = aum·A(h)·h_m/h`。

### 4.2 P-004 覆盖度（panels.py）

```python
    def _universe_codes(self, ym):
        """日频可投资域码集（int 归一，与 _adv_lookup 同款）。"""
        row = self._month_row(self.daily.universe, ym) if self.daily else None
        if row is None:
            return set()
        keep = np.asarray(row.fillna(False).to_numpy(), dtype=bool)
        names = row.index[keep]
        codes = set()
        for key in names:
            try:
                codes.add(int(str(key)))
            except (TypeError, ValueError):
                continue
        return codes

    def _universe_count(self, ym):        # 改为 len(_universe_codes)，单一真相源
        return len(self._universe_codes(ym))

    def _coverage(self, usable, partial, missing, counts, locks):
        ratio, raw = {}, {}
        for ym in usable:
            universe = self._universe_codes(ym)
            denom = len(universe)
            if denom <= 0:
                ratio[ym] = None
                raw[ym] = None
                continue
            codes = set(int(c) for c in self._month_codes.get(ym, ()))
            ratio[ym] = float(len(codes & universe)) / float(denom)
            raw[ym] = float(counts[ym]) / float(denom)
        ...
        return PanelCoverage(..., universe_ratio=ratio, ratio_raw=raw, ...)
```

注（复审 S3/S7）：`_month_codes` 实为 int64 ndarray（非 list），`set(int(c) for c in ...)` 已兼容；`keep` 的 bool 归一与现行 `_universe_count`（panels.py L238-239 `np.asarray(..., dtype=bool)`）同款。列跳过（不可 int 归一）使交集分母可能小于旧口径的原始列数——有意收窄，经 U-5 抽样确认，披露见 §7。`counts` 语义不变（D11）。

### 4.3 P-005 留痕（panels.py 新增 + script 调用）

```python
def force_coverage_warning(messages):
    """--force-coverage 放行留痕文案（token 化，便于 grep 与断言）。"""
    return "coverage_gate_forced: " + "; ".join(str(m) for m in messages)
```

```python
                if not args.force_coverage:
                    return 2
                minute.setdefault("evidence_warnings", []).append(
                    force_coverage_warning(messages))
                print('[coverage] --force-coverage：门禁失败放行（留痕）')
```

### 4.4 F-5 payload 增量

```jsonc
"net": {"5": {"point": 0, "lo": 0, "hi": 0, "sd": 0}, ...},
"plateau": [5, 10, 20]
```

- `sd`：`nanstd(net_b, ddof=1)`；bootstrap 不可用（回退/退化）→ `NaN`；
- `plateau`：`net.sd` 在 `h*` 处有限时用 `decay.plateau(point_map, sd_h*)`，否则 `[]`；
- 既有键 `point/lo/hi` 不动；md 渲染忽略新键的依据：`scripts/verify_capacity_impact.py` 的 md 渲染逐键取 `point/lo/hi`（L483-488），不枚举未知键（复审 S5）。

## 5. 替代方案

### 5.1 方案 A（选择）：`DecayCurve` 内部接线

- 描述：`assemble_decay_curve` 计算完成后构造 `DecayCurve(...)`，再由其字段组装 payload；
- 优点：兑现 v3.9.3 DESIGN §3.2 契约；类型化中间态；零行为变化；
- 缺点：多一层构造（~8 行）；
- 选择理由：删除会使 DESIGN §3.2/§6 同时失真，改动面反而更大。

### 5.2 方案 B（否决）：删除 `DecayCurve`

- 优点：净减代码；
- 否决理由：需同步改 DESIGN 两处 + T393-7 符号表，文档返工大于实现收益。

### 5.3 方案 C（否决）：P-004 改分母（并集/分钟码数）

- 优点：读数不下移；
- 否决理由：覆盖率失去「域内覆盖」语义，任何值都可通过，等于取消门禁（RESEARCH §4.2）。

### 5.4 方案 D（否决）：`ratio_raw` 进入 md 报告

- 优点：人工可读；
- 否决理由：报告口径膨胀且需同步 R7 脚注；JSON 披露已满足可追溯性。

### 5.5 方案 E（否决）：保留 `DecayCurve` 现状 + DESIGN 标注为外部消费类型

RESEARCH §6.1 F-4 选项③。

- 否决理由（Step 8 F-B）：死类型零构造零消费，标注不能消除断言落差；接线（方案 A）/删除（方案 B）二选一，选 A 接线。

## 6. 数据结构

### 6.1 `PanelCoverage` 增量（panels.py L51-70）

```python
from dataclasses import dataclass, field   # panels.py L10 现仅 import dataclass（复审 S4）

@dataclass
class PanelCoverage:                        # 非 frozen，与现行 L50 一致（复审 S1）
    ...
    universe_ratio: dict
    ratio_raw: dict = field(default_factory=dict)   # v3.9.4：原式披露（可 >1）
```

- 字段置于末尾并带默认值 → 既有构造点（含测试）零改动；
- 序列化走既有 `as_dict`（panels.py L63-71；`coverage_gate` L651-652 以 `hasattr(cov, "as_dict")` 消费）→ 增 `"ratio_raw"`（str 键）（复审 S1）。

### 6.2 payload 增量

见 §4.4。`DecayCurve` 本身**不加字段**（sd/plateau 属报告层，非曲线本体）。

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---------|---------|------------|
| 日频域为空 / 无法归一（含全部列键不可 int 归一） | `ratio=raw=None`；`_universe_count=0`（与既有语义一致） | 门禁「覆盖度未产出」 |
| 域列键不可 int 归一 | 跳过该列（不抛）；分母因此可能小于旧口径的原始列数（有意收窄） | 无（U-5 抽样确认） |
| bootstrap 异常（回退分支） | `net.sd=NaN`、`plateau=[]` | 既有 `decay_ci_analytic_fallback` |
| 退化态 | `net` 三值 NaN + `sd` NaN + `plateau=[]` + `m_sensitivity={}` | `decay_curve_unidentified` |
| `n_bootstrap<100` | 回退分支（设计行为，不新增警告） | 既有回退警告 |
| gate 失败且未 force | `return 2` | 既有 messages |

## 8. 不变式（Invariants）

1. **INV-1** 默认 `out/capacity_impact.json` SHA 逐位不变（`82728CE1…`）；
2. **INV-2** `panel_hash` 输入键域不变，P-004 前后逐位相同 **[单源-待二核]**（hash payload 静态读码为单源，RESEARCH §8.4 B-2；第二源动作见 §10.3 改码前后备份对比）；
3. **INV-3** `universe_ratio ≤ 1` 恒成立，且 `ratio_raw ≥ universe_ratio`（同分母、交集 ≤ 分子）；
4. **INV-4** `stock_median` 仍基于原始 `counts`（不受交集影响）；
5. **INV-5** `net.point ∈ [lo, hi]`（B-1 修复后，含回退分支）；
6. **INV-6** 退化态：`m_sensitivity == {}`、`net.*` 全 NaN、`verdict=unidentified`；
7. **INV-7** `net[h].sd` 有限 ⟹ bootstrap 主路径可用（单向，复审 S6；反向不成立——主路径下个别 h 列全 NaN 时 sd=NaN，由 plateau 守卫兜底）；
8. **INV-8** `core/decay.py` 零改动、`__all__` 5 项、零新增依赖、Python 3.9。

## 9. 幻觉抑制审查（Step 4）

### 9.1 设计基于已验证的调研结论

- [x] 全部 11 条决策绑定 RESEARCH 锚点（§2.1）；
- [x] 无未验证假设（U-5/U-6 显式登记）；
- [x] 归因未经扭曲：D10 明确「阈值不放宽」而非「阈值有效」。

### 9.2 替代方案审查

- [x] §5 列 4 条替代（F-4 ×2、P-004 ×1、md 披露 ×1）（Step 8 F-B 勘误：原误计）；
- [x] 每条有否决理由；RESEARCH §6.1 F-4 选项③经 §5.5 否决。

### 9.3 职责边界审查

- [x] `coverage_gate` 保持纯判定；策略在 script；
- [x] 不吞并 P-003/P-010（成本与粒度口径）职责。

## 10. 对实施的输入

### 10.1 变更白名单

| 文件 | 动作 |
|------|------|
| `backtest/execution/shell/panels.py` | `_universe_codes` + `_universe_count` 改单一真相源 + `_coverage` 交集 + `PanelCoverage.ratio_raw` + `force_coverage_warning` |
| `backtest/execution/shell/runner.py` | F-1 区间、F-5 `sd`/`plateau`、F-6 守卫、F-4 `DecayCurve` 接线 |
| `scripts/verify_capacity_impact.py` | force 分支追加 token 警告 |
| `tests/test_execution_decay.py` | T394-1~T394-4 |
| `tests/test_minute_panels.py` | T394-5 + 更新 T381-17 期望（新口径） |
| `tests/test_execution_capacity.py` | T394-6（source-contract） |
| `spec/v393-alpha-decay-model/DESIGN.md` | 升 v1.2 增量勘误（L222/L278 枚举、L120 D5 注、L289/§7） |
| `spec/v393-alpha-decay-model/IMPLEMENTATION.md` | §5 通过线勘误（F-2） |
| `CHANGELOG.md` / `README*.md` / `docs/PROJECT_STATUS.md` / `docs/PROGRESS.md` | Step 9 同步 |

**不在白名单**：`core/decay.py`、`shell/report.py`、`loaders.py`、`out/*`、配置字段。

### 10.2 测试清单（先红后绿）

| 编号 | 断言 | 前置（红） |
|------|------|-----------|
| T394-1 | `n_bootstrap=50` → 回退分支 `point∈[lo,hi]`，且 `lo/hi` 与 m 形式独立复算一致 | 现实现 lo/hi 缺因子 → 断言失败 |
| T394-2 | 退化 panels + `n_bootstrap=50` → `m_sensitivity == {}`、不抛异常 | 现实现执行循环 → 空/NaN 项 |
| T394-3 | monkeypatch `core.decay.DecayCurve` 为 spy → 调用 1 次 | 现实现从不构造 → 0 次 |
| T394-4 | bootstrap 正常 → `net[h].sd` 有限、`plateau` 含 `argmax_h`、`plateau ⊆ horizons` | 现 payload 无 sd/plateau → KeyError |
| T394-5 | stub self 调 `_coverage`：3 只分钟码 / 2 只域（含 1 只非分钟码）→ `ratio=0.5`、`raw=1.5`、`stock_median` 不变 | 现实现 `ratio=1.5` 且无 `ratio_raw` |
| T394-6 | `force_coverage_warning` 文案 + 脚本源码含 `force_coverage_warning(messages)` 于 force 分支（source-contract：读 `scripts/verify_capacity_impact.py` 源码文本断言；复审 S8——不类比 G8，直接读源码） | 现 script 无该调用 |
| T394-7 | 同一输入两次 `builder.build()` → `panel_hash` 相同；且 hash payload 无 coverage 键 | 现实现已满足（回归护栏，**非红**） |
| T394-8 | `PanelCoverage(...)` 旧构造（无 `ratio_raw`）仍可用；`as_dict()` 含 `ratio_raw` | 现无该字段 → 失败 |

### 10.3 基线与验收

- 全量：`2057 + N passed / 15 skipped / 0 failed`（N = 新增数）；
- 默认 SHA `82728CE1…` 三方一致（跑前备份 / 跑后 / 复跑）；
- P-004 改码前备份 39 月 `panel_hash` → 改码后逐位对比相同（INV-2 第二源，E1，复审 S2）；
- 39 月校准重跑：`universe_ratio` 中位/最差、`ratio_raw`、门禁结果、`--force-coverage` 留痕一次到位。

## 11. 未决项

- **U-6 交集口径下门禁阈值的定标（U-1 收敛）**
  - **判据**：39 月交集 ratio 分布与 (0.95, 0.90) 的关系有实测表格；若触发失败，已留痕并登记新 P 行
  - **触发条件**：Step 9 校准重跑返回非 0 或 messages 非空
  - **当前倾向**：维持阈值（D10）；失败即留痕上报，不在本批调整
  - **证据等级**：待核（E1）

- **U-5 日频域列键格式**（继承 RESEARCH）
  - **判据**：抽样 ≥3 个月日频 universe 列键，int 归一化率 100%；不可归一列数登记
  - **触发条件**：`_universe_codes` 的 try/except 归一化失败命中，或 Step 9 抽样发现非 int 键
  - **当前倾向**：跳过不可归一列（§7 披露分母收窄）；若大量不可归一则升级为口径问题上报
  - **证据等级**：待核（E1，Step 9 抽样）

（决策矩阵不启用：本批均可逆 Type-2，无不可逆多方案选择。）

---

## 12. 异构复审记录（Step 4）

### 12.1 复审方式与输入

- **复审方式**：独立子代理（RULE-5），仅输入 RESEARCH v1.1 verified + DESIGN v1.0 draft + 源码锚点清单，不携带主会话推理链；
- **代码基线**: 源码 @ `a0cf914`；
- **复审范围**：全量 11 条决策、接口定义（§4）、数据结构（§6）、错误处理（§7）、不变式（§8）、实施输入（§10）、未决项（§11）。

### 12.2 结论

**PASS_WITH_FIXES**：1×P1 + 2×P2 + 6×P3；维度 V1/V2 PASS，V3/V4/V5 PASS_WITH_FIXES；门禁 c fail → S2/S6 修复后 pass。全部修复已落盘至本版（v1.1）。

### 12.3 维度矩阵

| 维度 | 结论 | 关键依据 |
|------|------|---------|
| V1 决策与调研一致性 | PASS | 11 条决策均绑定 RESEARCH 锚点，无漂移、无越权归因 |
| V2 架构与职责边界 | PASS | `coverage_gate` 纯判定、策略落 script 层；默认路径零改动成立 |
| V3 接口可实现性 | PASS_WITH_FIXES | S1（frozen/to_dict 错描）修复后可实现 |
| V4 测试清单可执行性 | PASS_WITH_FIXES | S8（T394-6 失锚）+ T394-8 接口名修复后可执行 |
| V5 不变式与验收可核性 | PASS_WITH_FIXES | S2（单源标记+第二源）与 S6（INV-7 单向）修复后闭合 |

### 12.4 发现与处置（全部已落盘至 v1.1）

| 编号 | 级别 | 位置 | 发现 | 处置 |
|------|------|------|------|------|
| S1 | P1 | §6.1/§3.3/§10.2 | 接口错描：写为 `@dataclass(frozen=True)` 与 `to_dict`；真实为非 frozen（panels.py L50）+ `as_dict`（L63-71）——按原文实施 T394-8 必 AttributeError | §6.1 改非 frozen + `as_dict`；§3.3 第 4 条、§10.2 T394-8 同步 |
| S2 | P2 | §8 INV-2/§10.3 | INV-2 未携带 RESEARCH §8.4 的 [单源-待二核] 标记，且无第二源动作 | INV-2 补标记；§10.3 增改码前后 `panel_hash` 备份对比 |
| S3 | P2 | §4.2/§7 | `keep` 缺 bool 归一（现行 L238-239 有 `np.asarray(..., dtype=bool)`）；列跳过使交集分母可能小于旧口径未披露 | §4.2 keep 归一 + 尾注；§7 两行披露 |
| S4 | P3 | §6.1 | `field` import 未明示（panels.py L10 仅 `import dataclass`） | §6.1 import 行明示 |
| S5 | P3 | §4.4 | 「md 渲染忽略新键」依据未限定 | 限定为 script md 渲染逐键取 point/lo/hi（L483-488） |
| S6 | P3 | §8 INV-7 | 「sd 有限 ⟺ 主路径可用」双向过强（主路径下全 NaN 列 sd=NaN） | 改单向 ⟹ + plateau 守卫说明 |
| S7 | P3 | §3.3/§4.2 | §3.3 第 1 条「`nan` →」开头残缺；`_month_codes` 实为 int64 ndarray 非 list | 第 1 条改写；§4.2 尾注 |
| S8 | P3 | §10.2 T394-6 | 「G8 同类」类比失锚 | 改为直接读 script 源码文本断言 |
| S9 | P3 | §11 U-5 | 非完整四元块（缺判据/触发条件/证据等级） | 补全四元块 |

### 12.5 门禁

| 门禁 | 结论 |
|------|------|
| a. 白名单改动 ↔ 决策一一对应 | pass |
| b. 全部测试条目有红前置（T394-7 显式标非红） | pass |
| c. 不变式无双向过强、无未溯源声明 | fail（S2/S6）→ 修复后 **pass** |
| d. 硬约束贯穿（Python 3.9 / 零新增依赖 / `core/decay.py` 零改动 / 默认 SHA） | pass |

### 12.6 复审边界

- 复审子代理声明未核验 §10.1「更新 T381-17 期望」的存在性 → 主会话已补核验：**T381-17 真实存在**（test_minute_panels.py L461 断言 2023-03 单月覆盖度 ≥0.90、L463 经 `as_dict` 取值、L464 断言 `universe_ratio["2023-03"] >= 0.90`），L297/L307 的 stub 直接传入 ratio dict、不受交集改动影响 → §10.1 该行**有效，无需修改**；
- U-5（列键格式）与 U-6（阈值定标）显式带入 Step 9，不在本批裁决；
- 本复审不改任何研究结论（`phi` / `m` / `net` 点估计口径不变）。

---

**Review 签字**: _________ 日期: _________
