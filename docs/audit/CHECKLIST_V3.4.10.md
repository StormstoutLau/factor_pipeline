# CHECKLIST v3.4.10 — HAC 检验 NaN 过滤

> **版本**: v1.0 (2026-11-16)
> **对照工件**: [EXECUTION v1.0](../EXECUTION_V3.4.10_HAC_NAN_FILTER.md) /
> [RESEARCH v1.0](../research/RESEARCH_HAC_NAN_FILTER.md) / DESIGN v1.0
> **使用方式**: 步骤 10 审计时逐项勾选, 任一项未勾选即不得发版。

## A. 代码落地 (E1)

- [x] A1 入口新增 `finite_mask = np.isfinite(a) & np.isfinite(b)` 联合掩码
- [x] A2 掩码在长度对齐**之后**、任何矩条件计算**之前**执行
- [x] A3 有效配对 `< 3` 时返回 `(0.0, 1.0)`, 不返回 NaN
- [x] A4 `T = n_valid` 重赋值后, 带宽 `q` 与全部 `/T` 归一化使用清洗后样本
- [x] A5 丢弃非有限配对时输出 1 条 `logger.debug`
- [x] A6 docstring 声明 Equal Spacing 口径 + 压缩时间轴局限 + Datta & Du (2012)
- [x] A7 公开签名 / 返回类型不变
- [x] A8 `compare` / `compare_all` / `circular_block_bootstrap` / `mean_diff_hac_statsmodels` 零改动

## B. 测试 (E1-E6)

- [x] B1 E1 同位置 NaN → 与显式删除这些时点的干净序列数值等价 (`rel=1e-12`), p 有限
- [x] B2 E2 不同位置 NaN → 等于联合掩码值, 且 ≠ 逐序列独立删除值
- [x] B3 E3 有效配对 2 个 → `(0.0, 1.0)`
- [x] B4 E4 全 NaN 序列 → `(0.0, 1.0)`
- [x] B5 E5 `±inf` 与 NaN 等价, 结果有限
- [x] B6 E6 `compare` 集成: 两臂 LS 各含 1 个 NaN (位置不同) → `p_value_hac` 有限 ∈[0,1] 且等于直接调用清洗后序列
- [x] B7 Red 阶段确认失败 (**6 failed / 5 passed**), Green 阶段全绿 (**11 passed**)

## C. 回归

- [x] C1 既有 `TestLedoitWolfHAC` 5 用例全绿 (无缺失输入零影响)
- [x] C2 定向回归: `tests/test_backtest/test_ablation_runner.py` 全绿 (**89 passed**)
- [x] C3 定向回归: `tests/test_backtest` 全绿 (**594 passed / 8 skipped**, 基线 588 → +6)
- [x] C4 全量回归 **1741 passed / 15 skipped / 0 failed** (基线 1735 → +6)

## D. 文档

- [x] D1 CHANGELOG 新增 v3.4.10 段
- [x] D2 PROJECT_STATUS 路标 + P2 条目改为已完成
- [x] D3 DEV_PROGRESS 路标追加 v3.4.10
- [x] D4 EXECUTION §5 验收表填入实测值
- [x] D5 MAD 实验报告 §6 O1 标注「已由 v3.4.10 修复」

## E. 一致性与发版

- [x] E1 六锚点均为 3.4.10 (版本测试 7 passed + 手工 6/6)
- [x] E2 文档数字与实测一致 (新增用例 6, 既有 5, 单文件 89, 目录 594)
- [x] E3 CONSISTENCY_REVIEW 判定 PASS
