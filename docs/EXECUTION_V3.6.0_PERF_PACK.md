# EXECUTION v3.6.0 性能包 — P2-1 五项超预算 (O1-O5)

> **版本**: v1.0 (2026-11-18)
> **流程**: [WORKFLOW_METHODOLOGY §13.8](WORKFLOW_METHODOLOGY.md#L1201) 小任务裁剪（步骤 5-6-9-10；调研/设计内联）
> **上游证据**: [ADD 审计 P2-1](audit/2026-11-18-v3.6.0-governance-base-audit.md#L158) /
> `out/govbase_perf.json`（E2）／本批剖析 `out/perf_profile.py`（E2）
> **目标版本**: **3.6.0 不 bump**（未提交批次内优化；6 锚点与缓存代际不动）
> **档位**: T1（Layer-1：`backtest/`）；裁剪理由：全部为函数内向量化/批量重写，无接口变更
> **新增依赖**: 零

---

## §1 任务清单

| # | 环节 | 基线（2026-11-18 复测） | 预算 | 目标 |
|---|------|------------------------|------|------|
| O1 | `GovernanceStore.append_many` 10k | **7.605s** | **1.0s（重估）** | 批量存在性 + 单次序列化；预算按实测下界重估（见 DR-P1） |
| O2 | `apply_bh_fdr` 100k | **0.0749s** | 0.05s | 向量化（argsort + 反向累积 min + searchsorted） |
| O3 | `apply_romano_wolf` 1000×1000 | **3.1232s** | 0.5s | 利用行内前缀有序性，消除 O(m·B·j log j) |
| O4 | `WhiteRealityCheck` / `HansenSPA` T=1000,K=100,B=1000 | **288.85s / 158.95s** | 10s | 索引生成向量化 + 分块 gather |
| O5 | `GoldenMaster.compare` 24×300×4 | **0.1372s** | 0.1s | `_to_long` 用 numpy 构造替代 melt |

> 基线复测命令：`python out/perf_profile.py <1|2|3|4|5>`；原审计读数（4.442s / 0.081s / 3.203s / >300s / 0.140s）同向。

---

## §2 工程事实（E2 剖析）

| # | 事实 | 证据 |
|---|------|------|
| F1 | `append_many` 已用 `INSERT ... SELECT`，但**每条记录两次** `model_dump` + `compute_payload_hash`，且 10k 次单行 `_decide` 查询 | `backtest/governance.py` L783-839、L697-712 |
| F2 | `canonical_json` 先递归 `_jsonable`（Python 层）再 `json.dumps`；JSON-native payload 白付 ~0.6s/10k | `governance.py` L~180；实测 raw dumps 0.173s vs canonical 0.786s |
| F3 | 10k 记录序列化下界：dump 0.104s + JSON 文本 0.173s + body hash 0.173s ≈ **0.45s**（不含载入 DB） | 本批实测（`out` 一次性脚本） |
| F4 | BH 用 Python 反向循环 + 正向 step-up 循环（各 10 万次） | `multiple_testing.py` L89-114 |
| F5 | RW 对每个 j 重排 `(B, j+1)` 子矩阵：O(m·B·j log j) | `multiple_testing.py` L554-565 |
| F6 | White/SPA 默认路径按 `b×k×t` 逐位置 Python 循环生成索引（1e8 次迭代）；individual p 再跑一遍 | `multiple_testing.py` L1119-1146、L1316-1340、L987-1006 |
| F7 | 行内前缀有序性 ⇒ 对 j ≥ k-1，前缀第 k 小 == 整行第 k 小（`sorted_boot[:, k-1]`），可一次 `searchsorted` 求全部 CDF | 推导 + 小样本对拍（T56） |
| F8 | `_to_long` 用 `DataFrame.melt` 展开 24×300×4 | `golden_master.py` L124-146 |
| F9 | `compute_payload_hash` 对每个顶层值再跑一次递归 `_jsonable`（JSON-native 时纯冗余），10k 记录 ≈0.43s | `governance.py` L236；分段剖析 `payload_hash 0.598s` vs `canonical_json 0.169s` |

---

## §3 设计决策（内联）

### DR-P1：append_many 批量化 + 预算重估

**决策**：① `model_dump` 每条一次；② 存在性检查改为注册 DataFrame + 一次 `JOIN`（`_existing_hashes`）；③ `canonical_json` 加 JSON-native 快路径（失败回退 `_jsonable`，语义不变）；④ `compute_payload_hash` 去掉逐字段 `_jsonable`（F9），改由 `canonical_json` 快路径/回退统一处理。
**预算重估**：0.1s → **1.0s**。依据：10k × 17.5MB JSON 的纯序列化下界 ≈0.45s（F3），0.1s 物理不可达；新预算 = 下界 × 2.2，留 DuckDB 写入与 DataFrame 构造余量。实测 **0.724s**（含 ④ 的 ~0.43s 削减），重估预算内达标。
**拒绝方案**：(a) 改存 msgpack/去 payload → 破坏 schema 与 `ancestors()` 重放；(b) 保留逐条查询 → 10k 次往返。

### DR-P2：BH 向量化

**决策**：`p_adj = minimum.accumulate(sorted_p * K / ranks)` 再按 `order` 还原；显著性用 `sorted_p <= alpha * ranks / K` 找最大 k*。
**Ties 口径**：排序改 `kind="stable"`（旧实现为默认快排、ties 次序不确定）；`p_adj` 与 ties 次序无关；仅当显著性边界恰落在 ties 组内部时，组内归属随排序次序而定 —— 旧实现同样未定义，现固定为稳定序（T55 含两位小数 ties 对拍）。
**拒绝方案**：`statsmodels.multipletests` → 新增依赖（违背零依赖）。

### DR-P3：RW 前缀统计量

**决策**：j ≥ k-1 时 `kth_in_sub = sorted_boot[:, k-1]`（F7），对其排序一次后 `searchsorted(sorted_p, side='right')/B`；j < k-1 的至多 k-1 列单独处理。
**拒绝方案**：保留子矩阵重排 → 3.1s 超预算 6 倍。

### DR-P4：White/SPA 索引向量化

**决策**：stationary 索引按「跨样本并行、沿 t 递推」生成（`np.where` 每步），分块上限 128MB；joint 与 individual 复用同一套索引矩阵（individual 用各自块大小）。circular 且逐列块大小不同（auto 估计）时按列独立生成后拼接，保持旧「每列用各自块大小」语义。
**数值影响**：同 seed 内部仍确定（现有测试只断言确定性/区间/单调，无硬编码 p 值）。
**拒绝方案**：`bootstrap_indices` 注入路径保持逐值不变（不动）。

### DR-P5：golden `_to_long` 向量化

**决策**：`np.tile` 日期 + `np.repeat` 股票 + `ravel(order="F")` 值列，一次构造长表；**行序复刻 melt 的列优先展开**（日期块按股票逐列铺开），输出列序与 dtype 与 melt 版逐值一致。
**过程读数**：首版用 `np.repeat` 日期 + `reshape(-1)`（日期优先行序），T58 对拍 `1 failed, 92 passed` —— 值/列/dtype 一致但行序不同；改为 `tile/repeat + order="F"` 后 `93 passed`。保留「行序也一致」以保证 capture/parquet 落盘与旧基线逐字节可比。
**预算**：保持 0.1s（不重估）。

---

## §4 代码变更点

| 文件 | 变更 |
|------|------|
| `backtest/governance.py` | `canonical_json` 快路径；`compute_payload_hash` 去冗余 `_jsonable`；`append_many` 单次 dump + 批量 JOIN（`_existing_hashes`） |
| `backtest/multiple_testing.py` | `apply_bh_fdr` / `_romano_wolf_stepdown` / `apply_romano_wolf(single_step)` 向量化；`WhiteRealityCheck.test` / `HansenSPA.test` 分块向量化；新增 `_stationary_indices_multi` / `_circular_indices_multi` / `_bootstrap_batch_rows` / `_indices_batch` / `_bootstrap_means` |
| `backtest/golden_master.py` | `_to_long` numpy 构造 |
| `out/perf_profile.py` | 剖析/复测脚本（证据，不入库） |

**接口/输出不变**：函数签名、返回结构、异常类型、`bootstrap_indices` 注入路径逐值不变。

---

## §5 红→绿读数（F5）

**红 = 优化前实测**（2026-11-18，`out/perf_profile.py`）：

```text
[红] append_many 10k          7.6051 s（预算 0.1s，拟重估 1.0s）
[红] BH 100k                  0.0749 s（预算 0.05s）
[红] RW 1000x1000             3.1232 s（预算 0.5s）
[红] White T=1000,K=100,B=1000  288.8493 s（预算 10s）
[红] SPA   T=1000,K=100,B=1000  158.9533 s（预算 10s）
[红] golden compare 24x300x4    0.1372 s（预算 0.1s）
```

**绿 = 优化后实测**（同脚本、同参数、同机器）：

```text
[绿] append_many 10k          0.7240 s（10.5×；重估预算 1.0s 内）
[绿] BH 100k                  0.0156 s（4.8×；预算 0.05s）
[绿] RW 1000x1000             0.0071 s（440×；预算 0.5s）
[绿] White T=1000,K=100,B=1000  7.5599 s（38.2×；预算 10s）
[绿] SPA   T=1000,K=100,B=1000  3.8915 s（40.8×；预算 10s）
[绿] golden compare 24x300x4    0.0586 s（2.3×；预算 0.1s）
[绿] White/SPA 峰值内存        170.9 / 170.2 MB（预算 <1GB；tracemalloc 开销下计时 9.10/4.38s）
```

**等价性测试（先绿，优化前后均须通过）**：T55 BH 对拍 / T56 RW 对拍 / T57 批量写入语义 /
T58 `_to_long` 对拍 / T59 性能烟测（宽阈值，防复杂度回退）。

**绿读数（测试侧）**：
- 定向 4 文件：`93 passed in 2.67s`（multiple_testing / ledger / governance / golden）
- 追加 data_contract：`101 passed in 2.62s`
- 中间读数（如实登记）：T58 首版行序不符 `1 failed, 92 passed in 3.03s` → 修 `_to_long`（DR-P5）后转绿
- AST py39：`py39_annotation_violations=0`、`subscript_builtin=[]`（3 个改动文件）
- 全量 gate：**1933 passed / 7 skipped / 13 subtests in 1059.21s**（seq 32，exit 0；耗时比 0.70 vs 1516.82s 基线）

---

## §6 兼容性、零变更与回退点

| 项 | 影响 | 处置 |
|----|------|------|
| 函数签名 / 返回结构 | 不变 | T55-T58 断言 |
| 随机数流（White/SPA） | 同 seed 结果与旧实现不同 | 测试只断言确定性/区间/单调；文档登记 |
| `bootstrap_indices` 注入 | 逐值不变 | 既有 T28/T57 覆盖 |
| 默认路径 golden | `_to_long` 输出逐值一致 | T58 对拍 |
| 预算修订 | 仅 O1（0.1→1.0s），依据 F3 | 审计报告与 CHECKLIST 同步 |
| 回退点 | 逐项独立 | O1-O5 各自回退单文件 hunk |

---

## §7 验收命令

```text
1) python out/perf_profile.py all          # 5 项复测（O4 需 >100s 预算余量）
1b) python out/perf_mem.py                 # White/SPA 峰值内存（<1GB 预算）
2) python -m pytest tests/test_backtest/test_multiple_testing.py tests/test_backtest/test_multiple_testing_ledger.py tests/test_backtest/test_governance.py tests/test_backtest/test_golden_master.py -q
3) python scripts/spec_runner_adapter.py gate unit-tests --session factorpipe-govbase-step9-20261117
4) AST py39 扫描
```

预期全量：1925 + 8 = **1933 passed / 7 skipped**。**实测：1933 passed / 7 skipped / 13 subtests in 1059.21s（seq 32，exit 0）**。

> 计数口径：T55-T59 为 **5 个测试函数 / 8 个收集用例**（T55 参数化 m=1/7/50 三例、T56 参数化 k=1/3 两例、T57/T58/T59 各一例）；开批时写的「+5 = 1930」按函数数估，实测 `--collect-only` 为 8，故期望修正为 1933，以 gate 实测为准。

---

## §8 未决项与边界

| # | 项 | 状态 |
|---|---|------|
| U1 | O1 预算 1.0s 属重估（下界 0.45s），非「达标 0.1s」 | 明示登记，不粉饰 |
| U2 | 性能烟测阈值取宽松值（CI 抖动），不替代本批实测 | T59 |
| U3 | P3-1 E3 行号 / P3-8 文档表格错位 | 不在本批 |
