# 审计报告 — v3.4.7 AblationRunner L3/L4 旋钮接线

> **日期**: 2026-11-15
> **版本**: v3.4.7
> **上游**: [RESEARCH_ABLATION_KNOB_WIRING.md](../research/RESEARCH_ABLATION_KNOB_WIRING.md) v1.0 / `docs/private/DESIGN_ABLATION_KNOB_WIRING.md` v1.0 / [EXECUTION_V3.4.7_ABLATION_KNOB_WIRING.md](../EXECUTION_V3.4.7_ABLATION_KNOB_WIRING.md) v1.0
> **清单**: [CHECKLIST_V3.4.7.md](CHECKLIST_V3.4.7.md) / [CONSISTENCY_REVIEW_V3.4.7.md](CONSISTENCY_REVIEW_V3.4.7.md)

---

## §1 结论

| 指标 | 结果 |
|------|------|
| P0 (阻断) | **0** |
| P1 (严重) | **0** |
| P2 (建议) | **3** |
| 审计得分 | **93 / 100 (A)** |
| 判定 | **PASS** — 可发版 |

---

## §2 验收矩阵

### A. 生产管线接线

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| A1 | `PipelineV2Config` +3 字段 | ✅ | `pipelines_v2.py:472-476` |
| A2 | 默认值 `percentile / 1.0 / 99.0` | ✅ | E10 断言通过 |
| A3 | `StaticFactorPipeline` +3 参数 | ✅ | `pipelines_v2.py:706-711` |
| A4 | 仅 percentile/quantile 传分位 | ✅ | `pipelines_v2.py:717-723`; E11 |
| A5 | `_create_pipeline('static')` 注入 | ✅ | `pipelines_v2.py:1324-1327`; E10b |
| A6 | 默认构造与 v3.4.6 逐位一致 | ✅ | E10: `('percentile', 1.0, 99.0)` |
| A7 | dynamic/mixed 未改动 | ✅ | diff 仅 static 分支 |

### B. 消融臂集合

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| B1 | `run_l4_oat` = 9 结果 | ✅ | E1 |
| B2 | outlier 4 / missing 1 / neutralization 3 | ✅ | `ablation_runner.py:1112-1122` |
| B3 | `L4_OUTLIER_MAP` 四映射 | ✅ | E3 (4 参数化用例) |
| B4 | `drop` 关闭 imputer | ✅ | E4 |
| B5 | `industry` 臂不传市值 | ✅ | E5 |
| B6 | L4 trivial = 2 | ✅ | E6 |
| B7 | `run_l3` = 7 结果 | ✅ | E7 |
| B8 | L3 6 臂 trivial + diagnostic | ✅ | E8 |
| B9 | 已删除族不存在 | ✅ | E9 |
| B10 | 不再产生 `_l4_*` 注入 | ✅ | `_apply_l4_overrides` 仅写真实字段; E-none |
| B11 | 报告 `Wiring` 列 | ✅ | `generate_report`; 报告测试通过 |

### C. 测试

| # | 项 | 结果 |
|---|----|------|
| C1 | E1-E12 全绿 | ✅ 新增 `test_ablation_knob_wiring.py` |
| C2 | Red 阶段失败 | ✅ 16 failed (旧实现) |
| C3 | `test_ablation_runner.py` 更新且全绿 | ✅ |
| C4 | `test_ablation_mktcap_alignment.py` 更新且全绿 | ✅ |

### D. 版本与文档

| # | 项 | 结果 |
|---|----|------|
| D1-D6 | 6 处锚点 = 3.4.7 | ✅ `verify_fix3_manual.py` 5/5 |
| D7 | CHANGELOG v3.4.7 段 | ✅ |
| D8 | PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI | ✅ |
| D9 | 缓存代际 `v2.3.0-cache` | ✅ 脚本校验通过 |

### E. 回归

