# 批次 Session：EIV 适用性与 remedy 审计（P-028 / Wave 0-1）

---
id: p028-eiv-applicability-audit-SESSION
type: session
version: 1.1
status: verified
date: 2026-11-24
depends: []
upstream: null
---

> **批次**：P-028 EIV 适用性与 remedy 审计（Wave 0 第 1 项）
> **档位**：**T3**（Layer-0 研究 / 文档）
> **判档依据**（SPEC_PROCESS v1.7.0 §判档规则 1）：改动路径 = `docs/PROGRESS.md` / `docs/PROJECT_STATUS.md` / `docs/SPEC_COMPLIANCE.md` / `docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` / `spec/p028-eiv-applicability-audit/SESSION.md`，与 `{scripts/, tests/, tools/, .pre-commit-config.yaml, .github/workflows/}` 交集为 **∅** → Layer-0 → T3。
> **裁剪理由**：本批只做**代码级适用性审计与 remedy 裁决**；零代码、零门禁、零默认变更。任何 remedy 实施（若裁决需要）另立 T1 批次。
> **Spec 步骤**：T3 五步决策流（判档 → 事实核对 → 裁决 → 实施 → 验收）。
> **回退点**：本批未产生 git 提交；回退 = `git checkout -- docs/PROGRESS.md docs/PROJECT_STATUS.md docs/SPEC_COMPLIANCE.md docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` + 删除本目录。

---

## 0. 决策流（五步）

| 步 | 动作 | 结论 | 证据出口 |
|---|---|---|---|
| 1 | 判档与登记 | T3；PROGRESS 登记 P-028（P2 / done） | `docs/PROGRESS.md` P-028 行 |
| 2 | 事实核对 | F-1~F-8：架构、SE、Shanken 错配、IV 可行性、数据缺口 | §1 |
| 3 | 裁决 | D1 Shanken 不适用；D2 remedy 矩阵；D3 推荐「披露 + 构造敏感性」；D4 松耦合约束 | §2 |
| 4 | 实施 | 审计 memo + 台账同步；零代码 | §3 |
| 5 | 验收 | 静态核对 + E-TODO 出口（可执行校验器未运行，见 §4） | §4-§6 |

---

## 1. 事实核对（E1，全部为仓内事实）

> **F1/F2 口径**：本批不使用外部来源；内部文件以「路径 + 行号区间」替代来源版本。
> **F3 降级链**：无外部检索；可执行校验器降级说明见 §4。
> **F4 引用验证表**：N/A（外部引用 0 条）。
> **F5 先失败记录**：N/A（零代码）。

