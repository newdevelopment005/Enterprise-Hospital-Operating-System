#!/usr/bin/env python
"""Seed the audit database with sample records (development only).

Usage:
    python scripts/seed_audit.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ehos_common.db import Database

from audit_service.configuration import get_settings
from audit_service.dto.schemas import AuditRecordCreate
from audit_service.entity.models import Base
from audit_service.service.audit_service import AuditService


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.init_models(Base)
    service = AuditService()
    samples = [
        ("PatientRegistered", "user-1", "patient-service"),
        ("PatientUpdated", "user-2", "patient-service"),
    ]
    async with database.session() as session:
        for event_type, actor, source in samples:
            await service.record(
                session, AuditRecordCreate(event_type=event_type, actor_id=actor, source=source)
            )
        await session.commit()
    print(f"Seeded {len(samples)} audit records.")
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())