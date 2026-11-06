"""Generate local credentials once. Does not start Docker or enable live trading."""
import os
import secrets
from pathlib import Path


def bootstrap(root: Path):
    target = root / ".env"
    values = {name: secrets.token_hex(32) for name in (
        "POSTGRES_PASSWORD", "TINA_ENGINE_TOKEN", "TINA_READ_TOKEN", "TINA_ADMIN_TOKEN",
        "TINA_RESEARCH_TOKEN", "TINA_FREQTRADE_PASSWORD", "TINA_FREQTRADE_JWT", "TINA_FREQTRADE_WS")}
    values.update(TINA_AI_POLICY="shadow", TINA_LLM_PROVIDER="", TINA_QUICK_MODEL="", TINA_DEEP_MODEL="")
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(".env already exists; credentials were not overwritten") from None
    with os.fdopen(fd, "w") as handle:
        handle.write("# Local secrets. Never commit or share this file.\n")
        for name, value in values.items():
            handle.write(f"{name}={value}\n")
    research = root / ".env.research"
    if not research.exists():
        fd = os.open(research, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write("# Add only the selected LLM provider API key here. No exchange keys.\n")
    print("Created local credentials. Paper mode only. Next: docker compose up -d --build")


if __name__ == "__main__":
    bootstrap(Path(__file__).resolve().parents[1])
