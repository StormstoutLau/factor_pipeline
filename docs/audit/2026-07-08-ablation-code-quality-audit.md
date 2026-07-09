# 代码质量与设计文档对齐审查报告 — ABLATION v3.0.0

**日期**: 2026-07-08
**审查范围**: ABLATION v3.0.0 E1-E7 (四层消融对照机制)
**审查基线**: 90 tests passed (ABLATION E1-E7)
**审查方法**: audit-driven-development 4 阶段 (Spec Inventory → Multi-Dimensional Audit → Fix Priority Matrix → Fix Baseline)

---

## 0. 修复跟踪表

| 编号 | 严重度 | 模块 | 描述 | 状态 | 测试验证 |
|------|--------|------|------|------|----------|
| P0-1 | Blocker | pipelines_v2 | module_enabled 透传完全缺失 (死字段) | ✅ 已修复 | 136 passed |
| P0-2 | Blocker | ablation_runner | L2 路由覆盖 _override_routing 未实现 | ✅ 已修复 | 91 passed |
| P0-3 | Blocker | ablation_runner | L3 参数注入 _apply_l3_overrides 未实现 | ✅ 已修复 | 91 passed |
| P0-4 | Blocker | ablation_runner | L4 OAT 参数注入 _apply_l4_overrides 未实现 | ✅ 已修复 | 91 passed |
| P1-1 | Critical | test_module_enabled | TestPipelineModuleEnabled (4 测试) 缺失 | ✅ 已修复 | 随 P0-1 |
| P1-2 | Critical | test_module_enabled | TestBackwardCompat (2 测试) 缺失 | ✅ 已修复 | 随 P0-1 |
| P1-3 | Critical | ablation_runner | L3 缺失 correction_method 消融 (3 配置) | ✅ 已修复 | 99 passed |
| P1-4 | Critical | ablation_runner | L3 CUSUM 用组合对而非 OAT | ✅ 已修复 | 99 passed |
| P1-5 | Major | ablation_runner | L3 winsorize 缺失 MAD 选项 | ✅ 已修复 | 99 passed |
| P1-6 | Major | ablation_runner | run_l2 缺失 b3_full_result 参数 (M6 未完整) | ✅ 已修复 | 99 passed |
| P1-7 | Major | ablation_runner | M5 平凡比较标注未实现 | ✅ 已修复 | 99 passed |
| P1-8 | Major | ablation_runner | _collect_rho_steps ortho before==after (恒 1.0) | ✅ 已修复 | 99 passed |
| P2-1 | Minor | adapters | Neutralizer/Imputer 未传 enabled 给 super | ⬜ 可选 | - |
| P2-2 | Minor | ablation_runner | bootstrap CI 仅对 IC 差, 未对 Sharpe 差 | ⬜ 可选 | - |
| P2-3 | Minor | ablation_runner | bootstrap p 值公式文字描述不一致 | ⬜ 可选 | - |
| P3-1 | Minor | test_module_enabled | _processor_class is None 未验证 | ⬜ 可选 | - |
| P3-2 | Minor | test_module_enabled | transformation ignores enabled 行为未验证 | ⬜ 可选 | - |

---

## 1. 审查范围与方法

### 1.1 设计文档清单
- `docs/EXECUTION_ABLATION_V3.0.0.md` v1.0 (2026-07-08) — ABLATION E1-E7 规格

### 1.2 审查维度
- **维度 1 (E1)**: adapters.py + pipelines_v2.py vs spec §1 (module_enabled 开关)
- **维度 2 (E2-E7)**: ablation_runner.py vs spec §2-7 (核心引擎 + L1-L4 + 报告)
- **维度 3**: 跨模块契约 (ADR-020/024/025/002a/026 不变式)

### 1.3 审查方法
- 3 个独立 subagent 并行审查 (每个维度 1 个)
- 每维度独立评分
- 跨维度问题汇总

---

## 2. 模块审查结果

### 2.1 E1: adapters.py + pipelines_v2.py (评分: C+)

**Adapter 层实现质量 A+ 级**, 但**管线侧透传完全缺失** (§1.4/§1.5 整段未落地), 导致 `PipelineV2Config.module_enabled` 成为死字段。

