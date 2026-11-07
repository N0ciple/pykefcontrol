# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-11-07

Full rewrite. This release contains breaking changes, see the [migration guide](MIGRATION.md).
It was rebuilt from the behaviour of the official KEF Connect app and validated on an LS50 Wireless II
(firmware 4.1.192); other models are supported from the app's data but not yet tested on hardware.

### Added

- `KefAsyncClient` (aiohttp) and `KefClient` (urllib3) with the same API. The blocking client is generated
  from the async one by `scripts/gen_sync.py`; CI checks it is up to date.
- Support for the whole W2 network platform: LS50 Wireless II, LS60 Wireless, LSX II, **LSX II LT, XIO and
  LS LUXE**, plus a generic mode for future models.
- HTTPS on port 4430 with the private KEF root CA and HMAC-signed requests (recent firmware), with
  automatic fallback to HTTP on port 80. New options `transport`, `verify_ssl`, `ssl_context`, `credentials`,
  `timeout`, and `create_ssl_context()` / `KEF_ROOT_CA_PEM`.
- Typed, fully annotated API (`py.typed`), `StrEnum` enums (`Source`, `SpeakerStatus`, `PlaybackState`,
  `PlayMode`, ...), dataclasses (`DeviceInfo`, `NetworkInfo`, `PlayerState`, `Track`, `PlayerControls`,
  `BluetoothState`, `SpeakerState`, `Event`) and an exception hierarchy rooted at `KefError`.
- `get_state()`: full snapshot in one call. `watch()`: push updates on a persistent event queue with
  automatic reconnection (`None` = speaker unavailable), optional `track_position` and `extra_paths`.
  Low-level `event_queue()` (independent `AsyncEventQueue` / `EventQueue` objects) and `events()`.
- Real mute (`set_mute`, `get_mute`), idempotent `play()` / `pause()`, `stop()`, `seek()`,
  `set_play_mode()` / `get_play_mode()`, `volume_up()` / `volume_down()`, `set_default_volume()`,
  `set_name()`, `reboot()`, `factory_reset()`, experimental `play_url()`.
- Device information and capabilities: `get_device_info()`, `get_capabilities()` (`SpeakerModel`,
  `Capabilities`, `Feature`, `FirmwareVersion`), `get_network_info()`, `get_mac_address()`.
- Equalizer / DSP: `get_eq_profile()`, `set_eq_profile()`, `update_eq_profile()`, `reset_eq_profile()`,
  `get_eq_descriptors()`, `get_eq_ranges()`, `get_eq_version()`. Writes are validated against the speaker's own ranges. Both profile formats (v1 indices, v2 values) are handled
  transparently. The speaker applies EQ writes asynchronously, so `set_eq_profile()` waits until it
  reports the new profile (`wait=False` to skip) and `update_eq_profile()` calls are serialized.
- Typed `Settings` catalogue with `get_setting()` / `set_setting()` (validated, range-checked).
- Raw API: `get_data()`, `get_value()`, `set_data()`, `set_value()`, `activate()`, `get_rows()`, and the
  `pykefcontrol.paths` constants.
- Bluetooth: `get_bluetooth_state()`, `bluetooth_pairing()`, `bluetooth_disconnect()`.
- mDNS discovery (`pykefcontrol.discovery`, optional extra `pykefcontrol[discovery]`).
- `pykefcontrol` command line tool, including `pykefcontrol diag <ip>` (diagnostic report for new
  models / firmware). It replaces the interactive `testing.py` script.
- Test suite, ruff and strict mypy configuration, Nix flake.

### Changed

- **Breaking:** `KefConnector` / `KefAsyncConnector` and the `pykefcontrol.kef_connector` module are
  replaced by `KefClient` / `KefAsyncClient`, importable from `pykefcontrol`. No aliases are provided.
- **Breaking:** properties (including the async "awaitable properties") and property setters are replaced by
  `get_*` / `set_*` methods.
- **Breaking:** the constructor performs no network I/O.
- **Breaking:** all `setData` calls are POST (key `"role"`); the per-model GET/POST selection and the
  `model=` workaround are gone. `model=` only serves capabilities now.
- **Breaking:** `power_on()` selects a real source (last known, else Wi-Fi) instead of writing `powerOn`.
- **Breaking:** `mute()` / `unmute()` become `set_mute(bool)` using the speaker's real mute setting.
- **Breaking:** values are `StrEnum` members instead of plain strings (they still compare equal to strings).
- **Breaking:** errors are raised as `KefError` subclasses instead of being swallowed or surfacing as raw
  `KeyError` / `requests` / `aiohttp` exceptions.
