"""Business logic for billing: charges → invoice → payment → receipt.

Publishes ``ChargeCreated`` / ``BillGenerated`` (``finance.billing.generated``)
/ ``PaymentReceived`` on the finance topics so finance and analytics services
keep projections fresh. Financial records are never hard-deleted; voids and
adjustments are recorded as separate correction entries.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from ehos_common.events import DomainEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_service.configuration import BillingSettings
from billing_service.dto.schemas import AdjustmentIn, ChargeIn, InvoiceIn, PaymentIn
from billing_service.entity.models import (
    Adjustment,
    Charge,
    Invoice,
    InvoiceItem,
    Payment,
    Receipt,
)

log = logging.getLogger("billing-service")

BILL_GENERATED_TOPIC = "finance.billing.generated"
CHARGE_CREATED_TOPIC = "finance.billing.charge_created"
PAYMENT_RECEIVED_TOPIC = "finance.billing.payment_received"

_TOPICS = {
    "BillGenerated": BILL_GENERATED_TOPIC,
    "ChargeCreated": CHARGE_CREATED_TOPIC,
    "PaymentReceived": PAYMENT_RECEIVED_TOPIC,
}

BILLED_STATUSES = ("BILLED",)


class BillingError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BillingService:
    def __init__(self, settings: BillingSettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = _TOPICS.get(event_type, BILL_GENERATED_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="billing-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break billing
            log.exception("failed to publish %s", event_type)

    async def _next_number(self, session: AsyncSession, model, column, prefix: str) -> str:
        result = await session.execute(
            select(func.max(column)).where(column.like(f"{prefix}-%"))
        )
        max_val = result.scalar()
        seq = int(max_val.rsplit("-", 1)[1]) if max_val else 0
        return f"{prefix}-{seq + 1:0{self.settings.number_width}d}"

    async def _get_invoice(self, session: AsyncSession, invoice_id) -> Invoice:
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None or invoice.deleted_at is not None:
            raise BillingError("INVOICE_NOT_FOUND", "Invoice not found", 404)
        return invoice

    # ------------------------------------------------------------ charges

    async def add_charge(self, session: AsyncSession, data: ChargeIn, actor=None) -> Charge:
        charge = Charge(
            patient_id=uuid.UUID(data.patient_id),
            encounter_id=uuid.UUID(data.encounter_id) if data.encounter_id else None,
            service_date=date.today(),
            item_type=data.item_type,
            item_code=data.item_code,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            discount=data.discount,
            source_service="MANUAL" if actor is None else "ehr-service",
            created_by=actor,
            status="PENDING",
        )
        session.add(charge)
        await session.flush()
        await self._publish(
            session,
            "ChargeCreated",
            {"chargeId": str(charge.id), "patientId": str(charge.patient_id), "itemType": data.item_type},
        )
        return charge

    async def list_charges(
        self,
        session: AsyncSession,
        *,
        patient_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Charge], int]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        stmt = select(Charge).where(Charge.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(Charge.patient_id == uuid.UUID(patient_id))
        if status:
            stmt = stmt.where(Charge.status == status.upper())
        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            (
                await session.execute(
                    stmt.order_by(Charge.service_date.desc(), Charge.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # ------------------------------------------------------------ invoicing

    async def create_invoice(self, session: AsyncSession, data: InvoiceIn, actor=None) -> Invoice:
        patient_id = uuid.UUID(data.patient_id)

        stmt = select(Charge).where(
            Charge.patient_id == patient_id,
            Charge.deleted_at.is_(None),
        )
        if data.charge_ids:
            wanted = {uuid.UUID(c) for c in data.charge_ids}
            stmt = stmt.where(Charge.id.in_(wanted))
        else:
            stmt = stmt.where(Charge.status == "PENDING")
        fetched = list((await session.execute(stmt)).scalars().all())

        billable = [c for c in fetched if c.status == "PENDING"]
        if data.charge_ids:
            # explicit selection: every requested charge must be billable
            non_pending = [str(c.id) for c in fetched if c.status != "PENDING"]
            missing = len(data.charge_ids) - len(fetched) + len(non_pending)
            if missing > 0 or non_pending:
                raise BillingError(
                    "CHARGE_NOT_BILLABLE",
                    f"{missing} of the requested charges are not in PENDING state.",
                    409,
                )
        elif not billable:
            raise BillingError("NOTHING_TO_BILL", "No pending charges found for this patient.", 409)

        items: list[tuple[Charge, Decimal]] = []
        total = Decimal("0")
        for c in billable:
            amount = (c.quantity * c.unit_price) - c.discount
            total += amount
            items.append((c, amount))

        insurance = min(data.insurance_amount, total)
        invoice_number = await self._next_number(
            session, Invoice, Invoice.invoice_number, self.settings.invoice_prefix
        )
        invoice = Invoice(
            invoice_number=invoice_number,
            patient_id=patient_id,
            total_amount=total,
            insurance_amount=insurance,
            patient_amount=total - insurance,
            paid_amount=Decimal("0"),
            discount_amount=sum((c.discount for c, _ in items), Decimal("0")),
            currency=self.settings.currency,
            issued_date=date.today(),
            due_date=data.due_date,
            created_by=actor,
            status="UNPAID",
        )
        session.add(invoice)
        await session.flush()

        for c, amount in items:
            session.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    charge_id=c.id,
                    description=c.description,
                    quantity=c.quantity,
                    unit_price=c.unit_price,
                    amount=amount,
                    status="ACTIVE",
                )
            )
            c.status = "BILLED"
            c.billing_ref = invoice.id

        await session.flush()
        await self._publish(
            session,
            "BillGenerated",
            {
                "invoiceId": str(invoice.id),
                "invoiceNumber": invoice.invoice_number,
                "patientId": str(patient_id),
                "totalAmount": float(total),
            },
        )
        return invoice

    async def get_invoice_detail(self, session: AsyncSession, invoice_id) -> dict:
        invoice = await self._get_invoice(session, invoice_id)
        items = (
            (
                await session.execute(
                    select(InvoiceItem).where(
                        InvoiceItem.invoice_id == invoice.id, InvoiceItem.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        payments = (
            (
                await session.execute(
                    select(Payment).where(
                        Payment.invoice_id == invoice.id, Payment.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        detail = _invoice_out(invoice)
        detail["items"] = [_invoice_item_out(i) for i in items]
        detail["payments"] = [_payment_out(p) for p in payments]
        detail["balance_due"] = float(invoice.patient_amount - invoice.paid_amount)
        return detail

    async def void_invoice(self, session: AsyncSession, invoice_id, reason: str, actor=None) -> Invoice:
        invoice = await self._get_invoice(session, invoice_id)
        if invoice.status == "VOID":
            raise BillingError("INVALID_STATUS", "Invoice is already void.", 409)
        if invoice.paid_amount > 0:
            raise BillingError(
                "INVOICE_HAS_PAYMENTS",
                "Cannot void an invoice with recorded payments; issue a credit note instead.",
                409,
            )

        invoice.status = "VOID"
        invoice.void_reason = reason
        invoice.updated_by = actor
        invoice.version += 1

        # release the charges back to PENDING so they can be re-billed correctly
        items = (
            (
                await session.execute(
                    select(InvoiceItem).where(
                        InvoiceItem.invoice_id == invoice.id, InvoiceItem.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            if item.charge_id is not None:
                charge = await session.get(Charge, item.charge_id)
                if charge is not None and charge.status == "BILLED":
                    charge.status = "PENDING"
                    charge.billing_ref = None

        session.add(
            Adjustment(
                invoice_id=invoice.id,
                patient_id=invoice.patient_id,
                adjustment_type="VOID",
                amount=invoice.total_amount,
                reason=reason,
                applied_by=actor,
                status="ACTIVE",
            )
        )
        await session.flush()
        return invoice

    # ------------------------------------------------------------ payments

    async def record_payment(self, session: AsyncSession, data: PaymentIn, actor=None) -> tuple[Payment, Receipt]:
        invoice = await self._get_invoice(session, uuid.UUID(data.invoice_id))
        if invoice.status in ("VOID", "CREDIT_NOTE"):
            raise BillingError("INVALID_STATUS", f"Cannot pay a {invoice.status} invoice.", 409)

        balance = invoice.patient_amount - invoice.paid_amount
        if data.amount > balance:
            raise BillingError(
                "OVERPAYMENT",
                f"Payment exceeds the outstanding balance of {balance:.2f} {invoice.currency}.",
                409,
            )

        payment = Payment(
            invoice_id=invoice.id,
            patient_id=invoice.patient_id,
            amount=data.amount,
            payment_method=data.payment_method,
            provider_ref=data.provider_ref,
            received_by=actor,
            status="APPROVED",
        )
        session.add(payment)
        await session.flush()

        invoice.paid_amount += data.amount
        if invoice.paid_amount >= invoice.patient_amount:
            invoice.status = "PAID"
        elif invoice.paid_amount > 0:
            invoice.status = "PARTIALLY_PAID"
        invoice.updated_by = actor
        invoice.version += 1

        receipt = Receipt(
            payment_id=payment.id,
            receipt_number=await self._next_number(
                session, Receipt, Receipt.receipt_number, self.settings.receipt_prefix
            ),
            issued_by=actor,
            receipt_ref=f"invoice:{invoice.invoice_number}",
            status="ACTIVE",
        )
        session.add(receipt)
        await session.flush()

        await self._publish(
            session,
            "PaymentReceived",
            {
                "invoiceId": str(invoice.id),
                "paymentId": str(payment.id),
                "patientId": str(invoice.patient_id),
                "amount": float(data.amount),
                "method": data.payment_method,
            },
        )
        return payment, receipt

    # ------------------------------------------------------------ patient summary

    async def patient_summary(self, session: AsyncSession, patient_id: str) -> dict:
        pid = uuid.UUID(patient_id)
        invoices = (
            (
                await session.execute(
                    select(Invoice)
                    .where(Invoice.patient_id == pid, Invoice.deleted_at.is_(None))
                    .order_by(Invoice.issued_date.desc())
                )
            )
            .scalars()
            .all()
        )
        pending_charges = (
            (
                await session.execute(
                    select(func.count())
                    .select_from(Charge)
                    .where(
                        Charge.patient_id == pid,
                        Charge.status == "PENDING",
                        Charge.deleted_at.is_(None),
                    )
                )
            ).scalar_one(),
        )[0]

        billed = sum((i.total_amount for i in invoices), Decimal("0"))
        paid = sum((i.paid_amount for i in invoices), Decimal("0"))
        outstanding = sum(
            (i.patient_amount - i.paid_amount for i in invoices if i.status not in ("VOID", "CREDIT_NOTE")),
            Decimal("0"),
        )
        return {
            "patient_id": patient_id,
            "invoices": [_invoice_out(i) for i in invoices],
            "pending_charge_count": pending_charges,
            "totals": {
                "billed": float(billed),
                "paid": float(paid),
                "outstanding": float(outstanding),
            },
        }

    # ------------------------------------------------------------ adjustments

    async def add_adjustment(self, session: AsyncSession, data: AdjustmentIn, actor=None) -> Adjustment:
        invoice = await self._get_invoice(session, uuid.UUID(data.invoice_id))
        if invoice.status == "VOID":
            raise BillingError("INVALID_STATUS", "Cannot adjust a voided invoice.", 409)
        adj = Adjustment(
            invoice_id=invoice.id,
            patient_id=invoice.patient_id,
            adjustment_type=data.adjustment_type,
            amount=data.amount,
            reason=data.reason,
            applied_by=actor,
            status="ACTIVE",
        )
        session.add(adj)
        if data.adjustment_type in ("DISCOUNT", "WRITE_OFF"):
            invoice.discount_amount += data.amount
            new_patient_amount = max(
                Decimal("0"),
                invoice.total_amount - invoice.insurance_amount - invoice.discount_amount,
            )
            invoice.patient_amount = new_patient_amount
            invoice.version += 1
        await session.flush()
        return adj


# ---------------------------------------------------------------- serializers

def _money(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _charge_out(c: Charge) -> dict:
    return {
        "id": str(c.id),
        "patient_id": str(c.patient_id),
        "encounter_id": str(c.encounter_id) if c.encounter_id else None,
        "service_date": c.service_date.isoformat(),
        "item_type": c.item_type,
        "item_code": c.item_code,
        "description": c.description,
        "quantity": _money(c.quantity),
        "unit_price": _money(c.unit_price),
        "discount": _money(c.discount),
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _invoice_out(i: Invoice) -> dict:
    return {
        "id": str(i.id),
        "invoice_number": i.invoice_number,
        "patient_id": str(i.patient_id),
        "total_amount": _money(i.total_amount),
        "insurance_amount": _money(i.insurance_amount),
        "patient_amount": _money(i.patient_amount),
        "paid_amount": _money(i.paid_amount),
        "currency": i.currency,
        "issued_date": i.issued_date.isoformat(),
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "status": i.status,
        "void_reason": i.void_reason,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _invoice_item_out(item: InvoiceItem) -> dict:
    return {
        "id": str(item.id),
        "charge_id": str(item.charge_id) if item.charge_id else None,
        "description": item.description,
        "quantity": _money(item.quantity),
        "unit_price": _money(item.unit_price),
        "amount": _money(item.amount),
    }


def _payment_out(p: Payment) -> dict:
    return {
        "id": str(p.id),
        "amount": _money(p.amount),
        "payment_method": p.payment_method,
        "provider_ref": p.provider_ref,
        "payment_date": p.payment_date.isoformat() if p.payment_date else None,
        "status": p.status,
    }
