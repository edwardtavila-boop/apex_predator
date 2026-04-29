from __future__ import annotations

import pytest

from eta_engine.scripts.sweep_crypto_orb_eth import (
    _parse_float_list,
    _parse_int_list,
)


def test_parse_int_list_accepts_comma_values() -> None:
    assert _parse_int_list("60, 120,240") == (60, 120, 240)


def test_parse_float_list_accepts_comma_values() -> None:
    assert _parse_float_list("1.0, 1.5,2") == (1.0, 1.5, 2.0)


def test_parse_grid_lists_reject_empty_values() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _parse_int_list(" , ")
    with pytest.raises(ValueError, match="at least one"):
        _parse_float_list(" , ")
