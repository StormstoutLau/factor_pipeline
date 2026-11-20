# -*- coding: utf-8 -*-
"""v3.9.0 步骤级追溯（默认关闭，零 IO）。

依据：DESIGN_SYNTHETIC_VALIDATION_TRACEABILITY.md §6（v1.3）。
顶层依赖：stdlib + numpy；pandas 仅在 DataFrame 分支内延迟 import（P-2 裁决）。
"""
import hashlib
import json
import os
import uuid
from datetime import datetime

import numpy as np

__all__ = ["PipelineTrace", "content_hash", "find_first_divergence"]

TRACE_VERSION = "1"


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError("content_hash 不支持: %r" % (type(value),))


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=_json_default)


def _df_stats(frame):
    numeric = frame.select_dtypes(include="number")
    return {
        "columns": [str(c) for c in frame.columns],
        "sum": [float(v) if np.isfinite(v) else "NaN" for v in numeric.sum().tolist()],
        "mean": [float(v) if np.isfinite(v) else "NaN" for v in numeric.mean().tolist()],
        "nan": [int(v) for v in frame.isna().sum().tolist()],
    }


def content_hash(obj):
    """ndarray / DataFrame / Mapping / Sequence / 标量 → 'sha256:' + hex。

    DataFrame 分支：`_content_digest`（首/中/尾抽样）**加**全量列 sum/mean/NaN 计数，
    避免抽样行之外的中段篡改漏检（步骤 6 M-3）。
    """
    digest = hashlib.sha256()
    _update(digest, obj)
    return "sha256:" + digest.hexdigest()


def _update(digest, obj):
    if isinstance(obj, np.ndarray):
        arr = np.asarray(obj)
        digest.update(b"nd|" + str(arr.shape).encode("ascii")
                      + b"|" + arr.dtype.str.encode("ascii") + b"|")
        if arr.dtype.kind in "fc":
            data = np.ascontiguousarray(arr, dtype=np.float64)
            mask = np.isnan(data)
            # ±inf 保留原值（IEEE bytes 唯一），仅 NaN 折 0.0 并以 mask 区分；
            # 折叠 inf 会使 [inf]/[0.0]、[+inf]/[-inf] hash 冲突（审计 H1）。
            digest.update(np.nan_to_num(data, nan=0.0).tobytes())
            digest.update(b"|nan|" + mask.tobytes())
        else:
            digest.update(np.ascontiguousarray(arr).tobytes())
        return
    if isinstance(obj, bool) or isinstance(obj, np.bool_):
        digest.update(b"bool|" + (b"1" if bool(obj) else b"0"))
        return
    if isinstance(obj, (int, float, np.integer, np.floating)):
        digest.update(b"num|" + repr(float(obj)).encode("ascii"))
        return
    if isinstance(obj, str):
        digest.update(b"str|" + obj.encode("utf-8"))
        return
    if obj is None:
        digest.update(b"none|")
        return
    if isinstance(obj, dict):
        digest.update(b"map|")
        for key in sorted(obj, key=lambda item: str(item)):
            digest.update(str(key).encode("utf-8") + b"=")
            _update(digest, obj[key])
            digest.update(b";")
        return
    if isinstance(obj, (list, tuple)):
        digest.update(b"seq|")
        for item in obj:
            _update(digest, item)
            digest.update(b";")
        return

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas 为既有核心依赖
        pd = None
    if pd is not None and isinstance(obj, pd.DataFrame):
        from backtest.data_contract import _content_digest
        digest.update(b"df|" + _content_digest(obj).encode("ascii"))
        digest.update(b"|stats|" + _canonical(_df_stats(obj)).encode("utf-8"))
        return
    raise TypeError("content_hash 不支持: %r" % (type(obj),))


def _package_version():
    try:
        from factor_pipeline import __version__
        return str(__version__)
    except Exception:  # noqa: BLE001 - 版本缺失不应阻断 trace
        return "unknown"


