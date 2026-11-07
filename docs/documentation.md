# 📖 pykefcontrol documentation

This is the full guide to pykefcontrol 1.0. For a quick overview, see the [README](../README.md). Coming
from 0.9? Read the [migration guide](../MIGRATION.md) first.

- [🚀 Getting started](#-getting-started)
- [🔌 Connecting to a speaker](#-connecting-to-a-speaker)
- [🎚️ Everyday control](#️-everyday-control)
- [🎛️ Equalizer and DSP](#️-equalizer-and-dsp)
- [⚙️ Speaker settings](#️-speaker-settings)
- [📡 Live updates](#-live-updates)
- [🧰 Raw API](#-raw-api)
- [🔎 Discovery and command line](#-discovery-and-command-line)
- [📦 Data reference](#-data-reference)
- [⚠️ Errors](#️-errors)
- [💡 Good to know](#-good-to-know)

## 🚀 Getting started

### Installation

```shell
pip install pykefcontrol
pip install "pykefcontrol[discovery]"   # optional: find speakers on the network
```

Python 3.12 or newer is required.

### Supported speakers

Every KEF speaker of the W2 platform: **LS50 Wireless II, LS60 Wireless, LSX II, LSX II LT, XIO and
LS LUXE**. Future W2 models should work out of the box. The Coda W and Muo are Bluetooth-only and the
first generation LS50 Wireless / LSX use a different API ([aiokef](https://github.com/basnijholt/aiokef)).

### Find the IP address of your speaker

Look in your router, or in the KEF Connect app: settings ⚙️ → your speaker → the circled "i". You can
also let pykefcontrol [find it for you](#discovery). Reserving a fixed IP for the speaker in your router is
a good idea.

### First steps

pykefcontrol has two clients with exactly the same methods:

- `KefClient` for regular scripts (blocking calls),
- `KefAsyncClient` for `asyncio` programs (`await` every call).

```python
from pykefcontrol import KefClient

with KefClient("192.168.1.20") as speaker:
    speaker.power_on()
    speaker.set_volume(30)
    print(speaker.get_name())
    # -> 'Living room'
```

```python
import asyncio
from pykefcontrol import KefAsyncClient

async def main():
    async with KefAsyncClient("192.168.1.20") as speaker:
        await speaker.power_on()
        await speaker.set_volume(30)

asyncio.run(main())
```

Creating a client does not touch the network. The connection happens on the first call (or when you call
`connect()`). Close the client when you are done, with the `with` block or by calling `close()`
(`await aclose()` for the async client).

**All examples below use the async client.** For `KefClient`, simply drop the `await`.

## 🔌 Connecting to a speaker

### Constructor options

```python
KefAsyncClient(
    "192.168.1.20",
    session=None,          # aiohttp.ClientSession to reuse (async client only)
    transport="auto",      # "auto", "https" or "http"
    credentials=None,      # Credentials(username, password) of the speaker user
    verify_ssl=True,       # set to False only for troubleshooting
    ssl_context=None,      # a ready-made ssl.SSLContext
    timeout=10.0,          # seconds, for ordinary requests
    model=None,            # e.g. "LS50WII" if you already know it
    http_port=80,
    https_port=4430,
)
```

None of these are needed in normal use: `KefAsyncClient("192.168.1.20")` is enough.

### HTTP or HTTPS?

Recent firmware exposes the API over **HTTPS on port 4430**, older firmware only over **HTTP on port 80**.
With `transport="auto"` (the default) the client tries HTTPS first and falls back to HTTP. Once HTTPS has
worked it never goes back to HTTP. While on HTTP, it tries HTTPS again every 5 minutes, so a firmware
update is picked up without restarting.

```python
speaker.is_secure
# -> True (HTTPS), False (HTTP) or None before the first request
```

On HTTPS, the speaker's certificate is checked against KEF's own certificate authority, which is bundled
with the library. Write requests are signed, and the library registers its user on the speaker by itself.
You have nothing to configure.

> This does not make your speaker private: anyone on your local network can control it, exactly as with
> the official app.

Use an **IP address** rather than a host name when you can: the certificates only list IP addresses, so
with a host name the certificate chain is still checked but the name cannot be.

### Sharing a session (Home Assistant and co.)

```python
speaker = KefAsyncClient(host, session=async_get_clientsession(hass))
```

A session you pass in is never closed by the library. If your framework forbids blocking calls in the
event loop, build the SSL context in an executor and pass it in:

```python
from pykefcontrol import create_ssl_context

ctx = await hass.async_add_executor_job(create_ssl_context)
speaker = KefAsyncClient(host, session=session, ssl_context=ctx)
```

## 🎚️ Everyday control

### Power and source

```python
from pykefcontrol import Source

await speaker.get_status()
# -> SpeakerStatus.POWER_ON (or STANDBY, NETWORK_SETUP, FIRMWARE_UPGRADE)
await speaker.is_on()
# -> True

await speaker.power_on()                  # last used source, or Wi-Fi
await speaker.power_on(Source.OPTICAL)
await speaker.power_off()                 # standby

await speaker.get_source()
# -> Source.WIFI (Source.STANDBY when the speaker is off)
await speaker.set_source(Source.TV)       # also wakes the speaker up
await speaker.set_source("tv")            # strings work too
```

Sources: `wifi`, `bluetooth`, `tv`, `optical`, `coaxial`, `analog`, `usb`. Not every model has every
input; `(await speaker.get_capabilities()).sources` gives the list for yours.

`reboot()` restarts the speaker. `factory_reset()` erases everything, and the speaker leaves your network.

### Volume and mute

```python
await speaker.get_volume()
# -> 35
await speaker.set_volume(30)              # 0 to 100
await speaker.volume_up()                 # by the speaker's volume step, returns the new volume
# -> 31
await speaker.volume_down(step=5)
# -> 26

await speaker.set_mute(True)
await speaker.get_mute()
# -> True

await speaker.set_default_volume(25)                  # volume when waking up (experimental)
await speaker.set_default_volume(40, source="tv")     # per source
```

### Playback

```python
await speaker.play()                      # does nothing if already playing
await speaker.pause()                     # does nothing if not playing
await speaker.play_pause()                # toggle
await speaker.stop()
await speaker.next_track()
await speaker.previous_track()
await speaker.seek(90_000)                # in milliseconds
await speaker.get_play_position()
# -> 93512
```

Shuffle and repeat:

```python
from pykefcontrol import PlayMode

await speaker.set_play_mode(PlayMode.SHUFFLE_REPEAT_ALL)
await speaker.set_play_mode(PlayMode.from_flags(shuffle=True, repeat="one"))   # "off", "one", "all"

mode = await speaker.get_play_mode()
mode.shuffle, mode.repeat
# -> (True, 'all')
```

What is playing:

```python
player = await speaker.get_player_state()
player.state                              # PlaybackState.PLAYING, PAUSED, STOPPED...
player.is_playing
# -> True
player.track.title, player.track.artist, player.track.album, player.track.cover_url
# -> ('Teardrop', 'Massive Attack', 'Mezzanine', 'https://...')
player.controls.next, player.controls.seek   # what the current source allows
# -> (True, False)
```

`play_url(url, title="My radio")` plays an internet radio stream, like the custom radios of the app.
It is **experimental**.

### Bluetooth

```python
state = await speaker.get_bluetooth_state()
state.connected, state.pairable
await speaker.bluetooth_pairing()         # make the speaker discoverable
await speaker.bluetooth_disconnect()
```

### Device information

```python
info = await speaker.get_device_info()
info.name, info.model, info.serial_number, info.mac_address
# -> ('Living room', SpeakerModel.LS50_WIRELESS_II, 'LSW0123456789ABC', '84:17:15:00:00:01')
info.firmware.major, info.firmware.minor, info.firmware.patch
# -> (4, 1, 192)

await speaker.set_name("Living room")

net = await speaker.get_network_info()
net.ip_address, net.active.ssid, net.active.signal_level
```

### Capabilities

Models don't all have the same inputs and options. `get_capabilities()` tells you what yours supports:

```python
from pykefcontrol import Feature

caps = await speaker.get_capabilities()
caps.model
# -> SpeakerModel.LS50_WIRELESS_II
caps.sources
# -> (Source.WIFI, Source.BLUETOOTH, Source.TV, Source.OPTICAL, Source.COAXIAL, Source.ANALOG)
caps.supports(Feature.CABLE_MODE)
# -> True
```

For a model the library does not know yet, `supports()` always answers `True`, and the speaker refuses
what it can't do.

## 🎛️ Equalizer and DSP

All the settings of the "EQ" screen of the KEF Connect app live in a single **EQ profile**. You read it,
change what you want, and write it back.

```python
from pykefcontrol import BassExtension

profile = await speaker.get_eq_profile()
profile.treble, profile.bass_extension
# -> (0.0, BassExtension.STANDARD)

# change a few fields, keep the rest
await speaker.update_eq_profile(treble=1.5, bass_extension=BassExtension.EXTRA, desk_mode=True)

# or write a whole profile
await speaker.set_eq_profile(profile.replace(wall_mode=True, wall_mode_setting=-2.0))

# back to KEF's defaults
await speaker.reset_eq_profile()
```

### Profile fields

Values are in real units: dB, Hz.

| Field | Values | Notes |
|---|---|---|
| `desk_mode`, `desk_mode_setting` | bool, -10 to 0 dB (step 0.5) | speakers on a desk |
| `wall_mode`, `wall_mode_setting` | bool, -10 to 0 dB (step 0.5) | speakers close to a wall |
| `wall_mounted` | bool | |
| `treble` | -3 to +3 dB (step 0.25) | |
| `bass_extension` | `less`, `standard`, `extra` | |
| `balance` | -30 (left) to +30 (right) | |
| `phase_correction` | bool | |
| `audio_polarity` | `normal`, `inverted` | |
| `high_pass_mode`, `high_pass_freq` | bool, 50 to 120 Hz | cuts the bass of the speakers when a sub is used |
| `subwoofer_out` | bool | |
| `subwoofer_count` | 0 to 2 | |
| `subwoofer_gain` | -10 to +10 dB (step 1) | |
| `sub_out_low_pass_freq` | 40 to 250 Hz | |
| `subwoofer_polarity` | `normal`, `inverted` | |
| `subwoofer_preset` | `custom`, `kc62`, `kf92`, `kube8b`, `kube10b`, `kube12b`, `kube15mie`, `t2`, `other` | |
| `sub_stereo` | bool | two subwoofers in stereo |
| `is_kw1` | bool | KW1 wireless subwoofer adapter |
| `sound_profile` | `default`, `music`, `movie`, `night`, `dialogue`, `direct` | XIO |
| `expert_mode` | bool | as in the app |
| `profile_name`, `profile_id` | str | empty for the default profile |

Values are checked before being sent and a `ValueError` is raised if one is out of range
(`set_eq_profile(..., validate=False)` to skip). The ranges are the ones your speaker advertises when it
does (EQ v2), else the app's defaults (the table above):

```python
ranges = await speaker.get_eq_ranges()
ranges["treble"]
# -> EqRange(minimum=-3.0, maximum=3.0, step=0.25, default=0.0)
descriptors = await speaker.get_eq_descriptors()   # raw descriptors, incl. the allowed choices
```

### Subwoofer presets

Choosing a KEF subwoofer in the app also adjusts the crossover frequencies and the gain. To get the same
result, use `apply_subwoofer_preset()`:

```python
from pykefcontrol import SubwooferPreset
from pykefcontrol.eq import apply_subwoofer_preset

profile = await speaker.get_eq_profile()
await speaker.set_eq_profile(apply_subwoofer_preset(profile, SubwooferPreset.KC62, "LS50WII"))
```

### Things to know

- The speaker applies a new profile a few tens of milliseconds after accepting it. `set_eq_profile()`
  waits until the change is visible, so you can read it back right away (`wait=False` to skip this).
- Older LS50 Wireless II firmware stores the profile in a different format. The library handles both;
  `get_eq_version()` tells you which one your speaker uses (1 or 2).
- Fields the library doesn't know about (new firmware) are kept in `profile.extra` and written back
  untouched.
- A few DSP options live outside the profile, in the [settings](#️-speaker-settings):
  `SUBWOOFER_OUT_V2`, `SUBWOOFER_GAIN_V2`, `DIALOGUE_MODE`, and for the XIO `PREFER_VIRTUAL_X` and
  `WIRELESS_REAR_GAIN`.

## ⚙️ Speaker settings

The other options of the app (standby, LEDs, remote...) are listed in `Settings`. Each entry knows its
type and limits, so values are checked before being sent.

```python
from pykefcontrol import Settings, StandbyMode

await speaker.get_setting(Settings.STANDBY_MODE)
# -> StandbyMode.MINUTES_30
await speaker.set_setting(Settings.STANDBY_MODE, StandbyMode.NEVER)
await speaker.set_setting(Settings.STARTUP_TONE, False)
await speaker.set_setting(Settings.MAXIMUM_VOLUME, 80)
await speaker.set_setting(Settings.MAXIMUM_VOLUME, 150)
# -> ValueError: settings:/kef/host/maximumVolume: 150 > maximum 100
```

| Topic | Settings |
|---|---|
| Identity (read-only) | `MODEL_NAME`, `SERIAL_NUMBER`, `FIRMWARE_VERSION`, `HARDWARE_VERSION`, `RELEASE_TEXT`, `MAC_ADDRESS`, `DEVICE_NAME` (writable) |
| Volume | `MAXIMUM_VOLUME`, `VOLUME_LIMIT`, `VOLUME_STEP`, `VOLUME_DISPLAY`, `STANDBY_DEFAULT_VOLUME`, `DEFAULT_VOLUME_*` (read-only, use `set_default_volume()`) |
| Power | `STANDBY_MODE`, `WAKE_UP_SOURCE`, `AUTO_SWITCH_TO_TV`, `STARTUP_TONE`, `SCHEDULED_REBOOT_*` |
| Lights and panel | `DISABLE_FRONT_LED`, `DISABLE_FRONT_STANDBY_LED`, `TOP_PANEL_LED`, `TOP_PANEL_STANDBY_LED`, `DISABLE_TOP_PANEL` |
| Speaker pair | `CABLE_MODE`, `MASTER_CHANNEL_MODE` |
| Subwoofer | `SUBWOOFER_FORCE_ON`, `SUBWOOFER_FORCE_ON_KW1`, `SUBWOOFER_OUT_V2`, `SUBWOOFER_GAIN_V2` |
| Remote and buttons | `REMOTE_IR`, `SPEAKER_IR_CODE`, `REMOTE_IR_CODE`, `FAVOURITE_BUTTON`, `EQ_BUTTON_1`, `EQ_BUTTON_2`, `USER_FIXED_VOLUME` |
| Other | `USB_CHARGING`, `AUTO_DETECT_PLACEMENT`, `SPEAKER_LANGUAGE`, `DISABLE_ANALYTICS`, `DIALOGUE_MODE`, `PREFER_VIRTUAL_X`, `WIRELESS_REAR_GAIN`... |

Each setting has a `description`. If your model doesn't have a setting, the speaker answers with a
`KefApiError`.

## 📡 Live updates

### `watch()`

The speaker can push its changes: no need to poll it every few seconds. `watch()` gives you a new
`SpeakerState` each time something changes (volume, source, track, power...), usually within a tenth of a
second.

```python
async for state in speaker.watch():
    if state is None:
        print("speaker unreachable")
        continue
    print(state.source, state.volume, state.track and state.track.title)
```

- The first state is a full snapshot, then one state per change.
- `None` means the speaker can't be reached. `watch()` keeps trying to reconnect (every 1 s, slowing down
  to every 30 s) and sends a full state again as soon as the speaker is back.
  `watch(reconnect=False)` raises the error instead.
- The loop ends when the client is closed. Several `watch()` loops can run on the same client.
- `watch(track_position=True)` also sends the play position every second while playing. Without it, use
  `state.position_ms` and `state.position_updated_at` to compute the current position.
- `watch(extra_paths=[...])` follows more API paths, found in `state.extra`.

With `KefClient` it is a regular loop: `for state in speaker.watch(): ...`.

If you only need one reading, `get_state()` returns the same `SpeakerState` without watching.

### Events (lower level)

`watch()` is built on the speaker's event queue, which you can also use directly:

```python
from pykefcontrol import paths

async for event in speaker.events([paths.VOLUME, paths.MUTE]):
    print(event.path, event.value)
# -> player:volume 32
```

Or by hand:

```python
queue = speaker.event_queue()
await queue.subscribe([paths.VOLUME])
events = await queue.poll(timeout=25)     # waits up to 25 s, [] if nothing happened
```

Unlike `watch()`, these don't reconnect by themselves. The speaker only sends changes, so read the
current value after subscribing.

## 🧰 Raw API

For anything the library doesn't cover, you can talk to the speaker's API directly. `pykefcontrol.paths`
lists the known paths.

```python
from pykefcontrol import paths, ValueType

await speaker.get_value(paths.MUTE)
# -> False
await speaker.get_data(paths.VOLUME)                    # with its type
# -> {'type': 'i32_', 'i32_': 35}
await speaker.set_value(paths.VOLUME, ValueType.I32, 30)
await speaker.activate("powermanager:goReboot")         # trigger an action
await speaker.get_rows(paths.PLAY_QUEUE, 0, 19)         # read a list (play queue...)
```

## 🔎 Discovery and command line

### Discovery

With the `discovery` extra installed:

```python
from pykefcontrol.discovery import discover

for found in await discover(timeout=3.0):               # discover_blocking() without asyncio
    print(found.host, found.name, found.marketing_name)
# -> 192.168.1.20 Living room LS50 Wireless II
```

For zeroconf integrations, `parse_service_info()` turns a `_kef-info._tcp` record into the same
`DiscoveredSpeaker` object.

### Command line

Installing the package also installs a `pykefcontrol` command:

```shell
pykefcontrol discover
pykefcontrol info 192.168.1.20
pykefcontrol state 192.168.1.20
pykefcontrol watch 192.168.1.20
pykefcontrol power 192.168.1.20 on --source optical
pykefcontrol volume 192.168.1.20 30
pykefcontrol eq 192.168.1.20
pykefcontrol get 192.168.1.20 settings:/kef/host/modelName
pykefcontrol --help
```

`pykefcontrol diag 192.168.1.20` checks what your speaker supports (HTTP, HTTPS, EQ format, events...)
and prints a report. Please include it when you report a bug.

## 📦 Data reference

All objects are immutable dataclasses. Use `.replace(...)` to get a modified copy.

**`SpeakerState`** (from `get_state()` and `watch()`): `status`, `source`, `volume`, `muted`,
`play_mode`, `player`, `position_ms`, `position_updated_at`, `name`, `extra`, plus `is_on`,
`playback_state` and `track` shortcuts.

**`PlayerState`**: `state`, `track`, `controls`, `is_playing`, `duration_ms`.

**`Track`**: `title`, `artist`, `album`, `album_artist`, `cover_url`, `service_id`, `duration_ms`, `live`,
`codec`, `sample_rate`, `bits_per_sample`, `channels`, `bit_rate`. Any of them can be `None`.

**`PlayerControls`**: `pause`, `next`, `previous`, `seek` (booleans), `play_modes`.

**`DeviceInfo`**: `name`, `model`, `model_name`, `serial_number`, `mac_address`, `firmware`,
`release_text`, `hardware_version`.

**`NetworkInfo`**: `wired`, `wireless` (`NetworkInterface`: `ssid`, `signal_level`, `addresses`...),
`active`, `ip_address`.

**`BluetoothState`**: `connected`, `discoverable`, `pairable`, `discovering`, `pairing_code`.

**Enums**: `Source`, `SpeakerStatus`, `PlaybackState`, `PlayMode`, `StandbyMode`, `WakeUpSource`,
`CableMode`, `MasterChannelMode`, `BassExtension`, `Polarity`, `SubwooferPreset`, `SoundProfile`,
`SpeakerModel`... They are string enums: `Source.TV == "tv"`. If a speaker returns a value the library
doesn't know (newer firmware), you get it as a member anyway instead of an error;
`source.is_known` tells the difference.

## ⚠️ Errors

Every error raised by the library is a `KefError`:

```
KefError
├── KefConnectionError      speaker unreachable (off, wrong IP, network...)
│   └── KefTimeoutError     no answer in time
├── KefAuthError            the speaker refused our credentials
├── KefApiError             the speaker answered with an error (.status, .message, .path)
├── KefProtocolError        the answer doesn't make sense (not a KEF speaker?)
└── KefUnsupportedError     not supported by this model or firmware
```

```python
from pykefcontrol import KefConnectionError, KefError

try:
    await speaker.set_volume(30)
except KefConnectionError:
    print("speaker offline")
except KefError as err:
    print("speaker error:", err)
```

Wrong arguments (a volume of 150, an unknown source) raise `ValueError` or `TypeError` before anything is
sent.

## 💡 Good to know

- **Standby**: a speaker in standby still answers on the network, so you can read its state and wake it up.
- **Power on**: the API has no "power on" command. Selecting a source is what wakes the speaker up, which
  is why `power_on()` takes a source.
- **Default volume per input**: if "default volume" is enabled in the KEF app, the speaker sets its own
  volume about one second after waking up or changing input. A `set_volume()` sent right after
  `power_on()` / `set_source()` can be overridden: wait for the volume change (e.g. with `watch()`) or
  a second or two before setting the volume.
- **Logs**: the library logs under the `pykefcontrol` logger. Enable `DEBUG` to see the transport chosen,
  reconnections, etc.
- **Concurrency**: one async client can be shared by several tasks.
