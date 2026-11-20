# -*- coding: utf-8 -*-
"""v3.9.0 E2（S3）：12 条不变量常驻 + 注册表自检。"""
import pytest

from tests.invariants import INVARIANTS, Invariant, register, run_all
from tests.synthetic import SCENARIOS


@pytest.mark.parametrize("inv", INVARIANTS, ids=[item.name for item in INVARIANTS])
def test_invariant(inv):
    results = {name: (ok, detail) for name, ok, detail in run_all()}
    ok, detail = results[inv.name]
    assert ok, "[%s] %s" % (inv.name, detail)


def test_registry_rejects_duplicate():
    dup = Invariant(
        name=INVARIANTS[0].name, module="x", kind="bound",
        scenario="clean", check=lambda panel: (True, ""))
    with pytest.raises(ValueError):
        register(dup)


def test_registry_unique_and_nonempty():
    assert len(INVARIANTS) == 12
    assert len({item.name for item in INVARIANTS}) == 12
    assert all(item.scenario in SCENARIOS for item in INVARIANTS)
    assert all(item.kind in ("bound", "monotonic", "invariant", "equivalence")
               for item in INVARIANTS)