- **Breaking:** `poll_speaker()` is replaced by `watch()` (or `event_queue()` / `events()`).
- A session injected into `KefAsyncClient` is never closed by the library.
- Event queue: a single persistent queue (25 s long-poll, like the official app) instead of a new queue
  every 50 s.
- Speaker model and firmware come from the `modelName` / `firmwareVersion` settings instead of parsing the
  release text.
- **Python 3.12 or newer** is required (was 3.10). `requests` is replaced by `urllib3`.
- Packaging moved entirely to `pyproject.toml` (hatchling); `setup.py`, `requirements.txt` and `testing.py`
  were removed.

### Removed

- `KefConnector`, `KefAsyncConnector`, `kef_connector` module (see above).
- `resurect_session()`, `close_session()` (use `aclose()` / `close()` or a context manager),
  `previous_volume` emulation, `song_status` / `poll_song_status` arguments, `_POST_MODELS`,
  `_MODEL_ALIASES`.
- The interactive `testing.py` script.

### Fixed

Bugs of 0.9.3 that no longer exist in the rewrite:

- Async `poll_speaker()` raised `AttributeError` from the second poll (misspelled attribute).
- `poll_song_status=True` did nothing: the play time was never subscribed.
- Events without a value (`remove` events, `item` subscriptions) crashed the event parser.
- The async poll used a hard-coded HTTP timeout and ignored the `timeout` argument, so values above 10 s
  cut the connection short.
- Blocking requests had no network timeout and could hang forever if the speaker disappeared.
- The blocking constructor made a network request, so a client could not be created offline.
- `close_session()` closed a session provided by the caller (for example Home Assistant's shared session);
  `resurect_session()` created a session that was never closed.
- `mute()` set the volume to 0 and `unmute()` without a prior `mute()` set the volume to 15 (async).
  The speaker's real mute is now used.
- Audio codec and Wi-Fi information were read from the wrong place in the player data (and every error was
  silently swallowed). They now come from the track resources and the network info, and errors surface.
- `song_length` issued several requests and could read inconsistent state; the track duration now comes
  from a single player state.
- `firmware_version` raised `IndexError` when the release text had an unexpected format.
- Deprecation message of `song_status` claimed removal in 0.8.0.

## [0.9.3]

- Fix LS60 support: `setData` now uses POST for LS60 (matches LS50WII / LSXII behavior).

## [0.9.2]

- Add LSX II support: `setData` now uses POST for LSX II (matches LS50WII / LSXIILT behavior).

## [0.9.1]

- Fix issue with new LSXIILT firmware: `setData` now uses POST for LSXIILT.

## [0.9]

- Switch from GET to POST for `setData` on LS50WII.

## [0.8]

- Add codec information and WiFi monitoring properties.
- Add generic API methods.

## [0.7.1]

- Fix issue with async version of `get_speaker_model` and `get_firmware_version`.

## [0.7]

- Now compatible with LSX II and LS60.
- Add `speaker_model` and `firmware_version` properties.
- The `song_status` argument of `poll_speaker` is deprecated. Use `poll_song_status`.

## [0.6.2]

- Modify `poll_speaker` to prevent failing if `song_status` is not properly defined by the speaker.
- Regenerate the queue ID if `song_status` was changed before the queue timeout.

## [0.6.1]

- Add parameter `song_status` to the method `poll_speaker`.

## [0.6]

- Add method `poll_speaker` that returns the last changes made to properties since the last poll.

## [0.5]

- Add option to pass an existing `session=aiohttp.ClientSession()` to `KefAsyncConnector`.
- Add methods `close_session` and `resurect_session`.

## [0.4]

- Add `KefAsyncConnector`, a class with the same functionality as `KefConnector` but with async
  properties and methods.

## [0.3]

- Breaking: `get_song_information()` now returns a dictionary, no longer a tuple.
- Add property `mac_address` that returns the MAC address of the speaker as a string.
- Add property `speaker_name` that returns the friendly speaker name as defined in the KEF Connect app
  onboarding process.

## [0.2]

- Correct a bug in `power_on` and `shutdown`.

## [0.1]

- First version.

[1.0.0]: https://github.com/N0ciple/pykefcontrol/compare/0.9.3...1.0.0
[0.9.3]: https://github.com/N0ciple/pykefcontrol/releases/tag/0.9.3
