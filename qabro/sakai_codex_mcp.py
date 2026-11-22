"""Expose the restricted Sakai worker bridge as one stdio MCP tool."""

import json
import os
import sys
from urllib.request import Request, urlopen


def main():
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion": request["params"]["protocolVersion"],
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "sakai", "version": "1"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [{
                "name": "sakai", "description": "Read the skill, inspect visible controls, or act with a selector.",
                "inputSchema": {"type": "object", "properties": {
                    "action": {"enum": ["inspect", "click", "fill", "fill_many", "read_skill"], "type": "string"},
                    "selector": {"type": "string"},
                    "selectors": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                }, "required": ["action"], "additionalProperties": False},
            }]}
        elif method == "tools/call" and request["params"]["name"] == "sakai":
            call = Request(os.environ["QABRO_SAKAI_BRIDGE"],
                           data=json.dumps(request["params"].get("arguments", {})).encode(),
                           headers={"Authorization": "Bearer " + os.environ["QABRO_SAKAI_TOKEN"]})
            with urlopen(call, timeout=18) as reply:
                result = {"content": [{"type": "text", "text": reply.read().decode()}]}
        else:
            response["error"] = {"code": -32601, "message": "Method not found"}
            print(json.dumps(response), flush=True)
            continue
        response["result"] = result
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