| # | 项 | 结果 |
|---|----|------|
| E1 | 定向 `tests/test_backtest` | ✅ 576 passed, 8 skipped (24:02) |
| E2 | 全量 `pytest tests` | ✅ **1723 passed, 15 skipped** (41:49) |
| E3 | P0/P1 = 0 | ✅ |

---

## §3 代码审计

### 3.1 正确性

- `outlier_method` 四臂映射与 `adapters._OUTLIER_METHODS` 合法集一致
  (`z_score` / `mad` / `percentile`), 不会触发 adapter `ValueError`;
- 未知臂名显式抛 `ValueError`, 不静默降级 (E3b);
- `missing_method` 非 `drop` 显式抛 `ValueError`, 与「删除 median/knn 臂」一致;
- trivial 判定用 `defaults.get(param_name)`, 避免 `KeyError`
  (missing 自由度无默认值, 恒为非平凡)。

### 3.2 默认行为零变更

- 默认三元组 `('percentile', 1.0, 99.0)` 与 v3.4.6 硬编码逐位一致 (E10);
- `outlier_kwargs` 仅在 percentile/quantile 分支构造, 其它方法不新增参数;
- 代码级检查: 全仓 `3.4.7` 之外无残留旧版本锚点; 缓存代际未变。

### 3.3 范围控制

- 未触碰 `compare` / `compare_all` 显著性逻辑;
- 未改动 `dynamic` / `mixed` 管道;
- 未触碰 ADR-040 (因果性) / ADR-042 (统一路由)。

---

## §4 测试审计

| 层级 | 结果 |
|------|------|
| TDD Red | 16 failed — 新用例在原实现上确实失败 (非空转) |
| TDD Green | 3 个测试文件全绿 |
| 定向回归 | 576 passed / 8 skipped |
| 全量回归 | 1723 passed / 15 skipped (基线 1715 + 新增 8) |
| 版本脚本 | 5/5 |

测试覆盖: 臂数、注入映射、市值传递、trivial 口径、BH 空输入、管线默认值、
非 percentile 路径、已删除族缺失 —— 与 DESIGN §5 E1-E12 一一对应。

---

## §5 文档一致性

[CONSISTENCY_REVIEW_V3.4.7.md](CONSISTENCY_REVIEW_V3.4.7.md): 数字 / 符号 / 语义 / 引用
四维一致, 判定 PASS。研究文档的 10 个可接线臂 vs 本版 4 个, 已在 DESIGN §2 显式解释。

---

## §6 建议 (P2, 不阻断)

| # | 建议 | 理由 |
|---|------|------|
| P2-1 | 未传市值时 `neutralization='industry+mktcap'` 臂与 B3 同口径, 建议 runner 层打日志或在报表标注 | 该场景下 1 个非平凡臂实际 Δ≈0, 可能干扰 BH 分母; 当前文档已说明默认口径, 风险低 |
| P2-2 | `AblationConfig` 仍有 8 个无消费者字段 (`ewma_*` / `scaler_method` / `time_align` / `data_window` 等) | 已注释标记; 建议下一大版本删除, 或迁移为独立「评估口径」消融任务 |
| P2-3 | EWMA / 标准化 / 插补策略若要消融, 应由独立任务设计 | 会改变指标序列形状或历史数值, 不适合并入本次接线 |

---

## §7 判定

**PASS**。P0/P1 为 0, 全量回归 1723 passed, 默认生产行为零变更,
臂集合与真实自由度一致, 文档与实现一致。可提交发版。

---

## §8 独立异构复审 (2026-11-15, 三路只读 subagent + 主会话补核)

### 8.1 各路结论

