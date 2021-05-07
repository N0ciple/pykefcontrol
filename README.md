# 🔉 pykefcontrol 
Python library for controling the KEF LS50 Wireless II



## 📄 General Informations 
This library works with the KEF LS50 Wireless II only. If you are searching a library for the first generation LS50W, you can use [aiokef](https://github.com/basnijholt/aiokef)

## ⬇️ Installation 
To install pykefcontrol, you can use pip : 
```shell
pip install pykefcontrol
```

You can make sure you have the last version by typing :
`>>> print(pykefcontrol.__version__)`

Currently, the last version is version `0.1`

## ⚙️ Usage

### 👨‍💻 Get the IP address
 In order to use the pykefcontrol library, you need to know the IP address of your speakers. To do so, you can have a look at your router web page, or check in the KEF Connect app by doing the following :
 1. Launch the KEF Connect app
 2. Tap the gear icon on the bottom right
 3. Then your speaker name (It should be right bellow your profile informations)
 4. Finally the little circled "i" next to your speaker name in the _My Speakers_ section
 5. You should find your IP address in the "IP address" section under the form `www.xxx.yyy.zzz`, where `www`,`xxx`,`yyy` and `zzz` are integers between `0` and `255`.

### 🎚️ Control the speaker with pykefcontrol
Once pykefcontrol is installed and you have your KEF Speaker IP address, you can use pykefcontrol in the following way :

#### First Step

First, import the class and create a `KefConnector` object :
```python
from pykefcontrol.kef_connector import KefConnector
my_speaker = KefConnector("www.xxx.yyy.zzz")
```
⚠️ Dont forget to replace `www.xxx.yyy.zzz` by your speaker IP address. You should give your IP address as a string. It's to say that you should leave the quotation marks `"` arround the IP address

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
my_speaker.volume # it is not a method so it does not requires parenthesis
# (output example) >>> 23

# Set volume
my_speaker.volume = 42 # 42 for example but it can by any integer between 0 and 100.

# Set volume (alternative way)
my_speaker.set_volume(42) # 42 for example but it can by any integer between 0 and 100.
```

**Playback info**
```python
# Check if the speaker is playing : it returns a boolean (either True or False)
my_speaker.is_playing # it is not a method so it does not requires parenthesis
# (output example) >>> True

# Get current media information : it retuns a tuple of string ('title','artist','album')
# (works on songs/podcast/radio. It may works on other media but I have not tested it yet)
my_speaker.get_song_information
# (output example) >>> ('Money','Pink Floyd','The Dark Side of the Moon')

# Get media length in miliseconds : it returns a integer representing the song length in ms
my_speaker.song_length # it is not a method so it does not requires parenthesis
# (output example) >>> 300251

# Get song progress : it returns the current playhead position in the current track in ms
my_speaker.song_status # it is not a method so it does not requires parenthesis
# (output example) >>> 136900
```


#### Advanced features
These function are used internally by pykefcontrol and return a json output with a lot of informations. You might want to use them to get extra information such as the artwork/album cover URL, wich is not currently supported in pykefcontrol

```python
# Get currently playing media information
my_speaker._get_player_data()
# (output example) >>> {'trackRoles': {'icon': 'http://www.xxx.yyy.zzz:80/file/stream//tmp/temp_data_airPlayAlbum_xxxxxxxxx', 'title': 'I Want To Break Free', 'mediaData': {'resources': [{'duration': 263131}], 'metaData': {'album': 'Greatest Hits', 'artist': 'Queen'}}}, 'playId': {'systemMemberId': 'kef_one-xxxxxxxx', 'timestamp': 676181357}, 'mediaRoles': {'audioType': 'audioBroadcast', 'title': 'AirPlay', 'doNotTrack': True, 'type': 'audio', 'mediaData': {'resources': [{'mimeType': 'audio/unknown', 'uri': 'airplay://'}], 'metaData': {'serviceID': 'airplay', 'live': True, 'playLogicPath': 'airplay:playlogic'}}}, 'state': 'playing', 'status': {'duration': 263131, 'playSpeed': 1}, 'controls': {'pause': True, 'next_': True, 'previous': True}}

```

## 📜 Changelog
- ''Version 0.2**
  - correct a bug in `power_on` and `shutdown` 

- **Version 0.1**
  - first version