#### 严重问题
- **P0-1: [Blocker] 管线侧 module_enabled 透传完全缺失** (pipelines_v2.py:797-800, 853-857, 949-954, 1406-1440, 1208, 1219)
  - spec §1.4 要求三条管道 `__init__` 新增 `module_enabled` 并用 `me.get(...)` 透传到 Adapter
  - 代码实际: `module_enabled` 在整个 pipelines_v2.py 中仅出现 1 次 (L736 字段声明), 从未被读取/传递/使用
  - 影响: `PipelineV2Config.module_enabled = {'imputer': False}` 对管线行为零效果

#### 中度问题
- **P1-1: TestPipelineModuleEnabled 测试类缺失** — spec §1.7 E1-T4 要求 4 个测试
- **P1-2: TestBackwardCompat 测试类缺失** — spec §1.7 E1-T5 要求 2 个测试

#### 轻微问题
- P2-1: Neutralizer/Imputer 未传 enabled 给 super().__init__()
- P3-1: _processor_class is None 未在测试中验证
- P3-2: transformation ignores enabled 行为未验证

#### 测试盲区
- **核心盲区**: test_module_enabled.py 仅在 Adapter 单文件层测试, 完全没有测试 `PipelineV2Config.module_enabled → _create_pipeline → StaticFactorPipeline → ImputerAdapter(enabled=...)` 跨文件传递链
- 正是此盲区导致 P0-1 未被发现

### 2.2 E2-E7: ablation_runner.py (评分: B-)

**数据结构与核心算法正确** (LW HAC /T 因子 ✅, circular bootstrap ✅, ρ_step spearmanr ✅, BH-FDR 复用 ✅), 但 **3 个参数注入方法完全未实现**, 导致 L2/L3/L4 消融实验产出全部 = B3 默认。

#### 严重问题
- **P0-2: [Blocker] L2 路由覆盖逻辑未实现** (ablation_runner.py:495-540)
  - spec §2.5/§4.3 要求 `_override_routing` 在 fit 后覆盖 `factor_classifications`
  - 代码无此方法, `routing_mode` 字段被完全忽略
  - 影响: L2 的 5 个配置产出完全相同

- **P0-3: [Blocker] L3 参数注入未实现** (ablation_runner.py:495-540)
  - spec §6.4 要求 `_apply_l3_overrides` 注入 cusum_k/h/ewma_*/winsorize_ratio
  - 代码无此方法
  - 影响: L3 的 ~25 个配置产出全部 = B3 默认

- **P0-4: [Blocker] L4 OAT 参数注入未实现** (ablation_runner.py:495-540)
  - spec §5.4 要求 `_apply_l4_overrides` 注入 outlier/scaler/missing/neutralization/time_align/data_window
  - 代码无此方法
  - 影响: L4 的 ~20 个配置产出全部 = B3 默认

#### 中度问题
- P1-3: L3 缺失 correction_method 消融 (3 配置)
- P1-4: L3 CUSUM 用组合对而非 OAT (规格要求 k=0.25/0.5/0.75 + h=4.0/5.5/7.0 分离 OAT)
- P1-5: L3 winsorize 缺失 MAD 选项
- P1-6: run_l2 缺失 b3_full_result 参数 (M6 修正未完整应用)
- P1-7: M5 平凡比较标注未实现 (L4 OAT 默认选项应从 BH-FDR 排除)
- P1-8: _collect_rho_steps 中 orthogonalizer before==after (恒 1.0, 无法测量正交化影响)

#### 轻微问题
- P2-2: bootstrap CI 仅对 IC 差计算, 未对 Sharpe 差计算
- P2-3: bootstrap p 值公式与规格文字描述不一致 (实现用中心化版本, 更稳健)

#### 测试盲区
- BS-1: /T 因子未直接测试 (test 通过但未断言 /T 存在性)
- BS-2: L2 路由覆盖行为未测试 (测试仅检查 config.routing_mode 字段值, 未验证 pipeline.factor_classifications 覆盖)
- BS-3: L4 OAT 参数注入未测试 (测试仅检查 config 字段值)
- BS-4: L3 参数注入未测试 (测试仅检查 config 字段值)
- BS-5: L3 结果数断言过于宽松 (>=19 vs 规格 ~25)
- BS-6: 平凡比较 (M5) 未测试

