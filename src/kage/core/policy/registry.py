"""Registry for policy rules and conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass, field

from .context import PolicyContext
from .decision import PolicyDecision
from .rules import PolicyRule, decision_weight


@dataclass(slots=True)
class PolicyRegistry:
    """Stores and evaluates policy rules in priority order."""

    _rules: list[PolicyRule] = field(default_factory=list)
    _overrides: dict[str, PolicyDecision] = field(default_factory=dict)
    _disabled_groups: set[str] = field(default_factory=set)

    def register(self, rule: PolicyRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda item: (item.priority, item.rule_id))

    def register_many(self, rules: list[PolicyRule]) -> None:
        for rule in rules:
            self.register(rule)

    def set_override(self, rule_id: str, decision: PolicyDecision) -> None:
        self._overrides[rule_id] = decision

    def disable_group(self, group: str) -> None:
        self._disabled_groups.add(group)

    def enable_group(self, group: str) -> None:
        self._disabled_groups.discard(group)

    def list_rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        matched: list[tuple[PolicyRule, PolicyDecision]] = []
        for rule in self._rules:
            if rule.group in self._disabled_groups:
                continue
            if not rule.applies(context):
                continue
            decision = self._overrides.get(rule.rule_id, rule.evaluate(context))
            matched.append((rule, decision))

        if not matched:
            return PolicyDecision.allow(reason="No matching policy rule", rule_id="policy.default_allow")

        strictest_rule, strictest_decision = matched[0]
        for rule, decision in matched[1:]:
            current_weight = decision_weight(strictest_decision.decision)
            candidate_weight = decision_weight(decision.decision)
            if candidate_weight > current_weight:
                strictest_rule, strictest_decision = rule, decision
                continue
            if candidate_weight == current_weight and rule.priority < strictest_rule.priority:
                strictest_rule, strictest_decision = rule, decision
        return strictest_decision

