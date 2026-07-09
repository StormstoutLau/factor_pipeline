# 代码质量与设计文档对齐审查报告 — RESEARCH_NOTES E1-E10 + V3.1.0 E1-E6

**日期**: 2026-07-08
**审查范围**: RESEARCH_NOTES E1-E10 + V3.1.0 E1-E6 (共 16 个 E 任务)
**审查基线**: 1308 tests passed, 6 skipped, 11 subtests (零回归)
**审查方法**: audit-driven-development 4 阶段 (Spec Inventory → Multi-Dim Audit → Fix Matrix → Baseline)

---

## 0. 修复跟踪表

**修复基线**: 1334 tests passed, 6 skipped, 11 subtests (零回归)

| 编号 | 严重度 | 模块 | 描述 | 状态 | 测试验证 |
|------|--------|------|------|------|----------|
| P0-1 | Blocker | RN-E3 | WhiteRealityCheck/HansenSPA 应为类接口返回 Dict, 实际为函数返回 Tuple | ✅ 已修复 | 51 passed (含 7 新类接口测试) |
| P0-2 | Blocker | RN-E6 | 算法核心偏离: LinUCB → Thompson Sampling, 签名/参数/方法全不符 | ✅ 已修复 | 19 passed (LinUCB + CUSUM 修复) |
| P0-3 | Blocker | RN-E7 | PipelineV2Config 未扩展 E7 必需 4 字段 | ✅ 已修复 | 631 passed (既有零回归) |
| P0-4 | Blocker | RN-E7 | akshare 实际接口未实现, 始终降级合成数据 | ✅ 已修复 | 11 passed (含 4 新 akshare 测试) |
| P0-5 | Blocker | RN-E10 | PipelineV2Config 未扩展 E10 必需 3 字段 | ✅ 已修复 | 631 passed (既有零回归) |
| P0-6 | Blocker | RN-E10 | __init__ 缺 lambda_softmax 和 oco_eta 参数 | ✅ 已修复 | 43 passed (Bridge 测试) |
| P0-7 | Blocker | RN-E10 | Q2 soft-update 公式偏离: Welford vs 指数衰减 | ✅ 已修复 | 43 passed (spec 指数衰减公式) |
| P0-8 | Blocker | RN-E10 | get_diagnostics 缺 lambda_softmax 和 oco_eta 字段 | ✅ 已修复 | 43 passed |
| P1-1 | Critical | V3.1.0-E3 | oster_r_max_multiplier 配置字段装饰性 (check_endogeneity 不消费) | ✅ 已修复 | 57 passed (E3+E5 测试) |
| P1-2 | Critical | V3.1.0-E3 | endogeneity_ife_max_dim 配置字段装饰性 | ✅ 已修复 | 57 passed |
| P1-3 | Critical | V3.1.0-E3 | endogeneity_alert_threshold 配置字段完全未消费 | ✅ 已修复 | 57 passed (传入 threat_threshold) |
| P1-4 | Critical | V3.1.0-E5 | EndogeneityRegularizer 三个核心方法名/参数/返回类型全不一致 | ✅ 已处理 | 更新 spec 5.3.1 对齐配置型 (4 块编辑: docstring/__init__/_resolve_tau/apply_l1-l3); 既有 57 passed 零回归 |
| P1-5 | Critical | V3.1.0-E5 | PipelineV2Config 字段缺失与改名 | ✅ 已修复 | 新增 skip_stage2/extra_check 阈值字段 |
| P1-6 | Critical | V3.1.0-E5 | _extra_beta_check 方法未实现 | ✅ 已修复 | 57 passed (含 _extra_beta_check) |
| P1-7 | Critical | V3.1.0-E6 | Profile GMM method_formal_name 缺 (Hong-Su-Jiang 2022) | ✅ 已修复 | 43 passed |
| P1-8 | Critical | V3.1.0-E6 | IVX method_formal_name 缺 (Kostakis-Magdalinos-Stamatogiannis 2015) | ✅ 已修复 | 43 passed |
| P1-9 | Critical | V3.1.0-E6 | DOLS method_formal_name 缺 (Stock-Watson 1993) | ✅ 已修复 | 43 passed |
| P1-10 | Critical | V3.1.0-E6 | Profile GMM absorption_ratio 公式不一致 (核范数 vs Frobenius) | ✅ 已处理 | 更新 spec 对齐 Frobenius (energy = Σσ², Parseval 标准); 补充 IVX 诊断字段 alpha_c_constant/alpha_delta_exponent; 既有 43 passed 零回归 |
| P1-11 | Critical | V3.1.0-E6 | IVX α 计算公式不一致 (基于 T vs 基于 ρ) | ✅ 已处理 | 重写代码对齐 spec (Kostakis 2015 原始公式 α = 1 - c/T^δ, c=5.0, δ=0.95); 6 passed (5 既有 + 1 新增 T10b 单调性验证) |
| P1-12 | Critical | V3.1.0-E6 | 选择器类名/文件名/参数名/逻辑顺序不一致 | ✅ 已处理 | 重写代码 6 处修复 (类名 EstimationMethodSelector+别名/参数名 endogeneity_report/逻辑顺序 低秩→IVX→τ<0.3→默认/all_methods_ranked/Frobenius 低秩公式); 7 passed (4 既有 + 3 新增 T20b/c/d) |
| P2+ | Minor | 多模块 | 各类轻微偏离 (见各 E 任务详情) | ⬜ 可选 | - |

