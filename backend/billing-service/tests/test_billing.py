"""Tests for the billing flow: charge → invoice → payment → receipt, voids."""

import contextlib
import types
import uuid
from decimal import Decimal

import pytest
from ehos_common.db import Database

from billing_service.api.routes import get_session
from billing_service.dto.schemas import AdjustmentIn, ChargeIn, InvoiceIn, PaymentIn
from billing_service.entity.models import Base
from billing_service.service.billing_service import (
    BILL_GENERATED_TOPIC,
    CHARGE_CREATED_TOPIC,
    PAYMENT_RECEIVED_TOPIC,
    BillingError,
    BillingService,
)

PATIENT = str(uuid.uuid4())
PATIENT_B = str(uuid.uuid4())


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event, headers=None) -> None:
        self.published.append((topic, event.envelope()))


def _charge(**overrides) -> ChargeIn:
    payload = {
        "patient_id": PATIENT,
        "item_type": "CONSULTATION",
        "description": "General consultation",
        "quantity": Decimal("1"),
        "unit_price": Decimal("200.00"),
    }
    payload.update(overrides)
    return ChargeIn(**payload)


# ---------------------------------------------------------------- charges

async def test_add_charge_starts_pending(session, service):
    c = await service.add_charge(session, _charge())
    assert c.status == "PENDING"
    assert c.billing_ref is None


async def test_list_charges_filters_by_status(session, service):
    await service.add_charge(session, _charge())
    await service.add_charge(session, _charge(item_type="LAB", description="CBC"))
    rows, total = await service.list_charges(session, patient_id=PATIENT)
    assert total == 2
    rows, total = await service.list_charges(session, patient_id=PATIENT_B)
    assert total == 0


# ---------------------------------------------------------------- invoicing

async def test_invoice_bundles_pending_charges_and_marks_billed(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("200")))
    await service.add_charge(
        session, _charge(item_type="LAB", description="X-ray", unit_price=Decimal("350.50"), quantity=Decimal("2"))
    )
    invoice = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    # 200 + 350.50*2 = 901.00
    assert invoice.total_amount == Decimal("901.00")
    assert invoice.patient_amount == Decimal("901.00")

    _, total_charges = await service.list_charges(session, patient_id=PATIENT, status="BILLED")
    assert total_charges == 2


async def test_invoice_with_insurance_split(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("500")))
    invoice = await service.create_invoice(
        session, InvoiceIn(patient_id=PATIENT, insurance_amount=Decimal("300"))
    )
    assert invoice.insurance_amount == Decimal("300")
    assert invoice.patient_amount == Decimal("200")


async def test_invoice_nothing_to_bill_409(session, service):
    with pytest.raises(BillingError) as err:
        await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    assert err.value.error_code == "NOTHING_TO_BILL"


async def test_cannot_double_bill_same_charge(session, service):
    c = await service.add_charge(session, _charge())
    await service.create_invoice(session, InvoiceIn(patient_id=PATIENT, charge_ids=[str(c.id)]))
    with pytest.raises(BillingError) as err:
        await service.create_invoice(session, InvoiceIn(patient_id=PATIENT, charge_ids=[str(c.id)]))
    assert err.value.error_code == "CHARGE_NOT_BILLABLE"


# ---------------------------------------------------------------- payments

async def test_payment_updates_invoice_and_issues_receipt(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("400")))
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))

    payment, receipt = await service.record_payment(
        session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("150"), payment_method="CASH")
    )
    assert payment.status == "APPROVED"
    assert receipt.receipt_number.startswith("RCPT-")
    assert inv.status == "PARTIALLY_PAID"

    payment2, _ = await service.record_payment(
        session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("250"), payment_method="CARD")
    )
    assert float(payment2.amount) == 250.0
    assert inv.status == "PAID"


async def test_overpayment_rejected(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("100")))
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    with pytest.raises(BillingError) as err:
        await service.record_payment(
            session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("999"), payment_method="CASH")
        )
    assert err.value.error_code == "OVERPAYMENT"
    assert err.value.status_code == 409


async def test_cannot_pay_void_invoice(session, service):
    await service.add_charge(session, _charge())
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    await service.void_invoice(session, inv.id, reason="wrong patient bill")
    with pytest.raises(BillingError):
        await service.record_payment(
            session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("10"), payment_method="CASH")
        )


# ---------------------------------------------------------------- void / adjustments

async def test_void_releases_charges_for_rebill(session, service):
    c = await service.add_charge(session, _charge())
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))

    voided = await service.void_invoice(session, inv.id, reason="duplicate visit")
    assert voided.status == "VOID"

    await session.refresh(c)
    assert c.status == "PENDING" and c.billing_ref is None

    # re-billing works again
    reinv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    assert reinv.id != inv.id


async def test_void_blocked_when_paid(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("100")))
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    await service.record_payment(
        session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("100"), payment_method="CASH")
    )
    with pytest.raises(BillingError) as err:
        await service.void_invoice(session, inv.id, reason="nope")
    assert err.value.error_code == "INVOICE_HAS_PAYMENTS"


async def test_discount_adjustment_reduces_patient_share(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("100")))
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    adj = await service.add_adjustment(
        session,
        AdjustmentIn(
            invoice_id=str(inv.id),
            adjustment_type="DISCOUNT",
            amount=Decimal("25"),
            reason="staff family discount",
        ),
    )
    assert adj.amount == Decimal("25")
    assert inv.patient_amount == Decimal("75")


# ---------------------------------------------------------------- summary & events

async def test_patient_summary_totals(session, service):
    await service.add_charge(session, _charge(unit_price=Decimal("300")))
    inv = await service.create_invoice(session, InvoiceIn(patient_id=PATIENT))
    await service.record_payment(
        session, PaymentIn(invoice_id=str(inv.id), amount=Decimal("120"), payment_method="WALLET")
    )
    summary = await service.patient_summary(session, PATIENT)
    assert summary["totals"]["billed"] == 300.0
    assert summary["totals"]["paid"] == 120.0
    assert summary["totals"]["outstanding"] == 180.0


async def test_events_published_only_after_commit(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = BillingService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, billing_service=service, producer=producer)
        )
    )
    gen = get_session(request)
    session = await gen.__anext__()
    try:
        await service.add_charge(session, _charge())
        assert producer.published == []
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)

    topics = [t for t, _ in producer.published]
    assert topics == [CHARGE_CREATED_TOPIC]
    await db.dispose()


async def test_invoice_and_payment_event_sequence(settings, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}")
    await db.init_models(Base)
    producer = FakeProducer()
    service = BillingService(settings, producer=producer)

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(database=db, billing_service=service, producer=producer)
        )
    )

    gen = get_session(request)
    s = await gen.__anext__()
    try:
        await service.add_charge(s, _charge(unit_price=Decimal("80")))
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)

    gen = get_session(request)
    s = await gen.__anext__()
    try:
        inv = await service.create_invoice(s, InvoiceIn(patient_id=PATIENT))
        await service.record_payment(
            s, PaymentIn(invoice_id=str(inv.id), amount=Decimal("80"), payment_method="CASH")
        )
    finally:
        with contextlib.suppress(StopAsyncIteration):
            await gen.asend(None)

    topics = [t for t, _ in producer.published]
    assert topics == [
        CHARGE_CREATED_TOPIC,
        BILL_GENERATED_TOPIC,
        PAYMENT_RECEIVED_TOPIC,
    ]
    await db.dispose()
