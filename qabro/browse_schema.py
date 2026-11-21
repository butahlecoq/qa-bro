"""Inspect the tool schema exposed by the installed browse MCP executable."""

import argparse
import json
import os
import subprocess
from hashlib import sha256


def inspect(executable: str) -> dict:
    messages = [
        {"id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "qa-bro", "version": "0.1"},
        }},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list", "params": {}},
    ]
    request = "".join(json.dumps({"jsonrpc": "2.0", **message}) + "\n" for message in messages)
    output = subprocess.run(
        [executable, "mcp"], input=request, text=True, capture_output=True,
        check=True, timeout=10, env={**os.environ, "OPENCODE_BROWSER_TOOLS": "plain"},
    ).stdout
    replies = {}
    for line in output.splitlines():
        reply = json.loads(line)
        if "id" in reply:
            replies[reply["id"]] = reply
    try:
        server = replies[1]["result"]["serverInfo"]
        tool_list = replies[2]["result"]
        tools = sorted(tool_list["tools"], key=lambda tool: tool["name"])
    except (KeyError, TypeError) as error:
        raise ValueError("Browse did not return a complete MCP tool schema") from error
    if not tools or tool_list.get("nextCursor"):
        raise ValueError("Browse did not return the full tool list")
    fingerprint = sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest()
    return {"server": server, "schema_sha256": fingerprint, "tools": tools}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", default="browse")
    args = parser.parse_args()
    print(json.dumps(inspect(args.executable), indent=2))
