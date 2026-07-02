# -*- coding: utf-8 -*-
"""
Fix 2 手工校验: 逐字段对比手工期望值与程序输出

构造一个自定义 Unified 配置, 手工列出期望的 dataclass 字段值,
调用 to_pipeline_v2_config(), 逐字段对比.
"""
import sys
from pathlib import Path

_PROJECT_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
for ext in ["F:/Coding/Factor_Fingerprint", "F:/Coding/Factor_Decoupler"]:
    if ext not in sys.path:
        sys.path.insert(0, ext)

from factor_pipeline.config_v2 import (
    PipelineV2ConfigUnified,
    StaticPipelineConfig, DynamicPipelineConfig, MixedPipelineConfig,
    GarchConfig, TransformationConfig,
)
from factor_pipeline.pipelines_v2 import PipelineV2Config


def main():
    print("=" * 70)
    print("Fix 2 手工校验: Unified → dataclass 字段映射")
    print("=" * 70)

    # ── 构造自定义 Unified 配置 ──
    unified = PipelineV2ConfigUnified(
        hard_routing_prob=0.78,
        merge_alpha=0.35,
        ks_alpha=0.02,
        mixed_winsor_sigma=2.7,
        classification_threshold_static=0.82,
        classification_threshold_dynamic=0.38,
        enable_monitoring=True,
        static=StaticPipelineConfig(garch=GarchConfig(
            enabled=True, p=2, q=1, vol='EGarch', min_obs=80,
        )),
        dynamic=DynamicPipelineConfig(
            decorrelation_strength=0.85,
            max_ar_order=7,
            ar_criterion='bic',
        ),
        mixed=MixedPipelineConfig(
            conditional_transform=False,
            transformation=TransformationConfig(
                skew_threshold=1.8, kurt_threshold=4.5,
            ),
        ),
    )

    # ── 手工期望值 (独立计算, 不依赖程序) ──
    expected = {
        # 4 共享字段 (直接复制)
        'hard_routing_prob': 0.78,
        'merge_alpha': 0.35,
        'ks_alpha': 0.02,
        'mixed_winsor_sigma': 2.7,
        # 概念对应字段
        'classification.static_ar1_threshold': 0.82,
        'classification.dynamic_ar1_threshold': 0.38,
        # 嵌套 → 扁平 (static.garch.*)
        'static_enable_garch': True,
        'static_garch_p': 2,
        'static_garch_q': 1,
        'static_garch_vol': 'EGarch',
        'static_garch_min_obs': 80,
        # 嵌套 → 扁平 (dynamic.*)
        'dynamic_decorrelation_strength': 0.85,
        'dynamic_max_ar_order': 7,
        'dynamic_ar_criterion': 'bic',
        # 嵌套 → 扁平 (mixed.*)
        'mixed_conditional_transform': False,
        'mixed_skew_threshold': 1.8,
        'mixed_kurt_threshold': 4.5,
    }

    # ── 调用程序转换 ──
    dc = unified.to_pipeline_v2_config()
    dc2 = PipelineV2Config.from_unified(unified)  # 备选入口

    # ── 逐字段对比 ──
    print("\n[1] 4 共享字段 (直接复制):")
    shared_fields = ['hard_routing_prob', 'merge_alpha', 'ks_alpha', 'mixed_winsor_sigma']
    for f in shared_fields:
        actual = getattr(dc, f)
        exp = expected[f]
        ok = abs(actual - exp) < 1e-9
        print(f"  {f:30s}: 期望={exp:.6f}, 实际={actual:.6f}  {'✓' if ok else '✗'}")

    print("\n[2] 概念对应字段 (classification_threshold_* → classification.*_ar1_threshold):")
    cls_fields = [
        ('classification.static_ar1_threshold', dc.classification.static_ar1_threshold, 0.82),
        ('classification.dynamic_ar1_threshold', dc.classification.dynamic_ar1_threshold, 0.38),
    ]
    for name, actual, exp in cls_fields:
        ok = abs(actual - exp) < 1e-9
        print(f"  {name:50s}: 期望={exp:.6f}, 实际={actual:.6f}  {'✓' if ok else '✗'}")

    print("\n[3] 嵌套 → 扁平 (static.garch.* → static_garch_*):")
    garch_fields = [
        ('static_enable_garch', dc.static_enable_garch, True),
        ('static_garch_p', dc.static_garch_p, 2),
        ('static_garch_q', dc.static_garch_q, 1),
        ('static_garch_vol', dc.static_garch_vol, 'EGarch'),
        ('static_garch_min_obs', dc.static_garch_min_obs, 80),
    ]
    for name, actual, exp in garch_fields:
        ok = actual == exp
        print(f"  {name:30s}: 期望={exp!r}, 实际={actual!r}  {'✓' if ok else '✗'}")

    print("\n[4] 嵌套 → 扁平 (dynamic.* → dynamic_*):")
    dyn_fields = [
        ('dynamic_decorrelation_strength', dc.dynamic_decorrelation_strength, 0.85),
        ('dynamic_max_ar_order', dc.dynamic_max_ar_order, 7),
        ('dynamic_ar_criterion', dc.dynamic_ar_criterion, 'bic'),
    ]
    for name, actual, exp in dyn_fields:
        ok = (abs(actual - exp) < 1e-9) if isinstance(exp, float) else (actual == exp)
        print(f"  {name:35s}: 期望={exp!r}, 实际={actual!r}  {'✓' if ok else '✗'}")

    print("\n[5] 嵌套 → 扁平 (mixed.* → mixed_*):")
    mix_fields = [
        ('mixed_conditional_transform', dc.mixed_conditional_transform, False),
        ('mixed_skew_threshold', dc.mixed_skew_threshold, 1.8),
        ('mixed_kurt_threshold', dc.mixed_kurt_threshold, 4.5),
    ]
    for name, actual, exp in mix_fields:
        ok = (abs(actual - exp) < 1e-9) if isinstance(exp, float) else (actual == exp)
        print(f"  {name:35s}: 期望={exp!r}, 实际={actual!r}  {'✓' if ok else '✗'}")

    print("\n[6] enable_monitoring → monitor.enable_smooth_transition:")
    ok = dc.monitor.enable_smooth_transition == True
    print(f"  monitor.enable_smooth_transition: 期望=True, 实际={dc.monitor.enable_smooth_transition}  {'✓' if ok else '✗'}")

    print("\n[7] from_unified() 备选入口一致性:")
    ok = (abs(dc.hard_routing_prob - dc2.hard_routing_prob) < 1e-9 and
          abs(dc.merge_alpha - dc2.merge_alpha) < 1e-9 and
          abs(dc.ks_alpha - dc2.ks_alpha) < 1e-9 and
          abs(dc.mixed_winsor_sigma - dc2.mixed_winsor_sigma) < 1e-9)
    print(f"  to_pipeline_v2_config() vs from_unified(): 4 共享字段一致  {'✓' if ok else '✗'}")

    print("\n[8] 旧版 to_pipeline_config() 兼容层仍可用:")
    legacy = unified.to_pipeline_config()
    ok = legacy is not None
    print(f"  to_pipeline_config() 返回非 None  {'✓' if ok else '✗'}")

    print("\n" + "=" * 70)
    print("手工校验完成")
    print("=" * 70)


if __name__ == '__main__':
    main()
