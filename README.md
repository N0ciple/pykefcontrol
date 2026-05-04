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

## ⬇️ Installation 
To install pykefcontrol, you can use pip : 
```shell
pip install pykefcontrol
```

You can make sure you have the latest version by typing:
`>>> print(pykefcontrol.__version__)`

Currently, the latest version is version `0.9.3`

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
 
## 📜 Changelog
- **version 0.9.3**
  - Fix LS60 support: `setData` now uses POST for LS60 (matches LS50WII / LSXII behavior).
- **version 0.9.2**
  - Add LSX II support: `setData` now uses POST for LSX II (matches LS50WII / LSXIILT behavior).
- **version 0.9.1**
  - Fix issue with new LSXIILT firmware: `setData` now uses POST for LSXIILT.
- **version 0.9**
  - Switch from GET to POST for `setData` on LS50WII.
- **version 0.8**
  - Add codec information and WiFi monitoring properties.
  - Add generic API methods.
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
