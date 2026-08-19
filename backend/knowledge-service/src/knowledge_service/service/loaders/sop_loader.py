"""Hospital SOP loader — structured JSON SOPs normalized into searchable text."""

from __future__ import annotations

import json
import os

from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError

SOP_TEMPLATE = (
    "SOP: {title}\nDepartment: {department}\nOwner: {owner}\n"
    "Purpose: {purpose}\nScope: {scope}\nApproval: {approval}\n"
    "{sections}"
)


def _loads_payload(raw: bytes) -> dict | list:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise LoaderError("PARSE_ERROR", f"SOP JSON is invalid: {err}") from err


def _render_sop(entry: dict) -> LoadedDocument:
    title = str(entry.get("title") or entry.get("id") or "Hospital SOP")
    sections: list[str] = []
    for section in entry.get("sections", []) or []:
        heading = f"## {section.get('title')}" if section.get("title") else "## Section"
        if section.get("purpose"):
            sections.append(f"{heading}\nPurpose: {section['purpose']}")
        if section.get("scope"):
            sections.append(f"Scope: {section['scope']}")
        steps = section.get("steps") or []
        if steps:
            steps_text = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
            sections.append(f"{heading}\n{steps_text}")
        if section.get("references"):
            refs = "\n".join(f"- {ref}" for ref in section["references"])
            sections.append(f"{heading}\nReferences:\n{refs}")
    content = SOP_TEMPLATE.format(
        title=title,
        department=entry.get("department", ""),
        owner=entry.get("owner", ""),
        purpose=entry.get("purpose", ""),
        scope=entry.get("scope", ""),
        approval=entry.get("approval", ""),
        sections="\n".join(sections) or "No sections supplied.",
    )
    metadata = {
        "department": entry.get("department"),
        "owner": entry.get("owner"),
        "sop_version": entry.get("version"),
    }
    return LoadedDocument(
        title=title,
        doc_type="PROTOCOL",
        text=content,
        source_format="SOP",
        ingestion_ref=None,
        metadata=metadata,
    )


class SopLoader(DocumentLoader):
    """Parse one or more SOP objects from a structured JSON payload."""

    formats = ()
    kind = "sop"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        payload = _loads_payload(raw)
        entries = payload if isinstance(payload, list) else [payload]
        documents = [_render_sop(entry) for entry in entries]
        for doc in documents:
            doc.ingestion_ref = os.path.basename(filename) or "sop"
        if not documents:
            raise LoaderError("PARSE_ERROR", "SOP payload contained no entries")
        return documents