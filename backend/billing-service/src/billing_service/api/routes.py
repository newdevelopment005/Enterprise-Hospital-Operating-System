"""REST API for the billing-service.

Endpoints under ``/api/v1/billing`` return the standard EHOS envelope. The
service sits behind the API gateway which injects the OAuth2 token.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.api import success_response
from ehos_common.outbox import Outbox
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from billing_service.dto.schemas import AdjustmentIn, ChargeIn, InvoiceIn, PaymentIn, VoidIn
from billing_service.service.billing_service import (
    BillingError,
    BillingService,
    _charge_out,
)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        outbox = Outbox()
        session.info["outbox"] = outbox
        try:
            yield session
            await session.commit()
            # Publish staged events only after the write is durable; events
            # staged for a rolled-back transaction are discarded (no phantom
            # events when the DB commit fails).
            await outbox.flush(getattr(request.app.state, "producer", None))
        except Exception:
            await session.rollback()
            outbox.discard()
            raise


def get_service(request: Request) -> BillingService:
    return request.app.state.billing_service


SvcDep = Annotated[BillingService, Depends(get_service)]


# ================================================================== charges

@router.post("/charges", status_code=201)
async def add_charge(
    data: ChargeIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    charge = await svc.add_charge(session, data)
    return success_response(_charge_out(charge))


@router.get("/charges")
async def list_charges(
    patient_id: str | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    rows, total = await svc.list_charges(
        session, patient_id=_opt_uuid(patient_id), status=status, limit=limit, offset=offset
    )
    return success_response({"charges": [_charge_out(c) for c in rows], "total": total, "limit": limit})


# ================================================================== invoices

@router.post("/invoices", status_code=201)
async def create_invoice(
    data: InvoiceIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    invoice = await svc.create_invoice(session, data)
    return success_response(await svc.get_invoice_detail(session, invoice.id))


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.get_invoice_detail(session, _uuid(invoice_id)))


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    invoice_id: str,
    data: VoidIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    invoice = await svc.void_invoice(session, _uuid(invoice_id), data.reason)
    return success_response(await svc.get_invoice_detail(session, invoice.id))


# ================================================================== payments

@router.post("/payments", status_code=201)
async def record_payment(
    data: PaymentIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    payment, receipt = await svc.record_payment(session, data)
    return success_response(
        {
            "payment": {
                "id": str(payment.id),
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "status": payment.status,
            },
            "receipt_number": receipt.receipt_number,
        }
    )


# ================================================================== adjustments

@router.post("/adjustments", status_code=201)
async def add_adjustment(
    data: AdjustmentIn,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    adj = await svc.add_adjustment(session, data)
    return success_response(
        {
            "id": str(adj.id),
            "invoice_id": str(adj.invoice_id),
            "adjustment_type": adj.adjustment_type,
            "amount": float(adj.amount),
            "reason": adj.reason,
        }
    )


# ================================================================== patient view

@router.get("/patients/{patient_id}/summary")
async def patient_summary(
    patient_id: str,
    session: AsyncSession = Depends(get_session),
    svc: SvcDep = ...,
) -> dict:
    return success_response(await svc.patient_summary(session, _uuid_str(patient_id)))


# ================================================================== helpers

def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise BillingError("INVALID_ID", f"Invalid identifier: {value}", 422) from exc


def _uuid_str(value: str | None) -> str | None:
    if value is None:
        return None
    _uuid(value)
    return value


def _opt_uuid(value: str | None) -> str | None:
    return _uuid_str(value)
