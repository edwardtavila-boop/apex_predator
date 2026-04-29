from __future__ import annotations

from eta_engine.data import library as data_library
from eta_engine.scripts import sweep_orb_params


def test_parse_grid_lists_accept_cli_overrides() -> None:
    assert sweep_orb_params._parse_int_list("5, 15") == [5, 15]
    assert sweep_orb_params._parse_float_list("1.25, 2") == [1.25, 2.0]


def test_build_grid_uses_cli_override_dimensions() -> None:
    grid = sweep_orb_params._build_grid(
        range_minutes=[5],
        rr_targets=[2.0, 3.0],
        atr_stop_mults=[1.5],
        ema_periods=[0, 200],
    )

    assert grid == [
        sweep_orb_params.SweepCell(5, 2.0, 1.5, 0),
        sweep_orb_params.SweepCell(5, 2.0, 1.5, 200),
        sweep_orb_params.SweepCell(5, 3.0, 1.5, 0),
        sweep_orb_params.SweepCell(5, 3.0, 1.5, 200),
    ]


def test_parse_cells_accepts_explicit_research_cells() -> None:
    assert sweep_orb_params._parse_cells("15:2.0:1.5:200") == [
        sweep_orb_params.SweepCell(15, 2.0, 1.5, 200),
    ]


def test_sweep_orb_run_one_returns_zero_result_when_positive_price_filter_empties_dataset(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeDataset:
        symbol = "MNQ1"

    class FakeLibrary:
        def get(self, *, symbol: str, timeframe: str) -> FakeDataset:
            return FakeDataset()

        def load_bars(self, dataset: FakeDataset, **kwargs: object) -> list[object]:
            calls.append(kwargs)
            return []

    monkeypatch.setattr(data_library, "default_library", lambda: FakeLibrary())

    result = sweep_orb_params.run_one(
        sweep_orb_params.SweepCell(
            range_minutes=15,
            rr_target=2.0,
            atr_stop_mult=1.5,
            ema_bias_period=200,
        ),
        symbol="MNQ1",
        timeframe="5m",
        window_days=60,
        step_days=30,
        max_bars=100,
        bar_slice="tail",
    )

    assert calls == [
        {
            "limit": 100,
            "limit_from": "tail",
            "require_positive_prices": True,
        }
    ]
    assert result.n_windows == 0
    assert result.pass_gate is False


def test_sweep_orb_run_one_returns_zero_result_when_dataset_is_missing(monkeypatch) -> None:
    class FakeLibrary:
        def get(self, *, symbol: str, timeframe: str) -> None:
            return None

    monkeypatch.setattr(data_library, "default_library", lambda: FakeLibrary())

    result = sweep_orb_params.run_one(
        sweep_orb_params.SweepCell(
            range_minutes=15,
            rr_target=2.0,
            atr_stop_mult=1.5,
            ema_bias_period=200,
        ),
        symbol="MNQ1",
        timeframe="5m",
        window_days=60,
        step_days=30,
    )

    assert result.n_windows == 0
    assert result.pass_gate is False
