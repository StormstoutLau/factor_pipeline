# PL-08 AR 阶数选择信息准则可比性调研

**文档版本**: v1.2 (2026-11-04; v1.1 = 步骤 2 review 修订; v1.2 = 步骤 3 设计期回注 `min_obs` 可估条件)
**缺陷编号**: DEFECT-PL-08
**状态**: 调研 + review 完成; 可进入步骤 3 (设计文档)
**上游依据**:
[PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md](PL05_DYNAMIC_AR_LOOKAHEAD_RESEARCH.md) §10.4「附带发现: AIC 跨阶数不可比」;
[2026-11-04-code-quality-audit.md](../audit/2026-11-04-code-quality-audit.md) L265;
[DEV_PROGRESS.md](../DEV_PROGRESS.md) §4.0 P1。

**调研范围**: `AROrderSelector._fit_ar` 的逐阶估计样本一致性; `hold_back` 语义; AIC/BIC/HQIC/AICc 的适用性; `ARDecoupler` 行为影响; `TemporalDecoupler` / `OptimizedARDecoupler` 边界。

**调研工具**: `mcp_paper-search` (Crossref/OpenAlex 检索与 DOI 元数据) / `mcp_stackexchange` (Cross Validated 问答) / `WebSearch` / `WebFetch` (官方文档与讲义) / 本地 Python 探针 (含 statsmodels 交叉验证)。

**证据等级**:
- **A**: 直接读到原文/摘要/官方文档/源码/作者讲义, 可逐字核对
- **B**: 搜索摘要、二手转引或第三方论文对原文的转述, 未读到原文对应段落
- **C**: 项目内部代码/文档/实测输出, 可复现
- **U**: 未能验证, 明确标注, 不作为论据

---

## §0 摘要 (TL;DR)

PL-08 是 **AR 阶数选择的信息准则建立在不同估计样本上**:

