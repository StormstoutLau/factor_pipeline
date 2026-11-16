# CHECKLIST — v3.5.0 多断点支持 (Bai-Perron) + Stata 对拍

> **版本**: v1.0 (2026-11-16)
> **对照**: [EXECUTION_V3.5.0](EXECUTION_V3.5.0_MULTIPLE_BREAKPOINTS.md) §3 / §5
> **用法**: 步骤 10 审计逐项确认; 全部 `[x]` 方可发版

## A. 代码

| # | 验收项 | 判据 | 状态 |
|---|--------|------|------|
| C1 | `detect_multiple(lambda_hat, m_max=None)` 存在且可导入 | `from factor_pipeline.modules.factor_health import BreakpointDetector` | [x] |
| C2 | `detect` 逐位不变 | 既有 23 例全绿 | [x] |
| C3 | DP 递推可行域正确 | E5 穷举对拍逐位相同 | [x] |
| C4 | 输出 12 键齐全 | 逐键断言 | [x] |
| C5 | 断点索引映射到原序列 | E7 | [x] |
| C6 | T<30 退化 12 键 | E6 | [x] |
| C7 | 常数序列守卫 | 常数输入 → `n_breaks=0` | [x] |
| C8 | `m_max` 自动下调 | `(m_max+1)*h > T` 时 `m_cap` 生效 | [x] |
| C9 | `diagnose` 零改动 | diff 不含 diagnose | [x] |

## B. 测试 (E1-E8)

| # | 验收项 | 状态 |
|---|--------|------|
| T1 | E1 单断点检测 (n=1) | [x] |
| T2 | E2 两断点检测 (n=2) | [x] |
| T3 | E3 纯噪声 → n=0 | [x] |
| T4 | E4 SSR 单调 + 准则覆盖 + best 范围 | [x] |
| T5 | E5 DP vs 穷举逐位一致 | [x] |
| T6 | E6 T<30 退化 | [x] |
| T7 | E7 NaN 索引映射 | [x] |
| T8 | E8 与 detect 可比 (差 ≤1, SSR 1e-8) | [x] |
| T9 | layer3 文件全绿 (23 + 8 = 31) | [x] |

## C. Stata 对拍

| # | 验收项 | 判据 | 状态 |
|---|--------|------|------|
| S1 | Stata 路径自动探测 | 存在 `C:\Program Files\Stata18\StataMP-64.exe` | [x] |
| S2 | L1 单点 F 一致 | 相对误差 < 1e-8 | [x] |
| S3 | L2 m=0/1/2 全局 SSR + 断点一致 | 断点相同; SSR < 1e-6 | [x] |
| S4 | L3 BIC/LWZ 一致 | < 1e-8; `best_*_m` 相同 | [x] |
| S5 | 真实数据 (β_t) 对拍 | 同上 | [x] |
| S6 | Stata 缺失时 SKIP 且退出码 0 | 实测 `--stata-path` 不存在 → SKIP + exit 0 | [x] |
| S7 | 对拍证据落库 | 报告表 + log 摘要 | [x] |

## D. 文档

| # | 验收项 | 状态 |
|---|--------|------|
| D1 | RESEARCH 记录 Stata 实测事实 (F1-F6) | [x] |
| D2 | DESIGN G1-G14 与代码一致 | [x] |
| D3 | EXECUTION §6 review + §7 实施记录回填 | [x] |
| D4 | ADR-046 (背景/决策/后果/替代方案/对拍证据) | [x] |
| D5 | CHANGELOG v3.5.0 条目 | [x] |
| D6 | PROJECT_STATUS §1 路标 + P2 划项 + 缺陷登记不变 | [x] |
| D7 | DEV_PROGRESS 版本路标 + 模块影响 | [x] |
| D8 | CODE_WIKI 版本 + 版本历史 + 4.13 节 API | [x] |
| D9 | 审计报告 (10 阶段) | [x] |

## E. 兼容

| # | 验收项 | 判据 | 状态 |
|---|--------|------|------|
| K1 | 版本 3.5.0 六锚点 | 版本统一 7 passed + 手工 6/6 | [x] |
| K2 | 缓存代际不变 | `v2.3.0-cache` | [x] |
| K3 | 无新依赖 | `pyproject.toml` 仅版本号变 | [x] |
| K4 | 全量回归 | **1768 passed / 15 skipped / 0 failed** (1131.57s; = 1760 + 8) | [x] |
| K5 | 性能 | T=200 实测 **0.0051s** (< 0.2s) | [x] |
