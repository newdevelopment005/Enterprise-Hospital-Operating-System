"""Tests for the in-memory outbox used to publish events after the DB commit."""


from ehos_common.outbox import Outbox


class FakeProducer:
    def __init__(self):
        self.published = []

    async def publish(self, topic, event) -> None:
        self.published.append((topic, event, "publish"))

    async def publish_envelope(self, topic, envelope) -> None:
        self.published.append((topic, envelope, "publish_envelope"))


async def test_flush_publishes_staged_entries_in_order():
    outbox = Outbox()
    producer = FakeProducer()
    outbox.add("topic.a", {"e": 1})
    outbox.add_envelope("topic.b", {"e": 2})
    outbox.add("topic.a", {"e": 3})

    await outbox.flush(producer)

    assert producer.published == [
        ("topic.a", {"e": 1}, "publish"),
        ("topic.b", {"e": 2}, "publish_envelope"),
        ("topic.a", {"e": 3}, "publish"),
    ]
    assert outbox.pending == 0


async def test_discard_drops_staged_events():
    outbox = Outbox()
    producer = FakeProducer()
    outbox.add("topic.a", {"e": 1})
    outbox.discard()
    await outbox.flush(producer)
    assert producer.published == []
    assert outbox.pending == 0


async def test_flush_failure_is_swallowed_and_clears():
    class BoomProducer:
        async def publish(self, topic, event) -> None:
            raise RuntimeError("broker down")

    outbox = Outbox()
    outbox.add("topic.a", {"e": 1})
    await outbox.flush(BoomProducer())  # must not raise
    assert outbox.pending == 0