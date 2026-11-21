"""Scenario inputs resolved against the current attempt."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from random import Random
from string import ascii_letters

from qabro.journal import Journal


@dataclass(frozen=True)
class Option:
    id: str
    label: str


@dataclass(frozen=True)
class Options:
    items: tuple[Option, ...]
    complete: bool


@dataclass(frozen=True)
class Literal:
    value: str


@dataclass(frozen=True)
class Generated:
    length: int
    alphabet: str = ascii_letters

    def __post_init__(self):
        if self.length < 0 or not self.alphabet:
            raise ValueError("Invalid generated input constraints")


@dataclass(frozen=True)
class CurrentTime:
    format: str


@dataclass(frozen=True)
class Select:
    last: bool = False


Rule = Literal | Generated | CurrentTime | Select


class UnresolvedBinding(Exception):
    """Available evidence cannot establish the requested input."""


class AttemptBindings:
    def __init__(
        self, rules: dict[str, Rule], *, seed: int, base_time: datetime,
        journal: Journal | None = None, attempt: str | None = None,
    ):
        if base_time.utcoffset() is None:
            raise ValueError("Attempt time must include a timezone")
        self._rules = dict(rules)
        self._values: dict[str, str | Option] = {}
        self._random = Random(seed)
        self.seed = seed
        self.base_time = base_time

        if (journal is None) != (attempt is None):
            raise ValueError("Persistent bindings require a journal and attempt ID")
        self._journal = journal
        self._attempt = attempt
        if journal is not None and attempt is not None:
            journal.append(attempt, "bindings:setup", "binding_setup", {
                "seed": seed, "base_time": base_time.isoformat(), "revision": self.revision,
            })
            for _, _, kind, payload in journal.events(attempt):
                if kind != "binding_used":
                    continue
                key = payload["key"]
                rule = self._rules[key]
                if isinstance(rule, Generated):
                    expected = "".join(self._random.choices(rule.alphabet, k=rule.length))
                    if expected != payload["value"]:
                        raise ValueError(f"Generated rule changed for {key!r}")
                    self._values[key] = expected
                elif isinstance(rule, Select):
                    self._values[key] = Option(payload["id"], payload["label"])
                else:
                    raise ValueError(f"Binding rule changed for {key!r}")

    @property
    def revision(self) -> str:
        rules = {key: (type(rule).__name__, asdict(rule)) for key, rule in self._rules.items()}
        data = {"rules": rules, "seed": self.seed, "base_time": self.base_time.isoformat()}
        return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def use(self, key: str, *, options: Options | None = None) -> str | Option:
        """Resolve on first use and keep the selected identity for this attempt."""
        rule = self._rules[key]
        if key in self._values:
            value = self._values[key]
            if isinstance(value, Option) and options is not None and options.complete:
                if not any(item.id == value.id for item in options.items):
                    raise UnresolvedBinding(f"Selected option {value.id!r} disappeared")
            return value

        match rule:
            case Literal(value):
                pass
            case Generated(length, alphabet):
                value = "".join(self._random.choices(alphabet, k=length))
            case CurrentTime(format):
                value = self.base_time.strftime(format)
            case Select(last):
                if options is None or not options.items or not options.complete:
                    raise UnresolvedBinding(f"Cannot resolve ordered options for {key!r}")
                value = options.items[-1 if last else 0]
        if self._journal is not None and self._attempt is not None:
            payload = None
            if isinstance(rule, Generated):
                payload = {"key": key, "value": value}
            elif isinstance(value, Option):
                payload = {"key": key, "id": value.id, "label": value.label}
            if payload is not None:
                self._journal.append(self._attempt, f"binding:{key}:used", "binding_used", payload)
        self._values[key] = value
        return value
