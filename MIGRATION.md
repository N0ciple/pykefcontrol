# Migrating from 0.9 to 1.0

Version 1.0 is a full rewrite with a clean break: there are no compatibility aliases and the
`pykefcontrol.kef_connector` module no longer exists. This guide maps every public name of 0.9.3 to its
replacement.

Requirements changed too: **Python 3.12 or newer**, and `requests` is replaced by `urllib3` (the async
client still uses `aiohttp`).

```diff
-from pykefcontrol.kef_connector import KefConnector, KefAsyncConnector
+from pykefcontrol import KefClient, KefAsyncClient
```

## Quick before / after

```python
# 0.9
from pykefcontrol.kef_connector import KefConnector
speaker = KefConnector("192.168.1.20")     # made a network request!
speaker.power_on()
speaker.volume = 30
print(speaker.get_song_information()["title"])
```

```python
# 1.0
from pykefcontrol import KefClient
with KefClient("192.168.1.20") as speaker: # no I/O until the first call
    speaker.power_on()
    speaker.set_volume(30)
    track = speaker.get_player_state().track
    print(track.title if track else None)
```

Async, 0.9 versus 1.0:

```python
# 0.9
speaker = KefAsyncConnector("192.168.1.20", session=session)
volume = await speaker.volume
await speaker.set_volume(30)
await speaker.close_session()             # also closed YOUR session

# 1.0
speaker = KefAsyncClient("192.168.1.20", session=session)
volume = await speaker.get_volume()
await speaker.set_volume(30)
await speaker.aclose()                     # your session is left open
```

## Methods and properties

`KefConnector` and `KefAsyncConnector` are mapped together; "(async)" marks names that only existed on the
async class. In 0.9 the async class exposed properties as awaitables (`await speaker.volume`); in 1.0
everything is a method on both clients.

### Construction and lifecycle

| 0.9 | 1.0 |
|---|---|
| `KefConnector(host, model=None)` | `KefClient(host, *, model=None, transport="auto", verify_ssl=True, ssl_context=None, credentials=None, timeout=10.0, ...)`. No network I/O in the constructor. `model=` is now only used for capabilities. |
| `KefAsyncConnector(host, session=None, model=None)` | `KefAsyncClient(host, *, session=None, model=None, ...)`. An injected session is never closed. |
| `close_session()` (async) | `await aclose()`, or `async with KefAsyncClient(...)`. Closes only a session the client created itself. The blocking client has `close()` and `with`. |
| `resurect_session()` (async) | Removed. The client lazily creates a session when needed. |

### Power and source

| 0.9 | 1.0 |
|---|---|
| `power_on()` | `power_on(source=None)`. Selects a real source (last known, else Wi-Fi) like the official app, instead of writing `powerOn`. |
| `shutdown()` | `power_off()` |
| `status` (property, `"powerOn"` / `"standby"`) | `get_status()` returns a `SpeakerStatus` (`POWER_ON`, `STANDBY`, `NETWORK_SETUP`, `FIRMWARE_UPGRADE`). `is_on()` returns a bool. |
| `status = "powerOn"` / `set_status(...)` (async) | `power_on()` / `power_off()`. |
| `source` (property) | `get_source()` returns a `Source` (`Source.STANDBY` when off). |
| `source = "wifi"` / `set_source("wifi")` (async) | `set_source(Source.WIFI)` (a plain string still works). Selecting a source wakes the speaker. |

### Volume and mute

| 0.9 | 1.0 |
|---|---|
| `volume` (property) | `get_volume()` |
| `volume = 30` / `set_volume(30)` | `set_volume(30)` |
| `mute()` (sets volume to 0) | `set_mute(True)`: a real mute, the volume is untouched. |
| `unmute()` (restores previous volume) | `set_mute(False)`. `get_mute()` reads the state. |
| (none) | New: `volume_up(step=None)`, `volume_down(step=None)`, `set_default_volume(volume, source=None)` |

### Playback and track information

