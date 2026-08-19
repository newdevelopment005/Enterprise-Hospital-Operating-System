"""Business logic for configuration management.

Publishes ``ConfigurationUpdated`` events so downstream services observe changes.
Values are cached in Redis for low-latency reads.
"""

import logging

from ehos_common.events import DomainEvent, KafkaProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config_service.dto.schemas import ConfigurationEntryIn, FeatureFlagIn
from config_service.entity.models import ConfigurationEntry, FeatureFlag

log = logging.getLogger("configuration-service")

CONFIG_CACHE_PREFIX = "ehos:config:"


class Publisher:
    """Wraps the shared Kafka producer for configuration events."""

    def __init__(self, producer: KafkaProducer):
        self.producer = producer

    async def publish_configuration_updated(self, config_key: str, value: object, user_id: str | None = None) -> None:
        try:
            await self.producer.publish(
                "configuration.topic",
                DomainEvent(
                    event_type="ConfigurationUpdated",
                    source="configuration-service",
                    correlation_id=None,
                    user_id=user_id,
                    payload={"configKey": config_key, "value": value},
                ),
            )
        except Exception:
            log.exception("failed to publish ConfigurationUpdated event")


class ConfigurationService:
    def __init__(self, redis_client, publisher: Publisher):
        self.redis = redis_client
        self.publisher = publisher

    # ---- Feature flags ----

    async def create_flag(self, session: AsyncSession, data: FeatureFlagIn, updated_by: str | None) -> FeatureFlag:
        flag = FeatureFlag(name=data.name, enabled=data.enabled, description=data.description, created_by=updated_by)
        session.add(flag)
        await session.flush()
        return flag

    async def list_flags(self, session: AsyncSession) -> list[FeatureFlag]:
        return list((await session.execute(select(FeatureFlag).order_by(FeatureFlag.name))).scalars().all())

    async def get_flag(self, session: AsyncSession, name: str) -> FeatureFlag | None:
        return (
            await session.execute(select(FeatureFlag).where(FeatureFlag.name == name))
        ).scalar_one_or_none()

    async def set_flag(
        self, session: AsyncSession, name: str, enabled: bool, updated_by: str | None
    ) -> FeatureFlag | None:
        flag = await self.get_flag(session, name)
        if flag is None:
            return None
        flag.enabled = enabled
        flag.updated_by = updated_by
        await session.flush()
        return flag

    # ---- Reference configuration entries ----

    async def upsert_entry(
        self, session: AsyncSession, data: ConfigurationEntryIn, updated_by: str | None
    ) -> ConfigurationEntry:
        entry = (
            await session.execute(select(ConfigurationEntry).where(ConfigurationEntry.config_key == data.config_key))
        ).scalar_one_or_none()
        if entry is None:
            entry = ConfigurationEntry(
                config_key=data.config_key,
                config_value=data.config_value,
                value_type=data.value_type,
                description=data.description,
                version=1,
                created_by=updated_by,
            )
            session.add(entry)
        else:
            entry.config_value = data.config_value
            entry.value_type = data.value_type
            entry.description = data.description
            entry.version += 1
            entry.updated_by = updated_by
        await session.flush()

        await self.redis.set_json(
            f"{CONFIG_CACHE_PREFIX}{data.config_key}",
            {"value": data.config_value, "type": data.value_type, "version": entry.version},
        )
        await self.publisher.publish_configuration_updated(data.config_key, data.config_value, updated_by)
        return entry

    async def list_entries(self, session: AsyncSession) -> list[ConfigurationEntry]:
        result = await session.execute(select(ConfigurationEntry).order_by(ConfigurationEntry.config_key))
        return list(result.scalars().all())

    async def get_entry(self, session: AsyncSession, config_key: str) -> ConfigurationEntry | None:
        return (
            await session.execute(select(ConfigurationEntry).where(ConfigurationEntry.config_key == config_key))
        ).scalar_one_or_none()

    async def get_entry_cached(self, session: AsyncSession, config_key: str) -> object | None:
        cached = await self.redis.get_json(f"{CONFIG_CACHE_PREFIX}{config_key}")
        if cached is not None:
            return cached
        entry = await self.get_entry(session, config_key)
        if entry is None:
            return None
        await self.redis.set_json(
            f"{CONFIG_CACHE_PREFIX}{config_key}",
            {"value": entry.config_value, "type": entry.value_type, "version": entry.version},
        )
        return {"value": entry.config_value, "type": entry.value_type, "version": entry.version}