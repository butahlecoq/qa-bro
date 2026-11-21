"""Summarize one opencode run --format json stream."""

import json
import sys
from collections.abc import Iterable


def summarize(lines: Iterable[str]) -> dict:
    events = [json.loads(line) for line in lines if line.strip()]
    sessions = {event["sessionID"] for event in events}
    if len(sessions) != 1:
        raise ValueError("Expected exactly one opencode session")
    starts = [event for event in events if event["type"] == "step_start"]
    finishes = [event for event in events if event["type"] == "step_finish"]
    usage = [event["part"]["tokens"] for event in finishes]
    tools = [event["part"]["tool"] for event in events if event["type"] == "tool_use"]
    return {
        "model_steps_started": len(starts),
        "model_steps_completed": len(finishes),
        "input_tokens": sum(item["input"] for item in usage),
        "output_tokens": sum(item["output"] for item in usage),
        "reasoning_tokens": sum(item["reasoning"] for item in usage),
        "cache_read_tokens": sum(item["cache"]["read"] for item in usage),
        "cache_write_tokens": sum(item["cache"]["write"] for item in usage),
        "tool_dispatches": len(tools),
        "tools": sorted(set(tools)),
        "errors": sum(event["type"] == "error" for event in events),
        "event_span_ms": events[-1]["timestamp"] - events[0]["timestamp"],
    }


if __name__ == "__main__":
    print(json.dumps(summarize(sys.stdin), indent=2))
