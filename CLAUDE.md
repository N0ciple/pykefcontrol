# pykefcontrol - Context for AI Assistants

Python library for controlling KEF wireless speakers with the W2 platform.

## Project Overview

- **Type:** Python Library (synchronous and asynchronous)
- **Version:** 0.8
- **License:** MIT
- **Python:** 3.7+ (recommended: 3.11+)
- **Installation:** PyPI via `pip install pykefcontrol`

## Supported Hardware

All KEF W2 Platform speakers with network connectivity (WiFi/Ethernet):

| Model | Type | Physical Inputs | Tested |
|-------|------|----------------|--------|
| **LS50 Wireless II** | Bookshelf | WiFi, BT, Optical, Coaxial, Analogue, HDMI | ⚠️ Not tested |
| **LS60 Wireless** | Floorstanding | WiFi, BT, Optical, Coaxial, Analogue, HDMI | ⚠️ Not tested |
| **LSX II** | Compact bookshelf | WiFi, BT, Optical, USB, Analogue, HDMI | ✅ Tested |
| **LSX II LT** | Compact bookshelf | WiFi, BT, Optical, USB, HDMI | ✅ Tested |
| **XIO Soundbar** | Soundbar (5.1.2) | WiFi, BT, Optical, HDMI eARC | ✅ Tested |

