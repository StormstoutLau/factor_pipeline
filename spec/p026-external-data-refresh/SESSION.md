# 批次 Session：外部数据项梳理与刷新请求（P-026）

---
id: p026-external-data-refresh-SESSION
type: session
version: 1.0
status: verified
date: 2026-11-24
depends: []
upstream: null
---

> **批次**：P-026 外部数据项梳理（`market_value.csv` + `barra_df_tl.pkl` + `stock_ind.pkl`）
> **档位**：**T3**（Layer-0 数据需求 / 账本；零代码 / 零门禁）
> **判档依据**：改动路径 = `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` / `docs/SPEC_COMPLIANCE.md` / `docs/analysis/DATA_GAPS_DIAGNOSIS.md` / `spec/p026-external-data-refresh/SESSION.md`；与 `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` 交集为 **∅**。
> **裁剪理由**：本批只定义外部数据请求、验收口径、接入步骤与阻塞点；不写代码、不改契约、不新增门禁。数据交付后的实施另立 T1 批次。
> **状态**：`blocked`——2026-11-24 用户裁决**暂时 suspend**（需求规格保留不撤销；恢复触发=外部数据源确定并交付，见 §5）。
> **回退点**：本批未产生 git 提交；回退 = `git checkout -- docs/PROGRESS.md docs/PROJECT_STATUS.md docs/SPEC_COMPLIANCE.md docs/analysis/DATA_GAPS_DIAGNOSIS.md` + 删除本目录。

---

## 0. 决策流（五步）

| 步 | 动作 | 结论 | 证据出口 |
|---|---|---|---|
| 1 | 判档与登记 | T3；PROGRESS 登记 **P-026**（blocked / P1） | `docs/PROGRESS.md` P-026 行 |
| 2 | 事实核对 | F-1~F-8：mv 缺 5 日；barra 缺 32 个月末；行业缺 640 日；结构已实探 | §1 |
| 3 | 需求规格 | D1 mv / D2 barra / D3 行业，逐字段对齐现有格式 | §2 |
| 4 | 验收与接入 | A-1~A-4 验收；I-1~I-6 交付后接入 | §3-§4 |
| 5 | 阻塞与回退 | B-1~B-5 决策点；F-1~F-3 回退方案 | §5-§6 |

---

## 1. 事实核对（E1，2026-11-24）

