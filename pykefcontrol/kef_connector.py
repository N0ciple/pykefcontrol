import json

import requests
import aiohttp
import time
import warnings


_POST_MODELS = {"LS50WII", "LSXIILT", "LSXII"}
_MODEL_ALIASES = {"LS50W2": "LS50WII", "LSX2LT": "LSXIILT", "LSX2": "LSXII"}


class KefConnector:
    def __init__(self, host, model=None):
        self.host = host
        self._speaker_model = _MODEL_ALIASES.get(model, model)
        self.previous_volume = self.volume
        self.last_polled = None
        self.polling_queue = None
        self._previous_poll_song_status = False

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

    def _set_data(self, payload):
        if self._speaker_model is None:
            self._speaker_model = self.speaker_model
        if self._speaker_model in _POST_MODELS:
            with requests.post(
                "http://" + self.host + "/api/setData", json=payload
            ) as response:
                response.raise_for_status()
                return response.json()
        else:
            payload = dict(payload)
            payload["value"] = json.dumps(payload["value"], separators=(",", ":"))
            with requests.get(
                "http://" + self.host + "/api/setData", params=payload
            ) as response:
                response.raise_for_status()
                return response.json()

    def _track_control(self, command):
        """
        toogle play/pause
        """
        payload = {
            "path": "player:player/control",
            "roles": "activate",
            "value": {"control": command},
        }

        self._set_data(payload)

    def set_volume(self, volume):
        """
        Set volume
        """
        self.volume = volume

    def get_default_volume(self, input_source):
        """Get default volume for a specific input source.

        Args:
            input_source (str): Input source name (wifi, bluetooth, optic, coaxial, usb, analog, tv)

        Returns:
            int: Volume level (0-100) for the specified input

        Example:
            volume = speaker.get_default_volume('wifi')  # Returns 50
        """
        # Map input source to API path
        source_map = {
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optic': 'Optical',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analog': 'Analogue',
            'analogue': 'Analogue',
            'tv': 'TV',
            'hdmi': 'TV'
        }

        if input_source.lower() not in source_map:
            raise ValueError(f"Invalid input source: {input_source}. Valid sources: {', '.join(source_map.keys())}")

        api_source = source_map[input_source.lower()]
        payload = {
            "path": f"settings:/kef/host/defaultVolume{api_source}",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["i32_"]

    def set_default_volume(self, input_source, volume):
        """Set default volume for a specific input source.

        Args:
            input_source (str): Input source name (wifi, bluetooth, optic, coaxial, usb, analog, tv)
            volume (int): Volume level (0-100)

        Example:
            speaker.set_default_volume('wifi', 50)
            speaker.set_default_volume('bluetooth', 40)
        """
        if not 0 <= volume <= 100:
            raise ValueError(f"Volume must be between 0 and 100, got {volume}")

        # Map input source to API path
        source_map = {
            'global': 'Global',
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optic': 'Optical',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analog': 'Analogue',
            'analogue': 'Analogue',
            'tv': 'TV',
            'hdmi': 'TV'
        }

        if input_source.lower() not in source_map:
            raise ValueError(f"Invalid input source: {input_source}. Valid sources: {', '.join(source_map.keys())}")

        api_source = source_map[input_source.lower()]
        payload = {
            "path": f"settings:/kef/host/defaultVolume{api_source}",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{volume}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_all_default_volumes(self):
        """Get default volumes for all input sources on this speaker model.

        Returns:
            dict: Dictionary of input sources and their default volumes

        Example:
            volumes = speaker.get_all_default_volumes()
            # Returns: {'global': 50, 'wifi': 45, 'bluetooth': 40, 'optical': 50, ...}
        """
        # Define all possible inputs
        all_inputs = ['global', 'wifi', 'bluetooth', 'optical', 'coaxial', 'usb', 'analogue', 'tv']

        # Map to API names
        source_map = {
            'global': 'Global',
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analogue': 'Analogue',
            'tv': 'TV'
        }

        volumes = {}
        for input_source in all_inputs:
            try:
                api_source = source_map[input_source]
                payload = {
                    "path": f"settings:/kef/host/defaultVolume{api_source}",
                    "roles": "value",
                }

                with requests.get(
                    "http://" + self.host + "/api/getData", params=payload
                ) as response:
                    if response.status_code == 200:
                        response.raise_for_status()
                        json_output = response.json()
                        volumes[input_source] = json_output[0]["i32_"]
            except:
                # Skip inputs that don't exist on this model
                pass

        return volumes

    def get_volume_settings(self):
        """Get volume behavior settings.

        Returns:
            dict: Volume settings including max_volume, step, limit, display mode

        Example:
            settings = speaker.get_volume_settings()
            # Returns: {'max_volume': 100, 'step': 1, 'limit': 100, 'display': 'linear'}
        """
        settings = {}

        # Get maximum volume
        try:
            payload = {"path": "settings:/kef/host/maximumVolume", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    response.raise_for_status()
                    settings['max_volume'] = response.json()[0]["i32_"]
        except:
            pass

        # Get volume step (uses i16_ not i32_)
        try:
            payload = {"path": "settings:/kef/host/volumeStep", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    response.raise_for_status()
                    settings['step'] = response.json()[0]["i16_"]
        except:
            pass

        # Get volume limit (is bool, not int)
        try:
            payload = {"path": "settings:/kef/host/volumeLimit", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    response.raise_for_status()
                    settings['limit_enabled'] = response.json()[0]["bool_"]
        except:
            pass

        # Get volume display (XIO only)
        try:
            payload = {"path": "settings:/kef/host/volumeDisplay", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    response.raise_for_status()
                    settings['display'] = response.json()[0]["string_"]
        except:
            pass

        return settings

    def set_volume_settings(self, max_volume=None, step=None, limit=None):
        """Set volume behavior settings.

        Args:
            max_volume (int, optional): Maximum volume (0-100)
            step (int, optional): Volume increment step
            limit (int, optional): Volume limiter (0-100)

        Example:
            speaker.set_volume_settings(max_volume=80, step=2)
            speaker.set_volume_settings(limit=75)
        """
        if max_volume is not None:
            if not 0 <= max_volume <= 100:
                raise ValueError(f"max_volume must be between 0 and 100, got {max_volume}")
            payload = {
                "path": "settings:/kef/host/maximumVolume",
                "roles": "value",
                "value": f'{{"type":"i32_","i32_":{max_volume}}}',
            }
            with requests.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

        if step is not None:
            if not 1 <= step <= 10:
                raise ValueError(f"step must be between 1 and 10, got {step}")
            payload = {
                "path": "settings:/kef/host/volumeStep",
                "roles": "value",
                "value": f'{{"type":"i16_","i16_":{step}}}',
            }
            with requests.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

        if limit is not None:
            payload = {
                "path": "settings:/kef/host/volumeLimit",
                "roles": "value",
                "value": f'{{"type":"bool_","bool_":{str(limit).lower()}}}',
            }
            with requests.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

    def get_standby_volume_behavior(self):
        """Get standby volume behavior setting.

        Returns:
            bool: True if using global volume mode, False if using per-input mode

        Example:
            is_global = speaker.get_standby_volume_behavior()
        """
        payload = {
            "path": "settings:/kef/host/advancedStandbyDefaultVol",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        # advancedStandbyDefaultVol: false = global, true = per-input
        return not json_output[0]["bool_"]

    def set_standby_volume_behavior(self, use_global):
        """Set standby volume behavior.

        Args:
            use_global (bool): True for global volume mode, False for per-input mode

        Example:
            speaker.set_standby_volume_behavior(True)  # Use global volume
            speaker.set_standby_volume_behavior(False)  # Use per-input volumes
        """
        # advancedStandbyDefaultVol: false = global, true = per-input
        payload = {
            "path": "settings:/kef/host/advancedStandbyDefaultVol",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(not use_global).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_startup_volume_enabled(self):
        """Get whether startup volume feature is enabled.

        When enabled, the speaker uses configured startup volumes when waking from standby.
        When disabled, the speaker resumes at the last volume level.

        Returns:
            bool: True if startup volume is enabled, False if disabled

        Example:
            is_enabled = speaker.get_startup_volume_enabled()
        """
        payload = {
            "path": "settings:/kef/host/standbyDefaultVol",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["bool_"]

    def set_startup_volume_enabled(self, enabled):
        """Enable or disable the startup volume feature.

        When enabled, the speaker uses configured startup volumes when waking from standby.
        When disabled, the speaker resumes at the last volume level.

        Args:
            enabled (bool): True to enable startup volume, False to disable

        Example:
            speaker.set_startup_volume_enabled(True)   # Enable startup volume
            speaker.set_startup_volume_enabled(False)  # Disable (resume at last volume)
        """
        payload = {
            "path": "settings:/kef/host/standbyDefaultVol",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    # Network Diagnostics Methods (Phase 4)
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
            response.raise_for_status()
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
            response.raise_for_status()
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
                {"path": "kef:eqProfile", "type": "itemWithValue"},
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["string_"]

    @property
    def speaker_name(self):
        """Get the friendly name of the Speaker"""
        payload = {"path": "settings:/deviceName", "roles": "value"}

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["string_"]

    @property
    def status(self):
        """Status of the speaker : standby or poweredOn"""
        payload = {"path": "settings:/kef/host/speakerStatus", "roles": "value"}

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["kefSpeakerStatus"]

    @status.setter
    def status(self, status):
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": {"type": "kefPhysicalSource", "kefPhysicalSource": status},
        }

        self._set_data(payload)

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
            response.raise_for_status()
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
            "value": {"type": "kefPhysicalSource", "kefPhysicalSource": source},
        }

        self._set_data(payload)

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
            response.raise_for_status()
            json_output = response.json()

        return json_output[0]["i32_"]

    @volume.setter
    def volume(self, volume):
        payload = {
            "path": "player:volume",
            "roles": "value",
            "value": {"type": "i32_", "i32_": volume},
        }

        self._set_data(payload)

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
            response.raise_for_status()
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
            response.raise_for_status()
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


    def get_auto_switch_hdmi(self):
        """Get auto-switch to HDMI setting.

        Returns:
            bool: True if auto-switch enabled, False otherwise

        Example:
            enabled = speaker.get_auto_switch_hdmi()
        """
        payload = {
            "path": "settings:/kef/host/autoSwitchToHDMI",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("bool_", False)

    def set_auto_switch_hdmi(self, enabled):
        """Set auto-switch to HDMI when signal detected.

        Args:
            enabled (bool): True to enable auto-switch, False to disable

        Example:
            speaker.set_auto_switch_hdmi(True)
        """
        payload = {
            "path": "settings:/kef/host/autoSwitchToHDMI",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_standby_mode(self):
        """Get auto-standby mode setting.

        Returns:
            str: Standby mode ('standby_20mins', 'standby_30mins', 'standby_60mins', 'standby_none')

        Example:
            mode = speaker.get_standby_mode()  # Returns 'standby_20mins' (ECO mode)
        """
        payload = {
            "path": "settings:/kef/host/standbyMode",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("string_", "standby_20mins")

    def set_standby_mode(self, mode):
        """Set auto-standby mode.

        Args:
            mode (str): Standby mode - 'standby_20mins' (ECO), 'standby_30mins',
                       'standby_60mins', or 'standby_none' (Never)

        Example:
            speaker.set_standby_mode('standby_20mins')  # ECO mode (20 minutes)
            speaker.set_standby_mode('standby_none')     # Never auto-standby
        """
        valid_modes = ['standby_20mins', 'standby_30mins', 'standby_60mins', 'standby_none']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Valid modes: {', '.join(valid_modes)}")

        payload = {
            "path": "settings:/kef/host/standbyMode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{mode}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_startup_tone(self):
        """Get startup tone setting.

        Returns:
            bool: True if startup beep enabled, False otherwise

        Example:
            enabled = speaker.get_startup_tone()
        """
        payload = {
            "path": "settings:/kef/host/startupTone",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("bool_", False)

    def set_startup_tone(self, enabled):
        """Set startup tone (power-on beep).

        Args:
            enabled (bool): True to enable startup beep, False to disable

        Example:
            speaker.set_startup_tone(False)  # Disable startup beep
        """
        payload = {
            "path": "settings:/kef/host/startupTone",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_subwoofer_wake_on_startup(self):
        """Get wake subwoofer on startup setting.

        When enabled, the speaker will wake the subwoofer when it powers on.
        This works with wired subwoofers.

        Returns:
            bool: True if wake subwoofer on startup is enabled
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOn",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("bool_", False)

    def set_subwoofer_wake_on_startup(self, enabled):
        """Set wake subwoofer on startup.

        When enabled, the speaker will wake the subwoofer when it powers on.
        This works with wired subwoofers.

        Args:
            enabled (bool): True to enable wake subwoofer on startup

        Example:
            speaker.set_subwoofer_wake_on_startup(True)
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOn",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_kw1_wake_on_startup(self):
        """Get KW1 wake on startup setting.

        When enabled, the speaker will wake a wireless subwoofer connected
        via KW1 adapter when it powers on. This is specifically for
        KC62/KF92 subwoofers with KW1 wireless adapter.

        Returns:
            bool: True if KW1 wake on startup is enabled
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOnKW1",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("bool_", False)

    def set_kw1_wake_on_startup(self, enabled):
        """Set KW1 wake on startup.

        When enabled, the speaker will wake a wireless subwoofer connected
        via KW1 adapter when it powers on. This is specifically for
        KC62/KF92 subwoofers with KW1 wireless adapter.

        Args:
            enabled (bool): True to enable KW1 wake on startup

        Example:
            speaker.set_kw1_wake_on_startup(True)
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOnKW1",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_wake_source(self):
        """Get wake-up source setting.

        Returns:
            str: Wake source ('wakeup_default', 'tv', 'wifi', 'bluetooth', 'optical')

        Example:
            source = speaker.get_wake_source()  # Returns 'wakeup_default'
        """
        payload = {
            "path": "settings:/kef/host/wakeUpSource",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("kefWakeUpSource", "wakeup_default")

    def set_wake_source(self, source):
        """Set wake-up source.

        Args:
            source (str): Wake source - 'wakeup_default', 'tv', 'wifi', 'bluetooth', 'optical'

        Example:
            speaker.set_wake_source('tv')  # Wake on TV/HDMI signal
        """
        valid_sources = ['wakeup_default', 'tv', 'wifi', 'bluetooth', 'optical']
        if source not in valid_sources:
            raise ValueError(f"Invalid source: {source}. Valid sources: {', '.join(valid_sources)}")

        payload = {
            "path": "settings:/kef/host/wakeUpSource",
            "roles": "value",
            "value": f'{{"type":"kefWakeUpSource","kefWakeUpSource":"{source}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_usb_charging(self):
        """Get USB charging setting.

        Returns:
            bool: True if USB charging enabled, False otherwise

        Example:
            enabled = speaker.get_usb_charging()
        """
        payload = {
            "path": "settings:/kef/host/usbCharging",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("bool_", False)

    def set_usb_charging(self, enabled):
        """Set USB port charging.

        Args:
            enabled (bool): True to enable USB charging, False to disable

        Example:
            speaker.set_usb_charging(True)  # Enable USB charging
        """
        payload = {
            "path": "settings:/kef/host/usbCharging",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_cable_mode(self):
        """Get cable mode (wired/wireless inter-speaker connection).

        Returns:
            str: Cable mode ('wired' or 'wireless')

        Example:
            mode = speaker.get_cable_mode()  # Returns 'wired'
        """
        payload = {
            "path": "settings:/kef/host/cableMode",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("string_", "wired")

    def set_cable_mode(self, mode):
        """Set cable mode for inter-speaker connection.

        Args:
            mode (str): Cable mode - 'wired' or 'wireless'

        Example:
            speaker.set_cable_mode('wireless')  # Use wireless connection
        """
        valid_modes = ['wired', 'wireless']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Valid modes: {', '.join(valid_modes)}")

        payload = {
            "path": "settings:/kef/host/cableMode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{mode}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_master_channel(self):
        """Get master channel (left/right speaker designation).

        Returns:
            str: Master channel ('left' or 'right')

        Example:
            channel = speaker.get_master_channel()  # Returns 'left'
        """
        payload = {
            "path": "settings:/kef/host/masterChannelMode",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output[0].get("kefMasterChannelMode", "right")

    def set_master_channel(self, channel):
        """Set master channel designation.

        Args:
            channel (str): Master channel - 'left' or 'right'

        Example:
            speaker.set_master_channel('right')  # Set as right speaker
        """
        valid_channels = ['left', 'right']
        if channel not in valid_channels:
            raise ValueError(f"Invalid channel: {channel}. Valid channels: {', '.join(valid_channels)}")

        payload = {
            "path": "settings:/kef/host/masterChannelMode",
            "roles": "value",
            "value": f'{{"type":"kefMasterChannelMode","kefMasterChannelMode":"{channel}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()


    def get_front_led(self):
        """Get front panel LED setting.

        Note: This API setting exists but has no visible effect on any
        currently tested KEF speakers (LSX II, LSX II LT, XIO). The setting
        may be reserved for future models or have no hardware implementation.

        Returns:
            bool: True if front LED is enabled, False if disabled

        Example:
            enabled = speaker.get_front_led()
        """
        payload = {
            "path": "settings:/kef/host/disableFrontLED",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        # Note: API uses "disable" so we invert the boolean
        return not json_output[0].get("bool_", False)

    def set_front_led(self, enabled):
        """Set front panel LED.

        Note: This API setting exists but has no visible effect on any
        currently tested KEF speakers (LSX II, LSX II LT, XIO). The setting
        may be reserved for future models or have no hardware implementation.

        Args:
            enabled (bool): True to enable LED, False to disable

        Example:
            speaker.set_front_led(False)  # Disable front LED
        """
        # Note: API uses "disable" so we invert the boolean
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableFrontLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_standby_led(self):
        """Get standby LED setting.

        Returns:
            bool: True if standby LED is enabled, False if disabled

        Example:
            enabled = speaker.get_standby_led()
        """
        payload = {
            "path": "settings:/kef/host/disableFrontStandbyLED",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        # Note: API uses "disable" so we invert the boolean
        return not json_output[0].get("bool_", False)

    def set_standby_led(self, enabled):
        """Set standby LED.

        Args:
            enabled (bool): True to enable LED, False to disable

        Example:
            speaker.set_standby_led(True)  # Enable standby LED
        """
        # Note: API uses "disable" so we invert the boolean
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableFrontStandbyLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_top_panel_enabled(self):
        """Get top panel (touch controls) enabled setting.

        Returns:
            bool: True if top panel is enabled, False if disabled

        Example:
            enabled = speaker.get_top_panel_enabled()
        """
        payload = {
            "path": "settings:/kef/host/disableTopPanel",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        # Note: API uses "disable" so we invert the boolean
        return not json_output[0].get("bool_", False)

    def set_top_panel_enabled(self, enabled):
        """Set top panel (touch controls) enabled.

        Args:
            enabled (bool): True to enable top panel, False to disable

        Example:
            speaker.set_top_panel_enabled(False)  # Disable touch panel
        """
        # Note: API uses "disable" so we invert the boolean
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableTopPanel",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_top_panel_led(self):
        """Get top panel LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)

        Example:
            enabled = speaker.get_top_panel_led()  # XIO only
            if enabled is not None:
                print(f"Top panel LED: {'ON' if enabled else 'OFF'}")
        """
        payload = {
            "path": "settings:/kef/host/topPanelLED",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                    return json_output[0].get("bool_", False)
            return None

    def set_top_panel_led(self, enabled):
        """Set top panel LED (XIO only).

        Args:
            enabled (bool): True to enable LED, False to disable

        Example:
            speaker.set_top_panel_led(True)  # XIO only
        """
        payload = {
            "path": "settings:/kef/host/topPanelLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    def get_top_panel_standby_led(self):
        """Get top panel standby LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)

        Example:
            enabled = speaker.get_top_panel_standby_led()  # XIO only
            if enabled is not None:
                print(f"Top panel standby LED: {'ON' if enabled else 'OFF'}")
        """
        payload = {
            "path": "settings:/kef/host/topPanelStandbyLED",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                    return json_output[0].get("bool_", False)
            return None

    def set_top_panel_standby_led(self, enabled):
        """Set top panel standby LED (XIO only).

        Args:
            enabled (bool): True to enable LED, False to disable

        Example:
            speaker.set_top_panel_standby_led(False)  # XIO only
        """
        payload = {
            "path": "settings:/kef/host/topPanelStandbyLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

    # ===== Remote Control Methods =====


    def get_fixed_volume_mode(self):
        """Get fixed volume mode setting.

        Returns:
            int or None: Fixed volume level (0-100), or None if disabled

        Example:
            volume = speaker.get_fixed_volume_mode()
            if volume is not None:
                print(f"Fixed volume: {volume}")
            else:
                print("Fixed volume mode disabled")
        """
        payload = {
            "path": "settings:/kef/host/remote/userFixedVolume",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()
            value = json_output[0].get("i32_", -1)
            return None if value < 0 else value

    def set_fixed_volume_mode(self, volume):
        """Set fixed volume mode (locks volume at specific level).

        Args:
            volume (int or None): Volume level to lock (0-100), or None to disable

        Example:
            speaker.set_fixed_volume_mode(50)    # Lock volume at 50%
            speaker.set_fixed_volume_mode(None)  # Disable fixed volume mode
        """
        if volume is None:
            volume = -1  # -1 disables fixed volume mode
        elif not isinstance(volume, int) or volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0-100 or None to disable")

        payload = {
            "path": "settings:/kef/host/remote/userFixedVolume",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{volume}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()


    # Generic write method
    def set_request(self, path, roles="value", value=None):
        """Generic method to set data via any API path.

        Args:
            path: API path to set (e.g., "firmwareupdate:downloadNewUpdate")
            roles: API roles parameter (default: "value", use "activate" for actions)
            value: Optional value to set (can be JSON string or dict)

        Returns:
            JSON response from API
        """
        payload = {
            "path": path,
            "roles": roles,
        }
        if value is not None:
            payload["value"] = value
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = response.json()

        return json_output


class KefAsyncConnector:
    def __init__(self, host, session=None, model=None):
        self.host = host
        self._session = session
        self._speaker_model = _MODEL_ALIASES.get(model, model)
        self.previous_volume = (
            15  # Hardcoded previous volume, in case unmute is used before mute
        )
        self.last_polled = None
        self.polling_queue = None
        self._previous_poll_song_status = False

    async def close_session(self):
        """close session"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def resurect_session(self):
        if self._session is None:
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

    async def _set_data(self, payload):
        if self._speaker_model is None:
            self._speaker_model = await self.get_speaker_model()
        await self.resurect_session()
        if self._speaker_model in _POST_MODELS:
            async with self._session.post(
                "http://" + self.host + "/api/setData", json=payload
            ) as response:
                response.raise_for_status()
                return await response.json()
        else:
            payload = dict(payload)
            payload["value"] = json.dumps(payload["value"], separators=(",", ":"))
            async with self._session.get(
                "http://" + self.host + "/api/setData", params=payload
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def _track_control(self, command):
        """toogle play/pause"""
        payload = {
            "path": "player:player/control",
            "roles": "activate",
            "value": {"control": command},
        }
        await self._set_data(payload)

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
            response.raise_for_status()
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
            response.raise_for_status()
            json_output = await response.json()

        return json_output

    async def set_request(self, path, roles="value", value=None):
        """Generic method to set data via any API path.

        Args:
            path: API path to set (e.g., "firmwareupdate:install")
            roles: API roles parameter (default: "value")
            value: Optional value to send (JSON string)

        Returns:
            JSON response from API
        """
        payload = {
            "path": path,
            "roles": roles,
        }
        if value is not None:
            payload["value"] = value
        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
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
            "value": {"type": "kefPhysicalSource", "kefPhysicalSource": source},
        }
        await self._set_data(payload)

    async def set_volume(self, volume):
        """Set speaker volume (between 0 and 100)"""
        payload = {
            "path": "player:volume",
            "roles": "value",
            "value": {"type": "i32_", "i32_": volume},
        }
        await self._set_data(payload)

    async def set_status(self, status):
        payload = {
            "path": "settings:/kef/play/physicalSource",
            "roles": "value",
            "value": {"type": "kefPhysicalSource", "kefPhysicalSource": status},
        }
        await self._set_data(payload)

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
                {"path": "kef:eqProfile", "type": "itemWithValue"},
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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

    async def get_default_volume(self, input_source):
        """Get default volume for a specific input source.

        Args:
            input_source (str): Input source name (wifi, bluetooth, optic, coaxial, usb, analog, tv)

        Returns:
            int: Volume level (0-100) for the specified input

        Example:
            volume = await speaker.get_default_volume('wifi')  # Returns 50
        """
        # Map input source to API path
        source_map = {
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optic': 'Optical',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analog': 'Analogue',
            'analogue': 'Analogue',
            'tv': 'TV',
            'hdmi': 'TV'
        }

        if input_source.lower() not in source_map:
            raise ValueError(f"Invalid input source: {input_source}. Valid sources: {', '.join(source_map.keys())}")

        api_source = source_map[input_source.lower()]
        payload = {
            "path": f"settings:/kef/host/defaultVolume{api_source}",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

        return json_output[0]["i32_"]

    async def set_default_volume(self, input_source, volume):
        """Set default volume for a specific input source.

        Args:
            input_source (str): Input source name (global, wifi, bluetooth, optic, coaxial, usb, analog, tv)
            volume (int): Volume level (0-100)

        Example:
            await speaker.set_default_volume('global', 30)  # Set global startup volume
            await speaker.set_default_volume('wifi', 50)
            await speaker.set_default_volume('bluetooth', 40)
        """
        if not 0 <= volume <= 100:
            raise ValueError(f"Volume must be between 0 and 100, got {volume}")

        # Map input source to API path
        source_map = {
            'global': 'Global',
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optic': 'Optical',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analog': 'Analogue',
            'analogue': 'Analogue',
            'tv': 'TV',
            'hdmi': 'TV'
        }

        if input_source.lower() not in source_map:
            raise ValueError(f"Invalid input source: {input_source}. Valid sources: {', '.join(source_map.keys())}")

        api_source = source_map[input_source.lower()]
        payload = {
            "path": f"settings:/kef/host/defaultVolume{api_source}",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{volume}}}',
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_all_default_volumes(self):
        """Get default volumes for all input sources on this speaker model.

        Returns:
            dict: Dictionary of input sources and their default volumes

        Example:
            volumes = await speaker.get_all_default_volumes()
            # Returns: {'global': 50, 'wifi': 45, 'bluetooth': 40, 'optical': 50, ...}
        """
        # Define all possible inputs
        all_inputs = ['global', 'wifi', 'bluetooth', 'optical', 'coaxial', 'usb', 'analogue', 'tv']

        # Map to API names
        source_map = {
            'global': 'Global',
            'wifi': 'Wifi',
            'bluetooth': 'Bluetooth',
            'optical': 'Optical',
            'coaxial': 'Coaxial',
            'usb': 'USB',
            'analogue': 'Analogue',
            'tv': 'TV'
        }

        volumes = {}
        await self.resurect_session()

        for input_source in all_inputs:
            try:
                api_source = source_map[input_source]
                payload = {
                    "path": f"settings:/kef/host/defaultVolume{api_source}",
                    "roles": "value",
                }

                async with self._session.get(
                    "http://" + self.host + "/api/getData", params=payload
                ) as response:
                    if response.status == 200:
                        response.raise_for_status()
                        json_output = await response.json()
                        volumes[input_source] = json_output[0]["i32_"]
            except:
                # Skip inputs that don't exist on this model
                pass

        return volumes

    async def get_volume_settings(self):
        """Get volume behavior settings.

        Returns:
            dict: Volume settings including max_volume, step, limit, display mode

        Example:
            settings = await speaker.get_volume_settings()
            # Returns: {'max_volume': 100, 'step': 1, 'limit': 100, 'display': 'linear'}
        """
        settings = {}
        await self.resurect_session()

        # Get maximum volume
        try:
            payload = {"path": "settings:/kef/host/maximumVolume", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    response.raise_for_status()
                    json_output = await response.json()
                    settings['max_volume'] = json_output[0]["i32_"]
        except:
            pass

        # Get volume step (uses i16_ not i32_)
        try:
            payload = {"path": "settings:/kef/host/volumeStep", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    response.raise_for_status()
                    json_output = await response.json()
                    settings['step'] = json_output[0]["i16_"]
        except:
            pass

        # Get volume limit (is bool, not int)
        try:
            payload = {"path": "settings:/kef/host/volumeLimit", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    response.raise_for_status()
                    json_output = await response.json()
                    settings['limit_enabled'] = json_output[0]["bool_"]
        except:
            pass

        # Get volume display (XIO only)
        try:
            payload = {"path": "settings:/kef/host/volumeDisplay", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    response.raise_for_status()
                    json_output = await response.json()
                    settings['display'] = json_output[0]["string_"]
        except:
            pass

        return settings

    async def set_volume_settings(self, max_volume=None, step=None, limit=None):
        """Set volume behavior settings.

        Args:
            max_volume (int, optional): Maximum volume (0-100)
            step (int, optional): Volume increment step (1-10)
            limit (bool, optional): Enable volume limiter

        Example:
            await speaker.set_volume_settings(max_volume=80, step=2)
            await speaker.set_volume_settings(limit=True)
        """
        await self.resurect_session()

        if max_volume is not None:
            if not 0 <= max_volume <= 100:
                raise ValueError(f"max_volume must be between 0 and 100, got {max_volume}")
            payload = {
                "path": "settings:/kef/host/maximumVolume",
                "roles": "value",
                "value": f'{{"type":"i32_","i32_":{max_volume}}}',
            }
            async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

        if step is not None:
            if not 1 <= step <= 10:
                raise ValueError(f"step must be between 1 and 10, got {step}")
            payload = {
                "path": "settings:/kef/host/volumeStep",
                "roles": "value",
                "value": f'{{"type":"i16_","i16_":{step}}}',
            }
            async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

        if limit is not None:
            payload = {
                "path": "settings:/kef/host/volumeLimit",
                "roles": "value",
                "value": f'{{"type":"bool_","bool_":{str(limit).lower()}}}',
            }
            async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
                pass

    async def get_standby_volume_behavior(self):
        """Get standby volume behavior setting.

        Returns:
            bool: True if using global volume mode (All sources), False if using per-input mode (Individual sources)

        Example:
            is_global = await speaker.get_standby_volume_behavior()
        """
        payload = {
            "path": "settings:/kef/host/advancedStandbyDefaultVol",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

        # advancedStandbyDefaultVol: false = global (All sources), true = per-input (Individual sources)
        return not json_output[0]["bool_"]

    async def set_standby_volume_behavior(self, use_global):
        """Set standby volume behavior.

        Args:
            use_global (bool): True for global volume mode (All sources), False for per-input mode (Individual sources)

        Example:
            await speaker.set_standby_volume_behavior(True)  # All sources
            await speaker.set_standby_volume_behavior(False)  # Individual sources
        """
        # advancedStandbyDefaultVol: false = global (All sources), true = per-input (Individual sources)
        payload = {
            "path": "settings:/kef/host/advancedStandbyDefaultVol",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(not use_global).lower()}}}',
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_startup_volume_enabled(self):
        """Get whether reset volume feature is enabled.

        When enabled, the speaker uses configured reset volumes when waking from standby.
        When disabled, the speaker resumes at the last volume level.

        Returns:
            bool: True if reset volume is enabled, False if disabled

        Example:
            is_enabled = await speaker.get_startup_volume_enabled()
        """
        payload = {
            "path": "settings:/kef/host/standbyDefaultVol",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

        return json_output[0]["bool_"]

    async def set_startup_volume_enabled(self, enabled):
        """Enable or disable the reset volume feature.

        When enabled, the speaker uses configured reset volumes when waking from standby.
        When disabled, the speaker resumes at the last volume level.

        Args:
            enabled (bool): True to enable reset volume, False to disable

        Example:
            await speaker.set_startup_volume_enabled(True)   # Enable reset volume
            await speaker.set_startup_volume_enabled(False)  # Disable (resume at last volume)
        """
        payload = {
            "path": "settings:/kef/host/standbyDefaultVol",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            response.raise_for_status()
            json_output = await response.json()

    # Async Network Diagnostics Methods (Phase 4)

    async def get_auto_switch_hdmi(self):
        """Get auto-switch to HDMI setting."""
        payload = {"path": "settings:/kef/host/autoSwitchToHDMI", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("bool_", False)

    async def set_auto_switch_hdmi(self, enabled):
        """Set auto-switch to HDMI when signal detected."""
        payload = {
            "path": "settings:/kef/host/autoSwitchToHDMI",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_standby_mode(self):
        """Get auto-standby mode setting."""
        payload = {"path": "settings:/kef/host/standbyMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("string_", "standby_20mins")

    async def set_standby_mode(self, mode):
        """Set auto-standby mode."""
        valid_modes = ['standby_20mins', 'standby_30mins', 'standby_60mins', 'standby_none']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Valid modes: {', '.join(valid_modes)}")
        payload = {
            "path": "settings:/kef/host/standbyMode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{mode}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_startup_tone(self):
        """Get startup tone setting."""
        payload = {"path": "settings:/kef/host/startupTone", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("bool_", False)

    async def set_startup_tone(self, enabled):
        """Set startup tone (power-on beep)."""
        payload = {
            "path": "settings:/kef/host/startupTone",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_subwoofer_wake_on_startup(self):
        """Get wake subwoofer on startup setting.

        When enabled, the speaker will wake the subwoofer when it powers on.
        This works with wired subwoofers.

        Returns:
            bool: True if wake subwoofer on startup is enabled
        """
        payload = {"path": "settings:/kef/host/subwooferForceOn", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("bool_", False)

    async def set_subwoofer_wake_on_startup(self, enabled):
        """Set wake subwoofer on startup.

        When enabled, the speaker will wake the subwoofer when it powers on.
        This works with wired subwoofers.

        Args:
            enabled (bool): True to enable wake subwoofer on startup
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOn",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_kw1_wake_on_startup(self):
        """Get KW1 wake on startup setting.

        When enabled, the speaker will wake a wireless subwoofer connected
        via KW1 adapter when it powers on. This is specifically for
        KC62/KF92 subwoofers with KW1 wireless adapter.

        Returns:
            bool: True if KW1 wake on startup is enabled
        """
        payload = {"path": "settings:/kef/host/subwooferForceOnKW1", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("bool_", False)

    async def set_kw1_wake_on_startup(self, enabled):
        """Set KW1 wake on startup.

        When enabled, the speaker will wake a wireless subwoofer connected
        via KW1 adapter when it powers on. This is specifically for
        KC62/KF92 subwoofers with KW1 wireless adapter.

        Args:
            enabled (bool): True to enable KW1 wake on startup
        """
        payload = {
            "path": "settings:/kef/host/subwooferForceOnKW1",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_wake_source(self):
        """Get wake-up source setting."""
        payload = {"path": "settings:/kef/host/wakeUpSource", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("kefWakeUpSource", "wakeup_default")

    async def set_wake_source(self, source):
        """Set wake-up source."""
        valid_sources = ['wakeup_default', 'tv', 'wifi', 'bluetooth', 'optical']
        if source not in valid_sources:
            raise ValueError(f"Invalid source: {source}. Valid sources: {', '.join(valid_sources)}")
        payload = {
            "path": "settings:/kef/host/wakeUpSource",
            "roles": "value",
            "value": f'{{"type":"kefWakeUpSource","kefWakeUpSource":"{source}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_usb_charging(self):
        """Get USB charging setting."""
        payload = {"path": "settings:/kef/host/usbCharging", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("bool_", False)

    async def set_usb_charging(self, enabled):
        """Set USB port charging."""
        payload = {
            "path": "settings:/kef/host/usbCharging",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_cable_mode(self):
        """Get cable mode (wired/wireless inter-speaker connection)."""
        payload = {"path": "settings:/kef/host/cableMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("string_", "wired")

    async def set_cable_mode(self, mode):
        """Set cable mode for inter-speaker connection."""
        valid_modes = ['wired', 'wireless']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Valid modes: {', '.join(valid_modes)}")
        payload = {
            "path": "settings:/kef/host/cableMode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{mode}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_master_channel(self):
        """Get master channel (left/right speaker designation)."""
        payload = {"path": "settings:/kef/host/masterChannelMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return json_output[0].get("kefMasterChannelMode", "right")

    async def set_master_channel(self, channel):
        """Set master channel designation."""
        valid_channels = ['left', 'right']
        if channel not in valid_channels:
            raise ValueError(f"Invalid channel: {channel}. Valid channels: {', '.join(valid_channels)}")
        payload = {
            "path": "settings:/kef/host/masterChannelMode",
            "roles": "value",
            "value": f'{{"type":"kefMasterChannelMode","kefMasterChannelMode":"{channel}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()


    async def get_front_led(self):
        """Get front panel LED setting.

        Note: This API setting exists but has no visible effect on any
        currently tested KEF speakers (LSX II, LSX II LT, XIO).
        """
        payload = {"path": "settings:/kef/host/disableFrontLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return not json_output[0].get("bool_", False)

    async def set_front_led(self, enabled):
        """Set front panel LED.

        Note: This API setting exists but has no visible effect on any
        currently tested KEF speakers (LSX II, LSX II LT, XIO).
        """
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableFrontLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_standby_led(self):
        """Get standby LED setting."""
        payload = {"path": "settings:/kef/host/disableFrontStandbyLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return not json_output[0].get("bool_", False)

    async def set_standby_led(self, enabled):
        """Set standby LED."""
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableFrontStandbyLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_top_panel_enabled(self):
        """Get top panel (touch controls) enabled setting."""
        payload = {"path": "settings:/kef/host/disableTopPanel", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        return not json_output[0].get("bool_", False)

    async def set_top_panel_enabled(self, enabled):
        """Set top panel (touch controls) enabled."""
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableTopPanel",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_top_panel_led(self):
        """Get top panel LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)
        """
        payload = {"path": "settings:/kef/host/topPanelLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0].get("bool_", False)
        return None

    async def set_top_panel_led(self, enabled):
        """Set top panel LED (XIO only)."""
        payload = {
            "path": "settings:/kef/host/topPanelLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    async def get_top_panel_standby_led(self):
        """Get top panel standby LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)
        """
        payload = {"path": "settings:/kef/host/topPanelStandbyLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0].get("bool_", False)
        return None

    async def set_top_panel_standby_led(self, enabled):
        """Set top panel standby LED (XIO only)."""
        payload = {
            "path": "settings:/kef/host/topPanelStandbyLED",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

    # ===== Remote Control Methods (Async) =====


    async def get_fixed_volume_mode(self):
        """Get fixed volume mode setting.

        Returns:
            int or None: Fixed volume level (0-100), or None if disabled

        Example:
            volume = await speaker.get_fixed_volume_mode()
            if volume is not None:
                print(f"Fixed volume: {volume}")
            else:
                print("Fixed volume mode disabled")
        """
        payload = {"path": "settings:/kef/host/remote/userFixedVolume", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()
        value = json_output[0].get("i32_", -1)
        return None if value < 0 else value

    async def set_fixed_volume_mode(self, volume):
        """Set fixed volume mode (locks volume at specific level).

        Args:
            volume (int or None): Volume level to lock (0-100), or None to disable

        Example:
            await speaker.set_fixed_volume_mode(50)    # Lock volume at 50%
            await speaker.set_fixed_volume_mode(None)  # Disable fixed volume mode
        """
        if volume is None:
            volume = -1  # -1 disables fixed volume mode
        elif not isinstance(volume, int) or volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0-100 or None to disable")

        payload = {
            "path": "settings:/kef/host/remote/userFixedVolume",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{volume}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            response.raise_for_status()
            json_output = await response.json()

