"""Tests for the specialized AI agents runtime and its event bridge."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from ai_service.entity import models as ent
from ai_service.service import agents as ag
from ai_service.service.agents import build_agent_event_handlers


async def test_seed_creates_ten_agents(service, session):
    runtime = service.agents
    inserted = await runtime.ensure_seeds(session)
    await session.flush()
    rows = (await session.execute(select(ent.AgentDefinition))).scalars().all()
    assert inserted == 10
    assert {r.key for r in rows} == set(ag.AGENT_KEYS)


@pytest.mark.asyncio
async def test_run_completes_for_clinical(service, session):
    runtime = service.agents
    run = await runtime.run_agent(session, "clinical", goal="advise on sepsis guidelines", user_id=uuid.uuid4())
    assert run.status == "COMPLETED"
    assert run.finished_at is not None
    actions = await runtime.list_actions(session, run.id)
    assert actions
    assert all(a.output is not None for a in actions)
    assert all(not a.requires_approval for a in actions)


@pytest.mark.asyncio
async def test_run_pauses_on_approval_gate(service, session):
    runtime = service.agents
    run = await runtime.run_agent(session, "pharmacy", goal="draft a discharge medication plan", user_id=uuid.uuid4())
    assert run.status == "AWAITING_APPROVAL"
    actions = await runtime.list_actions(session, run.id)
    gated = [a for a in actions if a.requires_approval]
    assert gated
    assert gated[-1].approval_status == "PENDING"


@pytest.mark.asyncio
async def test_decide_action_approve_completes_run(service, session):
    runtime = service.agents
    run = await runtime.run_agent(session, "pharmacy", goal="draft a discharge medication plan", user_id=uuid.uuid4())
    gated = [a for a in await runtime.list_actions(session, run.id) if a.requires_approval]
    approver = str(uuid.uuid4())
    final = await runtime.decide_action(session, gated[-1].id, approver, approved=True, comments="clinician on duty")
    assert final.status == "COMPLETED"
    assert "Approved" in final.result_ref


@pytest.mark.asyncio
async def test_decide_action_reject_cancels_run(service, session):
    runtime = service.agents
    run = await runtime.run_agent(session, "finance", goal="draft an invoice letter", user_id=uuid.uuid4())
    gated = [a for a in await runtime.list_actions(session, run.id) if a.requires_approval]
    final = await runtime.decide_action(session, gated[-1].id, str(uuid.uuid4()), approved=False)
    assert final.status == "CANCELLED"


@pytest.mark.asyncio
async def test_goal_keywords_plan_tools(service, session):
    runtime = service.agents
    user = uuid.uuid4()
    run = await runtime.run_agent(session, "inventory", goal="forecast stock shortage for paracetamol", user_id=user)
    actions = await runtime.list_actions(session, run.id)
    tools = [a.tool for a in actions]
    assert "predict" in tools
    assert "knowledge_search" in tools


@pytest.mark.asyncio
async def test_disallowed_tool_blocks_run(service, session):
    runtime = service.agents
    await runtime.ensure_seeds(session)
    definition = (
        await session.execute(select(ent.AgentDefinition).where(ent.AgentDefinition.key == "nursing"))
    ).scalar_one()
    definition.allowed_tools = {"allowed": ["knowledge_search"]}
    await session.flush()
    run = await runtime.run_agent(session, "nursing", goal="draft a patient education handout", user_id=uuid.uuid4())
    assert run.status == "BLOCKED"
    actions = await runtime.list_actions(session, run.id)
    assert actions[-1].approval_status == "BLOCKED"


@pytest.mark.asyncio
async def test_event_handler_runs_matching_agent(service, session):
    runtime = service.agents

    @asynccontextmanager
    async def session_factory():
        yield session

    handlers = build_agent_event_handlers(runtime, session_factory=session_factory)
    envelope = {"eventId": str(uuid.uuid4()), "eventType": "MedicationDispensed", "userId": None}
    await handlers["MedicationDispensed"](envelope, record=None)
    runs = (await session.execute(select(ent.AgentRun).order_by(ent.AgentRun.created_at.desc()))).scalars().first()
    assert runs is not None
    agent = (
        await session.execute(select(ent.AgentDefinition).where(ent.AgentDefinition.id == runs.agent_id))
    ).scalar_one()
    assert agent.key == "pharmacy"


@pytest.mark.asyncio
async def test_event_handler_ignores_unmapped_event(service, session):
    runtime = service.agents

    @asynccontextmanager
    async def session_factory():
        yield session

    handlers = build_agent_event_handlers(runtime, session_factory=session_factory)
    await handlers["EmergencyTriggered"]({"eventType": "UnrelatedEvent", "eventId": str(uuid.uuid4())}, record=None)
    rows = (await session.execute(select(ent.AgentRun))).scalars().all()
    assert rows == []


async def test_list_runs_and_pending_action_tools(service, session):
    runtime = service.agents
    user = uuid.uuid4()
    await runtime.run_agent(session, "pharmacy", goal="draft discharge plan", user_id=user)
    runs, total = await runtime.list_runs(session, agent_key="pharmacy", status="AWAITING_APPROVAL", limit=10, offset=0)
    assert total >= 1
    assert all(r.status == "AWAITING_APPROVAL" for r in runs)