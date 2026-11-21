"""Expose a run's scoped skill summaries and hints over local MCP stdio."""

import argparse
import json
import sys
from pathlib import Path

from qabro.catalog import Catalog, Scope
from qabro.skills import RunSkills


TOOLS = [
    {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": {key: {"type": "string"} for key in keys},
        "required": keys, "additionalProperties": False,
    }}
    for name, description, keys in (
        ("find_skills", "Find summaries of applicable UI skills.", ["query"]),
        ("read_hint", "Read a selected skill offered by the search.", ["id", "revision"]),
    )
]


def serve(skills: RunSkills) -> None:
    offered = {}
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _rpc_error(None, -32700, "Parse error")
            continue
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            _rpc_error(None, -32600, "Invalid request")
            continue
        if "id" not in request:
            continue
        method = request.get("method")
        response = {"jsonrpc": "2.0", "id": request["id"]}
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "qa-bro-skills", "version": "0.1"},
            }
        elif method == "ping":
            response["result"] = {}
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                params = request["params"]
                arguments = params["arguments"]
                if not isinstance(arguments, dict):
                    raise ValueError("Expected an argument object")
                schema = next(tool["inputSchema"] for tool in TOOLS if tool["name"] == params["name"])
                if arguments.keys() != set(schema["required"]) or any(
                    not isinstance(value, str) for value in arguments.values()
                ):
                    raise ValueError("Arguments do not match the tool schema")
                if params["name"] == "find_skills":
                    refs = skills.find(arguments["query"])
                    offered.update(((ref.id, ref.revision), ref) for ref in refs)
                    content = json.dumps([vars(ref) for ref in refs])
                elif params["name"] == "read_hint":
                    ref = offered[arguments["id"], arguments["revision"]]
                    content = skills.catalog.load_hint(skills.run, ref)
                else:
                    raise ValueError("Unknown skill tool")
                response["result"] = {"content": [{"type": "text", "text": content}]}
            except (KeyError, StopIteration, TypeError, ValueError):
                response["result"] = {
                    "isError": True,
                    "content": [{"type": "text", "text": "Invalid or unavailable skill request."}],
                }
        else:
            response["error"] = {"code": -32601, "message": "Method not found"}
        print(json.dumps(response), flush=True)


def _rpc_error(request_id: object, code: int, message: str) -> None:
    print(json.dumps({
        "jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message},
    }), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("run")
    parser.add_argument("platform")
    parser.add_argument("component")
    parser.add_argument("context")
    parser.add_argument("role")
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()
    serve(RunSkills(
        Catalog(args.database), args.run, Scope(args.platform, args.component, args.context, args.role),
        frozenset(args.capability),
    ))
