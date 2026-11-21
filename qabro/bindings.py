"""Scenario inputs resolved against the current attempt."""

from dataclasses import dataclass
from datetime import datetime
from random import Random
from string import ascii_letters


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
    def __init__(self, rules: dict[str, Rule], *, seed: int, base_time: datetime):
        if base_time.utcoffset() is None:
            raise ValueError("Attempt time must include a timezone")
        self._rules = dict(rules)
        self._values: dict[str, str | Option] = {}
        self._random = Random(seed)
        self.seed = seed
        self.base_time = base_time

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
        self._values[key] = value
        return value
