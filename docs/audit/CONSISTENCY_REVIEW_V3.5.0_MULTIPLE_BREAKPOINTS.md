# CONSISTENCY REVIEW — v3.5.0 多断点支持

> **版本**: v1.0 (2026-11-16) — 步骤 8 工件
> **对齐对象**: RESEARCH / DESIGN / EXECUTION / CHECKLIST / ADR-046 / PROJECT_STATUS

## §1 文档间一致性

| # | 检查项 | 结论 |
|---|--------|------|
| I1 | RESEARCH §3 算法口径 = DESIGN §2.2 DP 递推 = EXECUTION §2.1 | ✅ 一致 (`cost[k,j] = min[cost[k-1,i] + ssr[i,j]]`, `i∈[kh, j-h]`) |
| I2 | RESEARCH §4 对拍三级 = DESIGN §6 = EXECUTION §4 | ✅ 一致 (L1 官方 F / L2 循环 regress / L3 BIC·LWZ); 均已改为「Stata 官方 regress 穷举」 |
| I3 | DESIGN 输出契约 12 键 = EXECUTION §2 返回 dict | ✅ 逐键一致 |
| I4 | EXECUTION §3 E1-E8 = CHECKLIST §B T1-T8 | ✅ 一一对应 |
| I5 | 版本 3.5.0 在三份文档 + ADR + CHECKLIST K1 中一致 | ✅ |
| I6 | 缓存代际 `v2.3.0-cache` 在 DESIGN §7 / EXECUTION §1 / CHECKLIST K2 一致 | ✅ |
| I7 | RESEARCH F14 (v3.3.0 曾否决 Bai-Perron) 在 DESIGN §8 有逐条回应 | ✅ 三条理由全部覆盖 |

## §2 与既有代码/文档的对齐

| # | 检查项 | 结论 |
|---|--------|------|
| I8 | trimming `h = max(5, int(εT))` 与 `detect` L296 一致 | ✅ |
| I9 | 断点索引语义与 `detect` 的 `breakpoint_idx` 一致 (`np.where(valid)[0]`) | ✅ |
| I10 | T<30 退化与 v3.4.13 DEFECT-1 契约一致 | ✅ 不抛异常 + 显式空结果 |
| I11 | `diagnose` 不接入 → PROJECT_STATUS 缺陷登记不受影响 | ✅ 无新增缺陷 |
| I12 | ADR 编号 046 未被占用 (最大 045) | ✅ |
| I13 | 版本锚点 6 处与 v3.4.13 清单一致 | ✅ |
| I14 | v3.4.13 异构复审结论 (H3 短样本标签) 不被本任务推翻 | ✅ 多断点不改变 diagnose 标签 |

## §3 数值口径一致性

| # | 检查项 | 结论 |
|---|--------|------|
| I15 | `SSR_0` (= `ssr_mat[0,T]`) 与 `detect` 的 `ssr_full` 同义 | ✅ 均为全样本去均值 SSR |
| I16 | m=1 的 DP 解与 `detect` 的网格最优同目标函数 | ✅ 允许 ≤1 格差异 (H5) |
| I17 | BIC/LWZ 参数个数 = k+1 (每段 1 均值) | ✅ 与 Bai-Perron (2003) SC 定义一致 |
| I18 | `ln(T)^(2+δ0)` 在代码中写为 `log(T) ** 2.1` | ✅ δ0=0.1 |

## §4 待解决事项

| # | 事项 | 处置 |
|---|------|------|
| O1 | 未硬编码 Bai-Perron sup-F 临界值表 | 记录于 RESEARCH §5 + ADR-046 替代方案; `n_breaks` 由 BIC/LWZ 决定 |
| O2 | Stata 无官方 Bai-Perron 命令 | 已实测记录 (F3/F4); 对拍改走官方 `regress` 穷举 |

**结论**: PASS — 无文档间冲突; 2 项边界已在 ADR 中显式声明。
