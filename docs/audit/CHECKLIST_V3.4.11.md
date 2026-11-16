# CHECKLIST v3.4.11 — 技术债小包

> **版本**: v1.0 (2026-11-16)
> **对照工件**: [EXECUTION v1.0](../EXECUTION_V3.4.11_TECH_DEBT_PACK.md)
> **使用方式**: 步骤 10 审计时逐项勾选, 任一项未勾选即不得发版。

## A. 代码落地

- [x] A1 `ledoit_wolf_hac_test` 签名移除 `alpha`; docstring Args 同步删除
- [x] A2 `compare` 调用改为两参数; `self.alpha` 判定逻辑不动
- [x] A3 `mean_diff_hac_statsmodels` 增加成对 `isfinite` 掩码
- [x] A4 `mean_diff_hac_statsmodels` 有效配对 <3 → `(0.0, 1.0)`; `maxlags` 基于清洗后 n
- [x] A5 `PipelineV2Config` 新增 `static_outlier_adaptive_threshold=True` / `static_outlier_max_outlier_frac=0.05`
- [x] A6 `StaticFactorPipeline` 新增两参数, 非分位方法透传到 detector
- [x] A7 `_create_pipeline('static')` 转发两字段
- [x] A8 percentile / quantile 路径参数不变

## B. 测试

- [x] B1 E1 不同位置 NaN → 等于联合掩码结果, 有限
- [x] B2 E2 有效配对 <3 → `(0.0, 1.0)`
- [x] B3 E3 默认 config / adapter kwargs = `True` / `0.05`
- [x] B4 E4 `adaptive_threshold=False` 传到 adapter
- [x] B5 E5 `_create_pipeline` 转发非默认值
- [x] B6 Red **5 failed / 3 passed** → Green **8 passed**

## C. 回归

- [x] C1 `tests/test_backtest/test_ablation_runner.py` 全绿
- [x] C2 `tests/test_backtest/test_ablation_knob_wiring.py` 全绿
- [x] C3 `tests/test_backtest` 全绿 (**599 passed / 8 skipped**, 基线 594 → +5)
- [x] C4 全量回归 **1746 passed / 15 skipped / 0 failed** (基线 1741 → +5)

## D. 文档

- [x] D1 CHANGELOG 新增 v3.4.11 段
- [x] D2 PROJECT_STATUS 路标 + 完成表 + 非生产解耦器候选标注「不修复」
- [x] D3 DEV_PROGRESS 路标追加 v3.4.11
- [x] D4 CODE_WIKI 版本 + 配置字段说明
- [x] D5 MAD 实验 §6 O2 标注「已由 v3.4.11 提供参数化」

## E. 一致性与发版

- [x] E1 六锚点均为 3.4.11 (版本测试 7 passed + 手工 6/6)
- [x] E2 文档数字与实测一致 (新增 5 例; 定向 123 + 46)
- [x] E3 CONSISTENCY_REVIEW 判定 PASS
