"""Typed predicates over values returned by registered recipe probes."""

from dataclasses import dataclass

from qabro.evidence import Evidence


@dataclass(frozen=True)
class ProbeValue:
    observed_ns: int
    artifact_id: str
    value: object


@dataclass(frozen=True)
class RecipeCheck:
    probe: str
    operator: str
    expected: str | int | bool | None = None
    binding: str | None = None

    def __post_init__(self):
        if not isinstance(self.probe, str) or not self.probe.strip():
            raise ValueError("A recipe check requires a registered probe name")
        if self.operator not in {"equals", "contains", "visible", "state", "count"}:
            raise ValueError("Unsupported recipe check operator")
        if self.binding is not None and (not self.binding or self.expected is not None):
            raise ValueError("A recipe check uses either a binding or a literal")
        if self.operator == "visible" and (self.binding is not None or type(self.expected) is not bool):
            raise ValueError("Visibility requires a boolean")
        if self.operator == "count" and (
            self.binding is not None or type(self.expected) is not int or self.expected < 0
        ):
            raise ValueError("Count requires a nonnegative integer")
        if self.binding is None and type(self.expected) not in {str, int, bool}:
            raise ValueError("A recipe check requires a scalar expected value")

    def evaluate(self, observation: ProbeValue, *, bound_value: str | None = None) -> Evidence:
        actual = observation.value
        expected = self.expected if self.binding is None else bound_value
        matches = None
        if self.operator == "count" and isinstance(actual, (tuple, list)):
            matches = len(actual) == expected
        elif self.operator == "contains" and isinstance(actual, (tuple, list)) and expected is not None:
            matches = any(type(item) is type(expected) and item == expected for item in actual)
        elif self.operator in {"equals", "visible", "state"} and expected is not None and type(actual) is type(expected):
            matches = actual == expected
        return Evidence(observation.observed_ns, observation.artifact_id, matches)


@dataclass(frozen=True)
class RepeatCheck:
    check: RecipeCheck
    max_samples: int
    max_wait_ns: int

    def __post_init__(self):
        if type(self.max_samples) is not int or not 1 <= self.max_samples <= 20:
            raise ValueError("A repeated check requires between one and twenty samples")
        if type(self.max_wait_ns) is not int or self.max_wait_ns <= 0:
            raise ValueError("A repeated check requires a positive time limit")
