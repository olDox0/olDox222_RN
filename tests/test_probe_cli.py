import json

from click.testing import CliRunner

from engine.cli import cli
from engine.telemetry import cli as probe_cli


def test_orn_probe_status_json(monkeypatch) -> None:
    payload = {"status": "online", "requests": 3, "errors": 0, "avg_elapsed_s": 0.2, "telemetry_hotspots": []}
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: payload)

    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status", "--json-output"])
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert out["status"] == "online"


def test_orn_probe_status_offline(monkeypatch) -> None:
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status"])
    assert result.exit_code == 0
    assert "Servidor offline" in result.output


def test_orn_probe_script_main_json(monkeypatch, capsys) -> None:
    payload = {
        "status": "online",
        "requests": 7,
        "errors": 1,
        "avg_elapsed_s": 0.5,
        "telemetry_hotspots": [{"name": "server.infer", "calls": 7, "avg_ms": 9.2, "p95_ms": 12.0}],
    }
    monkeypatch.setattr(probe_cli, "query_server_status", lambda host, port: payload)

    rc = probe_cli.main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    parsed = json.loads(captured.out)
    assert parsed["telemetry_hotspots"][0]["name"] == "server.infer"
