import requests
import aiohttp
import time


class KefConnector:
    def __init__(self, host):
        self.host = host
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
        info_dict["artist"] = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
            .get("artist")
        )
        info_dict["album"] = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
            .get("album")
        )
        info_dict["cover_url"] = song_data.get("trackRoles", {}).get("icon", None)

        return info_dict

    def _get_polling_queue(self, song_status=True):
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

    def poll_speaker(self, timeout=10, song_status=False):
        """poll speaker for info"""

        # check if it is necessary to get a new queue
        # recreate a new queue if polling_queue is None
        # or if last poll was more than 50 seconds ago
        if (
            (self.polling_queue == None)
            or ((time.time() - self.last_polled) > 50)
            or (song_status != self._previous_poll_song_status)
        ):
            self._previous_poll_song_status = song_status
            self._get_polling_queue(song_status=song_status)

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


class KefAsyncConnector:
    def __init__(self, host, session=None):
        self.host = host
        self._session = session
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
        info_dict["artist"] = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
            .get("artist")
        )
        info_dict["album"] = (
            song_data.get("trackRoles", {})
            .get("mediaData", {})
            .get("metaData", {})
            .get("album")
        )
        info_dict["cover_url"] = song_data.get("trackRoles", {}).get("icon", None)

        return info_dict

    async def get_polling_queue(self, song_status=None):
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

    async def poll_speaker(self, timeout=10, song_status=False):
        """poll speaker for info"""

        # check if it is necessary to get a new queue
        if (
            (self.polling_queue == None)
            or ((time.time() - self.last_polled) > 50)
            or (song_status != self._previous_polling_song_status)
        ):
            await self.get_polling_queue(song_status=song_status)

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
