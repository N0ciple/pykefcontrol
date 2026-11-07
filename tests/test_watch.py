"""Event queue: subscribe / poll / events() / watch() against the fake speaker."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any

import pytest

from pykefcontrol import (
    KefApiError,
    KefAsyncClient,
    KefClient,
    KefConnectionError,
    KefError,
    PlaybackState,
    SpeakerState,
    Subscription,
    SubscriptionType,
    const,
    create_ssl_context,
)

from .fake_speaker import PKI, PLAY_DATA_PATH, FakeSpeaker, player_data, typed

VOLUME = "player:volume"
SOURCE = "settings:/kef/play/physicalSource"
MUTE = "settings:/mediaPlayer/mute"


@pytest.fixture(autouse=True)
def _fast(fast_reconnect: None) -> None:
    """Short back-off and no minimum poll interval (the fake answers polls in 0.2 s)."""


@pytest.fixture
async def client(speaker: FakeSpeaker) -> AsyncIterator[KefAsyncClient]:
    async with KefAsyncClient(speaker.host, transport="http", http_port=speaker.http_port) as c:
        yield c


async def nxt(gen: AsyncIterator[Any]) -> Any:
    async with asyncio.timeout(5):
        return await anext(gen)


# --- event queue ------------------------------------------------------------------------


async def test_subscribe_returns_true_only_for_a_new_queue(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    queue = client.event_queue()
    assert speaker.requests == []  # no I/O when creating a queue
    assert await queue.subscribe([VOLUME]) is True
    assert await queue.subscribe([MUTE]) is False  # same queue, subscription added
    (queue_id,) = speaker.queues
    assert queue.queue_id == queue_id
    assert set(speaker.queues[queue_id].subs) == {VOLUME, MUTE}
    second = speaker.requests_to("/api/event/modifyQueue")[1].json
    assert second["queueId"] == queue_id

    speaker.new_queue_on_modify = True  # the speaker lost our queue
    assert await queue.subscribe(["settings:/deviceName"]) is True
    newest = list(speaker.queues.values())[-1]
    assert set(newest.subs) == {VOLUME, MUTE, "settings:/deviceName"}  # all re-sent
    assert {s.path for s in queue.subscriptions} == set(newest.subs)


async def test_unsubscribe_and_subscription_types(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    queue = client.event_queue()
    await queue.subscribe([VOLUME, Subscription(MUTE, SubscriptionType.ITEM)])
    (server_queue,) = speaker.queues.values()
    assert server_queue.subs == {VOLUME: "itemWithValue", MUTE: "item"}
    await queue.subscribe([], unsubscribe=[VOLUME])
    assert server_queue.subs == {MUTE: "item"}


async def test_poll_returns_every_event_in_arrival_order(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    queue = client.event_queue()
    await queue.subscribe([VOLUME, MUTE])
    speaker.set(VOLUME, typed("i32_", 1))
    speaker.set(MUTE, typed("bool_", True))
    speaker.set(VOLUME, typed("i32_", 2))
    events = await queue.poll(1)
    assert [(e.path, e.value) for e in events] == [(VOLUME, 1), (MUTE, True), (VOLUME, 2)]
    (poll,) = speaker.requests_to("/api/event/pollQueue")
    assert poll.query["timeout"] == "1"
    assert await queue.poll(1) == []  # nothing new: long poll times out


async def test_poll_before_subscribe_raises(client: KefAsyncClient) -> None:
    with pytest.raises(KefError, match="Not subscribed"):
        await client.event_queue().poll(1)


async def test_item_subscription_has_no_value(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    queue = client.event_queue()
    await queue.subscribe([Subscription(VOLUME, SubscriptionType.ITEM)])
    speaker.set(VOLUME, typed("i32_", 9))
    (event,) = await queue.poll(1)
    assert event.has_value is False


async def test_poll_on_expired_queue_raises_and_forgets_it(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    queue = client.event_queue()
    await queue.subscribe([VOLUME])
    speaker.forget_queues()
    with pytest.raises(KefApiError) as info:
        await queue.poll(1)
    assert info.value.status == 500
    assert queue.queue_id is None
    with pytest.raises(KefError, match="Not subscribed"):
        await queue.poll(1)
    assert await queue.subscribe([VOLUME]) is True


async def test_queues_are_independent(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    q1, q2 = client.event_queue(), client.event_queue()
    await q1.subscribe([VOLUME])
    await q2.subscribe([VOLUME])
    assert q1.queue_id != q2.queue_id
    speaker.set(VOLUME, typed("i32_", 5))
    assert [e.value for e in await q1.poll(1)] == [5]
    assert [e.value for e in await q2.poll(1)] == [5]


async def test_events_low_level(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    timer = threading.Timer(0.1, speaker.set, (VOLUME, typed("i32_", 70)))
    timer.start()
    try:
        events = client.events([VOLUME], timeout=1)
        event = await nxt(events)
        await events.aclose()
    finally:
        timer.cancel()
    assert (event.path, event.value) == (VOLUME, 70)


async def test_events_raises_on_connection_loss(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    events = client.events([VOLUME], timeout=1)
    timer = threading.Timer(0.1, speaker.stop)
    timer.start()
    try:
        with pytest.raises(KefConnectionError):
            await nxt(events)
    finally:
        timer.cancel()


# --- watch ---------------------------------------------------------------------------------


async def test_watch_snapshot_then_changes(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    gen = client.watch()
    state = await nxt(gen)
    assert isinstance(state, SpeakerState)
    assert (state.volume, state.muted, state.name) == (30, False, "Living room")
    assert state.playback_state == PlaybackState.PLAYING
    assert state.position_ms == 42000

    speaker.set(VOLUME, typed("i32_", 55))
    state = await nxt(gen)
    assert state.volume == 55

    speaker.set(SOURCE, typed("kefPhysicalSource", "tv"))
    state = await nxt(gen)
    assert state.source == "tv"
    assert state.volume == 55  # the rest of the state is kept

    speaker.set(PLAY_DATA_PATH, player_data("paused"))
    state = await nxt(gen)
    assert state.playback_state == PlaybackState.PAUSED
    assert state.position_ms == 42000  # refreshed (paused players keep a position)

    speaker.set(MUTE, typed("bool_", True))
    assert (await nxt(gen)).muted is True
    await gen.aclose()


async def test_watch_skips_events_that_change_nothing(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    gen = client.watch()
    await nxt(gen)
    speaker.set(VOLUME, typed("i32_", 30))  # same value
    speaker.set(MUTE, typed("bool_", True))
    state = await nxt(gen)  # first yield is for the mute change (volume event folded away)
    assert state.muted is True and state.volume == 30
    await gen.aclose()


async def test_watch_rereads_value_when_event_has_none(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    gen = client.watch()
    await nxt(gen)
    speaker.store[VOLUME] = typed("i32_", 81)  # silent change, then a value-less event
    speaker.emit({"path": VOLUME, "itemType": "update"})
    assert (await nxt(gen)).volume == 81
    await gen.aclose()


async def test_watch_extra_paths_and_position(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    extra = "settings:/kef/host/maximumVolume"
    gen = client.watch(extra_paths=[extra], track_position=True)
    state = await nxt(gen)
    assert state.extra == {extra: 80}
    speaker.set(extra, typed("i32_", 60))
    assert (await nxt(gen)).extra == {extra: 60}
    speaker.set("player:player/data/playTime", typed("i64_", 50000))
    assert (await nxt(gen)).position_ms == 50000
    await gen.aclose()


async def test_watch_yields_none_when_speaker_goes_away_then_recovers(
    client: KefAsyncClient, speaker: FakeSpeaker, fast_reconnect: None
) -> None:
    gen = client.watch()
    assert (await nxt(gen)).volume == 30
    speaker.stop()
    assert await nxt(gen) is None
    speaker.store[VOLUME] = typed("i32_", 66)
    speaker.restart()
    state = await nxt(gen)  # full snapshot again
    assert state is not None and state.volume == 66
    speaker.set(VOLUME, typed("i32_", 67))  # and live updates resume
    assert (await nxt(gen)).volume == 67
    await gen.aclose()


async def test_watch_recreates_expired_queue_silently(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    gen = client.watch()
    await nxt(gen)
    speaker.store[VOLUME] = typed("i32_", 77)
    speaker.forget_queues()
    state = await nxt(gen)  # no None in between: straight to a fresh snapshot
    assert state is not None and state.volume == 77
    speaker.set(VOLUME, typed("i32_", 78))
    assert (await nxt(gen)).volume == 78
    await gen.aclose()


async def test_watch_without_reconnect_raises(client: KefAsyncClient, speaker: FakeSpeaker) -> None:
    gen = client.watch(reconnect=False)
    await nxt(gen)
    speaker.stop()
    with pytest.raises(KefConnectionError):
        await nxt(gen)


async def test_watch_offline_at_start_yields_none_then_snapshot(speaker: FakeSpeaker) -> None:
    speaker.stop()
    async with KefAsyncClient(speaker.host, transport="http", http_port=speaker.http_port) as c:
        gen = c.watch()
        assert await nxt(gen) is None  # told right away
        task = asyncio.ensure_future(nxt(gen))
        await asyncio.sleep(0.3)
        assert not task.done()  # retries silently: no more None
        speaker.restart()
        state = await task
        assert state is not None and state.volume == 30
        await gen.aclose()


async def test_two_watchers_each_see_every_change(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    g1, g2 = client.watch(), client.watch()
    await nxt(g1)
    await nxt(g2)
    for volume in (41, 42):
        speaker.set(VOLUME, typed("i32_", volume))
        assert (await nxt(g1)).volume == volume
        assert (await nxt(g2)).volume == volume
    await g1.aclose()
    await g2.aclose()


async def test_watch_ends_when_client_is_closed(speaker: FakeSpeaker) -> None:
    c = KefAsyncClient(speaker.host, transport="http", http_port=speaker.http_port)
    gen = c.watch()
    await nxt(gen)
    await c.aclose()
    async with asyncio.timeout(5):
        remaining = [item async for item in gen]
    assert all(item is None for item in remaining)  # at most the "lost" notification


async def test_watch_does_not_spin_when_poll_returns_immediately(
    client: KefAsyncClient, speaker: FakeSpeaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(const, "MIN_POLL_INTERVAL", 0.3)
    speaker.max_poll_wait = 0.0  # pollQueue answers [] at once
    gen = client.watch()
    await nxt(gen)
    speaker.clear_requests()
    task = asyncio.ensure_future(nxt(gen))
    await asyncio.sleep(1.0)
    task.cancel()
    polls = len(speaker.requests_to("/api/event/pollQueue"))
    assert 1 <= polls <= 5  # ~1 per 0.3 s instead of hundreds


async def test_watch_resyncs_when_applying_an_event_fails(
    client: KefAsyncClient, speaker: FakeSpeaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("unexpected")

    gen = client.watch()
    await nxt(gen)
    monkeypatch.setattr(client, "_apply_events", boom)
    speaker.set(VOLUME, typed("i32_", 50))
    state = await nxt(gen)  # resynced with get_state() instead of crashing
    assert state is not None and state.volume == 50
    await gen.aclose()


async def test_watch_undecodable_event_value_becomes_none(
    client: KefAsyncClient, speaker: FakeSpeaker
) -> None:
    gen = client.watch()
    await nxt(gen)
    speaker.emit({"path": VOLUME, "itemType": "update", "itemValue": typed("string_", "junk")})
    state = await nxt(gen)
    assert state is not None and state.volume is None
    await gen.aclose()


async def test_watch_survives_auth_errors(tls_speaker: FakeSpeaker, pki: PKI) -> None:
    ctx = create_ssl_context(ca_pem=pki.ca_pem)
    async with KefAsyncClient(
        tls_speaker.host, transport="https", ssl_context=ctx, https_port=tls_speaker.https_port
    ) as c:
        tls_speaker.fail_signed = 2  # modifyQueue: 401, then 401 after re-provisioning
        gen = c.watch()
        assert await nxt(gen) is None  # KefAuthError is handled like any outage
        state = await nxt(gen)
        assert state is not None and state.volume == 30
        await gen.aclose()


# --- blocking client -----------------------------------------------------------------------


def test_sync_watch_and_subscribe(speaker: FakeSpeaker) -> None:
    with KefClient(speaker.host, transport="http", http_port=speaker.http_port) as c:
        gen = c.watch()
        state = next(gen)
        assert state is not None and state.volume == 30
        speaker.set(VOLUME, typed("i32_", 44))
        state = next(gen)
        assert state is not None and state.volume == 44
        gen.close()

        queue = c.event_queue()
        assert queue.subscribe([MUTE]) is True
        assert queue.subscribe([SOURCE]) is False
        speaker.set(MUTE, typed("bool_", True))
        events = queue.poll(1)
        assert [(e.path, e.value) for e in events] == [(MUTE, True)]


def test_sync_watch_recovers(speaker: FakeSpeaker, fast_reconnect: None) -> None:
    with KefClient(speaker.host, transport="http", http_port=speaker.http_port) as c:
        gen = c.watch()
        assert next(gen) is not None
        timer = threading.Timer(0.2, speaker.restart)
        speaker.stop()
        timer.start()
        try:
            assert next(gen) is None
            state = next(gen)
        finally:
            timer.cancel()
        assert state is not None and state.volume == 30
        gen.close()
