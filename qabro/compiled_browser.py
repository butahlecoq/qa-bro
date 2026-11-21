"""Build bounded browse execute programs for paired backend trials."""

import json
from dataclasses import dataclass

from qabro.runner import Action


# These plain tools share their implementation with the corresponding browse globals.
_TOOLS = frozenset({"navigate", "click", "fill", "select", "snapshot"})


@dataclass(frozen=True)
class Operation:
    step: str
    action: Action
    expected_text: str | None = None


def compile_operations(operations: tuple[Operation, ...], *, timeout_ms: int) -> dict:
    """Compile resolved operations with optional explicit snapshot checks."""
    if not operations or type(timeout_ms) is not int or timeout_ms <= 0:
        raise ValueError("A compiled trial requires operations and a positive timeout")
    plan = []
    for operation in operations:
        action = operation.action
        if action.tool not in _TOOLS or "tab" in action.arguments:
            raise ValueError("The operation is unsupported by the compiled trial")
        if operation.expected_text is not None and (
            action.tool != "snapshot" or not operation.expected_text
        ):
            raise ValueError("An explicit text check requires a snapshot and nonempty text")
        plan.append({
            "step": operation.step, "tool": action.tool, "args": action.arguments,
            "expected": operation.expected_text,
        })
    encoded = json.dumps(plan, allow_nan=False)
    code = f"""const plan = JSON.parse({json.dumps(encoded)});
const events = [];
for (const [index, {{step, tool, args, expected}}] of plan.entries()) {{
  console.log("qa-bro: " + index + " started");
  let evidence;
  try {{
    evidence = await browse[tool](args);
  }} catch (error) {{
    events.push({{step, tool, outcome: "unknown", evidence: String(error)}});
    console.log("qa-bro: " + index + " unknown");
    break;
  }}
  let outcome = "returned";
  if (expected !== null) {{
    outcome = typeof evidence !== "string" ? "unknown"
      : evidence.includes(expected) ? "matched" : "mismatched";
  }}
  events.push({{step, tool, outcome, evidence: evidence ?? null}});
  console.log("qa-bro: " + index + " " + outcome);
  if (outcome === "unknown" || outcome === "mismatched") break;
}}
return {{events}};"""
    return {"code": code, "timeoutMs": timeout_ms}
