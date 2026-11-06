"""Guard the supplied deployment: this release deliberately refuses live execution."""
import json
import os
import sys

ALLOWED_ENV = {"FREQTRADE__API_SERVER__USERNAME", "FREQTRADE__API_SERVER__PASSWORD",
               "FREQTRADE__API_SERVER__JWT_SECRET_KEY", "FREQTRADE__API_SERVER__WS_TOKEN"}
COMMANDS = {"trade", "download-data", "backtesting", "list-strategies", "lookahead-analysis", "recursive-analysis", "show-config"}


def build_command(args, config, environ):
    if (config.get("dry_run") is not True or config.get("trading_mode") != "spot"
            or config.get("exchange", {}).get("name") != "kraken"
            or config.get("strategy") != "TinaStrategy"
            or config.get("force_entry_enable") is not False
            or config.get("position_adjustment_enable") is not False):
        raise ValueError("Only the reviewed dry-run spot configuration is supported")
    if any(k.startswith("FREQTRADE__") and k not in ALLOWED_ENV for k in environ):
        raise ValueError("Unreviewed Freqtrade environment override")
    if config["exchange"].get("key") or config["exchange"].get("secret"):
        raise ValueError("Remove exchange credentials; paper mode needs no exchange key")
    command = args[0] if args else "trade"
    if command not in COMMANDS:
        raise ValueError("Unsupported command")
    if command == "trade" and len(args) > 1:
        raise ValueError("Additional trading CLI overrides are not permitted")
    blocked = ("--config", "-c", "--strategy", "-s", "--userdir", "--user-data-dir", "--strategy-path", "--db-url")
    if any(arg.split("=")[0] in blocked for arg in args[1:]):
        raise ValueError("Configuration overrides are not permitted")
    result = ["freqtrade", command, "--config", "/freqtrade/config.json"]
    if command == "trade":
        result += ["--dry-run", "--db-url", "sqlite:////freqtrade/user_data/tradesv3.dryrun.sqlite"]
    return result + args[1:]


if __name__ == "__main__":
    with open("/freqtrade/config.json", encoding="utf-8") as handle:
        configuration = json.load(handle)
    try:
        command = build_command(sys.argv[1:], configuration, os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    os.execvp(command[0], command)