| # | 事实 | 读数 | 来源 |
|---|---|---|---|
| F-1 | `PremiumEstimator` 是「单遍横截面回归 + 核平滑」，不是 two-pass beta pricing | `estimate()` 逐期回归 `r_{i,t}=α_t+β_t·f_{i,t−1}+ε`，β_t 即溢价；随后 Epanechnikov 核平滑为 λ̂(t) | `modules/factor_health/__init__.py` L48-L63 / L160-L176 / L182-L220 |
| F-2 | Layer 3 诊断只用点估计，不消费 HAC SE | `diagnose()` 调 `self.estimator.estimate(...)`；`estimate_with_errors()` 存在但未被 `diagnose` 调用 | `modules/factor_health/__init__.py` L65-L155 / L842 |
| F-3 | Shanken 修正对象与当前路径不匹配 | Shanken (1992) 修正 two-pass 中「估计 β 作为第二遍回归元」的 generated-regressor 偏差；当前代码无第二遍回归；仓内代码 `Shanken` 命中 **0** | 代码检索；[分析 §12.7](../../docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md#L536-L543) |
| F-4 | 当前 EIV 风险来自因子/暴露的测量误差 | 预处理含缩尾 / rank / zscore / 中性化，可降低异常值影响但不消除经典测量误差；用含噪控制变量做中性化还可能引入 generated-regressor 噪声 | `pipelines_v2.py` Static 链 L739-L763；`adapters.py` NeutralizerAdapter |
| F-5 | 外部 IV 当前不可得 | 无外部工具变量数据集；P-026 外部数据 blocked/suspend；仓内无 IV 数据契约 | `docs/PROGRESS.md` P-026 行；P-026 SESSION |
| F-6 | Lewbel 内部 IV 不是 drop-in | `LewbelInternalIVChecker.fit` 按 `factor_data.size` 展平面板，构造 `Z_internal=(Z−Z̄)×ê²`；面向 E3 面板诊断，不是逐期截面溢价估计 | `modules/endogeneity_check/core/lewbel_iv.py` L35-L100 |
| F-7 | 无 reliability / 重复测量 | 代码中 `reliability` / `attenuat` / `measurement_error` 命中 **0**；无重复测量或验证样本，衰减系数不可识别 | 代码检索 |
| F-8 | 默认路径不受影响 | Layer 3 未接入 `pipelines_v2`；E3/E5/E6 全 opt-in；本审计不改变任何默认输出 | `pipelines_v2.py` L546 / L574 / L583；分析 §10 |

---

## 2. 裁决（Step 3-4）

### D1 Shanken 不适用，禁止在当前 `PremiumEstimator` 中实现

- 当前 β_t 是溢价本身，不是第二遍回归的输入；套用 Shanken 会修正一个不存在的偏差。
- 若未来新增「估计 β → 第二遍截面回归」的 beta-pricing 路径，再在该路径实现 Shanken，不在本模块实现。

### D2 EIV remedy 矩阵

| Remedy | 可行性 | 裁决 |
|---|---|---|
| 外部 IV | 无工具变量数据；P-026 未交付 | **暂不实施**；待外部数据/工具变量到位 |
| Lewbel 内部 IV | 已有 E3 面板实现；改成逐期截面会改变估计口径、复杂度高 | **仅研究分支**；不进主线 |
| 衰减校正（attenuation correction） | 需要 reliability ratio / 测量误差方差；当前无重复测量或验证样本，不可识别 | **不实施**；不得用任意 λ 硬校正 |
| 构造层降噪（缩尾 / rank / zscore / 组合排序） | 已部分存在；可降低噪声但不能消除 | **保留**；以敏感性诊断衡量 |
| 披露 + 构造变体敏感性 | 零新增依赖、零默认变更；可量化 premium 对构造选择的敏感度 | **推荐 Wave 1** |
| Two-pass + Shanken | 仅在未来新增 beta-pricing 路径时适用 | **延后** |

### D3 Wave 1 推荐：`eiv_sensitivity` 只读诊断

- 对同一因子比较至少 4 种构造变体（raw / winsorized / rank / neutralized）的 λ̂ 轨迹与 premium 均值，输出**离散带**而非单点修正。
- 若离散带相对宽度超阈值 → 标记 `eiv_construction_sensitive=True` 并披露；否则记录「对构造选择稳健」。
- 形态：独立函数 / opt-in，默认关；不改 `fit/transform`；零新增依赖；不新增 τ 消费者。
- 本项若实施，另立 T1 批次（P-029 或并入 P-027 Stage 1 探针）。

### D4 松耦合约束

1. 独立入口，不修改 `fit/transform` 默认路径；
2. 配置开关默认关；
3. 不新增 τ 消费者，不进入 P-009 / Layer 3；
4. 零新增运行时依赖；
5. 独立单测 + 默认 SHA 逐位不变；
6. 诊断结论必须写「不是因果识别，也不是 EIV 修正」。

### 2.1 不变式

- **INV-1**：本批零代码——不修改任何 `.py` / `.toml` / `.yaml` / `.json` / 测试。
- **INV-2**：不实现 Shanken 修正；不新增任意衰减系数。
- **INV-3**：默认路径零变更（E3 / E5 / E6 仍全部关闭）。
- **INV-4**：不新增 τ 消费者。
- **INV-5**：审计结论 + Wave 1 建议 + 重访条件完整留痕。

---

## 3. 实施记录（Step 5-6，零代码）

| 文件 | 位置 | 改动 |
|---|---|---|
| `spec/p028-eiv-applicability-audit/SESSION.md` | 本文件 | 新建 T3 审计 session |
| `docs/PROGRESS.md` | 待办表 | 新增 **P-028**（P2 / done），依据链本 session；优先级视图同步 |
| `docs/PROJECT_STATUS.md` | §2 | P 号范围 → P-001 ~ P-028；P2 视图标注 P-028 done |
| `docs/SPEC_COMPLIANCE.md` | §1 / §4 | P 号范围 → P-001 ~ P-028 |
| `docs/analysis/ENDOGENEITY_PREMIUM_GOVERNANCE_ANALYSIS.md` | §12.7 末 | 增 P-028 审计结论与 Wave 1 建议指针 |

> **零代码自证**：本批全部写入均通过 Write / Edit 限定在 `docs/` 与 `spec/`；未触碰任何代码 / 配置 / 测试文件。

---

## 4. 机械核验（Step 8）

| 检查 | 方法 | 读数 |
|---|---|---|
| Shanken 未实现 | Grep `Shanken` over `*.py` | **0 命中** |
| EIV 修正未实现 | Grep `reliability\|attenuat\|measurement_error` over `*.py` | **0 命中** |
| 默认开关未变 | Read `pipelines_v2.py` L546 / L574 / L583 | `False` / `False` / `False` |
| P-028 登记 | Read `docs/PROGRESS.md` P-028 行 | `done` / P2，链接本 session |
| P 号范围 | Grep `P-001 ~ P-028` | SPEC_COMPLIANCE / PROJECT_STATUS 一致 |
| 零代码 | 写入范围自证（Write/Edit 仅 docs/spec） | **0 个代码文件** |
| 三校验器 / `console_gen --check` | — | **未执行**：权威校验器在 `F:\Spec_Workflow`（仓外）；工作区标记 untrusted，禁止执行仓内脚本/命令。降级为静态 grep/Read + 写入范围自证；待工作区信任后补跑 |

---

## 5. E-TODO 出口（SPEC_COMPLIANCE §7，T3 简化执行）

| 步 | 结果 |
|---|---|
| E1 候选清单 | B-1 Shanken 错配 / B-2 外部 IV 不可得 / B-3 衰减系数不可识别 / B-4 构造噪声可降不可消 |
| E2 映射 | B-1→D1；B-2/B-3→D2；B-4→D3；映射率 **100%** |
| E3 逐行状态 | P-028 → `done`；Wave 1 建议保持待立项 |
| E4 证据链接 | 本文件 §1/§2/§4 + 分析 §12.7 |
| E5 双写 | PROGRESS P-028 行与本文件 §3 一致；PROJECT_STATUS §2 视图同步 |

---

## 6. Step 10 审计（T3 裁剪）

本批为 **T3 研究 / 文档级**，无代码、无门禁、无运行时变更；按 T3 裁剪不启独立 ADD 审计。以 §4 静态核验 + 写入范围自证替代。结论：**PASS（条件：可执行校验器未运行，待工作区信任后补跑）**。

---

## 7. 结论与后续

- **P-028 审计结论**：Shanken 修正不适用；外部 IV / Lewbel 截面化 / 衰减校正均不具备当前条件；推荐 Wave 1 采用「披露 + 构造变体敏感性」，不做硬修正。
- **Wave 1 执行（2026-11-24）**：4 因子 × 6 构造变体 + 行业窗口已跑；4/4 判定构造敏感；rank→normal 效应 +124%~+244%；amihud 在缩尾/市值/行业中性化下均敏感。详见 [EIV_SENSITIVITY_P028.md](../../docs/analysis/EIV_SENSITIVITY_P028.md)；工件 `out/eiv_sensitivity_p028.{py,json}`。
- **重访条件**：① 外部工具变量或验证样本到位；② 新增 two-pass beta-pricing 路径；③ 构造敏感性显示 premium 对噪声高度敏感且业务需要修正。
- **Wave 0 剩余项**：P-029（反向因果诊断）与 P-030（IPCA/DML/贝叶斯收缩研究分支）尚未登记，待用户裁决。
- **P-027 不受影响**：Stage 0a 已完成，Stage 0b / Stage 1 仍按原路线推进。
