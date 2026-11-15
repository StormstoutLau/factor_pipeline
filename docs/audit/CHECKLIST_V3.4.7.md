# 验收清单 — v3.4.7 AblationRunner L3/L4 旋钮接线

> **日期**: 2026-11-15
> **上游**: [RESEARCH](../research/RESEARCH_ABLATION_KNOB_WIRING.md) / `docs/private/DESIGN_ABLATION_KNOB_WIRING.md` / [EXECUTION](../EXECUTION_V3.4.7_ABLATION_KNOB_WIRING.md)

## A. 生产管线接线

- [x] A1 `PipelineV2Config` 新增 `static_outlier_method='percentile'`
- [x] A2 新增 `static_outlier_percentile_lower=1.0` / `_upper=99.0`
- [x] A3 `StaticFactorPipeline.__init__` 接受 3 个同名可选参数
- [x] A4 仅 `percentile` / `quantile` 方法传分位参数
- [x] A5 `_create_pipeline('static')` 从 config 注入三字段
- [x] A6 默认构造的 outlier 步骤参数 = `('percentile', 1.0, 99.0)` (与 v3.4.6 逐位一致)
- [x] A7 `dynamic` / `mixed` 管道未改动

## B. 消融臂集合

- [x] B1 `run_l4_oat` 返回 9 (B3 + 8)
- [x] B2 outlier 4 臂 / missing 1 臂 / neutralization 3 臂
- [x] B3 `L4_OUTLIER_MAP` 四映射与 DESIGN §4.1 一致
- [x] B4 `missing_method='drop'` 关闭 imputer
- [x] B5 `neutralization='industry'` 臂不传市值
- [x] B6 L4 trivial = 2 (`winsorize_1pct` + 默认中性化)
- [x] B7 `run_l3` 返回 7 (B3 + 6 CUSUM)
- [x] B8 CUSUM 6 臂全 `_is_trivial=True` 且 `_wiring_status='diagnostic'`
- [x] B9 L3 无 `ewma` / `threshold` / `winsorize` / `correction` 臂
- [x] B10 `_apply_l4_overrides` 不再产生 `_l4_*` 属性注入
- [x] B11 报告含 `Wiring` 列

## C. 测试

- [x] C1 新增 `test_ablation_knob_wiring.py` E1-E12 全绿
- [x] C2 Red 阶段确认新用例在原实现上失败
- [x] C3 `test_ablation_runner.py` 中 L4/L3 段已更新且全绿
- [x] C4 `test_ablation_mktcap_alignment.py` 臂数断言已更新且全绿

## D. 版本与文档

- [x] D1 `__init__.py` = 3.4.7
- [x] D2 `pyproject.toml` = 3.4.7
- [x] D3 `config_v2.py` 默认 version = 3.4.7
- [x] D4 `reporting.py` pipeline_version = 3.4.7
- [x] D5 `test_fix3_version_unification.py` EXPECTED_VERSION = 3.4.7
- [x] D6 `verify_fix3_manual.py` EXPECTED_VERSION = 3.4.7
- [x] D7 CHANGELOG 新增 v3.4.7 段
- [x] D8 PROJECT_STATUS / DEV_PROGRESS / CODE_WIKI 同步
- [x] D9 缓存代际仍为 `v2.3.0-cache`

## E. 回归

- [x] E1 定向回归 `tests/test_backtest/` 全绿
- [x] E2 全量回归 `pytest tests -q` 无 failed (基线 1715 passed / 15 skipped)
- [x] E3 audit 报告 P0/P1 = 0
