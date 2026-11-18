# CONSISTENCY REVIEW — v3.6.0 性能包（O1-O5）

> **审查对象**: [EXECUTION_V3.6.0_PERF_PACK.md](../EXECUTION_V3.6.0_PERF_PACK.md) v1.0 ↔
> [CHECKLIST_V3.6.0_PERF_PACK.md](CHECKLIST_V3.6.0_PERF_PACK.md) v1.0
> **上游基线**: ADD 审计 P2-1（5 项超预算）/ `out/govbase_perf.json`
> **时点**: 2026-11-18 开批（实施后按 §5 复核）

---

## §1 反向引用矩阵

| 审计项 | 任务 | 设计决策 | 等价性测试 | 验收 |
|--------|------|---------|-----------|------|
| P2-1 record 10k | O1 | DR-P1（+预算重估） | T57 | CHECKLIST §1 O1 |
| P2-1 BH 100k | O2 | DR-P2 | T55 | CHECKLIST §1 O2 |
| P2-1 RW 1000×1000 | O3 | DR-P3 | T56 | CHECKLIST §1 O3 |
| P2-1 White/SPA | O4 | DR-P4 | T59（烟测） | CHECKLIST §1 O4 |
| P2-1 golden compare | O5 | DR-P5 | T58 | CHECKLIST §1 O5 |

> 5/5 项有「来源 → 任务 → 决策 → 测试 → 验收」链。

## §2 事实 ↔ 变更点

| 事实 | 变更点 | 一致 |
|------|--------|------|
| F1/F2 append 双序列化 + 逐条查询 | governance.py 快路径 + 批量 JOIN | 是 |
| F3 序列化下界 0.45s | O1 预算 1.0s | 是 |
| F4 BH Python 循环 | 向量化 | 是 |
| F5/F7 RW 子矩阵重排 | 前缀统计量 + searchsorted | 是 |
| F6 White/SPA 逐位置循环 | 索引向量化 + 分块 | 是 |
| F8 golden melt | numpy 构造 | 是 |

## §3 计数与版本

| 检查 | 读数 |
|------|------|
| 优化项 | 5（O1-O5） |
| 新增测试 | 5（T55-T59），编号接续 T54 |
| 接口变更 | 0（签名/返回/异常不变） |
| 新增依赖 | 0 |
| 版本 / 缓存 | 3.6.0 / `v2.3.0-cache` 不变 |
| 预期全量 | 1933 passed / 7 skipped（T55-T59 = 5 函数 / 8 用例；开批按 +5 写的 1930 已更正） |

## §4 冲突检查

| 潜在冲突 | 判定 |
|---------|------|
| RW 向量化改变数值 | 否：T56 与朴素参考逐值一致（含 ties） |
| BH 向量化改变数值 | 否：T55 逐值一致（p_adj 与 ties 次序无关；边界 ties 归属沿用旧实现的未定义口径，DR-P2 已登记） |
| White/SPA 随机流变化 | 是（预期）：同 seed 内部确定；无硬编码 p 值断言 |
| `bootstrap_indices` 注入路径 | 不变（不重构该分支） |
| `_to_long` 输出顺序 | T58 断言列序/行序/值逐值一致（`ravel(order="F")` 复刻 melt 的列优先） |
| O1 预算重估是否掩盖未优化 | 否：优化后实测 + 下界推导双证据 |

## §5 实施后复核

| # | 复核项 | 状态 |
|---|-------|------|
| C1 | 5 项复测达标（O1 按重估预算） | 完成：0.724s / 0.0156s / 0.0071s / 7.56s+3.89s / 0.0586s；峰值内存 170.9/170.2MB |
| C2 | T55-T59 全绿；既有 multiple_testing + ledger 全绿 | 完成：定向 4 文件 93 passed（含 8 新用例）、追加 data_contract 101 passed；T58 首版行序修正已登记 |
| C3 | 全量 1933 / 7 skipped | 完成：**1933 passed / 7 skipped / 13 subtests in 1059.21s**（seq 32，exit 0） |
| C4 | 审计 P2-1 / CHECKLIST §5 / PROJECT_STATUS / CHANGELOG 同步 | 完成：4 处均已更新（含 O1 预算重估明示） |
| C5 | 本文件读数与实施后一致 | 完成：§3 预期 1933 已实测确认；§4 ties/circular/行序口径已补 |

**结论（实施后）**：通过 —— 5/5 性能达标（O1 按重估预算）、8 个新增用例全绿、全量 1933/7、0 接口变更；`version-consistency` pass（seq 31）、AST py39 0 违规、12 文档机械校验 0 问题。