| # | 事实 | 读数 | 来源 |
|---|---|---|---|
| F-1 | 行情面板末日 | `stock_close` 等 1475×5688，2020-01-02 → **2026-01-30** | `E:\Ashare_data\market_data` 实读；`all_dates` 1475 日 |
| F-2 | `market_value.csv` 末日 | 1470×5684，2020-01-02 → **2026-01-23**，mtime 2026-01-27；缺 **5 个交易日** + 4 个新上市列 | 实读；[数据缺口诊断 §2](../../docs/analysis/DATA_GAPS_DIAGNOSIS.md#L34-L68) |
| F-3 | `barra_df_tl.pkl` 结构 | `pd.Series`，索引 = 月末交易日字符串；173 期（2009-01-23 → **2023-05-31**）；每值为 `dict`：`_id` + `BETA/MOMENTUM/SIZE/EARNYILD/RESVOL/GROWTH/BTOP/LEVERAGE/LIQUIDTY/SIZENL/INDNAME`；因子为 `code→float`，`INDNAME` 为 `code→str` | 实读探针 |
| F-4 | `barra_df_tl.pkl` 缺口 | 2023-06-30 → 2026-01-30 共 **32 个月末交易日**缺失 | `all_dates` 按月取最后交易日复算 |
| F-5 | `stock_ind.pkl` 结构 | `pd.DataFrame`，3510×5344，索引 = 交易日字符串（2009-01-05 → **2023-06-13**），列为 6 位代码，值为行业名（object） | 实读探针 |
| F-6 | `stock_ind.pkl` 缺口 | 2023-06-14 → 2026-01-30 共 **640 个交易日**缺失 | `all_dates` 复算 |
| F-7 | 消费方 | `scripts/run_ablation_real.py`（mv + stock_ind）、`scripts/verify_long_side_research.py`（mv + stock_ind）、`scripts/verify_multifactor_multiyear.py`（barra）、`scripts/verify_layer3_real.py` / `scripts/test_more_factors.py`（mv） | 仓内 grep |
| F-8 | 契约口径 | `data_contract`：`mv` `max_lag=1`；`barra` / `industry` `required=False, missing_semantics="known_gap"`，`GAP_CODE_BY_FIELD={"barra":"barra_stale","industry":"industry_stale"}` | [data_contract.py L236/L254-L257/L40-L43](../../backtest/data_contract.py#L236) |

**判读**：三份文件均为**外部/独立导出批次**，不是项目计算产物；缺口是数据管道停更，不是代码缺陷。mv 可短期补齐；barra/行业是 2023-06 后风格/行业中性化的硬阻塞。

---

## 2. 数据需求规格（D1-D3）

### D1 `market_value.csv`

| 项 | 要求 |
|---|---|
| 路径 | `E:\Ashare_data\market_data\market_value.csv` |
| 格式 | UTF-8 CSV，首列 `trade_date`（`YYYY-MM-DD` 字符串），其余列为 6 位股票代码 |
| 单位 | **元**（与 `data_contract` 的 `mv.unit="元"` 一致） |
| 覆盖 | 与 `all_dates` 对齐：2020-01-02 → 样本末（当前 2026-01-30）；本次补 2026-01-26~30 共 5 日；补 4 个新上市代码列 |
| 语义 | 每个交易日收盘总市值；未上市/退市/停牌按现有 NaN 语义；禁止用未来日期回填 |
| 一致性 | 历史交集行/列**逐位不变**；不得重排索引、不得改代码格式（6 位字符串） |
| 更新 | 日更，收盘后与行情面板同批；mtime 不早于行情面板 |

### D2 `barra_df_tl.pkl`

| 项 | 要求 |
|---|---|
| 路径 | `E:\Ashare_data\market_data\barra_df_tl.pkl` |
| 格式 | `pd.Series`；索引 = 每个月最后一个**交易日**的 `YYYY-MM-DD` 字符串；每值 = `dict` |
| 必含键 | `_id`（与索引同日）、`BETA`、`MOMENTUM`、`SIZE`、`EARNYILD`、`RESVOL`、`GROWTH`、`BTOP`、`LEVERAGE`、`LIQUIDTY`、`SIZENL`、`INDNAME` |
| 值类型 | 10 个风格键为 `dict[str, float]`（6 位代码 → 暴露）；`INDNAME` 为 `dict[str, str]`（6 位代码 → 行业名） |
| 覆盖 | 本次补 **32 期**：2023-06-30 → 2026-01-30 的月末交易日；既有 173 期**逐位不变** |
| PIT | 按月末时点截面生成；禁止用最新分类回填历史；供应商/版本/分类标准写入交付说明 |
| 更新 | 月度，月末后交付；`_id` 必须等于索引日期 |

### D3 `stock_ind.pkl`

| 项 | 要求 |
|---|---|
| 路径 | `E:\Ashare_data\market_data\stock_ind.pkl` |
| 格式 | `pd.DataFrame`；索引 = 交易日 `YYYY-MM-DD` 字符串；列 = 6 位代码；值 = 行业名（object/string） |
| 覆盖 | 本次补 **640 个交易日**：2023-06-14 → 2026-01-30；既有 3510 行**逐位不变** |
| 列覆盖 | 新日期上的列集 ⊇ `stock_close` 当日列集；新上市代码按上市日进入 |
| 末行质量 | 末行非空 ≥ 在上市股票的 **95%**；无整行为空 |
| PIT | 按交易日时点行业分类；行业分类标准/版本（如中信/申万）与代码变更映射写入交付说明 |
| 更新 | 日更；与行情面板同批 |

---

## 3. 验收口径（A-1~A-4）

### A-1 文件级

- mv：`index` 覆盖 `all_dates` 全部交易日；末日 == 样本末；列集 ⊇ `stock_close`；历史交集（行×列）SHA256 与交付前一致。
- barra：期数 = 173 + 32 = **205**；索引无重复、严格递增；每期 `_id` == 索引日期；11 个键齐全。
- industry：索引覆盖 2023-06-14 → 样本末全部交易日；末行非空 ≥95%；历史交集 SHA256 一致。

### A-2 数值/语义级

- mv：末 5 日每日非空列数 ≥ 当日 `stock_close` 非空列数的 **95%**；与旧 mv 重叠日的秩相关 > **0.99**（防整表错位）；值 > 0（除 NaN）。
- barra：每期 10 个风格键的覆盖 ≥ 当日 `stock_close` 列的 **90%**；值有限；截面 median/std 落在既有 173 期包的合理范围（人工复核异常尖峰/整列常数）；`INDNAME` 非空 ≥95%。
- industry：每个新交易日非空 ≥ 在上市股票的 **95%**；行业标签 ⊆ 旧标签 ∪ 交付说明中的新增标签；在上市但无行业标签的代码清单必须为空或附说明。

### A-3 契约门禁

```bash
python scripts/contract_gate.py --data-root E:\Ashare_data --sample-end 2026-01-30 \
  --report-json out/p026_contract.json
```

- 期望 exit **0**；`mv` freshness PASS；`known_gaps` 中不再出现 `barra_stale` / `industry_stale`。
- 因 `barra`/`industry` 当前 `max_lag=None`，另用一次性探针核对 A-1/A-2（探针不并入本批代码，交付后由 T1 批次落地）。

### A-4 消费方冒烟

- `scripts/verify_multifactor_multiyear.py` 能读取新 barra 并完成 2023-07+ 中性化，不再因缺数据截断；
- `scripts/run_ablation_real.py` / `scripts/verify_long_side_research.py` 能读取新行业数据并跑通；
- 记录运行日志与输出 hash，旧基线不覆盖，另存版本化证据。

---

## 4. 交付后接入（I-1~I-6）

| # | 步骤 | 说明 |
|---|---|---|
| I-1 | 备份 + 哈希 | 备份三份旧文件；记录历史交集 SHA256 |
| I-2 | 预验收 | 在临时目录按 §3 验收；不通过不替换 |
| I-3 | 原子替换 | `os.replace` 或同盘移动；保留旧文件只读副本 |
| I-4 | 契约/探针 | 跑 A-3；记录 `data_snapshot_hash` / `panel_hash` |
| I-5 | 复跑 | 39 月校准、容量、多头端、Barra 中性化研究；新旧读数并列，不静默覆盖旧证据 |
| I-6 | 文档/台账 | 更新 `DATA_GAPS_DIAGNOSIS`、`PROJECT_STATUS` 已知限制、相关研究结论；P-026 → done |

---

## 5. 阻塞点与决策（B-1~B-5）

| # | 决策/阻塞 | 选项 | 需要谁决定 |
|---|---|---|---|
| B-1 | barra/风格数据源 | A. 续约原供应商（同 schema）；B. Tushare 行业 + 自建风格因子；C. 其他商业源 | 用户/业务（成本、授权、合规） |
| B-2 | 交付责任与机制 | 数据管道团队导出到 `E:\Ashare_data\market_data`；或提供可复现导出脚本/接口 | 用户/数据 owner |
| B-3 | schema 保真 | 供应商若改结构，必须映射回 D2 的 Series[dict] 与 11 键；不接受仅"字段名相似" | 数据 owner + 本批评审 |
| B-4 | PIT/回溯 | 必须提供 2023-06 起的历史时点数据；只有最新快照不能回填，否则引入前视 | 数据 owner |
| B-5 | 行业分类标准 | 中信/申万/其他；版本与代码变更映射必须随交付 | 用户/研究口径 |

> **blocked 触发条件**：外部数据源确定并交付（mv 至行情末日；barra/行业覆盖 2023-06 之后）。触发后另立 T1 批次执行 I-1~I-6。

---

## 6. 回退/替代方案

- **barra/行业未交付**：2023-07+ 的风格/行业中性化研究继续锁定样本 ≤ **2023-06**，并在结论中显式标注「无风格/行业控制」；可用市值做 size-only 中性化，但不得表述为 Barra 中性化。
- **仅行业可得**：解锁行业中性化；风格因子仍缺失，相关结论标注「仅行业控制」。
- **mv 未交付**：保留 `max_lag=1` 门禁，不降低阈值；末月 `turnover_1m` 继续按 stale 披露，末月不进入绩效。
- **供应商只给最新快照**：不用于历史回填；只追加当前月起的数据，历史缺口保留并披露。

---

## 7. 非目标

- 不包含 DA-2（历史指数成分 / 公告日 / 退市覆盖）——另立数据请求；
- 不包含 `stock_adj` 81 日缺口修复（DL-2，另有 P 编号/批次）；
- 不在本批写 reader、契约字段或校验代码；交付后由 T1 批次落地。

---

## 8. 结论

P-026 已把三份外部数据的需求、验收与接入步骤定形；当前状态 **blocked**，唯一触发条件是数据源确定并交付。技术侧已明确：必须保持现有 schema / 历史交集不变 / PIT 时点，交付后先预验收再原子替换，复跑证据另存版本，不覆盖旧基线。
