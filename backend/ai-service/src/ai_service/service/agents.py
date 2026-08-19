"""Specialized AI Agents runtime (SPECIALIZED_AI_AGENTS_ARCHITECTURE.md).

Implements:
- The 10 agent definitions (seeded into ``agent_definitions``).
- A shared tool registry with permission levels + approval gates.
- AgentRuntime: deterministic, bounded execution of an agent against a goal
  (grounding via knowledge RAG, predictions, memory) writing AgentRun/AgentAction
  rows, pausing on approval-gated actions (status AWAITING_APPROVAL).
- ``build_agent_event_handlers`` to bridge the ehos-common EventProcessor so
  domain events (patient registered, dispensed, emergency…) trigger agents.

Execution is deliberately deterministic so tests and operators can reason about
it; a real LLM plumb can later replace role prompts without changing the
runtime contract.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.configuration import AiSettings
from ai_service.entity import models as ent
from ai_service.service import engines as eng
from ai_service.service.knowledge_client import KnowledgeClient

logger = logging.getLogger("ai_service.agents")

AGENT_KEYS = (
    "clinical",
    "nursing",
    "pharmacy",
    "laboratory",
    "radiology",
    "inventory",
    "finance",
    "hr",
    "executive",
    "compliance",
)

# eventType -> agent key that reacts to it (SPECIALIZED_AI_AGENTS_ARCHITECTURE.md §events)
EVENT_TO_AGENT: dict[str, str] = {
    "PatientRegistered": "clinical",
    "AppointmentCreated": "clinical",
    "LabOrdered": "laboratory",
    "MedicationDispensed": "pharmacy",
    "EmergencyTriggered": "clinical",
    "InventoryUpdated": "inventory",
    "BillGenerated": "finance",
    "PayrollCompleted": "hr",
}

AGENT_SEEDS: list[dict[str, Any]] = [
    {
        "key": "clinical",
        "name": "Clinical Practice Agent",
        "description": "Grounds clinical queries in approved local guidelines and forecasts",
        "capabilities": {"domains": ["ehr", "guidelines", "lab", "pharmacy", "emergency"]},
        "approval_policy": {"default_level": 2, "require_for": {"generate_draft": 3}},
    },
    {
        "key": "nursing",
        "name": "Nursing Workflow Agent",
        "description": "Nursing tasks, patient education drafts, shift handover summaries",
        "capabilities": {"domains": ["nursing", "patient_education", "handover"]},
        "approval_policy": {"default_level": 2, "require_for": {"generate_draft": 2}},
    },
    {
        "key": "pharmacy",
        "name": "Pharmacy Agent",
        "description": "Medication dispensing signals, formulary lookups, interaction flags",
        "capabilities": {"domains": ["pharmacy", "formulary", "medication"]},
        "approval_policy": {"default_level": 3, "require_for": {"generate_draft": 3}},
    },
    {
        "key": "laboratory",
        "name": "Laboratory Agent",
        "description": "Lab order signals, turnaround monitoring, result interpretation support",
        "capabilities": {"domains": ["lab", "panels"]},
        "approval_policy": {"default_level": 2, "require_for": {"generate_draft": 3}},
    },
    {
        "key": "radiology",
        "name": "Radiology Agent",
        "description": "Imaging order support, protocol lookups, report draft assistance",
        "capabilities": {"domains": ["radiology", "imaging"]},
        "approval_policy": {"default_level": 3, "require_for": {"generate_draft": 4}},
    },
    {
        "key": "inventory",
        "name": "Inventory Agent",
        "description": "Stock signals, shortage forecasting, reorder recommendations",
        "capabilities": {"domains": ["inventory", "supply", "forecast"]},
        "approval_policy": {"default_level": 2, "require_for": {"generate_draft": 3}},
    },
    {
        "key": "finance",
        "name": "Finance Agent",
        "description": "Billing, revenue forecasts, payment reconciliation support",
        "capabilities": {"domains": ["billing", "finance", "forecast"]},
        "approval_policy": {"default_level": 4, "require_for": {"generate_draft": 3}},
    },
    {
        "key": "hr",
        "name": "HR Agent",
        "description": "Payroll, staffing forecasts, shift planning support",
        "capabilities": {"domains": ["payroll", "hr", "forecast"]},
        "approval_policy": {"default_level": 4, "require_for": {"generate_draft": 4}},
    },
    {
        "key": "executive",
        "name": "Executive Insights Agent",
        "description": "Cross-domain dashboards: capacity, revenue, demand",
        "capabilities": {"domains": ["analytics", "forecast", "executive"]},
        "approval_policy": {"default_level": 2, "require_for": {"generate_draft": 2}},
    },
    {
        "key": "compliance",
        "name": "Compliance Agent",
        "description": "Tracks regulated actions, approval chains, audit readiness",
        "capabilities": {"domains": ["audit", "compliance", "approvals"]},
        "approval_policy": {"default_level": 4, "require_for": {"generate_draft": 3}},
    },
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    level: int  # 1 read-only public, 2 read internal, 3 action, 4 high-impact action
    read_only: bool
    fn: Callable[..., Coroutine[Any, Any, dict]]


def build_toolset(runtime: AgentRuntime) -> dict[str, ToolSpec]:
    return {
        "knowledge_search": ToolSpec(
            "knowledge_search", "Search approved local knowledge (RAG)", 1, True, runtime.tool_knowledge_search
        ),
        "predict": ToolSpec(
            "predict", "Latest approved forecast for an entity", 1, True, runtime.tool_predict
        ),
        "list_agent_runs": ToolSpec(
            "list_agent_runs", "Recent runs of an agent", 1, True, runtime.tool_list_runs
        ),
        "list_pending_actions": ToolSpec(
            "list_pending_actions", "Actions awaiting human approval", 2, True, runtime.tool_pending_actions
        ),
        "get_memory": ToolSpec("get_memory", "Read long-term agent memory", 1, True, runtime.tool_get_memory),
        "store_memory": ToolSpec(
            "store_memory", "Persist a workflow/decision memory", 2, False, runtime.tool_store_memory
        ),
        "generate_draft": ToolSpec(
            "generate_draft", "Produce a draft summary/letter for review", 3, False, runtime.tool_generate_draft
        ),
    }


class AgentRuntime:
    """Owns agent definitions, tools, and run lifecycles."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.inference = eng.InferenceEngine(settings)
        self.rag = KnowledgeClient(settings)
        self.tools = build_toolset(self)

    # --- definitions ---------------------------------------------------------

    async def ensure_seeds(self, session: AsyncSession) -> int:
        """Insert the 10 agent definitions if missing; returns created count."""
        inserted = 0
        for seed in AGENT_SEEDS:
            exists = (
                await session.execute(select(ent.AgentDefinition).where(ent.AgentDefinition.key == seed["key"]))
            ).scalar_one_or_none()
            if exists is not None:
                continue
            session.add(
                ent.AgentDefinition(
                    key=seed["key"],
                    name=seed["name"],
                    description=seed["description"],
                    capabilities=seed.get("capabilities"),
                    allowed_tools={"allowed": ["*"]},
                    approval_policy=seed.get("approval_policy", {"default_level": 2}),
                    is_active=True,
                )
            )
            inserted += 1
        if inserted:
            await session.flush()
        return inserted

    async def list_definitions(self, session: AsyncSession) -> list[ent.AgentDefinition]:
        await self.ensure_seeds(session)
        return list(
            (
                await session.execute(select(ent.AgentDefinition).order_by(ent.AgentDefinition.created_at))
            ).scalars().all()
        )

    async def get_definition(self, session: AsyncSession, key: str) -> ent.AgentDefinition:
        await self.ensure_seeds(session)
        row = (
            await session.execute(
                select(ent.AgentDefinition).where(
                    ent.AgentDefinition.key == key,
                    ent.AgentDefinition.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise eng.AiError("AGENT_NOT_FOUND", f"agent '{key}' not found", 404)
        return row

    # --- runs ----------------------------------------------------------------

    async def run_agent(
        self,
        session: AsyncSession,
        key: str,
        goal: str,
        user_id: uuid.UUID,
        context: dict | None = None,
    ) -> ent.AgentRun:
        definition = await self.get_definition(session, key)
        await self.ensure_seeds(session)
        run = ent.AgentRun(
            agent_id=definition.id,
            run_token=str(uuid.uuid4()),
            user_id=user_id,
            goal=goal,
            status="RUNNING",
            created_by=user_id,
        )
        session.add(run)
        await session.flush()
        await self._execute(session, run, definition, goal, context or {})
        await session.flush()
        return run

    async def _execute(
        self,
        session: AsyncSession,
        run: ent.AgentRun,
        definition: ent.AgentDefinition,
        goal: str,
        context: dict,
    ) -> None:
        steps = plan_workflow(goal, context)
        allowed = self._allowed_set(definition)
        executed = 0
        for tool_name, kwargs in steps:
            spec = self.tools.get(tool_name)
            if spec is None or (allowed != ["*"] and tool_name not in allowed):
                session.add(
                    self._action(
                        run.id, "tool", tool_name, kwargs, {"error": f"tool '{tool_name}' not allowed"}, "BLOCKED"
                    )
                )
                run.status = "BLOCKED"
                run.result_ref = "Blocked: requested tool is not permitted for this agent"
                run.finished_at = datetime.now(UTC)
                return

            output = await spec.fn(session, definition=definition, run_id=run.id, **kwargs)
            needs_approval = self._needs_approval(definition, tool_name, spec.level)
            status = "PENDING" if needs_approval else "NO_APPROVAL_REQUIRED"
            session.add(self._action(run.id, "tool", tool_name, kwargs, output, status, needs_approval))
            executed = executed + 1

            if needs_approval:
                run.status = "AWAITING_APPROVAL"
                run.result_ref = f"Paused awaiting approval after '{tool_name}'"
                return

        run.status = "COMPLETED"
        run.result_ref = _summarize(output=output, executed=executed)
        run.finished_at = datetime.now(UTC)

    def _allowed_set(self, definition: ent.AgentDefinition) -> list[str]:
        allowed = (definition.allowed_tools or {}).get("allowed") or ["*"]
        return list(allowed)

    def _needs_approval(self, definition: ent.AgentDefinition, tool_name: str, level: int) -> bool:
        policy = definition.approval_policy or {}
        threshold = policy.get("require_for", {}).get(tool_name, policy.get("default_level", 3))
        return level >= threshold

    @staticmethod
    def _action(
        run_id: uuid.UUID,
        action_type: str,
        tool: str,
        input_: dict,
        output: dict,
        approval_status: str,
        requires_approval: bool = False,
    ) -> ent.AgentAction:
        return ent.AgentAction(
            run_id=run_id,
            action_type=action_type,
            tool=tool,
            input=input_,
            output=output,
            requires_approval=requires_approval,
            approval_status=approval_status,
        )

    # --- read paths ----------------------------------------------------------

    async def list_runs(
        self, session: AsyncSession, agent_key: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[ent.AgentRun], int]:
        stmt = select(ent.AgentRun).where(ent.AgentRun.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        if agent_key:
            agent = (
                await session.execute(select(ent.AgentDefinition).where(ent.AgentDefinition.key == agent_key))
            ).scalar_one_or_none()
            if agent is not None:
                stmt = stmt.where(ent.AgentRun.agent_id == agent.id)
                count_stmt = select(func.count()).select_from(stmt.subquery())
        if status:
            valid = ("RUNNING", "AWAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED")
            if status not in valid:
                raise eng.AiError("INVALID_STATUS", f"status must be one of {', '.join(valid)}", 422)
            stmt = stmt.where(ent.AgentRun.status == status)
            count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()
        rows = (
            await session.execute(stmt.order_by(ent.AgentRun.created_at.desc()).limit(limit).offset(offset))
        ).scalars().all()
        return list(rows), total

    async def get_run(self, session: AsyncSession, run_id: uuid.UUID) -> ent.AgentRun:
        row = (
            await session.execute(
                select(ent.AgentRun).where(ent.AgentRun.id == run_id, ent.AgentRun.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if row is None:
            raise eng.AiError("NOT_FOUND", "agent run not found", 404)
        return row

    async def list_actions(self, session: AsyncSession, run_id: uuid.UUID) -> list[ent.AgentAction]:
        return list(
            (
                await session.execute(
                    select(ent.AgentAction).where(ent.AgentAction.run_id == run_id).order_by(ent.AgentAction.created_at)
                )
            ).scalars().all()
        )

    async def decide_action(
        self, session: AsyncSession, action_id: uuid.UUID, approver_id: str, approved: bool, comments: str | None = None
    ) -> ent.AgentRun:
        action = (
            await session.execute(select(ent.AgentAction).where(ent.AgentAction.id == action_id))
        ).scalar_one_or_none()
        if action is None:
            raise eng.AiError("NOT_FOUND", "agent action not found", 404)
        if action.approval_status != "PENDING":
            raise eng.AiError("ALREADY_DECIDED", "action already decided", 409)
        action.approval_status = "APPROVED" if approved else "REJECTED"
        action.updated_by = uuid.UUID(approver_id)
        run = await self.get_run(session, action.run_id)
        if run.status != "AWAITING_APPROVAL":
            return run
        if approved:
            run.status = "COMPLETED"
            run.result_ref = f"Approved by {approver_id}" + (f" — {comments}" if comments else "")
        else:
            run.status = "CANCELLED"
            run.result_ref = f"Rejected by {approver_id}" + (f" — {comments}" if comments else "")
        run.finished_at = datetime.now(UTC)
        run.updated_by = uuid.UUID(approver_id)
        await session.flush()
        return run

    # --- tools ---------------------------------------------------------------

    async def tool_knowledge_search(self, session: AsyncSession, **kwargs: Any) -> dict:
        query = str(kwargs.get("query", "") or "")
        top_k = int(kwargs.get("top_k") or 3)
        sources = await self.rag.search(query, top_k=top_k)
        return {
            "query": query,
            "sources": [s.model_dump() for s in sources],
        }

    async def tool_predict(self, session: AsyncSession, **kwargs: Any) -> dict:
        entity_type = kwargs.get("entity_type")
        predicate = [ent.Prediction.status == "VALID"]
        if entity_type:
            predicate.append(ent.Prediction.entity_type == entity_type)
        row = (
            await session.execute(
                select(ent.Prediction).where(*predicate).order_by(ent.Prediction.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return {"found": False, "prediction_key": None}
        return {
            "found": True,
            "prediction_key": row.prediction_key,
            "entity_type": row.entity_type,
            "horizon": row.horizon,
            "forecast": row.forecast,
            "confidence": float(row.confidence) if row.confidence is not None else None,
        }

    async def tool_list_runs(self, session: AsyncSession, **kwargs: Any) -> dict:
        limit = int(kwargs.get("limit") or 5)
        rows, _total = await self.list_runs(session, None, None, limit, 0)
        return {"runs": [{"id": str(r.id), "status": r.status, "goal": r.goal[:120]} for r in rows]}

    async def tool_pending_actions(self, session: AsyncSession, **kwargs: Any) -> dict:
        rows = (
            await session.execute(
                select(ent.AgentAction)
                .where(ent.AgentAction.approval_status == "PENDING")
                .order_by(ent.AgentAction.created_at)
            )
        ).scalars().all()
        return {"pending": [{"id": str(a.id), "run_id": str(a.run_id), "tool": a.tool} for a in rows]}

    async def tool_get_memory(self, session: AsyncSession, **kwargs: Any) -> dict:
        user = kwargs.get("user_id")
        rows = (
            await session.execute(
                select(ent.AiMemory)
                .where(ent.AiMemory.deleted_at.is_(None), ent.AiMemory.user_id == uuid.UUID(user) if user else True)
                .order_by(ent.AiMemory.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        return {"memories": [{"memory_type": m.memory_type, "content": m.content[:160]} for m in rows]}

    async def tool_store_memory(self, session: AsyncSession, **kwargs: Any) -> dict:
        user_id = kwargs.get("user_id") or str(uuid.UUID(int=0))
        row = ent.AiMemory(
            user_id=uuid.UUID(user_id),
            memory_type=str(kwargs.get("memory_type") or "WORKFLOW"),
            content=str(kwargs.get("content") or ""),
            importance=int(kwargs.get("importance") or 2),
        )
        session.add(row)
        await session.flush()
        return {"stored": True, "id": str(row.id)}

    async def tool_generate_draft(self, session: AsyncSession, **kwargs: Any) -> dict:
        query = str(kwargs.get("query") or "")
        prompt = (
            "You are drafting a professional clinical/hospital document for human review.\n"
            "Draft requested: {{query}}\n\nDRAFT ONLY — never final. State clearly that human "
            "review and signature are required before use."
        ).replace("{{query}}", query)
        result = await self.inference.complete(self.settings.default_model_key, prompt)
        return {"draft": result.text, "draft_only": True, "human_review_required": True}


# --- planning + serializers ---------------------------------------------------


def plan_workflow(goal: str, context: dict | None = None) -> list[tuple[str, dict]]:
    """Deterministic bounded plan for a goal (implementation detail of the runtime).

    Always grounds with knowledge search, then adds purpose tools by keyword.
    """
    lowered = goal.lower()
    steps: list[tuple[str, dict]] = [("knowledge_search", {"query": goal[:200], "top_k": 3})]
    if any(word in lowered for word in ("predict", "forecast", "inflow", "demand", "shortage", "capacity")):
        entity_type = _infer_entity(goal)
        steps.append(("predict", {"entity_type": entity_type}))
    if any(word in lowered for word in ("memory", "remember", "handover")):
        steps.append(
            (
                "store_memory",
                {"user_id": _user_from_context(context), "content": goal[:2000], "memory_type": "WORKFLOW"},
            )
        )
    if any(word in lowered for word in ("draft", "summar", "report", "letter", "education")):
        steps.append(("generate_draft", {"query": goal}))
    if any(word in lowered for word in ("approval", "pending", "audit", "compliance")):
        steps.append(("list_pending_actions", {}))
    return steps


def _infer_entity(goal: str) -> str:
    lowered = goal.lower()
    for key in ("patient inflow", "inflow", "emergency", "admission"):
        if key in lowered:
            return "patient-inflow"
    if "inventory" in lowered or "stock" in lowered:
        return "inventory"
    if "revenue" in lowered or "finance" in lowered:
        return "revenue"
    if "hr" in lowered or "staff" in lowered or "payroll" in lowered:
        return "staffing"
    return "unknown"


def _user_from_context(context: dict | None) -> str:
    if context and context.get("user_id"):
        return str(context["user_id"])
    return str(uuid.UUID(int=0))


def _summarize(output: dict, executed: int) -> str:
    """Single-line summary of the run result."""
    if output and output.get("sources"):
        titles = ", ".join(s.get("document_title", "?")[:60] for s in output["sources"][:2])
        return f"{executed} steps executed; grounded in: {titles}"
    if output and output.get("draft"):
        return f"{executed} steps executed; draft produced for human review"
    return f"{executed} steps executed"


def agent_def_out(row: ent.AgentDefinition) -> dict:
    return {
        "id": str(row.id),
        "key": row.key,
        "name": row.name,
        "description": row.description,
        "capabilities": row.capabilities,
        "allowed_tools": (row.allowed_tools or {}).get("allowed"),
        "approval_policy": row.approval_policy,
        "is_active": row.is_active,
        "version": row.version,
    }


def agent_run_out(row: ent.AgentRun) -> dict:
    return {
        "id": str(row.id),
        "agent_id": str(row.agent_id),
        "run_token": row.run_token,
        "user_id": str(row.user_id),
        "goal": row.goal,
        "status": row.status,
        "result_ref": row.result_ref,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
    }


def agent_action_out(row: ent.AgentAction) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "action_type": row.action_type,
        "tool": row.tool,
        "input": row.input,
        "output": row.output,
        "requires_approval": row.requires_approval,
        "approval_status": row.approval_status,
        "performed_at": row.performed_at,
    }


# --- event bus bridge ----------------------------------------------------------


def build_agent_event_handlers(
    runtime: AgentRuntime, session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
) -> dict:
    """Returns ``{eventType: handler}`` for the ehos-common EventProcessor.

    Each handler opens a short-lived session and reacts to the event by running
    the matching agent (best-effort — agent failures never poison the bus).
    """

    async def _trigger(envelope: dict, *, record: Any) -> None:
        agent_key = EVENT_TO_AGENT.get(str(envelope.get("eventType", "")))
        if agent_key is None:
            return
        goal = f"process {envelope.get('eventType')} context={str(envelope.get('eventId', ''))}"
        async with session_factory() as session:
            try:
                await runtime.run_agent(
                    session,
                    agent_key,
                    goal=goal,
                    user_id=_uid_from_envelope(envelope),
                    context={"eventId": envelope.get("eventId"), "eventType": envelope.get("eventType")},
                )
            except Exception:  # noqa: BLE001 - best-effort event reaction
                logger.exception("agent event handler failed", extra={"eventType": envelope.get("eventType")})

    return {event_type: _trigger for event_type in EVENT_TO_AGENT}


def _uid_from_envelope(envelope: dict) -> uuid.UUID:
    raw = envelope.get("userId")
    try:
        return uuid.UUID(str(raw)) if raw else uuid.UUID(int=0)
    except ValueError:
        return uuid.UUID(int=0)