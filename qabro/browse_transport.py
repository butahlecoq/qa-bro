"""A local stdio MCP connection to browse."""

import json
import os
import selectors
import subprocess
from time import monotonic

from qabro.budget import Budget


class BrowseTransport:
    def __init__(self, executable: str = "browse", *, timeout: float = 15, budget: Budget | None = None):
        self.executable = executable
        self.timeout = timeout
        self.budget = budget
        self._buffer = bytearray()
        self._request_id = 0

    def __enter__(self):
        self._process = subprocess.Popen(
            [self.executable, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            env={**os.environ, "OPENCODE_BROWSER_TOOLS": "plain"},
        )
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._process.stdout, selectors.EVENT_READ)
        try:
            self.server_info = self.request("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "qa-bro", "version": "0.1"},
            })["serverInfo"]
            self._send({"method": "notifications/initialized"})
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        self._selector.close()
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        finally:
            self._process.stdin.close()
            self._process.stdout.close()

    def _send(self, message: dict) -> None:
        line = json.dumps({"jsonrpc": "2.0", **message}, allow_nan=False)
        self._process.stdin.write((line + "\n").encode())
        self._process.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        timeout = self.timeout
        if self.budget is not None:
            timeout = min(timeout, self.budget.remaining_seconds())
        deadline = monotonic() + timeout
        self._request_id += 1
        self._send({"id": self._request_id, "method": method, "params": params})
        while True:
            end = self._buffer.find(b"\n")
            if end >= 0:
                reply = json.loads(self._buffer[:end])
                del self._buffer[:end + 1]
                if reply.get("id") != self._request_id:
                    continue
                if "error" in reply:
                    return {"isError": True, "rpcError": reply["error"]}
                return reply["result"]
            remaining = deadline - monotonic()
            if remaining <= 0 or not self._selector.select(remaining):
                raise TimeoutError(f"browse MCP timed out during {method}")
            chunk = os.read(self._process.stdout.fileno(), 65536)
            if not chunk:
                raise ConnectionError("browse MCP closed its output")
            self._buffer.extend(chunk)

    def __call__(self, tab: str, tool: str, arguments: dict) -> object:
        return self.request("tools/call", {
            "name": tool, "arguments": {**arguments, "tab": tab},
        })
