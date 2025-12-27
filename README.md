# 🔉 pykefcontrol

Python library for controlling KEF wireless speakers: LS50 Wireless II, LS60 Wireless, LSX II, LSX II LT, and XIO Soundbar

⚠️ **Read the changelog to see breaking changes.**
For the **async** version, please read [this section](#️-specificity-of-kefasyncconnector)

🏠️ **For the Home Assistant integration, please see [hass-kef-connector](https://github.com/N0ciple/hass-kef-connector)**

- [🔉 pykefcontrol](#-pykefcontrol)
  - [📄 General Information](#-general-information)
  - [⬇️ Installation](#️-installation)
  - [⚙️ Usage](#️-usage)
    - [Get the IP address](#get-the-ip-address)
    - [Control the speaker with pykefcontrol](#control-the-speaker-with-pykefcontrol)
      - [First Step](#first-step)
      - [Available features](#available-features)
      - [Advanced features](#advanced-features)
  - [🕵️ Specificity of KefAsyncConnector](#️-specificity-of-kefasyncconnector)
    - [Renaming of property setters](#renaming-of-property-setters)
  - [📜 Changelog](#-changelog)


## 📄 General Information
This library works with the KEF LS50 Wireless II, LSX II and LS60 only. If you are searching for a library for the first generation LS50W or LSX, you can use [aiokef](https://github.com/basnijholt/aiokef).
Pykefcontrol has 2 main components: `KefConnector` and `KefAsyncConnector`. The first one can be used in all classic scripts and python programs, whereas the second one (`KefAsyncConnector`) can be used in asynchronous programs.

### Supported KEF Speakers

All KEF W2 platform speakers with network connectivity (WiFi/Ethernet) are supported:

| Model | Type | Physical Inputs | Features | Tested |
|---|---|---|---|---|
| **LS50 Wireless II** | Bookshelf | WiFi, BT, Optical, Coaxial, Analogue, HDMI | DSP, EQ, Sub out, HDMI eARC, MAT | ⚠️ Not tested |
| **LS60 Wireless** | Floorstanding | WiFi, BT, Optical, Coaxial, Analogue, HDMI | DSP, EQ, Sub out, MAT | ⚠️ Not tested |
| **LSX II** | Compact bookshelf | WiFi, BT, Optical, USB, Analogue, HDMI | DSP, EQ, Sub out | ✅ Tested |
| **LSX II LT** | Compact bookshelf | WiFi, BT, Optical, USB, HDMI | DSP, EQ, Sub out | ✅ Tested |
| **XIO Soundbar** | Soundbar (5.1.2) | WiFi, BT, Optical, HDMI eARC | DSP, EQ, Dolby Atmos, DTS:X, Sound profiles, Dialogue mode | ✅ Tested |

**Incompatible Models:**
- **Coda W, Muo** - Bluetooth-only, no network API
- **LS50 Wireless (Gen 1), LSX (Gen 1)** - Use [aiokef](https://github.com/basnijholt/aiokef) instead

### Current Implementation Status

**✅ API Discovery 100% COMPLETE - All 209 KEF API endpoints discovered! 🎉**

Using full JADX decompilation of KEF Connect v1.26.1 APK, we have discovered **ALL 209 API endpoints** from the definitive source code (`ApiPath.java`). This represents **89 new endpoints** beyond the previous 120 documented.

**API Discovery Breakdown (209 total endpoints):**
- 🔧 **124 Settings paths** (`settings:/`) - Speaker configuration
- ⚙️ **37 KEF Operations** (`kef:`) - System operations
- ▶️ **5 Player Control** (`player:`) - Playback control (NEW)
- 🔋 **3 Power Management** (`powermanager:`) - Standby/reboot (NEW)
- ⏰ **10 Alerts & Timers** (`alerts:/`) - Alarms and timers (NEW)
- 📱 **4 Bluetooth** (`bluetooth:`) - BT device management (NEW)
- 🔄 **3 Firmware Updates** (`firmwareupdate:`) - Update checking (NEW)
- 📡 **5 Google Cast** (`googlecast:`) - Cast configuration (NEW)
- 🌐 **7 Network** (`network:`/`networkwizard:`) - WiFi management
- 🔗 **2 Grouping** (`grouping:`) - Multi-room grouping (NEW)
- 🔔 **3 Notifications** (`notifications:/`) - UI notifications (NEW)
- 🎛️ **6 Other** - XIO-specific and legacy endpoints (NEW)

**Currently Implemented (v0.9 - 188 methods):**
- ✅ **46 core methods** - Power, volume, source control, playback, queuing
- ✅ **36 DSP/EQ methods** - Complete DSP control
- ✅ **10 subwoofer methods** - Enable, gain, preset, low-pass, polarity, stereo
- ✅ **14 XIO methods** - Sound profiles, calibration, BLE firmware
- ✅ **57 system methods** - Volume management, network diagnostics, system behavior, LED/remote control, device info, privacy
- ✅ **25 NEW methods** - Bluetooth (4), Alerts/Timers (13), Grouping (2), Notifications (3), Google Cast (3)

**Remaining (~5 endpoints - mostly redundant):**
- ▶️ Player Control (5 methods) - Already covered via polling/playback methods
- 🔋 Power Management (3 methods) - Already covered via power_on/shutdown
- 🎛️ Additional XIO features (6 methods)

See **[apk_analysis.md](apk_analysis.md)** for complete API documentation with all 209 endpoints cataloged.

## ⬇️ Installation

To install pykefcontrol, you can use pip:

```shell
pip install pykefcontrol
```

You can make sure you have the latest version by typing:
```python
>>> print(pykefcontrol.__version__)
```

Currently, the latest version is version `0.8`

## ⚙️ Usage

### Get the IP address

To use the pykefcontrol library, you need to know the IP address of your speakers. To do so, you can have a look at your router web page, or check in the KEF Connect app by doing the following:

1. Launch the KEF Connect app
2. Tap the gear icon on the bottom right
3. Then your speaker name (It should be right below your profile information)
4. Finally, the little circled "i" next to your speaker name in the _My Speakers_ section
5. You should find your IP address in the "IP address" section under the form `www.xxx.yyy.zzz`, where `www`, `xxx`, `yyy` and `zzz` are integers between `0` and `255`.

### Control the speaker with pykefcontrol

Once pykefcontrol is installed and you have your KEF Speaker IP address, you can use pykefcontrol in the following way:

#### First Step

⚠️ _For the **async** version, please read the section [Specificity of KefAsyncConnector](#️-specificity-of-kefasyncconnector)._

First, import the class and create a `KefConnector` object:

```python
from pykefcontrol.kef_connector import KefConnector
my_speaker = KefConnector("www.xxx.yyy.zzz")
```

⚠️ Do not forget to replace `www.xxx.yyy.zzz` with your speaker IP address. You should give your IP address as a string. It's to say that you should leave the quotation marks `"` around the IP address

#### Available features

Once the `my_speaker` object is created, you can use it in the following ways:

**Power, Shutdown and Status**
```python
# Power on
my_speaker.power_on() 

# Shutdown
my_speaker.shutdown() 

# Get speaker status : it returns a string ('powerOn' or 'standby')
my_speaker.status # it is not a method so it does not requires parenthesis
# (output example) >>> 'powerOn'

```

**Speaker Info**
```python
# Get the speaker MAC hardress
my_speaker.mac_address
# (output example) >>> 'AB:CD:EF:12:13:45'

# Get the speaker friendly name if configured
my_speaker.speaker_name
# (output example) >>> 'My Kef LS50W2'

# Get the speaker model
my_speaker.speaker_model
# (output example) >>> 'LS50WII'

# Get the firmware version
my_speaker.firmware_version
# (output example) >>> 'V27100'
```

**Source Control**
```python
# Get currently selected source : it returns a string ('wifi', 'bluetooth', 'tv', 'optical', 'coaxial', 'analog')
# If the speaker is not powered on, it will return 'standby'
my_speaker.source # it is not a method so it does not requires parenthesis
# (output example) >>> 'wifi'

# Set the input source 
# If the speaker is shutdown, setting a source will power it on
my_speaker.source = 'wifi' # 'wifi is an example, you can use any other supported string 'tv', 'analog', etc..
```

**Control playback**
```python
# Toggle play/pause
my_speaker.toggle_play_pause() 

# Next track
my_speaker.next_track()

# Previous track
my_speaker.previous_track()
```

**Control volume**
```python
# Muste speaker
my_speaker.mute() 

# Unmute speaker
my_speaker.unmute()

# Get volume : it reruns an integer between 0 and 100
my_speaker.volume # it is not a method so it does not require parenthesis
# (output example) >>> 23

# Set volume
my_speaker.volume = 42 # 42 for example but it can by any integer between 0 and 100.

# Set volume (alternative way)
my_speaker.set_volume(42) # 42 for example but it can by any integer between 0 and 100.
```

**Playback info**
```python
# Check if the speaker is playing : it returns a boolean (either True or False)
my_speaker.is_playing # it is not a method so it does not require parenthesis
# (output example) >>> True

# Get current media information : it retuns a dictionnary 
# (works on songs/podcast/radio. It may works on other media but I have not tested it yet)
my_speaker.get_song_information()
# (output example) >>> {'title':'Money','artist':'Pink Floyd','album':'The Dark Side of the Moon','cover_url':'http://cover.url'}

# Get media length in miliseconds : it returns an integer representing the song length in ms
my_speaker.song_length # it is not a method so it does not require parenthesis
# (output example) >>> 300251

# Get song progress : it returns the current playhead position in the current track in ms
my_speaker.song_status # it is not a method so it does not require parenthesis
# (output example) >>> 136900
```

**DSP / EQ Profile Control**

Pykefcontrol provides comprehensive control over the speaker's DSP (Digital Signal Processing) and EQ (Equalizer) settings. These settings allow you to customize the audio output to match your room acoustics and personal preferences.

⚠️ **Note**: These methods work with both Expert Mode and Normal EQ profiles in the KEF Connect app. Changes apply immediately to the speaker and are reflected in the KEF Connect app.

```python
# Get complete EQ profile
profile = my_speaker.get_eq_profile()
print(profile['kefEqProfileV2']['profileName'])  # e.g., "Expert" or "Kantoor"
print(profile['kefEqProfileV2']['isExpertMode'])  # True/False

# Profile Name Management
name = my_speaker.get_profile_name()  # Get current profile name
profile_id = my_speaker.get_profile_id()  # Get unique profile ID (UUID)
my_speaker.rename_profile("Living Room")  # Rename current profile

# Note: KEF speakers do not support deleting profiles via API
# The profile ID remains the same when renaming

# Desk Mode - compensates for speaker placement on a desk
# Note: Only available on bookshelf speakers (LSX II, LSX II LT, LS50 Wireless II)
#       Not available on LS60 (floorstanding) or XIO (soundbar)
# Returns (enabled: bool, db_value: float)
enabled, db = my_speaker.get_desk_mode()
print(f"Desk mode: {enabled}, attenuation: {db} dB")

# Enable desk mode with -3dB attenuation (range: -10.0 to 0.0 dB)
my_speaker.set_desk_mode(enabled=True, db_value=-3.0)

# Disable desk mode
my_speaker.set_desk_mode(enabled=False)

# Wall Mode - compensates for speaker placement near walls
# Note: Only available on bookshelf speakers (LSX II, LSX II LT, LS50 Wireless II)
#       Not available on LS60 (floorstanding) or XIO (soundbar - use wall_mounted instead)
enabled, db = my_speaker.get_wall_mode()
my_speaker.set_wall_mode(enabled=True, db_value=-2.0)  # -10.0 to 0.0 dB

# Bass Extension - controls low-frequency extension
mode = my_speaker.get_bass_extension()  # Returns: "standard", "less", or "extra"
my_speaker.set_bass_extension("extra")  # Options: "standard", "less", "extra"

# Treble Amount - adjust high-frequency balance
treble_db = my_speaker.get_treble_amount()  # Returns float in dB
my_speaker.set_treble_amount(1.5)  # Range: -3.0 to +3.0 dB

# Balance - adjust left/right balance
balance = my_speaker.get_balance()  # Returns float
my_speaker.set_balance(0.0)  # Range: -6.0 (left) to +6.0 (right), 0=center

# Phase Correction - enable/disable phase correction
phase = my_speaker.get_phase_correction()  # Returns bool
my_speaker.set_phase_correction(True)

# Advanced: Set complete EQ profile
profile = my_speaker.get_eq_profile()
profile['kefEqProfileV2']['deskMode'] = True
profile['kefEqProfileV2']['deskModeSetting'] = -3.0
profile['kefEqProfileV2']['trebleAmount'] = 1.5
my_speaker.set_eq_profile(profile)

# Advanced: Update single DSP setting
my_speaker.update_dsp_setting('trebleAmount', 1.5)
my_speaker.update_dsp_setting('phaseCorrection', True)
```

**Subwoofer Control** (for speakers with subwoofer output)

```python
# Check if subwoofer is enabled
enabled = my_speaker.get_subwoofer_enabled()  # Returns bool

# Enable/disable subwoofer output
my_speaker.set_subwoofer_enabled(True)

# Subwoofer gain control
gain = my_speaker.get_subwoofer_gain()  # Returns float in dB
my_speaker.set_subwoofer_gain(5.0)  # Range: -10.0 to +10.0 dB

# Subwoofer preset (auto-configuration for KEF subwoofers)
preset = my_speaker.get_subwoofer_preset()  # Returns str
my_speaker.set_subwoofer_preset('kube8b')  # Options: "custom", "kube8b", "kc62",
                                            # "kf92", "kube10b", "kube12b", "kube15", "t2"

# Subwoofer low-pass filter (crossover frequency)
freq = my_speaker.get_subwoofer_lowpass()  # Returns float in Hz
my_speaker.set_subwoofer_lowpass(80.0)  # Range: 40.0 to 250.0 Hz

# Subwoofer polarity
polarity = my_speaker.get_subwoofer_polarity()  # Returns "normal" or "inverted"
my_speaker.set_subwoofer_polarity('normal')

# Subwoofer stereo mode
# Note: API field exists but has no audible effect on current firmware
stereo = my_speaker.get_subwoofer_stereo()  # Returns bool
my_speaker.set_subwoofer_stereo(False)  # False=mono, True=stereo (no effect)

# KW1 Wireless Subwoofer Adapter
# The KW1 is KEF's wireless subwoofer adapter for all W2 platform speakers
kw1_enabled = my_speaker.get_kw1_enabled()  # Returns bool
my_speaker.set_kw1_enabled(True)  # Enable KW1 wireless adapter

# Note: KW2 (built-in wireless module in XIO) cannot be controlled via HTTP API.
# KW2 uses Bluetooth Low Energy pairing which is handled by the KEF Connect app.

# High-pass filter for main speakers (use with subwoofer)
# Returns (enabled: bool, freq_hz: float)
enabled, freq = my_speaker.get_high_pass_filter()
my_speaker.set_high_pass_filter(enabled=True, freq_hz=80.0)  # Range: 50.0 to 120.0 Hz

# Audio polarity for main speakers
polarity = my_speaker.get_audio_polarity()  # Returns "normal" or "inverted"
my_speaker.set_audio_polarity('normal')
```

For the **async** version (`KefAsyncConnector`), all DSP methods work identically but require `await`:

```python
# Async examples - Basic DSP
profile = await my_speaker.get_eq_profile()
enabled, db = await my_speaker.get_desk_mode()
await my_speaker.set_desk_mode(enabled=True, db_value=-3.0)
await my_speaker.set_bass_extension("extra")
await my_speaker.set_treble_amount(1.5)

# Async examples - Subwoofer control
gain = await my_speaker.get_subwoofer_gain()
await my_speaker.set_subwoofer_gain(5.0)
await my_speaker.set_subwoofer_preset('kube8b')
await my_speaker.set_subwoofer_lowpass(80.0)
enabled, freq = await my_speaker.get_high_pass_filter()
await my_speaker.set_high_pass_filter(enabled=True, freq_hz=80.0)

# Async examples - KW1 wireless adapter
kw1_enabled = await my_speaker.get_kw1_enabled()
await my_speaker.set_kw1_enabled(True)
```

### EQ Profile Management

Save, load, and manage custom EQ profiles. Profiles are stored as JSON files and can be shared across speakers or backed up.

**⚠️ Note for Home Assistant Users:**
The Home Assistant integration uses HA's native Storage API for profile management instead of these JSON file methods. These methods are provided for standalone Python scripts and CLI usage. If you're using this library through Home Assistant, profile management is handled automatically by the integration.

**Profile Storage (Standalone/CLI Usage):**
- Profiles are saved to `~/.kef_profiles/` (or custom directory via `profile_dir` parameter)
- Each profile includes all DSP/EQ settings, metadata, and timestamps
- Profiles can be exported/imported as JSON files for sharing or backup
- Not used by Home Assistant integration (HA uses `.storage/` instead)

```python
# Save current speaker settings as a named profile
my_speaker.save_eq_profile("Movie Night", "Extra bass for movies")

# List all saved profiles
profiles = my_speaker.list_eq_profiles()
for profile in profiles:
    print(f"{profile['name']}: {profile['description']}")
    print(f"  Created: {profile['created_at']}")
    print(f"  Modified: {profile['modified_at']}")

# Load a saved profile (applies to speaker immediately)
my_speaker.load_eq_profile("Movie Night")

# Check if a profile exists
if my_speaker.profile_exists("Music Mode"):
    my_speaker.load_eq_profile("Music Mode")

# Rename a profile
my_speaker.rename_eq_profile("Old Name", "New Name")

# Delete a profile
my_speaker.delete_eq_profile("Unused Profile")

# Get profile count
count = my_speaker.get_profile_count()
print(f"You have {count} saved profiles")

# Export profile for backup or sharing
my_speaker.export_eq_profile("Movie Night", "/backup/movie_profile.json")

# Import profile from file
profile_name = my_speaker.import_eq_profile("/backup/movie_profile.json", "Imported Profile")
my_speaker.load_eq_profile(profile_name)

# Example workflow: Create custom profiles for different use cases
# 1. Adjust settings for movies
my_speaker.set_bass_extension("extra")
my_speaker.set_treble_amount(0.5)
my_speaker.set_subwoofer_gain(3.0)
my_speaker.save_eq_profile("Movies", "Extra bass for cinema experience")

# 2. Adjust settings for music
my_speaker.set_bass_extension("standard")
my_speaker.set_treble_amount(1.0)
my_speaker.set_subwoofer_gain(0.0)
my_speaker.save_eq_profile("Music", "Balanced for music listening")

# 3. Switch between profiles easily
my_speaker.load_eq_profile("Movies")  # Watch a movie
# ... later ...
my_speaker.load_eq_profile("Music")   # Listen to music
```

**Async version** - Only `save_eq_profile()` and `load_eq_profile()` are async (they interact with the speaker). All other profile management methods are synchronous (they only access local files):

```python
# Async methods (interact with speaker)
await my_speaker.save_eq_profile("Movie Night", "Extra bass")
await my_speaker.load_eq_profile("Movie Night")

# Sync methods (local file operations - no await needed)
profiles = my_speaker.list_eq_profiles()
my_speaker.delete_eq_profile("Old Profile")
my_speaker.rename_eq_profile("Old", "New")
my_speaker.export_eq_profile("Profile", "/backup/profile.json")
profile_name = my_speaker.import_eq_profile("/backup/profile.json")
```

**Custom Profile Directory:**

```python
# Specify custom profile storage location
my_speaker = KefConnector('192.168.1.100', profile_dir='/custom/path/profiles')

# Or use default: ~/.kef_profiles/ or /config/.kef_profiles/ (Home Assistant)
my_speaker = KefConnector('192.168.1.100')
```

### Volume Management

Control per-input default volumes and volume behavior settings. Each physical input (WiFi, Bluetooth, Optical, etc.) can have its own default volume level, or you can use a global volume for all inputs.

#### Per-Input Default Volumes

Set different default volumes for each input source:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Get default volume for a specific input
wifi_volume = speaker.get_default_volume('wifi')  # Returns 0-100
bluetooth_volume = speaker.get_default_volume('bluetooth')

# Set default volume for specific inputs
speaker.set_default_volume('wifi', 50)       # Set WiFi to 50%
speaker.set_default_volume('bluetooth', 40)  # Set Bluetooth to 40%
speaker.set_default_volume('optical', 60)    # Set Optical to 60%

# Get all default volumes at once
all_volumes = speaker.get_all_default_volumes()
# Returns: {'global': 30, 'wifi': 50, 'bluetooth': 40, 'optical': 60, ...}

# Print all volumes
for source, volume in sorted(all_volumes.items()):
    print(f"{source:12s}: {volume}%")
```

**Available input sources by model:**
- **LSX II**: wifi, bluetooth, optical, usb, analogue, tv (6 inputs)
- **LSX II LT**: wifi, bluetooth, optical, usb, tv (5 inputs)
- **LS50 Wireless II**: wifi, bluetooth, optical, coaxial, analogue, tv (6 inputs)
- **LS60 Wireless**: wifi, bluetooth, optical, coaxial, analogue, tv (6 inputs)
- **XIO Soundbar**: wifi, bluetooth, optical, tv (4 inputs)

#### Volume Behavior Settings

Configure global volume limits and behavior:

```python
# Get current volume settings
settings = speaker.get_volume_settings()
# Returns: {'max_volume': 100, 'step': 1, 'limit': 100, 'display': 'linear'}

# Set maximum volume limit (safety feature for children/hearing protection)
speaker.set_volume_settings(max_volume=80)  # Limit to 80%

# Set volume step size (how much volume changes per button press)
speaker.set_volume_settings(step=2)  # Change by 2% per step

# Set volume limiter
speaker.set_volume_settings(limit=75)  # Soft limit at 75%

# Combine multiple settings
speaker.set_volume_settings(max_volume=85, step=2, limit=80)
```

#### Reset Volume (Startup Volume)

The "Reset Volume" feature (called "Startup Volume" in some contexts) controls what volume the speaker uses when waking from standby. This matches the KEF Connect app's "Reset volume" setting.

```python
# Check if reset volume is enabled
is_enabled = speaker.get_startup_volume_enabled()
# Returns: True = enabled, False = disabled (resumes at last volume)

# Enable reset volume feature
speaker.set_startup_volume_enabled(True)

# Disable reset volume (speaker resumes at last volume level)
speaker.set_startup_volume_enabled(False)
```

#### All Sources vs Individual Sources Mode

When reset volume is enabled, choose between "All Sources" (global) or "Individual Sources" (per-input) mode:

```python
# Check current mode
is_all_sources = speaker.get_standby_volume_behavior()
# Returns: True = All Sources, False = Individual Sources

# Set to "All Sources" mode (same reset volume for all inputs)
speaker.set_standby_volume_behavior(True)

# Set to "Individual Sources" mode (different reset volume per input)
speaker.set_standby_volume_behavior(False)
```

**How it works:**
- **All Sources (True)**: All inputs use the same reset volume (set via `defaultVolumeGlobal`)
- **Individual Sources (False)**: Each input has its own reset volume (WiFi, Bluetooth, etc.)

#### Async Support

All volume management methods support async:

```python
import asyncio
import pykefcontrol as pkf

async def manage_volumes():
    speaker = pkf.KefAsyncConnector('192.168.1.100')

    # Get all volumes
    volumes = await speaker.get_all_default_volumes()

    # Set specific input volumes
    await speaker.set_default_volume('wifi', 45)
    await speaker.set_default_volume('bluetooth', 35)

    # Configure volume settings
    await speaker.set_volume_settings(max_volume=80, step=2)

    # Enable reset volume with Individual Sources mode
    await speaker.set_standby_volume_behavior(False)  # Individual Sources
    await speaker.set_startup_volume_enabled(True)    # Enable reset volume

asyncio.run(manage_volumes())
```

### Network Diagnostics

Monitor network connectivity, stability, and perform speed tests. Useful for troubleshooting streaming issues or verifying network performance.

#### Internet Connectivity Check

Test if the speaker can reach the internet:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Ping internet
ping_ms = speaker.ping_internet()
if ping_ms > 0:
    print(f"Internet connected: {ping_ms}ms ping")
else:
    print("No internet connection")

# Check network stability
stability = speaker.get_network_stability()
print(f"Network stability: {stability}")  # Returns 'idle', 'stable', or 'unstable'
```

#### Network Speed Test

Run a complete speed test to measure download speeds and packet loss:

```python
import time

# Start speed test
speaker.start_speed_test()
print("Speed test started...")

# Monitor progress
while True:
    status = speaker.get_speed_test_status()
    print(f"Status: {status}")

    if status == 'complete':
        break
    elif status == 'idle':
        print("Speed test failed to start")
        break

    time.sleep(2)

# Get results when complete
results = speaker.get_speed_test_results()
print(f"Average download: {results['avg_download']} Mbps")
print(f"Current download: {results['current_download']} Mbps")
print(f"Packet loss: {results['packet_loss']}%")

# Stop test if needed
# speaker.stop_speed_test()
```

#### Speed Test Results

The `get_speed_test_results()` method returns a dictionary with:
- `avg_download`: Average download speed in Mbps
- `current_download`: Current download speed in Mbps
- `packet_loss`: Packet loss percentage

**Note:** Speed test results are only meaningful when status is 'running' or 'complete'. When idle, all values return 0.

#### Async Network Diagnostics

All network diagnostic methods support async:

```python
import asyncio
import pykefcontrol as pkf

async def check_network():
    speaker = pkf.KefAsyncConnector('192.168.1.100')

    # Quick connectivity check
    ping = await speaker.ping_internet()
    stability = await speaker.get_network_stability()

    print(f"Ping: {ping}ms, Stability: {stability}")

    # Run speed test
    await speaker.start_speed_test()

    # Wait for completion
    while True:
        status = await speaker.get_speed_test_status()
        if status == 'complete':
            break
        await asyncio.sleep(2)

    # Get results
    results = await speaker.get_speed_test_results()
    print(f"Speed: {results['avg_download']} Mbps")

asyncio.run(check_network())
```

### System Behavior Settings

Configure speaker power management, startup behavior, and inter-speaker connection settings.

#### Auto-Standby Mode

Control when the speaker automatically enters standby mode:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Get current standby mode
mode = speaker.get_standby_mode()
print(f"Current mode: {mode}")  # Returns 'standby_20mins'

# Set standby mode
speaker.set_standby_mode('standby_20mins')  # ECO mode (20 minutes)
speaker.set_standby_mode('standby_30mins')  # 30 minutes
speaker.set_standby_mode('standby_60mins')  # 60 minutes
speaker.set_standby_mode('standby_none')    # Never auto-standby
```

**Standby Modes:**
- `standby_20mins` - ECO mode (shown as "ECO" in KEF Connect app)
- `standby_30mins` - 30 minutes auto-standby
- `standby_60mins` - 60 minutes auto-standby
- `standby_none` - Never auto-standby (manual standby only)

#### Wake Source & HDMI Auto-Switch

Configure which input wakes the speaker and HDMI auto-switching:

```python
# Set wake source (which input can wake speaker from standby)
speaker.set_wake_source('wakeup_default')  # All inputs can wake
speaker.set_wake_source('tv')              # Only TV/HDMI wakes
speaker.set_wake_source('optical')         # Only optical wakes

# Enable auto-switch to HDMI when signal detected
speaker.set_auto_switch_hdmi(True)   # Auto-switch enabled
speaker.set_auto_switch_hdmi(False)  # Manual input selection

# Check current settings
wake = speaker.get_wake_source()
auto_hdmi = speaker.get_auto_switch_hdmi()
print(f"Wake source: {wake}, Auto-HDMI: {auto_hdmi}")
```

#### Startup Behavior

Control startup tone and USB charging:

```python
# Disable startup beep
speaker.set_startup_tone(False)

# Enable USB port charging
speaker.set_usb_charging(True)

# Check current settings
tone = speaker.get_startup_tone()
usb = speaker.get_usb_charging()
```

#### Inter-Speaker Connection

Configure wired vs wireless connection between left/right speakers:

```python
# Set cable mode (for stereo pairs)
speaker.set_cable_mode('wired')     # Use cable connection
speaker.set_cable_mode('wireless')  # Use wireless connection

# Set master channel designation
speaker.set_master_channel('left')   # This is the left speaker
speaker.set_master_channel('right')  # This is the right speaker

# Get current settings
cable = speaker.get_cable_mode()
channel = speaker.get_master_channel()
```

#### Speaker Status

Check if the speaker is powered on or in standby:

```python
status = speaker.get_speaker_status()
if status == 'powerOn':
    print("Speaker is powered on")
elif status == 'standby':
    print("Speaker is in standby mode")
```

#### Complete Configuration Example

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Configure for home theater use
speaker.set_standby_mode('standby_60mins')  # Long timeout
speaker.set_wake_source('tv')                # Wake on TV signal
speaker.set_auto_switch_hdmi(True)           # Auto-switch to HDMI
speaker.set_startup_tone(False)              # Silent startup

# Configure stereo pair
speaker.set_cable_mode('wired')              # Use cable for better quality
speaker.set_master_channel('left')           # Designate as left speaker
```

#### Async System Behavior

All system behavior methods support async:

```python
import asyncio
import pykefcontrol as pkf

async def configure_speaker():
    speaker = pkf.KefAsyncConnector('192.168.1.100')

    # Get all settings
    mode = await speaker.get_standby_mode()
    wake = await speaker.get_wake_source()
    status = await speaker.get_speaker_status()

    print(f"Standby: {mode}, Wake: {wake}, Status: {status}")

    # Configure settings
    await speaker.set_standby_mode('standby_30mins')
    await speaker.set_startup_tone(False)

asyncio.run(configure_speaker())
```

### XIO Soundbar Features

The KEF XIO soundbar includes exclusive features for home theater optimization. These features work on XIO soundbars only (model firmware V13xxx+).

#### Sound Profile Control

Sound profiles optimize audio for different content types with specialized DSP processing:

```python
# Get current sound profile
profile = my_speaker.get_sound_profile()
print(f"Current profile: {profile}")  # Returns: "default", "music", "movie", "night", "dialogue", or "direct"

# Switch to movie mode for films
my_speaker.set_sound_profile("movie")

# Available profiles:
# - "default": Balanced sound for general content
# - "music": Optimized for music playback
# - "movie": Cinema-like experience with enhanced dynamics
# - "night": Reduced dynamic range for late-night viewing
# - "dialogue": Enhanced speech clarity
# - "direct": Minimal DSP processing, pure sound

# Example: Automatically switch profiles based on input source
my_speaker.set_source("opt")  # Switch to TV input
my_speaker.set_sound_profile("movie")  # Use movie profile for TV

my_speaker.set_source("wifi")  # Switch to music streaming
my_speaker.set_sound_profile("music")  # Use music profile for streaming
```

**Async version:**
```python
profile = await my_speaker.get_sound_profile()
await my_speaker.set_sound_profile("movie")
```

#### Dialogue Enhancement Toggle

> ⚠️ **Note:** The `dialogueMode` boolean field exists in the KEF API and can be read/written, but **does not appear to have any audible effect** on current firmware (tested on XIO V13120). This is separate from the "dialogue" **sound profile** which works correctly. The `dialogueMode` toggle may be a placeholder for a future feature. For dialogue enhancement, use `set_sound_profile("dialogue")` instead.

The `dialogueMode` toggle was intended to enhance speech clarity independently of the sound profile, but currently has no effect:

```python
# Get dialogue enhancement state (reads correctly but toggle has no effect)
enabled = my_speaker.get_dialogue_mode()
print(f"Dialogue enhancement: {'On' if enabled else 'Off'}")

# These API calls succeed but have no audible effect
my_speaker.set_dialogue_mode(True)
my_speaker.set_dialogue_mode(False)

# For actual dialogue enhancement, use the dialogue sound profile instead:
my_speaker.set_sound_profile("dialogue")  # This works!
```

**Async version:**
```python
enabled = await my_speaker.get_dialogue_mode()
await my_speaker.set_dialogue_mode(True)  # No audible effect
await my_speaker.set_sound_profile("dialogue")  # Use this instead
```

#### Wall Mount Detection

XIO soundbars include a gravity sensor that detects wall mounting. You can read the current state or override it manually:

```python
# Check if soundbar is wall-mounted (via g-sensor)
is_wall_mounted = my_speaker.get_wall_mounted()
print(f"Wall mounted: {is_wall_mounted}")

# Manually override wall mount setting (if g-sensor is incorrect)
my_speaker.set_wall_mounted(True)  # Force wall-mounted mode
my_speaker.set_wall_mounted(False)  # Force shelf/TV-stand mode

# Note: Wall mounting affects speaker positioning (drivers used for sound)
# The g-sensor usually detects this automatically, but manual override is available
```

**Async version:**
```python
is_wall_mounted = await my_speaker.get_wall_mounted()
await my_speaker.set_wall_mounted(True)
```

#### Room Calibration

XIO soundbars include acoustic room calibration that measures your room and adjusts audio output for optimal sound. The calibration process uses a microphone to analyze room acoustics and applies dB adjustments automatically.

**Reading Calibration Data:**

```python
import pykefcontrol as pkf

xio = pkf.KefConnector('192.168.1.100')  # XIO Soundbar

# Check calibration status
status = xio.get_calibration_status()
if status['isCalibrated']:
    print(f"Calibrated on: {status['year']}-{status['month']:02d}-{status['day']:02d}")
    print(f"Network stability during calibration: {status['stability']}")
else:
    print("Room calibration not performed")

# Get calibration dB adjustment
result = xio.get_calibration_result()
print(f"Calibration applied: {result} dB adjustment")

# Check calibration progress (during calibration)
step = xio.get_calibration_step()
print(f"Calibration step: {step}")
# Possible values:
# - 'step_1_start': Calibration starting
# - 'step_2_processing': Calibration in progress
# - 'step_3_complete': Calibration complete
```

**Async version:**
```python
status = await xio.get_calibration_status()
result = await xio.get_calibration_result()
step = await xio.get_calibration_step()
```

**Note:** These methods are read-only and return the current calibration state. To perform a new calibration, use the KEF Connect app which guides you through the microphone-based calibration process.

#### BLE Firmware Updates (KW2 Subwoofer Module)

XIO soundbars have a built-in KW2 wireless subwoofer module with its own Bluetooth Low Energy (BLE) firmware that can be updated independently from the main speaker firmware.

**Checking BLE Firmware:**

```python
import pykefcontrol as pkf

xio = pkf.KefConnector('192.168.1.100')  # XIO Soundbar

# Get current BLE firmware version
version = xio.get_ble_firmware_version()
print(f"BLE firmware version: {version}")

# Get current update status
status = xio.get_ble_firmware_status()
print(f"Update status: {status}")
# Possible values: 'startUp', 'downloading', 'installing', 'complete'

# Check for available updates
update = xio.check_ble_firmware_update()
if update:
    print(f"BLE firmware update available: {update}")
else:
    print("No BLE firmware update available")
```

**Installing BLE Firmware Updates:**

```python
# Install BLE firmware update immediately
xio.install_ble_firmware_now()
print("BLE firmware update started")

# Or schedule update for later
xio.install_ble_firmware_later()
print("BLE firmware update scheduled")
```

**Async version:**
```python
version = await xio.get_ble_firmware_version()
status = await xio.get_ble_firmware_status()
update = await xio.check_ble_firmware_update()
await xio.install_ble_firmware_now()
await xio.install_ble_firmware_later()
```

**Note:** BLE firmware updates are for the KW2 wireless subwoofer module only and are separate from the main speaker firmware updates. This feature only works on XIO soundbars with the built-in wireless subwoofer.

### Do Not Disturb Settings

Control LED indicators and startup behavior to minimize distractions. In the KEF Connect app, these appear under "Do Not Disturb" settings.

**Important Note:** The API endpoints work on all KEF W2 platform speakers, but the physical effects vary by model:
- **LSX II / LSX II LT / LS50 W2 / LS60**: Only standby LED and startup tone are exposed in KEF Connect app
- **XIO Soundbar**: Full control panel LED controls (4 settings: control panel LED, control panel in standby, startup tone, control panel lock)

#### Standby LED

Control whether the LED indicator is visible when the speaker is in standby mode:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Enable standby LED (default)
speaker.set_standby_led(True)

# Disable standby LED (for dark rooms)
speaker.set_standby_led(False)

# Check current setting
enabled = speaker.get_standby_led()
print(f"Standby LED: {'On' if enabled else 'Off'}")
```

**Async version:**
```python
enabled = await speaker.get_standby_led()
await speaker.set_standby_led(False)
```

#### Startup Tone

Control the audible beep when powering on (also in System Behavior Settings):

```python
# Disable startup beep for silent power-on
speaker.set_startup_tone(False)

# Enable startup beep
speaker.set_startup_tone(True)

# Check current setting
enabled = speaker.get_startup_tone()
```

#### XIO Soundbar: Control Panel LED Controls

The XIO soundbar has exclusive control panel LED settings (4 controls shown in KEF Connect app under "Do Not Disturb"). The `set_top_panel_*` methods only work on XIO models.

> **Note:** The `get/set_front_led()` methods exist for all models but have no visible effect on any currently tested speakers (LSX II, LSX II LT, XIO). The API field exists in firmware but appears to have no hardware implementation. These methods are kept for completeness in case future models support this feature.

```python
# Control panel LED during operation
speaker.set_front_led(True)   # LED on during operation (default)
speaker.set_front_led(False)  # LED off during operation

# Control panel LED in standby
speaker.set_top_panel_standby_led(True)   # LED on in standby
speaker.set_top_panel_standby_led(False)  # LED off in standby

# Enable/disable top panel entirely (control panel lock)
speaker.set_top_panel_enabled(True)   # Panel active (default)
speaker.set_top_panel_enabled(False)  # Panel locked/disabled

# Check current settings
front_led = speaker.get_front_led()
panel_enabled = speaker.get_top_panel_enabled()
standby_led = speaker.get_top_panel_standby_led()

print(f"Front LED: {front_led}, Panel enabled: {panel_enabled}, Standby LED: {standby_led}")
```

**XIO Async version:**
```python
# XIO-specific async methods
await speaker.set_front_led(False)
await speaker.set_top_panel_standby_led(False)
await speaker.set_top_panel_enabled(False)
```

#### Complete Do Not Disturb Configuration

```python
import pykefcontrol as pkf

# Configure LSX II for bedroom use (minimal LEDs)
lsx_speaker = pkf.KefConnector('192.168.1.100')  # LSX II
lsx_speaker.set_standby_led(False)    # No standby indicator
lsx_speaker.set_startup_tone(False)   # Silent power-on

# Configure XIO for home theater (all LEDs off)
xio_speaker = pkf.KefConnector('192.168.1.101')  # XIO Soundbar
xio_speaker.set_standby_led(False)              # No standby LED
xio_speaker.set_startup_tone(False)             # Silent power-on
xio_speaker.set_front_led(False)                # Control panel off during operation
xio_speaker.set_top_panel_standby_led(False)    # Control panel off in standby
xio_speaker.set_top_panel_enabled(False)        # Lock control panel (optional)
```

### Remote Control Settings

Configure physical IR remote control behavior, including button assignments and volume locking.

#### IR Remote Control

Enable/disable IR remote control and set the IR code set to avoid conflicts with other devices:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Enable/disable IR remote
speaker.set_remote_ir_enabled(True)   # Enable IR remote (default)
speaker.set_remote_ir_enabled(False)  # Disable IR remote

# Check current setting
enabled = speaker.get_remote_ir_enabled()
print(f"IR remote: {'Enabled' if enabled else 'Disabled'}")

# Set IR code set (to avoid conflicts with other IR devices)
speaker.set_ir_code_set('ir_code_set_a')  # Default code set
speaker.set_ir_code_set('ir_code_set_b')  # Alternative if conflicts occur
speaker.set_ir_code_set('ir_code_set_c')  # Second alternative

# Check current code set
code = speaker.get_ir_code_set()
print(f"IR code set: {code}")
```

**Async version:**
```python
enabled = await speaker.get_remote_ir_enabled()
await speaker.set_remote_ir_enabled(True)

code = await speaker.get_ir_code_set()
await speaker.set_ir_code_set('ir_code_set_a')
```

#### XIO: EQ Button Assignment

On XIO soundbars, assign sound profiles to the two EQ buttons on the remote:

```python
# Get current EQ button assignments (XIO only)
preset1 = speaker.get_eq_button(1)
preset2 = speaker.get_eq_button(2)
print(f"EQ Button 1: {preset1}, Button 2: {preset2}")

# Assign sound profiles to EQ buttons
speaker.set_eq_button(1, 'dialogue')  # Button 1 = dialogue mode
speaker.set_eq_button(2, 'night')     # Button 2 = night mode
speaker.set_eq_button(1, 'music')     # Button 1 = music mode
speaker.set_eq_button(2, 'movie')     # Button 2 = movie mode

# Available presets: 'dialogue', 'night', 'music', 'movie', 'default', 'direct'
```

**Note:** EQ button assignment only works on XIO soundbars. LSX/LS50/LS60 models will return an error.

**Async version:**
```python
preset1 = await speaker.get_eq_button(1)
await speaker.set_eq_button(1, 'dialogue')
```

#### Favourite Button

Configure the action assigned to the favourite button on the remote:

```python
# Get current favourite button action
action = speaker.get_favourite_button_action()
print(f"Favourite button: {action}")

# Set favourite button action
speaker.set_favourite_button_action('nextSource')  # Cycle through inputs
```

**Async version:**
```python
action = await speaker.get_favourite_button_action()
await speaker.set_favourite_button_action('nextSource')
```

#### Fixed Volume Mode

Lock the speaker volume at a fixed level, preventing volume changes via remote or app:

```python
# Enable fixed volume mode (lock at specific level)
speaker.set_fixed_volume_mode(50)  # Lock volume at 50%
speaker.set_fixed_volume_mode(75)  # Lock volume at 75%

# Disable fixed volume mode (allow volume changes)
speaker.set_fixed_volume_mode(None)

# Check current setting
volume = speaker.get_fixed_volume_mode()
if volume is not None:
    print(f"Volume locked at: {volume}%")
else:
    print("Fixed volume mode disabled")
```

**Use case:** Commercial installations, public spaces, or preventing accidental volume changes.

**Async version:**
```python
volume = await speaker.get_fixed_volume_mode()
await speaker.set_fixed_volume_mode(50)
await speaker.set_fixed_volume_mode(None)
```

#### Complete Remote Control Example

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Enable IR remote with alternative code set (avoid conflicts)
speaker.set_remote_ir_enabled(True)
speaker.set_ir_code_set('ir_code_set_b')

# For XIO: Configure EQ buttons
if speaker.speaker_model == 'XIO':
    speaker.set_eq_button(1, 'dialogue')
    speaker.set_eq_button(2, 'night')

# Configure favourite button
speaker.set_favourite_button_action('nextSource')

# Lock volume for commercial use
speaker.set_fixed_volume_mode(60)  # Lock at 60%
```

### Firmware Update

Check for and manage firmware updates for your KEF speakers:

```python
# Sync version
import pykefcontrol as pkf

my_speaker = pkf.KefConnector("192.168.1.100")

# Check current firmware version
print(f"Current firmware: {my_speaker.firmware_version}")

# Trigger check for available updates (speaker needs internet connection)
update_info = my_speaker.check_for_firmware_update()
if update_info:
    print(f"Update available: {update_info}")

    # Install the update
    result = my_speaker.install_firmware_update()
    print("Firmware update started!")

    # Monitor progress (speaker will restart during update)
    status = my_speaker.get_firmware_update_status()
    if status:
        print(f"Update status: {status}")
```

```python
# Async version
import asyncio
import pykefcontrol as pkf

async def check_updates():
    my_speaker = pkf.KefAsyncConnector("192.168.1.100")

    # Check current firmware version
    firmware = await my_speaker.get_firmware_version()
    print(f"Current firmware: {firmware}")

    # Trigger check for available updates
    update_info = await my_speaker.check_for_firmware_update()
    if update_info:
        print(f"Update available: {update_info}")

        # Install the update
        result = await my_speaker.install_firmware_update()
        print("Firmware update started!")

        # Monitor progress (speaker will restart during update)
        status = await my_speaker.get_firmware_update_status()
        if status:
            print(f"Update status: {status}")

asyncio.run(check_updates())
```

### Firmware Release Notes

Fetch official firmware release notes from KEF's website to show users the latest available firmware and release history:

```python
import pykefcontrol as pkf

# Get release notes for all KEF models
releases = pkf.get_kef_firmware_releases()

# Or get releases for specific model
releases = pkf.get_kef_firmware_releases(model_filter="LSX II")
# Can also use API model name format
releases = pkf.get_kef_firmware_releases(model_filter="LSXII")

# Show latest firmware
if "LSX II" in releases and releases["LSX II"]:
    latest = releases["LSX II"][0]
    print(f"Latest version: {latest['version']}")
    print(f"Release date: {latest['date']}")
    print("Changes:")
    for note in latest['notes']:
        print(f"  • {note}")
```

**Home Assistant Integration:**
Use this to create sensors showing latest available firmware versions and release notes without requiring internet connection on the speaker itself.

### KEF XIO Soundbar Features

The KEF XIO soundbar has additional features not available on other KEF speakers:

**Sound Profiles** - Six preset audio modes optimized for different content:

```python
# Get current sound profile
profile = my_speaker.get_sound_profile()  # Returns str

# Set sound profile
my_speaker.set_sound_profile('movie')

# Available profiles:
# - 'default' - Default sound profile
# - 'music' - Optimized for music playback
# - 'movie' - Enhanced for movie audio
# - 'night' - Reduced dynamics for late-night listening
# - 'dialogue' - Voice clarity enhancement
# - 'direct' - No processing, direct audio path
```

**Wall Mount Configuration:**

```python
# Check if soundbar is configured as wall-mounted
mounted = my_speaker.get_wall_mounted()  # Returns bool

# Update wall mount configuration
my_speaker.set_wall_mounted(True)
```

**Async Version:**

```python
profile = await my_speaker.get_sound_profile()
await my_speaker.set_sound_profile('movie')

mounted = await my_speaker.get_wall_mounted()
await my_speaker.set_wall_mounted(True)
```

**Note:** These methods work on XIO soundbars only. Using them on other KEF models will work via `update_dsp_setting()` but may not have any effect depending on the model.

### Device Information

Get comprehensive device information for your KEF speakers:

```python
import pykefcontrol as pkf

speaker = pkf.KefConnector('192.168.1.100')

# Get all device info at once
info = speaker.get_device_info()
print(f"Model: {info['model_name']}")
print(f"Serial: {info['serial_number']}")
print(f"KEF ID: {info['kef_id']}")
print(f"Hardware: {info['hardware_version']}")
print(f"MAC: {info['mac_address']}")

# Or get individual values
model = speaker.get_model_name()  # Returns: 'SP4041', 'SP4077', 'SP4083', etc.
serial = speaker.get_serial_number()
kef_id = speaker.get_kef_id()  # UUID for KEF cloud services
hw_ver = speaker.get_hardware_version()
mac = speaker.get_mac_address()  # Format: 'XX:XX:XX:XX:XX:XX'
```

**Model codes:**
- `SP4041` = LSX II
- `SP4077` = LSX II LT
- `SP4083` = XIO Soundbar
- `SP4045` = LS50 Wireless II
- `SP4065` = LS60 Wireless

**Async version:**
```python
info = await speaker.get_device_info()
model = await speaker.get_model_name()
serial = await speaker.get_serial_number()
```

### Privacy & Streaming Settings

Control analytics, streaming quality, and language preferences:

#### Analytics Controls

```python
# Check KEF analytics state (speaker usage data to KEF)
analytics_enabled = speaker.get_analytics_enabled()  # Returns bool

# Enable/disable KEF analytics
speaker.set_analytics_enabled(True)   # Allow KEF to collect data
speaker.set_analytics_enabled(False)  # Disable data collection

# Check app analytics state (KEF Connect app usage data)
app_analytics = speaker.get_app_analytics_enabled()  # Returns bool

# Enable/disable app analytics
speaker.set_app_analytics_enabled(True)
speaker.set_app_analytics_enabled(False)
```

#### Streaming Quality

Configure streaming service bitrate limits:

```python
# Get current quality setting
quality = speaker.get_streaming_quality()  # Returns: 'unlimited', '320', '256', '192', or '128'

# Set streaming quality (kbps)
speaker.set_streaming_quality('unlimited')  # No limit (best quality)
speaker.set_streaming_quality('320')        # 320 kbps (high quality)
speaker.set_streaming_quality('256')        # 256 kbps (good quality)
speaker.set_streaming_quality('192')        # 192 kbps (medium quality)
speaker.set_streaming_quality('128')        # 128 kbps (data saving)
```

**Note:** Lower bitrates reduce bandwidth usage but decrease audio quality. Only affects streaming services (Spotify, Tidal, etc.), not local sources.

#### UI Language

```python
# Get current language
lang = speaker.get_ui_language()  # Returns: 'en_GB', 'nl_NL', etc.

# Set UI language (ISO language codes)
speaker.set_ui_language('en_GB')  # English (UK)
speaker.set_ui_language('en_US')  # English (US)
speaker.set_ui_language('nl_NL')  # Dutch
speaker.set_ui_language('de_DE')  # German
speaker.set_ui_language('fr_FR')  # French
speaker.set_ui_language('es_ES')  # Spanish
speaker.set_ui_language('it_IT')  # Italian
speaker.set_ui_language('ja_JP')  # Japanese
speaker.set_ui_language('zh_CN')  # Chinese (Simplified)
speaker.set_ui_language('zh_TW')  # Chinese (Traditional)
```

**Async version:**
```python
analytics = await speaker.get_analytics_enabled()
await speaker.set_analytics_enabled(False)

quality = await speaker.get_streaming_quality()
await speaker.set_streaming_quality('320')

lang = await speaker.get_ui_language()
await speaker.set_ui_language('en_GB')
```

### Advanced Operations

#### Speaker Location

Configure the speaker's geographic region (affects available streaming services and regional settings):

```python
# Get current location code
location = speaker.get_speaker_location()  # Returns integer country code

# Set speaker location
speaker.set_speaker_location(44)  # Set to UK (example code)
```

**Async version:**
```python
location = await speaker.get_speaker_location()
await speaker.set_speaker_location(44)
```

#### DSP Operations

```python
# Restore DSP settings to factory defaults
# Resets: EQ, bass extension, wall/desk mode, phase, etc.
# Does NOT affect: Network settings, user profiles, streaming accounts
speaker.restore_dsp_defaults()

# Get complete DSP state information
dsp_info = speaker.get_dsp_info()
print(f"DSP configuration: {dsp_info}")
```

**Async version:**
```python
await speaker.restore_dsp_defaults()
dsp_info = await speaker.get_dsp_info()
```

#### Firmware Upgrade Progress

Monitor firmware update progress for all components:

```python
# Get firmware upgrade progress during an update
progress = speaker.get_firmware_upgrade_progress()
print(f"Main firmware: {progress.get('main', 0)}%")
print(f"DSP firmware: {progress.get('dsp', 0)}%")
print(f"BLE firmware: {progress.get('ble', 0)}%")  # XIO only
```

**Async version:**
```python
progress = await speaker.get_firmware_upgrade_progress()
```

#### Factory Reset

**⚠️ WARNING: Use with extreme caution!**

Performing a factory reset will erase ALL settings and return the speaker to factory defaults. This includes:
- Network configuration (WiFi credentials)
- User preferences and profiles
- Streaming service accounts
- Paired Bluetooth devices
- All custom settings

The speaker will require complete setup again through the KEF Connect app.

```python
# Perform factory reset (NO CONFIRMATION PROMPT!)
speaker.factory_reset()
```

**Async version:**
```python
await speaker.factory_reset()
```

**Recommendation:** Only use in troubleshooting or before selling/transferring the speaker.

### Network Management

Scan and manage WiFi networks:

#### WiFi Network Scanning

```python
import time

# Trigger a new WiFi scan
speaker.activate_wifi_scan()

# Wait for scan to complete
time.sleep(3)

# Get available networks
networks = speaker.scan_wifi_networks()
for network in networks:
    print(f"SSID: {network['ssid']}")
    print(f"  Security: {network['security']}")
    print(f"  Signal: {network['signalStrength']}")
    print(f"  Frequency: {network['frequency']}")
    print()
```

**Network information includes:**
- `ssid` - Network name
- `security` - Security type (WPA2, WPA3, Open, etc.)
- `signalStrength` - Signal strength indicator
- `frequency` - Band (2.4GHz or 5GHz)

**Async version:**
```python
import asyncio

# Trigger scan
await speaker.activate_wifi_scan()

# Wait for scan
await asyncio.sleep(3)

# Get results
networks = await speaker.scan_wifi_networks()
for network in networks:
    print(f"{network['ssid']}: {network['signalStrength']}")
```

**Use case:** Network diagnostics, finding optimal WiFi channel, checking signal strength before placement.

**Information Polling**

Pykefcontrol offers a polling functionality. Instead of manually fetching all parameters to see what has changed, you can use the method `poll_speaker`. This method returns the updated properties since the last time the changes were polled. If multiple changes are made to the same property, only the last change will be kept. It is technically possible to track all the changes to a property since the last poll, although it is not implemented. Please submit an issue if you need such a feature.

`poll_speaker` will return a dictionary whose keys are the names of the properties which have been updated.

`poll_speaker` arguments:

| Argument | Required | Default Value | Comment |
|----------|----------|---------------|---------|
| `timeout` | Optional | `10` | `timeout` is in seconds. If no change has been made since the last poll when you call `poll_speaker`, the method will wait for changes during `timeout` seconds for new changes. If there is a change before the end of the timeout, `poll_speaker` will return them immediately and stop monitoring changes. If no changes are made, the method will return an empty dictionary. ⚠️ the real timeout is `timeout`+ 0.5 seconds. The speaker will wait for `timeout` seconds before returning an empty dictionary if no changes are made. Therefore it is necessary to add a small margin in the python function to account for processing/networking time. Please submit an issue if you feel that this parameter needs tweaking. |
| `song_status` | Optional | `False` | **Deprecated**, please use `poll_song_status` instead |
| `poll_song_status` | Optional | `False` | If `poll_song_status` if set to `True`, it will poll the song status (how many miliseconds of the current song have been played so far). If a song is playing and `poll_song_status` is set to `True`, `poll_speaker` will return almost imediately since `song_status` is updated at each second. This is forcing you to poll agressively to get other events. By default it is set to `False` in order to track other events more efficiently. |

```python
my_speaker.poll_speaker(timeout=3) # example of a 3 seconds timeout
# (output example) >>> {}  # it will return an empty dict if no changes were made

# no suppose you start playing a song
my_speaker.poll_speaker(poll_song_satus=True) # timeout is 10 seconds by default
# (output example) >>> {'song_info': {'title': 'Am I Wrong',
#  'artist': 'Etienne de Crécy',
#  'album': 'Am I Wrong',
#  'cover_url': 'https://some-url/some-image.jpg'},
# 'song_length': 238000,
# 'status': 'playing',
# 'song_status': 26085}
#
# -> in this case it returns a dictionary with the keys "song_info" , 
# "song_length", "status" and "song_status" containing information about the new song

# now suppose you change the volume to 32
my_speaker.poll_speaker(poll_song_satus=True)
# (output example) >>> {'song_status': 175085, 'volume': 32}
#
# -> in this case it returns both "song_status" (because the song kept playing), 
# and "volume" because you updated the volume

# if you do not want to poll the song status
my_speaker.poll_speaker()
# (output example) >>> {'volume': 32}
```
All the possible keys of the dictionary are:
`source`, `song_status`, `volume`, `song_info`, `song_length`, `status`, `speaker_status`, `device_name`, `mute` and `other`.

`other` contains some of the speaker-specific information that might have changed, but are not properties of either `KefConnector` or `KefAsyncConnector`.

#### Advanced features

This function is used internally by pykefcontrol and returns a JSON output with a lot of information. You might want to use them to get extra information such as the artwork/album cover URL, which does not have a dedicated function yet in pykefcontrol.

```python
# Get currently playing media information
my_speaker._get_player_data()
# (output example) >>> {'trackRoles': {'icon': 'http://www.xxx.yyy.zzz:80/file/stream//tmp/temp_data_airPlayAlbum_xxxxxxxxx', 'title': 'I Want To Break Free', 'mediaData': {'resources': [{'duration': 263131}], 'metaData': {'album': 'Greatest Hits', 'artist': 'Queen'}}}, 'playId': {'systemMemberId': 'kef_one-xxxxxxxx', 'timestamp': 676181357}, 'mediaRoles': {'audioType': 'audioBroadcast', 'title': 'AirPlay', 'doNotTrack': True, 'type': 'audio', 'mediaData': {'resources': [{'mimeType': 'audio/unknown', 'uri': 'airplay://'}], 'metaData': {'serviceID': 'airplay', 'live': True, 'playLogicPath': 'airplay:playlogic'}}}, 'state': 'playing', 'status': {'duration': 263131, 'playSpeed': 1}, 'controls': {'pause': True, 'next_': True, 'previous': True}}

```

## 🕵️ Specificity of KefAsyncConnector

Pykefcontrol offers an **asynchronous connector** with the same feature set as the synchronous connector. However, there are a few changes in the property setters. You can no longer use `my_speaker.volume = 28` to set a property. You have to use the setter like so: `await my_speaker.set_volume(28)`.

The actions you make with `KefAsyncConnector` should be embedded in an async function. Here is a quick example:

```python
import asyncio
from pykefcontrol.kef_connector import KefAsyncConnector

# Define an async function
async def main():
  my_speaker = KefAsyncConnector("192.168.yyy.zz")
  # Get speaker name
  print(await my_speaker.speaker_name)
  # Get volume
  print(await my_speaker.volume)

  # Turn on speaker
  await my_speaker.power_on()
  # Toggle play/pause
  await my_speaker.toggle_play_pause()

  # Set volume
  # Please read through to see precision about setters
  await my_speaker.set_volume(28)
  # Set source
  await my_speaker.set_source("bluetooth")
  # Set status
  await my_speaker.set_status("powerOn")

  # To avoid warning about an unclosed session
  # once your program is over, run:
  await my_speaker._session.close()
  # This is not mandatory. But if you do not close 
  # the session, you will have a warning.

# Get loop
loop = asyncio.get_event_loop()
# Run main function in async context
loop.run_until_complete(main())
```
### Renaming of property setters

`KefAsyncConnector` has the same property and methods as its synchronous counterpart `KefConnector`. You can access the same properties and methods in an asynchronous context by using `await my_speaker.property` or `await my_speaker.method()`. For the list of available properties and methods, read [Available features](#available-features).

**However**, to have an asynchronous property setter, the way to set properties has changed. You should use the specific setter. For a `property`, the setter is called `set_property`. As you can see in the example script above, to set the volume, use `set_volume`. Here is the list of properties with such setters:

- volume: use `set_volume`
- state: use `set_state`
- source: use `set_source`

## 🧪 Testing

The `testing.py` script provides comprehensive testing for all pykefcontrol features. It supports network discovery, interactive mode, and non-interactive testing.

### Network Discovery

Automatically discover KEF speakers on your network:

```bash
# Auto-detect network and scan
python3 testing.py --discover

# Specify network range
python3 testing.py --discover --network 192.168.16.0/24
```

This will scan your network and display a table of all discovered KEF speakers with their IP addresses, names, models, firmware versions, and MAC addresses.

**Features:**
- Fast parallel scanning (50 concurrent threads)
- Auto-detects network from local IP if not specified
- Works with all KEF speaker models (LSX II, LSX II LT, LS50 Wireless II, LS60, XIO soundbar)
- Displays results in a formatted table

### Interactive Mode

Run the full interactive test suite:
```bash
python3 testing.py
```

The script will guide you through testing all features with prompts and confirmations.

### Non-Interactive Mode

For automated testing or quick verification, use command-line arguments:

**Quick connection test:**
```bash
python3 testing.py --host 192.168.16.22 --test info --model 0
```

**Test specific features:**
```bash
# Test DSP/EQ features (desk mode, wall mode, bass, treble, balance, etc.)
python3 testing.py --host 192.168.16.22 --test dsp --model 0

# Test subwoofer controls
python3 testing.py --host 192.168.16.22 --test subwoofer --model 0

# Test firmware update features
python3 testing.py --host 192.168.16.22 --test firmware --model 0

# Test XIO soundbar-specific features
python3 testing.py --host 192.168.16.26 --test xio --model 0
```

**Run all tests non-interactively:**
```bash
python3 testing.py --host 192.168.16.22 --test all --model 0
```

**Model codes:**
- `0` = LSX II
- `1` = LS50 Wireless II
- `2` = LS60

**Available test suites:**
- `info` - Speaker information only
- `dsp` - DSP/EQ controls (11 methods)
- `subwoofer` - Subwoofer controls (6 methods)
- `xio` - XIO soundbar features (2 methods)
- `firmware` - Firmware update features (3 methods)
- `all` - Complete test suite

## 🚧 Currently Working On

**Goal:** Achieve feature parity with KEF Connect app for official Home Assistant integration

### Profile Management
- Save/load/manage EQ profiles
- JSON storage with metadata
- Import/export functionality
- Share profiles between speakers

### XIO Soundbar Features
- Sound profile control (default/music/movie/night/dialogue/direct)
- Dialogue enhancement mode
- Room calibration control
- Wall mount detection
- BLE firmware updates (KW2 subwoofer)

See [SPEAKER_FEATURES_ANALYSIS.md](SPEAKER_FEATURES_ANALYSIS.md) for complete feature analysis.

## 📜 Changelog
- **version 0.7.1**
  - Fix issue with async version of `get_speaker_model` and `get_firmware_version`.
- **version 0.7**
  - Now **compatible with LSX II and LS60** !
  - Add `speaker_model` and `firmware_version` properties.
  - ⚠️ `song_status` argument of `poll_speaker` is now deprecated. Please use `poll_song_status`
- **Version 0.6.2**
  - modify `poll_speaker` to prevent falling if `song_status` is not properly defined by the speaker
  - regenerate the queue_id if `song_status` was changed before the queue timeout.
- **Version 0.6.1**
  - Add parameter `song_status` to the method `poll_speaker`. 

- **Version 0.6**
  - Add method `poll_speaker` that returns the last changes made to properties since the last poll.
  
- **Version 0.5**
  - Add option to pass existing `session=aiohttp.ClientSession()` to `KefAsyncConnector`.
  - Add method `close_session` and `resurect_session`

- **Version 0.4**
  - Add `KefAsyncConnector`. A class with the same functionality as `KefConnector` but with async properties and methods.

- **Version 0.3**
  - ⚠️ _Breaking change :_ `get_song_information()` now returns a dictionary, no longer a tuple
  - add property `mac_address` that returns the MAC address of the speaker as a string
  - add property `speaker_name` that returns the friendly speaker name as defined in the KEF Connect app onboarding process

- **Version 0.2**
  - correct a bug in `power_on` and `shutdown` 

- **Version 0.1**
  - first version

## 🔬 Development Notes

### KEF XIO Soundbar Investigation

The XIO soundbar has been tested and confirmed to support all features. Additional XIO-specific findings:

**Confirmed Features:**
- **Sound Profiles**: Six modes confirmed (default, music, movie, night, dialogue, direct) - all stored in lowercase in API
- **Wall Mounted**: Boolean field indicating soundbar mounting configuration
- **Stability**: Field exists (always `0`), purpose unknown - may be related to wall mounting or vibration control

**API Details:**
- XIO uses same `kef:eqProfile/v2` endpoint as other speakers
- All 25 standard fields present
- 3 additional fields: `soundProfile`, `wallMounted`, `stability`

**Known Limitations:**
- Some EQ settings may only be visible when device is actively playing audio
- `isKW2` toggle mentioned in app not found in API responses (may be app-only UI element)

**Home Assistant Integration:**

Recommended HA entities for firmware updates:
1. **sensor.kef_speaker_firmware** - Current firmware version with model/name attributes
2. **button.kef_speaker_check_update** - Trigger update check with `check_for_firmware_update()`
3. **binary_sensor.kef_speaker_update_available** - Update availability from check response
4. **button.kef_speaker_install_update** - Install with `install_firmware_update()` (show warning)
5. **sensor.kef_speaker_update_status** - Progress tracking via `get_firmware_update_status()`

Recommended HA entities for XIO soundbar:
- **select.xio_sound_profile** - Six profiles via `get_sound_profile()` / `set_sound_profile()`
- **binary_sensor.xio_wall_mounted** - Config via `get_wall_mounted()` / `set_wall_mounted()`

**XIO Development - Real-time Monitoring:**
```python
import pykefcontrol as pkf
import time

speaker = pkf.KefConnector('192.168.16.26')
previous = None

print("Monitoring XIO - change settings in KEF app...")
while True:
    current = speaker.get_eq_profile()['kefEqProfileV2']
    if previous and current != previous:
        for key in current:
            if current[key] != previous.get(key):
                print(f"{key}: {previous[key]} -> {current[key]}")
    previous = current.copy()
    time.sleep(1)
```

See test suite in `testing.py` for complete feature coverage (22 automated tests).

---

## 🏠 Home Assistant Integration Notes

### Profile Management in Home Assistant

The Home Assistant integration for KEF speakers uses **HA's native Storage API** instead of the JSON file-based ProfileManager included in this library. This provides better integration with HA's backup system and follows HA best practices.

**For Home Assistant Integration Developers:**

Use `homeassistant.helpers.storage.Store` for profile storage:

```python
from homeassistant.helpers.storage import Store
from datetime import datetime

STORAGE_VERSION = 1
STORAGE_KEY = "kef_connector.profiles"

class KefProfileStorage:
    """Manage KEF EQ profiles using HA Storage API."""

    def __init__(self, hass, speaker_mac):
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{speaker_mac}")

    async def async_save_profile(self, name, profile_data, description=""):
        """Save profile to HA storage (.storage/kef_connector.profiles.{mac})."""
        profiles = await self.store.async_load() or {}
        profiles[name] = {
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat() if name not in profiles
                         else profiles[name].get("created_at"),
            "modified_at": datetime.now().isoformat(),
            "profile_data": profile_data
        }
        await self.store.async_save(profiles)

    async def async_load_profile(self, name):
        """Load profile from HA storage."""
        profiles = await self.store.async_load() or {}
        if name not in profiles:
            raise ValueError(f"Profile '{name}' not found")
        return profiles[name]["profile_data"]

    async def async_list_profiles(self):
        """List all saved profiles."""
        profiles = await self.store.async_load() or {}
        return list(profiles.keys())
```

**Integration with media_player entity:**

```python
@property
def sound_mode(self):
    """Return current profile name from speaker."""
    return self.coordinator.data.get("profile_name", "Expert")

@property
def sound_mode_list(self):
    """Return list of saved profiles."""
    return self._cached_profile_list

async def async_select_sound_mode(self, sound_mode):
    """Load and apply saved profile."""
    profile_data = await self._profile_storage.async_load_profile(sound_mode)
    await self.coordinator.speaker.set_eq_profile(profile_data)
    await self.coordinator.async_request_refresh()
```

**Key points:**
- ✅ Profiles stored per-speaker using MAC address: `.storage/kef_connector.profiles.XX_XX_XX_XX_XX_XX`
- ✅ Integrated with HA backups automatically
- ✅ Fully async operation
- ✅ Use `sound_mode` entity feature for profile selection
- ✅ Add custom services for save/delete/rename operations

---

## 📋 API Discovery & Testing

Complete KEF speaker API documentation from APK analysis is available in **[apk_analysis.md](apk_analysis.md)**.

This includes:
- 57 newly discovered API methods (doubles library capability to 103 methods)
- Complete endpoint catalog (121 endpoints tested)
- Model-specific feature comparison (LSX II, LSX II LT, XIO)
- Implementation roadmap with code examples

To test API compatibility on your speakers, run:
```bash
python apk_analysis.py --host YOUR_SPEAKER_IP --verbose
```

The analysis achieved 98% feature parity with the KEF Connect app.

## 📖 Developer Documentation

For detailed technical documentation, architecture notes, and AI assistant context, see **[CLAUDE.md](CLAUDE.md)**.

---

## 📚 Sources

KEF speaker model information sourced from:
- [KEF LS Wireless Collection](https://international.kef.com/collections/ls-wireless-collection)
- [KEF XIO Soundbar](https://us.kef.com/products/xio-soundbar)
- [KEF Coda W](https://us.kef.com/products/coda-w)
- [KEF Muo](https://us.kef.com/products/muo)
- [What Hi-Fi: KEF wireless speaker systems compared](https://www.whathifi.com/advice/kef-wireless-speaker-systems-compared-from-lsx-ii-to-ls60-which-one-should-you-buy)
