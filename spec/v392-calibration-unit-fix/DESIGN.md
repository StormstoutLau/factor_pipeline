# DESIGN v3.9.2 — 校准读数口径一致性修复（c σ / rho 频率 / temporary 标注）

---
id: v392-calibration-unit-fix-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v392-calibration-unit-fix-RESEARCH]
upstream: null
---

> **版本**: v1.1 (2026-11-20；步骤 4 复审修正 5 项，见 §19)
> **批次**: v3.9.2（P2 校准读数诊断的修复批次）
> **对应调研**: [RESEARCH.md](./RESEARCH.md) **v1.1**（§9 步骤 2 复审 PASS_WITH_FIXES）
> **上游约束**: DESIGN_EXECUTION_CAPACITY_V3.8.0 §5.1/§7/§10；EXECUTION_V3.8.0 §2.4/§2.5/§2.8
> **产出定位**: 只修「读数口径」；不重估模型族、不改默认输出、不实现截面 T+1 reversal
> **实施归**: 步骤 9（TDD，先红后绿）

---

## §1 目标与非目标

### 1.1 目标

| # | 目标 | 对应调研裁决 |
|---|------|-------------|
| G1 | `impact_samples` 的 σ 与 impact 同为**日频尺度**，消除 `c≈15` 的量纲放大 | §4.1 |
| G2 | `sqrt` 拟合增加过原点 `R²`，`c` 不可识别时**显式回退默认 0.5**，禁止伪精确 | §4.1 / §5.2 |
| G3 | `rho` 改用**日频组合超额**估计，`rho<=0` 回退 1.0 并留痕，消除符号翻转 | §4.2 |
| G4 | `temporary_share` 明确标注为**组合 AR(1) 代理**，不进入容量 | §4.3 |
| G5 | 默认 `out/capacity_impact.json` SHA256 逐位不变 | §5.4 |

### 1.2 非目标（明确不做）

- 不改变 `SqrtImpact/LinearImpact/LogImpact/PowerImpact` 的 `fit/predict` 签名与端口契约；
- 不引入带截距/符号冲击回归（方案 C，v3.9.3+）；
- 不把样本粒度从「股票×日」改为「股票×月」（登记为 B9 遗留）；
  > **P-010 勘误（v3.9.8，2026-11-23）**：该非目标经 E1 39 月探针复核后**维持**（点估计差 −4.02% < 10%）；月聚类 CI 已落地为方案 C，见 [spec/p010-granularity-bias/DESIGN.md](../p010-granularity-bias/DESIGN.md) D6。
- 不实现截面 T+1 reversal（B11，后续批次）；
- 不动 `loaders.py` 的 `MinuteAggregate/σ` 语义（BVC 分类仍需分钟 σ）。

---

## §2 关键决策与替代方案

### D1 σ 同尺度（G1）

**决策**：在 `MinutePanelBuilder._month_lambda` 内，对每只股票用当月 `ret_day` 序列计算
`sigma_d = std(ret_day, ddof=1)`，clip 到 `cfg.sigma_clip`，作为该股所有样本行的 σ。

**理由**：`y=|ret_day|` 是日收益；`x=σ·sqrt(p)` 必须与 y 同尺度，c 才无量纲。
分钟 bar σ 只服务 BVC 分类（EXECUTION §2.4 的 `日内收益标准差`），不进入冲击拟合。

**被拒替代**：
- 保留 bar σ、把 c 改名为 `c_bar`：否——仍驱动成本，业务读数继续失真；
- 用市值/行业波动代理：否——引入新依赖与不可复现口径。

**边界**：有效天数 `<2` 或 `std==0` 时仍走 clip 下界 0.005（不丢样本），并计入现有告警口径。

### D2 c 识别门槛（G2）

**决策**：
1. 新增纯函数 `fit_r2(pred, y)`（过原点拟合的 `1 − SSE/SST`，`SST==0` 返回 0.0）；
2. `_fit_impact` 与 `runner` 对 `sqrt` 输出 `r2`；
3. 判定 `c_identifiable = (r2 >= 0.05) and (0.1 <= c <= 2.0)`；
4. `build_daily_panels` 在 `identifiable=False` 时用 `c_default=0.5` 计算 `impact_bps`/`cost_by_h`，
   并写 `evidence_warnings`；`c_calib_*` 仍原值报告（标 `[区间]`）；
5. `runner` 用同一 `fit_r2 / C_R2_MIN / C_RANGE` 计算 `c_identifiable` 与 `c_effective`，
   与 panels 的门控结果必须一致（测试 T7 断言）。

**理由**：即使 σ 修正，过原点拟合仍会把 `|r|` 的噪声底折进 c（调研 §4.1 第 3 点）；
门槛是「不得用不可识别参数驱动容量」的最小守卫。

**被拒替代**：
- 去掉 c 不报告：否——丢失诊断信息；
- 给 `SqrtImpact.fit` 加截距：否——破坏四模型同构与端口签名，且需重做 CV 口径（v3.9.3）。

