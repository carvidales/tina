"""Standalone GET-only bridge. Give OpenClaw only TINA_READ_TOKEN, never repository .env access."""
import argparse
import os
import urllib.request

PATHS = {"status": "/v1/status", "research": "/v1/research", "decisions": "/v1/decisions"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=PATHS)
    args = parser.parse_args()
    token = os.environ.get("TINA_READ_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("Set the read-only TINA_READ_TOKEN in the OpenClaw process environment")
    base = os.environ.get("TINA_CONTROL_URL", "http://127.0.0.1:8081")
    request = urllib.request.Request(base + PATHS[args.command], headers={"Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        print(response.read(262144).decode())


if __name__ == "__main__":
    main()