**Incompatible Models:**
- KEF LS50 Wireless Gen 1 / LSX Gen 1 - Use [aiokef](https://github.com/basnijholt/aiokef) instead
- KEF Coda W, Muo - Bluetooth-only, no network API

## Repository Structure

```
pykefcontrol/
├── pykefcontrol/
│   ├── __init__.py           # Package initialization
│   ├── kef_connector.py      # Main library (KefConnector + KefAsyncConnector)
│   └── profile_manager.py    # EQ profile storage management
├── setup.py                  # PyPI package configuration
├── testing.py                # Comprehensive test suite with network discovery
├── apk_analysis.py           # API discovery tool
├── apk_analysis.md           # Complete API documentation (163 methods)
└── README.md                 # User documentation
```

## Architecture

### Two Main Classes

1. **`KefConnector`** - Synchronous connector for standard Python scripts
2. **`KefAsyncConnector`** - Asynchronous connector for async/await programs

Both classes have identical features with different invocation patterns.

### Key Components

**kef_connector.py:**
- Core API communication via HTTP requests
- Property-based interface for status, volume, source, etc.
- 163 public methods covering all KEF Connect app features
- Polling support for real-time updates
- Error handling and connection management

**profile_manager.py:**
- JSON-based EQ profile storage
- Save/load/list/delete/rename/export/import profiles
- Profile metadata (creation date, modification date, description)
- Default location: `~/.kef_profiles/` or `/config/.kef_profiles/` (HA)

## Feature Categories (163 Methods Total)

### Core Methods (46)
- Power, volume, source control
- Playback control (play/pause/next/previous)
- Media information retrieval
- Mute control
- Speaker status

### DSP/EQ Methods (36)
- Desk mode (with dB attenuation)
- Wall mode (with dB attenuation)
- Bass extension (standard/less/extra)
- Treble amount (-3.0 to +3.0 dB)
- Balance (-6.0 to +6.0)
- Phase correction
- High-pass filter
- Audio polarity
- Complete EQ profile get/set

### Subwoofer Methods (10)
- Enable/disable
- Gain control (-10 to +10 dB)
- Preset selection (kube8b, kc62, kf92, etc.)
- Low-pass filter (40-250 Hz)
- Polarity (normal/inverted)
- Stereo mode
- KW1 wireless adapter enable

### Profile Management (10)
- Save/load EQ profiles
- List profiles with metadata
- Delete/rename profiles
- Export/import as JSON
- Profile existence check
- Profile count

### Firmware Methods (3)
- Check for updates
- Get update status
- Install updates

### XIO Soundbar Methods (14)
- Sound profiles (default, music, movie, night, dialogue, direct)
- Dialogue mode toggle
- Wall mount detection
- Room calibration (status, result, step)
- BLE firmware updates (5 methods for KW2 subwoofer)

### Volume Management (6)
- Per-input default volumes
- Get/set all default volumes
- Volume settings (max, step, limit)
- Startup volume enable/disable
- Standby volume behavior (all sources vs individual)

### Network Diagnostics (6)
- Internet ping
- Network stability check
- Speed test (start, stop, status, results)

### System Behavior (8)
- Auto-standby modes (20/30/60 min, none)
- Wake source selection
- HDMI auto-switch
- Startup tone enable/disable
- USB charging enable/disable
- Cable mode (wired/wireless)
- Master channel (left/right)
- Speaker status

### LED Control (5)
- Front LED (no effect on current models)
- Standby LED
- Top panel LED (3 universal + 2 XIO-exclusive)

### Remote Control (7)
- IR remote enable/disable
- IR code set selection
- EQ button assignment (XIO only)
- Favourite button action
- Fixed volume mode

### Device Info (6)
- Model name (SP4041, SP4077, etc.)
- Serial number
- KEF ID (UUID)
- Hardware version
- MAC address
- Friendly speaker name

### Privacy/Streaming (4)
- KEF analytics enable/disable
- App analytics enable/disable
- Streaming quality (unlimited, 320, 256, 192, 128 kbps)
- UI language

### Advanced Operations (5)
- Speaker location (country code)
- DSP defaults restore
- Factory reset
- DSP info
- Firmware upgrade progress

### Network Management (2)
- WiFi network scanning
- Trigger WiFi scan

## API Communication

### HTTP Endpoints

The library communicates with KEF speakers via HTTP REST API:

**Base URL:** `http://{speaker_ip}:80/api/`

**Key Endpoints:**
- `/api/status` - Speaker status
- `/api/kef:play/v1` - Playback control
- `/api/kef:eqProfile/v2` - EQ/DSP settings
- `/api/network/v1` - Network diagnostics
- `/api/device/v1` - Device information
- `/api/firmware/v1` - Firmware management

**Request Format:** JSON payload via GET/POST
**Response Format:** JSON

### Property vs Method Pattern

**Properties (no parentheses):**
```python
status = speaker.status              # Get status
volume = speaker.volume              # Get volume
source = speaker.source              # Get source
is_playing = speaker.is_playing      # Get playback state
```

**Property Setters (direct assignment):**
```python
speaker.volume = 50                  # Set volume (sync only)
speaker.source = 'wifi'              # Set source (sync only)
```

**Methods (with parentheses):**
```python
speaker.power_on()                   # Power on
speaker.shutdown()                   # Shutdown
speaker.toggle_play_pause()          # Toggle playback
profile = speaker.get_eq_profile()   # Get EQ settings
speaker.set_eq_profile(profile)      # Set EQ settings
```

## Synchronous vs Async

### Synchronous (KefConnector)

```python
from pykefcontrol.kef_connector import KefConnector

speaker = KefConnector("192.168.1.100")

# Properties
print(speaker.volume)
print(speaker.status)

# Property setters
speaker.volume = 50
speaker.source = 'wifi'

# Methods
speaker.power_on()
speaker.set_bass_extension("extra")
```

### Asynchronous (KefAsyncConnector)

```python
import asyncio
from pykefcontrol.kef_connector import KefAsyncConnector

async def main():
    speaker = KefAsyncConnector("192.168.1.100")

    # Properties (must await)
    print(await speaker.volume)
    print(await speaker.status)

    # Property setters (use set_* methods)
    await speaker.set_volume(50)
    await speaker.set_source('wifi')

    # Methods (must await)
    await speaker.power_on()
    await speaker.set_bass_extension("extra")

    # Close session when done
    await speaker._session.close()

asyncio.run(main())
```

**Key Difference:** Async version requires:
1. `await` for all property access
2. `set_*` methods for property setters (no direct assignment)
3. Session management (close when done)

## Profile Management

### Standalone Usage (JSON Files)

```python
# Save current settings as profile
speaker.save_eq_profile("Movie Night", "Extra bass for movies")

# List all profiles
profiles = speaker.list_eq_profiles()

# Load profile (applies immediately)
speaker.load_eq_profile("Movie Night")

# Export/import
speaker.export_eq_profile("Movie Night", "/backup/movie.json")
speaker.import_eq_profile("/backup/movie.json", "Imported Profile")

# Custom storage location
speaker = KefConnector('192.168.1.100', profile_dir='/custom/path')
```

### Home Assistant Usage (Storage API)

**Note:** Home Assistant integration uses HA's Storage API instead of ProfileManager. See hass-kef-connector README for HA-specific implementation.

## Polling for Real-Time Updates

```python
# Monitor speaker changes
while True:
    changes = speaker.poll_speaker(timeout=10, poll_song_status=False)
    if changes:
        print(f"Changes: {changes}")
        # Changes contains: source, volume, status, song_info, etc.
```

**Polling Keys:**
- `source` - Input source changed
- `volume` - Volume changed
- `status` - Playback status changed
- `song_info` - Track info changed
- `song_status` - Playback position (if poll_song_status=True)
- `mute` - Mute state changed
- `speaker_status` - Power state changed
- `device_name` - Speaker renamed
- `other` - Other speaker-specific changes

## Testing and Discovery

### Network Discovery

```bash
# Auto-detect and scan network
python3 testing.py --discover

# Specify network
python3 testing.py --discover --network 192.168.1.0/24
```

**Features:**
- Fast parallel scanning (50 threads)
- Auto-detects local network
- Displays table of all KEF speakers with IP, name, model, firmware, MAC

### Test Suite

```bash
# Interactive mode (guides through all features)
python3 testing.py

# Quick connection test
python3 testing.py --host 192.168.1.100 --test info --model 0

# Test specific features
python3 testing.py --host 192.168.1.100 --test dsp --model 0       # DSP/EQ
python3 testing.py --host 192.168.1.100 --test subwoofer --model 0 # Subwoofer
python3 testing.py --host 192.168.1.100 --test xio --model 0       # XIO features

# Run all tests
python3 testing.py --host 192.168.1.100 --test all --model 0
```

**Model Codes:**
- `0` = LSX II
- `1` = LS50 Wireless II
- `2` = LS60

## API Discovery (apk_analysis.py)

```bash
# Test API compatibility
python apk_analysis.py --host 192.168.1.100 --verbose
```

Discovers and tests all 121 KEF API endpoints. Results documented in [apk_analysis.md](apk_analysis.md).

## Development Patterns

### Adding a New Method

1. **Identify the API endpoint** from apk_analysis.md
2. **Add getter method:**
```python
def get_some_setting(self):
    """Get some setting from speaker."""
    response = self._get_request('/api/some/endpoint')
    return response.get('someSetting')
```

3. **Add setter method:**
```python
def set_some_setting(self, value):
    """Set some setting on speaker."""
    payload = {'someSetting': value}
    self._set_request('/api/some/endpoint', payload)
```

4. **Add async versions in KefAsyncConnector:**
```python
async def get_some_setting(self):
    """Get some setting from speaker."""
    response = await self._get_request('/api/some/endpoint')
    return response.get('someSetting')

async def set_some_setting(self, value):
    """Set some setting on speaker."""
    payload = {'someSetting': value}
    await self._set_request('/api/some/endpoint', payload)
```

5. **Add to testing.py** for automated testing
6. **Update README.md** with usage examples

### Error Handling

```python
try:
    speaker.set_volume(50)
except requests.exceptions.RequestException as err:
    print(f"Communication error: {err}")
except Exception as err:
    print(f"Error: {err}")
```

### Session Management (Async)

```python
# Option 1: Manual session management
speaker = KefAsyncConnector("192.168.1.100")
await speaker.power_on()
await speaker._session.close()

# Option 2: Pass existing session
import aiohttp
session = aiohttp.ClientSession()
speaker = KefAsyncConnector("192.168.1.100", session=session)
await speaker.power_on()
await session.close()

# Option 3: Resurrect closed session
await speaker.resurect_session()
```

## Model-Specific Features

### LSX II / LSX II LT / LS50 Wireless II
- Desk mode (bookshelf speakers only)
- Wall mode (bookshelf speakers only)
- Standard DSP/EQ features
- Subwoofer output (except LSX II LT)

### LS60 Wireless
- No desk/wall mode (floorstanding)
- Enhanced bass extension
- Dual subwoofer outputs

### XIO Soundbar
- 6 sound profiles (exclusive)
- Dialogue mode toggle (no effect on current firmware)
- Wall mount detection via g-sensor
- Room calibration (read-only via API)
- BLE firmware for KW2 wireless subwoofer
- Control panel LED settings (4 controls)

## Implementation Status

### API Endpoint Discovery: 209 Total Endpoints Found

From complete JADX decompilation of KEF Connect v1.26.1 APK (`ApiPath.java`):
- **209 total API endpoints** discovered across all categories
- **~150+ endpoints** implemented via 163 Python methods
- **~30 endpoints** not yet implemented (specialized features)

### ✅ Implemented Features (163 Methods)

**Core Control (46 methods)**
- Power, volume, source control, playback, media info, mute, speaker status

**DSP/EQ Methods (36 methods)**
- Complete audio customization: desk mode, wall mode, bass, treble, balance
- Phase correction, high-pass filter, audio polarity
- Full EQ profile management

**Subwoofer Control (10 methods)**
- Gain, preset, low-pass, polarity, stereo mode, KW1 wireless adapter

**XIO Soundbar Features (14 methods)**
- Sound profiles (6 modes), dialogue mode, wall mount detection
- Room calibration (status, result, step)
- BLE firmware updates for KW2 subwoofer module

**Profile Management (10 methods)**
- Save, load, list, delete, rename, import/export EQ profiles

**Firmware Management (3 methods)**
- Check for updates, get status, install updates

**Volume Management (6 methods)**
- Per-input default volumes, startup volume, volume behavior settings

**Network Diagnostics (6 methods)**
- Internet ping, stability check, speed tests (start/stop/status/results)

**System Behavior (8 methods)**
- Standby modes, wake sources, HDMI auto-switch, USB charging, cable mode

**LED Controls (5 methods)**
- Front LED, standby LED, top panel controls (XIO-specific)

**Remote Control (7 methods)**
- IR remote enable/disable, code sets, EQ buttons (XIO), fixed volume

**Device Info (6 methods)**
- Model name, serial number, KEF ID, hardware version, MAC address

**Privacy/Streaming (4 methods)**
- Analytics controls, streaming quality, UI language

**Advanced Operations (5 methods)**
- Speaker location, DSP defaults restore, factory reset, firmware progress

**Network Management (2 methods)**
- WiFi scanning and activation

**Bluetooth Control (4 methods)** - NEW!
- `get_bluetooth_state`, `disconnect_bluetooth`, `set_bluetooth_discoverable`, `clear_bluetooth_devices`

**Grouping/Multiroom (2 methods)** - NEW!
- `get_group_members`, `save_persistent_group`

**Notifications (3 methods)** - NEW!
- `get_notification_queue`, `cancel_notification`, `get_player_notification`

**Alerts & Timers (13 methods)** - NEW!
- `list_alerts`, `add_timer`, `remove_timer`, `add_alarm`, `remove_alarm`
- `enable_alarm`, `disable_alarm`, `remove_all_alarms`, `stop_alert`, `snooze_alarm`
- `get/set_snooze_time`, `play_default_alert_sound`, `stop_default_alert_sound`

**Google Cast (3 methods)** - NEW!
- `get/set_cast_usage_report`, `get_cast_tos_accepted`

**Total Methods:** 188 (163 + 25 new methods)

### ⚠️ Not Yet Implemented (~5 Endpoints)

**Player Control (5 paths)** - Some return 500 errors, use polling instead
- `player:volume`, `player:player/control`, `player:player/data`, etc.
- Note: Playback control already implemented via different paths

**Power Management (3 paths)** - Direct power control paths
- `powermanager:target`, `powermanager:targetRequest`, `powermanager:goReboot`
- Note: Power on/shutdown already implemented via different endpoints

See [apk_analysis.md](apk_analysis.md) for complete API documentation and feature analysis.

## Dependencies

- **requests** >= 2.26.0 (synchronous HTTP)
- **aiohttp** >= 3.7.4 (asynchronous HTTP)

## Code Style

- Follow PEP 8
- Type hints on method signatures
- Docstrings for all public methods
- Descriptive variable names
- Error handling for network operations

## Common Pitfalls

1. **Property vs Method:** Volume, source, status are properties (no parentheses)
2. **Async Setters:** Use `set_volume()`, not `speaker.volume = X` in async
3. **Session Closing:** Always close async sessions to prevent warnings
4. **Polling Song Status:** Set `poll_song_status=False` unless tracking playback position
5. **Model Differences:** Check speaker_model before using XIO-specific features

## Related Projects

- **hass-kef-connector:** Home Assistant integration using this library
- **aiokef:** Library for KEF Gen 1 speakers (LS50W, LSX Gen 1)

## Recent Bug Fixes (2025-12-25)

### XIO Calibration Parsing
**Issue:** Calibration status showed "Not calibrated" when speaker was calibrated, and adjustment dB showed 0 instead of actual value.

**Root Cause:** API returns nested structure `{"kefDspCalibrationStatus": {...}}` but code was parsing flat structure. Adjustment uses `double_` type, not `i32_`.

**Fix:** Updated both sync and async methods:
- `get_calibration_status()`: Lines 1686-1701, 5107-5120
- `get_calibration_result()`: Lines 1703-1729, 5122-5143

**Status:** ✅ Fixed - XIO now shows correct calibration status and -5 dB adjustment

### Subwoofer Gain Step Size
**Issue:** UI allowed 0.5 dB steps (e.g., 5.5 dB) but KEF API only accepts integers.

**Fix:** Added validation to enforce 1 dB integer steps (-10 to +10):
- `set_subwoofer_gain()`: Lines 3326-3345, 6494-6513

**Status:** ✅ Fixed - Now rejects non-integer values with clear error message

### Treble Step Size
**Issue:** UI allowed any float value but KEF Connect app uses 0.25 dB increments.

**Fix:** Added validation to enforce 0.25 dB steps (-3.0 to +3.0):
- `set_treble_amount()`: Lines 3094-3114, 6221-6241

**Status:** ✅ Fixed - Now only accepts valid 0.25 dB increments (e.g., 1.25, 1.5, 1.75)

### API Response Format Documentation
All fixes based on actual API testing of XIO soundbar (V13120):
```json
// Calibration Status (nested object)
[{"type":"kefDspCalibrationStatus","kefDspCalibrationStatus":{"isCalibrated":true,...}}]

// Calibration Result (double, not int)
[{"type":"double_","double_":-5}]

// EQ Profile (integers for gain, floats for others)
{"subwooferGain":6,"trebleAmount":1.5,"subOutLPFreq":52.5}
```

## Contributors

- **Robin Dupont** - Original author
- **N0ciple** - Maintainer and feature expansion
- **danielpetrovic** - Testing and XIO soundbar analysis