| # | 事实 | 性质 | 实测 |
|---|------|------|------|
| 1 | [`_fit_ar`](../../modules/factor_decoupler/core/ar_model.py#L139-L184) 对每个阶数 `p` 取 `y_trimmed = y[order:]` | 各阶 `n_obs = n - p` 不同 | `n=100` 时 AR(1..5) 的 `n_obs = 99/98/97/96/95` |
| 2 | AIC/BIC/HQIC 的似然项 `-n_obs/2(ln(2πσ²)+1)` 使用各自的 `n_obs` | 准则值跨阶不可比 | 每多一阶少 1 个观测; 在 `σ²` 近似不变时样本项约降 `ln(2πσ²)+1 ≈ 2.84`, 大于 AIC 的参数罚 `2` |
| 3 | 结果是**系统性偏向最高阶** | 不是随机误差 | `max_order=5` 时, AR(1) 真值面板上 AIC 均值 **4.80**, BIC **2.20**, HQIC **3.87** |
| 4 | statsmodels 明确要求 `hold_back ≥ maxlag` 才能比较不同阶数 | 官方语义 | `AutoReg(hold_back=None)` 默认等于 `maxlag`; 源码 `y = y[hold_back:]`, `x = x[hold_back:]` |
| 5 | 统一 `hold_back=max_order` 后阶数分布恢复 | 修复有效 | 同面板 AIC 均值 **1.23**, BIC/HQIC **1.00**; AR(2)/AR(3) 真值仍可识别 (均值 2.53 / 3.23) |
| 6 | 输出变化很大, 但因果性不变 | 重大行为变更 | T=100: **2790/3000 格 (93.0%)**, `max_abs=6.9968`; T=500: **14410/15000 (96.1%)**, `max_abs=4.6718` |
| 7 | 截断不变式仍成立 | 不引入前视 | AIC/BIC/AICc 在 9 个截断点 (7/8/9/10/12/15/25/60/80) 全部 **0 格 / 0 NaN** |
| 8 | 性能无实质变化 | 无额外成本 | 2500×300: 当前 **2.76s** vs hold_back **2.72s** (单次, 噪声级) |

**核心结论**:

1. 缺陷成立, 且**不是 AIC 专属**: 当前 BIC/HQIC 的阶数同样被抬高 (BIC 2.20 / HQIC 3.87 vs 上限 5)。修复必须作用于 `_fit_ar` 的样本构造, 与选用哪个准则无关。
2. 修复口径 = **统一 `hold_back = max_order`**: 所有阶数的响应向量与估计样本完全一致 (`y[H:]`, `x[H:]`), 这是 statsmodels 官方定义的"comparable models"。
3. **必须同时加有效样本守卫** `n_obs > order + 5`。否则 warm-up 早期 `t=7` 只有 `n_obs=2`、`k=2`, OLS 精确拟合导致 `σ²=0` 与 `ln(0)`; 实测 (T=500 面板) 弱守卫变体 `max_abs=322.68`, 加守卫后回到 **4.67–5.31**, 并消除 `divide by zero` 警告。
4. 守卫放在 `_fit_ar` 内、作用于 `n_obs` 后, `transform` 的 `early = min_order + 6` **无需改动**, `test_cold_start_is_identity` 契约保持; 实测其行为与"把 early 抬到 `H+min_order+6`"一致 (同面板 `max_abs=4.6718`; 早期行 t=9..13 在 S000 列抽查逐值相同)。
5. **不引入 AICc**: 生产拟合窗口 `warmup_obs=120` 下 `n_obs=115`, AICc 与 AIC 的阶数分布几乎相同 (T=500 面板完全相同, T=100 面板仅 1/30 列不同), 尾部一步 MSE 无改善 (`1.048759` 对 `1.048759`); 增加公共配置面不划算。
6. 修复**不改变 AIC 的不一致性**: AIC 仍会以固定概率过选阶 (Shibata 1976; 二手转引 0.2883), 但移除了"因样本长度不同造成的机械偏向"。这是"可比性修复", 不是"一致性修复"。
7. 核心影响面: `AROrderSelector` 与 `ARDecoupler` 的**拟合阶数/系数**; `transform` 结构、`warmup_obs` 语义、配置面均不变。`min_order == max_order` (固定阶数 p) 时, **`fit` 的冻结模型与当前完全相同** (`H = max_order = p` 使 `y[H:] = y[p:]`, 系数/准则/残差索引逐值一致; 守卫 `n_obs = len-p > p+5` 在默认 `min_obs=20`、`p ≤ 7` 下不触发); 但 **transform 的 warm-up 段不再逐行相同**: 守卫使 identity 起点推迟 (p=1 时 t=7 → t=8), refit 步点随之平移。`TemporalDecoupler` 共用同一选择器, 阶数会被动变化 (非生产路径); `OptimizedARDecoupler` 有同缺陷的独立实现, 不在本任务范围。
8. 版本建议 **v3.3.7**, 缓存 **`v2.2.5-cache`**, 决策编号 **ADR-041** (ADR-041 起未占用)。

---

## §1 调研问题清单

| # | 问题 | 结论 | 状态 |
|---|------|------|------|
| Q1 | 信息准则能否比较估计样本量不同的模型? | 不能; 似然项随 `n` 变化, 必须使用同一样本 | ✅ 已答 (§2, §3.1/§3.4) |
| Q2 | 标准实现如何保证跨阶可比? | statsmodels `AutoReg` 用 `hold_back`; 默认等于 `maxlag`; `hold_back ≥ maxlag` | ✅ 已答 (§3.1) |
| Q3 | 统一样本后 AIC 是否就"正确"选阶? | 否; AIC 仍不一致, 固定概率过选; BIC/HQIC 强一致 | ✅ 已答 (§2.1/§2.2) |
| Q4 | 是否需要 AICc 小样本修正? | 本项目 `warmup_obs=120` 下无必要; 修正项在 `n_obs=115`、`k≤6` 时可忽略 | ✅ 已答 (§2.2, §6.6) |
| Q5 | 修复对本项目阶数分布与输出影响多大? | 阶数均值 4.8→1.2–1.6; 输出 93%–96% 格子变化 | ✅ 已答 (§6.2/§6.3) |
| Q6 | 修复是否破坏 PL-05 的截断不变式? | 否; 9 个截断点全 0 格 / 0 NaN | ✅ 已答 (§6.4) |
| Q7 | 修复是否引入早期退化拟合? | 会; 必须加 `n_obs > order+5` 守卫 | ✅ 已答 (§6.5) |
| Q8 | 性能/兼容性/版本代价? | 性能无变化; `residuals` 索引起点由 `order` 变 `H`; 需版本与缓存 bump | ✅ 已答 (§6.7/§7) |

---

## §2 学术文献调研

### 2.1 文献与证据表

| 引用 | MCP/检索工具 | paper_id / DOI | 关键结论 | 状态 |
|------|-------------|---------------|---------|------|
| Akaike (1974) | Crossref | `10.1109/TAC.1974.1100705` | AIC 定义 `-2lnL + 2k`; 目标是 KL 信息的渐近无偏估计 | ✅ A (元数据); 公式为通用知识 |
| Shibata (1976) | Crossref | `10.1093/biomet/63.1.117` | 二手转述: AIC 有正概率渐近过选阶, 概率不趋于 0 | ✅ A (元数据); 摘要为空, 内容 ⚠️ B |
| Hurvich & Tsai (1989) | Crossref | `10.1093/biomet/76.2.297` | 小样本 AIC 有偏; 提出 AICc 修正 | ✅ A (元数据); 修正公式见 Hurvich 讲义 (A) |
| Hurvich & Tsai (1993) | Crossref | `10.1111/j.1467-9892.1993.tb00144.x` | AICc 扩展到向量 AR | ✅ A (元数据); 内容 ⚠️ U |
| Ing & Wei (2005) | OpenAlex | `10.1214/009053605000000525` | 摘要确认: Shibata (1980) 证明 AIC 及其变体对一步预测**渐近有效**; 本文进一步证明"同一实现预测"下仍有效 | ✅ A (摘要原文) |
| Burnham & Anderson (2002) | Crossref | `10.1007/b97636` | 信息准则模型比较的教科书参考; 具体"同一数据"原句未读 | ⚠️ A (书目元数据); 原句 ⚠️ U → §4 |
| Grant (2017) | WebSearch | `10.1111/jtsa.12238` | 转述: AIC 过选阶概率约 **0.2883** (Shibata 1976; Quinn 1988); BIC/HQIC 一致, HQIC 低估更少 | ⚠️ B (检索摘要) |
| JRSS-B (1985) 摘要 | WebSearch | `https://academic.oup.com/jrsssb/article-abstract/47/2/216/7035729` | "BIC 与 LIL 强一致; AIC 有正概率渐近过选阶 (Shibata 1976); AIC 不一致不等于劣于其他准则" | ⚠️ B (摘要片段) |
| Hurvich 讲义 (NYU) | WebFetch | `pages.stern.nyu.edu/~churvich/TimeSeries/Handouts/AICC.pdf` | "In small samples, however, AIC can drastically overfit... given n data points, AIC will prefer the saturated AR(n) model"; 给出 AICc 修正因子 | ✅ A (作者讲义原文) |
| FPP3 §ARIMA | WebSearch | `otexts.robjhyndman.com/fpp3/arima.html` | AICc 公式 `AIC + 2(p+q+k+1)(p+q+k+2)/(T-p-q-k-2)` | ⚠️ B (摘要片段); 公式与 Hurvich 一致 |
| Enders, *Applied Econometric Time Series* | WebSearch | 书籍预览 | "In using the criteria to compare alternative models, we must estimate over the same sample period so that they will be comparable" | ⚠️ B (检索片段); 版次/页码未核 |

### 2.2 理论要点

1. **可比性的前提是同一响应样本**。信息准则的拟合项是 `-2 ln L(θ̂ | y_obs)`; 若模型 A 用 `n` 个观测、模型 B 用 `n-1` 个观测, 似然值不在同一尺度上, 差值不能解释为模型优劣。这是 §3.1 官方文档与 §3.4 社区答案的共同结论。
2. **AIC 不一致, BIC/HQIC 强一致**。Shibata (1976) 证明 AIC 选阶在真值为有限阶 AR 时仍有正概率过选; 二手转引给出约 `0.2883`。BIC/HQIC 的罚项随 `ln n` / `ln ln n` 增长, 因而强一致。**修复可比性不会改变这一性质**。
3. **"不一致"不等于"预测差"**。Shibata (1980, *Ann. Statist.* 8: 147–164) 证明 AIC 及其变体对一步预测渐近有效; Ing & Wei (2005) 摘要进一步确认"同一实现预测"下仍有效。AIC 的过选阶是为预测效率付出的代价; BIC 的一致性优势针对"识别真实阶数", 两者目标不同。本项目以残差解耦/一步预测为目标, 因此保持 AIC 默认是合理的 (§5.2 D4)。
4. **AICc 的定位是小样本偏差修正, 不是可比性修正**。Hurvich & Tsai (1989) 的 `AICc = AIC + 2k(k+1)/(n-k-1)` 修正的是 AIC 作为 KL 估计的偏差; 它同样要求所有候选模型使用同一 `n`。
5. **本项目 `AIC` 与 statsmodels `AIC` 存在恒定偏移**。实测同一 hold_back 设计下, 系数、`llf`、`σ²`、`n_obs` 完全一致, 但 statsmodels 的 AIC 恒高 **2.0000**。原因已实测验证: statsmodels `AIC = -2·llf + 2·(df_model + 1)` 且 `df_model = p+1` (设计矩阵列数, 含常数项), 即参数计数为 `p+2` (滞后 + 截距 + 方差); 本项目为 `2·(p+1)`, 差恒为 2 (§6.8)。**恒定偏移不改变任何跨阶排序**; 本调研的所有结论对偏移不敏感。
6. **「同一数据」不等于「同一日历区间」**。`hold_back` 的语义是丢弃前 `H` 个观测后, 所有阶数使用同一响应向量; 对 AR(p)、p<H, 这意味着主动放弃前 `H-p` 个可用滞后对, 换取可比性——这是 statsmodels 文档明确的代价。

---

## §3 工程实践调研

### 3.1 statsmodels `AutoReg` 的 `hold_back` 语义 (A)

官方文档原文 (`statsmodels.tsa.ar_model.AutoReg`, stable):

> **hold_back : {None, int}**
> Initial observations to exclude from the estimation sample. If None, then hold_back is equal to the maximum lag in the model. **Set to a non-zero value to produce comparable models with different lag length.** For example, to compare the fit of a model with lags=3 and lags=1, set hold_back=3 which ensures that both models are estimated using observations 3,…,nobs. **hold_back must be >= the maximum lag in the model.**

来源: <https://www.statsmodels.org/stable/generated/statsmodels.tsa.ar_model.AutoReg.html>

源码 (`statsmodels/tsa/ar_model.py`, stable `_modules` 页面):

```python
if hold_back is None:
    hold_back = self._maxlag
if hold_back < self._maxlag:
    raise ValueError("hold_back must be >= lags ...")
...
y = y[hold_back:]
x = x[hold_back:]
```

来源: <https://www.statsmodels.org/stable/_modules/statsmodels/tsa/ar_model.html>

**对本项目的映射**: `AROrderSelector` 的 `max_order` 对应 `maxlag`; `_fit_ar` 应以 `H = self.max_order` 构造统一样本。当前实现未做, 即违反 `hold_back >= maxlag` 的可比性条件。

### 3.2 `ar_select_order` 不是"连续阶数"选择器 (A)

官方文档:

> **glob** : bool — Flag indicating whether to use a **global search across all combinations of lags**. ... the global search requires fitting **2\*\*maxlag** models.

来源: <https://www.statsmodels.org/stable/generated/statsmodels.tsa.ar_model.ar_select_order.html>

**结论**: `ar_select_order` 搜索的是**滞后子集** (如 `[1, 3, 9]`), 不是 `AR(1)..AR(p)` 的连续阶数。因此不能用它与本项目的 `max_order` 连续阶数选择做"分布逐列相等"的强断言; 正确的交叉验证对象是 `AutoReg(lags=p, hold_back=H)` 的逐阶 AIC (§6.8)。

### 3.3 社区证据: 不同样本量的信息准则不可比 (A)

Cross Validated Q94718「Model comparison with AIC based on different sample size」, 接受答案 `answer_id=224768` (score 7, owner Ivan Svetunkov):

> "All the information criteria are based on likelihood function, which in its turn depends on sample size. The larger sample size is, the smaller likelihood becomes and as a result the greater IC becomes. So, you should expect that with the increase of sample size, IC will increase as well (whatever criteria you use). **This means that you cannot compare different models fitted on different sample sizes using any information criteria.**"

来源: <https://stats.stackexchange.com/questions/94718>
检索方式: `mcp_stackexchange_get_answers(question_id=94718, site='stats', sort='votes')`。

同页另一答案 (score 0) 给出 AICc 公式 `AICc = AIC + 2k(k+1)/(n-k-1)`, 与 Hurvich 讲义一致 (仅作旁证)。

### 3.4 工程声明核实表

| 声明 | 核实方式 | 证据 | 状态 |
|------|---------|------|------|
| statsmodels 提供 `hold_back` 以保证跨阶可比 | WebFetch 官方文档 | AutoReg 文档原文 (§3.1) | ✅ VERIFIED |
| `hold_back=None` 默认等于 `maxlag`; `hold_back < maxlag` 报错 | WebFetch 官方源码 | `_check_lags` / `_setup_regressors` (§3.1) | ✅ VERIFIED |
| 所有阶数使用同一 `y[hold_back:]` 与 `x[hold_back:]` | 官方源码 | `y = y[hold_back:]`, `x = x[hold_back:]` | ✅ VERIFIED |
| `ar_select_order` 是滞后子集搜索, 不是连续阶数 | 官方文档 | `glob` 说明 + 2^maxlag | ✅ VERIFIED |
| 不同样本量的 IC 不可比 | StackExchange MCP | 接受答案原文 (§3.3) | ✅ VERIFIED |
| AIC 过选阶概率约 0.2883 | WebSearch 二手转引 | Grant (2017) 摘要 | ⚠️ B (未读原文) |
| BIC/HQIC 强一致 | WebSearch 二手转引 | JRSS-B 1985 摘要; HASTE 工作论文 | ⚠️ B |
| AICc 公式 | Hurvich 讲义 + FPP3 片段 | 两处一致 | ✅ A/B |

### 3.5 与本项目实现形态最接近的第三方实现

| 实现 | 做法 | 与本项目的关系 |
|------|------|---------------|
| statsmodels `AutoReg` / `ar_select_order` | `hold_back` 统一估计样本, 默认 `maxlag` | 直接对标; 本项目应实现同一语义 |
| statsmodels `AR` (deprecated) | 已弃用, 不作为锚点 | 不采用 |
| R `stats::ar` / `forecast::auto.arima` | 未逐行核对源码 | ⚠️ 未核实, 不作为论据 |
| 本项目 `OptimizedARDecoupler._fit_ar_order` | 同样 `y[order:]`, 同缺陷的独立副本 | 非生产路径, 不在本任务范围 (§7) |

---

## §4 待核实项 (⚠️ UNVERIFIABLE)

| # | 项 | 原因 | 处置 |
|---|----|------|------|
| U1 | Burnham & Anderson (2002) "models must be fit to the same data" 原句页码 | 书籍 paywall; 仅得书目 DOI 与二手转述 | 正文只引用"同一响应样本"原则, 不引用具体页码; 以 statsmodels 官方文档 (A) 为主锚 |
| U2 | Shibata (1976) 原文摘要/定理表述 | Crossref 摘要为空; 全文未获取 | `0.2883` 仅作 **B 级二手转引** (Grant 2017); 结论" AIC 不一致/过选"以 Hurvich 讲义 (A) 与 JRSS-B 摘要 (B) 交叉支持 |
| U3 | Quinn (1988) 原文 | 未检索到可读全文 | 不作为独立论据; 仅随 Grant (2017) 二手转引 |
| U4 | FPP3 "same data" 原句 | 仅命中 AICc 公式片段, 未定位到明确句子 | AICc 公式按 B 级引用; 可比性原则不依赖 FPP3 |
| U5 | `mcp_english-search` 的 `search_academic` / `search_web` | 前序检索返回 HTTP 404 | 已改用 `WebSearch` / `WebFetch` / Crossref MCP; 不影响结论 |
| U6 | `mcp_paper-search` 的 `search_semantic` | 对 Shibata/Hurvich 查询返回空列表 | 改用 Crossref DOI 元数据 + 官方/讲义文本 |
| U7 | `TemporalDecoupler` 的量化输出变化 | 仅通过共享 `AROrderSelector` 推断, 未单独跑面板 | 非生产路径; 在设计文档登记为"被动变化, 不纳入验收" |
| U8 | AICc 在 `warmup_obs < 120` 配置下的效果 | 未做多配置扫描 | 当前默认 `warmup_obs=120`; 若未来暴露配置面, 需重新评估 |

---

## §5 调研结论

### 5.1 可直接引用 (可进设计/实施文档)

1. **可比性条件**: 跨阶信息准则必须使用同一估计样本; statsmodels `hold_back` 的官方语义是 `hold_back = maxlag`、`y=y[H:]`、`x=x[H:]` (A, §3.1)。
2. **社区一致结论**: 不同样本量的模型不能用任何信息准则比较 (A, §3.3)。
3. **AIC 不一致但预测有效**: AIC 有正概率渐近过选阶; BIC/HQIC 强一致; 同时 AIC 对一步预测渐近有效 (Ing & Wei 2005 摘要) (A/B, §2.1/§2.2)。
4. **AICc 的适用边界**: 修正项 `2k(k+1)/(n-k-1)` 针对小样本偏差; 本项目 `n_obs=115` 时可忽略 (A/B, §2.2/§6.6)。
5. **本项目实测**: 统一 `hold_back` 后阶数均值 4.8→1.2–1.6; 输出 93.0%–96.1% 格子变化; 截断不变式 0/0; 性能不变 (C, §6)。
6. **早期退化**: 未加守卫时 `n_obs=2, k=2` 导致 `σ²=0`/`ln(0)`, `max_abs=322.68`; 加 `n_obs > order+5` 守卫后回到 4.67–5.31 (C, §6.5)。

### 5.2 需在步骤 3/4 确认的设计选择

| # | 选择 | 本调研建议 | 理由 |
|---|------|-----------|------|
| D1 | `hold_back` 取值 | `H = self.max_order` | statsmodels 默认; 与 `_fit_best` 的搜索上界一致 |
| D2 | 有效样本守卫 | `if n_obs <= order + 5: raise ValueError` | 与 `_fit_best` 的总长守卫同语义; 防止 `σ²=0`; 保证 AICc 分母 > 0 |
| D3 | `transform` 的 `early` | **不改** (`min_order + 6`) | 守卫在 `_fit_ar` 内自然把早期行留作 identity; 保持既有测试契约 |
| D4 | 默认准则 | **保持 `aic`** | 缺陷与准则无关; AIC 对一步预测渐近有效 (Ing & Wei 2005 摘要); BIC 一致性针对阶数识别, 且在 AR(3) 真值面板均值 2.53 (有低估) |
| D5 | AICc | **不加入公共配置面** | 生产拟合窗口下与 AIC 分布几乎相同; 无 MSE 改善; 增加 API 面 |
| D6 | `residuals` / `fitted_values` 索引 | 统一为 `series.index[H:]` | 与估计样本一致; 消费端 `TemporalDecoupler` 首 H 行变 NaN (非生产) |
| D7 | 版本/缓存 | **v3.3.7 / `v2.2.5-cache`** | 93%–96% 输出变化, 必须使缓存失效 |
| D8 | 决策编号 | **ADR-041** | ADR-040 已占用, ADR-041 起未占用 ([DECISIONS.md](../../DECISIONS.md) L43-L44) |
| D9 | 范围 | `AROrderSelector` + `ARDecoupler`; 不动 `optimized.py` / `TemporalDecoupler` 实现 | 最小改动; 非生产路径既有登记 |

### 5.3 不可引用 / 已证伪

| 说法 | 判定 | 依据 |
|------|------|------|
| "AIC 越高阶越好是数据本身的信号" | ❌ 已证伪 | 每阶少 1 个观测, 似然项约降 2.84 > 参数罚 2; 统一样本后最高阶不再系统性胜出 (§6.1) |
| "统一样本会让所有序列退化为 AR(1)" | ❌ 已证伪 | AR(2)/AR(3) 真值面板 AIC 均值 2.53/3.23, 仍能识别 (§6.2) |
| "`hold_back` 能修正 AIC 的不一致性" | ❌ 不可引用 | 只修可比性; AIC 仍固定概率过选 (Shibata 1976; §2.2) |
| "statsmodels `ar_select_order` 可直接对齐本项目选阶" | ⚠️ 不可直接引用 | 它搜索滞后子集, 不是连续 AR(p) (§3.2) |
| "必须用 AICc 才能正确选阶" | ❌ 不成立 | 本项目窗口下 AICc 与 AIC 分布几乎相同, MSE 无改善 (§6.2/§6.3) |
| "AIC 不一致, 所以应改用 BIC" | ⚠️ 过度推论 | AIC 不一致针对阶数识别; 一步预测下 AIC 渐近有效 (Shibata 1980, 经 Ing & Wei 2005 摘要), 本项目目标是残差/一步预测 |

### 5.4 候选方案

| 代号 | 方案 | 实测结果 | 判定 |
|------|------|---------|------|
| A | 统一 `hold_back` + 最小守卫 `n_obs > 1` | 阶数恢复, 但 `t=7..11` (`n_obs=2..6`) 出现 `σ²=0`/`ln(0)`; `max_abs=322.68` | ❌ 拒绝 |
| B | `hold_back` + 守卫 `n_obs > order+2` | 消除 `σ²=0`; `max_abs=5.3131`; 早期 `t=9..11` 仍用 4–6 个观测 | ⚠️ 可用但不够稳 |
| **C** | **`hold_back` + 守卫 `n_obs > order+5`** | **`max_abs=4.6718`**; 与"early 抬到 `H+min_order+6`"行为一致; `early`/测试契约不变 | ✅ **推荐** |
| D | C + AICc | 阶数分布与 C 几乎相同 (T=500 完全相同; T=100 差 1/30); MSE 无改善 | ❌ 不采纳 |
| E | C + 默认 BIC | 阶数均值 1.0; AR(3) 真值面板均值 2.53 (低估); 尾部 MSE 在 AR(1) 面板略优 | ❌ 超出缺陷范围 |

### 5.5 建议 (供步骤 3 设计文档采用)

1. **`_fit_ar` 统一 `hold_back`**:
   - `H = self.max_order`;
   - `y_trim = y[H:]`;
   - `X = [y[H-i : n-i] for i in 1..order]`, 再前置 `np.ones`;
   - `residuals` / `fitted_values` 索引 = `series.index[H:]`;
   - `n_obs = n - H` (所有阶数相同)。
2. **有效样本守卫**: `if n_obs <= order + 5: raise ValueError(...)`。放在构建设计矩阵之前; `_fit_best` 的异常捕获会跳过该阶; 若全部失败, 既有 AR(1) 回退 ([ar_model.py L129-133](../../modules/factor_decoupler/core/ar_model.py#L129-L133)) 同样经过 `_fit_ar`, 因此也受守卫约束——默认配置 (拟合路径 `n_obs ≥ 15 > 6`) 下可用, 极端配置下回退亦抛错、由 `batch_fit` 跳过该列。注意: 对阶数 `p`, 可估条件是 `min_obs - max_order > p + 5`; **全部阶数可估**需 `min_obs > 2*max_order + 5`, **仅 AR(1) 可估**需 `min_obs > max_order + 6`。默认 `min_obs=20, max_order=5` 满足全部可估 (`20 > 15`); 极端配置下 `batch_fit` 跳过该列。
3. **`transform` 不改**; `early = min_order + 6` 保留。守卫会使 `t=7..11` 自然输出 identity (与 `H+min_order+6` 等效)。
4. **默认准则保持 `aic`**; `criterion ∈ {aic,bic,hqic}` 的公共接口不变; 不新增 `aicc`。
5. **测试计划** (步骤 5/7 落地):
   - 同一序列 AR(1..max_order) 的 `n_obs` 必须相等;
   - AR(1) 真值面板选阶均值显著低于当前 (如 `<= 2.0`);
   - AR(2)/AR(3) 真值面板选阶均值接近真值 (容差需在设计中量化);
   - 截断不变式多截断点 0/0/0 (含 `t=7/8/9/10/12`);
   - 无 `σ²=0` / `ln(0)` 警告;
   - `residuals.index[0] == series.index[H]`;
   - 小样本 (`n_total=20`, `max_order=5`) 不崩溃;
   - 回归复跑 `tests/test_factor_decoupler/test_hidden_effect.py` 的 φ 断言 (`0.5<φ<0.9`, 容差 0.15): 阶数降低后 φ 取自 AR(1) 系数, 预期更稳, 但需实测确认。
6. **版本/缓存/ADR**: v3.3.7 / `v2.2.5-cache` / ADR-041。
7. **回滚**: 单点回滚 `_fit_ar` 即可; 无需数据迁移, 但缓存必须重建。

---

## §6 本地实测

> 探针脚本位于 `C:\Users\Peng\AppData\Local\Temp\pl08_research_probe.py`、`pl08_research_probe2.py`、`pl08_final_probe.py`, **不入库**。以下数值均为本次实际运行输出, 未做平滑或外推。

### 6.1 缺陷机制

**有效样本随阶数变化** (`T=100`, 单列, `seed=22`):

| 阶数 | 当前 `n_obs` | 当前 `residuals` 起点 | hold_back `n_obs` | hold_back 起点 |
|------|-------------|----------------------|-------------------|----------------|
| AR(1) | 99 | 2020-02-29 | 95 | 2020-06-30 |
| AR(2) | 98 | 2020-03-31 | 95 | 2020-06-30 |
| AR(3) | 97 | 2020-04-30 | 95 | 2020-06-30 |
| AR(4) | 96 | 2020-05-31 | 95 | 2020-06-30 |
| AR(5) | 95 | 2020-06-30 | 95 | 2020-06-30 |

**当前实现的逐阶 AIC** (`T=100`, `seed=22`, `S000`):

| 阶数 | AIC | ΔAIC | BIC | ΔBIC |
|------|-----|------|-----|------|
| AR(1) | 300.262 | — | 305.452 | — |
| AR(2) | 298.834 | -1.428 | 306.589 | +1.137 |
| AR(3) | 297.288 | -1.546 | 307.587 | +0.998 |
| AR(4) | 288.684 | -8.604 | 301.506 | -6.081 |
| AR(5) | 283.279 | -5.406 | 298.602 | -2.904 |

该序列上 AIC 单调下降 → 选 `max_order=5`。机制: 每多一阶少 1 个观测; 在 `σ²` 近似不变时, `-2lnL` 的样本项约减少 `ln(2πσ²)+1 ≈ 2.84`, 大于 AIC 的 `+2` 参数罚。实际 `ΔAIC` 还受 `σ²` 改善影响: 实测 AR(2)/AR(3) 的 `ΔAIC = -1.43/-1.55`, 仍为负, 因此阶数被持续推高。BIC/HQIC 也受同一"样本缩短"效应影响, 只是罚项更大、程度较轻。

### 6.2 阶数分布

**拟合窗口**: `T=100` 面板用 100 行; `T=500` 面板按生产语义只用前 `warmup_obs=120` 行。

| 面板 | 当前 AIC | hold_back AIC | hold_back AICc | hold_back BIC | hold_back HQIC |
|------|---------|---------------|----------------|---------------|----------------|
| T=100/N=30 seed=22 | mean **4.800** `{3:1,4:4,5:25}` | mean **1.233** `{1:27,2:1,3:1,5:1}` | mean **1.167** `{1:28,2:1,5:1}` | mean **1.000** `{1:30}` | mean **1.000** `{1:30}` |
| T=500/N=30 seed=42 | mean **4.867** `{3:1,4:2,5:27}` | mean **1.600** `{1:21,2:3,3:4,4:1,5:1}` | mean **1.600** 同 AIC | mean **1.000** `{1:30}` | mean **1.167** `{1:27,2:1,3:2}` |

**当前实现的其他准则** (T=100/N=30 seed=22): AIC 4.800 / BIC **2.200** / HQIC **3.867**。三项均被抬高, 证明缺陷不是 AIC 专属。

**真值恢复** (`T=120`, `N=30`, 不同 AR 真值):

| 真值 | 当前 AIC | hold_back AIC | hold_back BIC | hold_back HQIC |
|------|---------|---------------|---------------|----------------|
| AR(1) φ=0.7 | 4.87 `{3:1,4:2,5:27}` | 1.60 `{1:21,2:3,3:4,4:1,5:1}` | 1.00 `{1:30}` | 1.17 `{1:27,2:1,3:2}` |
| AR(2) (0.6, 0.3) | 4.87 `{4:4,5:26}` | **2.53** `{2:18,3:9,4:2,5:1}` | 2.00 `{1:2,2:26,3:2}` | 2.23 `{2:24,3:5,4:1}` |
| AR(3) (0.5, 0.3, 0.2) | 4.97 `{4:1,5:29}` | **3.23** `{2:5,3:17,4:4,5:4}` | 2.53 `{2:15,3:14,4:1}` | 2.93 `{2:9,3:16,4:3,5:2}` |

结论: `hold_back` 不会把一切压成 AR(1); 真值阶数仍可识别。BIC 在 AR(3) 面板略低估, 支持"保持默认 AIC"。

### 6.3 输出影响矩阵 (推荐方案 C)

| 面板 | 准则 | 变化格子 / 总格子 | `max_abs` | `mean_abs` | 尾部一步 MSE (t≥120) |
|------|------|-------------------|-----------|------------|----------------------|
| T=100/N=30 seed=22 | AIC | **2790 / 3000 (93.0%)** | 6.9968 | 0.3295 | — |
| 同上 | AICc | 2790 / 3000 (93.0%) | 6.9968 | 0.3364 | — |
| 同上 | BIC | 2790 / 3000 (93.0%) | 6.9968 | 0.3549 | — |
| 同上 | HQIC | 2790 / 3000 (93.0%) | 6.9968 | 0.3428 | — |
| T=500/N=30 seed=42 | AIC | **14410 / 15000 (96.1%)** | 4.6718 | 0.1337 | **1.048759** |
| 同上 | AICc | 14410 / 15000 (96.1%) | 4.6718 | 0.1335 | 1.048759 |
| 同上 | BIC | 14790 / 15000 (98.6%) | 4.6718 | 0.1673 | 1.030683 |
| 同上 | HQIC | 14790 / 15000 (98.6%) | 4.6718 | 0.1558 | 1.035097 |
| 同上 | 当前 AIC (参考) | — | — | — | 1.067782 |

**注意**: T=500 面板是 AR(1) 真值, 因此 BIC 的 MSE 优势 (1.0307) 是"真值更简约"的预期结果, 不能外推为"BIC 普遍更优"。AIC/AICc 的 MSE 相同, 说明 AICc 在本窗口无增益。

### 6.4 截断不变式

`ARDecoupler(max_order=5, warmup_obs=120)`, T=100/N=30 seed=22, 全样本 vs 截断面板逐元素对比 (`atol=1e-12`):

| 准则 | t=7 | t=8 | t=9 | t=10 | t=12 | t=15 | t=25 | t=60 | t=80 |
|------|-----|-----|-----|------|------|------|------|------|------|
| AIC | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| BIC | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| AICc | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |

格式为 `差异格子 / NaN 模式不一致`; 全部为零。hold_back 只改变估计样本长度, 不改变"只用前缀"的因果结构, 因此 PL-05 的不变式保持。

### 6.5 冷启动退化与守卫 (关键发现)

统一 `hold_back` 后, `transform` 在 `t=7` 的前缀只有 7 行, 丢弃前 5 行后 `n_obs=2`, 而 AR(1) 带截距 `k=2` → OLS 精确拟合, `σ²=0` → `ln(0)`:

- 弱守卫变体 (`n_obs > 1`) 在 `t=7..11` (`n_obs=2..6`) 出现 `RuntimeWarning: divide by zero encountered in log`;
- 早期行系数外推导致 `max_abs` 恶化到 **322.6771** (T=500 面板);
- 加上守卫后 (方案 B/C) `max_abs` 回到 **4.6718–5.3131**。

守卫对比 (`max_abs` 均为 T=500/N=30 seed=42 面板 vs 当前实现):

| 方案 | 守卫 | 早期首个可拟合 t | `max_abs` vs 当前 | 备注 |
|------|------|------------------|------------------|------|
| B | `n_obs > order+2` | t=9 (n_obs=4) | 5.3131 | t=9..11 仍用 4–6 观测 |
| **C** | **`n_obs > order+5`** | **t=12 (n_obs=7)** | **4.6718** | 与 early=12 变体行为一致 |
| early 变体 | 同一 df 守卫 + `early=H+min_order+6=12` | t=12 | 4.6718 | 需改 `early` 与冷启动测试 |

方案 C 的守卫语义与 `_fit_best` 现有守卫 `len(series) <= order + 5: continue` 一致, 只是把"总长度"换成"有效样本长度"。在默认 `min_obs=20`、`max_order=5` 下, 该守卫对拟合路径 (`n_obs=15`) 不触发; 只在 warm-up 早期触发。

### 6.6 小样本 AICc 分母

`n_obs = n_total - max_order`, `k = p+1 ≤ 6` (max_order=5):

| `n_total` | 20 | 21 | 22 | 25 | 30 | 40 | 60 | 80 | 100 | 120 |
|-----------|----|----|----|----|----|----|----|----|-----|-----|
| `n_obs` | 15 | 16 | 17 | 20 | 25 | 35 | 55 | 75 | 95 | 115 |
| `min(n_obs-k-1)` | 8 | 9 | 10 | 13 | 18 | 28 | 48 | 68 | 88 | 108 |

全部 > 0, 默认配置下 AICc 不会出现负分母。若未来把 `max_order` 调大, 守卫 `n_obs > order+5` 会先跳过不可估的高阶。

### 6.7 性能

`T=2500, N=300`, 单次 `fit_transform`, 同一进程:

| 实现 | 时间 |
|------|------|
| 当前 AIC | 2.76s |
| hold_back AIC (方案 C) | 2.72s |
| hold_back BIC | 2.76s |

差异在单次运行的噪声范围内; `hold_back` 每阶构造矩阵的规模从 `n-order` 变为 `n-H`, 总计算量同阶, 无实质成本。

### 6.8 与 statsmodels 的逐项交叉验证

`T=100`, `seed=22`, `S000`, `hold_back=5`:

| 阶数 | 本实现系数 | statsmodels 系数 | `llf` 差异 | `σ²` 差异 | `n_obs` | AIC 差异 |
|------|-----------|------------------|-----------|----------|---------|---------|
| AR(1) | `[0.1116, 0.7733]` | 完全一致 | 0 | 0 | 95/95 | **-2.0000** |
| AR(2) | `[0.1083, 0.7263, 0.0601]` | 完全一致 | 0 | 0 | 95/95 | -2.0000 |
| AR(3) | `[0.1069, 0.7243, 0.0308, 0.0390]` | 完全一致 | 0 | 0 | 95/95 | -2.0000 |
| AR(4) | `[0.1189, ..., -0.2901]` | 完全一致 | 0 | 0 | 95/95 | -2.0000 |
| AR(5) | `[0.1310, ..., -0.1729]` | 完全一致 | 0 | 0 | 95/95 | -2.0000 |

AIC 的恒定 `-2` 偏移来自参数计数口径, 已实测验证: `AutoReg(...).aic == -2·llf + 2·(df_model + 1)` 且 `df_model = p+1` (p=1/3/5 三点全部吻合), 即 statsmodels 计 `p+2` 个参数 (滞后 + 截距 + 方差), 本项目计 `p+1`; **偏移对所有阶数相同, 不改变排序**。

`ar_select_order(hold_back=5, ic='aic')` 在本面板上 `glob=False` 与 `glob=True` 均选 AR(1) 30/30, 本实现 hold_back AIC 为 27/30 选 AR(1)。差异来自 `ar_select_order` 的**滞后子集搜索** (§3.2), 不作为实现一致性判据。

---

## §7 兼容性、范围与版本

### 7.1 行为影响面

| 对象 | 影响 | 说明 |
|------|------|------|
| `AROrderSelector.fit` / `_fit_best` | 阶数分布变化 | 本次缺陷的直接修复对象 |
| `ARDecoupler.fit` / `_results` | 冻结模型的阶数与系数变化 | 93%–96% 输出格子变化 |
| `ARDecoupler._get_ar_phi_for_diagnosis` | 平均 φ 变化 | φ 取自选定阶数的 `coefficients[1]`, 随阶数变化; 本调研未量化其偏差 |
| `ARModelResult.residuals` / `fitted_values` | 索引起点 `series.index[order:]` → `series.index[H:]` | 与统一估计样本一致 |
| `ARDecoupler.get_residual_stats` | 统计值变化 | `dropna()` 后计算, 索引起点不影响 |
| `TemporalDecoupler._apply_ar_residual` | 选定阶数 `p < H` 的列, 残差索引由 `index[p:]` 变 `index[H:]`, 中间 `H-p` 行经 `reindex` 变 NaN (`p = H` 的列不变) | 非生产路径; `reindex` 后自然缺值 |
| `OptimizedARDecoupler._fit_ar_order` | **不变** | 独立副本, 同缺陷但不在本任务范围 |
| `DynamicFactorPipeline` / `CompositeDecoupler` | 输出变化 | 通过 Stage 2 的 `ARDecoupler` 被动变化 |
| 配置面 (`PipelineV2Config` / optimizer) | **不变** | `max_order`/`criterion`/`warmup_obs` 语义不变 |

### 7.2 版本与缓存

| 项 | 当前 | 修复后 | 依据 |
|----|------|--------|------|
| 包版本 | 3.3.6 | **3.3.7** | [pyproject.toml](../../pyproject.toml) L7 |
| 缓存代号 | `v2.2.4-cache` | **`v2.2.5-cache`** | [cache_manager.py](../../backtest/cache_manager.py) L58 |
| ADR | ADR-040 | **ADR-041** | [DECISIONS.md](../../DECISIONS.md) L44 |
| 兼容性 | — | 输出不兼容 (需重建缓存); API 兼容 | 无签名变更 |

### 7.3 不在本任务范围

- `OptimizedARDecoupler` / `TemporalDecoupler` 的实现改造 (非生产路径, 既有登记)。
- 默认准则从 AIC 切换为 BIC/HQIC (超出缺陷范围)。
- `warmup_obs` / `_WARMUP_REFIT_STRIDE` 的再调参 (PL-05 已定稿)。
- 冻结模型对非平稳因子的失配回测 (独立任务)。

---

## 附录 A 探针与原始输出

### A.1 探针脚本

| 脚本 | 用途 |
|------|------|
| `%TEMP%\pl08_impact_probe.py` | 初版: hold_back + **总长守卫** `n > H+5` (t ≥ 11 才拟合); 阶数分布与输出偏移 |
| `%TEMP%\pl08_research_probe.py` | 准则对比 (AIC/AICc/BIC/HQIC)、截断不变式、AICc 分母、性能; 其 hold_back 变体仅守 `n > H+1` (即 `n_obs > 1`), 用于暴露退化 |
| `%TEMP%\pl08_research_probe2.py` | 冷启动边界 (`early=7` vs `early=12`) 与退化拟合 |
| `%TEMP%\pl08_final_probe.py` | 推荐口径 (hold_back + `n_obs > order+5` 守卫) 的最终矩阵 |

以上脚本均为临时探针, 不进入仓库; 关键数值已固化在本 §6。

### A.2 关键原始输出 (节选)

**初版探针 `pl08_impact_probe.py` (hold_back + 总长守卫 `n > H+5`, 即 t ≥ 11 才拟合)**:

```text
[T=100/N=30 seed=22]
  current order: mean=4.800 dist={3: 1, 4: 4, 5: 25}
  holdback order: mean=1.233 dist={1: 27, 2: 1, 3: 1, 5: 1}
  output delta: cells=2790/3000 max_abs=5.7503 mean_abs=0.3253
[T=500/N=30 seed=42]
  current order: mean=4.833 dist={3: 2, 4: 1, 5: 27}
  holdback order: mean=1.467 dist={1: 21, 2: 6, 3: 2, 5: 1}
  output delta: cells=14410/15000 max_abs=4.6718 mean_abs=0.1356
```

**弱守卫变体 `pl08_research_probe.py` (仅 `n > H+1`, 即 `n_obs > 1`; 暴露退化)**:

```text
[T=100/N=30 seed=22] delta: cells=2634/3000 max_abs=27.7125 mean_abs=0.4183
[T=500/N=30 seed=42] delta: cells=14367/15000 max_abs=322.6771 mean_abs=0.2980
```

> 注 1: 初版的**阶数分布**在全 500 行序列上计算 (`AROrderSelector.fit` 直接吃全序列), 而 `ARDecoupler` 输出仍按生产语义只用前 120 行拟合; §6.2 按生产语义统一用 120 行, 故 `mean=1.600` 与初版 `1.467` 不同。两者都说明阶数大幅下降。
> 注 2: `max_abs=322.6771` 是 `n_obs=2..6` 早期退化拟合的瞬态, 见 §6.5。初版总长守卫 (t ≥ 11) 与推荐方案 C (t ≥ 12) 仅差早期个别行, T=500 输出偏移几乎相同 (14410 格 / 4.6718)。

**推荐口径 (方案 C: hold_back + `n_obs > order+5` 守卫)**:

```text
[T=100/N=30 seed=22] fit 窗口=100 行
  holdback AIC : mean=1.233 dist={1: 27, 2: 1, 3: 1, 5: 1}
  delta [AIC ]: cells=2790/3000 (93.0%) max_abs=6.9968 mean_abs=0.3295
[T=500/N=30 seed=42] fit 窗口=120 行
  holdback AIC : mean=1.600 dist={1: 21, 2: 3, 3: 4, 4: 1, 5: 1}
  delta [AIC ]: cells=14410/15000 (96.1%) max_abs=4.6718 mean_abs=0.1337 mse_tail=1.048759
```

**无守卫时的退化 (`σ²=0`)**:

```text
RuntimeWarning: divide by zero encountered in log
  ll = -n_obs / 2 * (np.log(2 * np.pi * sigma2) + 1)
...
max_abs = 322.6771
```

**推荐口径的截断不变式**:

```text
[AIC ] cut=  7: cells=0/210 nan_mis=0 max_abs=0.0e+00
[AIC ] cut= 12: cells=0/360 nan_mis=0 max_abs=0.0e+00
[AIC ] cut= 80: cells=0/2400 nan_mis=0 max_abs=0.0e+00
[BIC ] cut=  7: cells=0/210 nan_mis=0 max_abs=0.0e+00
[AICC] cut= 12: cells=0/360 nan_mis=0 max_abs=0.0e+00
```

---

## 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-11-04 | 步骤 1 调研初稿 |
| v1.1 | 2026-11-04 | 步骤 2 调研 review 修订 (CRITICAL 0 / MAJOR 2 / MINOR 7, 全部修复): M1 §0 结论 7 固定阶数等价性改写为"`fit` 冻结模型等价 + warm-up 段守卫时点/步点平移"; M2 §A.1/§A.2 探针归属更正 (初版总长守卫 vs 弱守卫变体, 补初版原始输出); m1 statsmodels AIC 口径由推断升级为实测公式; m2 §7.1 TemporalDecoupler NaN 行数精确化; m3 §1 Q3 锚点补 §2.2; m4 调研工具补 OpenAlex; m5 §6.5 守卫对比表补面板标注; m6 §5.5 AR(1) 回退守卫前提; m7 §0/§5.1 max_abs 时序措辞 |
| v1.2 | 2026-11-04 | 步骤 3 设计期回注: §5.5 D2 的 `min_obs` 约束精确化为"全部阶数可估 `min_obs > 2*max_order+5`; 仅 AR(1) 可估 `min_obs > max_order+6`"; 与设计文档 §9 R5 对齐 |

**调研 review 结论**: 2026-11-04; 引用逐条核实通过 (statsmodels 文档/源码、SE Q94718 原文、Crossref/OpenAlex DOI、Hurvich 讲义), 数值对账通过 (§0/§5/§6/§A 与探针原始输出一致), 结构符合 §13.3 工件 A。可进入步骤 3 (设计文档)。
