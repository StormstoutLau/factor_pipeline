# 裁决前调研：P-003 反转成本口径 与 P-007 限价取整口径

---
id: research-p003-p007-decisions
type: research
version: 1.0
status: draft
date: 2026-11-21
depends: []
upstream: null
---

> **用途**: 为 [PROGRESS.md](../PROGRESS.md) 两项待裁决事项提供外部证据（交易所规则 / 学术文献 / 开源实现），作为后续 Step 1 RESEARCH 与 Step 3 DESIGN 的输入。
> **方法**: 两路独立检索代理（互不知情）+ 项目内部代码实核；外部来源均附 URL/DOI，条款号与部分链接仍需 Step 1 复核原文。
> **纪律**: 本文件**不替用户做裁决**，只给出证据强度、分歧点与未决问题。

---

## 0. 结论摘要

| 事项 | 外部证据倾向 | 内部现状 | 建议动作 |
|------|-------------|---------|---------|
| P-007 限价取整 | 涨跌停价**四舍五入（half-up）到 0.01**，沪深规则明文；判定与成交价假设应**拆成两个子决策** | `np.round` 为银行家舍入（ties-to-even），在 `.xx5` 边界与规则不符；但仅 `tradability.py` 自算路径受影响 | **已裁决（2026-11-21，用户）：并入 P-006**——判定口径随接入落地，成交价假设独立取值 |
| P-003 反转入成本 | 反转 ≡ 临时冲击的度量，与价差/冲击**存在重复计价风险**；A 股 close-to-close 反转被 T+1 隔夜折价污染 | `impact_bps` 拟合于**盘中 bar 价格移动**（≈临时冲击）；`temporary_share` 为组合层 close-to-close AR(1) | **已裁决（2026-11-21，用户）：走口径 A**——仅证据层真实现，`cost_by_h` / `net(h)` 不变 |

---

## 1. P-007：限价取整口径

### 1.1 交易所规则（强证据）

- **上交所**《交易规则》：涨跌幅限制价格 = 前收盘价 × (1 ± 比例)；**计算结果按四舍五入原则取至申报价格最小变动单位**；A 股最小变动单位 0.01 元；超过涨跌幅限制的申报无效。
  来源: <https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml>（条款号 3.3.11 / 3.3.13 / 3.3.16 / 3.3.17，**待 Step 1 复核原文**）
- **深交所**《交易规则》：同一口径，四舍五入 + 0.01 元 tick。
  来源: <http://docs.static.szse.cn/www/lawrules/rule/allrules/bussiness/W020260424690713155663.pdf>（条款号 3.3.11 / 3.3.14 / 3.3.18 / 3.3.19，**待复核**）
- **北交所**：公式与 0.01 元 tick 明确，股票规则正文未见「四舍五入」字样。
  来源: <https://www.bse.cn/jygl_list/200028217.html> `[部分未核实]`
- 监管问答复述同一口径：<https://www.csrc.gov.cn/guangdong/c105590/c1295922/content.shtml>
- 上交所英文版仅写 "rounded to the nearest tick size"，未界定 tie，**以中文本为准**。

**含义**：`np.round` 在恰为 `.xx5` 时向偶数取整（10.15×1.1 = 11.165 → 11.16，而 half-up 应为 11.17），与交易所规则不符；且二进制浮点会把邻近值推到边界，正确实现应走 `Decimal` 或显式 half-up。

### 1.2 学术文献（强证据：离散化偏差普遍存在）