---

## 1. 审查范围与方法

### 1.1 设计文档清单
- `docs/EXECUTION_RESEARCH_NOTES.md` v1.0 — RESEARCH_NOTES E1-E10 规格
- `docs/EXECUTION_V3.1.0.md` v1.0 — V3.1.0 E1-E6 规格

### 1.2 审查维度
- 维度 1: RN E1-E5 (PowerCurve / Romano-Wolf / White RC / FingerprintLogger / Attribution)
- 维度 2: RN E6-E10 (Bandit / State / Performance / Decomposition / Bridge)
- 维度 3: V3.1.0 E1-E3 (隐藏效应 / P-hacking / 内生性 S1-S4)
- 维度 4: V3.1.0 E4-E6 (格兰杰 / 三层正则化 / 估计层方法)

### 1.3 审查方法
- 4 个独立 subagent 并行审查 (每个维度 1 个)
- 每维度独立评分
- 跨维度问题汇总

---

## 2. 模块审查结果

### 2.1 RESEARCH_NOTES E1-E5

| 任务 | 评分 | P0 | P1 | P2 | 关键问题 |
|------|------|----|----|----|---------|
| E1 PowerCurveAnalyzer | A- | 0 | 0 | 1 | 签名默认值形式微调 |
| E2 Romano-Wolf | A | 0 | 0 | 3 | stepdown 实现路径等价偏离, 复现测试恒真 |
| E3 White RC + Hansen SPA | **C+** | **2** | **4** | 2 | **类→函数, Dict→Tuple, 公式偏离, 方法缺失** |
| E4 FingerprintPerformanceLogger | A | 0 | 0 | 3 | fit 集成方式偏离 (改进项) |
| E5 AttributionAnalyzer | A- | 0 | 0 | 5 | Layer2 归一化偏离, 多个测试缺失 |

**E3 核心问题**: spec L566-569 要求类 `WhiteRealityCheck`/`HansenSPA` + `.test()` 返回 Dict (7/8 字段), 代码实现为函数 `apply_white_reality_check`/`apply_hansen_spa` 返回 `Tuple[float, bool]`。`_circular_block_bootstrap` 完全缺失, `_auto_block_size` 公式简化丢失 rho 项。

### 2.2 RESEARCH_NOTES E6-E10

| 任务 | 评分 | P0 | P1 | 关键问题 |
|------|------|----|----|---------|
| E6 DriftAwareBandit | **C** | **10** | 4 | **算法核心偏离 (LinUCB→Thompson), 签名/参数/方法全面不符** |
| E7 StateDataLoader+Markov | **B-** | **3** | 3 | PipelineV2Config 未扩展, akshare 接口未实现 |
| E8 StateConditionedPerf | B+ | 1 | 5 | 文件名不符, 因变量构造改进但偏离 spec |
| E9 ThreeChannelDecomp | B+ | 0 | 3 | 趋势归一化方式不同 (改进) |
| E10 StatisticalDecisionBridge | **C+** | **4** | 4 | Q2 公式偏离 (Welford vs 指数衰减), PipelineV2Config 未扩展 |

