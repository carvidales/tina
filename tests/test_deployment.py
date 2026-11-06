import importlib.util
import json
from pathlib import Path
import pytest
import yaml
from tina.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_launcher_forces_paper():
    cfg = json.loads((ROOT / "config/freqtrade.json").read_text())
    assert "--dry-run" in load("engine_start").build_command(["trade"], cfg, {})
    cfg["dry_run"] = False
    with pytest.raises(ValueError):
        load("engine_start").build_command(["trade"], cfg, {})


@pytest.mark.parametrize("args,env", [(["trade", "--config", "live.json"], {}),
    (["trade"], {"FREQTRADE__DRY_RUN": "false"}), (["webserver"], {}),
    (["backtesting", "--config=other.json"], {})])
def test_launcher_overrides_denied(args, env):
    cfg = json.loads((ROOT / "config/freqtrade.json").read_text())
    with pytest.raises(ValueError):
        load("engine_start").build_command(args, cfg, env)


def test_secret_separation():
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    assert services["freqtrade"]["image"].endswith(":2026.10")
    assert "TINA_ADMIN_TOKEN" not in services["research"]["environment"]
    assert "TINA_ENGINE_TOKEN" not in services["research"]["environment"]
    assert "TINA_ADMIN_TOKEN" not in services["freqtrade"]["environment"]
    assert not services["postgres"].get("ports")
    for service in services.values():
        assert all(p.startswith("127.0.0.1:") for p in service.get("ports", []))
        assert "docker.sock" not in str(service.get("volumes", []))


def test_bootstrap(tmp_path):
    tool = load("bootstrap")
    tool.bootstrap(tmp_path)
    contents = (tmp_path / ".env").read_text()
    values = [line.split("=", 1)[1] for line in contents.splitlines() if "TOKEN=" in line]
    assert len(values) == len(set(values)) == 4
    assert all(len(v) == 64 for v in values)
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        tool.bootstrap(tmp_path)
    assert (tmp_path / ".env").read_text() == contents


def test_missing_process_secrets(monkeypatch):
    for name in ("ENGINE_TOKEN", "READ_TOKEN", "ADMIN_TOKEN", "RESEARCH_TOKEN"):
        monkeypatch.delenv("TINA_" + name, raising=False)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_reader_has_fixed_get_routes():
    assert load("openclaw_client").PATHS == {"status": "/v1/status", "research": "/v1/research", "decisions": "/v1/decisions"}
