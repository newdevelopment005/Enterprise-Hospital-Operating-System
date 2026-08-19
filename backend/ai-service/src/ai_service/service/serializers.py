"""Swappable serialization helpers for the ai-service."""

from __future__ import annotations

import uuid


def _s_id(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def conversation_out(row) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "agent_key": row.agent_key,
        "title": row.title,
        "model_key": row.model_key,
        "system_prompt_code": row.system_prompt_code,
        "summary": row.summary,
        "last_message_at": row.last_message_at,
        "created_at": row.created_at,
    }


def message_out(row) -> dict:
    return {
        "id": str(row.id),
        "conversation_id": str(row.conversation_id),
        "role": row.role,
        "content": row.content,
        "tokens_in": row.tokens_in,
        "tokens_out": row.tokens_out,
        "latency_ms": row.latency_ms,
        "request_id": _s_id(row.request_id),
        "sources": row.sources,
        "created_at": row.created_at,
    }


def prompt_out(row) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "purpose": row.purpose,
        "template": row.template,
        "vars_schema": row.vars_schema,
        "safety_rules": row.safety_rules,
        "is_active": row.is_active,
        "version": row.version,
        "created_at": row.created_at,
    }


def memory_out(row) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "memory_type": row.memory_type,
        "content": row.content,
        "importance": row.importance,
        "created_at": row.created_at,
    }


def request_out(row) -> dict:
    return {
        "id": str(row.id),
        "request_id": row.request_id,
        "user_id": str(row.user_id),
        "model_id": _s_id(row.model_id),
        "request_type": row.request_type,
        "context_type": row.context_type,
        "context_ref": _s_id(row.context_ref),
        "input_ref": row.input_ref,
        "approval_level": row.approval_level,
        "approval_status": row.approval_status,
        "latency_ms": row.latency_ms,
        "tokens_in": row.tokens_in,
        "tokens_out": row.tokens_out,
        "error": row.error,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
    }


def feedback_out(row) -> dict:
    return {
        "id": str(row.id),
        "ai_request_id": str(row.ai_request_id),
        "user_id": str(row.user_id),
        "rating": row.rating,
        "category": row.category,
        "comment": row.comment,
        "accepted": row.accepted,
        "feedback_at": row.feedback_at,
    }