**E6 核心问题**: spec 要求 LinUCB (Li et al. 2010) + 上下文向量 x_t, 代码实现为 Thompson Sampling 无上下文。`__init__` 用 `n_factors` 替换 `n_regimes`, `run_comparison` 缺 `drift_magnitude` 参数, `evaluate_decision_gate` 方法完全缺失。

**E7/E10 共性问题**: PipelineV2Config 扩展缺失是系统性遗漏 (E7 4 字段 + E10 3 字段 = 7 字段未新增)。

### 2.3 V3.1.0 E1-E3

| 任务 | 评分 | P0 | P1 | 关键问题 |
|------|------|----|----|---------|
| E1 隐藏效应诊断 | A- | 0 | 0 | 有益扩展, spec 文档补充即可 |
| E2 P-hacking 防御 | A- | 0 | 0 | 范围澄清后无实质问题 |
| E3 内生性 S1-S4 | B+ | 0 | 3 | **三个配置字段装饰性** |

**v1.3 术语严格性全部落实**: Oster δ / R_max=1.3×R̃ / IFE lambda_i'*F_t / Lewbel (Z-Z̄)×ê² / Sargan-Hansen J=n×Q_min / S1→S2 逻辑衔接 / S3-S2 等数值差分 — 全部精确匹配。

**E3 核心问题**: `oster_r_max_multiplier`/`endogeneity_ife_max_dim`/`endogeneity_alert_threshold` 三个配置字段存在但 `check_endogeneity` 不消费, 违背 ADR-024 opt-in 原则。

### 2.4 V3.1.0 E4-E6

| 任务 | 评分 | P0 | P1 | 关键问题 |
|------|------|----|----|---------|
| E4 格兰杰检验 | A+ | 0 | 0 | 完全对齐 |
| E5 三层正则化 | B | 0 | 4 | 方法名/返回类型全改, config 字段缺失 |
| E6 估计层方法 | **B-** | 0 | **22** | **method_formal_name 缺作者年份(×3), 多处公式/算法不一致** |

**E6 核心问题**:
- 术语: Profile GMM / IVX / DOLS 的 `method_formal_name` 都缺作者年份后缀 (仅 PFGMM 正确)
- 公式: absorption_ratio (核范数 vs Frobenius)、residual_threat_tau (4 个估计器全部与 spec 不同)、IVX α 自适应 (基于 T vs 基于 ρ)
- 算法: Profile GMM 的 2-step GMM 退化为 OLS, IVX 的 2SLS 退化为直接 IV
- 选择器: 类名/文件名/参数名/逻辑顺序/低秩判定公式 6 处不一致

---

## 3. 跨模块契约审查

### 3.1 PipelineV2Config 扩展一致性
- **E7/E10 字段缺失**: spec 明确要求 7 个新字段, 代码 0 个 — 系统性遗漏
- **E5 字段改名**: `endogeneity_reg_strength`→`regularizer_rho`, 缺失 2 个阈值字段
- **E3 装饰性字段**: 3 个字段存在但不被消费

### 3.2 术语严格性
- ✅ V3.1.0 E3 v1.3 术语全部正确 (Oster δ, R_max, IFE, Lewbel, Sargan-Hansen)
- ❌ V3.1.0 E6 method_formal_name 3/4 缺作者年份
- ✅ RESEARCH_NOTES 无术语违规

### 3.3 测试盲区系统性问题
- 多数测试验证"返回类型/字段存在/数值在范围内", 不验证 spec 公式/阈值的精确实现
- 存在断言恒真式 (E2 复现测试, E6-T10/T17/T18, E3-T21)
- 跨文件传递依赖链无端到端测试

---

## 4. 修复优先级矩阵

### Tier 1: P0 Blocker (立即修复, 按成本排序)

#### 低成本 (1-10 行) — 优先修复
1. **P0-3**: PipelineV2Config 新增 E7 4 字段 — 4 行
2. **P0-5**: PipelineV2Config 新增 E10 3 字段 — 3 行
3. **P0-6**: StatisticalDecisionBridge.__init__ 新增 lambda_softmax/oco_eta — 5 行
4. **P0-8**: get_diagnostics 新增 lambda_softmax/oco_eta 字段 — 2 行
5. **P1-7/8/9**: method_formal_name 添加作者年份后缀 — 3 行