| 0.9 | 1.0 |
|---|---|
| `toggle_play_pause()` | `play_pause()` (toggle). New idempotent `play()` and `pause()`, plus `stop()`. |
| `next_track()`, `previous_track()` | unchanged |
| `is_playing` (property) | `(get_player_state()).is_playing` |
| `get_song_information()` returns a dict (`title`, `artist`, `album`, `album_artist`, `cover_url`, `service_id`) | `get_player_state().track`, a `Track` with the same fields as attributes (`title`, `artist`, `album`, `album_artist`, `cover_url`, `service_id`), or `None` when nothing is loaded. |
| `get_song_information(song_data)` (parse a given payload) | `PlayerState.from_api(raw)` |
| `get_audio_codec_information()` returns a dict (`codec`, `sampleFrequency`, `streamSampleRate`, ...) | Fields of the `Track`: `codec`, `sample_rate`, `bits_per_sample`, `channels`, `bit_rate`, `service_id`. Errors are no longer swallowed. |
| `song_length` (property, ms) | `get_player_state().duration_ms` (or `track.duration_ms`) |
| `song_status` (property, position in ms) | `get_play_position()` |
| `_get_player_data()` (private, raw dict) | `get_data(paths.PLAY_DATA)` (raw) or `get_player_state()` (typed; the original payload is in `.raw`) |
| (none) | New: `seek(position_ms)`, `get_play_mode()`, `set_play_mode()`, `play_url()` (experimental) |

### Device information

| 0.9 | 1.0 |
|---|---|
| `mac_address` (property) | `get_mac_address()` (also in `get_device_info().mac_address`) |
| `speaker_name` (property) | `get_name()`; new `set_name(name)` |
| `speaker_model` / `get_speaker_model()` (async) | `get_device_info().model` (a `SpeakerModel`) or `get_capabilities().model` |
| `firmware_version` / `get_firmware_version()` (async) | `get_device_info().firmware` (parsed `FirmwareVersion`) or `.firmware_version` (raw string from the speaker, `None` when unreadable). The old value was derived from the release text (e.g. `V27100`); it is available as `.release_text`. |
| `get_wifi_information()` returns a dict (`signalLevel`, `ssid`, `frequency`, `bssid`) | `get_network_info().wireless`, a `NetworkInterface` with `signal_level`, `ssid`, `frequency`, `bssid`, `channel`. Also `.wired` and `.ip_address`. |
| (none) | New: `get_capabilities()`, `reboot()`, `factory_reset()`, `get_bluetooth_state()`, EQ methods, `get_setting()` / `set_setting()` |

### Generic API access

| 0.9 | 1.0 |
|---|---|
| `get_request(path, roles="value")` | `get_data(path, roles="value")` (raw), `get_value(path)` (decoded). The old return value was the full JSON list; `get_data` returns its first element. |
| `_set_data(payload)` (private) | `set_data(path, value)`, `set_value(path, value_type, value)` and `activate(path, value=None)` |
| `_track_control(command)` (private) | Use the playback methods. |
| (none) | New: `get_rows(path, start, end)`, and the `pykefcontrol.paths` constants |

### Polling

| 0.9 | 1.0 |
|---|---|
| `poll_speaker(timeout=10, song_status=False, poll_song_status=False)` | `watch()`: an iterator of `SpeakerState` that handles the event queue and reconnection. `poll_song_status=True` becomes `watch(track_position=True)`. Low level: `event_queue()` (`subscribe()`, `poll(timeout)`), `events()`. |
| `get_polling_queue(...)` (async, public) / `_get_polling_queue` | `queue = client.event_queue(); queue.subscribe(paths)` |
| `parse_events(events)` | Not needed. `EventQueue.poll()` returns typed `Event` objects and `watch()` applies them to a `SpeakerState`. |
| `polling_queue`, `last_polled`, `_previous_poll_song_status`, `previous_volume` (attributes) | Removed (internal). |

Keys of the dictionary returned by `poll_speaker()` and where to find them now:

| 0.9 key | 1.0 (`SpeakerState` field) |
|---|---|
| `source` | `state.source` |
| `volume` | `state.volume` |
| `mute` | `state.muted` |
| `speaker_status` | `state.status` |
| `device_name` | `state.name` |
| `status` (playback) | `state.player.state` |
| `song_info` | `state.track` (`state.player.track`) |
| `song_length` | `state.player.duration_ms` |
| `song_status` | `state.position_ms` (see `position_updated_at`) |
| `other` | `state.extra`, via `watch(extra_paths=[...])` |

Two differences to be aware of. `poll_speaker()` returned only what changed, whereas `watch()` yields a
complete `SpeakerState` each time, so compare with the previous state if you need a diff. And `watch()`
yields `None` when the speaker becomes unreachable, then a full snapshot when it returns.

```python
# 0.9
while True:
    changes = await speaker.poll_speaker(timeout=10)
    if "volume" in changes:
        print(changes["volume"])

# 1.0
async for state in speaker.watch():
    if state is None:
        print("speaker unavailable")
    else:
        print(state.volume)
```

