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


def test_orn_probe_status_offline_json_strict(monkeypatch) -> None:
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status", "--json-output", "--strict"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "offline"


def test_orn_probe_script_main_json_offline(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe_cli, "query_server_status", lambda host, port: None)

    rc = probe_cli.main(["--json"])
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.out)
    assert payload["status"] == "offline"


def test_orn_probe_status_json_out_file(monkeypatch, tmp_path) -> None:
    payload = {"status": "online", "requests": 1, "errors": 0, "avg_elapsed_s": 0.1, "telemetry_hotspots": []}
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: payload)

    out_file = tmp_path / "probe_status.json"
    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status", "--json-output", "--out", str(out_file)])
    assert result.exit_code == 0
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["status"] == "online"


def test_orn_probe_script_main_json_out_file(monkeypatch, tmp_path) -> None:
    payload = {"status": "online", "requests": 9, "errors": 0, "avg_elapsed_s": 0.9, "telemetry_hotspots": []}
    monkeypatch.setattr(probe_cli, "query_server_status", lambda host, port: payload)

    out_file = tmp_path / "probe_script.json"
    rc = probe_cli.main(["--json", "--out", str(out_file)])
    assert rc == 0
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["requests"] == 9


def test_orn_probe_human_includes_ai_perf_block(monkeypatch) -> None:
    payload = {
        "status": "online",
        "requests": 2,
        "errors": 0,
        "avg_elapsed_s": 10.0,
        "boot_perf": {"vulcan_boot_ms": 40.0, "model_load_ms": 2200.0},
        "ai_perf": {
            "infer_calls": 2,
            "last_infer_s": 1.5,
            "last_tokens_per_s": 80.0,
            "avg_prompt_chars": 100.0,
            "avg_output_chars": 120.0,
        },
        "telemetry_hotspots": [],
    }
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: payload)

    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status"])
    assert result.exit_code == 0
    assert "IA perf" in result.output
    assert "last_tokens_per_s=80.0" in result.output


def test_orn_probe_human_includes_ai_phase_fields(monkeypatch) -> None:
    payload = {
        "status": "online",
        "requests": 2,
        "errors": 0,
        "avg_elapsed_s": 10.0,
        "boot_perf": {"vulcan_boot_ms": 40.0, "model_load_ms": 2200.0},
        "ai_perf": {
            "infer_calls": 2,
            "last_infer_s": 1.5,
            "last_tokens_per_s": 80.0,
            "total_tokens_per_s": 42.0,
            "avg_prompt_chars": 100.0,
            "avg_output_chars": 120.0,
            "last_lock_wait_ms": 1.2,
            "last_llm_call_ms": 1400.0,
            "last_non_llm_ms": 100.0,
            "last_llm_share_pct": 93.3,
        },
        "telemetry_hotspots": [],
    }
    monkeypatch.setattr(probe_cli, "query_server_status", lambda: payload)

    runner = CliRunner()
    result = runner.invoke(cli, ["probe", "status"])
    assert result.exit_code == 0
    assert "last_lock_wait" in result.output
    assert "last_llm_call" in result.output
    assert "last_llm_share" in result.output
