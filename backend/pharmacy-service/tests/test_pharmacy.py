"""Tests for pharmacy: catalog, stock FEFO dispensing, controlled drugs, returns."""

import contextlib
import types
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from ehos_common.db import Database

from pharmacy_service.api.routes import get_session
from pharmacy_service.dto.schemas import (
    DispenseIn,
    MedicationIn,
    StockReceiveIn,
)
from pharmacy_service.entity.models import Base
from pharmacy_service.service.pharmacy_service import (
    MEDICATION_DISPENSED_TOPIC,
    MEDICATION_RETURNED_TOPIC,
    PharmacyError,
    PharmacyService,
)

PATIENT = str(uuid.uuid4())
PHARMACIST = str(uuid.uuid4())
NURSE = str(uuid.uuid4())


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


async def _med(session, service, code="MED-001", name="Paracetamol 500mg", controlled=False):
    return await service.create_medication(
        session, MedicationIn(code=code, name=name, form="TABLET", controlled=controlled)
    )


async def _receive(session, service, med_id, qty, batch="B1", days=365, location="MAIN"):
    return await service.receive_stock(
        session,
        StockReceiveIn(
            medication_id=str(med_id),
            location=location,
            batch_number=batch,
            expiry_date=date.today() + timedelta(days=days),
            quantity=Decimal(qty),
        ),
    )


def _dispense(med_id: str, qty: str, **overrides) -> DispenseIn:
    payload = {
        "patient_id": PATIENT,
        "medication_id": med_id,
        "quantity": Decimal(qty),
        "dispensed_by": PHARMACIST,
    }
    payload.update(overrides)
    return DispenseIn(**payload)


# ---------------------------------------------------------------- catalog

async def test_create_and_search_medication(session, service):
    await _med(session, service)
    await _med(session, service, code="MED-002", name="Amoxicillin 500mg")
    items, total = await service.search_medications(session, q="amoxicillin")
    assert total == 1 and items[0]["name"] == "Amoxicillin 500mg"


async def test_duplicate_code_rejected(session, service):
    await _med(session, service)
    with pytest.raises(PharmacyError) as err:
        await _med(session, service)
    assert err.value.error_code == "DUPLICATE_CODE"


# ---------------------------------------------------------------- stock

async def test_receive_stock_accumulates_same_batch(session, service):
    med = await _med(session, service)
    await _receive(session, service, med.id, "100", batch="B1")
    row = await _receive(session, service, med.id, "50", batch="B1")
    assert Decimal(row.quantity) == Decimal("150")


async def test_receive_expired_stock_rejected(session, service):
    med = await _med(session, service)
    with pytest.raises(ValueError):
        await StockReceiveIn(
            medication_id=str(med.id),
            batch_number="OLD",
            expiry_date=date.today() - timedelta(days=1),
            quantity=Decimal("10"),
        )


async def test_batch_expiry_conflict_rejected(session, service):
    med = await _med(session, service)
    await _receive(session, service, med.id, "10", batch="B1", days=100)
    with pytest.raises(PharmacyError) as err:
        await _receive(session, service, med.id, "10", batch="B1", days=200)
    assert err.value.error_code == "BATCH_CONFLICT"


# ---------------------------------------------------------------- dispensing

async def test_dispense_fefo_uses_soonest_expiry_first(session, service):
    med = await _med(session, service)
    await _receive(session, service, med.id, "50", batch="SOON", days=30)
    await _receive(session, service, med.id, "50", batch="LATE", days=400)

    record = await service.dispense(session, _dispense(str(med.id), "60"))
    # SOON exhausted first, remainder from LATE
    assert "SOON" in record.batch_number and "LATE" in record.batch_number
    stock = await service.medication_stock(session, med.id)
    batches = {b["batch_number"]: b["quantity"] for b in stock["batches"]}
    assert batches["SOON"] == 0.0 and batches["LATE"] == 40.0


async def test_dispense_insufficient_stock_mutates_nothing(session, service):
    med = await _med(session, service)
    await _receive(session, service, med.id, "5")
    with pytest.raises(PharmacyError) as err:
        await service.dispense(session, _dispense(str(med.id), "10"))
    assert err.value.error_code == "INSUFFICIENT_STOCK"
    assert err.value.status_code == 409
    stock = await service.medication_stock(session, med.id)
    assert stock["total"] == 5.0