| 复审路 | 结论 | 摘要 |
|--------|------|------|
| 代码语义路 (subagent + 主会话补核) | **PASS_WITH_FIXES** | subagent 未产出结构化结论, 关键项由主会话按同一清单补核 (见 8.2); 唯一发现 R-1 已收口 |
| 测试质量路 (subagent + 主会话补核) | **PASS** | mock 签名与真实 `run_single` 兼容; Red 有效性成立; 无残留已删除族断言; 负向断言 (`not hasattr`) 为有效断言而非恒真 |
| 文档契约路 (subagent) | **PASS** | 6 处版本锚点全为 3.4.7; 3.4.6 残留均为合法历史记载 (CHANGELOG 历史段/docstring/历史行); 文档数字与事实一致 |

### 8.2 主会话补核记录 (代码语义路 + 测试质量路)

| 检查项 | 证据 | 结论 |
|--------|------|------|
| 默认零行为变更 | `git show HEAD:pipelines_v2.py`: 旧硬编码 `method='percentile', percentile_lower=1.0, percentile_upper=99.0` 与新默认三元组逐位一致 | ✅ |
| L4_OUTLIER_MAP 合法性 | `z_score`/`mad`/`percentile` 均在 [adapters.py:50-52](../../adapters.py#L50-L52) `_OUTLIER_METHODS`; 非 percentile/quantile 时分位点置 None ([adapters.py:387-429](../../adapters.py#L387-L429)) | ✅ |
| 死注入清理 | 全仓 grep `_l3_ewma/_l3_winsorize/_l3_correction/_l4_outlier_method/_l4_scaler/_l4_imputer/_l4_time_align/_l4_data_window` → 仅剩测试负向断言 | ✅ (R-1 收口后) |
| `StaticFactorPipeline` 调用方兼容 | 全仓 15 处实例化均为 kwargs 或无参; 新参数追加尾部安全 | ✅ |
| `run_l4_oat` trivial/市值转发 | trivial 判定用 `defaults.get(param_name)` (missing 无默认 → 恒非平凡); `industry` 臂 `arm_kwargs={}` 跳过市值, 其余臂转发 | ✅ |
| `run_l3` 市值转发 | 全臂统一 `**extra_kwargs` | ✅ |
| 报告 Wiring 列 | 表头/分隔行/数据行均 10 列; `getattr(..., 'wired')` 回退 | ✅ |
| mock 签名兼容 | 真实 `run_single` ([ablation_runner.py:446-452](../../backtest/ablation_runner.py#L446-L452)) 接受 `market_cap_data` kwarg, 与三处 monkeypatch 兼容 | ✅ |
| Red 有效性 | `git show HEAD:pipelines_v2.py` 无任何 `static_outlier` 命中 → 新断言在旧实现下必然 AttributeError | ✅ |
| 已删除族测试残留 | grep 三测试文件无 `L3_ewma/L3_threshold_scale/L3_winsorize/L3_correction/L4_scaler_method/L4_time_align/L4_data_window` 正向断言 | ✅ |

### 8.3 复审发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| R-1 | P2 | [ablation_runner.py:674](../../backtest/ablation_runner.py#L674) 仍写 `modified_config._l4_neutralization` — 全仓无消费者, 且与审计 B10「不再产生 `_l4_*` 注入」矛盾 | ✅ 已删除死注入 (中性化口径完全由 runner 层 `market_cap_data` 转发控制); EXECUTION §4.5 同步; 新增负向断言锁定; 定向回归 109 passed |
| R-2 | P3 | subagent 三路均未产出结构化结论, 仅返回代码片段 | 既有惯例 (v3.4.3 复审相同), 主会话按同一清单补核, 接受 |

**复审总评: PASS_WITH_FIXES → 已收口 (P0/P1 = 0; R-1 已修, R-2 接受)**

> **R-1 收口 (2026-11-15)**: `_apply_l4_overrides` 中性化分支重构为仅处理 `'none'`;
> `industry` / `industry+mktcap` 臂不再写任何 config 属性。
> 新增 [test_l4_neutralization_writes_no_config_attr](../../tests/test_backtest/test_ablation_knob_wiring.py)
> 锁定; 三测试文件定向回归 **109 passed**。