## Behavioural changes

- **No I/O in the constructor.** `KefConnector(host)` used to read the volume; creating a client now never
  fails and works offline. Connection errors appear on the first call (or `connect()`).
- **POST everywhere, with the `"role"` key.** The per-model GET/POST logic (`_POST_MODELS`,
  `_MODEL_ALIASES`) is gone, and so is the need to pass `model=` for it.
- **HTTPS first.** The client talks HTTPS on port 4430 with signed requests on recent firmware and falls
  back to HTTP on port 80. If a firewall blocks 4430 you can force `transport="http"`.
- **`power_on()` selects a source**, so the speaker really wakes up on a usable input.
- **Mute is a real mute.** `set_mute(True)` leaves the volume alone.
- **Enums instead of strings.** `Source`, `SpeakerStatus`, `PlaybackState`, `PlayMode`... are `StrEnum`s:
  `state.source == "wifi"` still works, `str(Source.WIFI) == "wifi"`, and functions accepting an enum also
  accept the string. Note that the optical source is `optical` (some 0.9 docstrings said `optic`).
- **Exceptions.** Everything raised by the library derives from `KefError`:
  `KefConnectionError` / `KefTimeoutError` (unreachable), `KefApiError` (HTTP error, with `.status`),
  `KefAuthError`, `KefProtocolError`, `KefUnsupportedError`. Errors that 0.9 swallowed (codec and Wi-Fi
  information) now propagate; invalid arguments raise `ValueError` / `TypeError`.
- **Sessions you inject are never closed.** The library only closes the session it created.
- **Timeouts everywhere.** Both clients apply `timeout` (default 10 s) to ordinary requests. `watch()`
  uses a 25 s long poll.
- **Typed results.** Dictionaries are replaced by dataclasses; the raw payloads remain available through
  `.raw` and the generic `get_data()`.

## Home Assistant migration example

A typical 0.9 `media_player` that polled the speaker:

```python
# 0.9
from pykefcontrol.kef_connector import KefAsyncConnector

class KefMediaPlayer(MediaPlayerEntity):
    def __init__(self, hass, host):
        self._speaker = KefAsyncConnector(host, session=async_get_clientsession(hass))

    async def async_update(self):
        self._volume = await self._speaker.volume / 100
        self._source = await self._speaker.source
        self._is_playing = await self._speaker.is_playing
        self._info = self._speaker.get_song_information()

    async def async_mute_volume(self, mute):
        await (self._speaker.mute() if mute else self._speaker.unmute())

    async def async_turn_on(self):
        await self._speaker.power_on()

    async def async_turn_off(self):
        await self._speaker.shutdown()
```

The 1.0 version uses push updates instead of polling (`local_push`), and no longer needs to guess the
source list:

```python
# 1.0
from pykefcontrol import KefAsyncClient, create_ssl_context

class KefMediaPlayer(MediaPlayerEntity):
    _attr_should_poll = False

    async def async_added_to_hass(self):
        self._speaker = KefAsyncClient(self._host, session=async_get_clientsession(self.hass))
        self._sources = [str(s) for s in (await self._speaker.get_capabilities()).sources]
        self._task = self.hass.async_create_background_task(self._follow(), "kef_watch")

    async def async_will_remove_from_hass(self):
        self._task.cancel()
        await self._speaker.aclose()          # the shared HA session stays open

    async def _follow(self):
        async for state in self._speaker.watch():
            self._attr_available = state is not None
            if state is not None:
                self._attr_volume_level = state.volume / 100
                self._attr_is_volume_muted = state.muted
                self._attr_source = str(state.source)
                self._attr_media_title = state.track.title if state.track else None
            self.async_write_ha_state()

    async def async_mute_volume(self, mute):
        await self._speaker.set_mute(mute)

    async def async_turn_on(self):
        await self._speaker.power_on()

    async def async_turn_off(self):
        await self._speaker.power_off()
```

Notes for integrations:

- `get_state()` provides the initial refresh (for example in a config flow or coordinator), and
  `watch()` keeps it up to date.
- To follow the playback position, use `state.position_ms` and `state.position_updated_at`, or
  `watch(track_position=True)`.
- If Home Assistant reports blocking calls when the TLS context is created, build it once in an executor
  with `create_ssl_context()` and pass it as `ssl_context=`.
- Use `pykefcontrol.discovery.parse_service_info()` to support zeroconf discovery.
