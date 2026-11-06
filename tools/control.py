"""Human operator CLI; never give repository .env access to the general-purpose agent."""
import argparse
import json
import os
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "halt", "resume"])
    parser.add_argument("--reason", default="Manual operator entry halt")
    args = parser.parse_args()
    env = {}
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key] = value
    token = os.environ.get("TINA_ADMIN_TOKEN") or env.get("TINA_ADMIN_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("Missing operator token")
    base = os.environ.get("TINA_CONTROL_URL", "http://127.0.0.1:8081")
    payload = None if args.command == "status" else json.dumps({"reason": args.reason} if args.command == "halt" else {}).encode()
    request = urllib.request.Request(base + "/v1/" + args.command, data=payload,
        method="GET" if payload is None else "POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()