### 2.3 跨模块契约 (评分: C+)

**所有 ADR 不变式结构层面 PASS**, 但**参数流断裂**。

#### ADR 不变式检查
| ADR | 不变式 | 状态 | 证据 |
|-----|--------|------|------|
| ADR-020 | OrthogonalizerAdapter.enabled from config | ✅ PASS | adapters.py:849 |
| ADR-024 | L2 compatible with T1 fingerprint routing | ✅ PASS | ablation_runner.py:530 |
| ADR-025 | L3 covers cusum_k/cusum_h | ✅ PASS | ablation_runner.py:324-325 |
| ADR-002a | compare_all reuses apply_bh_fdr | ✅ PASS | ablation_runner.py:36, :1053 |
| ADR-026 | AblationRunner independent | ✅ PASS | backtest/ablation_runner.py |

#### 参数流断裂 (P0-1/2/3/4 的跨模块视角)
```
AblationConfig.module_enabled → modified_config.module_enabled ✓
  → _create_pipeline ✗ (未透传)
  → StaticFactorPipeline ✗ (未接受)
  → ImputerAdapter.enabled ✗ (未到达)

AblationConfig.ortho_enabled → modified_config.orthogonalization.enabled ✓ (唯一生效路径)

AblationConfig.routing_mode → _override_routing ✗ (方法不存在)
AblationConfig.cusum_k/cusum_h → _apply_l3_overrides ✗ (方法不存在)
AblationConfig.outlier_method → _apply_l4_overrides ✗ (方法不存在)
```

---

## 3. 修复优先级矩阵

### Tier 1: P0 Blocker (立即修复)
1. **P0-1**: pipelines_v2.py module_enabled 透传 (~30 行, spec §1.4 有完整代码)
2. **P0-2**: ablation_runner.py _override_routing (L2 路由覆盖)
3. **P0-3**: ablation_runner.py _apply_l3_overrides (L3 参数注入)
4. **P0-4**: ablation_runner.py _apply_l4_overrides (L4 OAT 参数注入)

### Tier 2: P1 Critical + 低成本 P2
5. P1-1 + P1-2: 补 TestPipelineModuleEnabled + TestBackwardCompat (6 测试)
6. P1-3: L3 补 correction_method 消融 (3 配置)
7. P1-4: L3 CUSUM 改为 OAT (重写配置生成)
8. P1-5: L3 补 MAD winsorize (1 配置)
9. P1-6: run_l2 补 b3_full_result 参数
10. P1-7: M5 平凡比较标注
11. P1-8: _collect_rho_steps ortho before/after 分离

### Tier 3: P2 + P3 (可选)
12. P2-1: Neutralizer/Imputer 传 enabled 给 super
13. P2-2: bootstrap CI 补 Sharpe 差
14. P3-1, P3-2: 测试改进

---

## 4. 修复后预期评分提升

| 模块 | 当前 | Tier 1 修复后 | Tier 2 修复后 |
|------|------|--------------|--------------|
| E1 (adapters + pipelines_v2) | C+ → | A (P0-1 修复) → | **A+** (P1-1/2 补测试) |
| E2-E7 (ablation_runner) | B- → | B+ (P0-2/3/4 修复) → | **A-** (P1-3~P1-8 修复) |
| 跨模块契约 | C+ → | B+ (参数流打通) → | **A-** (rho_step 修复) |

**最终测试基线**: 192 passed, 2 skipped (ABLATION 117 + RESEARCH_NOTES 48 + 既有管线/适配器 27)
**审计完成日期**: 2026-07-08
**Tier 3 (P2/P3)**: 5 项可选改进,不阻断功能,可后续迭代

---

## 5. 下一步建议

1. **立即**: 修复 4 项 P0 Blocker (Tier 1)
2. **本轮**: 修复 P1 Critical (Tier 2), 建立回归基线
3. **可选**: P2/P3 改进 (Tier 3)

---

## 附录: 审查基线

- ABLATION 测试基线: 90 passed (tests/test_adapters/test_module_enabled.py + tests/test_backtest/test_ablation_runner.py)
- 审查 subagent: 3 个 (E1 维度 / E2-E7 维度 / 跨模块契约维度)
- 审查日期: 2026-07-08
