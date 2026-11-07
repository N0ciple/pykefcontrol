# pykefcontrol

Python library to control **KEF W2-platform wireless speakers** over the local network, with both an
`asyncio` client and a blocking client sharing the same API.

> **Status: 1.0 alpha (`1.0.0a1`).** Version 1.0 is a full rewrite. It was rebuilt from the behaviour of
> the official KEF Connect app and validated so far on an LS50 Wireless II (firmware 4.1.192, HTTPS mode).
> Bug reports and feedback for other models / firmware (ideally with the output of
> `pykefcontrol diag <ip>`) are very welcome.
> Coming from 0.9? Read the [migration guide](MIGRATION.md).

Looking for Home Assistant? See [hass-kef-connector](https://github.com/N0ciple/hass-kef-connector).

## Supported speakers

| Speaker | Supported |
|---|---|
| KEF LS50 Wireless II | yes |
| KEF LS60 Wireless | yes |
| KEF LSX II | yes |
| KEF LSX II LT | yes |
| KEF XIO (soundbar) | yes |
| KEF LS LUXE | yes |
| Future W2-platform speakers | best effort (generic mode, every feature allowed; the speaker refuses what it cannot do) |
| KEF Coda W, KEF Muo | **no**: Bluetooth-only, they have no network API |
| First generation LS50 Wireless / LSX | **no**: use [aiokef](https://github.com/basnijholt/aiokef) |

## Installation

```shell
pip install pykefcontrol
# optional: network discovery of speakers (mDNS)
pip install "pykefcontrol[discovery]"
```

Requires Python 3.12 or newer. Runtime dependencies: `aiohttp` (async client) and `urllib3` (blocking client).

## Quick start

You need the speaker's IP address: check your router, or in the KEF Connect app go to settings, tap your
speaker, then the "i" icon. Giving the speaker a fixed IP (DHCP reservation) is recommended. You can also
[discover it](#discovery).

Blocking:

```python
from pykefcontrol import KefClient

with KefClient("192.168.1.20") as speaker:
    speaker.power_on()
    speaker.set_volume(30)
    print(speaker.get_player_state().track)
```

Asynchronous:

```python
import asyncio
from pykefcontrol import KefAsyncClient

async def main():
    async with KefAsyncClient("192.168.1.20") as speaker:
        await speaker.power_on()
        await speaker.set_volume(30)
        print((await speaker.get_player_state()).track)

asyncio.run(main())
```

`KefClient` is the blocking twin of `KefAsyncClient`: same method names, without `async`/`await`.
The only differences are `aclose()` which is `close()`, and async iterators (`watch()`, `events()`) which
are plain iterators. The constructor does **no network I/O**; the connection is made on the first request
(or by `connect()`). All examples below are written for the async client.

### Discovery

With the `discovery` extra installed:

```python
from pykefcontrol.discovery import discover, discover_blocking

for found in await discover(timeout=3.0):       # or discover_blocking()
    print(found.host, found.name, found.marketing_name, found.firmware)
```

`parse_service_info()` in the same module turns mDNS records (`_kef-info._tcp`) into a
`DiscoveredSpeaker` without any extra dependency, which is what a zeroconf config flow needs.

### Command line

The package installs a `pykefcontrol` command (also `python -m pykefcontrol`):

```shell
pykefcontrol discover                  # needs the [discovery] extra
pykefcontrol info 192.168.1.20         # model, firmware, transport (http/https), network
pykefcontrol state 192.168.1.20
pykefcontrol watch 192.168.1.20        # live updates
pykefcontrol volume 192.168.1.20 30
pykefcontrol power 192.168.1.20 on --source optical
pykefcontrol get 192.168.1.20 settings:/kef/host/modelName   # raw API
pykefcontrol --help
```

**Testing a model or firmware?** `pykefcontrol diag <ip>` probes HTTP (port 80) and HTTPS (port 4430),
the certificate, identity values, EQ format and the event queue, and prints a JSON report. Add `--write`
to also test writes (it re-writes the current volume, so nothing audible changes). Please attach the
report to bug reports.

## Feature tour

### Power and source

```python
from pykefcontrol import Source

await speaker.get_status()            # SpeakerStatus.POWER_ON / STANDBY / ...
await speaker.is_on()
await speaker.power_on()              # wakes up on the last known source (else Wi-Fi)
await speaker.power_on(Source.OPTICAL)
await speaker.set_source("tv")        # strings are accepted everywhere an enum is
await speaker.get_source()            # Source.STANDBY when the speaker is off
await speaker.power_off()
```

Like the official app, `power_on()` selects a real source: selecting a source wakes the speaker.
`reboot()` and `factory_reset()` also exist (the latter makes the speaker leave your network).

### Volume and mute

```python
await speaker.set_volume(30)                 # 0-100
await speaker.get_volume()
await speaker.volume_up()                    # by the speaker's volume step, returns the new volume
await speaker.volume_down(step=5)
await speaker.set_mute(True)                 # a real mute: the volume is left untouched
await speaker.get_mute()
await speaker.set_default_volume(25, source=Source.TV)   # volume applied on wake-up (experimental)
```

### Playback

```python
from pykefcontrol import PlayMode

await speaker.play()          # idempotent: does nothing if already playing
await speaker.pause()         # idempotent: does nothing if not playing
await speaker.play_pause()    # toggle
await speaker.stop()
await speaker.next_track()
await speaker.previous_track()
await speaker.seek(90_000)    # milliseconds
await speaker.set_play_mode(PlayMode.SHUFFLE_REPEAT_ALL)
await speaker.get_play_mode()

player = await speaker.get_player_state()
player.state, player.is_playing, player.duration_ms
player.track                  # Track: title, artist, album, cover_url, codec, sample_rate, ...
player.controls               # PlayerControls: which commands the current source allows
await speaker.get_play_position()   # ms
```

`PlayMode.from_flags(shuffle=True, repeat="all")` builds a mode from flags, and the mode has `.shuffle`
and `.repeat` properties.

`play_url(url, title=None)` plays an audio stream URL (internet radio) like the app's custom radios.
It is **experimental**.

### Device information and capabilities

```python
info = await speaker.get_device_info()    # name, model, serial_number, mac_address, firmware, ...
await speaker.get_name(); await speaker.set_name("Living room")
await speaker.get_mac_address()
net = await speaker.get_network_info()    # wired / wireless interface, SSID, signal_level, ip_address

caps = await speaker.get_capabilities()   # detected once, then cached
caps.model                                # SpeakerModel.LS50_WIRELESS_II, ...
caps.sources                              # sources this model offers
caps.supports(Feature.EQ_PROFILE)         # from pykefcontrol import Feature
```

For an unknown (future) model, `supports()` returns `True` and lets the speaker decide.

### State snapshot

```python
state = await speaker.get_state()
state.status, state.source, state.volume, state.muted, state.play_mode
state.player, state.track, state.name
state.position_ms, state.position_updated_at   # extrapolate the position from these
state.is_on
```

`get_state(extra_paths=[...])` also reads additional API paths into `state.extra`.
`SpeakerState` is an immutable dataclass; use `state.replace(...)` to derive a copy.

### Live updates with `watch()`

`watch()` is the recommended way to follow a speaker: it keeps one long-poll request open on the
speaker's event queue (push, no polling interval) and yields a fresh `SpeakerState` on every change.

```python
async for state in speaker.watch():
    if state is None:
        print("speaker unavailable")
    else:
        print(state.volume, state.track)
```

- The first item is a full snapshot, then a new state is yielded after each change.
- `None` means the speaker is **unavailable** (also yielded first if it is offline when `watch()` starts).
  The client then reconnects by itself with exponential back-off (1 s up to 30 s), re-subscribes, and
  yields a full snapshot again when it is back. An expired event queue is recreated silently.
  Pass `reconnect=False` to get exceptions instead.
- Each `watch()` uses its own event queue, so several consumers can watch the same client. The
  iteration ends when the client is closed.
- `track_position=True` also follows the play time (one event per second while playing). By default the
  position is only refreshed when the player changes; extrapolate from `position_ms` and
  `position_updated_at`.
- `extra_paths=[...]` follows additional API paths, exposed in `state.extra`.

The blocking client offers the same thing as a plain `for state in speaker.watch():` loop.

For lower-level control, use the event queue directly:

```python
queue = speaker.event_queue()                                    # no I/O yet
created = await queue.subscribe([paths.VOLUME, paths.MUTE])      # True if a new queue was created
events = await queue.poll(timeout=25)                            # list[Event], [] on timeout
async for event in speaker.events([paths.VOLUME]):               # own queue, subscribe + poll forever
    print(event.path, event.value)
```

These raise on errors (no automatic reconnection). `poll()` returns every event, in arrival order. The
speaker does not replay current values: read the state after subscribing.

### Equalizer / DSP

```python
from pykefcontrol import BassExtension

profile = await speaker.get_eq_profile()     # EqProfile, in physical units (dB, Hz...)
profile.treble, profile.bass_extension, profile.desk_mode, profile.subwoofer_gain

await speaker.update_eq_profile(treble=1.5, bass_extension=BassExtension.EXTRA)  # read-modify-write
await speaker.set_eq_profile(profile.replace(wall_mode=True))                    # whole profile
await speaker.reset_eq_profile()                                                  # factory DSP settings

await speaker.get_eq_version()               # 2 (values) or 1 (indices, old LS50 Wireless II firmware)
descriptors = await speaker.get_eq_descriptors()   # ranges/choices advertised by the speaker (v2)
```

The profile format differs between firmware generations (v1 stores indices, v2 stores real values); the
library detects it and converts transparently, so your code always sees an `EqProfile`. Values are
validated before being written (`validate=False` to skip).

### Settings catalogue

Most speaker settings are described declaratively in `Settings` and read/written with typed, validated
calls:

```python
from pykefcontrol import Settings, StandbyMode

await speaker.get_setting(Settings.STARTUP_TONE)                    # bool
await speaker.set_setting(Settings.STARTUP_TONE, False)
await speaker.set_setting(Settings.STANDBY_MODE, StandbyMode.MINUTES_30)
await speaker.set_setting(Settings.MAXIMUM_VOLUME, 80)              # range-checked
await speaker.get_setting(Settings.FIRMWARE_VERSION)                # read-only settings raise on write
```

The catalogue covers identity, volume limits and defaults, standby and wake-up behaviour, LEDs, top panel,
USB charging, cable mode, subwoofer and master channel, IR remote, favourite/EQ buttons, scheduled reboot,
language, and more. Browse `Settings` (and `Setting.description`) in your editor or REPL. A `Setting` can
be unsupported by your model or firmware; the speaker then answers with `KefApiError`.

### Raw API

For anything not covered above, the generic calls talk to the speaker's JSON API directly:

```python
from pykefcontrol import paths, ValueType

await speaker.get_data(paths.VOLUME)                      # raw typed value: {"type": "i32_", "i32_": 30}
await speaker.get_value("settings:/mediaPlayer/mute")     # decoded: False
await speaker.set_value(paths.VOLUME, ValueType.I32, 35)
await speaker.activate("powermanager:goReboot")           # trigger an action node
await speaker.get_rows(paths.PLAY_QUEUE, 0, 19)          # list rows of a container
```

`pykefcontrol.paths` holds the known API path constants. `set_data()` is the untyped variant of
`set_value()`.

### Bluetooth

```python
state = await speaker.get_bluetooth_state()   # connected, discoverable, pairable, pairing_code...
await speaker.bluetooth_pairing()             # make the speaker discoverable
await speaker.bluetooth_disconnect()
```

## Connection and security

Recent firmware serves its API over **HTTPS on port 4430**, with a certificate issued by a private KEF
root CA (the library embeds it, as `KEF_ROOT_CA_PEM`, and trusts nothing else for the speaker). Older
firmware only speaks plain HTTP on port 80. Write requests to the HTTPS API must be signed with an HMAC
`Authorization` header; the library creates a user on the speaker and signs requests automatically.

```python
KefAsyncClient(host, transport="auto")    # default: try HTTPS, fall back to HTTP
KefAsyncClient(host, transport="https")   # HTTPS only
KefAsyncClient(host, transport="http")    # HTTP only (legacy firmware, troubleshooting)
speaker.is_secure                          # True / False, None before the first request
```

In `auto` mode the client keeps retrying HTTPS periodically while it uses HTTP.

An honest note on security: the default credentials are the same for every user of the official app, and
the speaker accepts new users without authentication. The signing scheme therefore identifies *clients* to
the speaker; it is **not a security boundary on your LAN**. Anyone on your network can control your
speaker, as with the official app. Keep it off untrusted networks.

Other options:

- `verify_ssl=False` disables certificate verification (troubleshooting only).
- `credentials=Credentials(username, password)` uses a different speaker user.
- `timeout=` (seconds, default 10) sets the timeout of ordinary requests; `http_port=`/`https_port=`
  override the ports.
- `model="LSXII"` tells the client the model up front (skips detection for capabilities).

**IP addresses vs host names.** Speaker certificates only list IP addresses. With an IP address the
certificate is fully verified (chain and address). With a host name the library still verifies the chain
against the KEF CA but skips the hostname match. An IP address (ideally reserved in your DHCP server)
is recommended.

**Blocking calls in the event loop.** Building an `ssl.SSLContext` loads certificates from disk/memory,
which some frameworks (Home Assistant) flag as blocking I/O. The async client builds it in an executor
for you (and caches it); if you prefer to control this, build it yourself and pass it in:

```python
ctx = await loop.run_in_executor(None, create_ssl_context)   # from pykefcontrol import create_ssl_context
speaker = KefAsyncClient(host, ssl_context=ctx)
```

## Home Assistant and other frameworks

- Inject the shared `aiohttp.ClientSession`: `KefAsyncClient(host, session=session)`. A session you
  provide is **never closed** by the library; only a session it created itself is.
- Use `get_state()` for the first refresh and `watch()` in a background task for `local_push` updates;
  a `None` from `watch()` means "unavailable".
- Use `get_capabilities().sources` instead of a hard-coded source list.
- Build the SSL context in an executor (see above) if your framework forbids blocking calls in the loop.
- `pykefcontrol.discovery.parse_service_info()` supports zeroconf-based config flows.

## Errors

Every exception derives from `KefError`:

```
KefError
├── KefConnectionError      speaker unreachable (refused, DNS, TLS...)
│   └── KefTimeoutError     no answer in time
├── KefAuthError            credentials rejected
├── KefApiError             HTTP error status (.status, .message, .path)
├── KefProtocolError        unintelligible answer
└── KefUnsupportedError     feature not supported by this speaker / firmware
```

Invalid arguments (a volume of 150, a wrongly-typed setting value) raise `ValueError` / `TypeError`
before anything is sent.

## Development

The project uses [uv](https://docs.astral.sh/uv/) (and a Nix flake: `nix develop` provides uv).

```shell
uv sync                         # create the environment with dev dependencies
uv run pytest                   # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy                     # strict typing
uv run python scripts/gen_sync.py          # regenerate the sync client
uv run python scripts/gen_sync.py --check  # what CI runs: fail if it is stale
```

The asynchronous client in `pykefcontrol/_async/` is the single source of truth: the blocking client in
`pykefcontrol/_sync/` is **generated** from it by `scripts/gen_sync.py`. Never edit `_sync/client.py` or
`_sync/transport.py` by hand; edit the async version and regenerate.

## License

MIT, see [LICENSE](LICENSE). pykefcontrol is an independent project, not affiliated with or endorsed by
KEF.