- Harris (1991), *RFS* 4(3):389-415，DOI [10.1093/rfs/4.3.389](https://doi.org/10.1093/rfs/4.3.389)：价格聚类普遍，聚类程度随价格水平与波动率变化。
- Ball (1988), *JF* 43(4):841-865，DOI [10.1111/j.1540-6261.1988.tb02608.x](https://doi.org/10.1111/j.1540-6261.1988.tb02608.x)：tick 离散化使方差/峰度估计系统性偏高。
- Ball & Chordia (2001), *JF* 56(5)，DOI [10.1111/0022-1082.00390](https://doi.org/10.1111/0022-1082.00390)：固定网格下观察价与价差偏离真值。
- He & Wu (2004), *IREF* 13:19-41，DOI [10.1016/S1059-0560(03)00035-2](https://doi.org/10.1016/S1059-0560(03)00035-2)：十进制化后取整现象减弱。
- Harris (2003), *Trading and Exchanges*, OUP（教科书综述）。

`half-up vs half-even` 的专门实证**未检索到** `[未核实]`；仅影响 tie 情形，但涨跌停价恰为 tie 时决定「能否成交」。

### 1.3 开源实现（分歧明显）

| 框架 | 取整方式 | 备注 |
|------|---------|------|
| vnpy | `round_to`：Decimal 后内置 `round`（ties-to-even） | 无买卖方向差异；另有 `floor_to/ceil_to` 未被下单路径使用 |
| Zipline-reloaded | `asymmetric_round_price`：限价买向下、卖向上 | 保守化的是**成交概率**；明确避开 numpy banker's rounding |
| Backtrader | 未见 tick 取整 | 价格原样撮合 |
| Qlib | 不按 tick 取整 | `limit_threshold` 用涨跌幅生成可交易标记，涨跌停价由数据给定 |
| RQAlpha | `limit_up/limit_down` 取自数据源 | 比较时留一档容差 + epsilon |

链接：<https://github.com/vnpy/vnpy/blob/master/vnpy/trader/utility.py>、<https://github.com/stefan-jansen/zipline-reloaded/blob/main/src/zipline/finance/execution.py>、<https://github.com/ricequant/rqalpha/blob/master/rqalpha/utils/price_limits.py>、<https://github.com/microsoft/qlib/blob/main/backtest/exchange.py>

### 1.4 项目现状对照

[backtest/tradability.py L82-86](file:///f:/Coding/factor_pipeline/backtest/tradability.py#L82-L86)：

```python
def limit_price(prev_close, pct, side="up"):
    sign = 1.0 if side == "up" else -1.0
    return np.round(np.asarray(prev_close, dtype=float) * (1.0 + sign * pct), 2)
```

该函数同时服务于「涨跌停判定」（`can_trade`）与「价格假设」，即两个用途目前共用同一口径。

### 1.5 证据强度与待复核

- **强**：沪深规则明文 + tick 0.01；离散化偏差文献充分。
- **中**：北交所缺明文；英文版未界定 tie。
- **未核实**：A 股涨跌停价取整的专门实证；条款号需 Step 1 对照原文。
- **核心分歧**：交易所只约束「涨跌幅限制价格/有效申报价格范围」，**未规定回测成交价如何取整**；开源三派并存（nearest / 不取整 / 非对称）。
- **结论形态**：P-007 宜拆为 **(a) 涨跌停判定口径**（规则驱动，half-up）与 **(b) 成交价假设**（回测惯例，需单独裁决）两个子决策。

### 1.6 触发条件与影响面（与数据频率无关）

实核结论：**P-007 不是分钟级判定问题，且现有容量主路径完全不受影响。**

| 路径 | 是否计算限价 | 判定方式 | 受 P-007 影响 |
|------|------------|---------|--------------|
| `backtest/tradability.py`（日频 OHLC，`target_w` 为 (T,N)） | **是**（`np.round`） | `high >= up - eps` / `low <= down + eps` | **是**（但未接入引擎，P-006 pending；全仓仅测试引用） |
| 容量主路径（`MinutePanelBuilder` / `build_daily_panels`） | **否** | [`detect_limit_lock`](file:///f:/Coding/factor_pipeline/backtest/execution/core/classification.py#L57-L66)：`h==l`（一字板）或 `v==0 且 o=c=h=l` | 否 |
| 分钟 bar 聚合（`loaders.py`） | **否** | 同上结构判定，结果仅作 `locked` 计数 | 否 |

关键点：判定「是否触板」有两条互斥路线——
1. **自算限价再比较**（需要取整口径 → P-007）；
2. **结构/涨幅带判定**（不需要精确分值 → 无 P-007）。

OHLC 场景并不自动消除问题：只要仍用 `high >= limit_price(prev_close)`，取整误差依旧存在；但 OHLC 提供了**规避条件**——一字板可用四价相等结构判定，开板可用「涨幅落在 pct 容差带内且 `low < limit`」近似，无需计算分值。分钟级反而是唯一必须逐 bar 精确比较价位的场景，而项目当前没有逐 bar 撮合路径。

**推论**：P-007 的优先级应视为 **P-006（tradability 接入引擎）的前置口径**，而非容量研究的缺陷；若 P-006 接入时改为读取数据源 `limit_up/limit_down` 字段，或沿用结构判定，则取值口径只影响「成交价假设」这一子决策。

---

## 2. P-003：反转是否进入容量成本

### 2.1 理论框架：反转 = 临时冲击的度量方式（学术共识）

- Almgren & Chriss (2001), *J. Risk* 3(2):5-39，DOI [10.21314/JOR.2001.041](https://doi.org/10.21314/JOR.2001.041)：冲击拆为永久（信息）与临时（流动性补偿），临时部分在成交后衰减。
- Almgren, Thum, Hauptmann & Li (2005), *Risk*：把「成交后价格回落」作为临时冲击的识别手段——**反转就是临时冲击**。
  来源: <https://www.smallake.kr/wp-content/uploads/2016/03/Equity_Mkt_impact.pdf>
- Perold (1988), *JPM* 14(3):4-9，DOI [10.3905/jpm.1988.409150](https://doi.org/10.3905/jpm.1988.409150)：implementation shortfall = 佣金 + 半价差 + 冲击 + 延迟 + 机会成本。

### 2.2 重复计价：叠加即三重计价（学术共识）

- 有效价差 = 实现价差（成交后回落）+ 价格冲击：Huang & Stoll (1996), *JFE*，DOI [10.1016/0304-405X(95)00867-E](https://doi.org/10.1016/0304-405X(95)00867-E)；Glosten & Harris (1988), *JFE*，DOI [10.1016/0304-405X(88)90041-4](https://doi.org/10.1016/0304-405X(88)90041-4)。**两者是同一价差的分解项，不能相加。**
- Roll (1984), *JF*，DOI [10.1111/j.1540-6261.1984.tb03897.x](https://doi.org/10.1111/j.1540-6261.1984.tb03897.x)：一阶自协方差反推有效价差——现有 `temporary_share`（AR(1) 代理）本质是 Roll 型价差估计量。
- 唯一不重复的做法：把 `impact_bps` **拆成永久/临时**只收永久，或从冲击估计中**扣除**观测回落——即**替换**而非叠加。

### 2.3 实证量级

- Frazzini, Israel & Moskowitz "Trading Costs"（SSRN 工作论文 3229719，**非 JF**）：到达时平均半价差 21.33 bps，日内完成单平均冲击 <9 bps；组合层总成本 6.4（美大盘）/ 18.3（美小盘）/ 13.2（国际）bps。
- Novy-Marx & Velikov (2016), *RFS* 29(1):104-147，DOI [10.1093/rfs/hhv063](https://doi.org/10.1093/rfs/hhv063)：成本对换手高度敏感；其成本模型仅 spread + impact，**无反转项**。
- **必须区分**：A 股月度反转多空约 1–2.6%/月、隔夜-日内反转约 1.12%/日，属**信号反转（alpha）**，与「单笔交易后的价格回落」量级不可互推。

### 2.4 A 股特殊性（对口径 B 最不利的证据）

- T+1 制度使隔夜收益系统性为负：《金融研究》2025 估计年化折价 12.11%（≈5 bps/日），<http://www.jryj.org.cn/CN/Y2025/V535/I1/170>；深交所研究月均隔夜收益 −2.59%，<http://docs.static.szse.cn/www/aboutus/research/secuities/daily/W020200818633845765180.pdf>。
- Economic Modelling 2026，DOI [10.1016/j.econmod.2026.107783](https://doi.org/10.1016/j.econmod.2026.107783)：高成交量下跌日后的强反转集中在 **t+1 日内**，部分来自 T+1 延迟卖出而非冲击回落。
- **含义**：用 close-to-close 计算反转，会把 5–13 bps/日的制度性隔夜折价误记为冲击反转，与真实冲击同阶甚至更大。
- A 股「交易冲击 → 回落」的公开 bps 标定**未找到** `[无证据]`。

### 2.5 业界实现：无「反转」成本项

| 来源 | 成本项 | 反转 |
|------|--------|------|
| Qlib `Exchange` | `open_cost=0.0015` / `close_cost=0.0025` / `impact_cost=0.0` | 无 |
| Zipline / Quantopian | 佣金（PerShare/PerDollar）+ 滑点（Fixed / VolumeShareSlippage） | 无 |
| vnpy | 手续费率 + 每手滑点 | 无 |
| AQR | 基于真实成交的 TCA（规模/ADV、波动、价格） | 无独立项 |

惯例分类：fee / spread / impact / slippage / delay 五类，反转不单列。

### 2.6 项目现状对照（决定是否重复的关键）

1. **冲击模型**：[impact.py L66-76](file:///f:/Coding/factor_pipeline/backtest/execution/core/impact.py#L66-L76) `frac = c · σ · √p`（Almgren 型 **瞬时/临时**冲击形式），由分钟层 [loaders.py L119-129](file:///f:/Coding/factor_pipeline/backtest/execution/shell/loaders.py#L119-L129) 的**盘中 bar 收益 / 滚动 σ** 拟合 → 度量的正是成交时点的价格移动（≈临时冲击）。
2. **成本公式**：[panels.py L647-652](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L647-L652) `cost_by_h = (20/h)·AUM·换手·2·(FEE_BPS + impact_bps)/1e4`，其中 `FEE_BPS=10`（[L33](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L33)）为费率近似，**未单列半价差**。
3. **反转代理**：[panels.py L550-558](file:///f:/Coding/factor_pipeline/backtest/execution/shell/panels.py#L550-L558) 用组合日频超额 `excess_d` 的 t 与 t+1 序列 → **close-to-close** 口径，且显式警告「非 T+1 反转，不进入容量」；[runner.py L523-528](file:///f:/Coding/factor_pipeline/backtest/execution/shell/runner.py#L523-L528) 仅写入 payload。

### 2.7 口径 A vs 口径 B 的证据倾向

**支持口径 A（仅证据层，不改 net）**

1. 反转在理论上即临时冲击；本项目 `impact_bps` 已按瞬时冲击形式拟合，叠加即重复（§2.1/§2.2）。
2. 有效价差分解不允许「实现价差 + 冲击」相加（Huang-Stoll / Glosten-Harris）。
3. A 股 close-to-close 反转被 5–13 bps/日的 T+1 隔夜折价污染，信号不可识别（§2.4）。
4. 业界四家主流实现均无反转成本项（§2.5）。

**支持口径 B（接入 cost_by_h）**

1. 若能干净分离「交易诱发回落」，它确实是交易者真实付出的一部分（implementation shortfall 口径）。
2. 若 `impact_bps` 实际只标定了**永久**冲击，则临时项确实缺失（但 §2.6 显示拟合于盘中移动，不支持这一前提）。
3. A 股 t+1 日内反转显著，确有被低估的可能，但需 trade-to-trade 口径重构。

**关键未决点（Step 1 必须先答）**

- U-1 `impact_bps` 标定的是总冲击还是永久冲击？（现证据指向瞬时/临时冲击 → 重复风险高）
- U-2 反转序列能否改为 **trade-to-trade** 口径（而非 close-to-close），以剥离 T+1 隔夜折价？
- U-3 10 bps 费率是否已隐含半价差？（当前仅费率，若不含价差，则缺的是**价差**而非反转）
- U-4 买/卖方向是否对称？涨跌停日样本如何处理？

---

## 3. 证据强度总表

| 结论 | 强度 | 依据 |
|------|------|------|
| 沪深涨跌停价四舍五入到 0.01 | 强 | 交易所规则原文 + 监管问答 |
| 当前 `np.round` 属 banker's，与规则不符 | 强 | Python/numpy 语义 + §1.1 |
| 回测成交价取整无行业统一口径 | 强 | 五家实现三派并存 |
| 反转 = 临时冲击的度量 | 强（学术共识） | Almgren 系列 / Huang-Stoll / Roll |
| 反转与冲击/价差叠加会重复计价 | 强 | 有效价差分解文献 |
| A 股 close-to-close 反转含 T+1 隔夜折价污染 | 强 | 《金融研究》2025 / 深交所研究 |
| A 股「冲击→回落」bps 标定 | 无 | 未检索到公开标定 |

---

## 4. 未核实项与复核建议（Step 1）

1. 沪深规则**条款号**逐一对照原文（URL 已给，条款号来自检索代理）。
2. 北交所是否有股票取整明文。
3. `temporary_share` 现有读数（39 月）与「T+1 隔夜折价」量级的对照——若代理值本身已接近 5–13 bps/日，则强烈提示口径污染。
4. Frazzini et al. 的正式发表版本信息（检索代理称为 SSRN 工作论文，需确认）。
5. 本项目 `impact_fit` 的拟合样本是否含涨跌停/停牌 bar（影响 U-4）。

---

## 5. 来源清单

交易所/监管：
- 上交所《交易规则》 <https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml>
- 深交所《交易规则》PDF <http://docs.static.szse.cn/www/lawrules/rule/allrules/bussiness/W020260424690713155663.pdf>
- 北交所《交易规则》 <https://www.bse.cn/jygl_list/200028217.html>
- 证监会广东局问答 <https://www.csrc.gov.cn/guangdong/c105590/c1295922/content.shtml>

学术：
- Harris (1991) 10.1093/rfs/4.3.389；Ball (1988) 10.1111/j.1540-6261.1988.tb02608.x；Ball & Chordia (2001) 10.1111/0022-1082.00390；He & Wu (2004) 10.1016/S1059-0560(03)00035-2
- Almgren & Chriss (2001) 10.21314/JOR.2001.041；Almgren et al. (2005) <https://www.smallake.kr/wp-content/uploads/2016/03/Equity_Mkt_impact.pdf>；Perold (1988) 10.3905/jpm.1988.409150
- Huang & Stoll (1996) 10.1016/0304-405X(95)00867-E；Glosten & Harris (1988) 10.1016/0304-405X(88)90041-4；Roll (1984) 10.1111/j.1540-6261.1984.tb03897.x
- Novy-Marx & Velikov (2016) 10.1093/rfs/hhv063；Frazzini, Israel & Moskowitz, SSRN 3229719
- 《金融研究》2025 <http://www.jryj.org.cn/CN/Y2025/V535/I1/170>；深交所隔夜收益研究 <http://docs.static.szse.cn/www/aboutus/research/secuities/daily/W020200818633845765180.pdf>

开源实现：
- vnpy `utility.py` <https://github.com/vnpy/vnpy/blob/master/vnpy/trader/utility.py>
- zipline-reloaded `execution.py` <https://github.com/stefan-jansen/zipline-reloaded/blob/main/src/zipline/finance/execution.py>
- Qlib `exchange.py` <https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py>
- RQAlpha `price_limits.py` <https://github.com/ricequant/rqalpha/blob/master/rqalpha/utils/price_limits.py>
- Backtrader `bbroker.py` <https://github.com/mementum/backtrader/blob/master/backtrader/brokers/bbroker.py>
