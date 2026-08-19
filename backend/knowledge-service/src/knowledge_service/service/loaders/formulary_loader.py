"""Drug Formulary loader — CSV or JSON monographs into per-drug documents."""

from __future__ import annotations

import csv
import io
import json

from knowledge_service.service.loaders.base import DocumentLoader, LoadedDocument, LoaderError

MONOGRAPH_TEMPLATE = (
    "Medication: {name}\nGeneric name: {generic}\nTherapeutic class: {class_}\n"
    "Indications: {indications}\nContraindications: {contraindications}\n"
    "Interactions: {interactions}\nAdverse effects: {adverse_effects}\n"
    "Dosage form / strengths: {dosage_form}\n"
    "Adult dosage: {adult_dosage}\nPediatric dosage: {pediatric_dosage}\n"
    "Maximum dose: {max_dose}\nNotes: {notes}\n"
)

_FIELDS = (
    "drug_name",
    "generic_name",
    "class",
    "indications",
    "contraindications",
    "interactions",
    "adverse_effects",
    "dosage_form",
    "strengths",
    "adult_dosage",
    "pediatric_dosage",
    "max_dose",
    "notes",
)


def _to_document(payload: dict, *, source_format: str, filename: str) -> LoadedDocument | None:
    name = str(payload.get("drug_name") or payload.get("generic_name") or "").strip()
    if not name:
        return None
    generic = str(payload.get("generic_name") or "").strip()
    strengths = str(payload.get("strengths") or "").strip()
    text = MONOGRAPH_TEMPLATE.format(
        name=name,
        generic=generic or name,
        class_=str(payload.get("class") or "").strip(),
        indications=str(payload.get("indications") or "").strip(),
        contraindications=str(payload.get("contraindications") or "").strip(),
        interactions=str(payload.get("interactions") or "").strip(),
        adverse_effects=str(payload.get("adverse_effects") or "").strip(),
        dosage_form=f"{payload.get('dosage_form', '')} {strengths}".strip(),
        adult_dosage=str(payload.get("adult_dosage") or "").strip(),
        pediatric_dosage=str(payload.get("pediatric_dosage") or "").strip(),
        max_dose=str(payload.get("max_dose") or "").strip(),
        notes=str(payload.get("notes") or "").strip(),
    )
    return LoadedDocument(
        title=name,
        doc_type="MEDICATION",
        text=text,
        source_format=source_format,
        ingestion_ref=filename,
        metadata={"generic_name": generic, "drug_class": payload.get("class")},
    )


class FormularyLoader(DocumentLoader):
    """Parse a drug formulary CSV (.csv) or JSON (.formulary / kind=formulary).

    One ``LoadedDocument`` per drug so each monograph is individually searchable.
    """

    formats = (".csv", ".formulary.json")
    kind = "formulary"

    def load(self, raw: bytes, *, filename: str) -> list[LoadedDocument]:
        lower = filename.lower()
        payload = _read_csv(raw) if lower.endswith(".csv") else _read_json(raw)
        documents = [
            doc
            for entry in payload
            if (doc := _to_document(entry, source_format=self._label(lower), filename=filename))
        ]
        if not documents:
            raise LoaderError("PARSE_ERROR", "formulary payload produced no drug entries")
        return documents

    @staticmethod
    def _label(lower: str) -> str:
        return "FORMULARY" if lower.endswith(".formulary.json") else "CSV"


def _read_csv(raw: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="replace")))
    rows = [dict(row) for row in reader]
    if not rows:
        raise LoaderError("PARSE_ERROR", "formulary CSV is empty (missing header?")
    if "drug_name" not in rows[0] and "generic_name" not in rows[0]:
        raise LoaderError("PARSE_ERROR", "formulary CSV requires a 'drug_name' or 'generic_name' column")
    return rows


def _read_json(raw: bytes) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as err:
        raise LoaderError("PARSE_ERROR", f"formulary JSON is invalid: {err}") from err
    entries = payload if isinstance(payload, list) else [payload]
    return [entry for entry in entries if isinstance(entry, dict)]