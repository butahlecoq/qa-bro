"""Inspect the tool schema exposed by the installed browse MCP executable."""

import argparse
import json
from hashlib import sha256

from qabro.browse_transport import BrowseTransport


def inspect(executable: str) -> dict:
    with BrowseTransport(executable, timeout=10) as browse:
        server = browse.server_info
        tool_list = browse.request("tools/list", {})
    try:
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
