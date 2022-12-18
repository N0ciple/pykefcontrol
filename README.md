### ⚠️ Help test Pykefcontrol on the **LSX 2** and **LS60**
Pykefcontrol should be compatible with **LSX 2** and **LS60**, but tests are needed to ensure it is the case since I do not have these models at home!
If you want to help test the library for such models, please clone the repository, install the testing requirements, execute the testing script and report the output to [this issue](https://github.com/N0ciple/pykefcontrol/issues/2)

```
git clone https://github.com/N0ciple/pykefcontrol.git
cd pykefcontrol
pip install -r testing_reqs.txt
python testing.py
```
Thank you for your help ! 👌

# 🔉 pykefcontrol 
Python library for controlling the KEF LS50 Wireless II

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
This library works with the KEF LS50 Wireless II only. If you are searching for a library for the first generation LS50W, you can use [aiokef](https://github.com/basnijholt/aiokef).
Pykefcontrol has 2 main components: `KefConnector` and `KefAsyncConnector`. The first one can be used in all classic scripts and python programs, whereas the second one (`KefAsyncConnector`) can be used in asynchronous programs.

## ⬇️ Installation 
To install pykefcontrol, you can use pip : 
```shell
pip install pykefcontrol
```

You can make sure you have the latest version by typing:
`>>> print(pykefcontrol.__version__)`

Currently, the latest version is version `0.6.1`

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
| `song_status` | *Optional* | `False`       |  if `song_status` if set to `True`, it will poll the song status (how many miliseconds of the current song have been played so far). If a song is playing and `song_status` is set to `True`, `poll_speaker` will return almost imediately since `song_status` is updated at each second. This is forcing you to poll agressively to get other events. By default it is set to `False` in order to track other events more efficiently. |

```python
my_speaker.poll_speaker(timeout=3) # example of a 3 seconds timeout
# (output example) >>> {}  # it will return an empty dict if no changes were made

# no suppose you start playing a song
my_speaker.poll_speaker() # timeout is 10 seconds by default
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
my_speaker.poll_speaker()
# (output example) >>> {'song_status': 175085, 'volume': 32}
#
# -> in this case it returns both "song_status" (because the song kept playing), 
# and "volume" because you updated the volume

# if you do not want to poll the song status
my_speaker.poll_speaker(song_satus=False)
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
  await my_speaker.tunr_on()
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
