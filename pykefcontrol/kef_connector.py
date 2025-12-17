import requests
import time
import warnings
import json
from html.parser import HTMLParser
from .profile_manager import ProfileManager

# Make aiohttp optional - only required for async KefAsyncConnector
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None


# EQ/DSP Setting Constants
BASS_EXTENSION_MODES = ["standard", "less", "extra"]
AUDIO_POLARITY_MODES = ["normal", "inverted"]
SUBWOOFER_POLARITY_MODES = ["normal", "inverted"]
SOUND_PROFILES = ["default", "music", "movie", "night", "dialogue", "direct"]

# Subwoofer presets (auto-adjust settings based on subwoofer model)
SUBWOOFER_PRESETS = [
    "custom", "kc62", "kf92", "kube8b", "kube10b",
    "kube12b", "kube15", "t2"
]

# Desk Mode: -10dB to 0dB in 0.5dB steps (0-20, where 20=0dB, 0=-10dB)
DESK_MODE_SETTING_MIN = 0
DESK_MODE_SETTING_MAX = 20
DESK_MODE_SETTING_NEUTRAL = 20  # 0dB

# Wall Mode: -10dB to 0dB in 0.5dB steps (0-20, where 20=0dB, 0=-10dB)
WALL_MODE_SETTING_MIN = 0
WALL_MODE_SETTING_MAX = 20
WALL_MODE_SETTING_NEUTRAL = 20  # 0dB

# Treble: -3dB to +3dB in 0.25dB steps (0-24, where 12=0dB)
TREBLE_AMOUNT_MIN = 0
TREBLE_AMOUNT_MAX = 24
TREBLE_AMOUNT_NEUTRAL = 12  # 0dB

# Balance: L30-C-R30 (0-60, where 30=center)
BALANCE_MIN = 0
BALANCE_MAX = 60
BALANCE_CENTER = 30

# High-pass frequency: 50-120Hz in 2.5Hz steps (0-28, where 0=50Hz)
HIGH_PASS_FREQ_MIN = 0
HIGH_PASS_FREQ_MAX = 28

# Sub out low-pass frequency: 40-250Hz in 2.5Hz steps (0-84, where 0=40Hz)
SUB_LP_FREQ_MIN = 0
SUB_LP_FREQ_MAX = 84

# Subwoofer gain: -10dB to +10dB in 1dB steps (0-20, where 10=0dB)
SUB_GAIN_MIN = 0
SUB_GAIN_MAX = 20
SUB_GAIN_NEUTRAL = 10  # 0dB

# KEF Firmware Release Notes URL
KEF_RELEASE_NOTES_URL = "https://assets.kef.com/pm/pm_firmware/release_notes.html"


class _KEFReleaseNotesParser(HTMLParser):
    """Parser for KEF firmware release notes HTML"""

    def __init__(self):
        super().__init__()
        self.firmware_data = {}
        self.current_model = None
        self.in_dl = False
        self.current_date = None
        self.current_version = None
        self.current_notes = []
        self.in_dd = False
        self.dd_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "h3":
            self.current_model = None  # Will be set in handle_data
        elif tag == "dl" and self.current_model:
            self.in_dl = True
        elif tag == "dt" and self.in_dl:
            self.current_date = None  # Will be set in handle_data
        elif tag == "dd" and self.in_dl:
            self.in_dd = True
            self.dd_text = ""

    def handle_endtag(self, tag):
        if tag == "dd" and self.in_dd:
            self.in_dd = False
            text = self.dd_text.strip()
            if text:
                # Check if this is a version line
                if self.current_date and not self.current_version:
                    # Remove "Version " prefix if present
                    if text.startswith("Version "):
                        text = text[8:]  # Remove "Version "
                    # Split version from notes if they're on same line
                    if "•" not in text:
                        # Check if version ends with lowercase letter (likely note text)
                        # Versions are like "2.6" followed immediately by "Add..."
                        import re
                        match = re.match(r'^(\d+\.?\d*)(.+)?$', text)
                        if match:
                            self.current_version = match.group(1)
                            if match.group(2):
                                # There's additional text (release notes)
                                self.current_notes.append(match.group(2).strip())
                        else:
                            self.current_version = text
                    else:
                        # Version and note are combined with bullet, split them
                        parts = text.split("•", 1)
                        self.current_version = parts[0].strip()
                        if len(parts) > 1:
                            self.current_notes.append(parts[1].strip())
                # Check if this is a note line (starts with bullet)
                elif text.startswith("•"):
                    self.current_notes.append(text[1:].strip())
        elif tag == "dl" and self.in_dl:
            # Save the collected data
            if self.current_model and self.current_version:
                if self.current_model not in self.firmware_data:
                    self.firmware_data[self.current_model] = []
                self.firmware_data[self.current_model].append({
                    'date': self.current_date,
                    'version': self.current_version,
                    'notes': self.current_notes
                })
            self.in_dl = False
            self.current_date = None
            self.current_version = None
            self.current_notes = []

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return

        # Check for model name in h3
        if "Firmware" in data and not self.in_dl:
            # Extract model name (e.g., "LSX II Speaker Firmware" -> "LSX II")
            model = data.replace(" Speaker Firmware", "").replace(" Firmware", "").strip()
            self.current_model = model
        # Collect date from dt
        elif self.in_dl and not self.in_dd and data and not self.current_date:
            # This is a date line
            self.current_date = data
        # Collect text from dd
        elif self.in_dd:
            self.dd_text += data


def _normalize_model_name(model_name):
    """Normalize model name for matching between API and release notes.

    Args:
        model_name (str): Model name from API (e.g., "LSXII") or release notes (e.g., "LSX II")

    Returns:
        str: Normalized model name with space (e.g., "LSX II")
    """
    # Handle common API model names
    model_map = {
        "LSXII": "LSX II",
        "LSXIILT": "LSX II LT",
        "LS50WirelessII": "LS50 Wireless II",
        "LS60Wireless": "LS60 Wireless",
        "XIO": "XIO Soundbar",
    }

    # Check if it's a known mapping
    if model_name in model_map:
        return model_map[model_name]

    # Otherwise, try to add space before "II" if missing
    if "II" in model_name and " II" not in model_name:
        model_name = model_name.replace("II", " II")

    return model_name


def get_kef_firmware_releases(model_filter=None, timeout=10):
    """Fetch and parse KEF firmware release notes.

    Args:
        model_filter (str, optional): Filter for specific model (e.g., "LSX II", "LSX II LT", or "LSXII")
        timeout (int, optional): Request timeout in seconds

    Returns:
        dict: Dictionary mapping model names to list of firmware releases
              Each release contains: date, version, and notes

    Example:
        >>> releases = get_kef_firmware_releases(model_filter="LSX II")
        >>> latest = releases["LSX II"][0]
        >>> print(f"Latest LSX II: {latest['version']} ({latest['date']})")
        Latest LSX II: 2.6 (10-Nov-2025)
        >>> print(f"Changes: {', '.join(latest['notes'])}")
        Changes: Add support for non-Wi-Fi mode

        >>> # Can also use API model name format
        >>> releases = get_kef_firmware_releases(model_filter="LSXII")
        >>> # Returns same data for "LSX II"

    Note:
        - Release notes use display version format (e.g., "2.6")
        - API firmware_version uses different format (e.g., "V26120")
        - Version mapping between formats is not provided by KEF
        - Model names are automatically normalized (LSXII -> LSX II)
    """
    try:
        response = requests.get(KEF_RELEASE_NOTES_URL, timeout=timeout)
        response.raise_for_status()

        parser = _KEFReleaseNotesParser()
        parser.feed(response.text)

        if model_filter:
            # Normalize the filter
            normalized_filter = _normalize_model_name(model_filter)
            # Return only the filtered model
            return {k: v for k, v in parser.firmware_data.items() if k == normalized_filter}
        else:
            return parser.firmware_data

    except Exception as e:
        # Return empty dict on error
        return {}