**阈值来源**：`R²>=0.05` 与 `c∈[0.1,2.0]` 为本设计自定守卫（非文献结论），
覆盖设计默认 `c=0.5` 与历史敏感性区间 `{0.1,0.5,1.0}`；报告必须写明「自定阈值」。

### D3 rho 日频 + 非正守卫（G3）

**决策**：
1. `build_daily_panels` 用 `excess_d`（日频组合超额）估计 rho；
2. `rho_series` 改存日频序列，新增 `rho_freq="daily"` 与 `rho_n`；
3. `rho<=0` → 置 1.0，写 `evidence_warnings`「rho<=0，按无衰减处理」；
4. `excess_d` 不足 3 点 → 1.0 + 告警（沿用现有异常路径）。

**理由**：DESIGN §7 明确日频；`h` 是交易日，月频 rho 代入即单位错配；
`rho<=0` 无经济含义（alpha 不可能是负保留率），与「CI 覆盖 1 → 无衰减」同向回退。

**被拒替代**：
- 保留月频 rho、把 h 换算成月：否——与 `cost(h)` 的交易日口径冲突，且偏离设计原文；
- `rho<=0` 时输出 `None` 并清空 net：否——会让报告字段消失，破坏下游对账；回退 1.0 更保守可解释。

**文档裁决**：v3.8.1 调研 §6 U3「建议组合月超额 AR(1)」**被本设计废止**，以 DESIGN §7 日频为准；
该冲突在 §19 复审记录留痕。

### D4 temporary 降级标注（G4）

**决策**：
1. 保留现有数值计算（不改 `temporary_share` 函数）；
2. `build_daily_panels` 增加 `temporary_basis="portfolio_ar1_proxy"`，并写
   `evidence_warnings`「temporary_share 为组合日超额 AR(1) 代理，非 T+1 反转，不进入容量」；
3. `runner` 结果透传 `temporary_basis`。

**理由**：算法本身无算术错误，错在「测的对象」；本批用元数据阻断误读，
真正的截面实现需要新输入契约（股票级收益 + 交易方向），列入 v3.9.3。

**被拒替代**：
- 直接输出 `None`：否——下游字段缺失、报告崩坏风险；
- 在 panels 里用日频价格硬造截面反转：否——无交易方向，属伪实现。

### D5 版本与默认路径（G5）

- 包版本 3.9.1 → **3.9.2**（6 处代码锚点 + CHANGELOG，共 7 个落点：`pyproject.toml:7`、
  根 `__init__.py:58`、`config_v2.py:371`、`reporting.py:40`、
  `tests/test_fix3_version_unification.py:34`、`tests/test_backtest/verify_fix3_manual.py:21`、
  `CHANGELOG.md` 顶部新条目）；
- 全部改动只作用于 `--calibrate` 分支；默认路径不构造面板（脚本 L428 门控，调研 §9.1 P5）。

---

## §3 接口与签名（实施前锁定）

### 3.1 新增纯函数（`core/impact.py`）

```python
C_R2_MIN = 0.05
C_RANGE = (0.1, 2.0)

def fit_r2(pred, y):
    """过原点拟合的 R² = 1 - SSE/SST；SST==0 -> 0.0。"""
```

- 入参 1 维、等长、有限；非有限时按 0.0 返回；
- 加入 `__all__`，不进入端口；
- `panels._fit_impact` 与 `runner` 共用同一对常量，禁止各自硬编码。

### 3.2 `panels._fit_impact` 返回字段（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| `r2` | float | 主模型（仅 sqrt 时）的过原点 R²；其他模型为 `None` |
| `identifiable` | bool | 仅 sqrt 有意义；非 sqrt 恒 `True`（本批不设门槛） |

### 3.3 `build_daily_panels` 新增输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `rho_freq` | str | 固定 `"daily"` |
| `rho_n` | int | 日频样本数 |
| `temporary_basis` | str | `"portfolio_ar1_proxy"` |
| `impact_bps_source` | str | `"calibrated"` / `"default_fallback"` |

### 3.4 `runner.run_calibration` 输出（校准 JSON）

- `models.sqrt.r2: float|None`；
- `c` 块新增 `c_identifiable: bool`、`c_effective: float`（回退后实际使用值）、`c_r2`；
- 顶层新增 `temporary_basis: str|None`。

> 兼容性：只增字段，不改既有键名/类型；`c_calib_point` 仍是原始拟合并保留。

---

## §4 数据流（改动点）

```
loaders.load_month_regression
  └─ ret_day(日) / sigma(分钟)                 # 不变
panels._month_lambda
  ├─ sigma_d = std(ret_day, ddof=1) clip       # D1 新增
  └─ _samples += (p, |ret_day|, sigma_d)       # 改：第三元
panels._fit_impact
  ├─ 四模型 fit（不变）
  └─ sqrt: r2=fit_r2(pred,y); identifiable=?   # D2 新增
panels.build_daily_panels
  ├─ impact_bps：identifiable ? 校准 : c=0.5    # D2 门控
  ├─ rho：excess_d（日频）→ estimate_rho        # D3 改
  ├─ rho<=0 → 1.0 + warning                    # D3 新增
  └─ temporary_basis + warning                 # D4 新增
runner.run_calibration
  └─ models/c/temporary 透传新字段             # 只增
```

