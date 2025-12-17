# 🔉 pykefcontrol 
Python library for controlling KEF speakers : LS50WII, LSX II and LS60

⚠️ **Read the changelog to see breaking changes.**
For the **async** version, please read [this section](#️-specificity-of-kefasyncconnector)

🏠️ **For the Home Assistant integration, please see [hass-kef-connector](https://github.com/N0ciple/hass-kef-connector)**

- [🔉 pykefcontrol](#-pykefcontrol)
  - [📄 General Informations](#-general-informations)
  - [⬇️ Installation](#️-installation)
  - [⚙️ Usage](#️-usage)
    - [👨‍💻 Get the IP address](#-get-the-ip-address)
    - [🎚️ Control the speaker with pykefcontrol](#️-control-the-speaker-with-pykefcontrol)
      - [First Step](#first-step)
      - [Available features](#available-features)
      - [Advanced features](#advanced-features)
  - [🕵️ Specificity of `KefAsyncConnector`](#️-specificity-of-kefasyncconnector)
    - [Renaming of property setters](#renaming-of-property-setters)
  - [📜 Changelog](#-changelog)
  

## 📄 General Informations
This library works with the KEF LS50 Wireless II, LSX II and LS60 only. If you are searching for a library for the first generation LS50W or LSX, you can use [aiokef](https://github.com/basnijholt/aiokef).
Pykefcontrol has 2 main components: `KefConnector` and `KefAsyncConnector`. The first one can be used in all classic scripts and python programs, whereas the second one (`KefAsyncConnector`) can be used in asynchronous programs.

### Supported KEF Speakers

All KEF W2 platform speakers with network connectivity (WiFi/Ethernet) are supported:

| Model | Type | Physical Inputs | Features | Tested |
|---|---|---|---|---|
| **LS50 Wireless II** | Bookshelf | WiFi, BT, Optical, USB, Analogue, HDMI | DSP, EQ, Sub out, HDMI eARC, MAT | ⚠️ Not tested |
| **LS60 Wireless** | Floorstanding | WiFi, BT, Optical, USB, Analogue | DSP, EQ, Sub out, MAT | ⚠️ Not tested |
| **LSX II** | Compact bookshelf | WiFi, BT, Optical, USB, Analogue | DSP, EQ, Sub out | ✅ Tested |
| **LSX II LT** | Compact bookshelf | WiFi, BT, Optical, USB | DSP, EQ, Sub out | ✅ Tested |
| **XIO Soundbar** | Soundbar (5.1.2) | WiFi, BT, Optical, HDMI eARC | DSP, EQ, Dolby Atmos, DTS:X, Sound profiles, Dialogue mode | ✅ Tested |

**Incompatible Models:**
- **Coda W, Muo** - Bluetooth-only, no network API
- **LS50 Wireless (Gen 1), LSX (Gen 1)** - Use [aiokef](https://github.com/basnijholt/aiokef) instead

### Current Implementation Status

**Implemented (v0.9):**
- ✅ **46 core methods** - Power, volume, source control, playback, queuing
- ✅ **36 DSP/EQ methods** - Complete DSP control (desk mode, wall mode, bass extension, treble, balance, phase correction, high-pass filter, audio polarity)
- ✅ **10 subwoofer methods** - Enable, gain, preset, low-pass, polarity, stereo mode
- ✅ **3 firmware methods** - Check updates, get status, install updates
- ✅ **10 profile methods** - Save/load/list/delete/rename/export/import EQ profiles with metadata
- ✅ **6 XIO methods** - Sound profiles (6 modes), dialogue enhancement, wall mount detection

**Discovered but not yet implemented (57 methods):**
- 📋 **Volume Management** (6 methods) - Per-input default volumes, volume behavior settings
- 📋 **Network Diagnostics** (6 methods) - Internet ping, stability check, speed test
- 📋 **System Behavior** (8 methods) - Auto-switch HDMI, standby modes, startup tone, wake source
- 📋 **LED Controls** (5 methods) - Front LED, standby LED, top panel controls (XIO)
- 📋 **Remote Control** (7 methods) - IR learning, remote buttons
- 📋 **XIO Calibration** (3 methods) - Acoustic room calibration
- 📋 **BLE Firmware** (5 methods) - Bluetooth module updates (XIO)
- 📋 **Device Info** (6 methods) - Model detection, serial numbers, capabilities
- 📋 **Privacy/Streaming** (4 methods) - Analytics, streaming service settings
- 📋 **Advanced Operations** (5 methods) - Factory reset, speaker pairing
- 📋 **Network Management** (2 methods) - WiFi scanning, network setup

See **[apk_analysis.md](apk_analysis.md)** for complete API documentation and implementation roadmap.

## ⬇️ Installation 
To install pykefcontrol, you can use pip : 
```shell
pip install pykefcontrol
```

You can make sure you have the latest version by typing:
`>>> print(pykefcontrol.__version__)`

Currently, the latest version is version `0.9`

## ⚙️ Usage

### 👨‍💻 Get the IP address
To use the pykefcontrol library, you need to know the IP address of your speakers. To do so, you can have a look at your router web page, or check in the KEF Connect app by doing the following :
 1. Launch the KEF Connect app
 2. Tap the gear icon on the bottom right
 3. Then your speaker name (It should be right below your profile information)
 4. Finally, the little circled "i" next to your speaker name in the _My Speakers_ section
 5. You should find your IP address in the "IP address" section under the form `www.xxx.yyy.zzz`, where `www`, `xxx`, `yyy` and `zzz` are integers between `0` and `255`.

### 🎚️ Control the speaker with pykefcontrol
Once pykefcontrol is installed and you have your KEF Speaker IP address, you can use pykefcontrol in the following way :

#### First Step

☝️ _For the **async** version, please read the section_ [🕵️ Specificity of `KefAsyncConnector`](#️-specificity-of-kefasyncconnector).

First, import the class and create a `KefConnector` object :
```python
from pykefcontrol.kef_connector import KefConnector
my_speaker = KefConnector("www.xxx.yyy.zzz")
```
⚠️ Do not forget to replace `www.xxx.yyy.zzz` with your speaker IP address. You should give your IP address as a string. It's to say that you should leave the quotation marks `"` around the IP address

#### Available features

Once the `my_speaker` object is created, you can use it in the following ways :

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
# Returns (enabled: bool, db_value: float)
enabled, db = my_speaker.get_desk_mode()
print(f"Desk mode: {enabled}, attenuation: {db} dB")

# Enable desk mode with -3dB attenuation (range: -10.0 to 0.0 dB)
my_speaker.set_desk_mode(enabled=True, db_value=-3.0)

# Disable desk mode
my_speaker.set_desk_mode(enabled=False)

# Wall Mode - compensates for speaker placement near walls
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
stereo = my_speaker.get_subwoofer_stereo()  # Returns bool
my_speaker.set_subwoofer_stereo(False)  # False=mono, True=stereo

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
```

### EQ Profile Management

Save, load, and manage custom EQ profiles. Profiles are stored as JSON files and can be shared across speakers or backed up.

**Profile Storage:**
- Profiles are saved to `~/.kef_profiles/` (or `/config/.kef_profiles/` in Home Assistant)
- Each profile includes all DSP/EQ settings, metadata, and timestamps
- Profiles can be exported/imported as JSON files for sharing or backup

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

#### Dialogue Enhancement

Dialogue mode enhances speech clarity independently of the sound profile. This is useful for content with hard-to-hear dialogue without switching to the dialogue sound profile:

```python
# Get dialogue enhancement state
enabled = my_speaker.get_dialogue_mode()
print(f"Dialogue enhancement: {'On' if enabled else 'Off'}")

# Enable dialogue enhancement (works with any sound profile)
my_speaker.set_dialogue_mode(True)

# Disable dialogue enhancement
my_speaker.set_dialogue_mode(False)

# Example: Enhance dialogue while keeping music profile
my_speaker.set_sound_profile("music")
my_speaker.set_dialogue_mode(True)  # Add dialogue boost to music profile
```

**Async version:**
```python
enabled = await my_speaker.get_dialogue_mode()
await my_speaker.set_dialogue_mode(True)
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

**Information polling**

Pykefcontrol offers a polling functionality. Instead of manually fetching all parameters to see what has changed, you can use the method `poll_speaker`. This method returns the updated properties since the last time the changes were polled. If multiple changes are made to the same property, only the last change will be kept. It is technically possible to track all the changes to a property since the last poll, although it is not implemented. Please submit an issue if you need such a feature.
`poll_speaker` will return a dictionary whose keys are the names of the properties which have been updated.

`poll_speaker` arguments:

| argument      | required   | default value | comment |
| ------------- | ---------- | ------------- | ------- |
| `timeout`     | *Optional* | `10`          |  `timeout` is in seconds. If no change has been made since the last poll when you call `poll_speaker`, the method will wait for changes during `timeout` seconds for new changes. If there is a change before the end of the timeout, `poll_speaker` will return them immediately and stop monitoring changes. If no changes are made, the method will return an empty dictionary.  ⚠️ the real timeout is `timeout`+ 0.5 seconds. The speaker will wait for `timeout` seconds before returning an empty dictionary if no changes are made. Therefore it is necessary to add a small margin in the python function to account for processing/networking time. Please submit an issue if you feel that this parameter needs tweaking. |
| `song_status` | *Optional* | `False`    | **Deprecated**, please use `poll_song_status` instead |
| `poll_song_status` | *Optional* | `False` |if `poll_song_status` if set to `True`, it will poll the song status (how many miliseconds of the current song have been played so far). If a song is playing and `poll_song_status` is set to `True`, `poll_speaker` will return almost imediately since `song_status` is updated at each second. This is forcing you to poll agressively to get other events. By default it is set to `False` in order to track other events more efficiently. |

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
This function is used internally by pykefcontrol and returns a JSON output with a lot of information. You might want to use them to get extra information such as the artwork/album cover URL, which does not have a dedicated function _yet_ in pykefcontrol.

```python
# Get currently playing media information
my_speaker._get_player_data()
# (output example) >>> {'trackRoles': {'icon': 'http://www.xxx.yyy.zzz:80/file/stream//tmp/temp_data_airPlayAlbum_xxxxxxxxx', 'title': 'I Want To Break Free', 'mediaData': {'resources': [{'duration': 263131}], 'metaData': {'album': 'Greatest Hits', 'artist': 'Queen'}}}, 'playId': {'systemMemberId': 'kef_one-xxxxxxxx', 'timestamp': 676181357}, 'mediaRoles': {'audioType': 'audioBroadcast', 'title': 'AirPlay', 'doNotTrack': True, 'type': 'audio', 'mediaData': {'resources': [{'mimeType': 'audio/unknown', 'uri': 'airplay://'}], 'metaData': {'serviceID': 'airplay', 'live': True, 'playLogicPath': 'airplay:playlogic'}}}, 'state': 'playing', 'status': {'duration': 263131, 'playSpeed': 1}, 'controls': {'pause': True, 'next_': True, 'previous': True}}

```

## 🕵️ Specificity of `KefAsyncConnector`

Pykefcontrol offers an **asynchronous connector** with the same feature set as the synchronous connector. However, there are a few changes in the property setters. You can no longer use `my_speaker.volume = 28` to set a property. You have to use the setter like so: `await my_speaker.set_volume(28)`.

The actions you make with `KefAsyncConnector` should be embedded in an async function. Here is a quick example :

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

**However**, to have an asynchronous property setter, the way to set properties has changed. You should use the specific setter. For a `property`, the setter is called `set_property`. As you can see in the example script above, to set the volume, use `set_volume`. Here is the list of properties with such setters : 

- volume : use `set_volume`
- state : use `set_state`
- source : use `set_source`

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

### ✅ Phase 1: Profile Management (COMPLETED)
- ✅ Save/load/manage EQ profiles
- ✅ 10 methods implemented (sync & async)
- ✅ JSON storage with metadata
- ✅ Import/export functionality
- ✅ Tested on Kantoor speaker (.22)

### ⏳ Phase 2: XIO Soundbar Features (NEXT)
**Target:** Sound profiles, dialogue mode, HDMI auto-switch
- Sound profile control (default/music/movie/night/dialogue/direct)
- Dialogue enhancement mode
- Subwoofer output control
- Auto-switch to HDMI

### 📋 Upcoming Phases
- **Phase 3:** Volume per input defaults (WiFi/Bluetooth/Analog/etc)
- **Phase 4:** Network diagnostics (stability, speed test, packet loss)
- **Phase 5:** Speaker status & behavior control
- **Phase 6:** Room calibration (IPT) control
- **Phase 7:** BLE firmware updates (XIO KW2 subwoofer)
- **Phase 8-10:** Streaming settings, privacy controls, advanced DSP

**Progress:** 10/50 methods complete (~20%)

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

---

## 📚 Sources

KEF speaker model information sourced from:
- [KEF LS Wireless Collection](https://international.kef.com/collections/ls-wireless-collection)
- [KEF XIO Soundbar](https://us.kef.com/products/xio-soundbar)
- [KEF Coda W](https://us.kef.com/products/coda-w)
- [KEF Muo](https://us.kef.com/products/muo)
- [What Hi-Fi: KEF wireless speaker systems compared](https://www.whathifi.com/advice/kef-wireless-speaker-systems-compared-from-lsx-ii-to-ls60-which-one-should-you-buy)
