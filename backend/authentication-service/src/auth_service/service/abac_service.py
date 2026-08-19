"""Attribute-Based Access Control (ABAC).

Policies encode rules of the form:

    resource="patient.record", action="read",
    conditions={"department": {"==": "cardiology"}, "clearance": {"gte": 3}}

The engine matches subject attributes against the condition expressions and
applies the highest-priority matching policy (DENY overrides ALLOW by default,
matching zero-trust). ABAC runs in addition to RBAC, not instead of it.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.dto.schemas import AbacCheckRequest, AbacEffect
from auth_service.entity.models import AbacPolicy

_COMPARATORS: dict[str, object] = {
    "==": operator.eq,
    "!=": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda value, allowed: value in allowed,
    "not_in": lambda value, disallowed: value not in disallowed,
}


@dataclass
class Decision:
    effect: str  # allow | deny
    matched: list[AbacEffect]


class AbacService:
    """Evaluates ABAC decisions against stored policies."""

    def __init__(self):
        self._cache: dict[str, list[AbacPolicy]] = {}

    async def list_policies(self, session: AsyncSession) -> list[AbacPolicy]:
        result = await session.execute(
            select(AbacPolicy).where(AbacPolicy.deleted_at.is_(None)).order_by(AbacPolicy.priority.desc())
        )
        return list(result.scalars().all())

    async def create_policy(
        self,
        session: AsyncSession,
        code: str,
        resource: str,
        action: str,
        effect: str,
        conditions: dict,
        priority: int,
        description: str | None,
        enabled: bool = True,
    ) -> AbacPolicy:
        policy = AbacPolicy(
            code=code,
            resource=resource,
            action=action,
            effect=effect,
            conditions=conditions,
            priority=priority,
            description=description,
            enabled=enabled,
        )
        session.add(policy)
        await session.flush()
        return policy

    async def get_policy(self, session: AsyncSession, code: str) -> AbacPolicy | None:
        result = await session.execute(select(AbacPolicy).where(AbacPolicy.code == code))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------ evaluation

    @staticmethod
    def _match_conditions(conditions: dict | None, attributes: dict) -> bool:
        """Evaluate the conditions map against the subject attributes."""
        if not conditions:
            return True
        for key, expr in conditions.items():
            if not isinstance(expr, dict):
                continue
            actual = attributes.get(key)
            for op_symbol, expected in expr.items():
                comparator = _COMPARATORS.get(op_symbol)
                if comparator is None:
                    continue
                try:
                    if not comparator(actual, expected):
                        return False
                except (TypeError, ValueError):
                    return False
        return True

    async def evaluate(self, session: AsyncSession, request: AbacCheckRequest) -> Decision:
        policies = await self.list_policies(session)
        relevant = [
            p
            for p in policies
            if p.enabled and p.resource == request.resource and p.action == request.action
        ]
        # higher priority first (list_policies already sorted desc)
        for policy in relevant:
            if self._match_conditions(policy.conditions, request.attributes):
                effect = AbacEffect(policy_code=policy.code, effect=policy.effect)
                if policy.effect == "deny":
                    return Decision(effect="deny", matched=[effect])
                return Decision(effect="allow", matched=[effect])
        # default deny (zero-trust)
        return Decision(effect="deny", matched=[])