async def test_expired_batch_is_not_dispensed(session, service):
    med = await _med(session, service)
    # receive a batch that will already be expired at dispense time by backdating
    row = await _receive(session, service, med.id, "100", batch="OLD", days=30)
    row.expiry_date = date.today() - timedelta(days=1)
    with pytest.raises(PharmacyError) as err:
        await service.dispense(session, _dispense(str(med.id), "1"))
    assert err.value.error_code == "INSUFFICIENT_STOCK"


# ---------------------------------------------------------------- controlled drugs

async def test_controlled_requires_witness(session, service):
    med = await _med(session, service, code="MORPH-1", name="Morphine 10mg", controlled=True)
    await _receive(session, service, med.id, "20")
    with pytest.raises(PharmacyError) as err:
        await service.dispense(session, _dispense(str(med.id), "5"))
    assert err.value.error_code == "WITNESS_REQUIRED"


async def test_controlled_issue_writes_log_with_balance(session, service):
    med = await _med(session, service, code="MORPH-2", name="Fentanyl patch", controlled=True)
    await _receive(session, service, med.id, "20")
    await service.dispense(session, _dispense(str(med.id), "5", witness_id=NURSE))

    detail = await service.patient_history(session, PATIENT)
    assert detail[0]["quantity"] == 5.0
    # running balance recorded via the log: total is now 15
    stock = await service.medication_stock(session, med.id)
    assert stock["total"] == 15.0


# ---------------------------------------------------------------- returns & history

async def test_return_restocks_and_marks_record(session, service):
    med = await _med(session, service, code="MED-RET", name="Ibuprofen 400mg")
    await _receive(session, service, med.id, "50")
    record = await service.dispense(session, _dispense(str(med.id), "10"))
    returned = await service.return_dispensing(session, record.id, reason="wrong strength")
    assert returned.status == "RETURNED"

    stock = await service.medication_stock(session, med.id)
    assert stock["total"] == 50.0  # 50 - 10 + 10


async def test_double_return_rejected(session, service):
    med = await _med(session, service, code="MED-RET2", name="Codeine syrup", controlled=False)
    await _receive(session, service, med.id, "30")
    rec = await service.dispense(session, _dispense(str(med.id), "5"))
    await service.return_dispensing(session, rec.id, reason="unused")
    with pytest.raises(PharmacyError):
        await service.return_dispensing(session, rec.id, reason="again")


async def test_patient_history_filters_by_patient(session, service):
    other = str(uuid.uuid4())
    med = await _med(session, service, code="MED-H", name="Cetirizine 10mg")
    await _receive(session, service, med.id, "100")
    await service.dispense(session, _dispense(str(med.id), "2"))
    await service.dispense(session, _dispense(str(med.id), "3", patient_id=other))
    mine = await service.patient_history(session, PATIENT)
    assert len(mine) == 1 and mine[0]["patient_id"] == PATIENT


# ---------------------------------------------------------------- outbox events

async def test_events_published_only_after_commit(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'pharmacy.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PharmacyService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, pharmacy_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        med = await _med(session, service)
        await _receive(session, service, med.id, "10")
        await service.dispense(session, _dispense(str(med.id), "2"))
        # nothing may hit the bus before the transaction commits
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)  # commit -> flush outbox

    topics = [t for t, _ in producer.published]
    assert topics == [MEDICATION_DISPENSED_TOPIC]
    await db.dispose()


async def test_return_publishes_event(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'pharmacy.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PharmacyService(settings, producer=producer)

    async with db.session() as raw:
        med = await _med(raw, service)
        await _receive(raw, service, med.id, "10")
        rec = await service.dispense(raw, _dispense(str(med.id), "2"))
        await raw.commit()
    producer.published.clear()

    async with db.session() as raw:
        await service.return_dispensing(raw, rec.id, reason="not needed")
        await raw.commit()

    topics = [t for t, _ in producer.published]
    assert topics[-1] == MEDICATION_RETURNED_TOPIC
    await db.dispose()


async def test_rollback_discards_staged_events(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'pharmacy.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = PharmacyService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, pharmacy_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        med = await _med(session, service)
        await _receive(session, service, med.id, "10")
        await service.dispense(session, _dispense(str(med.id), "1"))
    finally:
        with contextlib.suppress(RuntimeError):
            await gen.athrow(RuntimeError("boom"))

    assert producer.published == []
    await db.dispose()
