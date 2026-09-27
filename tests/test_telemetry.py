from engine.telemetry import TelemetryAggregator, orn_probe


def test_orn_probe_collects_calls_and_cold_warm_counts() -> None:
    agg = TelemetryAggregator()

    @orn_probe(category="exec", critical=True, aggregator=agg, probe_name="unit.add")
    def add(x: int, y: int) -> int:
        return x + y

    for i in range(5):
        assert add(i, i) == 2 * i

    snap = agg.snapshot()["unit.add"]
    assert snap["calls"] == 5
    assert snap["cold_calls"] == 1
    assert snap["warm_calls"] == 4
    assert snap["failures"] == 0


def test_orn_probe_tracks_failures() -> None:
    agg = TelemetryAggregator()

    @orn_probe(category="stability", aggregator=agg, probe_name="unit.fail")
    def explode() -> None:
        raise ValueError("boom")

    try:
        explode()
    except ValueError:
        pass

    snap = agg.snapshot()["unit.fail"]
    assert snap["calls"] == 1
    assert snap["failures"] == 1