---

## §5 错误与边界

| 场景 | 行为 |
|------|------|
| `ret_day` 有效天数 < 2 | σ 取 clip 下界；样本保留 |
| `excess_d` < 3 | rho=1.0 + warning（沿用） |
| `excess_d` 为常数 | `estimate_rho` 抛 `ValueError` → 1.0 + warning（沿用） |
| `rho<=0` | 1.0 + warning（新增） |
| `sqrt` fit 失败 | 不写 r2；`identifiable=False`；成本回退 0.5（新增分支） |
| `y` 为常数 | 沿用 H1 规则：不拟合、warning |
| 非 sqrt 主模型 | 不做门槛，`identifiable=True` |

---

## §6 测试矩阵（步骤 9 先红后绿）

| # | 用例 | 断言 |
|---|------|------|
| T1 | 合成 `ret_day` 与分钟 σ | 样本 σ = `std(ret_day)`，且 ≠ 分钟 σ |
| T2 | 纯噪声样本 | `r2<0.05` → `identifiable=False`；cost 用 c=0.5；warning |
| T3 | 强信号样本（y=c·σ√p） | `r2≈1`、`identifiable=True`、c 还原 |
| T4 | 日频 ex_d | `rho_series` 长度 = ex_d 长度；`rho_freq="daily"` |
| T5 | rho<0 序列 | rho 输出 1.0；`retention(5)>0`；warning 含「无衰减」 |
| T6 | temporary 存在 | `temporary_basis="portfolio_ar1_proxy"`；warning 含「非 T+1」 |
| T7 | runner 输出 | 含 `c_r2/c_identifiable/c_effective/temporary_basis` |
| T8 | 默认路径 | `capacity_impact.json` SHA256 = `82728CE1…` |

---

## §7 风险

| # | 风险 | 缓解 |
|---|------|------|
| R1 | σ 改日频后 c 仍偏大 | D2 门槛回退；报告标 `[区间]` |
| R2 | 日频 rho 接近 1 | 与设计「无衰减」一致；net(h) 单调性由测试覆盖 |
| R3 | 新增字段破坏报告渲染 | 只增不改；renderer 对未知字段已忽略 |
| R4 | 校准脚本消费旧字段 | `attach_panel_meta` 仅读 `sigma_median/impact_fit`，兼容 |

---

## §8 回滚

代码回滚到 v3.9.1 标签即可；本批不迁移数据、不删字段、不改配置默认值。

---

## §19 步骤 4 复审记录（v1.0 → v1.1，2026-11-20）

**复审方式**：逐条把决策映射到现有函数签名/返回结构（Read/Grep），核对是否可实施；
不引入新文献、不新增外部依赖。

### 19.1 通过项

| # | 项 | 结果 |
|---|----|------|
| P1 | `SqrtImpact.fit` 可直接得到 `params["c"]` 并预测 | ✅ `impact.py` L59-68 / L52-57 |
| P2 | `_fit_impact` 已有 `primary/params/cv_rmse`，可增字段 | ✅ `panels.py` L127-142 |
| P3 | `build_daily_panels` 持有 `impact_fit` 与 `MODELS` 映射，可做回退 | ✅ L556-568 |
| P4 | `runner` 已有 `models_out` 与 `c_info`，可增 `r2/c_identifiable/c_effective` | ✅ L201-245 |
| P5 | 默认输出不含校准字段，门控在 `--calibrate` 分支 | ✅ 脚本 L428 / 默认 JSON 仅 `meta/results` |
| P6 | 版本落点 6 代码锚点与 v3.8.1 审计一致 | ✅ 见 §1.5/D5 |

### 19.2 发现与修正

| # | 级别 | 发现 | 修正 |
|---|------|------|------|
| F1 | P2 | D5 把「6 处锚点」与 CHANGELOG 混写，计数易歧义 | 改为「6 处代码锚点 + CHANGELOG，共 7 个落点」 |
| F2 | P2 | `fit_r2` 的「不抛错」表述与 NaN 入参边界不清 | 明确「非有限按 0.0 返回」 |
| F3 | P2 | panels 与 runner 各自算门槛，存在常量漂移风险 | 增加 `C_R2_MIN/C_RANGE` 共享常量与一致性测试 T7 |
| F4 | P3 | D1 未说明 σ 是否用与回归相同的 `ok` 掩码 | 明确用同一 `ok`（有限 x 与 r）掩码内的 `ret_day` |
| F5 | P3 | 既有测试可能断言月频 rho / bar σ | 步骤 9 同步更新 `tests/test_minute_panels.py`、`test_execution_capacity.py`，列入白名单 |

### 19.3 结论

**PASS_WITH_FIXES（已闭环）**。决策 D1-D5 不变；无学术幻觉（全部口径引自已复审 DESIGN/RESEARCH 原文）；
无 API 幻觉（逐条对照现有签名）。进入步骤 5 实施文档。