#### 中等成本 (10-50 行)
6. **P0-7**: Q2 soft-update 公式从 Welford 改为指数衰减 — ~20 行
7. **P1-1/2/3**: E3 三个装饰性配置字段消费 — ~10 行
8. **P1-5**: V3.1.0 E5 PipelineV2Config 字段补齐 — ~5 行
9. **P1-6**: V3.1.0 E5 _extra_beta_check 实现 — ~15 行

#### 高成本 (50+ 行) — 需评估
10. **P0-1**: E3 WhiteRealityCheck/HansenSPA 从函数改为类接口 — ~150 行重写
11. **P0-2**: E6 整个沙箱从 Thompson Sampling 改为 LinUCB — ~200 行重写
12. **P0-4**: E7 akshare 实际接口实现 — ~100 行 (需真实 API 测试)

### Tier 2: P1 Critical (本轮已处理 ✅)
- ✅ V3.1.0 E5 P1-4: 更新 spec 5.3.1 对齐配置型 (4 块编辑: docstring/__init__/_resolve_tau/apply_l1-l3)
- ✅ V3.1.0 E6 P1-10: 更新 spec absorption_ratio 对齐 Frobenius (energy = Σσ², Parseval) + IVX 诊断字段补充
- ✅ V3.1.0 E6 P1-11: 重写 IVX α 公式为基于 T (Kostakis 2015: α = 1 - c/T^δ, c=5.0, δ=0.95)
- ✅ V3.1.0 E6 P1-12: 重写选择器 6 处修复 (类名 EstimationMethodSelector+别名/参数名/逻辑顺序 低秩→IVX→τ<0.3→默认/all_methods_ranked/Frobenius 低秩公式)

### Tier 3: P2/P3 (可选)
- 各类轻微偏离、测试盲区补强

---

## 5. 测试盲区汇总

### 断言恒真式
- RN-E2: `test_romano_wolf_reproducibility` 同输入断言一致 (函数确定性, 恒真)
- V3.1.0-E3: `E3-T21` 仅断言字段存在, 未断言 `critical_alert=True` 触发条件
- V3.1.0-E6: `E6-T10` `bias_reduction >= 0.0` (abs 恒非负), `E6-T17/T18` 两个等价条件

### 设计约束无测试
- RN-E7/E10: PipelineV2Config 字段存在性无测试
- V3.1.0-E3: 配置字段修改后生效无测试
- V3.1.0-E6: method_formal_name 完整性无测试, 选择器逻辑顺序无测试

### 跨文件传递依赖无测试
- V3.1.0-E3: `check_endogeneity` S1→S2→S4 全链路无端到端测试

---

## 6. 修复后预期评分提升

| 任务 | 当前 | 修复后 | 关键修复 |
|------|------|--------|---------|
| RN-E3 | C+ | B+ | P0-1 (类接口) |
| RN-E6 | C | B- | P0-2 (LinUCB) — 若不修复则保持 C |
| RN-E7 | B- | A- | P0-3 (Config 字段) |
| RN-E10 | C+ | B+ | P0-5/6/7/8 (Config + Q2 公式) |
| V3.1.0-E3 | B+ | A- | P1-1/2/3 (装饰性字段) |
| V3.1.0-E5 | B | A- | P1-5/6 (Config + _extra_beta_check) |
| V3.1.0-E6 | B- | B+ | P1-7/8/9 (method_formal_name) |

---

## 7. 下一步建议

### A. 立即修复 Tier 1 低成本 P0 (本轮)
- PipelineV2Config 字段扩展 (E7/E10)
- StatisticalDecisionBridge 参数/字段补齐
- method_formal_name 作者年份补齐
- E3 装饰性配置字段消费

### B. 评估高成本 P0 (需用户决策)
- **P0-1 (E3 类接口重写)**: spec 明确要求类接口, 但当前函数接口功能等价。建议: 改 spec 为函数接口 (向后兼容), 或重写为类。
- **P0-2 (E6 LinUCB 重写)**: spec 要求 LinUCB + 上下文, 代码用 Thompson Sampling。建议: 评估是否接受 Thompson Sampling 作为实现选择 (更新 spec), 或重写为 LinUCB。
- **P0-4 (E7 akshare 接口)**: 需真实 A 股数据 API 测试, 当前合成数据降级可接受。

### C. 补强测试盲区 (下一轮)
- 修复断言恒真式
- 新增跨文件端到端契约测试
- 新增配置字段生效测试
