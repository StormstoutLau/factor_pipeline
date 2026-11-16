# RESEARCH V3.5.2 — 多断点路径 NaN 间隙守卫

> **版本**: v3.5.2 (2026-11-17)
> **上游**: v3.5.0 H7「NaN 间隙」+ v3.5.1 复审 H5「间隙假断点被两级门控压制 5-6 倍」
> **状态**: 调研完成 → 设计/实施
> **范围**: 仅 `breakpoint_mode='multiple'` 的标签路径; `detect` / 默认 `single` 零变更

---

## §1 问题定义

`detect_multiple` 先剔除 NaN，再在压缩后的有效序列上做 Bai-Perron 分段
（`valid = ~np.isnan(y_all); y = y_all[valid]`），断点索引最后映射回原序列。
这带来两个后果:

1. **时间距离失真**: 一段 10 期缺失被压缩为相邻两点，分段边界可能"跨越"缺失区间；
2. **时点不可观测**: 若水平位移恰好发生在缺失区间内，断点只能落在缺失区间的边缘，
   真实发生时点无法识别。

定义 **边界跨越缺失数**:

```
gap_missing(b) = idx_map[pos(b)] - idx_map[pos(b)-1] - 1
```

其中 `b` 为断点（原序列有效索引），`pos(b)` 为它在有效点序列中的位置。
若 `gap_missing >= 1`，说明该边界两侧的相邻观测在原时间轴上不连续。

---

## §2 探针 (P1-P3)

> 方法: 直接对 `BreakpointDetector.detect` / `detect_multiple` 输入 1D 序列
> （与 `diagnose` 内部的 `beta_raw` 同口径），300 次重复，α=0.05，T=120，
> 5 段修剪 `min_segment=0.05`。守卫规则临时在探针中复刻，gmin 扫描 1/2/3/5。

### P1 纯噪声 + 间隙（iid, N(0,1)）

| 场景 | conf | BIC>0 | material | gap_risk (gmin=2) | ES 旧 | ES 新 |
|------|------|-------|----------|-------------------|-------|-------|
| 无间隙 | 4.7% | 31.7% | 3.3% | 0.0% | 4.7% | 4.7% |
| 单间隙 g=10 | 6.0% | 33.7% | 5.7% | 0.0% | 6.0% | 6.0% |
| 5 段间隙 g=3 | 4.3% | 37.0% | 8.0% | 1.3% | 4.3% | 3.7% |
| 5% 散点 NaN | 5.0% | 32.7% | 3.3% | 0.0% | 5.0% | 5.0% |

结论: 纯噪声下守卫触发率 0-1.3%，ES 率 ≈ sup-F 名义 size；间隙本身不会
系统性制造 ES。

### P2 真实断点 d=0.8σ（T=120, 断点 60）

| 场景 | conf | gap_risk (gmin=2) | ES 旧 | ES 新 |
|------|------|-------------------|-------|-------|
| 无间隙 | 96.3% | 0.0% | 96.3% | 96.3% |
| 间隙远离断点 | 92.0% | 0.7% | 92.0% | 91.3% |
| 5% 散点 NaN | 94.3% | 0.3% | 94.3% | 94.0% |
| 间隙 g=5 正落在断点 | 95.3% | 21.7% | 95.3% | 73.7% |
| 间隙 g=10 正落在断点 | 93.0% | 17.0% | 93.0% | 76.0% |

结论: 间隙不在断点时守卫几乎不触发（≤0.7%）；真正落在断点时 17-22% 的
切分跨越间隙，被降级为 `suspect`——这是**有意的保守代价**（时点不可观测，
不应宣称 ES）。

### P3 gmin 选择

| gmin | 纯噪声 5×g3 | 真断点 + 散点 NaN | 真断点 + g=1 间隙 |
|------|-------------|-------------------|-------------------|
| 1 | 1.3% | 7.3% | 18.0% |
| 2 | 1.3% | 0.3% | 0.0% |
| 3 | 1.3% | 0.0% | 0.0% |
| 5 | 0.0% | 0.0% | 0.0% |

gmin=1 会把「真实断点 + 孤立缺失」误降级 7.3%；gmin=2 降到 0.3%，且仍能
捕获 g≥2 的间隙。**默认取 gmin=2**（`multi_break_gap_min_run=2`）。

### P4 自相关对照（范围外披露）

| φ | 无间隙 conf | 单间隙 g=10 conf |
|---|-------------|------------------|
| 0.0 | 4.3% | 3.3% |
| 0.2 | 15.7% | 14.3% |
| 0.5 | 48.7% | 45.3% |

结论: sup-F 在自相关下的过度拒绝与间隙**无关**（无间隙时同样高），
本守卫不处理该问题，仅作为已有限制披露，不扩大范围。

---

## §3 结论与设计约束

1. 守卫的目标是**诚实标注时点不可观测**，而非降低所有假阳性；
2. 仅当**标签相关边界**跨越 ≥2 期缺失时降级: `confirmed` 用 sup-F 断点，
   `material`（未确认）用最大位移所在 BIC 边界；
3. 降级方式: `breakpoint_gap_risk=True` → `premium_health` 不返回 ES/ES+TD，
   回落 `suspect`（若 TD 独立成立则保留 TD，沿用 v3.5.1 的 TD 优先级）；
4. `detect_multiple` 增加连续性描述键，不改分段结果与 `detect`；
5. 默认 `single` 模式守卫关闭（`breakpoint_gap_risk=False`），标签与旧版逐位一致；
6. 不引入新的临界值表，不做 NaN 插值或加权 SSR。

---

## §4 交付物

- `docs/private/DESIGN_V3.5.2_NAN_GAP_GUARD.md`（设计，未提交）
- `docs/EXECUTION_V3.5.2_NAN_GAP_GUARD.md`（实施记录）
- `docs/audit/2026-11-17-v3.5.2-nan-gap-guard-audit.md`（审计）
- `DECISIONS.md` ADR-048
- 代码: `modules/factor_health/__init__.py` + 测试 `tests/unit/test_layer3_factor_health.py`

---

## §5 参考

- Andrews, D. W. K. (1993). Tests for parameter instability and structural change with unknown change point. *Econometrica*, 61(4), 821-856.
- Bai, J., & Perron, P. (1998). Estimating and testing linear models with multiple structural changes. *Econometrica*, 66(1), 47-78.
- v3.5.0 [EXECUTION](../EXECUTION_V3.5.0_MULTIPLE_BREAKPOINTS.md) / ADR-046（H7 NaN 间隙）
- v3.5.1 [EXECUTION](../EXECUTION_V3.5.1_DIAGNOSE_MULTIBP.md) / ADR-047（复审 H5）
