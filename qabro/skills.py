"""Expose scoped skill lookup to the agent running a scenario."""

from collections.abc import Callable

from qabro.budget import Budget
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Step
from qabro.runner import Recipe


class RunSkills:
    def __init__(self, catalog: Catalog, run: str, scope: Scope, capabilities: frozenset[str]):
        self.catalog = catalog
        self.run = run
        self.scope = scope
        self.capabilities = capabilities
        catalog.pin(run)

    def find(self, query: str) -> tuple[SkillRef, ...]:
        return tuple(self.catalog.search(self.run, query, self.scope, self.capabilities))

    def _select(
        self, step: Step, choose: Callable[[Step, tuple[SkillRef, ...]], SkillRef | None],
    ) -> SkillRef | None:
        options = self.find(step.action)
        selected = choose(step, options) if options else None
        if selected is None:
            return None
        if selected not in options:
            raise ValueError("Agent selected a skill outside the offered scope")
        return selected

    def select_hint(
        self, step: Step, choose: Callable[[Step, tuple[SkillRef, ...]], SkillRef | None],
    ) -> str | None:
        selected = self._select(step, choose)
        return self.catalog.load_hint(self.run, selected) if selected else None

    def select_recipe(
        self, step: Step, choose: Callable[[Step, tuple[SkillRef, ...]], SkillRef | None],
    ) -> Recipe | None:
        selected = self._select(step, choose)
        return self.catalog.load_recipe(self.run, selected) if selected else None

    def select_with_model(
        self,
        step: Step,
        budget: Budget,
        choose: Callable[[Step, tuple[SkillRef, ...], float], SkillRef | None],
    ) -> Recipe | None:
        return self.select_recipe(
            step, lambda source, options: budget.call_model(
                lambda remaining: choose(source, options, remaining)
            ),
        )
