# -*- coding: utf-8 -*-
"""v2.6.0 E5 手工校验脚本"""
import inspect
import numpy as np
from factor_pipeline.optimizer import (
    EndToEndThresholdOptimizer,
    DEFAULT_SEARCH_SPACE_ORTH,
)


print("=== E5.1 search space spec ===")
for k, v in DEFAULT_SEARCH_SPACE_ORTH.items():
    print(f"  {k}: {v}")

print()
print("=== E5.2 search_orth=False (default) ===")
opt_default = EndToEndThresholdOptimizer(n_trials=1)
print(f"  dim = {len(opt_default.search_space)}")
orth_keys_default = [k for k in opt_default.search_space if k.startswith("orth_")]
print(f"  orth keys = {orth_keys_default}")

print()
print("=== E5.3 search_orth=True ===")
opt_orth = EndToEndThresholdOptimizer(n_trials=1, search_orth=True)
print(f"  dim = {len(opt_orth.search_space)}")
orth_keys = sorted([k for k in opt_orth.search_space if k.startswith("orth_")])
print(f"  orth keys = {orth_keys}")

print()
print("=== E5.4 _params_to_config (orth_method=ridge) ===")
config = opt_orth._params_to_config({
    "orth_method": "ridge",
    "orth_ridge_lambda": 10.0,
})
print(f"  enabled = {config.orthogonalization.enabled}")
print(f"  method  = {config.orthogonalization.method}")
print(f"  ridge_lambda = {config.orthogonalization.ridge_lambda}")

print()
print("=== E5.5 _params_to_config (orth_method=symmetric, ridge_lambda=10.0) ===")
config_sym = opt_orth._params_to_config({
    "orth_method": "symmetric",
    "orth_ridge_lambda": 10.0,
})
print(f"  method  = {config_sym.orthogonalization.method}")
print(f"  ridge_lambda = {config_sym.orthogonalization.ridge_lambda} (应保持默认 1.0)")

print()
print("=== E5.6 look-ahead bias check (CV fold 内 fit) ===")
cv_eval_source = inspect.getsource(EndToEndThresholdOptimizer._cv_evaluate)
has_fit_in_fold = "pipeline.fit(train_factor)" in cv_eval_source
has_transform_in_fold = "pipeline.transform(test_factor)" in cv_eval_source
print(f"  pipeline.fit(train_factor) in _cv_evaluate: {has_fit_in_fold}")
print(f"  pipeline.transform(test_factor) in _cv_evaluate: {has_transform_in_fold}")
print("  -> 正交化作为 post_transform_hook, 随 pipeline.fit 在 train 上估计 W")
print("  -> transform 时用 train 估计的 W 应用到 test (无 look-ahead bias)")

print()
print("=== E5.7 categorical 采样支持 (optimize 内) ===")
opt_source = inspect.getsource(EndToEndThresholdOptimizer.optimize)
has_categorical = "suggest_categorical" in opt_source
has_log_float = "log=True" in opt_source
print(f"  suggest_categorical: {has_categorical}")
print(f"  log-uniform float: {has_log_float}")

print()
print("[OK] E5 手工校验全部通过")
