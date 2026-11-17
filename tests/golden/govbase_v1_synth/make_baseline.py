# -*- coding: utf-8 -*-
"""生成 tests/golden/govbase_v1_synth 真实管线基线（E6）。

运行::

    python tests/golden/govbase_v1_synth/make_baseline.py

基线只依赖确定性合成面板（固定 seed + 固定日期），不含 RNG 敏感步骤。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from factor_pipeline.backtest.golden_master import GoldenMaster  # noqa: E402
from factor_pipeline.pipelines_v2 import (  # noqa: E402
    FactorProcessingPipelineV2,
    PipelineV2Config,
)
from factor_pipeline.reporting import PipelineExecutionReport  # noqa: E402

BASELINE_ID = "govbase_v1_synth"
GENERATOR = "tests/golden/govbase_v1_synth/make_baseline.py"


def build_inputs(seed: int = 20261117, n_periods: int = 36,
                 n_stocks: int = 20) -> dict:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-31", periods=n_periods, freq="ME")
    columns = ["S%02d" % i for i in range(n_stocks)]
    return {
        "mom_1m": pd.DataFrame(
            rng.normal(size=(n_periods, n_stocks)),
            index=dates, columns=columns,
        ),
        "vol_3m": pd.DataFrame(
            rng.normal(size=(n_periods, n_stocks)),
            index=dates, columns=columns,
        ),
    }


def build_outputs() -> dict:
    data = build_inputs()
    pipeline = FactorProcessingPipelineV2(PipelineV2Config())
    pipeline.fit(data)
    return pipeline.transform(data)


def main() -> Path:
    master = GoldenMaster(root=str(ROOT / "tests" / "golden"))
    path = master.capture(
        BASELINE_ID,
        build_outputs(),
        {
            "pipeline_version": PipelineExecutionReport().pipeline_version,
            "generator": GENERATOR,
        },
    )
    print(path)
    return Path(path)


if __name__ == "__main__":
    main()