class _NullStep(object):
    """enabled=False 的空实现：不计算 hash、不写文件。"""

    def __enter__(self):
        return self

    def add_input(self, name, obj, rows=None, cols=None):
        return self

    def add_output(self, name, obj, rows=None, cols=None):
        return self

    def diagnostic(self, key, value):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TraceStep(object):
    def __init__(self, trace, name, params):
        self._trace = trace
        self._name = name
        self._params = params
        self._inputs = []
        self._outputs = []
        self._diagnostics = {}
        self._status = "ok"
        self._error = None
        self._started_at = None

    def __enter__(self):
        self._started_at = datetime.now().isoformat()
        return self

    def add_input(self, name, obj, rows=None, cols=None):
        self._inputs.append(self._entry(name, obj, rows, cols))
        return self

    def add_output(self, name, obj, rows=None, cols=None):
        self._outputs.append(self._entry(name, obj, rows, cols))
        return self

    def diagnostic(self, key, value):
        self._diagnostics[str(key)] = value
        return self

    @staticmethod
    def _entry(name, obj, rows, cols):
        if rows is None and hasattr(obj, "shape") and len(obj.shape) >= 1:
            rows = int(obj.shape[0])
        if cols is None and hasattr(obj, "shape") and len(obj.shape) == 2:
            cols = int(obj.shape[1])
        return {"name": name, "hash": content_hash(obj),
                "rows": rows, "cols": cols}

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._status = "error"
            self._error = ("%s: %s" % (exc_type.__name__, exc))[:200]
        record = {
            "trace_version": TRACE_VERSION,
            "code_version": self._trace.code_version,
            "run_id": self._trace.run_id,
            "step": self._name,
            "seq": self._trace._next_seq(),
            "started_at": self._started_at,
            "params_hash": content_hash(self._params),
            "inputs": self._inputs,
            "outputs": self._outputs,
            "diagnostics": self._diagnostics,
            "status": self._status,
        }
        if self._error:
            record["error"] = self._error
        self._trace._write(record)
        return False


class PipelineTrace(object):
    def __init__(self, path=None, enabled=False, code_version=None):
        self.enabled = bool(enabled)
        self.path = path
        if self.enabled and not path:
            raise ValueError("enabled=True 时必须提供 path")
        self.code_version = code_version or _package_version()
        self._run_id = (datetime.now().strftime("%Y%m%dT%H%M%S")
                        + "-" + uuid.uuid4().hex[:6])
        self._seq = 0

    @property
    def run_id(self):
        return self._run_id

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def step(self, name, **params):
        if not self.enabled:
            return _NullStep()
        return TraceStep(self, name, params)

    def _write(self, record):
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n")

    def close(self):
        return None


def _load(path):
    if isinstance(path, (list, tuple)):
        return [dict(item) for item in path]
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def find_first_divergence(trace_a, trace_b):
    """按 seq 对齐比较；返回首个不一致事件 {seq, step, field, a, b} 或 None。"""
    a = _load(trace_a)
    b = _load(trace_b)
    n = min(len(a), len(b))
    for i in range(n):
        ra, rb = a[i], b[i]
        for field in ("step", "params_hash"):
            if ra.get(field) != rb.get(field):
                return {"seq": ra.get("seq"), "step": ra.get("step"),
                        "field": field, "a": ra.get(field), "b": rb.get(field)}
        for key in ("inputs", "outputs"):
            ha = [item.get("hash") for item in ra.get(key, [])]
            hb = [item.get("hash") for item in rb.get(key, [])]
            if len(ha) != len(hb):
                return {"seq": ra.get("seq"), "step": ra.get("step"),
                        "field": key + ".length", "a": len(ha), "b": len(hb)}
            for j, (left, right) in enumerate(zip(ha, hb)):
                if left != right:
                    return {"seq": ra.get("seq"), "step": ra.get("step"),
                            "field": "%s[%d].hash" % (key, j),
                            "a": left, "b": right}
    if len(a) != len(b):
        longer = a if len(a) > len(b) else b
        record = longer[n]
        return {"seq": record.get("seq"), "step": record.get("step"),
                "field": "length", "a": len(a), "b": len(b)}
    return None
