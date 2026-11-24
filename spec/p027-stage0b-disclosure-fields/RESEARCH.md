# P-027 Stage 0b — 披露字段登记（RESEARCH）

---
id: p027-stage0b-disclosure-RESEARCH
type: research
version: 1.0
status: verified
date: 2026-11-24
depends: [p027-tau-fusion-freeze-SESSION]
upstream: null
---

## §1 目标与范围

在 P-027 Stage 0 文档冻结与 Stage 1 探针（全失败）之后，补齐「τ 仅展示」所需的披露字段：

| 字段 | 落点 | 目的 |
|---|---|---|
| `weights_version` | `check_endogeneity` 顶层 + S2/S3/S4 + `final_assessment` | 权重可追溯；跨配置不可比 |
| `effective_weights` | 同上 | 仅启用方法的归一化权重 |
| `input_stage` | S2 / S3 | 声明阶段输入（imputed / neutralized） |
| `s4_input_stage` + `stage_fallback` | S4 / `final_assessment` | 区分「解耦后」与「回退到插补后」 |
| `experimental` / `heuristic` / `weights_version` / `effective_weights` | E5 输出 | 防止被当作「内生性已修正」 |

**非目标**：改 τ 数值、改权重、改默认路径、新增消费者、Layer 3 交互。

## §2 代码事实（E1，仓内）

| # | 事实 | 位置 |
|---|---|---|
| F-1 | 权重硬编码 `0.4/0.3/0.2/0.1`，按启用方法归一化 | `threat_assessor.py` L31-L36 / L67-L79 |
| F-2 | orchestrator 无参构造 assessor，无权重配置 | `diagnostic_orchestrator.py` L63 |
| F-3 | `check_endogeneity` 未记录权重/阶段字段 | `pipelines_v2.py` L1877-L1925（改前） |
| F-4 | S4 在未传 `decoupled_factor` 时静默回退 `imputed_factor` | `pipelines_v2.py` L1912 |
| F-5 | E5 输出仅 4 键（l1/l2/l3/threat_tau） | `pipelines_v2.py` L2069-L2130（改前） |
| F-6 | 默认 E3/E5 全关 | `pipelines_v2.py` L546 / L574 |
| F-7 | Stage 1 判定 τ 仅展示 | [TAU_FUSION_STAGE1_P027.md](../../docs/analysis/TAU_FUSION_STAGE1_P027.md) |
| F-8 | 现有测试无 dict 全等断言，追加键向后兼容 | `tests/test_endogeneity_check/` / `tests/test_endogeneity_regularizer/` |

## §3 外部依据

本批为内部输出契约补充，**不需要外部学术锚点**；A 类断言均为仓内代码事实（F-1~F-8）。不引用外部来源。

## §4 结论

字段只做披露，不参与 τ 计算；实现为纯追加键，默认数值输出不变。Stage 0b 不改变 P-027 的 Stage 2 判定（τ 仅展示）。
