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

# Balance: v1 API uses 0-60 (30=center), v2 API uses -30 to +30 (0=center)
# We use v2 API which is more intuitive
BALANCE_MIN = -30  # Full left
BALANCE_MAX = 30   # Full right
BALANCE_CENTER = 0

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

    # Volume Management Methods (Phase 3)
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
                    settings['max_volume'] = response.json()[0]["i32_"]
        except:
            pass

        # Get volume step (uses i16_ not i32_)
        try:
            payload = {"path": "settings:/kef/host/volumeStep", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    settings['step'] = response.json()[0]["i16_"]
        except:
            pass

        # Get volume limit (is bool, not int)
        try:
            payload = {"path": "settings:/kef/host/volumeLimit", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    settings['limit_enabled'] = response.json()[0]["bool_"]
        except:
            pass

        # Get volume display (XIO only)
        try:
            payload = {"path": "settings:/kef/host/volumeDisplay", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
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
            json_output = response.json()

    # Network Diagnostics Methods (Phase 4)
    def ping_internet(self):
        """Ping internet to check connectivity.

        Returns:
            int: Ping time in milliseconds, or 0 if offline

        Example:
            ping_ms = speaker.ping_internet()  # Returns 15 (ms)
        """
        payload = {
            "path": "kef:network/pingInternet",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0].get("i32_", 0)

    def get_network_stability(self):
        """Get network stability status.

        Returns:
            str: Network stability ('idle', 'stable', or 'unstable')

        Example:
            stability = speaker.get_network_stability()  # Returns 'stable'
        """
        payload = {
            "path": "kef:network/pingInternetStability",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0].get("string_", "idle")

    def start_speed_test(self):
        """Start network speed test.

        Use get_speed_test_status() to monitor progress and
        get_speed_test_results() to retrieve results when complete.

        Example:
            speaker.start_speed_test()
            # Wait and check status...
        """
        payload = {
            "path": "kef:speedTest/start",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

    def get_speed_test_status(self):
        """Get speed test status.

        Returns:
            str: Test status ('idle', 'running', or 'complete')

        Example:
            status = speaker.get_speed_test_status()  # Returns 'running'
        """
        payload = {
            "path": "kef:speedTest/status",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0].get("string_", "idle")

    def get_speed_test_results(self):
        """Get speed test results.

        Returns:
            dict: Speed test results with keys:
                - avg_download: Average download speed (Mbps)
                - current_download: Current download speed (Mbps)
                - packet_loss: Packet loss percentage

        Example:
            results = speaker.get_speed_test_results()
            # Returns: {'avg_download': 45.2, 'current_download': 47.1, 'packet_loss': 0.5}
        """
        results = {}

        # Get average download speed
        try:
            payload = {"path": "kef:speedTest/averageDownloadSpeed", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    json_output = response.json()
                    results['avg_download'] = json_output[0].get("double_", 0.0)
        except:
            results['avg_download'] = 0.0

        # Get current download speed
        try:
            payload = {"path": "kef:speedTest/currentDownloadSpeed", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    json_output = response.json()
                    results['current_download'] = json_output[0].get("double_", 0.0)
        except:
            results['current_download'] = 0.0

        # Get packet loss
        try:
            payload = {"path": "kef:speedTest/packetLoss", "roles": "value"}
            with requests.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status_code == 200:
                    json_output = response.json()
                    results['packet_loss'] = json_output[0].get("double_", 0.0)
        except:
            results['packet_loss'] = 0.0

        return results

    def stop_speed_test(self):
        """Stop running speed test.

        Example:
            speaker.stop_speed_test()
        """
        payload = {
            "path": "kef:speedTest/stop",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

    # System Behavior Methods (Phase 5)
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
            json_output = response.json()

    def get_speaker_status(self):
        """Get speaker power status.

        Returns:
            str: Speaker status ('powerOn' or 'standby')

        Example:
            status = speaker.get_speaker_status()  # Returns 'powerOn'
        """
        payload = {
            "path": "settings:/kef/host/speakerStatus",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        return json_output[0].get("kefSpeakerStatus", "standby")

    # LED Control Methods (Phase 6)
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
            json_output = response.json()

    # ===== Remote Control Methods =====

    def get_remote_ir_enabled(self):
        """Get IR remote control enabled state.

        Returns:
            bool: True if IR remote is enabled, False if disabled

        Example:
            enabled = speaker.get_remote_ir_enabled()
            print(f"IR remote: {'Enabled' if enabled else 'Disabled'}")
        """
        payload = {
            "path": "settings:/kef/host/remote/remoteIR",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("bool_", True)

    def set_remote_ir_enabled(self, enabled):
        """Enable or disable IR remote control.

        Args:
            enabled (bool): True to enable IR remote, False to disable

        Example:
            speaker.set_remote_ir_enabled(True)   # Enable IR remote
            speaker.set_remote_ir_enabled(False)  # Disable IR remote
        """
        payload = {
            "path": "settings:/kef/host/remote/remoteIR",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_ir_code_set(self):
        """Get IR code set (used to avoid conflicts with other devices).

        Returns:
            str: IR code set ('ir_code_set_a', 'ir_code_set_b', or 'ir_code_set_c')

        Example:
            code_set = speaker.get_ir_code_set()
            print(f"IR code set: {code_set}")
        """
        payload = {
            "path": "settings:/kef/host/remote/remoteIRCode",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "ir_code_set_a")

    def set_ir_code_set(self, code_set):
        """Set IR code set (used to avoid conflicts with other devices).

        Args:
            code_set (str): IR code set - 'ir_code_set_a', 'ir_code_set_b', or 'ir_code_set_c'

        Example:
            speaker.set_ir_code_set('ir_code_set_a')  # Default
            speaker.set_ir_code_set('ir_code_set_b')  # Use if conflicts with other remotes
            speaker.set_ir_code_set('ir_code_set_c')  # Alternative code set
        """
        valid_codes = ['ir_code_set_a', 'ir_code_set_b', 'ir_code_set_c']
        if code_set not in valid_codes:
            raise ValueError(f"Invalid code set '{code_set}'. Must be one of: {valid_codes}")

        payload = {
            "path": "settings:/kef/host/remote/remoteIRCode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{code_set}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_eq_button(self, button_num):
        """Get EQ button preset (XIO soundbar only).

        Args:
            button_num (int): Button number (1 or 2)

        Returns:
            str: Sound profile assigned to button ('dialogue', 'night', 'music', 'movie', etc.)

        Example:
            preset1 = speaker.get_eq_button(1)  # XIO only
            preset2 = speaker.get_eq_button(2)  # XIO only
            print(f"EQ Button 1: {preset1}, Button 2: {preset2}")
        """
        if button_num not in [1, 2]:
            raise ValueError("Button number must be 1 or 2")

        payload = {
            "path": f"settings:/kef/host/remote/eqButton{button_num}",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "default")

    def set_eq_button(self, button_num, preset):
        """Set EQ button preset (XIO soundbar only).

        Args:
            button_num (int): Button number (1 or 2)
            preset (str): Sound profile to assign ('dialogue', 'night', 'music', 'movie', 'default', 'direct')

        Example:
            speaker.set_eq_button(1, 'dialogue')  # XIO: Button 1 = dialogue mode
            speaker.set_eq_button(2, 'night')     # XIO: Button 2 = night mode
        """
        if button_num not in [1, 2]:
            raise ValueError("Button number must be 1 or 2")

        valid_presets = ['dialogue', 'night', 'music', 'movie', 'default', 'direct']
        if preset not in valid_presets:
            raise ValueError(f"Invalid preset '{preset}'. Must be one of: {valid_presets}")

        payload = {
            "path": f"settings:/kef/host/remote/eqButton{button_num}",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{preset}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_favourite_button_action(self):
        """Get favourite button action.

        Returns:
            str: Action assigned to favourite button (e.g., 'nextSource')

        Example:
            action = speaker.get_favourite_button_action()
            print(f"Favourite button action: {action}")
        """
        payload = {
            "path": "settings:/kef/host/remote/favouriteButton",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "nextSource")

    def set_favourite_button_action(self, action):
        """Set favourite button action.

        Args:
            action (str): Action to assign (e.g., 'nextSource')

        Example:
            speaker.set_favourite_button_action('nextSource')
        """
        payload = {
            "path": "settings:/kef/host/remote/favouriteButton",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{action}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

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
            json_output = response.json()

    # ===== XIO Calibration Methods =====

    def get_calibration_status(self):
        """Get room calibration status (XIO soundbar only).

        Returns:
            dict: Calibration status with keys, or None if not available (non-XIO speakers):
                - isCalibrated (bool): Whether calibration is complete
                - year (int): Calibration year
                - month (int): Calibration month
                - day (int): Calibration day
                - stability (int): Network stability during calibration

        Example:
            status = speaker.get_calibration_status()  # XIO only
            if status and status['isCalibrated']:
                print(f"Calibrated on: {status['year']}-{status['month']:02d}-{status['day']:02d}")
        """
        payload = {
            "path": "settings:/kef/dsp/calibrationStatus",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()

        # Parse the calibration status structure
        # API returns nested structure: [{"type":"kefDspCalibrationStatus","kefDspCalibrationStatus":{...}}]
        if isinstance(json_output, dict) and 'error' in json_output:
            return None
        if json_output and len(json_output) > 0:
            status_data = json_output[0].get('kefDspCalibrationStatus', {})
            if not status_data:
                return None
            return {
                'isCalibrated': status_data.get('isCalibrated', False),
                'year': status_data.get('year', 0),
                'month': status_data.get('month', 0),
                'day': status_data.get('day', 0),
                'stability': status_data.get('stability', 0)
            }
        return None

    def get_calibration_result(self):
        """Get room calibration dB adjustment result (XIO soundbar only).

        Returns:
            float: dB adjustment applied by calibration (typically negative), or None if not available (non-XIO speakers)

        Example:
            result = speaker.get_calibration_result()  # XIO only
            if result is not None:
                print(f"Calibration adjustment: {result} dB")
        """
        payload = {
            "path": "settings:/kef/dsp/calibrationResult",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                # API returns double_ type, not i32_
                return json_output[0].get("double_", None)
            return None

    def get_calibration_step(self):
        """Get current calibration step (XIO soundbar only).

        Returns:
            str: Current calibration step, or None if not available (non-XIO speakers):
                - 'step_1_start': Calibration starting
                - 'step_2_processing': Calibration in progress
                - 'step_3_complete': Calibration complete

        Example:
            step = speaker.get_calibration_step()  # XIO only
            if step:
                print(f"Calibration step: {step}")
        """
        payload = {
            "path": "settings:/kef/dsp/calibrationStep",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                    return json_output[0].get("string_", "step_1_start")
            return None

    def start_calibration(self):
        """Start room calibration (XIO soundbar only).

        Triggers the room calibration process. The speaker will play test tones
        and analyze the room acoustics. Monitor calibration_step to track progress.

        Example:
            speaker.start_calibration()  # XIO only
            # Check speaker.get_calibration_step() to monitor progress
        """
        payload = {
            "path": "kefdsp:/calibration/start",
            "roles": "activate",
            "value": "{}",
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    def stop_calibration(self):
        """Stop room calibration in progress (XIO soundbar only).

        Cancels a running calibration process.

        Example:
            speaker.stop_calibration()  # XIO only
        """
        payload = {
            "path": "kefdsp:/calibration/stop",
            "roles": "activate",
            "value": "{}",
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    # ===== BLE Firmware Methods (XIO KW2 Subwoofer Module) =====

    def check_ble_firmware_update(self):
        """Trigger BLE firmware update check (XIO soundbar only - KW2 subwoofer module).

        This triggers the speaker to check KEF's servers for KW2 module updates.
        After calling this, poll get_ble_firmware_status() which will return
        "updateAvailable" if an update exists.

        Example:
            speaker.check_ble_firmware_update()  # XIO only - triggers check
            time.sleep(5)  # Wait for check to complete
            status = speaker.get_ble_firmware_status()
            if status == "updateAvailable":
                print("Update available!")
        """
        payload = {
            "path": "kef:ble/checkForUpdates",
            "roles": "activate",
            "value": "{}",
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    def get_ble_firmware_status(self):
        """Get BLE firmware update status (XIO soundbar only - KW2 subwoofer module).

        Returns:
            str: Update status - 'startUp', 'downloading', 'installing', 'complete'
                Returns None if not available (non-XIO speakers)

        Example:
            status = speaker.get_ble_firmware_status()  # XIO only
            if status:
                print(f"BLE firmware status: {status}")
        """
        payload = {
            "path": "kef:ble/updateStatus",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if isinstance(json_output, list) and len(json_output) > 0:
                    return json_output[0].get("string_", "startUp")
            return None

    def get_ble_firmware_version(self):
        """Get BLE firmware version from update server (XIO soundbar only - KW2 subwoofer module).

        Note: This returns the version available on KEF's update server, NOT the installed version.
        The KEF API does not expose the actual installed version on the KW2 module.

        Returns:
            str: BLE firmware version from server (e.g., "1.2.3", "Empty" if not set, or None if not available)

        Example:
            version = speaker.get_ble_firmware_version()  # XIO only
            if version:
                print(f"BLE server version: {version}")
        """
        payload = {
            "path": "kef:ble/updateServer/txVersion",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                    return json_output[0].get("string_", "Empty")
            return None

    def get_ble_ui_info(self):
        """Get BLE UI information (XIO soundbar only - may include update details).

        Returns:
            dict: Full response from kef:ble/ui endpoint

        Example:
            info = speaker.get_ble_ui_info()  # XIO only
            print(f"BLE UI info: {info}")
        """
        payload = {
            "path": "kef:ble/ui",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    def install_ble_firmware_now(self):
        """Install BLE firmware update immediately (XIO soundbar only - KW2 subwoofer module).

        Example:
            speaker.install_ble_firmware_now()  # XIO only - starts BLE update immediately
        """
        payload = {
            "path": "kef:ble/updateNow",
            "roles": "activate",
            "value": "{}",
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    def install_ble_firmware_later(self):
        """Schedule BLE firmware update for later (XIO soundbar only - KW2 subwoofer module).

        Example:
            speaker.install_ble_firmware_later()  # XIO only - schedules BLE update
        """
        payload = {
            "path": "kef:ble/updateLater",
            "roles": "activate",
            "value": "{}",
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()
            return json_output

    # ===== Device Information Methods =====

    def get_device_info(self):
        """Get complete device information (all models).

        Returns:
            dict: Device information with keys:
                - model_name (str): Model code (e.g., 'SP4041', 'SP4077', 'SP4083')
                - serial_number (str): Unique serial number
                - kef_id (str): KEF cloud UUID
                - hardware_version (str): Hardware version
                - mac_address (str): Primary MAC address

        Example:
            info = speaker.get_device_info()
            print(f"Model: {info['model_name']}")
            print(f"Serial: {info['serial_number']}")
            print(f"MAC: {info['mac_address']}")
        """
        return {
            'model_name': self.get_model_name(),
            'serial_number': self.get_serial_number(),
            'kef_id': self.get_kef_id(),
            'hardware_version': self.get_hardware_version(),
            'mac_address': self.get_mac_address()
        }

    def get_model_name(self):
        """Get speaker model name (all models).

        Returns:
            str: Model code - 'SP4041' (LSX II), 'SP4077' (LSX II LT), 'SP4083' (XIO), etc.

        Example:
            model = speaker.get_model_name()
            print(f"Model: {model}")
        """
        payload = {
            "path": "settings:/kef/host/modelName",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "Unknown")

    def get_serial_number(self):
        """Get speaker serial number (all models).

        Returns:
            str: Unique serial number (e.g., 'LSX2G26497Q20RCG')

        Example:
            serial = speaker.get_serial_number()
            print(f"Serial: {serial}")
        """
        payload = {
            "path": "settings:/kef/host/serialNumber",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "Unknown")

    def get_kef_id(self):
        """Get KEF cloud UUID (all models).

        Returns:
            str: KEF cloud identifier UUID

        Example:
            kef_id = speaker.get_kef_id()
            print(f"KEF ID: {kef_id}")
        """
        payload = {
            "path": "settings:/kef/host/kefId",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "Unknown")

    def get_hardware_version(self):
        """Get hardware version (all models).

        Returns:
            str: Hardware version string

        Example:
            hw_version = speaker.get_hardware_version()
            print(f"Hardware version: {hw_version}")
        """
        payload = {
            "path": "settings:/kef/host/hardwareVersion",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "Unknown")

    def get_mac_address(self):
        """Get primary MAC address (all models).

        Returns:
            str: MAC address in format 'XX:XX:XX:XX:XX:XX'

        Example:
            mac = speaker.get_mac_address()
            print(f"MAC address: {mac}")
        """
        payload = {
            "path": "settings:/system/primaryMacAddress",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "00:00:00:00:00:00")

    # ===== Privacy & Streaming Methods =====

    def get_analytics_enabled(self):
        """Get KEF analytics enabled state (all models).

        Returns:
            bool: True if analytics enabled, False if disabled

        Example:
            enabled = speaker.get_analytics_enabled()
            print(f"KEF analytics: {'Enabled' if enabled else 'Disabled'}")
        """
        payload = {
            "path": "settings:/kef/host/disableAnalytics",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # API uses "disable" so invert for user-friendly interface
            return not json_output[0].get("bool_", False)

    def set_analytics_enabled(self, enabled):
        """Enable or disable KEF analytics (all models).

        Args:
            enabled (bool): True to enable analytics, False to disable

        Example:
            speaker.set_analytics_enabled(False)  # Disable analytics
        """
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableAnalytics",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_app_analytics_enabled(self):
        """Get app analytics enabled state (all models).

        Returns:
            bool: True if app analytics enabled, False if disabled

        Example:
            enabled = speaker.get_app_analytics_enabled()
            print(f"App analytics: {'Enabled' if enabled else 'Disabled'}")
        """
        payload = {
            "path": "settings:/kef/host/disableAppAnalytics",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # API uses "disable" so invert for user-friendly interface
            return not json_output[0].get("bool_", False)

    def set_app_analytics_enabled(self, enabled):
        """Enable or disable app analytics (all models).

        Args:
            enabled (bool): True to enable app analytics, False to disable

        Example:
            speaker.set_app_analytics_enabled(False)  # Disable app analytics
        """
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableAppAnalytics",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_streaming_quality(self):
        """Get streaming quality bitrate (all models).

        Returns:
            str: Bitrate setting - 'unlimited', '320', '256', '192', or '128'

        Example:
            quality = speaker.get_streaming_quality()
            print(f"Streaming quality: {quality} kbps")
        """
        payload = {
            "path": "settings:/airable/bitrate",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "unlimited")

    def set_streaming_quality(self, bitrate):
        """Set streaming quality bitrate (all models).

        Args:
            bitrate (str): Quality setting - 'unlimited', '320', '256', '192', or '128'

        Example:
            speaker.set_streaming_quality('unlimited')  # Best quality
            speaker.set_streaming_quality('256')        # 256 kbps
        """
        valid_bitrates = ['unlimited', '320', '256', '192', '128']
        if bitrate not in valid_bitrates:
            raise ValueError(f"Invalid bitrate '{bitrate}'. Must be one of: {valid_bitrates}")

        payload = {
            "path": "settings:/airable/bitrate",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{bitrate}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_ui_language(self):
        """Get UI language setting (all models).

        Returns:
            str: Language code (e.g., 'en_GB', 'nl_NL', 'de_DE')

        Example:
            lang = speaker.get_ui_language()
            print(f"UI language: {lang}")
        """
        payload = {
            "path": "settings:/ui/language",
            "roles": "value",
        }

        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("string_", "en_GB")

    def set_ui_language(self, lang_code):
        """Set UI language (all models).

        Args:
            lang_code (str): Language code (e.g., 'en_GB', 'nl_NL', 'de_DE', 'fr_FR', 'es_ES')

        Example:
            speaker.set_ui_language('en_GB')  # English (UK)
            speaker.set_ui_language('nl_NL')  # Dutch
        """
        payload = {
            "path": "settings:/ui/language",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{lang_code}"}}',
        }

        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    # Google Cast Methods
    def get_cast_usage_report(self):
        """Get Google Cast usage report setting.

        Returns:
            dict: Cast usage report status

        Example:
            report = speaker.get_cast_usage_report()
        """
        payload = {
            "path": "googlecast:usageReport",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def set_cast_usage_report(self, enabled):
        """Set Google Cast usage report.

        Args:
            enabled (bool): True to enable usage reporting

        Example:
            speaker.set_cast_usage_report(False)
        """
        payload = {
            "path": "googlecast:setUsageReport",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def get_cast_tos_accepted(self):
        """Get Google Cast Terms of Service acceptance status.

        Returns:
            bool: True if ToS accepted

        Example:
            accepted = speaker.get_cast_tos_accepted()
        """
        payload = {
            "path": "settings:/googlecast/tosAccepted",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("bool_", False)

    # ================== Advanced Operations ==================

    def get_speaker_location(self):
        """
        Get the speaker's configured country/region location.
        Returns the ISO country code (e.g., 'GB', 'US', 'NL').
        """
        payload = {"path": "settings:/kef/host/speakerLocation", "roles": "value"}
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("i32_", 0)

    def set_speaker_location(self, country_code):
        """
        Set the speaker's country/region location.

        Args:
            country_code: Integer country code value
        """
        if not isinstance(country_code, int):
            raise ValueError("Country code must be an integer")

        payload = {
            "path": "settings:/kef/host/speakerLocation",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{country_code}}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def restore_dsp_defaults(self):
        """
        Restore DSP settings to factory defaults.
        This resets all sound processing settings (EQ, bass extension, etc.)
        but does not affect network settings or user configuration.
        """
        payload = {
            "path": "kef:restoreDspSettings/v2",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def factory_reset(self):
        """
        Perform a complete factory reset of the speaker.

        WARNING: This will erase ALL settings including:
        - Network configuration
        - User preferences
        - Streaming service accounts
        - Paired devices

        The speaker will return to factory default state and require setup again.
        Use with extreme caution!
        """
        payload = {
            "path": "kef:speakerFactoryReset",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    def get_dsp_info(self):
        """
        Get comprehensive DSP (Digital Signal Processing) information.
        Returns a complete dictionary of all DSP settings and state.
        """
        payload = {"path": "kef:dspInfo", "roles": "value"}
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0]

    def get_firmware_upgrade_progress(self):
        """
        Get the current firmware upgrade progress for all components.
        Returns a dictionary with upgrade status, or None if no upgrade in progress.

        Returns:
            dict: Upgrade status for firmware components, or None if not upgrading

        Example:
            progress = speaker.get_firmware_upgrade_progress()
            if progress:
                print(f"Upgrade progress: {progress}")
        """
        payload = {"path": "kef:host/upgradeProgress", "roles": "value"}
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                    return json_output[0]
            return None

    # ================== Network Management ==================

    def scan_wifi_networks(self):
        """
        Get the list of available WiFi networks.
        Returns a list of dictionaries containing network information:
        - ssid: Network name
        - security: Security type (WPA2, Open, etc.)
        - signalStrength: Signal strength indicator
        - frequency: 2.4GHz or 5GHz
        """
        payload = {"path": "networkwizard:wireless/scan_results", "roles": "value"}
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("networks", [])

    def activate_wifi_scan(self):
        """
        Trigger a new WiFi network scan.
        After calling this, wait a few seconds then call scan_wifi_networks()
        to get the updated list of available networks.
        """
        payload = {
            "path": "networkwizard:wireless/scan_activate",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = response.json()

    # Bluetooth Control Methods
    def get_bluetooth_state(self):
        """Get Bluetooth connection state.

        Returns:
            dict: Bluetooth state information

        Example:
            state = speaker.get_bluetooth_state()
        """
        payload = {
            "path": "bluetooth:state",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def disconnect_bluetooth(self):
        """Disconnect current Bluetooth device.

        Example:
            speaker.disconnect_bluetooth()
        """
        payload = {
            "path": "bluetooth:disconnect",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def set_bluetooth_discoverable(self, enabled):
        """Set Bluetooth discoverability.

        Args:
            enabled (bool): True to make speaker discoverable

        Example:
            speaker.set_bluetooth_discoverable(True)
        """
        payload = {
            "path": "bluetooth:externalDiscoverable",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def clear_bluetooth_devices(self):
        """Clear all paired Bluetooth devices.

        Example:
            speaker.clear_bluetooth_devices()
        """
        payload = {
            "path": "bluetooth:clearAllDevices",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    # Grouping/Multiroom Methods
    def get_group_members(self):
        """Get current multiroom group members.

        Returns:
            dict: Group member information

        Example:
            members = speaker.get_group_members()
        """
        payload = {
            "path": "grouping:members",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def save_persistent_group(self):
        """Save current group as persistent group.

        Example:
            speaker.save_persistent_group()
        """
        payload = {
            "path": "grouping:savePersistentGroup",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    # Notifications Methods
    def get_notification_queue(self):
        """Get notification display queue.

        Returns:
            dict: Notification queue information

        Example:
            queue = speaker.get_notification_queue()
        """
        payload = {
            "path": "notifications:/display/queue",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def cancel_notification(self):
        """Cancel current notification.

        Example:
            speaker.cancel_notification()
        """
        payload = {
            "path": "notifications:/display/cancel",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def get_player_notification(self):
        """Get player notification status.

        Returns:
            dict: Player notification information

        Example:
            notification = speaker.get_player_notification()
        """
        payload = {
            "path": "notifications:/player/playing",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    # Alerts & Timers Methods
    def list_alerts(self):
        """Get list of all alarms and timers.

        Returns:
            dict: List of alerts (alarms and timers)

        Example:
            alerts = speaker.list_alerts()
        """
        payload = {
            "path": "alerts:/list",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def add_timer(self, duration_seconds):
        """Add a timer.

        Args:
            duration_seconds (int): Timer duration in seconds

        Example:
            speaker.add_timer(300)  # 5 minute timer
        """
        payload = {
            "path": "alerts:/timer/add",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{duration_seconds}}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def remove_timer(self, timer_id):
        """Remove a timer.

        Args:
            timer_id (str): Timer ID to remove

        Example:
            speaker.remove_timer("timer_123")
        """
        payload = {
            "path": "alerts:/timer/remove",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{timer_id}"}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def add_alarm(self, alarm_data):
        """Add an alarm.

        Args:
            alarm_data (dict): Alarm configuration (time, days, etc.)

        Example:
            speaker.add_alarm({"time": "07:00", "days": ["mon", "tue", "wed"]})
        """
        payload = {
            "path": "alerts:/alarm/add",
            "roles": "value",
            "value": json.dumps(alarm_data),
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def remove_alarm(self, alarm_id):
        """Remove an alarm.

        Args:
            alarm_id (str): Alarm ID to remove

        Example:
            speaker.remove_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/remove",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def enable_alarm(self, alarm_id):
        """Enable an alarm.

        Args:
            alarm_id (str): Alarm ID to enable

        Example:
            speaker.enable_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/enable",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def disable_alarm(self, alarm_id):
        """Disable an alarm.

        Args:
            alarm_id (str): Alarm ID to disable

        Example:
            speaker.disable_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/disable",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def remove_all_alarms(self):
        """Remove all alarms.

        Example:
            speaker.remove_all_alarms()
        """
        payload = {
            "path": "alerts:/alarm/remove/all",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def stop_alert(self):
        """Stop currently playing alert (alarm or timer).

        Example:
            speaker.stop_alert()
        """
        payload = {
            "path": "alerts:/stop",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def snooze_alarm(self):
        """Snooze currently playing alarm.

        Example:
            speaker.snooze_alarm()
        """
        payload = {
            "path": "alerts:/alarm/snooze",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def get_snooze_time(self):
        """Get snooze duration setting.

        Returns:
            int: Snooze time in minutes

        Example:
            minutes = speaker.get_snooze_time()
        """
        payload = {
            "path": "settings:/alerts/snoozeTime",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = response.json()
            return json_output[0].get("i32_", 10)

    def set_snooze_time(self, minutes):
        """Set snooze duration.

        Args:
            minutes (int): Snooze duration in minutes

        Example:
            speaker.set_snooze_time(10)
        """
        payload = {
            "path": "settings:/alerts/snoozeTime",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{minutes}}}',
        }
        with requests.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            return response.json()

    def play_default_alert_sound(self):
        """Play default alert sound.

        Example:
            speaker.play_default_alert_sound()
        """
        payload = {
            "path": "alerts:/defaultSound/play",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

    def stop_default_alert_sound(self):
        """Stop default alert sound.

        Example:
            speaker.stop_default_alert_sound()
        """
        payload = {
            "path": "alerts:/defaultSound/stop",
            "roles": "value",
        }
        with requests.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            return response.json()

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
            db_value (float): Treble amount in dB (-3.0 to +3.0 in 0.25 dB steps)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid or not a multiple of 0.25
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-3.0 <= db_value <= 3.0):
            raise ValueError(f"db_value must be between -3.0 and +3.0, got {db_value}")
        # Validate 0.25 dB step size (KEF Connect app uses 0.25 increments)
        if round(db_value / 0.25) != db_value / 0.25:
            raise ValueError(f"db_value must be a multiple of 0.25 dB, got {db_value}")

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
            position (int): Balance position (-30=full left, 0=center, +30=full right)
                           KEF app shows this as 0-60 with 30 as center.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If position is invalid
        """
        if not isinstance(position, (int, float)):
            raise ValueError(f"position must be a number, got {type(position)}")
        position = int(position)
        if not (-30 <= position <= 30):
            raise ValueError(f"position must be between -30 and +30, got {position}")

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
            int: Subwoofer gain in dB (-10 to +10)
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferGain']

    def set_subwoofer_gain(self, db_value):
        """Set subwoofer gain (v2 API).

        Args:
            db_value (int): Subwoofer gain in dB (-10 to +10, integer steps only)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid or not an integer
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-10 <= db_value <= 10):
            raise ValueError(f"db_value must be between -10 and +10, got {db_value}")
        if db_value != int(db_value):
            raise ValueError(f"db_value must be an integer (no decimal places), got {db_value}")

        return self.update_dsp_setting('subwooferGain', int(db_value))

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

    # Wireless Subwoofer Adapter Methods (v2 API)
    def get_kw1_enabled(self):
        """Get KW1 wireless subwoofer adapter status (v2 API).

        The KW1 is KEF's wireless subwoofer adapter. When enabled, it allows
        connecting a subwoofer wirelessly instead of via cable.

        Note: XIO supports both KW1 and KW2 adapters simultaneously.
        Use get_subwoofer_count() to check if KW2 is also enabled (count=2).

        Returns:
            bool: True if KW1 adapter is enabled, False if disabled
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['isKW1']

    def set_kw1_enabled(self, enabled):
        """Enable or disable KW1 wireless subwoofer adapter (v2 API).

        Args:
            enabled (bool): True to enable KW1 adapter, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return self.update_dsp_setting('isKW1', enabled)

    def get_subwoofer_count(self):
        """Get number of subwoofers configured (v2 API).

        On XIO, this controls whether KW2 is enabled:
        - count=1: Single subwoofer (KW1 or wired)
        - count=2: Two subwoofers (KW1 + KW2)

        Returns:
            int: Number of configured subwoofers (1 or 2)
        """
        profile = self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferCount']

    def set_subwoofer_count(self, count):
        """Set number of subwoofers (v2 API).

        On XIO, setting count=2 enables the KW2 wireless adapter
        in addition to KW1 or wired connection.

        Args:
            count (int): Number of subwoofers (1 or 2)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If count is not 1 or 2
        """
        if count not in (1, 2):
            raise ValueError(f"count must be 1 or 2, got {count}")

        return self.update_dsp_setting('subwooferCount', count)

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

    # Async Volume Management Methods (Phase 3)
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
                    json_output = await response.json()
                    settings['max_volume'] = json_output[0]["i32_"]
        except:
            pass

        # Get volume step (uses i16_ not i32_)
        try:
            payload = {"path": "settings:/kef/host/volumeStep", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    json_output = await response.json()
                    settings['step'] = json_output[0]["i16_"]
        except:
            pass

        # Get volume limit (is bool, not int)
        try:
            payload = {"path": "settings:/kef/host/volumeLimit", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    json_output = await response.json()
                    settings['limit_enabled'] = json_output[0]["bool_"]
        except:
            pass

        # Get volume display (XIO only)
        try:
            payload = {"path": "settings:/kef/host/volumeDisplay", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
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
            json_output = await response.json()

    # Async Network Diagnostics Methods (Phase 4)
    async def ping_internet(self):
        """Ping internet to check connectivity.

        Returns:
            int: Ping time in milliseconds, or 0 if offline

        Example:
            ping_ms = await speaker.ping_internet()  # Returns 15 (ms)
        """
        payload = {
            "path": "kef:network/pingInternet",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0].get("i32_", 0)

    async def get_network_stability(self):
        """Get network stability status.

        Returns:
            str: Network stability ('idle', 'stable', or 'unstable')

        Example:
            stability = await speaker.get_network_stability()  # Returns 'stable'
        """
        payload = {
            "path": "kef:network/pingInternetStability",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0].get("string_", "idle")

    async def start_speed_test(self):
        """Start network speed test.

        Use get_speed_test_status() to monitor progress and
        get_speed_test_results() to retrieve results when complete.

        Example:
            await speaker.start_speed_test()
            # Wait and check status...
        """
        payload = {
            "path": "kef:speedTest/start",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

    async def get_speed_test_status(self):
        """Get speed test status.

        Returns:
            str: Test status ('idle', 'running', or 'complete')

        Example:
            status = await speaker.get_speed_test_status()  # Returns 'running'
        """
        payload = {
            "path": "kef:speedTest/status",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

        return json_output[0].get("string_", "idle")

    async def get_speed_test_results(self):
        """Get speed test results.

        Returns:
            dict: Speed test results with keys:
                - avg_download: Average download speed (Mbps)
                - current_download: Current download speed (Mbps)
                - packet_loss: Packet loss percentage

        Example:
            results = await speaker.get_speed_test_results()
            # Returns: {'avg_download': 45.2, 'current_download': 47.1, 'packet_loss': 0.5}
        """
        results = {}
        await self.resurect_session()

        # Get average download speed
        try:
            payload = {"path": "kef:speedTest/averageDownloadSpeed", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    json_output = await response.json()
                    results['avg_download'] = json_output[0].get("double_", 0.0)
        except:
            results['avg_download'] = 0.0

        # Get current download speed
        try:
            payload = {"path": "kef:speedTest/currentDownloadSpeed", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    json_output = await response.json()
                    results['current_download'] = json_output[0].get("double_", 0.0)
        except:
            results['current_download'] = 0.0

        # Get packet loss
        try:
            payload = {"path": "kef:speedTest/packetLoss", "roles": "value"}
            async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
                if response.status == 200:
                    json_output = await response.json()
                    results['packet_loss'] = json_output[0].get("double_", 0.0)
        except:
            results['packet_loss'] = 0.0

        return results

    async def stop_speed_test(self):
        """Stop running speed test.

        Example:
            await speaker.stop_speed_test()
        """
        payload = {
            "path": "kef:speedTest/stop",
            "roles": "value",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/getData", params=payload
        ) as response:
            json_output = await response.json()

    # Async System Behavior Methods (Phase 5)
    async def get_auto_switch_hdmi(self):
        """Get auto-switch to HDMI setting."""
        payload = {"path": "settings:/kef/host/autoSwitchToHDMI", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_standby_mode(self):
        """Get auto-standby mode setting."""
        payload = {"path": "settings:/kef/host/standbyMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_startup_tone(self):
        """Get startup tone setting."""
        payload = {"path": "settings:/kef/host/startupTone", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_wake_source(self):
        """Get wake-up source setting."""
        payload = {"path": "settings:/kef/host/wakeUpSource", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_usb_charging(self):
        """Get USB charging setting."""
        payload = {"path": "settings:/kef/host/usbCharging", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_cable_mode(self):
        """Get cable mode (wired/wireless inter-speaker connection)."""
        payload = {"path": "settings:/kef/host/cableMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_master_channel(self):
        """Get master channel (left/right speaker designation)."""
        payload = {"path": "settings:/kef/host/masterChannelMode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_speaker_status(self):
        """Get speaker power status."""
        payload = {"path": "settings:/kef/host/speakerStatus", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("kefSpeakerStatus", "standby")

    # Async LED Control Methods (Phase 6)
    async def get_front_led(self):
        """Get front panel LED setting.

        Note: This API setting exists but has no visible effect on any
        currently tested KEF speakers (LSX II, LSX II LT, XIO).
        """
        payload = {"path": "settings:/kef/host/disableFrontLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_standby_led(self):
        """Get standby LED setting."""
        payload = {"path": "settings:/kef/host/disableFrontStandbyLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_top_panel_enabled(self):
        """Get top panel (touch controls) enabled setting."""
        payload = {"path": "settings:/kef/host/disableTopPanel", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_top_panel_led(self):
        """Get top panel LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)
        """
        payload = {"path": "settings:/kef/host/topPanelLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    async def get_top_panel_standby_led(self):
        """Get top panel standby LED setting (XIO only).

        Returns:
            bool: True if enabled, False if disabled, None if not available (non-XIO speakers)
        """
        payload = {"path": "settings:/kef/host/topPanelStandbyLED", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
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
            json_output = await response.json()

    # ===== Remote Control Methods (Async) =====

    async def get_remote_ir_enabled(self):
        """Get IR remote control enabled state.

        Returns:
            bool: True if IR remote is enabled, False if disabled

        Example:
            enabled = await speaker.get_remote_ir_enabled()
            print(f"IR remote: {'Enabled' if enabled else 'Disabled'}")
        """
        payload = {"path": "settings:/kef/host/remote/remoteIR", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("bool_", True)

    async def set_remote_ir_enabled(self, enabled):
        """Enable or disable IR remote control.

        Args:
            enabled (bool): True to enable IR remote, False to disable

        Example:
            await speaker.set_remote_ir_enabled(True)   # Enable IR remote
            await speaker.set_remote_ir_enabled(False)  # Disable IR remote
        """
        payload = {
            "path": "settings:/kef/host/remote/remoteIR",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_ir_code_set(self):
        """Get IR code set (used to avoid conflicts with other devices).

        Returns:
            str: IR code set ('ir_code_set_a', 'ir_code_set_b', or 'ir_code_set_c')

        Example:
            code_set = await speaker.get_ir_code_set()
            print(f"IR code set: {code_set}")
        """
        payload = {"path": "settings:/kef/host/remote/remoteIRCode", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "ir_code_set_a")

    async def set_ir_code_set(self, code_set):
        """Set IR code set (used to avoid conflicts with other devices).

        Args:
            code_set (str): IR code set - 'ir_code_set_a', 'ir_code_set_b', or 'ir_code_set_c'

        Example:
            await speaker.set_ir_code_set('ir_code_set_a')  # Default
            await speaker.set_ir_code_set('ir_code_set_b')  # Use if conflicts with other remotes
            await speaker.set_ir_code_set('ir_code_set_c')  # Alternative code set
        """
        valid_codes = ['ir_code_set_a', 'ir_code_set_b', 'ir_code_set_c']
        if code_set not in valid_codes:
            raise ValueError(f"Invalid code set '{code_set}'. Must be one of: {valid_codes}")

        payload = {
            "path": "settings:/kef/host/remote/remoteIRCode",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{code_set}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_eq_button(self, button_num):
        """Get EQ button preset (XIO soundbar only).

        Args:
            button_num (int): Button number (1 or 2)

        Returns:
            str: Sound profile assigned to button ('dialogue', 'night', 'music', 'movie', etc.)

        Example:
            preset1 = await speaker.get_eq_button(1)  # XIO only
            preset2 = await speaker.get_eq_button(2)  # XIO only
            print(f"EQ Button 1: {preset1}, Button 2: {preset2}")
        """
        if button_num not in [1, 2]:
            raise ValueError("Button number must be 1 or 2")

        payload = {"path": f"settings:/kef/host/remote/eqButton{button_num}", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "default")

    async def set_eq_button(self, button_num, preset):
        """Set EQ button preset (XIO soundbar only).

        Args:
            button_num (int): Button number (1 or 2)
            preset (str): Sound profile to assign ('dialogue', 'night', 'music', 'movie', 'default', 'direct')

        Example:
            await speaker.set_eq_button(1, 'dialogue')  # XIO: Button 1 = dialogue mode
            await speaker.set_eq_button(2, 'night')     # XIO: Button 2 = night mode
        """
        if button_num not in [1, 2]:
            raise ValueError("Button number must be 1 or 2")

        valid_presets = ['dialogue', 'night', 'music', 'movie', 'default', 'direct']
        if preset not in valid_presets:
            raise ValueError(f"Invalid preset '{preset}'. Must be one of: {valid_presets}")

        payload = {
            "path": f"settings:/kef/host/remote/eqButton{button_num}",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{preset}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_favourite_button_action(self):
        """Get favourite button action.

        Returns:
            str: Action assigned to favourite button (e.g., 'nextSource')

        Example:
            action = await speaker.get_favourite_button_action()
            print(f"Favourite button action: {action}")
        """
        payload = {"path": "settings:/kef/host/remote/favouriteButton", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "nextSource")

    async def set_favourite_button_action(self, action):
        """Set favourite button action.

        Args:
            action (str): Action to assign (e.g., 'nextSource')

        Example:
            await speaker.set_favourite_button_action('nextSource')
        """
        payload = {
            "path": "settings:/kef/host/remote/favouriteButton",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{action}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

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
            json_output = await response.json()

    # ===== XIO Calibration Methods (Async) =====

    async def get_calibration_status(self):
        """Get room calibration status (XIO soundbar only).

        Returns:
            dict: Calibration status with keys, or None if not available (non-XIO speakers):
                - isCalibrated (bool): Whether calibration is complete
                - year (int): Calibration year
                - month (int): Calibration month
                - day (int): Calibration day
                - stability (int): Network stability during calibration

        Example:
            status = await speaker.get_calibration_status()  # XIO only
            if status and status['isCalibrated']:
                print(f"Calibrated on: {status['year']}-{status['month']:02d}-{status['day']:02d}")
        """
        payload = {"path": "settings:/kef/dsp/calibrationStatus", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()

        # Parse the calibration status structure
        # API returns nested structure: [{"type":"kefDspCalibrationStatus","kefDspCalibrationStatus":{...}}]
        if json_output and len(json_output) > 0:
            status_data = json_output[0].get('kefDspCalibrationStatus', {})
            if not status_data:
                return None
            return {
                'isCalibrated': status_data.get('isCalibrated', False),
                'year': status_data.get('year', 0),
                'month': status_data.get('month', 0),
                'day': status_data.get('day', 0),
                'stability': status_data.get('stability', 0)
            }
        return None

    async def get_calibration_result(self):
        """Get room calibration dB adjustment result (XIO soundbar only).

        Returns:
            float: dB adjustment applied by calibration (typically negative), or None if not available (non-XIO speakers)

        Example:
            result = await speaker.get_calibration_result()  # XIO only
            if result is not None:
                print(f"Calibration adjustment: {result} dB")
        """
        payload = {"path": "settings:/kef/dsp/calibrationResult", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                # API returns double_ type, not i32_
                return json_output[0].get("double_", None)
        return None

    async def get_calibration_step(self):
        """Get current calibration step (XIO soundbar only).

        Returns:
            str: Current calibration step, or None if not available (non-XIO speakers):
                - 'step_1_start': Calibration starting
                - 'step_2_processing': Calibration in progress
                - 'step_3_complete': Calibration complete

        Example:
            step = await speaker.get_calibration_step()  # XIO only
            if step:
                print(f"Calibration step: {step}")
        """
        payload = {"path": "settings:/kef/dsp/calibrationStep", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0].get("string_", "step_1_start")
        return None

    async def start_calibration(self):
        """Start room calibration (XIO soundbar only).

        Triggers the room calibration process. The speaker will play test tones
        and analyze the room acoustics. Monitor calibration_step to track progress.

        Example:
            await speaker.start_calibration()  # XIO only
            # Check await speaker.get_calibration_step() to monitor progress
        """
        payload = {
            "path": "kefdsp:/calibration/start",
            "roles": "activate",
            "value": "{}",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()
            return json_output

    async def stop_calibration(self):
        """Stop room calibration in progress (XIO soundbar only).

        Cancels a running calibration process.

        Example:
            await speaker.stop_calibration()  # XIO only
        """
        payload = {
            "path": "kefdsp:/calibration/stop",
            "roles": "activate",
            "value": "{}",
        }

        await self.resurect_session()
        async with self._session.get(
            "http://" + self.host + "/api/setData", params=payload
        ) as response:
            json_output = await response.json()
            return json_output

    # ===== BLE Firmware Methods (Async - XIO KW2 Subwoofer Module) =====

    async def check_ble_firmware_update(self):
        """Trigger BLE firmware update check (XIO soundbar only - KW2 subwoofer module).

        This triggers the speaker to check KEF's servers for KW2 module updates.
        After calling this, poll get_ble_firmware_status() which will return
        "updateAvailable" if an update exists.

        Example:
            await speaker.check_ble_firmware_update()  # XIO only - triggers check
            await asyncio.sleep(5)  # Wait for check to complete
            status = await speaker.get_ble_firmware_status()
            if status == "updateAvailable":
                print("Update available!")
        """
        payload = {
            "path": "kef:ble/checkForUpdates",
            "roles": "activate",
            "value": "{}",
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()
        return json_output

    async def get_ble_firmware_status(self):
        """Get BLE firmware update status (XIO soundbar only - KW2 subwoofer module).

        Returns:
            str: Update status - 'startUp', 'downloading', 'installing', 'complete'
                Returns None if not available (non-XIO speakers)

        Example:
            status = await speaker.get_ble_firmware_status()  # XIO only
            if status:
                print(f"BLE firmware status: {status}")
        """
        payload = {"path": "kef:ble/updateStatus", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0].get("string_", "startUp")
        return None

    async def get_ble_firmware_version(self):
        """Get BLE firmware version from update server (XIO soundbar only - KW2 subwoofer module).

        Note: This returns the version available on KEF's update server, NOT the installed version.
        The KEF API does not expose the actual installed version on the KW2 module.

        Returns:
            str: BLE firmware version from server (e.g., "1.2.3", "Empty" if not set, or None if not available)

        Example:
            version = await speaker.get_ble_firmware_version()  # XIO only
            if version:
                print(f"BLE server version: {version}")
        """
        payload = {"path": "kef:ble/updateServer/txVersion", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0].get("string_", "Empty")
        return None

    async def get_ble_ui_info(self):
        """Get BLE UI information (XIO soundbar only - may include update details).

        Returns:
            dict: Full response from kef:ble/ui endpoint

        Example:
            info = await speaker.get_ble_ui_info()  # XIO only
            print(f"BLE UI info: {info}")
        """
        payload = {"path": "kef:ble/ui", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            return json_output

    async def install_ble_firmware_now(self):
        """Install BLE firmware update immediately (XIO soundbar only - KW2 subwoofer module).

        Example:
            await speaker.install_ble_firmware_now()  # XIO only - starts BLE update immediately
        """
        payload = {
            "path": "kef:ble/updateNow",
            "roles": "activate",
            "value": "{}",
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()
            return json_output

    async def install_ble_firmware_later(self):
        """Schedule BLE firmware update for later (XIO soundbar only - KW2 subwoofer module).

        Example:
            await speaker.install_ble_firmware_later()  # XIO only - schedules BLE update
        """
        payload = {
            "path": "kef:ble/updateLater",
            "roles": "activate",
            "value": "{}",
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()
            return json_output

    # ===== Device Information Methods (Async) =====

    async def get_device_info(self):
        """Get complete device information (all models).

        Returns:
            dict: Device information with keys:
                - model_name (str): Model code (e.g., 'SP4041', 'SP4077', 'SP4083')
                - serial_number (str): Unique serial number
                - kef_id (str): KEF cloud UUID
                - hardware_version (str): Hardware version
                - mac_address (str): Primary MAC address

        Example:
            info = await speaker.get_device_info()
            print(f"Model: {info['model_name']}")
            print(f"Serial: {info['serial_number']}")
            print(f"MAC: {info['mac_address']}")
        """
        return {
            'model_name': await self.get_model_name(),
            'serial_number': await self.get_serial_number(),
            'kef_id': await self.get_kef_id(),
            'hardware_version': await self.get_hardware_version(),
            'mac_address': await self.get_mac_address()
        }

    async def get_model_name(self):
        """Get speaker model name (all models).

        Returns:
            str: Model code - 'SP4041' (LSX II), 'SP4077' (LSX II LT), 'SP4083' (XIO), etc.

        Example:
            model = await speaker.get_model_name()
            print(f"Model: {model}")
        """
        payload = {"path": "settings:/kef/host/modelName", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "Unknown")

    async def get_serial_number(self):
        """Get speaker serial number (all models).

        Returns:
            str: Unique serial number (e.g., 'LSX2G26497Q20RCG')

        Example:
            serial = await speaker.get_serial_number()
            print(f"Serial: {serial}")
        """
        payload = {"path": "settings:/kef/host/serialNumber", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "Unknown")

    async def get_kef_id(self):
        """Get KEF cloud UUID (all models).

        Returns:
            str: KEF cloud identifier UUID

        Example:
            kef_id = await speaker.get_kef_id()
            print(f"KEF ID: {kef_id}")
        """
        payload = {"path": "settings:/kef/host/kefId", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "Unknown")

    async def get_hardware_version(self):
        """Get hardware version (all models).

        Returns:
            str: Hardware version string

        Example:
            hw_version = await speaker.get_hardware_version()
            print(f"Hardware version: {hw_version}")
        """
        payload = {"path": "settings:/kef/host/hardwareVersion", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "Unknown")

    async def get_mac_address(self):
        """Get primary MAC address (all models).

        Returns:
            str: MAC address in format 'XX:XX:XX:XX:XX:XX'

        Example:
            mac = await speaker.get_mac_address()
            print(f"MAC address: {mac}")
        """
        payload = {"path": "settings:/system/primaryMacAddress", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "00:00:00:00:00:00")

    # ===== Privacy & Streaming Methods (Async) =====

    async def get_analytics_enabled(self):
        """Get KEF analytics enabled state (all models)."""
        payload = {"path": "settings:/kef/host/disableAnalytics", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return not json_output[0].get("bool_", False)

    async def set_analytics_enabled(self, enabled):
        """Enable or disable KEF analytics (all models)."""
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableAnalytics",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_app_analytics_enabled(self):
        """Get app analytics enabled state (all models)."""
        payload = {"path": "settings:/kef/host/disableAppAnalytics", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return not json_output[0].get("bool_", False)

    async def set_app_analytics_enabled(self, enabled):
        """Enable or disable app analytics (all models)."""
        disabled = not enabled
        payload = {
            "path": "settings:/kef/host/disableAppAnalytics",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(disabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_streaming_quality(self):
        """Get streaming quality bitrate (all models)."""
        payload = {"path": "settings:/airable/bitrate", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "unlimited")

    async def set_streaming_quality(self, bitrate):
        """Set streaming quality bitrate (all models)."""
        valid_bitrates = ['unlimited', '320', '256', '192', '128']
        if bitrate not in valid_bitrates:
            raise ValueError(f"Invalid bitrate '{bitrate}'. Must be one of: {valid_bitrates}")

        payload = {
            "path": "settings:/airable/bitrate",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{bitrate}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_ui_language(self):
        """Get UI language setting (all models)."""
        payload = {"path": "settings:/ui/language", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("string_", "en_GB")

    async def set_ui_language(self, lang_code):
        """Set UI language (all models)."""
        payload = {
            "path": "settings:/ui/language",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{lang_code}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    # ===== Advanced Operations (Async) =====

    async def get_speaker_location(self):
        """Get the speaker's configured country/region location (all models).

        Returns:
            int: Country code value

        Example:
            location = await speaker.get_speaker_location()
            print(f"Speaker location: {location}")
        """
        payload = {"path": "settings:/kef/host/speakerLocation", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("i32_", 0)

    async def set_speaker_location(self, country_code):
        """Set the speaker's country/region location (all models).

        Args:
            country_code: Integer country code value

        Example:
            await speaker.set_speaker_location(44)  # Set to UK
        """
        if not isinstance(country_code, int):
            raise ValueError("Country code must be an integer")

        payload = {
            "path": "settings:/kef/host/speakerLocation",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{country_code}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def restore_dsp_defaults(self):
        """Restore DSP settings to factory defaults (all models).

        This resets all sound processing settings (EQ, bass extension, etc.)
        but does not affect network settings or user configuration.

        Example:
            await speaker.restore_dsp_defaults()
            print("DSP settings restored to defaults")
        """
        payload = {
            "path": "kef:restoreDspSettings/v2",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def factory_reset(self):
        """Perform a complete factory reset of the speaker (all models).

        WARNING: This will erase ALL settings including:
        - Network configuration
        - User preferences
        - Streaming service accounts
        - Paired devices

        The speaker will return to factory default state and require setup again.
        Use with extreme caution!

        Example:
            # Only use if you're absolutely sure!
            await speaker.factory_reset()
        """
        payload = {
            "path": "kef:speakerFactoryReset",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    async def get_dsp_info(self):
        """Get comprehensive DSP (Digital Signal Processing) information (all models).

        Returns a complete dictionary of all DSP settings and state.

        Returns:
            dict: Complete DSP configuration and state

        Example:
            dsp_info = await speaker.get_dsp_info()
            print(f"DSP configuration: {dsp_info}")
        """
        payload = {"path": "kef:dspInfo", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0]

    async def get_firmware_upgrade_progress(self):
        """Get the current firmware upgrade progress for all components (all models).

        Returns a dictionary with upgrade status for:
        - Main firmware
        - DSP firmware
        - BLE firmware (if applicable)

        Each component shows percentage complete and current state.

        Returns:
            dict: Firmware upgrade progress for all components

        Example:
            progress = await speaker.get_firmware_upgrade_progress()
            print(f"Firmware upgrade: {progress}")
        """
        payload = {"path": "kef:host/upgradeProgress", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            # Check if response is an error (dict with 'error' key) or empty
            if isinstance(json_output, dict) and 'error' in json_output:
                return None
            if json_output and len(json_output) > 0:
                return json_output[0]
        return None

    # ===== Network Management (Async) =====

    async def scan_wifi_networks(self):
        """Get the list of available WiFi networks (all models).

        Returns a list of dictionaries containing network information:
        - ssid: Network name
        - security: Security type (WPA2, Open, etc.)
        - signalStrength: Signal strength indicator
        - frequency: 2.4GHz or 5GHz

        Returns:
            list: List of available WiFi networks

        Example:
            networks = await speaker.scan_wifi_networks()
            for network in networks:
                print(f"{network['ssid']}: {network['signalStrength']}")
        """
        payload = {"path": "networkwizard:wireless/scan_results", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
        return json_output[0].get("networks", [])

    async def activate_wifi_scan(self):
        """Trigger a new WiFi network scan (all models).

        After calling this, wait a few seconds then call scan_wifi_networks()
        to get the updated list of available networks.

        Example:
            await speaker.activate_wifi_scan()
            await asyncio.sleep(3)
            networks = await speaker.scan_wifi_networks()
        """
        payload = {
            "path": "networkwizard:wireless/scan_activate",
            "roles": "value",
            "value": '{"type":"bool_","bool_":true}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            json_output = await response.json()

    # Bluetooth Control Methods (Async)
    async def get_bluetooth_state(self):
        """Get Bluetooth connection state.

        Returns:
            dict: Bluetooth state information

        Example:
            state = await speaker.get_bluetooth_state()
        """
        payload = {"path": "bluetooth:state", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def disconnect_bluetooth(self):
        """Disconnect current Bluetooth device.

        Example:
            await speaker.disconnect_bluetooth()
        """
        payload = {"path": "bluetooth:disconnect", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def set_bluetooth_discoverable(self, enabled):
        """Set Bluetooth discoverability.

        Args:
            enabled (bool): True to make speaker discoverable

        Example:
            await speaker.set_bluetooth_discoverable(True)
        """
        payload = {
            "path": "bluetooth:externalDiscoverable",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def clear_bluetooth_devices(self):
        """Clear all paired Bluetooth devices.

        Example:
            await speaker.clear_bluetooth_devices()
        """
        payload = {"path": "bluetooth:clearAllDevices", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    # Grouping/Multiroom Methods (Async)
    async def get_group_members(self):
        """Get current multiroom group members.

        Returns:
            dict: Group member information

        Example:
            members = await speaker.get_group_members()
        """
        payload = {"path": "grouping:members", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def save_persistent_group(self):
        """Save current group as persistent group.

        Example:
            await speaker.save_persistent_group()
        """
        payload = {"path": "grouping:savePersistentGroup", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    # Notifications Methods (Async)
    async def get_notification_queue(self):
        """Get notification display queue.

        Returns:
            dict: Notification queue information

        Example:
            queue = await speaker.get_notification_queue()
        """
        payload = {"path": "notifications:/display/queue", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def cancel_notification(self):
        """Cancel current notification.

        Example:
            await speaker.cancel_notification()
        """
        payload = {"path": "notifications:/display/cancel", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def get_player_notification(self):
        """Get player notification status.

        Returns:
            dict: Player notification information

        Example:
            notification = await speaker.get_player_notification()
        """
        payload = {"path": "notifications:/player/playing", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    # Alerts & Timers Methods (Async)
    async def list_alerts(self):
        """Get list of all alarms and timers.

        Returns:
            dict: List of alerts (alarms and timers)

        Example:
            alerts = await speaker.list_alerts()
        """
        payload = {"path": "alerts:/list", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def add_timer(self, duration_seconds):
        """Add a timer.

        Args:
            duration_seconds (int): Timer duration in seconds

        Example:
            await speaker.add_timer(300)  # 5 minute timer
        """
        payload = {
            "path": "alerts:/timer/add",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{duration_seconds}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def remove_timer(self, timer_id):
        """Remove a timer.

        Args:
            timer_id (str): Timer ID to remove

        Example:
            await speaker.remove_timer("timer_123")
        """
        payload = {
            "path": "alerts:/timer/remove",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{timer_id}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def add_alarm(self, alarm_data):
        """Add an alarm.

        Args:
            alarm_data (dict): Alarm configuration (time, days, etc.)

        Example:
            await speaker.add_alarm({"time": "07:00", "days": ["mon", "tue", "wed"]})
        """
        payload = {
            "path": "alerts:/alarm/add",
            "roles": "value",
            "value": json.dumps(alarm_data),
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def remove_alarm(self, alarm_id):
        """Remove an alarm.

        Args:
            alarm_id (str): Alarm ID to remove

        Example:
            await speaker.remove_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/remove",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def enable_alarm(self, alarm_id):
        """Enable an alarm.

        Args:
            alarm_id (str): Alarm ID to enable

        Example:
            await speaker.enable_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/enable",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def disable_alarm(self, alarm_id):
        """Disable an alarm.

        Args:
            alarm_id (str): Alarm ID to disable

        Example:
            await speaker.disable_alarm("alarm_123")
        """
        payload = {
            "path": "alerts:/alarm/disable",
            "roles": "value",
            "value": f'{{"type":"string_","string_":"{alarm_id}"}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def remove_all_alarms(self):
        """Remove all alarms.

        Example:
            await speaker.remove_all_alarms()
        """
        payload = {"path": "alerts:/alarm/remove/all", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def stop_alert(self):
        """Stop currently playing alert (alarm or timer).

        Example:
            await speaker.stop_alert()
        """
        payload = {"path": "alerts:/stop", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def snooze_alarm(self):
        """Snooze currently playing alarm.

        Example:
            await speaker.snooze_alarm()
        """
        payload = {"path": "alerts:/alarm/snooze", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def get_snooze_time(self):
        """Get snooze duration setting.

        Returns:
            int: Snooze time in minutes

        Example:
            minutes = await speaker.get_snooze_time()
        """
        payload = {"path": "settings:/alerts/snoozeTime", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            return json_output[0].get("i32_", 10)

    async def set_snooze_time(self, minutes):
        """Set snooze duration.

        Args:
            minutes (int): Snooze duration in minutes

        Example:
            await speaker.set_snooze_time(10)
        """
        payload = {
            "path": "settings:/alerts/snoozeTime",
            "roles": "value",
            "value": f'{{"type":"i32_","i32_":{minutes}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def play_default_alert_sound(self):
        """Play default alert sound.

        Example:
            await speaker.play_default_alert_sound()
        """
        payload = {"path": "alerts:/defaultSound/play", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def stop_default_alert_sound(self):
        """Stop default alert sound.

        Example:
            await speaker.stop_default_alert_sound()
        """
        payload = {"path": "alerts:/defaultSound/stop", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    # Google Cast Methods (Async)
    async def get_cast_usage_report(self):
        """Get Google Cast usage report setting.

        Returns:
            dict: Cast usage report status

        Example:
            report = await speaker.get_cast_usage_report()
        """
        payload = {"path": "googlecast:usageReport", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            return await response.json()

    async def set_cast_usage_report(self, enabled):
        """Set Google Cast usage report.

        Args:
            enabled (bool): True to enable usage reporting

        Example:
            await speaker.set_cast_usage_report(False)
        """
        payload = {
            "path": "googlecast:setUsageReport",
            "roles": "value",
            "value": f'{{"type":"bool_","bool_":{str(enabled).lower()}}}',
        }
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/setData", params=payload) as response:
            return await response.json()

    async def get_cast_tos_accepted(self):
        """Get Google Cast Terms of Service acceptance status.

        Returns:
            bool: True if ToS accepted

        Example:
            accepted = await speaker.get_cast_tos_accepted()
        """
        payload = {"path": "settings:/googlecast/tosAccepted", "roles": "value"}
        await self.resurect_session()
        async with self._session.get("http://" + self.host + "/api/getData", params=payload) as response:
            json_output = await response.json()
            return json_output[0].get("bool_", False)

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
            db_value (float): Treble amount in dB (-3.0 to +3.0 in 0.25 dB steps)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid or not a multiple of 0.25
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-3.0 <= db_value <= 3.0):
            raise ValueError(f"db_value must be between -3.0 and +3.0, got {db_value}")
        # Validate 0.25 dB step size (KEF Connect app uses 0.25 increments)
        if round(db_value / 0.25) != db_value / 0.25:
            raise ValueError(f"db_value must be a multiple of 0.25 dB, got {db_value}")

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
            position (int): Balance position (-30=full left, 0=center, +30=full right)
                           KEF app shows this as 0-60 with 30 as center.

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If position is invalid
        """
        if not isinstance(position, (int, float)):
            raise ValueError(f"position must be a number, got {type(position)}")
        position = int(position)
        if not (-30 <= position <= 30):
            raise ValueError(f"position must be between -30 and +30, got {position}")

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
            int: Subwoofer gain in dB (-10 to +10)
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferGain']

    async def set_subwoofer_gain(self, db_value):
        """Set subwoofer gain (v2 API).

        Args:
            db_value (int): Subwoofer gain in dB (-10 to +10, integer steps only)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If db_value is invalid or not an integer
        """
        if not isinstance(db_value, (int, float)):
            raise ValueError(f"db_value must be a number, got {type(db_value)}")
        if not (-10 <= db_value <= 10):
            raise ValueError(f"db_value must be between -10 and +10, got {db_value}")
        if db_value != int(db_value):
            raise ValueError(f"db_value must be an integer (no decimal places), got {db_value}")

        return await self.update_dsp_setting('subwooferGain', int(db_value))

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

    # Wireless Subwoofer Adapter Methods (v2 API)
    async def get_kw1_enabled(self):
        """Get KW1 wireless subwoofer adapter status (v2 API).

        The KW1 is KEF's wireless subwoofer adapter. When enabled, it allows
        connecting a subwoofer wirelessly instead of via cable.

        Note: XIO supports both KW1 and KW2 adapters simultaneously.
        Use get_subwoofer_count() to check if KW2 is also enabled (count=2).

        Returns:
            bool: True if KW1 adapter is enabled, False if disabled
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['isKW1']

    async def set_kw1_enabled(self, enabled):
        """Enable or disable KW1 wireless subwoofer adapter (v2 API).

        Args:
            enabled (bool): True to enable KW1 adapter, False to disable

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If enabled is not a boolean
        """
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {type(enabled)}")

        return await self.update_dsp_setting('isKW1', enabled)

    async def get_subwoofer_count(self):
        """Get number of subwoofers configured (v2 API).

        On XIO, this controls whether KW2 is enabled:
        - count=1: Single subwoofer (KW1 or wired)
        - count=2: Two subwoofers (KW1 + KW2)

        Returns:
            int: Number of configured subwoofers (1 or 2)
        """
        profile = await self.get_eq_profile()
        return profile['kefEqProfileV2']['subwooferCount']

    async def set_subwoofer_count(self, count):
        """Set number of subwoofers (v2 API).

        On XIO, setting count=2 enables the KW2 wireless adapter
        in addition to KW1 or wired connection.

        Args:
            count (int): Number of subwoofers (1 or 2)

        Returns:
            dict: JSON response from speaker

        Raises:
            ValueError: If count is not 1 or 2
        """
        if count not in (1, 2):
            raise ValueError(f"count must be 1 or 2, got {count}")

        return await self.update_dsp_setting('subwooferCount', count)

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
            # Use setData with activate role to trigger check
            result = await self.set_request(
                "firmwareupdate:checkForUpdate",
                roles="activate",
                value='{"type":"bool_","bool_":true}'
            )
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
            # Use setData with activate role and boolean value - try firmwareupdate:install first
            result = await self.set_request(
                "firmwareupdate:install",
                roles="activate",
                value='{"type":"bool_","bool_":true}'
            )
            return result[0] if result else None
        except Exception:
            # Fallback to firmwareupdate:update endpoint
            try:
                result = await self.set_request(
                    "firmwareupdate:update",
                    roles="activate",
                    value='{"type":"bool_","bool_":true}'
                )
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
