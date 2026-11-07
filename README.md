# pykefcontrol

Python library to control KEF wireless speakers (W2 platform) over the local network.

It provides an `asyncio` client and a blocking client with the same API, and covers power, sources,
volume, playback, EQ/DSP settings, speaker settings and live updates pushed by the speaker.

> Version 1.0 is a full rewrite with breaking changes: upgrading from 0.9? See the
> [migration guide](https://github.com/N0ciple/pykefcontrol/blob/main/MIGRATION.md). It has been validated on an LS50 Wireless II (firmware 4.1.192);
> reports for other models are welcome.

## Supported speakers

LS50 Wireless II, LS60 Wireless, LSX II, LSX II LT, XIO and LS LUXE. Other W2-platform speakers should work
in a generic mode.

Not supported: Coda W and Muo (Bluetooth only), first generation LS50 Wireless and LSX (see
[aiokef](https://github.com/basnijholt/aiokef)).

## Installation

```shell
pip install pykefcontrol
pip install "pykefcontrol[discovery]"   # with network discovery (mDNS)
```

Requires Python 3.12 or newer.

## Usage

```python
from pykefcontrol import KefClient

with KefClient("192.168.1.20") as speaker:
    speaker.power_on()
    speaker.set_volume(30)
    print(speaker.get_player_state().track)
```

```python
from pykefcontrol import KefAsyncClient

async def main():
    async with KefAsyncClient("192.168.1.20") as speaker:
        await speaker.set_volume(30)
        async for state in speaker.watch():   # pushed by the speaker on every change
            print(state)
```

A command line tool is included: `pykefcontrol --help`.

## Features

- Power, source selection, volume and mute
- Playback control, track information, shuffle and repeat
- Full EQ / DSP profile (desk and wall modes, treble, bass extension, subwoofer settings...)
- Typed catalogue of speaker settings (standby, LEDs, remote, volume limits...)
- Live updates through the speaker's event queue, with automatic reconnection
- HTTPS API of recent firmware (signed requests, KEF certificate) with fallback to HTTP
- Model and firmware capabilities, device and network information
- Speaker discovery (mDNS) and raw access to the speaker's API

## Documentation

- [Documentation](https://github.com/N0ciple/pykefcontrol/blob/main/docs/documentation.md): complete guide and reference
- [Migration guide](https://github.com/N0ciple/pykefcontrol/blob/main/MIGRATION.md): upgrading from 0.9
- [Changelog](https://github.com/N0ciple/pykefcontrol/blob/main/CHANGELOG.md)

For Home Assistant, see [hass-kef-connector](https://github.com/N0ciple/hass-kef-connector).

## Development

```shell
uv sync
uv run pytest
uv run ruff check . && uv run mypy
```

The blocking client (`pykefcontrol/_sync/`) is generated from the async one (`pykefcontrol/_async/`) by
`scripts/gen_sync.py`; edit the async code and regenerate.

## License

MIT. pykefcontrol is an independent project and is not affiliated with KEF.