class KefConnector:
    def __init__(self, host, port=80, profile_dir=None):
        self.host = host
        self.port = port
        self.previous_volume = self.volume
        self.last_polled = None
        self.polling_queue = None
        self._previous_poll_song_status = False
        self._profile_manager = ProfileManager(profile_dir)

    def power_on(self):
        self.status = "powerOn"

    def shutdown(self):
        self.source = "standby"

    def mute(self):
        self.previous_volume = self.volume
        self.volume = 0

    def unmute(self):
        """
        unmute speaker
        """
        self.volume = self.previous_volume

    def toggle_play_pause(self):
        """
        Toogle play/pause
        """
        self._track_control("pause")

    def next_track(self):
        """
        Next track
        """
        self._track_control("next")

    def previous_track(self):
        """
        Previous track
        """
        self._track_control("previous")

    def _track_control(self, command):
        """
        toogle play/pause
        """
        payload = {
            "path": "player:player/control",
            "roles": "activate",
            "value": """{{"control":"{command}"}}""".format(command=command),
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def set_volume(self, volume):
        """
        Set volume
        """
        self.volume = volume

    def _get_player_data(self):
        """
        Is the speaker currently playing
        """
        payload = {
            "path": "player:player/data",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]

    def get_song_information(self, song_data=None):
        """
        Get song title, album and artist
        """
        if song_data == None:
            song_data = self._get_player_data()
        info_dict = dict()
        info_dict["title"] = song_data.get("trackRoles", {}).get("title")

        metadata = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
        )

        info_dict["artist"] = metadata.get("artist")
        info_dict["album"] = metadata.get("album")
        # Use albumArtist if available, otherwise fallback to artist
        album_artist = metadata.get("albumArtist")
        info_dict["album_artist"] = album_artist if album_artist else metadata.get("artist")
        info_dict["cover_url"] = song_data.get("trackRoles", {}).get("icon", None)
        info_dict["service_id"] = metadata.get("serviceID")

        return info_dict

    def get_audio_codec_information(self, player_data=None):
        """
        Get audio codec information from player data.
        Returns dict with codec, sample rate, and channel information.
        """
        try:
            if player_data is None:
                player_data = self._get_player_data()

            codec_dict = {}
            active_resource = (
                player_data.get("trackRoles", {})
                .get("mediaData", {})
                .get("activeResource", {})
            )

            if active_resource:
                codec_dict["codec"] = active_resource.get("codec")
                codec_dict["sampleFrequency"] = active_resource.get("sampleFrequency")
                codec_dict["streamSampleRate"] = active_resource.get("streamSampleRate")
                codec_dict["streamChannels"] = active_resource.get("streamChannels")
                codec_dict["nrAudioChannels"] = active_resource.get("nrAudioChannels")

            # Get streaming service ID from metadata
            metadata = (
                player_data.get("trackRoles", {})
                .get("mediaData", {})
                .get("metaData", {})
            )
            if metadata:
                codec_dict["serviceID"] = metadata.get("serviceID")

            return codec_dict
        except Exception:
            # Silently return empty dict if codec info not available
            return {}

    def get_request(self, path, roles="value"):
        """Generic method to get data from any API path.

        Args:
            path: API path to query (e.g., "kef:eqProfile", "network:info")
            roles: API roles parameter (default: "value")

        Returns:
            JSON response from API
        """
        payload = {
            "path": path,
            "roles": roles,
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output

    def get_wifi_information(self):
        """Get WiFi information from speaker.

        Returns dict with WiFi signal strength, SSID, frequency, and BSSID.
        Returns empty dict if WiFi info is not available.
        """
        try:
            # Get network info from speaker
            network_data = self.get_request("network:info", roles="value")

            wifi_dict = {}
            network_info = (
                network_data[0].get("networkInfo", {}) if network_data else {}
            )

            if network_info:
                wireless = network_info.get("wireless", {})
                if wireless:
                    wifi_dict["signalLevel"] = wireless.get("signalLevel")
                    wifi_dict["ssid"] = wireless.get("ssid")
                    wifi_dict["frequency"] = wireless.get("frequency")
                    wifi_dict["bssid"] = wireless.get("bssid")

            return wifi_dict
        except Exception:
            # Silently return empty dict if WiFi info not available
            return {}

    def _get_polling_queue(self, song_status=False, poll_song_status=False):
        """
        Get the polling queue uuid, and subscribe to all relevant topics
        """
        payload = {
            "subscribe": [
                {"path": "settings:/mediaPlayer/playMode", "type": "itemWithValue"},
                {"path": "playlists:pq/getitems", "type": "rows"},
                {"path": "notifications:/display/queue", "type": "rows"},
                {"path": "settings:/kef/host/maximumVolume", "type": "itemWithValue"},
                {"path": "player:volume", "type": "itemWithValue"},
                {"path": "kef:fwupgrade/info", "type": "itemWithValue"},
                {"path": "settings:/kef/host/volumeStep", "type": "itemWithValue"},
                {"path": "settings:/kef/host/volumeLimit", "type": "itemWithValue"},
                {"path": "settings:/mediaPlayer/mute", "type": "itemWithValue"},
                {"path": "settings:/kef/host/speakerStatus", "type": "itemWithValue"},
                {"path": "settings:/kef/play/physicalSource", "type": "itemWithValue"},
                {"path": "player:player/data", "type": "itemWithValue"},
                {"path": "kef:speedTest/status", "type": "itemWithValue"},
                {"path": "network:info", "type": "itemWithValue"},
                {"path": "kef:eqProfile/v2", "type": "itemWithValue"},
                {"path": "settings:/kef/host/modelName", "type": "itemWithValue"},
                {"path": "settings:/version", "type": "itemWithValue"},
                {"path": "settings:/deviceName", "type": "itemWithValue"},
            ],
            "unsubscribe": [],
        }

        if song_status:
            payload["subscribe"].append(
                {"path": "player:player/data/playTime", "type": "itemWithValue"}
            )

        with requests.post(
            "http://" + self.host + "/api/event/modifyQueue", json=payload
        ) as response:
            json_output = response.json()

        # Update polling_queue property with queue uuid
        self.polling_queue = json_output[1:-1]

        # Update last polled time
        self.last_polled = time.time()

        return self.polling_queue

    def parse_events(self, events):
        """Parse events"""
        parsed_events = dict()

        for event in events:
            if event == "settings:/kef/play/physicalSource":
                parsed_events["source"] = events[event].get("kefPhysicalSource")
            elif event == "player:player/data/playTime":
                parsed_events["song_status"] = events[event].get("i64_")
            elif event == "player:volume":
                parsed_events["volume"] = events[event].get("i32_")
            elif event == "player:player/data":
                parsed_events["song_info"] = self.get_song_information(events[event])
                parsed_events["song_length"] = (
                    events[event].get("status", {}).get("duration")
                )
                parsed_events["status"] = events[event].get("state")
            elif event == "settings:/kef/host/speakerStatus":
                parsed_events["speaker_status"] = events[event].get("kefSpeakerStatus")
            elif event == "settings:/deviceName":
                parsed_events["device_name"] = events[event].get("string_")
            elif event == "settings:/mediaPlayer/mute":
                parsed_events["mute"] = events[event].get("bool_")
            else:
                if parsed_events.get("other") == None:
                    parsed_events["other"] = {}
                parsed_events["other"].update({event: events[event]})

        return parsed_events

    def poll_speaker(self, timeout=10, song_status=False, poll_song_status=False):
        """poll speaker for info"""

        if song_status:
            warnings.warn(
                "The 'song_status' parameter is deprecated and will be removed in version 0.8.0. "
                "Please use 'poll_song_status' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        # check if it is necessary to get a new queue
        # recreate a new queue if polling_queue is None
        # or if last poll was more than 50 seconds ago
        if (
            (self.polling_queue == None)
            or ((time.time() - self.last_polled) > 50)
            or (song_status != self._previous_poll_song_status)
        ):
            self._previous_poll_song_status = song_status
            self._get_polling_queue(poll_song_status=poll_song_status)

        payload = {
            "queueId": "{{{}}}".format(self.polling_queue),
            "timeout": timeout,
        }

        with requests.get(
            "http://" + self.host + "/api/event/pollQueue",
            params=payload,
            timeout=timeout + 0.5,  # add 0.5 seconds to timeout to allow for processing
        ) as response:
            json_output = response.json()

        # Process all events

        events = dict()
        # fill events lists
        for j in json_output:
            if events.get(j["path"], False):
                events[j["path"]].append(j)
            else:
                events[j["path"]] = [j]
        # prune events lists
        for k in events:
            events[k] = events[k][-1].get("itemValue", "updated")

        return self.parse_events(events)

    @property
    def mac_address(self):
        """Get the mac address of the Speaker"""
        """http://192.168.124.46/api/getData?path=settings:/system/primaryMacAddress&roles=value"""
        payload = {"path": "settings:/system/primaryMacAddress", "roles": "value"}

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["string_"]

    @property
    def speaker_name(self):
        """Get the friendly name of the Speaker"""
        payload = {"path": "settings:/deviceName", "roles": "value"}

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["string_"]

    @property
    def status(self):
        """Status of the speaker : standby or poweredOn"""
        payload = {"path": "settings:/kef/host/speakerStatus", "roles": "value"}

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["kefSpeakerStatus"]

    @status.setter
    def status(self, status):
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": """{{"type":"kefPhysicalSource","kefPhysicalSource":"{status}"}}""".format(
                status=status
            ),
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    @property
    def source(self):
        """
        Speaker source : standby (not powered on),
        wifi, bluetooth, tv, optic, coaxial or analog
        """
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["kefPhysicalSource"]

    @source.setter
    def source(self, source):
        """
        Set spaker source, if speaker in standby, it powers on the speaker.
        Possible sources : wifi, bluetooth, tv, optic, coaxial or analog
        """
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": """{{"type":"kefPhysicalSource","kefPhysicalSource":"{source}"}}""".format(
                source=source
            ),
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    @property
    def volume(self):
        """
        Speaker volume (1 to 100, 0 = muted)
        """
        payload = {
            "path": "player:volume",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["i32_"]

    @volume.setter
    def volume(self, volume):
        payload = {
            "path": "player:volume",
            "roles": "value",
            "value": """{{"type":"i32_","i32_":{volume}}}""".format(volume=volume),
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    @property
    def is_playing(self):
        """
        Is the speaker currently playing
        """
        return self._get_player_data()["state"] == "playing"

    @property
    def song_length(self):
        """
        Song length in ms
        """
        if self.is_playing:
            return self._get_player_data()["status"]["duration"]
        else:
            return None

    @property
    def song_status(self):
        """
        Progression of song
        """
        payload = {
            "path": "player:player/data/playTime",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["i64_"]

    def _get_speaker_firmware_version(self):
        """
        Get speaker firmware "release text"
        """

        payload = {
            "path": "settings:/releasetext",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0]["string_"]

    @property
    def speaker_model(self):
        """
        Speaker model
        """
        speaker_model = self._get_speaker_firmware_version().split("_")[0]
        return speaker_model

    @property
    def firmware_version(self):
        """
        Speaker firmware version
        """
        speaker_firmware_version = self._get_speaker_firmware_version().split("_")[1]
        return speaker_firmware_version

    # EQ/DSP Profile Methods
    def get_eq_profile(self):
        """Get complete EQ profile from speaker (v2 API).

        Note: Uses kef:eqProfile/v2 which returns the ACTIVE profile with
        direct dB/Hz values (not integer indices).

        Returns:
            dict: Complete EQ profile with structure:
                {
                    'type': 'kefEqProfileV2',
                    'kefEqProfileV2': {
                        'profileId': str,
                        'profileName': str,
                        'isExpertMode': bool,
                        'subwooferGain': float (dB),
                        'deskModeSetting': float (dB),
                        'trebleAmount': float (dB),
                        ... (all DSP settings)
                    }
                }

        Raises:
            Exception: If speaker communication fails
        """
        return self.get_request("kef:eqProfile/v2", roles="value")[0]

    def set_eq_profile(self, profile_dict):
        """Set complete EQ profile on speaker (v2 API).

        Args:
            profile_dict (dict): Complete profile dict as returned by get_eq_profile()
                Must include 'type' and 'kefEqProfileV2' keys

        Returns:
            bool/dict: Response from speaker (True on success)

        Raises:
            ValueError: If profile_dict structure is invalid

        Example:
            profile = speaker.get_eq_profile()
            profile['kefEqProfileV2']['subwooferGain'] = 5.0  # Direct dB value
            speaker.set_eq_profile(profile)
        """
        # Validate structure
        if not isinstance(profile_dict, dict):
            raise ValueError("profile_dict must be a dictionary")

        if 'type' not in profile_dict or profile_dict['type'] != 'kefEqProfileV2':
            raise ValueError(
                "profile_dict must have 'type' key with value 'kefEqProfileV2'"
            )

        if 'kefEqProfileV2' not in profile_dict:
            raise ValueError("profile_dict must have 'kefEqProfileV2' key")

        payload = {
            "path": "kef:eqProfile/v2",
            "roles": "value",
            "value": json.dumps(profile_dict),
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

        return json_output

    def update_dsp_setting(self, setting_name, value):
        """Update a single DSP setting without manual dict manipulation (v2 API).

        This is a convenience method that fetches the current profile,
        updates the specified DSP setting, and sends it back.

        Note: v2 API uses direct dB/Hz values, not integer indices.

        Args:
            setting_name (str): Name of the DSP setting (e.g., 'deskMode', 'subwooferGain')
            value: New value for the setting (dB for gains, Hz for frequencies, etc.)

        Returns:
            bool/dict: Response from speaker (True on success)

        Example:
            speaker.update_dsp_setting('deskMode', True)
            speaker.update_dsp_setting('subwooferGain', 5.0)  # Direct dB value
        """
        profile = self.get_eq_profile()
        profile['kefEqProfileV2'][setting_name] = value
        return self.set_eq_profile(profile)

    # EQ Profile Name Methods
    def get_profile_name(self):
        """Get the current EQ profile name.

        Returns:
            str: Current profile name

        Example:
            name = speaker.get_profile_name()
            print(f"Current profile: {name}")
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['profileName']

    def rename_profile(self, new_name):
        """Rename the current EQ profile.

        Args:
            new_name (str): New name for the profile

        Returns:
            bool/dict: Response from speaker (True on success)

        Raises:
            ValueError: If new_name is not a string or is empty

        Example:
            speaker.rename_profile("Living Room Settings")

        Note:
            This renames the currently active profile. The profile ID remains the same.
            KEF speakers do not support deleting profiles via the API.
        """
        if not isinstance(new_name, str):
            raise ValueError(f"new_name must be a string, got {type(new_name)}")
        if not new_name.strip():
            raise ValueError("new_name cannot be empty")

        return self.update_dsp_setting('profileName', new_name.strip())

    def get_profile_id(self):
        """Get the current EQ profile unique ID.

        Returns:
            str: Current profile UUID

        Example:
            profile_id = speaker.get_profile_id()
            print(f"Profile ID: {profile_id}")
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['profileId']

    # Desk Mode Methods (v2 API with direct dB values)
    def get_desk_mode(self):
        """Get desk mode setting and value (v2 API).

        Returns:
            tuple: (enabled: bool, db_value: float) where db_value is -10.0 to 0.0 dB
        """
        profile = self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['deskMode'], v2_profile['deskModeSetting'])

    def set_desk_mode(self, enabled, db_value=0.0):
        """Set desk mode enabled state and attenuation value (v2 API).

        Args:
            enabled (bool): True to enable desk mode, False to disable
            db_value (float): Desk mode attenuation in dB (-10.0 to 0.0)
                Only used if enabled=True. Default is 0.0 (no attenuation).

        Returns:
            bool/dict: Response from speaker (True on success)

        Raises:
            ValueError: If parameters are invalid

        Example:
            speaker.set_desk_mode(True, -3.0)  # Enable with -3dB attenuation
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(db_value, (int, float)):
                raise ValueError(f"db_value must be a number, got {type(db_value)}")
            if not (-10.0 <= db_value <= 0.0):
                raise ValueError(f"db_value must be between -10.0 and 0.0, got {db_value}")

        profile = self.get_eq_profile()
        profile['kefEqProfileV2']['deskMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['deskModeSetting'] = db_value
        return self.set_eq_profile(profile)

    # Wall Mode Methods (v2 API - direct dB values)
    def get_wall_mode(self):
        """Get wall mode setting and value (v2 API).

        Returns:
            tuple: (enabled: bool, db_value: float) where db_value is -10.0 to 0.0 dB
        """
        profile = self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['wallMode'], v2_profile['wallModeSetting'])

    def set_wall_mode(self, enabled, db_value=0.0):
        """Set wall mode enabled state and attenuation value (v2 API).

        Args:
            enabled (bool): True to enable wall mode, False to disable
            db_value (float): Wall mode attenuation in dB (-10.0 to 0.0)
                Only used if enabled=True. Default is 0.0 (no attenuation).

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(db_value, (int, float)):
                raise ValueError(f"db_value must be a number, got {type(db_value)}")
            if not (-10.0 <= db_value <= 0.0):
                raise ValueError(f"db_value must be between -10.0 and 0.0, got {db_value}")

        profile = self.get_eq_profile()
        profile['kefEqProfileV2']['wallMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['wallModeSetting'] = db_value
        return self.set_eq_profile(profile)

    # Bass Extension Methods (v2 API)
    def get_bass_extension(self):
        """Get bass extension setting (v2 API).

        Returns:
            str: Bass extension mode - "standard", "less", or "extra"
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['bassExtension']

    def set_bass_extension(self, mode):
        """Set bass extension mode (v2 API).

        Args:
            mode (str): Bass extension mode - "standard", "less", or "extra"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in BASS_EXTENSION_MODES:
            raise ValueError(f"mode must be one of {BASS_EXTENSION_MODES}, got {mode}")

        return self.update_dsp_setting('bassExtension', mode)

    # Sound Profile Methods (v2 API - XIO Soundbar virtualizer control)
    def get_sound_profile(self):
        """Get current sound profile (v2 API).

        Sound profiles control the virtualizer mode on XIO soundbars.
        Available on XIO soundbar models only.

        Returns:
            str: Sound profile - "default", "music", "movie", "night", "dialogue", or "direct"
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['soundProfile']

    def set_sound_profile(self, sound_profile):
        """Set sound profile (v2 API).

        Sound profiles control the virtualizer mode on XIO soundbars:
        - default: Standard virtualizer processing
        - music: Optimized for music playback
        - movie: Enhanced for movie audio
        - night: Reduced dynamic range for late-night listening
        - dialogue: Enhanced speech clarity
        - direct: No virtualizer processing (pass-through)

        Available on XIO soundbar models only.

        Args:
            sound_profile (str): Sound profile - "default", "music", "movie", "night", "dialogue", or "direct"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If sound_profile is invalid
        """
        if sound_profile not in SOUND_PROFILES:
            raise ValueError(f"sound_profile must be one of {SOUND_PROFILES}, got {sound_profile}")

        return self.update_dsp_setting('soundProfile', sound_profile)

    # Treble Methods (v2 API - direct dB values)
    def get_treble_amount(self):
        """Get treble amount (v2 API).

        Returns:
            float: Treble amount in dB (-3.0 to +3.0)
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['trebleAmount']

    def set_treble_amount(self, db_value):
        """Set treble amount (v2 API).

        Args:
            db_value (float): Treble amount in dB (-3.0 to +3.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-3.0 <= db_value <= 3.0):
            raise ValueError(f"db_value must be between -3.0 and +3.0, got {db_value}")

        return self.update_dsp_setting('trebleAmount', db_value)

    # Balance Methods (v2 API)
    def get_balance(self):
        """Get balance setting (v2 API).

        Returns:
            float: Balance position (negative=left, 0=center, positive=right)
                   Range: approximately -6.0 to +6.0
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['balance']

    def set_balance(self, position):
        """Set balance position (v2 API).

        Args:
            position (float): Balance position (negative=left, 0=center, positive=right)
                             Range: approximately -6.0 to +6.0

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If position is invalid
        """
        if not isinstance(position, (int, float)):
            raise ValueError(f"position must be a number, got {type(position)}")
        if not (-6.0 <= position <= 6.0):
            raise ValueError(f"position must be between -6.0 and +6.0, got {position}")

        return self.update_dsp_setting('balance', position)

    # Phase Correction Methods (v2 API)
    def get_phase_correction(self):
        """Get phase correction setting (v2 API).

        Returns:
            bool: True if phase correction is enabled, False otherwise
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['phaseCorrection']

    def set_phase_correction(self, enabled):
        """Set phase correction enabled state (v2 API).

        Args:
            enabled (bool): True to enable phase correction, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return self.update_dsp_setting('phaseCorrection', enabled)

    # Profile Name Methods (v2 API)
    def get_profile_name(self):
        """Get the name of the current EQ profile (v2 API).

        Returns:
            str: The profile name (e.g., "Kantoor", "Calibrated", "My Custom Profile")
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['profileName']

    def set_profile_name(self, name):
        """Set the name of the current EQ profile (v2 API).

        Args:
            name (str): The new profile name (must be a non-empty string)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If name is not a valid string
        """
        if not isinstance(name, str):
            raise ValueError(f"name must be a string, got {type(name)}")
        if not name.strip():
            raise ValueError("name cannot be empty or whitespace only")

        return self.update_dsp_setting('profileName', name.strip())

    # Wall Mounted Methods (v2 API)
    def get_wall_mounted(self):
        """Get whether the speaker is wall mounted (v2 API).

        This setting is primarily used on soundbars (like XIO) to optimize
        the sound for wall-mounted placement.

        Returns:
            bool: True if speaker is wall mounted, False otherwise
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['wallMounted']

    def set_wall_mounted(self, mounted):
        """Set whether the speaker is wall mounted (v2 API).

        Args:
            mounted (bool): True if speaker is wall mounted, False otherwise

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If mounted is not a boolean

        Note:
            This setting is primarily for soundbars and affects acoustic tuning.
        """
        if not isinstance(mounted, bool):
            raise ValueError(f"mounted must be a boolean, got {type(mounted)}")

        return self.update_dsp_setting('wallMounted', mounted)

    # XIO Soundbar Features (v2 API)
    def get_dialogue_mode(self):
        """Get dialogue enhancement mode (XIO soundbar only).

        Dialogue mode enhances speech clarity independently of the sound profile.

        Returns:
            bool: True if dialogue enhancement is enabled, False otherwise

        Note:
            This feature is only available on XIO soundbar.
            Can be used with any sound profile.

        Example:
            >>> xio = KefConnector('192.168.1.100')  # XIO soundbar
            >>> enabled = xio.get_dialogue_mode()
            >>> print(f"Dialogue mode: {enabled}")
            Dialogue mode: True
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2'].get('dialogueMode', False)

    def set_dialogue_mode(self, enabled):
        """Set dialogue enhancement mode (XIO soundbar only).

        Args:
            enabled (bool): True to enable dialogue enhancement, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean

        Note:
            This feature is only available on XIO soundbar.
            Works independently of sound profiles - can enhance dialogue
            in any mode (music, movie, etc).

        Example:
            >>> xio = KefConnector('192.168.1.100')  # XIO soundbar
            >>> # Enable dialogue enhancement for better speech clarity
            >>> xio.set_dialogue_mode(True)
            >>> # Disable for normal sound
            >>> xio.set_dialogue_mode(False)
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return self.update_dsp_setting('dialogueMode', enabled)

    # Subwoofer Control Methods (v2 API)
    def get_subwoofer_enabled(self):
        """Get subwoofer enabled state (v2 API).

        Returns:
            bool: True if subwoofer is enabled (subwooferCount > 0 or subwooferOut is True)
        """
        profile = self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        # Check both subwooferOut and subwooferCount for compatibility
        return v2_profile.get('subwooferOut', False) or v2_profile.get('subwooferCount', 0) > 0

    def set_subwoofer_enabled(self, enabled):
        """Enable or disable subwoofer output (v2 API).

        Args:
            enabled (bool): True to enable subwoofer, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        profile = self.get_eq_profile()
        profile['kefEqProfileV2']['subwooferOut'] = enabled
        profile['kefEqProfileV2']['subwooferCount'] = 1 if enabled else 0
        return self.set_eq_profile(profile)

    def get_subwoofer_gain(self):
        """Get subwoofer gain (v2 API).

        Returns:
            float: Subwoofer gain in dB (-10.0 to +10.0)
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferGain']

    def set_subwoofer_gain(self, db_value):
        """Set subwoofer gain (v2 API).

        Args:
            db_value (float): Subwoofer gain in dB (-10.0 to +10.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-10.0 <= db_value <= 10.0):
            raise ValueError(f"db_value must be between -10.0 and +10.0, got {db_value}")

        return self.update_dsp_setting('subwooferGain', db_value)

    def get_subwoofer_polarity(self):
        """Get subwoofer polarity (v2 API).

        Returns:
            str: Subwoofer polarity - "normal" or "inverted"
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferPolarity']

    def set_subwoofer_polarity(self, polarity):
        """Set subwoofer polarity (v2 API).

        Args:
            polarity (str): Subwoofer polarity - "normal" or "inverted"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If polarity is invalid
        """
        if polarity not in SUBWOOFER_POLARITY_MODES:
            raise ValueError(f"polarity must be one of {SUBWOOFER_POLARITY_MODES}, got {polarity}")

        return self.update_dsp_setting('subwooferPolarity', polarity)

    def get_subwoofer_preset(self):
        """Get subwoofer preset (v2 API).

        Returns:
            str: Subwoofer preset name (e.g., "custom", "kube8b", "kc62", "kf92")
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferPreset']

    def set_subwoofer_preset(self, preset):
        """Set subwoofer preset (v2 API).

        Setting a preset automatically adjusts subwoofer settings for that KEF subwoofer model.

        Args:
            preset (str): Subwoofer preset - "custom", "kube8b", "kc62", "kf92",
                         "kube10b", "kube12b", "kube15", "t2", etc.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If preset is invalid
        """
        if preset not in SUBWOOFER_PRESETS:
            raise ValueError(f"preset must be one of {SUBWOOFER_PRESETS}, got {preset}")

        return self.update_dsp_setting('subwooferPreset', preset)

    def get_subwoofer_lowpass(self):
        """Get subwoofer low-pass filter frequency (v2 API).

        Returns:
            float: Low-pass filter frequency in Hz (40.0 to 250.0)
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subOutLPFreq']

    def set_subwoofer_lowpass(self, freq_hz):
        """Set subwoofer low-pass filter frequency (v2 API).

        This controls the crossover frequency for the subwoofer output.

        Args:
            freq_hz (float): Low-pass filter frequency in Hz (40.0 to 250.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If freq_hz is invalid
        """
        if not isinstance(freq_hz, (int, float)):
            raise ValueError(f"freq_hz must be a number, got {type(freq_hz)}")
        if not (40.0 <= freq_hz <= 250.0):
            raise ValueError(f"freq_hz must be between 40.0 and 250.0, got {freq_hz}")

        return self.update_dsp_setting('subOutLPFreq', freq_hz)

    def get_subwoofer_stereo(self):
        """Get subwoofer stereo mode (v2 API).

        Returns:
            bool: True if stereo subwoofer output is enabled, False for mono
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subEnableStereo']

    def set_subwoofer_stereo(self, enabled):
        """Enable or disable stereo subwoofer output (v2 API).

        Args:
            enabled (bool): True for stereo sub output, False for mono

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return self.update_dsp_setting('subEnableStereo', enabled)

    # High-Pass Filter Methods (v2 API)
    def get_high_pass_filter(self):
        """Get high-pass filter settings (v2 API).

        Returns:
            tuple: (enabled: bool, freq_hz: float) where freq_hz is 50.0 to 120.0 Hz
        """
        profile = self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['highPassMode'], v2_profile['highPassModeFreq'])

    def set_high_pass_filter(self, enabled, freq_hz=80.0):
        """Set high-pass filter for main speakers (v2 API).

        Used with subwoofers to prevent low frequencies from reaching main speakers.

        Args:
            enabled (bool): True to enable high-pass filter, False to disable
            freq_hz (float): High-pass filter frequency in Hz (50.0 to 120.0)
                Only used if enabled=True. Default is 80.0 Hz.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(freq_hz, (int, float)):
                raise ValueError(f"freq_hz must be a number, got {type(freq_hz)}")
            if not (50.0 <= freq_hz <= 120.0):
                raise ValueError(f"freq_hz must be between 50.0 and 120.0, got {freq_hz}")

        profile = self.get_eq_profile()
        profile['kefEqProfileV2']['highPassMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['highPassModeFreq'] = freq_hz
        return self.set_eq_profile(profile)

    # Audio Polarity Methods (v2 API)
    def get_audio_polarity(self):
        """Get main speaker audio polarity (v2 API).

        Returns:
            str: Audio polarity - "normal" or "inverted"
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['audioPolarity']

    def set_audio_polarity(self, polarity):
        """Set main speaker audio polarity (v2 API).

        Args:
            polarity (str): Audio polarity - "normal" or "inverted"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If polarity is invalid
        """
        if polarity not in AUDIO_POLARITY_MODES:
            raise ValueError(f"polarity must be one of {AUDIO_POLARITY_MODES}, got {polarity}")

        return self.update_dsp_setting('audioPolarity', polarity)

    # Firmware Update Methods
    def check_for_firmware_update(self):
        """Trigger firmware update check.

        This triggers the speaker to check for available firmware updates.
        The speaker may need internet connectivity for this to work.

        Returns:
            dict: JSON response from speaker (may be None if no update available)

        Note:
            - Speaker must be connected to internet
            - Check may take a few seconds to complete
            - Use get_firmware_version() to check current version
        """
        try:
            # Try using activate role to trigger check
            result = self.get_request("firmwareupdate:checkForUpdate", roles="activate")
            return result[0] if result else None
        except Exception:
            # Fallback to value role
            result = self.get_request("firmwareupdate:checkForUpdate", roles="value")
            return result[0] if result else None

    def get_firmware_update_status(self):
        """Get firmware update status.

        Returns:
            dict: Update status information, or None if not available

        Note:
            This may only return data when an update is in progress
        """
        try:
            result = self.get_request("firmwareupdate:checkForUpdate", roles="value")
            return result[0] if result else None
        except Exception:
            return None

    def install_firmware_update(self):
        """Install available firmware update.

        This triggers the speaker to begin installing a firmware update that was
        previously detected by check_for_firmware_update().

        Returns:
            dict: JSON response from speaker

        Warning:
            - Only call this if check_for_firmware_update() indicates an update is available
            - Speaker will restart during the update process
            - Do not power off the speaker during the update
            - Update process may take several minutes
            - Speaker may be unavailable during update

        Note:
            Use get_firmware_update_status() to monitor update progress
        """
        try:
            # Try firmwareupdate:install endpoint first
            result = self.get_request("firmwareupdate:install", roles="activate")
            return result[0] if result else None
        except Exception:
            # Fallback to firmwareupdate:update endpoint
            try:
                result = self.get_request("firmwareupdate:update", roles="activate")
                return result[0] if result else None
            except Exception:
                return None

    # ========== EQ Profile Management ==========

    def save_eq_profile(self, name, description=""):
        """Save current speaker EQ settings as a named profile.

        This saves the complete EQ profile from the speaker to a JSON file for later use.
        Profiles can be loaded across different speakers of the same model.

        Args:
            name (str): Profile name (e.g., "Movie Night", "Music Mode")
            description (str, optional): Description of the profile

        Returns:
            str: Path to the saved profile file

        Raises:
            ValueError: If name is empty or profile data is invalid

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> # Adjust settings on speaker...
            >>> speaker.set_bass_extension("extra")
            >>> speaker.set_treble_amount(2.0)
            >>> # Save current settings as profile
            >>> path = speaker.save_eq_profile("Bass Boost", "Extra bass for movies")
            >>> print(f"Profile saved to {path}")
        """
        current_profile = self.get_eq_profile()

        # Try to get speaker model from the speaker name or default to Unknown
        speaker_model = "Unknown"
        try:
            # You could enhance this by adding a get_speaker_model() method
            speaker_model = current_profile.get('kefEqProfileV2', {}).get('profileName', 'Unknown')
        except:
            pass

        return self._profile_manager.save_profile(name, current_profile, description, speaker_model)

    def load_eq_profile(self, name):
        """Load a saved EQ profile and apply it to the speaker.

        Args:
            name (str): Profile name to load

        Returns:
            dict: JSON response from speaker after applying profile

        Raises:
            FileNotFoundError: If profile doesn't exist

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> speaker.load_eq_profile("Movie Night")
            >>> print("Profile loaded and applied to speaker")
        """
        profile_data = self._profile_manager.load_profile(name)
        return self.set_eq_profile(profile_data)

    def list_eq_profiles(self):
        """List all saved EQ profiles with metadata.

        Returns:
            list: List of profile metadata dicts containing:
                - name: Profile name
                - description: Profile description
                - speaker_model: Speaker model this profile was created on
                - created_at: Creation timestamp
                - modified_at: Last modification timestamp
                - filepath: Full path to profile file

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> profiles = speaker.list_eq_profiles()
            >>> for profile in profiles:
            ...     print(f"{profile['name']}: {profile['description']}")
            Movie Night: Extra bass for movies
            Music Mode: Balanced for music listening
        """
        return self._profile_manager.list_profiles()

    def delete_eq_profile(self, name):
        """Delete a saved EQ profile.

        Args:
            name (str): Profile name to delete

        Returns:
            bool: True if deleted, False if profile not found

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> if speaker.delete_eq_profile("Old Profile"):
            ...     print("Profile deleted")
            ... else:
            ...     print("Profile not found")
        """
        return self._profile_manager.delete_profile(name)

    def rename_eq_profile(self, old_name, new_name):
        """Rename a saved EQ profile.

        Args:
            old_name (str): Current profile name
            new_name (str): New profile name

        Returns:
            bool: True if renamed successfully

        Raises:
            FileNotFoundError: If old profile doesn't exist
            FileExistsError: If new name already exists

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> speaker.rename_eq_profile("Old Name", "New Name")
        """
        return self._profile_manager.rename_profile(old_name, new_name)

    def profile_exists(self, name):
        """Check if an EQ profile exists.

        Args:
            name (str): Profile name to check

        Returns:
            bool: True if profile exists

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> if speaker.profile_exists("Movie Night"):
            ...     print("Profile exists")
        """
        return self._profile_manager.profile_exists(name)

    def export_eq_profile(self, name, export_path):
        """Export a profile to a specific file path.

        Useful for sharing profiles or backing them up to a different location.

        Args:
            name (str): Profile name to export
            export_path (str): Destination file path

        Returns:
            str: Path to exported file

        Raises:
            FileNotFoundError: If profile doesn't exist

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> speaker.export_eq_profile("Movie Night", "/backup/movie_profile.json")
        """
        return self._profile_manager.export_profile(name, export_path)

    def import_eq_profile(self, import_path, name=None):
        """Import a profile from a JSON file.

        Useful for restoring profiles or loading profiles created on another system.

        Args:
            import_path (str): Path to profile JSON file
            name (str, optional): New name for imported profile. If not specified,
                                uses the name from the file.

        Returns:
            str: Name of imported profile

        Raises:
            FileNotFoundError: If import file doesn't exist
            ValueError: If import file is invalid

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> profile_name = speaker.import_eq_profile("/backup/movie_profile.json")
            >>> print(f"Imported as: {profile_name}")
            >>> # Now load it
            >>> speaker.load_eq_profile(profile_name)
        """
        return self._profile_manager.import_profile(import_path, name)

    def get_profile_count(self):
        """Get total number of saved EQ profiles.

        Returns:
            int: Number of saved profiles

        Example:
            >>> speaker = KefConnector('192.168.1.100')
            >>> count = speaker.get_profile_count()
            >>> print(f"You have {count} saved profiles")
        """
        return self._profile_manager.get_profile_count()


class KefAsyncConnector:
    def __init__(self, host, port=80, session=None, profile_dir=None):
        self.host = host
        self.port = port
        self._session = session
        self.previous_volume = (
            15  # Hardcoded previous volume, in case unmute is used before mute
        )
        self.last_polled = None
        self._profile_manager = ProfileManager(profile_dir)
        self.polling_queue = None
        self._previous_poll_song_status = False

    async def close_session(self):
        """close session"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def resurect_session(self):
        if self._session is None:
            if not AIOHTTP_AVAILABLE:
                raise ImportError(
                    "aiohttp is required for KefAsyncConnector. "
                    "Install it with: pip install aiohttp"
                )
            self._session = aiohttp.ClientSession()

    async def power_on(self):
        """power on speaker"""
        await self.set_status("powerOn")

    async def shutdown(self):
        """Shutdown speaker"""
        await self.set_source("standby")

    async def mute(self):
        """mute speaker"""
        self.previous_volume = await self.volume
        await self.set_volume(0)

    async def unmute(self):
        """unmute speaker"""
        await self.set_volume(self.previous_volume)

    async def toggle_play_pause(self):
        """Toogle play/pause"""
        await self._track_control("pause")

    async def next_track(self):
        """Next track"""
        await self._track_control("next")

    async def previous_track(self):
        """Previous track"""
        await self._track_control("previous")

    async def _track_control(self, command):
        """toogle play/pause"""
        payload = {
            "path": "player:player/control",
            "roles": "activate",
            "value": """{{"control":"{command}"}}""".format(command=command),
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()

    async def _get_player_data(self):
        """get data about currently playing media"""
        payload = {
            "path": "player:player/data",
            "roles": "value",
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]

    async def get_request(self, path, roles="value"):
        """Generic method to get data from any API path.

        Args:
            path: API path to query (e.g., "kef:eqProfile", "network:info")
            roles: API roles parameter (default: "value")

        Returns:
            JSON response from API
        """
        payload = {
            "path": path,
            "roles": roles,
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output

    async def get_wifi_information(self):
        """Get WiFi information from speaker.

        Returns dict with WiFi signal strength, SSID, frequency, and BSSID.
        Returns empty dict if WiFi info is not available.
        """
        try:
            # Get network info from speaker
            network_data = await self.get_request("network:info", roles="value")

            wifi_dict = {}
            network_info = (
                network_data[0].get("networkInfo", {}) if network_data else {}
            )

            if network_info:
                wireless = network_info.get("wireless", {})
                if wireless:
                    wifi_dict["signalLevel"] = wireless.get("signalLevel")
                    wifi_dict["ssid"] = wireless.get("ssid")
                    wifi_dict["frequency"] = wireless.get("frequency")
                    wifi_dict["bssid"] = wireless.get("bssid")

            return wifi_dict
        except Exception:
            # Silently return empty dict if WiFi info not available
            return {}

    async def set_source(self, source):
        """Set spaker source, if speaker in standby, it powers on the speaker.
        Possible sources : wifi, bluetooth, tv, optic, coaxial or analog"""
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": """{{"type":"kefPhysicalSource","kefPhysicalSource":"{source}"}}""".format(
                source=source
            ),
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()

    async def set_volume(self, volume):
        """Set speaker volume (between 0 and 100)"""
        payload = {
            "path": "player:volume",
            "roles": "value",
            "value": """{{"type":"i32_","i32_":{volume}}}""".format(volume=volume),
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()

    async def set_status(self, status):
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": """{{"type":"kefPhysicalSource","kefPhysicalSource":"{status}"}}""".format(
                status=status
            ),
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()

    async def get_song_information(self, song_data=None):
        """Get song title, album and artist"""
        if song_data == None:
            song_data = await self._get_player_data()
        info_dict = dict()
        info_dict["title"] = song_data.get("trackRoles", {}).get("title")

        metadata = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
        )

        info_dict["artist"] = metadata.get("artist")
        info_dict["album"] = metadata.get("album")
        # Use albumArtist if available, otherwise fallback to artist
        album_artist = metadata.get("albumArtist")
        info_dict["album_artist"] = album_artist if album_artist else metadata.get("artist")
        info_dict["cover_url"] = song_data.get("trackRoles", {}).get("icon", None)
        info_dict["service_id"] = metadata.get("serviceID")

        return info_dict

    async def get_audio_codec_information(self, player_data=None):
        """
        Get audio codec information from player data.
        Returns dict with codec, sample rate, and channel information.
        """
        try:
            if player_data is None:
                player_data = await self._get_player_data()

            codec_dict = {}
            active_resource = (
                player_data.get("trackRoles", {})
                .get("mediaData", {})
                .get("activeResource", {})
            )

            if active_resource:
                codec_dict["codec"] = active_resource.get("codec")
                codec_dict["sampleFrequency"] = active_resource.get("sampleFrequency")
                codec_dict["streamSampleRate"] = active_resource.get("streamSampleRate")
                codec_dict["streamChannels"] = active_resource.get("streamChannels")
                codec_dict["nrAudioChannels"] = active_resource.get("nrAudioChannels")

            # Get streaming service ID from metadata
            metadata = (
                player_data.get("trackRoles", {})
                .get("mediaData", {})
                .get("metaData", {})
            )
            if metadata:
                codec_dict["serviceID"] = metadata.get("serviceID")

            return codec_dict
        except Exception:
            # Silently return empty dict if codec info not available
            return {}

    async def get_polling_queue(self, song_status=False, poll_song_status=False):
        """Get the polling queue uuid, and subscribe to all relevant topics"""
        payload = {
            "subscribe": [
                {"path": "settings:/mediaPlayer/playMode", "type": "itemWithValue"},
                {"path": "playlists:pq/getitems", "type": "rows"},
                {"path": "notifications:/display/queue", "type": "rows"},
                {"path": "settings:/kef/host/maximumVolume", "type": "itemWithValue"},
                {"path": "player:volume", "type": "itemWithValue"},
                {"path": "kef:fwupgrade/info", "type": "itemWithValue"},
                {"path": "settings:/kef/host/volumeStep", "type": "itemWithValue"},
                {"path": "settings:/kef/host/volumeLimit", "type": "itemWithValue"},
                {"path": "settings:/mediaPlayer/mute", "type": "itemWithValue"},
                {"path": "settings:/kef/host/speakerStatus", "type": "itemWithValue"},
                {"path": "settings:/kef/play/physicalSource", "type": "itemWithValue"},
                {"path": "player:player/data", "type": "itemWithValue"},
                {"path": "kef:speedTest/status", "type": "itemWithValue"},
                {"path": "network:info", "type": "itemWithValue"},
                {"path": "kef:eqProfile/v2", "type": "itemWithValue"},
                {"path": "settings:/kef/host/modelName", "type": "itemWithValue"},
                {"path": "settings:/version", "type": "itemWithValue"},
                {"path": "settings:/deviceName", "type": "itemWithValue"},
            ],
            "unsubscribe": [],
        }

        if song_status:
            payload["subscribe"].append(
                {"path": "player:player/data/playTime", "type": "itemWithValue"}
            )

        await self.resurect_session()
        async with self._session.post(
            "http://" + self.host + "/api/event/modifyQueue", json=payload
        ) as response:
            json_output = await response.json()

        # Update polling_queue property with queue uuid
        self.polling_queue = json_output[1:-1]

        # Update last polled time
        self.last_polled = time.time()

        return self.polling_queue

    async def parse_events(self, events):
        """Parse events"""
        parsed_events = dict()

        for event in events:
            if event == "settings:/kef/play/physicalSource":
                parsed_events["source"] = events[event].get("kefPhysicalSource")
            elif event == "player:player/data/playTime":
                parsed_events["song_status"] = events[event].get("i64_")
            elif event == "player:volume":
                parsed_events["volume"] = events[event].get("i32_")
            elif event == "player:player/data":
                parsed_events["song_info"] = await self.get_song_information(
                    events[event]
                )
                parsed_events["song_length"] = (
                    events[event].get("status", {}).get("duration")
                )
                parsed_events["status"] = events[event].get("state")
            elif event == "settings:/kef/host/speakerStatus":
                parsed_events["speaker_status"] = events[event].get("kefSpeakerStatus")
            elif event == "settings:/deviceName":
                parsed_events["device_name"] = events[event].get("string_")
            elif event == "settings:/mediaPlayer/mute":
                parsed_events["mute"] = events[event].get("bool_")
            else:
                if parsed_events.get("other") == None:
                    parsed_events["other"] = {}
                parsed_events["other"].update({event: events[event]})

        return parsed_events

    async def poll_speaker(self, timeout=10, song_status=False, poll_song_status=False):
        """poll speaker for info"""

        if song_status:
            warnings.warn(
                "The 'song_status' parameter is deprecated and will be removed in version 0.8.0. "
                "Please use 'poll_song_status' instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        # check if it is necessary to get a new queue
        if (
            (self.polling_queue == None)
            or ((time.time() - self.last_polled) > 50)
            or (song_status != self._previous_polling_song_status)
        ):
            await self.get_polling_queue(poll_song_status=poll_song_status)

        payload = {"queueId": "{{{}}}".format(self.polling_queue), "timeout": timeout}

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/event/pollQueue",
            params=payload,
            timeout=10 + 0.5,  # add 0.5 seconds to timeout to allow for processing
        ) as response:
            json_output = await response.json()

        # Process all events

        events = dict()
        # fill events lists
        for j in json_output:
            if events.get(j["path"], False):
                events[j["path"]].append(j)
            else:
                events[j["path"]] = [j]
        # prune events lists
        for k in events:
            events[k] = events[k][-1].get("itemValue", "updated")

        return await self.parse_events(events)

    @property
    async def mac_address(self):
        """Get the mac address of the Speaker"""
        payload = {"path": "settings:/system/primaryMacAddress", "roles": "value"}
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["string_"]

    @property
    async def speaker_name(self):
        """Get the friendly name of the Speaker"""
        payload = {"path": "settings:/deviceName", "roles": "value"}
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["string_"]

    @property
    async def status(self):
        """Status of the speaker : standby or poweredOn"""
        payload = {"path": "settings:/kef/host/speakerStatus", "roles": "value"}
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["kefSpeakerStatus"]

    @property
    async def is_playing(self):
        """Is the speaker currently playing"""
        json_output = await self._get_player_data()
        return json_output["state"] == "playing"

    @property
    async def song_length(self):
        """Song length in ms"""
        if await self.is_playing:
            json_output = await self._get_player_data()
            return json_output["status"]["duration"]
        else:
            return None

    @property
    async def song_status(self):
        """Progression of song"""
        payload = {
            "path": "player:player/data/playTime",
            "roles": "value",
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["i64_"]

    @property
    async def source(self):
        """Speaker soe : standby (not powered on), wifi, bluetooth, tv, optic,
        coaxial or analog"""
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["kefPhysicalSource"]

    @property
    async def volume(self):
        """Speaker volume (1 to 100, 0 = muted)"""
        payload = {
            "path": "player:volume",
            "roles": "value",
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["i32_"]

    async def _get_speaker_firmware_version(self):
        """
        Get speaker firmware "release text"
        """

        payload = {
            "path": "settings:/releasetext",
            "roles": "value",
        }
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0]["string_"]

    async def get_speaker_model(self):
        """
        Speaker model
        """
        raw_data = await self._get_speaker_firmware_version()
        speaker_model = raw_data.split("_")[0]
        return speaker_model

    async def get_firmware_version(self):
        """
        Speaker firmware version
        """
        raw_data = await self._get_speaker_firmware_version()
        speaker_firmware_version = raw_data.split("_")[1]
        return speaker_firmware_version

    # EQ/DSP Profile Methods (v2 API)
    async def get_eq_profile(self):
        """Get complete EQ profile from speaker (v2 API).

        Note: Uses kef:eqProfile/v2 which returns the ACTIVE profile with
        direct dB/Hz values (not integer indices).

        Returns:
            dict: Complete EQ profile with structure:
                {
                    'type': 'kefEqProfileV2',
                    'kefEqProfileV2': {
                        'profileName': str,
                        'isExpertMode': bool,
                        'subwooferGain': float,  # Direct dB value
                        'deskModeSetting': float,  # Direct dB value
                        ...
                    }
                }

        Raises:
            Exception: If speaker communication fails
        """
        result = await self.get_request("kef:eqProfile/v2", roles="value")
        return result[0]

    async def set_eq_profile(self, profile_dict):
        """Set complete EQ profile on speaker (v2 API).

        Args:
            profile_dict (dict): Complete profile dict as returned by get_eq_profile()
                Must include 'type' and 'kefEqProfileV2' keys

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If profile_dict structure is invalid

        Example:
            profile = await speaker.get_eq_profile()
            profile['kefEqProfileV2']['deskMode'] = True
            profile['kefEqProfileV2']['deskModeSetting'] = -3.0  # -3dB
            await speaker.set_eq_profile(profile)
        """
        # Validate structure
        if not isinstance(profile_dict, dict):
            raise ValueError("profile_dict must be a dictionary")

        if 'type' not in profile_dict or profile_dict['type'] != 'kefEqProfileV2':
            raise ValueError(
                "profile_dict must have 'type' key with value 'kefEqProfileV2'"
            )

        if 'kefEqProfileV2' not in profile_dict:
            raise ValueError("profile_dict must have 'kefEqProfileV2' key")

        payload = {
            "path": "kef:eqProfile/v2",
            "roles": "value",
            "value": json.dumps(profile_dict),
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output

    async def update_dsp_setting(self, setting_name, value):
        """Update a single DSP setting (v2 API with direct dB/Hz values).

        This is a convenience method that fetches the current profile,
        updates the specified setting, and sends it back.

        Args:
            setting_name (str): Name of the DSP setting (e.g., 'deskMode', 'trebleAmount')
            value: New value for the setting (direct dB/Hz value for v2)

        Returns:
            dict: JSON response from speaker

        Example:
            await speaker.update_dsp_setting('deskMode', True)
            await speaker.update_dsp_setting('trebleAmount', 1.5)  # +1.5dB
        """
        profile = await self.get_eq_profile()
        profile['kefEqProfileV2'][setting_name] = value
        return await self.set_eq_profile(profile)

    # EQ Profile Name Methods (Async)
    async def get_profile_name(self):
        """Get the current EQ profile name.

        Returns:
            str: Current profile name

        Example:
            name = await speaker.get_profile_name()
            print(f"Current profile: {name}")
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['profileName']

    async def rename_profile(self, new_name):
        """Rename the current EQ profile.

        Args:
            new_name (str): New name for the profile

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If new_name is not a string or is empty

        Example:
            await speaker.rename_profile("Living Room Settings")

        Note:
            This renames the currently active profile. The profile ID remains the same.
            KEF speakers do not support deleting profiles via the API.
        """
        if not isinstance(new_name, str):
            raise ValueError(f"new_name must be a string, got {type(new_name)}")
        if not new_name.strip():
            raise ValueError("new_name cannot be empty")

        return await self.update_dsp_setting('profileName', new_name.strip())

    async def get_profile_id(self):
        """Get the current EQ profile unique ID.

        Returns:
            str: Current profile UUID

        Example:
            profile_id = await speaker.get_profile_id()
            print(f"Profile ID: {profile_id}")
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['profileId']

    # Desk Mode Methods (v2 API - direct dB values)
    async def get_desk_mode(self):
        """Get desk mode setting and value (v2 API).

        Returns:
            tuple: (enabled: bool, db_value: float) where db_value is -10.0 to 0.0 dB
        """
        profile = await self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['deskMode'], v2_profile['deskModeSetting'])

    async def set_desk_mode(self, enabled, db_value=0.0):
        """Set desk mode enabled state and attenuation value (v2 API).

        Args:
            enabled (bool): True to enable desk mode, False to disable
            db_value (float): Desk mode attenuation in dB (-10.0 to 0.0)
                Only used if enabled=True. Default is 0.0 (no attenuation).

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(db_value, (int, float)):
                raise ValueError(f"db_value must be a number, got {type(db_value)}")
            if not (-10.0 <= db_value <= 0.0):
                raise ValueError(f"db_value must be between -10.0 and 0.0, got {db_value}")

        profile = await self.get_eq_profile()
        profile['kefEqProfileV2']['deskMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['deskModeSetting'] = db_value
        return await self.set_eq_profile(profile)

    # Wall Mode Methods (v2 API - direct dB values)
    async def get_wall_mode(self):
        """Get wall mode setting and value (v2 API).

        Returns:
            tuple: (enabled: bool, db_value: float) where db_value is -10.0 to 0.0 dB
        """
        profile = await self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['wallMode'], v2_profile['wallModeSetting'])

    async def set_wall_mode(self, enabled, db_value=0.0):
        """Set wall mode enabled state and attenuation value (v2 API).

        Args:
            enabled (bool): True to enable wall mode, False to disable
            db_value (float): Wall mode attenuation in dB (-10.0 to 0.0)
                Only used if enabled=True. Default is 0.0 (no attenuation).

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(db_value, (int, float)):
                raise ValueError(f"db_value must be a number, got {type(db_value)}")
            if not (-10.0 <= db_value <= 0.0):
                raise ValueError(f"db_value must be between -10.0 and 0.0, got {db_value}")

        profile = await self.get_eq_profile()
        profile['kefEqProfileV2']['wallMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['wallModeSetting'] = db_value
        return await self.set_eq_profile(profile)

    # Bass Extension Methods (v2 API)
    async def get_bass_extension(self):
        """Get bass extension setting (v2 API).

        Returns:
            str: Bass extension mode - "standard", "less", or "extra"
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['bassExtension']

    async def set_bass_extension(self, mode):
        """Set bass extension mode (v2 API).

        Args:
            mode (str): Bass extension mode - "standard", "less", or "extra"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in BASS_EXTENSION_MODES:
            raise ValueError(f"mode must be one of {BASS_EXTENSION_MODES}, got {mode}")

        return await self.update_dsp_setting('bassExtension', mode)

    # Treble Methods (v2 API - direct dB values)
    async def get_treble_amount(self):
        """Get treble amount (v2 API).

        Returns:
            float: Treble amount in dB (-3.0 to +3.0)
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['trebleAmount']

    async def set_treble_amount(self, db_value):
        """Set treble amount (v2 API).

        Args:
            db_value (float): Treble amount in dB (-3.0 to +3.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-3.0 <= db_value <= 3.0):
            raise ValueError(f"db_value must be between -3.0 and +3.0, got {db_value}")

        return await self.update_dsp_setting('trebleAmount', db_value)

    # Balance Methods (v2 API)
    async def get_balance(self):
        """Get balance setting (v2 API).

        Returns:
            float: Balance position (negative=left, 0=center, positive=right)
                   Range: approximately -6.0 to +6.0
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['balance']

    async def set_balance(self, position):
        """Set balance position (v2 API).

        Args:
            position (float): Balance position (negative=left, 0=center, positive=right)
                             Range: approximately -6.0 to +6.0

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If position is invalid
        """
        if not isinstance(position, (int, float)):
            raise ValueError(f"position must be a number, got {type(position)}")
        if not (-6.0 <= position <= 6.0):
            raise ValueError(f"position must be between -6.0 and +6.0, got {position}")

        return await self.update_dsp_setting('balance', position)

    # Phase Correction Methods (v2 API)
    async def get_phase_correction(self):
        """Get phase correction setting (v2 API).

        Returns:
            bool: True if phase correction is enabled, False otherwise
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['phaseCorrection']

    async def set_phase_correction(self, enabled):
        """Set phase correction enabled state (v2 API).

        Args:
            enabled (bool): True to enable phase correction, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return await self.update_dsp_setting('phaseCorrection', enabled)

    # Profile Name Methods (v2 API)
    async def get_profile_name(self):
        """Get the name of the current EQ profile (v2 API).

        Returns:
            str: The profile name (e.g., "Kantoor", "Calibrated", "My Custom Profile")
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['profileName']

    async def set_profile_name(self, name):
        """Set the name of the current EQ profile (v2 API).

        Args:
            name (str): The new profile name (must be a non-empty string)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If name is not a valid string
        """
        if not isinstance(name, str):
            raise ValueError(f"name must be a string, got {type(name)}")
        if not name.strip():
            raise ValueError("name cannot be empty or whitespace only")

        return await self.update_dsp_setting('profileName', name.strip())

    # Sound Profile Methods (v2 API)
    async def get_sound_profile(self):
        """Get the current sound profile preset (XIO soundbar only).

        Sound profiles are EQ presets optimized for different content types.

        Returns:
            str: Sound profile name - "default", "music", "movie", "night", "dialogue", or "direct"
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['soundProfile']

    async def set_sound_profile(self, profile_name):
        """Set the sound profile preset (XIO soundbar only).

        Args:
            profile_name (str): Sound profile - "default", "music", "movie", "night", "dialogue", or "direct"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If profile_name is not valid

        Note:
            Available profiles:
            - "default": Balanced sound for general use
            - "music": Optimized for music playback
            - "movie": Enhanced for movie audio with dialogue clarity
            - "night": Reduced dynamic range for night listening
            - "dialogue": Enhanced dialogue/speech clarity
            - "direct": Direct sound without DSP processing
        """
        valid_profiles = ["default", "music", "movie", "night", "dialogue", "direct"]

        if not isinstance(profile_name, str):
            raise ValueError(f"profile_name must be a string, got {type(profile_name)}")

        profile_name = profile_name.lower().strip()

        if profile_name not in valid_profiles:
            raise ValueError(f"profile_name must be one of {valid_profiles}, got '{profile_name}'")

        return await self.update_dsp_setting('soundProfile', profile_name)

    # Wall Mounted Methods (v2 API)
    async def get_wall_mounted(self):
        """Get whether the speaker is wall mounted (v2 API).

        This setting is primarily used on soundbars (like XIO) to optimize
        the sound for wall-mounted placement.

        Returns:
            bool: True if speaker is wall mounted, False otherwise
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['wallMounted']

    async def set_wall_mounted(self, mounted):
        """Set whether the speaker is wall mounted (v2 API).

        Args:
            mounted (bool): True if speaker is wall mounted, False otherwise

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If mounted is not a boolean

        Note:
            This setting is primarily for soundbars and affects acoustic tuning.
        """
        if not isinstance(mounted, bool):
            raise ValueError(f"mounted must be a boolean, got {type(mounted)}")

        return await self.update_dsp_setting('wallMounted', mounted)

    # XIO Soundbar Features (v2 API)
    async def get_dialogue_mode(self):
        """Get dialogue enhancement mode (XIO soundbar only).

        Dialogue mode enhances speech clarity independently of the sound profile.

        Returns:
            bool: True if dialogue enhancement is enabled, False otherwise

        Note:
            This feature is only available on XIO soundbar.
            Can be used with any sound profile.

        Example:
            >>> xio = KefAsyncConnector('192.168.1.100')  # XIO soundbar
            >>> enabled = await xio.get_dialogue_mode()
            >>> print(f"Dialogue mode: {enabled}")
            Dialogue mode: True
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2'].get('dialogueMode', False)

    async def set_dialogue_mode(self, enabled):
        """Set dialogue enhancement mode (XIO soundbar only).

        Args:
            enabled (bool): True to enable dialogue enhancement, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean

        Note:
            This feature is only available on XIO soundbar.
            Works independently of sound profiles - can enhance dialogue
            in any mode (music, movie, etc).

        Example:
            >>> xio = KefAsyncConnector('192.168.1.100')  # XIO soundbar
            >>> # Enable dialogue enhancement for better speech clarity
            >>> await xio.set_dialogue_mode(True)
            >>> # Disable for normal sound
            >>> await xio.set_dialogue_mode(False)
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return await self.update_dsp_setting('dialogueMode', enabled)

    # Subwoofer Control Methods (v2 API)
    async def get_subwoofer_enabled(self):
        """Get subwoofer enabled state (v2 API).

        Returns:
            bool: True if subwoofer is enabled (subwooferCount > 0 or subwooferOut is True)
        """
        profile = await self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return v2_profile.get('subwooferOut', False) or v2_profile.get('subwooferCount', 0) > 0

    async def set_subwoofer_enabled(self, enabled):
        """Enable or disable subwoofer output (v2 API).

        Args:
            enabled (bool): True to enable subwoofer, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        profile = await self.get_eq_profile()
        profile['kefEqProfileV2']['subwooferOut'] = enabled
        profile['kefEqProfileV2']['subwooferCount'] = 1 if enabled else 0
        return await self.set_eq_profile(profile)

    async def get_subwoofer_gain(self):
        """Get subwoofer gain (v2 API).

        Returns:
            float: Subwoofer gain in dB (-10.0 to +10.0)
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferGain']

    async def set_subwoofer_gain(self, db_value):
        """Set subwoofer gain (v2 API).

        Args:
            db_value (float): Subwoofer gain in dB (-10.0 to +10.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-10.0 <= db_value <= 10.0):
            raise ValueError(f"db_value must be between -10.0 and +10.0, got {db_value}")

        return await self.update_dsp_setting('subwooferGain', db_value)

    async def get_subwoofer_polarity(self):
        """Get subwoofer polarity (v2 API).

        Returns:
            str: Subwoofer polarity - "normal" or "inverted"
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferPolarity']

    async def set_subwoofer_polarity(self, polarity):
        """Set subwoofer polarity (v2 API).

        Args:
            polarity (str): Subwoofer polarity - "normal" or "inverted"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If polarity is invalid
        """
        if polarity not in SUBWOOFER_POLARITY_MODES:
            raise ValueError(f"polarity must be one of {SUBWOOFER_POLARITY_MODES}, got {polarity}")

        return await self.update_dsp_setting('subwooferPolarity', polarity)

    async def get_subwoofer_preset(self):
        """Get subwoofer preset (v2 API).

        Returns:
            str: Subwoofer preset name (e.g., "custom", "kube8b", "kc62", "kf92")
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferPreset']

    async def set_subwoofer_preset(self, preset):
        """Set subwoofer preset (v2 API).

        Setting a preset automatically adjusts subwoofer settings for that KEF subwoofer model.

        Args:
            preset (str): Subwoofer preset - "custom", "kube8b", "kc62", "kf92",
                         "kube10b", "kube12b", "kube15", "t2", etc.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If preset is invalid
        """
        if preset not in SUBWOOFER_PRESETS:
            raise ValueError(f"preset must be one of {SUBWOOFER_PRESETS}, got {preset}")

        return await self.update_dsp_setting('subwooferPreset', preset)

    async def get_subwoofer_lowpass(self):
        """Get subwoofer low-pass filter frequency (v2 API).

        Returns:
            float: Low-pass filter frequency in Hz (40.0 to 250.0)
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subOutLPFreq']

    async def set_subwoofer_lowpass(self, freq_hz):
        """Set subwoofer low-pass filter frequency (v2 API).

        This controls the crossover frequency for the subwoofer output.

        Args:
            freq_hz (float): Low-pass filter frequency in Hz (40.0 to 250.0)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If freq_hz is invalid
        """
        if not isinstance(freq_hz, (int, float)):
            raise ValueError(f"freq_hz must be a number, got {type(freq_hz)}")
        if not (40.0 <= freq_hz <= 250.0):
            raise ValueError(f"freq_hz must be between 40.0 and 250.0, got {freq_hz}")

        return await self.update_dsp_setting('subOutLPFreq', freq_hz)

    async def get_subwoofer_stereo(self):
        """Get subwoofer stereo mode (v2 API).

        Returns:
            bool: True if stereo subwoofer output is enabled, False for mono
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subEnableStereo']

    async def set_subwoofer_stereo(self, enabled):
        """Enable or disable stereo subwoofer output (v2 API).

        Args:
            enabled (bool): True for stereo sub output, False for mono

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return await self.update_dsp_setting('subEnableStereo', enabled)

    # High-Pass Filter Methods (v2 API)
    async def get_high_pass_filter(self):
        """Get high-pass filter settings (v2 API).

        Returns:
            tuple: (enabled: bool, freq_hz: float) where freq_hz is 50.0 to 120.0 Hz
        """
        profile = await self.get_eq_profile()
        v2_profile = profile['kefEqProfileV2']
        return (v2_profile['highPassMode'], v2_profile['highPassModeFreq'])

    async def set_high_pass_filter(self, enabled, freq_hz=80.0):
        """Set high-pass filter for main speakers (v2 API).

        Used with subwoofers to prevent low frequencies from reaching main speakers.

        Args:
            enabled (bool): True to enable high-pass filter, False to disable
            freq_hz (float): High-pass filter frequency in Hz (50.0 to 120.0)
                Only used if enabled=True. Default is 80.0 Hz.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        if enabled:
            if not isinstance(freq_hz, (int, float)):
                raise ValueError(f"freq_hz must be a number, got {type(freq_hz)}")
            if not (50.0 <= freq_hz <= 120.0):
                raise ValueError(f"freq_hz must be between 50.0 and 120.0, got {freq_hz}")

        profile = await self.get_eq_profile()
        profile['kefEqProfileV2']['highPassMode'] = enabled
        if enabled:
            profile['kefEqProfileV2']['highPassModeFreq'] = freq_hz
        return await self.set_eq_profile(profile)

    # Audio Polarity Methods (v2 API)
    async def get_audio_polarity(self):
        """Get main speaker audio polarity (v2 API).

        Returns:
            str: Audio polarity - "normal" or "inverted"
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['audioPolarity']

    async def set_audio_polarity(self, polarity):
        """Set main speaker audio polarity (v2 API).

        Args:
            polarity (str): Audio polarity - "normal" or "inverted"

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If polarity is invalid
        """
        if polarity not in AUDIO_POLARITY_MODES:
            raise ValueError(f"polarity must be one of {AUDIO_POLARITY_MODES}, got {polarity}")

        return await self.update_dsp_setting('audioPolarity', polarity)

    # Firmware Update Methods
    async def check_for_firmware_update(self):
        """Trigger firmware update check.

        This triggers the speaker to check for available firmware updates.
        The speaker may need internet connectivity for this to work.

        Returns:
            dict: JSON response from speaker (may be None if no update available)

        Example:
            >>> result = await speaker.check_for_firmware_update()
            >>> print(result)
        """
        try:
            # Try using activate role to trigger check
            result = await self.get_request("firmwareupdate:checkForUpdate", roles="activate")
            return result[0] if result else None
        except Exception:
            # Fallback to value role
            result = await self.get_request("firmwareupdate:checkForUpdate", roles="value")
            return result[0] if result else None

    async def get_firmware_update_status(self):
        """Get firmware update status.

        Returns:
            dict: Update status information, or None if not available

        Example:
            >>> status = await speaker.get_firmware_update_status()
            >>> if status:
            ...     print(f"Update status: {status}")
        """
        try:
            result = await self.get_request("firmwareupdate:checkForUpdate", roles="value")
            return result[0] if result else None
        except Exception:
            return None

    async def install_firmware_update(self):
        """Install available firmware update.

        This triggers the speaker to begin installing a firmware update that was
        previously detected by check_for_firmware_update().

        Returns:
            dict: JSON response from speaker

        Warning:
            - Only call this if check_for_firmware_update() indicates an update is available
            - Speaker will restart during the update process
            - Do not power off the speaker during the update
            - Update process may take several minutes
            - Speaker may be unavailable during update

        Note:
            Use get_firmware_update_status() to monitor update progress

        Example:
            >>> # First check for updates
            >>> update_info = await speaker.check_for_firmware_update()
            >>> if update_info:
            ...     # Update available, install it
            ...     result = await speaker.install_firmware_update()
            ...     print("Update started!")
        """
        try:
            # Try firmwareupdate:install endpoint first
            result = await self.get_request("firmwareupdate:install", roles="activate")
            return result[0] if result else None
        except Exception:
            # Fallback to firmwareupdate:update endpoint
            try:
                result = await self.get_request("firmwareupdate:update", roles="activate")
                return result[0] if result else None
            except Exception:
                return None

    # ========== EQ Profile Management ==========

    async def save_eq_profile(self, name, description=""):
        """Save current speaker EQ settings as a named profile (async).

        Args:
            name (str): Profile name
            description (str, optional): Description of the profile

        Returns:
            str: Path to the saved profile file
        """
        current_profile = await self.get_eq_profile()
        speaker_model = "Unknown"
        try:
            speaker_model = current_profile.get('kefEqProfileV2', {}).get('profileName', 'Unknown')
        except:
            pass
        return self._profile_manager.save_profile(name, current_profile, description, speaker_model)

    async def load_eq_profile(self, name):
        """Load a saved EQ profile and apply it to the speaker (async).

        Args:
            name (str): Profile name to load

        Returns:
            dict: JSON response from speaker after applying profile
        """
        profile_data = self._profile_manager.load_profile(name)
        return await self.set_eq_profile(profile_data)

    def list_eq_profiles(self):
        """List all saved EQ profiles with metadata (sync method)."""
        return self._profile_manager.list_profiles()

    def delete_eq_profile(self, name):
        """Delete a saved EQ profile (sync method)."""
        return self._profile_manager.delete_profile(name)

    def rename_eq_profile(self, old_name, new_name):
        """Rename a saved EQ profile (sync method)."""
        return self._profile_manager.rename_profile(old_name, new_name)

    def profile_exists(self, name):
        """Check if an EQ profile exists (sync method)."""
        return self._profile_manager.profile_exists(name)

    def export_eq_profile(self, name, export_path):
        """Export a profile to a specific file path (sync method)."""
        return self._profile_manager.export_profile(name, export_path)

    def import_eq_profile(self, import_path, name=None):
        """Import a profile from a JSON file (sync method)."""
        return self._profile_manager.import_profile(import_path, name)

    def get_profile_count(self):
        """Get total number of saved EQ profiles (sync method)."""
        return self._profile_manager.get_profile_count()
