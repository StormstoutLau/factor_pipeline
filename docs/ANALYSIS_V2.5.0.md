# v2.5.0 多因子正交化模块方案分析报告 (ADR-020)

**状态**: 方案设计完成 (v2.1 — Layer 3 兼容性深度分析 + 决策学术支撑补充)
**创建日期**: 2026-07-03
**修订日期**: 2026-07-03 (v2.1: 补充 §3.6 Layer 3 兼容性深度分析 + D7'/D9'/D11/D12 学术支撑)
**基于**: ADR-020 + 学术文献研究 + 项目现状调研 + 架构兼容性分析
**关联**: v2.4.0 (ADR-019 内化完成后基线 632 passed)

---

## 目录

1. [执行摘要](#一执行摘要)
2. [学术研究: 正交化方法与 ML 方法分类](#二学术研究-正交化方法与-ml-方法分类)
3. [三层架构设计 (含 §3.6 Layer 3 兼容性深度分析)](#三层架构设计)
4. [项目现状诊断与架构兼容性](#四项目现状诊断与架构兼容性)
5. [技术决策与理由](#五技术决策与理由)
6. [功能设计 (O1-O6)](#六功能设计-o1-o6)
7. [风险与陷阱清单](#七风险与陷阱清单)
8. [实施路线图](#八实施路线图)
9. [验收标准](#九验收标准)
10. [附录 A: 学术文献完整引用](#附录-a-学术文献完整引用)
11. [附录 B: 性能基准目标](#附录-b-性能基准目标)
12. [附录 C: 修订日志](#附录-c-修订日志)

---

## 一、执行摘要

### 1.1 核心目标

为 factor_pipeline 增加**多因子横截面正交化**与**因子增量显著性检验**能力,与已有的 Factor_Fingerprint (单因子描述) 和 Factor_Decoupler (时序解耦) 形成**因子诊断三件套**: 描述 → 解耦 → 正交化 → 增量检验。

### 1.2 v2.0 修订核心论点: 三层架构分离

v1.0 报告存在三处架构设计缺陷,本修订版彻底重构为**三层分离架构**:

| 缺陷 | v1.0 错误 | v2.0 修正 |
|---|---|---|
| **正交化对象歧义** | 数学定义 `F ∈ R^(T×K)` (时序堆叠) 与 ADR-020 "横截面"约束矛盾 | 统一为**对象 A 横截面正交化**: `F_t ∈ R^(N×K)`, per-t 估计 W |
| **方法混合放置** | 双重 Lasso 与对称正交化并列在 O3 诊断 | 双重 Lasso 属 **Layer 3 (有监督检验)**,正交化属 **Layer 2 (无监督变换)**,分层不混 |
| **位置决策简化** | D7 "后处理" 一句话带过,未区分三层 | D7' 明确三层分离: Layer 1 管道内 (已有) / Layer 2 后处理 / Layer 3 回测子模块 |

### 1.3 三层架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: 单因子内部预处理 (Pipeline 内部, per-factor)        │
│  ├─ 行业中性化 (NeutralizerAdapter)        ← 已有           │
│  ├─ 时序解耦 (Factor_Decoupler)            ← 已有           │
│  └─ 单因子统计修复 (插补/去极值/标准化)    ← 已有           │
│  特征: 单因子 + 外部协变量, 无需其他因子, 无监督            │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: 多因子横截面变换 (Pipeline 后处理, cross-factor)   │
│  ├─ 对称正交化 (Symmetric / Löwdin)        ← v2.5.0 O1     │
│  ├─ Gram-Schmidt / PCA / Cholesky          ← v2.5.0 O1     │
│  ├─ Ledoit-Wolf 收缩 (预处理子步骤)        ← v2.5.0 O1     │
│  └─ 几何诊断 (VRR / κ / VIF / 正交性误差)  ← v2.5.0 O3a    │
│  特征: K 因子同时输入, 无监督, 输出 K 个变换后因子          │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: 因子增量检验 (回测/检验层, target-aware)           │
│  ├─ 双重 Lasso (Belloni 2014 PDS)          ← v2.5.0 O3b    │
│  ├─ Elastic Net 路径                       ← v2.5.0 O3b    │
│  ├─ IC 变化监控                            ← v2.5.0 O4     │
│  └─ Fama-MacBeth 回归                      ← 未来          │
│  特征: K 因子 + 收益 Y, 有监督, 输出 p 值/系数              │
└──────────────────────────────────────────────────────────────┘
```

### 1.4 关键决策 (用户确认 + 架构推导)

| 决策项 | 选择 | 理由 |
|---|---|---|
| 默认触发策略 | **默认关闭** (`enabled=False`) | 安全默认,不破坏 632 测试基线 |
| 窗口模式 | **滚动 + 全样本** 都支持 | 回测用滚动 (252日), 研究用全样本 |
| 分组正交化 | **纳入 O5** | 学术支撑强 (Stambaugh-Yuan 2017) |
| GPU 加速 | **可选依赖** (CuPy) | 类似 arch 模式, HAS_CUPY 标记 |
| **正交化对象** | **横截面 (对象 A)** | 与 Fingerprint/Decoupler 数据维度一致, ADR-020 方向 |
| **架构分层** | **三层分离** | 各层职责清晰,与现有架构兼容,不破坏 per-factor 管道 |
| **双重 Lasso 位置** | **Layer 3 (回测子模块)** | 需要 Y,属有监督检验,与无监督正交化分层 |
| **Pipeline 是否重构** | **保持 per-factor** | 不破坏 632 基线,正交化作为独立后处理层 |

### 1.5 学术依据概览

- **对称正交化 (Löwdin 1950)**: 无顺序依赖, VRR=1 完美保留总方差
- **双重 Lasso (Belloni-Chernozhukov-Hansen 2014)**: 高维因果推断渐进无偏
- **Factor Zoo 证据**: Harvey-Liu-Zhu (2016) 316 异象 + Hou-Xue-Zhang (2018) 447 异象
- **Value-Momentum 负相关** (Asness 2013): ρ ≈ -0.4, 不应强行正交 → 分组正交化依据
- **病态矩阵** (Ledoit-Wolf 2004): 条件数 κ>100 时需收缩估计
- **ML 实证** (Gu-Kelly-Xiu 2020): 树模型 > 神经网络 > 线性模型 (OOS R²)

---

## 二、学术研究: 正交化方法与 ML 方法分类

### 2.1 正交化对象澄清: 三种本质不同的"正交化"

"因子正交化"一词在文献中被滥用,v2.5.0 必须首先澄清对象:

#### 对象 A: 因子暴露的横截面正交化 (Cross-Sectional) — **v2.5.0 选择**

```
每个时点 t, 把 K 个因子在 N 只股票上的暴露正交化
F_t ∈ R^(N × K)  →  T_t = F_t @ W_t  (W_t ∈ R^(K × K))
```

- **消除**: 因子间在**股票截面**上的共线性 (例:PB 与市值在 3000 只股票上高度相关)
- **用途**: Barra/Axioma 风险模型、组合优化、因子冗余诊断
- **W 维度**: K×K, 每期可独立估计或滚动窗口共享
- **学术对应**: Stambaugh-Yuan (2017) 的 mispricing factors
- **与项目对齐**: 与 Fingerprint (T,N) 单因子面板、Decoupler (T,N) 时序解耦形成完整三件套

#### 对象 B: 因子收益的时序正交化 (Time-Series of Returns)

```
K 个因子的收益时间序列正交化
r ∈ R^(T × K)  →  r* = r @ W  (W ∈ R^(K × K))
```

- **消除**: 因子**收益**在**时间维度**上的相关性
- **用途**: Fama-French PCA 提取独立风险因子、因子收益相关性分析
- **不在 v2.5.0 范围**: 属风险因子提取,与因子诊断三件套定位不同

#### 对象 C: 因子值的时间序列正交化 (混合)

```
把每个因子在 N 只股票上的时间序列堆叠,正交化 K 个因子的面板
F ∈ R^((T·N) × K)  →  T = F @ W
```

- **消除**: 因子值在**时间×股票**面板上的整体相关性
- **问题**: 混淆截面和时序信息,经济意义模糊,实务少用
- **不在 v2.5.0 范围**

**v2.5.0 决策**: 选对象 A (横截面正交化),理由见决策 D5。

### 2.2 横截面正交化的两种实现子模式

对象 A 下,W 的估计样本有两种选择:

| 子模式 | W 估计样本 | 应用 | 优缺点 |
|---|---|---|---|
| **A1: 每期独立** | 每期 `F_t (N×K)` 单独估计 `W_t` | `T_t = F_t @ W_t` | 无 look-ahead;但 W_t 噪声大,因子时序不连续 |
| **A2: 滚动窗口共享 W** | 用过去 252 日面板 `(252·N, K)` 估计 W, 应用到当期截面 | `T_t = F_t @ W_{t, rolling}` | W 稳定;需用 t-1 及之前数据避免 look-ahead |

v2.5.0 决策:
- 滚动模式 (A2) — 回测/实盘用,避免 look-ahead bias
- 全样本模式 — 用全样本 `(T·N, K)` 估计单一 W, 应用到所有期,研究分析用
- 两种模式共用核心算法 (SymmetricOrthogonalizer),仅外层包装不同

### 2.3 主流正交化方法比较 (Layer 2 变换类)

#### 2.3.1 数学定义 (对象 A 横截面)

每个时点 t (或滚动窗口堆叠后), 因子暴露矩阵 `F ∈ R^(N × K)`, 通过线性变换矩阵 `W ∈ R^(K × K)` 转换为正交因子矩阵 `T = F @ W`,使得变换后因子协方差矩阵 `Σ* = W^T Σ W` 为对角矩阵。

#### 2.3.2 方法比较表

| 方法 | 数学公式 | 复杂度 | 保留语义 | 顺序依赖 | 数值稳定性 | 适用场景 |
|---|---|---|---|---|---|---|
| **对称正交化** (Löwdin) | `T = F W`, `W = (F^T F)^(-1/2)` | `O(NK² + K³)` | 部分(对称变换) | 否 | 高(需正定) | 无优先级因子 (主方法) |
| **Gram-Schmidt** | `q_i = f_i - Σ_{j<i} proj_{q_j}(f_i)` | `O(NK²)` | 是(首因子保留) | 是 | 中(改进版好) | 有明确优先级 |
| **PCA 正交化** | `Σ = V Λ V^T`, `T = F V` | `O(NK² + K³)` | 否(主成分) | 否 | 高 | 高维降维 |
| **Cholesky 分解** | `Σ = L L^T`, `T = F L^(-T)` | `O(NK² + K³/3)` | 是(首因子保留) | 是 | 高(需正定) | 风险模型 |
| **Ridge 正交化** | `W = (F^T F + λI)^(-1/2)` | `O(NK² + K³)` | 部分 | 否 | 高 | soft 正交化,病态矩阵 |

#### 2.3.3 各方法详细分析

**对称正交化 (Symmetric Orthogonalization / Löwdin)** — v2.5.0 主方法

- **来源**: Löwdin (1950) 在量子化学中首次提出,后迁移至计量金融
- **数学**: `W = (F^T F)^(-1/2)`, 对 `F^T F` 特征值分解 `F^T F = V Λ V^T`, 则 `W = V Λ^(-1/2) V^T`
- **优点**: 对所有因子对称处理,不偏好任何因子;最大化保留原始因子信息 (VRR=1)
- **缺点**: 变换后因子是原始因子的线性组合,经济意义模糊;需要 `F^T F` 正定
- **数值稳定性**: 高,使用 `numpy.linalg.eigh` 对对称矩阵稳定

**Gram-Schmidt 正交化** — 备选

- **数学**: 经典版本 `u_i = f_i - Σ_{j<i} <f_i, u_j>/<u_j, u_j> · u_j`, 然后归一化
- **改进版**: 修正 Gram-Schmidt (MGS) 数值稳定性更高
- **顺序选择策略**: 通常按因子 IC 或信噪比降序排列,优先保留强因子
- **陷阱**: 经典版本在数值不稳定时会出现"正交性漂移"

**PCA 正交化** — 降维场景

- **数学**: 对协方差矩阵 Σ 特征值分解 `Σ = V Λ V^T`, `T = F V`, 主成分按方差降序排列
- **方差保留**: 前 k 个主成分保留 `Σ_{i=1}^k λ_i / Σ_{i=1}^n λ_i` 比例的方差
- **优点**: 全局最优去相关,降维能力强
- **缺点**: 主成分经济意义模糊;对因子尺度敏感(需先标准化)

**Cholesky 分解正交化** — 风险模型场景

- **数学**: `Σ = L L^T` (L 为下三角), `T = F L^(-T)`, 则 `T^T T = L^(-1) Σ L^(-T) = I`
- **效率**: 比 LU 分解快约 2 倍,比特征值分解更快
- **顺序依赖**: 第一个因子完全保留,后续因子依次正交化

**Ridge 正交化** — soft 正交化

- **数学**: `W = (F^T F + λI)^(-1/2)`, λ > 0 为正则化参数
- **优点**: 始终数值稳定,不需要正定;通过 λ 控制"正交化强度"
- **缺点**: 不严格正交 (W^T F^T F W ≠ I, 而是接近对角)
- **与 Ledoit-Wolf 关系**: Ridge 是 Ledoit-Wolf 在 `F^T F` 谱上的特殊情况

### 2.4 ML 方法四类分类 (扩展视野)

近年 ML/统计方法在因子研究中流行,v2.5.0 需明确各方法归属:

#### 2.4.1 变换类 (Transformation) → Layer 2

| 方法 | 数学 | 优点 | 缺点 | v2.5.0 范围 |
|---|---|---|---|---|
| **对称正交化** (Löwdin) | `W=(F^TF)^(-1/2)` | VRR=1,无顺序依赖 | 经济意义模糊 | ✅ 主方法 (O1) |
| **PCA / SVD** | `Σ=VΛV^T, T=FV` | 全局最优去相关,降维 | 主成分无经济意义 | ✅ 备选 (O1) |
| **Gram-Schmidt** | 迭代投影 | 保留首因子语义 | 强顺序依赖 | ✅ 备选 (O1) |
| **Cholesky** | `Σ=LL^T, T=FL^(-T)` | 数值稳定,风险模型友好 | 强顺序依赖 | ✅ 备选 (O1) |
| **Ridge 正交化** | `W=(F^TF+λI)^(-1/2)` | 数值稳定,soft 正交化 | λ 调参,不严格正交 | ✅ 新增 (O1) |
| **Autoencoder** | 非线性 `T=Encoder(F)` | 非线性去相关 | 训练成本高,可解释性差 | ❌ 推迟 v2.6.0 |

#### 2.4.2 选择类 (Selection) → Layer 3

| 方法 | 数学 | 优点 | 缺点 | v2.5.0 范围 |
|---|---|---|---|---|
| **Lasso** | `min ‖y-Xβ‖² + λ‖β‖₁` | 自动变量选择 | 单因子单一目标 | ❌ 双重 Lasso 更优 |
| **双重 Lasso** (PDS) | 两阶段 Lasso + OLS | 因果推断渐进无偏 | 需指定 treatment | ✅ Layer 3 (O3b) |
| **Group Lasso** | `λΣ‖β_g‖₂` | 组结构选择 | 需先验组结构 | ❌ 推迟 |
| **Elastic Net** | `λ₁‖β‖₁ + λ₂‖β‖²₂` | 兼顾稀疏+稳定 | 双参数调优 | ✅ Layer 3 (O3b) |
| **Adaptive Lasso** | 加权 Lasso | 渐近正态性 | 需初始权重 | ❌ 推迟 |
| **SCAD** | 非凸惩罚 | Oracle 性质 | 计算复杂 | ❌ 推迟 |

#### 2.4.3 收缩类 (Shrinkage) → Layer 2 预处理

| 方法 | 数学 | 优点 | 缺点 | v2.5.0 范围 |
|---|---|---|---|---|
| **Ledoit-Wolf 收缩** | `Σ*=(1-α)S+αF` | 理论最优 α | 假设正态 | ✅ O1 utils |
| **Ridge** (协方差版) | `Σ*=S+λI` | 简单 | λ 选择主观 | ✅ O1 utils |
| **Graphic Lasso** | `max logdet(Σ)-tr(SΣ)-λ‖Σ^(-1)‖₁` | 稀疏精度矩阵 | 计算昂贵 | ❌ 推迟 |
| **POET** | PCA + 低秩 + 稀疏 | 高维协方差估计 | 假设因子结构 | ❌ 推迟 |

#### 2.4.4 混合类 (Hybrid) → Layer 3 / 推迟

| 方法 | 数学 | 优点 | 缺点 | v2.5.0 范围 |
|---|---|---|---|---|
| **PLS** (Partial Least Squares) | 同时考虑 X 和 Y 协方差 | 目标导向降维 | 需 Y 标签 | ❌ 推迟 |
| **DML** (Double ML) | 任意 ML 估计 nuisance | 灵活,非线性 | 计算昂贵 | ❌ 推迟 v2.6.0 |
| **Random Forest 残差** | `Y~X` by RF, 取残差 | 非线性 | 黑箱 | ❌ 推迟 |
| **Gradient Boosting** | 类似 RF | SOTA 性能 | 黑箱,过拟合风险 | ❌ 推迟 |

### 2.5 双重 Lasso 详解 (Layer 3 核心方法)

#### 2.5.1 Belloni-Chernozhukov-Hansen (2014) 框架

```
目标: 检验因子 D_k 是否对收益 Y 有"增量"解释力 (控制其他 K-1 个因子)

Stage 1: Lasso Y ~ X (X = 其他 K-1 因子) → 选出与 Y 相关的子集 S_Y
Stage 2: Lasso D_k ~ X → 选出与 D_k 相关的子集 S_D
Stage 3: OLS Y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即"净化后增量 alpha"
```

**关键性质**: Stage 2 是为了避免"遗漏变量偏差" — 如果某因子与 D_k 高度相关但与 Y 弱相关, Stage 1 可能漏选它,但 Stage 2 会捕获,这种"双重保险"保证因果效应估计的渐进无偏。

#### 2.5.2 双重 Lasso 与对称正交化的本质差异

| 维度 | 对称正交化 (Löwdin) | 双重 Lasso (PDS) |
|---|---|---|
| **本质** | 变量变换 (transformation) | 变量选择 + 因果推断 (selection + inference) |
| **输出** | K 个正交化后的因子 | 1 个目标因子的"净化"残差 + 显著性检验 |
| **是否保留全部因子** | 是 (VRR=1) | 否 (稀疏选择,部分系数=0) |
| **顺序依赖** | 无 | 有 (需指定"目标因子"作为 treatment) |
| **经济意义** | 模糊 (线性组合) | 清晰 (保留原始因子语义) |
| **核心问题** | 因子间冗余 | 因子增量信息 (incremental alpha) |
| **监督性** | 无监督 | 有监督 (需 Y) |
| **架构层** | Layer 2 | Layer 3 |
| **学术对应** | Löwdin 1950 | Belloni et al. 2014 |

**二者关系**: 正交化是**预处理**, 双重 Lasso 是**后处理检验**。可以先正交化再 Lasso 检验,也可以直接用 Lasso 跳过正交化 (但会丢掉变换后的几何结构)。

#### 2.5.3 Gu-Kelly-Xiu (2020) 实证发现

Gu-Kelly-Xiu 在 RFS 发表的 "Empirical Asset Pricing via Machine Learning" 对比了 ~10 种 ML 方法, 关键结论:

1. **树模型 (RF/GBM) > 神经网络 > 线性模型** (在 OOS R² 上)
2. **Autoencoder** 能从 ~100 个特征中提取隐因子,显著优于 PCA
3. **Lasso/Elastic Net** 在小样本下表现稳健,适合因子选择
4. **神经网络**需要大样本 (T>30 年) 才能稳定

**对 v2.5.0 的启示**:
- 因子诊断 (验证增量信息) → 双重 Lasso / Elastic Net (Layer 3)
- 因子变换 (去冗余用于组合优化) → 对称正交化 (Layer 2)
- 因子提取 (从 100+ 异象中提取隐因子) → PCA / Autoencoder (推迟, 属另一模块)

### 2.6 经典学术文献清单 (12 篇)

1. **Löwdin, P. O.** (1950). "On the Non-Orthogonality Problem Connected with the Use of Atomic Wave Functions in the Theory of Molecules and Crystals." *The Journal of Chemical Physics*, 18(3), 365-375.
2. **Fama, E. F., & French, K. R.** (1993). "Common risk factors in the returns on stocks and bonds." *Journal of Financial Economics*, 33(1), 3-56.
3. **Fama, E. F., & French, K. R.** (2015). "A five-factor asset pricing model." *Journal of Financial Economics*, 116(1), 1-22.
4. **Asness, C. S., Moskowitz, T. J., & Pedersen, L. H.** (2013). "Value and Momentum Everywhere." *The Journal of Finance*, 68(3), 929-985.
5. **Harvey, C. R., Liu, Y., & Zhu, H.** (2016). "... and the Cross-Section of Expected Returns." *The Review of Financial Studies*, 29(1), 5-68.
6. **Hou, K., Xue, C., & Zhang, L.** (2018). "Replicating Anomalies." *The Review of Financial Studies*, 33(5), 2019-2133.
7. **Hou, K., Xue, C., & Zhang, L.** (2015). "Digesting Anomalies: An Investment Approach." *The Review of Financial Studies*, 28(3), 650-705.
8. **Stambaugh, R. F., & Yuan, Y.** (2017). "Mispricing Factors." *The Review of Financial Studies*, 30(4), 1270-1315.
9. **Grinold, R. C., & Kahn, R. N.** (1999). *Active Portfolio Management* (2nd ed.). McGraw-Hill.
10. **Ledoit, O., & Wolf, M.** (2004). "Honey, I Shrunk the Sample Covariance Matrix." *The Journal of Portfolio Management*, 30(4), 110-119.
11. **Belloni, A., Chernozhukov, V., & Hansen, C.** (2014). "Inference on Treatment Effects after Selection among High-Dimensional Controls." *Review of Economic Studies*, 81(2), 608-650.
12. **Gu, S., Kelly, B., & Xiu, D.** (2020). "Empirical Asset Pricing via Machine Learning." *Review of Financial Studies*, 33(5), 2223-2273.

---

## 三、三层架构设计

### 3.1 架构总览

```
factor_pipeline/
├── pipelines_v2.py                         # Layer 1: 单因子预处理 (现有, 不变)
│   └── FactorProcessingPipelineV2
│       └── per-factor 分类 → Static/Dynamic/Mixed 管道
│           (含行业中性化、时序解耦、标准化)
│
├── modules/factor_orthogonalizer/          # Layer 2: 多因子横截面变换 (v2.5.0 新增)
│   └── CrossSectionalOrthogonalizer
│       ├─ 输入: Dict[str, (N, T)] (Pipeline 输出)
│       ├─ 对称/GS/PCA/Cholesky/Ridge 变换
│       ├─ Ledoit-Wolf 收缩预处理
│       └─ 输出: Dict[str, (N, T)] (同格式)
│
└── backtest/                               # Layer 3: 回测 + 因子检验 (部分现有, v2.5.0 扩展)
    ├── engine.py                           # 现有: 单因子 IC 评估
    └── factor_significance.py              # v2.5.0 新增: 双重 Lasso / Elastic Net / VIF
        ├─ 输入: 因子 + 收益 Y
        └─ 输出: p 值 / 系数 / 显著性
```

### 3.2 各层职责边界

| 层 | 输入 | 输出 | 监督性 | 因子数 | 架构位置 |
|---|---|---|---|---|---|
| **Layer 1** (Pipeline) | 原始因子 | 预处理后因子 | 无监督 | 1 (per-factor) | 管道内部 (已有) |
| **Layer 2** (Orthogonalizer) | K 个预处理后因子 | K 个正交化后因子 | 无监督 | K | 管道后处理 (新增) |
| **Layer 3** (Significance) | K 个因子 + Y | p 值/系数 | 有监督 | K + Y | 回测子模块 (新增) |

### 3.3 数据流

```
原始因子 dict
    ↓ Layer 1: FactorProcessingPipelineV2.transform()
预处理后因子 dict (经过分类、中性化、标准化)
    ↓ Layer 2: CrossSectionalOrthogonalizer.transform()
正交化后因子 dict (K 个因子横截面去冗余)
    ↓ Layer 3: BacktestEngine + FactorSignificanceTest
IC 评估 + 增量显著性 p 值
```

### 3.4 为什么必须三层分离 (而非统一后处理)

#### 3.4.1 现有 Pipeline 的核心特征

```
FactorProcessingPipelineV2.transform()
├─ 按因子独立循环 (per-factor loop, line 1058)
│   ├─ 分类 → 软路由权重 (static/dynamic/mixed)
│   ├─ 多管道加权混合 (_apply_weighted_transform)
│   └─ 输出单个处理后的因子
└─ 返回 Dict[str, pd.DataFrame]  ← 每个因子独立处理完
```

**关键事实**: 在 `transform()` 返回前, 任何时刻 Pipeline 都不知道"其他因子"的存在。每个因子在分类→预处理全程都是**孤立处理**的。

#### 3.4.2 四类方法的架构兼容性诊断

| 方法 | 输入语义 | 与 Pipeline 兼容? | 原因 | 应属层 |
|---|---|---|---|---|
| 对称正交化 / PCA / GS | K 因子同时 (`(N, K)` per t) | **不兼容管道内部** | 管道是 per-factor 循环 | Layer 2 |
| 双重 Lasso / Elastic Net | K 因子 + Y | **完全不兼容管道** | 需收益 Y, 管道是无监督预处理 | Layer 3 |
| Ledoit-Wolf / Ridge (收缩) | 协方差矩阵 Σ (K×K) | **不兼容管道内部** | 需 K 因子同时计算 | Layer 2 子步骤 |
| 行业中性化 (现有 Neutralizer) | 单因子 + 行业 | **完全兼容, 已在管道内** | 单因子操作 | Layer 1 |

#### 3.4.3 为什么不重构 Pipeline 为全因子联合

| 选项 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| (a) 保持 per-factor | 不破坏 632 基线, 单因子诊断能力保留 | 正交化必须独立后处理 | ✅ 选择 |
| (b) 重构为全因子联合 | 正交化可插入管道 | 破坏 632 测试, 单因子诊断能力丧失, 重构成本高 | ❌ 否决 |

**决策 D11**: 保持 Pipeline per-factor 架构, 正交化作为独立后处理层。

### 3.5 三层之间的接口契约

#### 3.5.1 Layer 1 → Layer 2 接口

```python
# Layer 1 输出 (现有)
def transform(self, factor_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """每个因子 shape (N_stocks, T_dates)"""
    return results

# Layer 2 输入
class CrossSectionalOrthogonalizer:
    def fit(self, factor_dict: Dict[str, pd.DataFrame], **kwargs):
        """factor_dict: {因子名: 宽表 (N, T)}, K 个因子"""
    def transform(self, factor_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """输出同格式, K 个正交化后因子"""
```

#### 3.5.2 Layer 2 → Layer 3 接口

```python
# Layer 3 输入
class FactorSignificanceTest:
    def fit(self, factor_dict: Dict[str, pd.DataFrame], 
            fwd_returns: np.ndarray,
            factor_names: List[str],
            **kwargs):
        """factor_dict: 正交化后因子 (可选正交化)
        fwd_returns: (T, N) 前向收益
        factor_names: 待检验的因子列表
        """
    def test_incremental_alpha(self, target_factor: str) -> Dict:
        """返回: {coefficient, std_error, p_value, ci_lower, ci_upper}"""
```

### 3.6 Layer 3 与单因子流程兼容性深度分析

**用户担忧**: 双重 Lasso 与单因子流程处理是否很难兼容? 因为批量单因子无法感知其他因子的收益率, 也无法事先排序, 这个问题如何解决?

**结论**: 三层架构已设计性解决该矛盾。核心论点: **Layer 3 不在 Pipeline 内部跑, 而是在所有因子处理完之后跑**, 因此 per-factor 流程完全不受影响, 也无需事先排序。

#### 3.6.1 矛盾的本质

```
Pipeline.transform() 是 per-factor 循环 (pipelines_v2.py:1058):
  for factor_k in factors:
      processed_k = pipeline.transform(raw_k)  # 单因子进, 单因子出
                                                       # 不知其他 K-1 个因子存在
                                                       # 不知 Y (fwd_returns)

双重 Lasso 需要:
  Stage 1: Lasso Y ~ X_{-k}           ← 需要 Y + 其他 K-1 因子
  Stage 2: Lasso D_k ~ X_{-k}         ← 需要 D_k + 其他 K-1 因子
  Stage 3: OLS Y ~ D_k + X_{S}        ← 需要 Y + 全部 K 因子
```

这个矛盾**不是 bug, 而是三层架构的特性** — 把"需要 K 因子 + Y 的有监督检验"从 per-factor 无监督管道中物理隔离。

#### 3.6.2 实际数据流 (三层解耦)

```
Step 1 (Layer 1, per-factor, 已有, 不变):
  processed_dict = {}
  for k in factors:
      processed_dict[k] = Pipeline.transform(raw_dict[k])  # 单因子, 无感知
  → 输出: Dict[str, (N, T)] 共 K 个 DataFrame

Step 2 (Layer 2, cross-factor, 可选默认关闭):
  F_panel = stack(processed_dict)  # (N·T, K) 或 (N, T, K)
  T_panel = Orthogonalizer.transform(F_panel)  # K 因子同时在场
  → 输出: K 个正交化后因子 (或 Step 1 直通, 跳过正交化)

Step 3 (Layer 3, target-aware, 新增, 回测后):
  # 此时全部 K 因子 + Y 都已在主进程内存
  significance_results = {}
  for k in factors:
      significance_results[k] = FactorSignificanceTest.fit(
          F=T_panel,           # K 因子矩阵 (正交化后或原始)
          y=fwd_returns,       # 前向收益 (来自 BacktestEngine)
          target_factor=k      # 当前轮次 treatment
      )
  → 输出: Dict[str, {p_value, coef, ci}]
```

**关键点**: Layer 3 是**所有因子处理完之后的汇总分析**, 不参与 Pipeline.transform() 循环, 因此 per-factor 流程完全不受影响。

#### 3.6.3 "无法事先排序"是误解 — 双重 Lasso 不需要排序

| 方法 | 是否需要排序 | 排序影响 |
|---|---|---|
| Gram-Schmidt | 是 | 强影响 (首因子完全保留, 后续因子被投影) |
| Cholesky | 是 | 强影响 (类似 GS, 第一个因子完全保留) |
| **双重 Lasso** | **否** | **无影响** (每轮独立 OLS 估计, 无信息累积) |

双重 Lasso 的运行方式是**轮询当 treatment**:

```
轮次 1: D_1 = factor_1, X = {factor_2, ..., factor_K} → 得 p_1
轮次 2: D_2 = factor_2, X = {factor_1, factor_3, ..., factor_K} → 得 p_2
...
轮次 K: D_K = factor_K, X = {factor_1, ..., factor_{K-1}} → 得 p_K
```

每个因子独立得到自己的 p 值, **轮次顺序不影响结果** (因为每轮 Stage 3 都用 OLS 重新估计系数, 不存在信息累积)。这与 GS 的"前序投影影响后序"完全不同。

#### 3.6.4 与 parallel_runner.py 的兼容性

```
当前架构 (不变):
  parallel_runner 并行跑 K 个单因子回测
  → 每个进程: factor_k → Pipeline.transform → IC/收益
  → 主进程汇总: K 个结果

Layer 3 新增 (回测完成后, 主进程):
  K 个因子结果 + fwd_returns 都已在主进程内存
  → FactorSignificanceTest 在主进程跑 K 次双重 Lasso
  → 不需要修改 parallel_runner
  → 不需要进程间共享因子数据
  → 与并行架构正交, 完全兼容
```

Layer 3 是**回测后的离线分析步骤**, 与并行架构正交。

#### 3.6.5 真正需要解决的工程问题 (用户未提但重要)

| # | 问题 | 严重性 | 解决方案 |
|---|---|---|---|
| 1 | **日期对齐** — K 因子 NULL 过滤后有效股票数不同, 日期范围可能不一致 | 高 | Layer 3 入口强制 `intersect_dates(K 因子 + Y)`, 丢弃不齐日期 |
| 2 | **Y 的来源** — 双重 Lasso 需要 fwd_returns, 通常在 backtest 时才有 | 中 | Layer 3 接受 `BacktestEngine` 输出的 fwd_returns (与 IC 计算共享) |
| 3 | **K 大时计算量** — K=50 跑 50 次 LassoCV(5-fold), 约 1250 次 Lasso fit | 中 | 并行化 (joblib, K 个 treatment 独立可并行); 预筛选 ρ<0.3 的因子跳过 |
| 4 | **Stage 2 S_D = ∅** — D_k 与其他因子低相关时, Lasso 选不出控制变量 | 低 | 退化为 OLS Y ~ D_k + X_{S_Y}, 代码兜底处理 |

#### 3.6.6 兼容性结论

**D7'/D9'/D11/D12 的设计已经预先解决了"双重 Lasso 与单因子流程不兼容"问题**:

- 双重 Lasso 在 Layer 3, 不在 Pipeline 内 → 不需要单因子感知其他因子
- 双重 Lasso 在所有因子处理完后跑 → 此时 K 因子 + Y 全部在场
- 不需要事先排序 → treatment 轮询, 每个因子独立得 p 值
- 与 parallel_runner 正交 → 不修改并行架构

**这正是三层分离的价值** — 把"需要 K 因子 + Y 的有监督检验"从 per-factor 无监督管道中物理隔离, 避免架构冲突。

---

## 四、项目现状诊断与架构兼容性

### 4.1 关键发现

| 维度 | 现状 | 对 v2.5.0 的约束 |
|---|---|---|
| **正交化代码** | 全项目零代码, `modules/factor_orthogonalizer/` 不存在 | 需从零设计 |
| **架构语义** | Static/Dynamic/Mixed 三管道均为**单因子语义** (per-factor fit/transform) | 正交化必须多因子同时输入, **不能放在单因子管道内** (Layer 2) |
| **数据流** | Pipeline 输出 `Dict[str, pd.DataFrame]` shape `(N_stocks, T)`, 回测消费 `(T, N_stocks)` ndarray | 正交化模块输出须与 Pipeline 输出一致 |
| **已有诊断三件套** | Fingerprint (描述) + Decoupler (时序解耦) + 待建正交化 (横截面) | ADR-020 已定方向: 对称正交化为主方法 |
| **配置系统** | Pydantic + StepConfigV2 通用 enable/disable 机制 | 新增 `OrthogonalizationConfig` 即可接入 |
| **回测引擎** | 单因子独立评估, 无组合优化器 | 双重 Lasso 等 Layer 3 方法需扩展回测层 |
| **分类预处理顺序依赖** | 三管道分类→预处理是 per-factor 独立的, 无跨因子依赖 | 与 Layer 2/3 完全兼容, 无冲突 |

### 4.2 现有模块接口

#### 4.2.1 Factor_Fingerprint (Layer 1 子组件)

- **位置**: `modules/factor_fingerprint/core/fingerprint.py`
- **核心类**: `FactorFingerprinter` (line 86-522)
- **输入**: `factor_data: pd.DataFrame, shape (T, N)` (单因子面板)
- **输出**: `FactorFingerprint` NamedTuple, 13 维指标
- **与 Layer 2 关系**: Fingerprint 输出可用于 Layer 3 的分组正交化 (按因子类型分组)

#### 4.2.2 Factor_Decoupler (Layer 1 子组件)

- **位置**: `modules/factor_decoupler/core/`
- **核心类**: `TemporalDecoupler` (unified_decoupler.py:35-325)
- **职责**: **时序解耦** (非横截面正交化), 消除单因子时间序列的自相关
- **输入**: `X: pd.DataFrame` shape (T, N) (因子面板)
- **输出**: `X_decoupled: pd.DataFrame` 同 shape
- **关键澄清**: 横截面正交化 (Layer 2) 与时序正交化 (Layer 1 Decoupler) 是**正交概念**, 可串联使用形成双重正交

#### 4.2.3 Pipeline 阶段顺序 (Layer 1)

**StaticFactorPipeline** (pipelines_v2.py:606-657):
```
imputer → outlier → transform → [garch_whiten] → neutralize → standardize
```

**DynamicFactorPipeline** (pipelines_v2.py:660-754):
```
imputer → 三重中性化解耦 (CompositeDecoupler) → standardize
```

**MixedFactorPipeline** (pipelines_v2.py:757-870):
```
imputer → 温和去极值(3σ) → 条件性变换 → neutralize → standardize
```

**关键约束**: 三条管道均为单因子语义, 正交化必须放在 `FactorProcessingPipelineV2.transform()` 输出后 (Layer 2)。

#### 4.2.4 NeutralizerAdapter (Layer 1 子组件)

- **位置**: `adapters.py:409-599`
- **职责**: 行业中性化 (截面 OLS 回归取残差)
- **接口**: `fit(X: pd.DataFrame, **kwargs)` / `transform(X: pd.DataFrame) -> pd.DataFrame`
- **与正交化的关系**:
  - Neutralizer: 单因子, 消除外部变量暴露 (行业/市值)
  - Orthogonalizer: 多因子, 消除因子间相关性
  - **协同**: 先中性化后正交化 (先剥离外部风险, 再消除因子间冗余)

#### 4.2.5 回测引擎 (Layer 3 现有部分)

- **位置**: `backtest/engine.py:50-333`
- **输入**: `data_loader.factor_data: Dict[str, np.ndarray]` shape `(n_dates, n_stocks)`
- **当前能力**: 单因子独立评估, **无组合优化器, 无因子显著性检验**
- **v2.5.0 扩展**: 新增 `backtest/factor_significance.py` 实现双重 Lasso / Elastic Net

### 4.3 分类预处理与正交化的相容性分析 (回应用户担忧)

**用户担忧**: "我们已经将因子进行分类预处理, 这种顺序依赖的预处理与正交化、双重 Lasso 等方法是否相容?"

**结论**: **完全相容, 无需修改现有 Pipeline, 正交化和双重 Lasso 必须作为独立后处理层**。

**理由**:

1. **分类预处理是 per-factor 独立的** — 每个因子独立分类为 STATIC/DYNAMIC/MIXED, 独立走对应管道, 不依赖其他因子。这种独立性使 Layer 2/3 可以无缝接入, 不会破坏 Layer 1。

2. **正交化需要 K 因子同时在场** — 这是 Layer 1 无法提供的, 因为 Layer 1 在 `transform()` 返回前任何时刻都只处理一个因子。正交化必须等 Layer 1 处理完所有因子后, 在 Layer 2 统一处理。

3. **双重 Lasso 需要收益 Y** — Layer 1 是无监督预处理, 没有 Y。双重 Lasso 必须在 Layer 3 (回测层), 与 IC 计算同层, 因为 Y 来自回测数据加载。

4. **三层之间的语义清晰**:
   - Layer 1: "把每个因子单独处理成可用的标准化因子"
   - Layer 2: "把 K 个标准因子变换为 K 个不相关因子"
   - Layer 3: "检验每个因子在控制其他因子后是否还有增量 alpha"

5. **顺序依赖的预处理不影响正交化** — Static/Dynamic/Mixed 三管道的顺序依赖 (imputer → outlier → transform → neutralize → standardize) 是单因子内部的顺序, 与跨因子的正交化是不同维度, 互不干扰。

### 4.4 ADR-020 已定约束

```
- 主方法: 对称正交化 (Symmetric, T = F @ W, W = (F^T F)^(-1/2))
- 备选: Gram-Schmidt
- 禁止: 默认使用顺序依赖方法
- 诊断指标: VRR_k = Var(T_k)/Var(F_k), VRR << 1 表示因子 k 高度冗余
- 三件套关系: Fingerprint (描述) → Decoupler (时序解耦) → Orthogonalizer (横截面正交)
```

**v2.0 补充约束** (基于三层架构分析):
```
- 正交化对象: 横截面 (对象 A), F_t ∈ R^(N×K), per-t 估计 W
- 架构分层: Layer 1 (per-factor, 已有) / Layer 2 (cross-factor, 新增) / Layer 3 (target-aware, 新增)
- 双重 Lasso 位置: Layer 3 (回测子模块), 非诊断层
- Pipeline 不重构: 保持 per-factor 架构, 正交化作为独立后处理层
```

---

## 五、技术决策与理由

### 5.1 决策矩阵

| # | 决策 | 选项 | 选择 | 理由 | 学术/工程依据 |
|---|---|---|---|---|---|
| D1 | 默认触发策略 | 默认开启/默认关闭/条件触发 | **默认关闭** | 不破坏 632 测试基线; 用户显式开启避免意外行为 | 工程最佳实践 (向后兼容) |
| D2 | 窗口模式 | 仅滚动/仅全样本/两者都支持 | **两者都支持** | 回测用滚动 (避免 look-ahead), 研究用全样本 (快速分析) | 量化研究实践共识 |
| D3 | 分组正交化 | 纳入 O5/推迟 v2.6.0/不实现 | **纳入 O5** | 学术支撑强 (Stambaugh-Yuan 2017); 保留经济语义 | Stambaugh-Yuan 2017 |
| D4 | GPU 支持 | 可选依赖/不支持/必须支持 | **可选依赖** | 类似 arch 模式 (HAS_ARCH); 有 GPU 时加速 100x, 无 GPU 时回退 CPU | ADR-015 模式一致性 |
| D5 | 主方法 | 对称/GS/PCA/Cholesky | **对称正交化** | 无顺序依赖; VRR=1 完美保留总方差; 数学简洁 | Löwdin 1950; ADR-020 |
| D6 | 病态矩阵处理 | 截断/Ledoit-Wolf/不处理 | **Ledoit-Wolf 收缩** | 解决高维病态问题; 学术经典方法 | Ledoit-Wolf 2004 |
| **D7'** | **架构分层** | 单层后处理/三层分离 | **三层分离** | 各层职责清晰, 与现有架构兼容, 不破坏 per-factor 管道 | 架构兼容性分析 (§3.4) |
| D8 | 几何诊断指标 | VRR only/全套/最小集 | **全套 (VRR+κ+VIF+正交性误差)** | 多维诊断避免误判 | ADR-020 + 经典统计 |
| **D9'** | **双重 Lasso 位置** | O3 独立诊断/O4 回测子模块 | **O4 回测子模块 (Layer 3)** | 需要 Y, 属有监督检验, 与无监督正交化分层 | Belloni et al. 2014 |
| D10 | ML 方法纳入范围 | 全部/变换+选择/仅变换 | **变换类 (Layer 2) + 选择类 (Layer 3)** | 变换类做主算法, 选择类做检验, 各司其职 | Gu-Kelly-Xiu 2020 |
| **D11** | **Pipeline 是否重构** | 保持 per-factor/重构为联合 | **保持 per-factor** | 不破坏 632 基线, 正交化作为独立后处理层 | 架构兼容性 (§3.4.3) |
| **D12** | **Layer 2/3 模块位置** | 都在 orthogonalizer/分开 | **Layer 2 在 orthogonalizer, Layer 3 在 backtest** | 架构层不同, 职责不同 | 三层分离原则 |
| **D13** | **正交化对象** | A 横截面/B 收益时序/C 混合 | **A 横截面** | 与 Fingerprint/Decoupler 数据维度一致, ADR-020 方向 | §2.1 对象分析 |

### 5.2 关键决策详细理由

#### D7': 三层架构分离

**理由**:
- v1.0 报告把双重 Lasso 与对称正交化并列在 O3 诊断, 混淆了无监督变换 (Layer 2) 与有监督检验 (Layer 3)
- 三层分离使各层职责清晰: Layer 1 单因子预处理 (已有) / Layer 2 多因子横截面变换 / Layer 3 因子增量检验
- 与现有 Pipeline per-factor 架构完全兼容, 不需重构

**学术支撑**:
- Belloni-Chernozhukov-Hansen (2014) PDS 框架本身区分 selection stage 与 inference stage, 双重 Lasso 的 Stage 1/2 (selection) 与 Stage 3 (inference) 是分层设计的
- Gu-Kelly-Xiu (2020) RFS 将 transformation (PCA/Autoencoder) 与 prediction (Lasso/RF/GBM) 分层, transformation 属特征工程, prediction 属评估, 明确不混用
- Chernozhukov et al. (2018) "Generic ML Inference" 进一步明确 post-estimation inference 是独立层

**实践支撑**:
- Barra/Axioma 风险模型工业实践: 因子预处理 → 协方差估计 → 组合优化, 标准分层架构
- scikit-learn 设计哲学: transformer (fit/transform) / regressor (fit/predict) / classifier 分离, 不混用接口
- WorldQuant Alpha101 平台: 单因子回测 → 组合优化 → 风险评估, 三层独立

**对比**:
- 单层后处理: 把所有方法混在 orthogonalizer 模块, 职责不清, 双重 Lasso 需 Y 但 orthogonalizer 无 Y
- 三层分离: Layer 2 在 `modules/factor_orthogonalizer/`, Layer 3 在 `backtest/factor_significance.py`, 各自接入正确数据源

#### D9': 双重 Lasso 位置 (Layer 3 而非 O3 诊断)

**理由**:
- 双重 Lasso 需要收益 Y 作为标签, 而 O3 诊断是无监督的几何诊断 (VRR/κ/VIF)
- 把双重 Lasso 放在 O3 会导致 Layer 2 模块依赖回测数据, 破坏架构分层
- 正确位置是 Layer 3 (backtest/factor_significance.py), 与 IC 计算同层, 共享 fwd_returns 数据

**学术支撑**:
- Belloni-Chernozhukov-Hansen (2014) 原论文定位是 "inference on treatment effects after selection", 本质是 post-estimation 检验而非特征变换
- Chernozhukov et al. (2018) "Generic ML Inference" 明确将 double ML 归为 post-estimation 分析层, 与特征工程层分开
- 与对称正交化 (Löwdin 1950, 量子化学特征变换) 的学术渊源完全不同, 不应混层

**实践支撑**:
- sklearn 中 LassoCV 是 fit-predict 模式 (regressor), 不在 transform 链路 (transformer), 接口契约天然排斥混用
- Layer 2 输入无 Y, 接口契约 `fit(factor_dict)` 不接受 fwd_returns, 强制分层
- 与项目 ADR-013/016/019 一致: 按职责拆分模块, 处理 vs 评估分开

**实现**: O3 拆为 O3a (Layer 2 几何诊断, 无监督) + O3b (Layer 3 因子检验, 有监督, 实际放在 O4 回测扩展中)

#### D11: 保持 Pipeline per-factor 架构

**理由**:
- v2.4.0 基线 632 passed, 重构 Pipeline 为全因子联合处理会破坏所有测试
- per-factor 架构保留了单因子诊断能力 (Fingerprint 分类、单管道可视性)
- 正交化作为独立后处理层, 通过 Dict 接口接入, 无侵入性

**学术支撑**:
- Harvey-Liu-Zhu (2016) 的 t-stat > 3.0 阈值是单因子独立检验框架, 强调单因子显著性评估应独立于组合
- Hou-Xue-Zhang (2018) 复现 447 异象的 q-factor model 检验也是 per-factor 独立评估, 而非联合估计
- 单因子诊断范式 (Fingerprint 分类 + Decoupler 时序解耦) 要求 per-factor 处理保留

**实践支撑**:
- WorldQuant Alpha101 平台: 单因子回测是标配, 组合优化是独立步骤, 不混用
- 改 Pipeline 为联合需重写 632 测试, 得不偿失 (基线保护原则)
- 正交化通过 Dict 接口接入, 无侵入性, 符合"开放-封闭"原则

**对比**:
- 重构为联合: 需重写 transform() 为全因子循环, 破坏分类路由逻辑, 632 测试全部失效
- 保持 per-factor: Layer 1 不变, Layer 2 独立模块, 零回归风险

#### D12: Layer 2/3 模块位置分开

**理由**:
- Layer 2 (orthogonalizer) 属 `modules/`, 与 Fingerprint/Decoupler 同级, 是因子处理模块
- Layer 3 (factor_significance) 属 `backtest/`, 与 engine.py 同级, 是回测扩展
- 分开符合"处理 vs 评估"的架构分界

**学术支撑**:
- Layer 2 无分布假设 (正交化是纯线性代数变换), Layer 3 假设 sparsity (Lasso 稀疏性假设) — 统计假设不同
- Löwdin (1950, 量子化学) 与 Belloni et al. (2014, 因果推断) 学术渊源不同, 不应混层
- Stambaugh-Yuan (2017) 的 mispricing factors 检验也是后处理评估, 非特征变换

**实践支撑**:
- 与项目 ADR-013/016/019 一致: 按职责拆分模块 (Fingerprint/Decoupler/Imputer/Neutralizer/AdaptiveWinsor 各自独立)
- scikit-learn 设计哲学: transformer / regressor / classifier 分开, 不混用接口
- Layer 2 在 `modules/` (处理层), Layer 3 在 `backtest/` (评估层), 目录结构反映职责分界

#### D13: 正交化对象 A (横截面)

**理由**:
- 与 Fingerprint (T,N) 单因子面板、Decoupler (T,N) 时序解耦形成完整三件套
- 与 Pipeline 输出 `Dict[str, (N, T)]` 自然衔接, 堆叠为 `(T, N, K)` 面板
- VRR 诊断在截面才有经济意义 (因子 k 在股票截面上冗余)
- ADR-020 已明确"横截面"方向

**对比**:
- 对象 B (收益时序): 属风险因子提取, 与因子诊断三件套定位不同
- 对象 C (混合): 经济意义模糊, 实务少用

#### D1: 默认关闭 (`enabled=False`)

**理由**:
- v2.4.0 基线 632 passed, 默认关闭可保证零回归
- 正交化是**可选增强**, 不是必需步骤 (低相关因子无需正交)
- 用户显式开启后, 需自行验证 IC 变化和 VRR 诊断
- 符合 ADR-015 "OPTIONAL 依赖才保留 fallback" 的设计哲学

#### D2: 滚动 + 全样本都支持

**理由**:
- **回测/实盘**: 必须用滚动窗口 (252日), 避免 look-ahead bias (子模式 A2)
- **研究分析**: 全样本正交化快速, 用于因子相关性分析和冗余诊断
- 两种模式共用核心算法 (`SymmetricOrthogonalizer`), 仅外层包装不同

#### D5: 对称正交化为主方法

**理由**:
- **无顺序依赖**: 对所有因子对称处理, 不偏好任何因子 (vs GS/Cholesky 强顺序依赖)
- **VRR=1**: 完美保留总方差, 不丢失信息 (vs PCA 主成分可能丢弃)
- **数学简洁**: 一次 `eigh` 分解, 比 `sqrtm` 快 2-3x
- **与 Fingerprint 理念一致**: Factor_Fingerprint 强调因子平等描述, 对称正交化不引入人为优先级

#### D6: Ledoit-Wolf 收缩预处理

**理由**:
- 因子协方差矩阵在高维 (K>50) 或短样本 (T<K) 时病态
- 条件数 κ>1000 时 `(F^TF)^(-1/2)` 数值爆炸
- Ledoit-Wolf 收缩是学术经典方法, 有理论最优解

**实现**:
```python
def ledoit_wolf_shrinkage(S, T):
    """Ledoit-Wolf 收缩估计
    S: 样本协方差, T: 样本数
    """
    mu = np.trace(S) / S.shape[0]  # 平均方差
    F = mu * np.eye(S.shape[0])    # 目标矩阵
    # 计算最优收缩强度 alpha
    d2 = np.linalg.norm(S - F, 'fro')**2 / S.shape[0]
    b2 = min(d2, np.linalg.norm(S - F, 'fro')**2 / S.shape[0] / T)
    alpha = b2 / d2
    return alpha * F + (1 - alpha) * S
```

#### D8: 全套几何诊断指标

**理由**:
- 单一指标容易误判 (如 VRR 低可能是因子本身方差小, 而非冗余)
- 多维交叉验证:
  - VRR: 方差保留率
  - κ: 矩阵病态程度
  - VIF: 多重共线性
  - 正交性误差: 数值验证

---

## 六、功能设计 (O1-O6)

### 6.1 模块结构 (按三层重组)

```
factor_pipeline/
├── modules/factor_orthogonalizer/          # Layer 2: 多因子横截面变换
│   ├── __init__.py                         # 顶层 re-export
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base.py                         # BaseOrthogonalizer (sklearn 风格)
│   │   ├── symmetric.py                    # SymmetricOrthogonalizer (主方法)
│   │   ├── gram_schmidt.py                 # GramSchmidtOrthogonalizer (备选)
│   │   ├── pca.py                          # PCAOrthogonalizer (降维场景)
│   │   ├── cholesky.py                     # CholeskyOrthogonalizer (风险模型)
│   │   ├── ridge.py                        # RidgeOrthogonalizer (soft 正交化, 新增)
│   │   └── diagnostics.py                  # O3a: VRR/κ/VIF/正交性误差 (几何诊断)
│   ├── grouped.py                          # GroupedOrthogonalizer (分组正交化, O5)
│   ├── rolling.py                          # RollingOrthogonalizer (滚动窗口, O4)
│   └── utils/
│       ├── __init__.py
│       ├── shrinkage.py                    # Ledoit-Wolf 收缩
│       └── gpu.py                          # CuPy GPU 加速 (HAS_CUPY)
│
├── adapters.py                             # OrthogonalizerAdapter (O2, 与现有 adapter 同级)
├── config_v2.py                            # OrthogonalizationConfig (O2, Pydantic)
│
└── backtest/
    ├── engine.py                           # 现有: 单因子 IC 评估 (Layer 3 部分)
    └── factor_significance.py              # O3b/O4 扩展: 双重 Lasso / Elastic Net (Layer 3 新增)
```

### 6.2 O1: 算法核心 (Layer 2, P0)

#### 6.2.1 SymmetricOrthogonalizer (主方法)

```python
import numpy as np
from scipy.linalg import eigh

class SymmetricOrthogonalizer:
    """对称正交化 (Löwdin) — 横截面正交化 (对象 A)
    
    每个时点 t (或滚动窗口堆叠后), 输入 F ∈ R^(N × K):
        T = F @ W, W = (F^T F)^(-1/2)
    VRR = 1 (完美保留总方差)
    
    学术依据: Löwdin (1950)
    架构层: Layer 2 (无监督变换)
    """
    def fit(self, F: np.ndarray, min_eigval: float = 1e-10):
        """
        F: (N, K) 因子暴露矩阵 (单期) 或 (N·T_window, K) (滚动窗口堆叠)
           N = 股票数, K = 因子数
        """
        G = F.T @ F  # (K, K) Gram 矩阵
        eigvals, eigvecs = eigh(G)  # 对称矩阵专用, 比 eig 快 2-3x
        # 截断小特征值, 处理病态矩阵
        threshold = eigvals[-1] * min_eigval
        eigvals_clipped = np.maximum(eigvals, threshold)
        self.W_ = eigvecs @ np.diag(1.0 / np.sqrt(eigvals_clipped)) @ eigvecs.T
        # 诊断指标
        self.condition_number_ = eigvals[-1] / eigvals[0]
        self.eigvals_ = eigvals
        return self
    
    def transform(self, F: np.ndarray) -> np.ndarray:
        """F: (N, K) → T: (N, K) 同 shape"""
        return F @ self.W_
    
    def fit_transform(self, F: np.ndarray) -> np.ndarray:
        return self.fit(F).transform(F)
```

#### 6.2.2 GramSchmidtOrthogonalizer (备选)

```python
class GramSchmidtOrthogonalizer:
    """Gram-Schmidt 正交化 (修正版, 数值稳定)
    按因子 IC 或指定顺序正交化
    
    学术依据: 经典数值分析
    架构层: Layer 2 (无监督变换)
    """
    def fit(self, F: np.ndarray, order: List[int] = None):
        """
        F: (N, K) 因子暴露矩阵
        order: 因子正交化顺序 (默认按 IC 降序, Layer 3 计算后传入)
        """
        K = F.shape[1]
        if order is None:
            order = list(range(K))
        self.order_ = order
        # 修正 Gram-Schmidt 实现
        Q = np.zeros_like(F)
        for i, idx in enumerate(order):
            v = F[:, idx].copy()
            for j in range(i):
                v -= np.dot(Q[:, j], F[:, idx]) * Q[:, j]
            Q[:, i] = v / np.linalg.norm(v)
        self.Q_ = Q
        return self
```

#### 6.2.3 RidgeOrthogonalizer (新增, soft 正交化)

```python
class RidgeOrthogonalizer:
    """Ridge 正交化 (soft, 始终数值稳定)
    W = (F^T F + λI)^(-1/2)
    
    与 Ledoit-Wolf 关系: Ridge 是 LW 在 F^T F 谱上的特殊情况
    架构层: Layer 2 (无监督变换)
    """
    def fit(self, F: np.ndarray, lambda_: float = 1.0):
        """F: (N, K), lambda_: 正则化参数"""
        G = F.T @ F + lambda_ * np.eye(F.shape[1])
        eigvals, eigvecs = eigh(G)
        self.W_ = eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T
        return self
    
    def transform(self, F: np.ndarray) -> np.ndarray:
        return F @ self.W_
```

### 6.3 O2: 适配器层 (Layer 2 接入, P0)

#### 6.3.1 OrthogonalizerAdapter

```python
class OrthogonalizerAdapter:
    """正交化适配器 (sklearn fit/transform 风格)
    
    与 NeutralizerAdapter 模式一致, 但处理多因子输入
    架构层: Layer 2 (无监督变换)
    位置: Pipeline.transform() 输出后
    """
    def __init__(self, method: str = 'symmetric', 
                 enabled: bool = False,
                 **kwargs):
        self.method = method
        self.enabled = enabled
        self.kwargs = kwargs
        self._orthogonalizer = None
    
    def fit(self, factor_dict: Dict[str, pd.DataFrame], **kwargs):
        """
        factor_dict: {因子名: 宽表 (N_stocks, T_dates)}
        架构: 把 K 个因子的所有期堆叠为 (N·T, K) 估计 W (全样本模式)
              或在 RollingOrthogonalizer 中按窗口堆叠 (滚动模式)
        """
        if not self.enabled:
            return self
        # 堆叠为 (N·T, K) — 全样本模式
        F = self._stack_factors_cross_section(factor_dict)
        if self.method == 'symmetric':
            self._orthogonalizer = SymmetricOrthogonalizer()
        elif self.method == 'gram_schmidt':
            self._orthogonalizer = GramSchmidtOrthogonalizer()
        elif self.method == 'ridge':
            self._orthogonalizer = RidgeOrthogonalizer()
        self._orthogonalizer.fit(F, **self.kwargs)
        return self
    
    def transform(self, factor_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        if not self.enabled or self._orthogonalizer is None:
            return factor_dict
        # 对每期 t 应用 W: T_t = F_t @ W
        result = {}
        for name, df in factor_dict.items():
            # df: (N, T), 按列 (日期) 应用 W
            T_transformed = self._apply_per_period(df)
            result[name] = pd.DataFrame(T_transformed, index=df.index, columns=df.columns)
        return result
    
    def _stack_factors_cross_section(self, factor_dict):
        """堆叠为 (N·T, K) 横截面面板"""
        # 对齐所有因子的 (N, T), 堆叠为 (N·T, K)
        pass
    
    def _apply_per_period(self, df):
        """对每期 t: F_t (N×1) → T_t = F_t @ W (单因子时 W 为标量)
        多因子时需联合应用, 见 CrossSectionalOrthogonalizer"""
        pass
```

#### 6.3.2 OrthogonalizationConfig

```python
class OrthogonalizationConfig(BaseModel):
    """正交化配置 (Layer 2)"""
    enabled: bool = Field(default=False, description="启用正交化")
    method: str = Field(default='symmetric', description="方法: symmetric/gram_schmidt/pca/cholesky/ridge")
    window_mode: str = Field(default='full_sample', description="窗口: full_sample/rolling")
    window_size: int = Field(default=252, description="滚动窗口大小 (日)")
    min_obs: int = Field(default=60, description="最小样本数")
    shrinkage: bool = Field(default=True, description="Ledoit-Wolf 收缩")
    vrr_threshold: float = Field(default=0.3, description="VRR 冗余阈值")
    groups: Optional[Dict[str, List[str]]] = Field(default=None, description="分组正交化")
    use_gpu: bool = Field(default=False, description="GPU 加速 (需 CuPy)")
```

### 6.4 O3a: 几何诊断 (Layer 2, P0)

```python
class OrthogonalizationDiagnostics:
    """正交化几何诊断 (Layer 2, 无监督)
    
    与 Layer 3 因子检验 (双重 Lasso) 区分:
    - Layer 2 诊断: 变换质量验证 (VRR/κ/VIF/正交性误差)
    - Layer 3 检验: 因子增量 alpha (p 值/系数)
    """
    
    @staticmethod
    def compute_vrr(F: np.ndarray, T: np.ndarray) -> np.ndarray:
        """方差保留比例 (Variance Retention Ratio)
        VRR_k = Var(T_k) / Var(F_k)
        VRR < 0.3 → 因子 k 高度冗余
        """
        var_F = np.var(F, axis=0)
        var_T = np.var(T, axis=0)
        return var_T / var_F
    
    @staticmethod
    def compute_condition_number(F: np.ndarray) -> float:
        """条件数 κ = λ_max / λ_min"""
        G = F.T @ F
        eigvals = np.linalg.eigvalsh(G)
        return eigvals[-1] / eigvals[0]
    
    @staticmethod
    def compute_vif(F: np.ndarray) -> np.ndarray:
        """方差膨胀因子 (Variance Inflation Factor)
        VIF_k = 1 / (1 - R_k²)
        VIF > 5 → 严重多重共线性
        """
        K = F.shape[1]
        vifs = np.zeros(K)
        for k in range(K):
            others = np.delete(F, k, axis=1)
            target = F[:, k]
            beta = np.linalg.lstsq(others, target, rcond=None)[0]
            r_squared = 1 - np.sum((target - others @ beta)**2) / np.sum(target**2)
            vifs[k] = 1.0 / (1.0 - r_squared) if r_squared < 1.0 else float('inf')
        return vifs
    
    @staticmethod
    def compute_orthogonality_error(T: np.ndarray) -> float:
        """正交性误差 ‖Σ* - diag(Σ*)‖_F"""
        Sigma = np.corrcoef(T.T)
        Sigma_diag = np.diag(np.diag(Sigma))
        return np.linalg.norm(Sigma - Sigma_diag, 'fro')
```

### 6.5 O3b + O4: 回测集成与因子检验 (Layer 3, P1)

#### 6.5.1 RollingOrthogonalizer (Layer 2 滚动模式, O4)

```python
class RollingOrthogonalizer:
    """滚动窗口正交化 (避免 look-ahead bias) — Layer 2
    
    窗口: 252日 (1年) 或 504日 (2年)
    子模式: A2 (滚动窗口共享 W)
    优化: 滑动协方差更新 (增量更新, O(K²) 每次)
    """
    def __init__(self, window_size: int = 252, method: str = 'symmetric'):
        self.window_size = window_size
        self.method = method
        self.G_ = None  # 滚动 Gram 矩阵 (K×K)
        self.window_ = deque(maxlen=window_size)
    
    def fit_transform(self, F_panel: np.ndarray) -> np.ndarray:
        """
        F_panel: (T, N, K) 因子面板 (T 期, N 股票, K 因子)
        返回: (T, N, K) 正交化后因子面板
        每期 t: 用 [t-window, t-1] 的数据估计 W_t, 应用到 F_t
        """
        T, N, K = F_panel.shape
        result = np.zeros_like(F_panel)
        for t in range(T):
            # 移除最旧
            if len(self.window_) == self.window_size:
                F_old = self.window_[0]  # (N, K)
                self.G_ -= F_old.T @ F_old
            # 加入最新 (注意: 用 t-1 数据估计 W, 应用到 t, 避免 look-ahead)
            if t > 0:
                F_new = F_panel[t-1]  # (N, K)
                self.window_.append(F_new)
                if self.G_ is None:
                    self.G_ = F_new.T @ F_new
                else:
                    self.G_ += F_new.T @ F_new
            # 用累积 G 估计 W, 应用到当期
            if len(self.window_) >= self.min_obs:
                F_window = np.vstack(list(self.window_))  # (N·window, K)
                orth = SymmetricOrthogonalizer().fit(F_window)
                result[t] = orth.transform(F_panel[t])  # 当期截面应用 W
            else:
                result[t] = F_panel[t]  # 样本不足, 跳过
        return result
```

#### 6.5.2 FactorSignificanceTest (Layer 3, O3b/O4 新增)

```python
from sklearn.linear_model import LassoCV, ElasticNetCV

class FactorSignificanceTest:
    """因子增量显著性检验 (Layer 3, 有监督)
    
    架构层: Layer 3 (回测子模块)
    位置: backtest/factor_significance.py
    输入: K 因子 + 收益 Y
    输出: p 值 / 系数 / 置信区间
    
    学术依据: Belloni-Chernozhukov-Hansen (2014) Post-Double-Selection Lasso
    """
    
    def __init__(self, method: str = 'double_lasso'):
        self.method = method
    
    def fit(self, factor_dict: Dict[str, pd.DataFrame], 
            fwd_returns: np.ndarray,
            factor_names: List[str]):
        """
        factor_dict: {因子名: (N, T)} (可正交化或原始)
        fwd_returns: (T, N) 前向收益 (来自回测数据加载)
        factor_names: 待检验的所有因子
        """
        self.factor_names_ = factor_names
        # 堆叠为 (N·T, K) 因子矩阵 + (N·T,) 收益向量
        self.F_, self.y_ = self._stack_factor_returns(factor_dict, fwd_returns)
        return self
    
    def test_incremental_alpha(self, target_factor: str) -> Dict:
        """
        检验目标因子在控制其他因子后是否有增量 alpha
        
        Returns:
            {
                'coefficient': float,  # 净化后系数
                'std_error': float,    # 标准误
                'p_value': float,      # 显著性 p 值
                'ci_lower': float,     # 95% 置信区间下界
                'ci_upper': float,     # 95% 置信区间上界
                'selected_controls': List[str]  # 双重 Lasso 选中的控制变量
            }
        """
        if self.method == 'double_lasso':
            return self._double_lasso_test(target_factor)
        elif self.method == 'elastic_net':
            return self._elastic_net_path(target_factor)
    
    def _double_lasso_test(self, target_factor: str) -> Dict:
        """Belloni-Chernozhukov-Hansen (2014) 双重 Lasso
        
        Stage 1: Lasso y ~ X (X = 其他 K-1 因子) → 选出 S_Y
        Stage 2: Lasso D_k ~ X → 选出 S_D
        Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha
        """
        k_idx = self.factor_names_.index(target_factor)
        D_k = self.F_[:, k_idx]  # 目标因子 (treatment)
        X = np.delete(self.F_, k_idx, axis=1)  # 其他 K-1 因子 (controls)
        other_names = [n for i, n in enumerate(self.factor_names_) if i != k_idx]
        
        # Stage 1: Lasso y ~ X
        lasso_y = LassoCV(cv=5, max_iter=10000).fit(X, self.y_)
        S_Y = set(np.where(lasso_y.coef_ != 0)[0])
        
        # Stage 2: Lasso D_k ~ X
        lasso_d = LassoCV(cv=5, max_iter=10000).fit(X, D_k)
        S_D = set(np.where(lasso_d.coef_ != 0)[0])
        
        # Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D}
        selected = sorted(S_Y | S_D)
        X_selected = X[:, selected] if selected else np.empty((len(self.y_), 0))
        X_final = np.column_stack([D_k, X_selected])
        
        # OLS + 标准误
        beta = np.linalg.lstsq(X_final, self.y_, rcond=None)[0]
        residuals = self.y_ - X_final @ beta
        n, p = X_final.shape
        sigma2 = np.sum(residuals**2) / (n - p)
        cov = sigma2 * np.linalg.inv(X_final.T @ X_final)
        se = np.sqrt(np.diag(cov))
        
        # D_k 是第 0 个系数
        from scipy import stats
        coef = beta[0]
        std_err = se[0]
        t_stat = coef / std_err
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n-p))
        
        return {
            'coefficient': coef,
            'std_error': std_err,
            'p_value': p_value,
            'ci_lower': coef - 1.96 * std_err,
            'ci_upper': coef + 1.96 * std_err,
            'selected_controls': [other_names[i] for i in selected],
            't_statistic': t_stat,
        }
    
    def _elastic_net_path(self, target_factor: str) -> Dict:
        """Elastic Net 路径分析 (Layer 3)
        
        在不同 λ 下检查因子系数稳定性
        """
        k_idx = self.factor_names_.index(target_factor)
        # 留一: 目标因子作为 D_k, 其他作为 X
        D_k = self.F_[:, k_idx]
        X = np.delete(self.F_, k_idx, axis=1)
        y = self.y_
        
        # Elastic Net CV
        enet = ElasticNetCV(l1_ratio=[0.5, 0.7, 0.9], cv=5, max_iter=10000)
        enet.fit(np.column_stack([D_k, X]), y)
        
        return {
            'coefficient': enet.coef_[0],  # D_k 的系数
            'optimal_alpha': enet.alpha_,
            'optimal_l1_ratio': enet.l1_ratio_,
            'stability': 'stable' if abs(enet.coef_[0]) > 0.01 else 'weak',
        }
    
    def _stack_factor_returns(self, factor_dict, fwd_returns):
        """堆叠因子和收益为 (N·T, K) 和 (N·T,)"""
        # 实现细节: 对齐日期和股票
        pass
```

### 6.6 O5: 协同设计 (P1)

#### 6.6.1 GroupedOrthogonalizer (Layer 2, 分组正交化)

```python
class GroupedOrthogonalizer:
    """分组正交化: 组内对称正交 + 组间保留 — Layer 2
    
    学术依据: Stambaugh-Yuan (2017) 风险因子 vs alpha 因子区别处理
    架构层: Layer 2 (无监督变换)
    """
    def __init__(self, groups: Dict[str, List[str]]):
        """
        groups = {
            'value': ['PE', 'PB', 'PCF'],
            'momentum': ['MOM', 'REV'],
            'quality': ['ROE', 'ROA', 'Gross'],
            'size': ['Size', 'MCap'],
            'technical': ['VOL', 'ILLIQ', 'TURNOVER']
        }
        """
        self.groups = groups
        self.orthogonalizers_ = {}
    
    def fit(self, factor_dict: Dict[str, pd.DataFrame]):
        """对每组分别估计 W (组内正交, 组间保留)"""
        for group_name, factor_names in self.groups.items():
            # 堆叠组内因子为 (N·T, K_group)
            F_group = self._stack_group_cross_section(factor_dict, factor_names)
            self.orthogonalizers_[group_name] = SymmetricOrthogonalizer().fit(F_group)
        return self
    
    def transform(self, factor_dict):
        """应用组内正交化, 组间相关性保留"""
        result = {}
        for group_name, factor_names in self.groups.items():
            F_group = self._stack_group_cross_section(factor_dict, factor_names)
            T_group = self.orthogonalizers_[group_name].transform(F_group)
            # 拆分回单因子
            for i, f in enumerate(factor_names):
                result[f] = self._unstack_factor(T_group[:, i], factor_dict[f])
        return result
```

#### 6.6.2 与 Fingerprint/Decoupler 串联 (三件套)

```
因子诊断三件套 (跨 Layer 1/2):
1. Fingerprint (Layer 1 描述): extract_fingerprint → 13 维指标 + STATIC/DYNAMIC/MIXED 分类
2. Decoupler (Layer 1 时序解耦): 消除单因子自相关 (AR 残差/差分/HP 滤波)
3. Orthogonalizer (Layer 2 横截面正交): 消除因子间相关性 (对称正交化)

串联顺序:
原始因子 
  → Fingerprint (分类) [Layer 1]
  → 单因子管道 (含 Decoupler) [Layer 1]
  → Orthogonalizer (横截面正交) [Layer 2]
  → FactorSignificanceTest (增量检验) [Layer 3]
```

### 6.7 O6: 文档验证 (P1)

- ADR-020 状态更新为已实施 (补充三层架构约束)
- TDD 全量回归 (632+ 测试, 零回归)
- 手工数值校验:
  - SymmetricOrthogonalizer 与独立 numpy `eigh` 实现对比, 精度 < 1e-10
  - FactorSignificanceTest 与独立 statsmodels OLS 对比, 精度 < 1e-10
- EXECUTION_V2.5.0.md 执行记录

---

## 七、风险与陷阱清单

| # | 陷阱 | 严重性 | 架构层 | 规避方法 | 验证方法 |
|---|---|---|---|---|---|
| 1 | **Look-ahead bias** | 高 | Layer 2 | 滚动窗口 252 日, 仅用 t-1 及之前数据估计 W, 应用到 t | 对比滚动 vs 全样本 IC 差异 |
| 2 | **病态矩阵数值爆炸** | 高 | Layer 2 | Ledoit-Wolf 收缩 + 特征值截断 | 构造 κ>1000 测试用例 |
| 3 | **IC 大幅下降** | 中 | Layer 2→3 | 监控 IC 变化率, 阈值 > 0.8 | 正交前后 IC 对比测试 |
| 4 | **VRR << 1 (过度冗余)** | 中 | Layer 2 | 预筛选高相关因子 (ρ>0.9) | 构造 ρ=0.95 冗余因子测试 |
| 5 | **解释性丧失** | 中 | Layer 2 | 对称正交 + Varimax 旋转 (可选) | 主成分可解释性分析 |
| 6 | **顺序依赖偏差** | 低 | Layer 2 | 已禁用 GS 默认, 用对称 | 对比 GS 不同顺序结果 |
| 7 | **过度正交化** | 低 | Layer 2 | 仅对 ρ>0.3 的子集正交 | 独立因子正交化前后对比 |
| 8 | **滚动窗口不稳定** | 中 | Layer 2 | EWMA 平滑 + 最小窗口约束 | 滚动 vs 全样本稳定性测试 |
| 9 | **架构层混淆** | 高 | 跨层 | 双重 Lasso 放 Layer 3 (需 Y), 不放 Layer 2 诊断 | 接口契约测试: Layer 2 不接受 Y |
| 10 | **per-factor 管道破坏** | 高 | Layer 1 | 保持 Pipeline 不变, 正交化作独立后处理 | 632 基线回归测试 |
| 11 | **双重 Lasso 遗漏变量** | 中 | Layer 3 | Stage 2 (D_k ~ X) 捕获与 D_k 相关的因子 | 对比 Stage 1 only vs 双重 Lasso 系数 |
| 12 | **Elastic Net l1_ratio 调参** | 中 | Layer 3 | CV 选择 l1_ratio ∈ [0.5, 0.7, 0.9] | 路径稳定性测试 |

---

## 八、实施路线图

### 8.1 阶段拆解 (按三层重组)

```
v2.5.0 多因子正交化与因子检验 [ADR-020, P1]
│
├─ O1: Layer 2 算法核心 (P0)
│   ├─ SymmetricOrthogonalizer (主方法, 横截面对象 A)
│   ├─ GramSchmidtOrthogonalizer (备选)
│   ├─ PCAOrthogonalizer (降维)
│   ├─ CholeskyOrthogonalizer (风险模型)
│   └─ RidgeOrthogonalizer (soft 正交化, 新增)
│
├─ O2: Layer 2 适配器层 (P0)
│   ├─ OrthogonalizerAdapter (sklearn fit/transform, 接入 Pipeline 输出)
│   ├─ 配置: OrthogonalizationConfig (Pydantic)
│   └─ 接入 PipelineV2ConfigUnified
│
├─ O3a: Layer 2 几何诊断 (P0)
│   ├─ VRR_k 计算
│   ├─ 条件数 κ + VIF
│   ├─ 正交性误差验证
│   └─ 与 Fingerprint 集成 (因子诊断三件套)
│
├─ O3b + O4: Layer 3 因子检验 + 回测扩展 (P1)
│   ├─ FactorSignificanceTest (backtest/factor_significance.py)
│   ├─ 双重 Lasso (Belloni 2014 PDS) — 增量 alpha 检验
│   ├─ Elastic Net 路径 — 系数稳定性
│   ├─ RollingOrthogonalizer (Layer 2 滚动模式, 252 日)
│   ├─ IC 变化监控 (Layer 3)
│   └─ 端到端回测验证
│
├─ O5: 协同设计 (P1)
│   ├─ 与 Fingerprint/Decoupler 串联 (三件套)
│   ├─ GroupedOrthogonalizer (按因子类型分组)
│   ├─ 静态 vs 动态因子分别处理
│   └─ 与 NeutralizerAdapter 协同 (先中性化后正交)
│
└─ O6: 文档验证 (P1)
    ├─ ADR-020 状态更新 (补充三层架构约束)
    ├─ TDD 全量回归 (632+ 测试)
    ├─ 手工数值校验 (Layer 2 + Layer 3 分别校验)
    └─ EXECUTION_V2.5.0.md
```

### 8.2 依赖关系

```
O1 (Layer 2 算法) ──→ O2 (适配器) ──→ O3a (Layer 2 诊断)
                       │                    │
                       ↓                    ↓
                   O4 (Layer 3 检验 + 回测) ←── O3b (Layer 3 检验)
                       │
                       ↓
                   O5 (协同) ──→ O6 (文档)
```

### 8.3 实施优先级

| 阶段 | 优先级 | 依赖 | 验收 |
|---|---|---|---|
| O1 | P0 | 无 | 5 种算法 + 数值精度 < 1e-10 |
| O2 | P0 | O1 | 适配器接入 + 默认关闭不影响基线 |
| O3a | P0 | O1, O2 | 几何诊断 + VRR 识别冗余因子 |
| O3b | P1 | O2 | 双重 Lasso + Elastic Net 实现 |
| O4 | P1 | O3b | 滚动正交 + 回测集成 + IC 监控 |
| O5 | P1 | O1-O4 | 分组正交 + 三件套串联 |
| O6 | P1 | O1-O5 | 文档 + TDD 回归 + 手工校验 |

---

## 九、验收标准

| 验收项 | 标准 | 架构层 | 验证方法 |
|---|---|---|---|
| 全量回归 | ≥ 632 passed, 零回归 | 跨层 | `pytest factor_pipeline/tests/` |
| 数值正确性 (Layer 2) | 与独立 numpy eigh 实现对比精度 < 1e-10 | Layer 2 | 手工校验脚本 |
| 数值正确性 (Layer 3) | 与独立 statsmodels OLS 对比精度 < 1e-10 | Layer 3 | 手工校验脚本 |
| VRR 诊断 | 能识别 ρ>0.9 的冗余因子 (VRR<0.3) | Layer 2 | 构造冗余因子测试 |
| 双重 Lasso 检验 | 能识别有增量 alpha 的因子 (p<0.05) | Layer 3 | 构造已知 alpha 因子测试 |
| 性能 (Layer 2) | 50 因子全样本 < 5s; 滚动 252 窗口 < 60s | Layer 2 | 性能基准测试 |
| 滚动 vs 全样本 | IC 差异 < 20% | Layer 2 | 端到端回测对比 |
| 病态矩阵 | κ>1000 时不崩溃 (Ledoit-Wolf 收缩) | Layer 2 | 构造病态矩阵测试 |
| GPU 加速 | CuPy 可用时自动加速, 不可用时回退 CPU | Layer 2 | HAS_CUPY 测试 |
| 分组正交化 | 组内 VRR 提升, 组间相关性保留 | Layer 2 | 分组对比测试 |
| 默认关闭 | `enabled=False` 时不影响现有 632 测试 | 跨层 | 默认配置回归测试 |
| 架构层分离 | Layer 2 模块不依赖 fwd_returns (Y) | 跨层 | 接口契约测试 |
| per-factor 不破坏 | Pipeline per-factor 循环不变 | Layer 1 | 632 基线回归 |

---

## 附录 A: 学术文献完整引用

1. **Löwdin, P. O.** (1950). "On the Non-Orthogonality Problem Connected with the Use of Atomic Wave Functions in the Theory of Molecules and Crystals." *The Journal of Chemical Physics*, 18(3), 365-375.
2. **Fama, E. F., & French, K. R.** (1993). "Common risk factors in the returns on stocks and bonds." *Journal of Financial Economics*, 33(1), 3-56.
3. **Fama, E. F., & French, K. R.** (2015). "A five-factor asset pricing model." *Journal of Financial Economics*, 116(1), 1-22.
4. **Asness, C. S., Moskowitz, T. J., & Pedersen, L. H.** (2013). "Value and Momentum Everywhere." *The Journal of Finance*, 68(3), 929-985.
5. **Harvey, C. R., Liu, Y., & Zhu, H.** (2016). "... and the Cross-Section of Expected Returns." *The Review of Financial Studies*, 29(1), 5-68.
6. **Hou, K., Xue, C., & Zhang, L.** (2018). "Replicating Anomalies." *The Review of Financial Studies*, 33(5), 2019-2133.
7. **Hou, K., Xue, C., & Zhang, L.** (2015). "Digesting Anomalies: An Investment Approach." *The Review of Financial Studies*, 28(3), 650-705.
8. **Stambaugh, R. F., & Yuan, Y.** (2017). "Mispricing Factors." *The Review of Financial Studies*, 30(4), 1270-1315.
9. **Grinold, R. C., & Kahn, R. N.** (1999). *Active Portfolio Management* (2nd ed.). McGraw-Hill.
10. **Ledoit, O., & Wolf, M.** (2004). "Honey, I Shrunk the Sample Covariance Matrix." *The Journal of Portfolio Management*, 30(4), 110-119.
11. **Belloni, A., Chernozhukov, V., & Hansen, C.** (2014). "Inference on Treatment Effects after Selection among High-Dimensional Controls." *Review of Economic Studies*, 81(2), 608-650.
12. **Gu, S., Kelly, B., & Xiu, D.** (2020). "Empirical Asset Pricing via Machine Learning." *Review of Financial Studies*, 33(5), 2223-2273.

---

## 附录 B: 性能基准目标

| 指标 | 目标 | 架构层 | 验证方法 |
|---|---|---|---|
| 单次全样本正交化 (50因子) | < 5s | Layer 2 | 端到端计时 |
| 滚动窗口 (252窗口) | < 60s | Layer 2 | 滑动更新优化 |
| 内存峰值 | < 2GB | Layer 2 | 分块计算 |
| GPU 加速 (可选) | < 1s | Layer 2 | CuPy 实现 |
| eigh vs sqrtm | eigh 快 2-3x | Layer 2 | 微基准测试 |
| 双重 Lasso (50因子) | < 10s | Layer 3 | LassoCV 计时 |
| Elastic Net 路径 | < 15s | Layer 3 | ElasticNetCV 计时 |

---

## 附录 C: 修订日志

### v2.1 (2026-07-03) — Layer 3 兼容性深度分析 + 决策学术支撑补充

**修订原因**: 用户进一步质疑"双重 Lasso 与单因子流程处理是否很难兼容, 因为批量单因子无法感知其他因子的收益率, 也无法事先排序", 并要求为 D7'/D9'/D11/D12 四个决策补充学术与实践支撑。

**核心修订**:

1. **新增 §3.6 Layer 3 与单因子流程兼容性深度分析**
   - §3.6.1 矛盾的本质: per-factor 循环 vs 双重 Lasso 的 K 因子 + Y 需求
   - §3.6.2 实际数据流: 三层解耦 (Layer 1 per-factor → Layer 2 cross-factor → Layer 3 target-aware)
   - §3.6.3 "无法事先排序"是误解: 双重 Lasso 是 treatment 轮询, 每轮独立 OLS, 无信息累积 (vs GS 强顺序依赖)
   - §3.6.4 与 parallel_runner.py 兼容性: Layer 3 是回测后离线分析, 与并行架构正交
   - §3.6.5 真正需要解决的工程问题: 日期对齐 / Y 来源 / K 大计算量 / Stage 2 空集兜底
   - §3.6.6 兼容性结论: 三层分离已设计性解决该矛盾

2. **§5.2 D7'/D9'/D11/D12 补充学术与实践支撑**
   - D7' 学术: Belloni 2014 PDS 分层 / Gu-Kelly-Xiu 2020 transformation vs prediction 分层 / Chernozhukov 2018 Generic ML
   - D7' 实践: Barra/Axioma 工业分层 / sklearn transformer-regressor 分离 / WorldQuant Alpha101 三层独立
   - D9' 学术: Belloni 2014 原论文定位 post-estimation / Chernozhukov 2018 明确 double ML 属后估计层
   - D9' 实践: sklearn LassoCV 是 regressor 不在 transform 链路 / Layer 2 接口契约无 Y 强制分层
   - D11 学术: Harvey-Liu-Zhu 2016 t-stat > 3.0 单因子独立检验 / Hou-Xue-Zhang 2018 per-factor 评估
   - D11 实践: WorldQuant 单因子回测标配 / 基线保护原则 / 开放-封闭原则
   - D12 学术: Layer 2 无分布假设 vs Layer 3 sparsity 假设 / Löwdin 1950 vs Belloni 2014 学术渊源不同
   - D12 实践: ADR-013/016/019 职责拆分一致 / sklearn transformer-regressor-classifier 分开

### v2.0 (2026-07-03) — 三层架构彻底修订

**修订原因**: v1.0 存在三处架构设计缺陷, 在用户质疑"正交化对象是什么"和"双重 Lasso 与分类预处理是否相容"后暴露。

**核心修订**:

1. **正交化对象澄清** (§2.1)
   - v1.0: 数学定义 `F ∈ R^(T×K)` 与 ADR-020 "横截面"约束矛盾
   - v2.0: 统一为对象 A (横截面), `F_t ∈ R^(N×K)`, per-t 估计 W
   - 新增决策 D13 明确对象选择

2. **三层架构分离** (§3, §5 D7'/D11/D12)
   - v1.0: 把双重 Lasso 与对称正交化并列在 O3 诊断, 混淆无监督变换与有监督检验
   - v2.0: 明确 Layer 1 (per-factor, 已有) / Layer 2 (cross-factor 变换, 新增) / Layer 3 (target-aware 检验, 新增)
   - 双重 Lasso 从 O3 移到 O3b/O4 (Layer 3 回测子模块)
   - 新增决策 D7' (三层分离) / D11 (Pipeline 不重构) / D12 (模块位置分开)

3. **ML 方法四类分类** (§2.4)
   - v1.0: 仅列变换类方法, 未覆盖 ML 流行方法
   - v2.0: 新增变换类/选择类/收缩类/混合类四类对比, 明确各方法归属架构层
   - 新增 Ridge 正交化 (Layer 2) 和双重 Lasso (Layer 3) 到 v2.5.0 范围

4. **架构兼容性分析** (§3.4, §4.3)
   - v1.0: 未分析分类预处理与正交化的相容性
   - v2.0: 新增四类方法架构兼容性诊断, 明确"完全相容, 无需修改现有 Pipeline"

5. **O1-O6 重组** (§6)
   - v1.0: O3 混合几何诊断与因子检验
   - v2.0: O3 拆为 O3a (Layer 2 几何诊断) + O3b (Layer 3 因子检验, 实际在 O4)
   - 新增 RidgeOrthogonalizer (O1)
   - 新增 FactorSignificanceTest (O3b/O4)

6. **风险清单扩展** (§7)
   - v1.0: 8 项风险
   - v2.0: 12 项风险, 新增架构层混淆 (陷阱 9) / per-factor 破坏 (陷阱 10) / 双重 Lasso 遗漏变量 (陷阱 11) / Elastic Net 调参 (陷阱 12)

7. **验收标准扩展** (§9)
   - v1.0: 9 项验收
   - v2.0: 13 项验收, 新增 Layer 3 数值正确性 / 双重 Lasso 检验 / 架构层分离 / per-factor 不破坏

### v1.0 (2026-07-03) — 初版

- 5 种正交化方法比较
- 12 篇经典学术文献
- 8 项技术决策 (D1-D8)
- O1-O6 功能设计
- 8 个风险陷阱
- 实施路线图与验收标准

---

**报告版本**: v2.1
**创建时间**: 2026-07-03
**修订时间**: 2026-07-03 (v2.1: Layer 3 兼容性深度分析 + 决策学术支撑补充)
**作者**: Scott Peng Liu
**审核状态**: 待用户确认后进入 O1 实施
