# -*- coding: utf-8 -*-
"""
面板分层插补策略
结合截面和时序信息的分层插补方法
"""

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats

try:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
except ImportError:
    StandardScaler = None
    PCA = None

from ..core.base import BaseImputer
