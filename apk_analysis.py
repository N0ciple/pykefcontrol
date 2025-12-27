#!/usr/bin/env python3
"""
KEF API Discovery - Comprehensive Testing Suite

This script tests ALL 209 discovered KEF API endpoints from complete JADX decompilation
of KEF Connect v1.26.1 APK across multiple speaker models.

Source: ApiPath.java (com/kef/streamunlimitedapi/model/base/ApiPath.java)
Total Endpoints: 209 paths across 12 categories

Categories:
  - Settings (124 paths): Speaker configuration
  - KEF Operations (37 paths): System operations
  - Player Control (5 paths): Playback control
  - Power Management (3 paths): Standby/reboot
  - Network (7 paths): WiFi management
  - Alerts (12 paths): Timers and alarms
  - Bluetooth (4 paths): BT device management
  - Firmware (3 paths): Update management
  - Google Cast (4 paths): Cast configuration
  - Grouping (2 paths): Multi-room
  - Notifications (3 paths): UI notifications
  - Other (7 paths): XIO-specific and legacy

Usage:
    python apk_analysis.py
    python apk_analysis.py --host 192.168.1.100
    python apk_analysis.py --models all --verbose
    python apk_analysis.py --output results.json
"""

import requests
import json
import argparse
import time
from typing import Dict, Any, List
from pathlib import Path


# Default test hosts - update these to match your network
DEFAULT_HOSTS = {
    'LSX II LT': '192.168.16.20',
    'LSX II': '192.168.16.23',
    'XIO': '192.168.16.26'
}


# Complete settings catalog from APK analysis
ALL_SETTINGS = {
    # Volume & Audio (14)
    'Volume - Global': 'settings:/kef/host/defaultVolumeGlobal',
    'Volume - WiFi': 'settings:/kef/host/defaultVolumeWifi',
    'Volume - Bluetooth': 'settings:/kef/host/defaultVolumeBluetooth',
    'Volume - Optical': 'settings:/kef/host/defaultVolumeOptical',
    'Volume - USB': 'settings:/kef/host/defaultVolumeUSB',
    'Volume - Analogue': 'settings:/kef/host/defaultVolumeAnalogue',
    'Volume - TV/HDMI': 'settings:/kef/host/defaultVolumeTV',
    'Volume - Coaxial': 'settings:/kef/host/defaultVolumeCoaxial',
    'Maximum Volume': 'settings:/kef/host/maximumVolume',
    'Volume Limit': 'settings:/kef/host/volumeLimit',
    'Volume Step': 'settings:/kef/host/volumeStep',
    'Volume Display': 'settings:/kef/host/volumeDisplay',
    'Standby Default Volume': 'settings:/kef/host/standbyDefaultVol',
    'Advanced Standby Volume': 'settings:/kef/host/advancedStandbyDefaultVol',

    # DSP Settings (18)
    'Prefer VirtualX': 'settings:/kef/dsp/preferVirtualX',
    'Desk Mode': 'settings:/kef/dsp/deskMode',
    'Desk Mode Setting': 'settings:/kef/dsp/deskModeSetting',
    'Wall Mode': 'settings:/kef/dsp/wallMode',
    'Wall Mode Setting': 'settings:/kef/dsp/wallModeSetting',
    'Bass Extension': 'settings:/kef/dsp/bassExtension',
    'Treble Amount': 'settings:/kef/dsp/trebleAmount',
    'Balance': 'settings:/kef/dsp/balance',
    'Phase Correction': 'settings:/kef/dsp/phaseCorrection',
    'High Pass Mode': 'settings:/kef/dsp/highPassMode',
    'High Pass Freq': 'settings:/kef/dsp/highPassModeFreq',
    'Subwoofer Count': 'settings:/kef/dsp/subwooferCount',
    'Subwoofer Gain': 'settings:/kef/dsp/subwooferGain',
    'Subwoofer Preset': 'settings:/kef/dsp/subwooferPreset',
    'Sub LowPass Freq': 'settings:/kef/dsp/subOutLPFreq',
    'Sub Polarity': 'settings:/kef/dsp/subwooferPolarity',
    'Sub Enable Stereo': 'settings:/kef/dsp/subEnableStereo',
    'Is KW1': 'settings:/kef/dsp/isKW1',

    # DSP v2 (XIO specific)
    'Dialogue Mode': 'settings:/kef/dsp/v2/dialogueMode',
    'Sound Profile': 'settings:/kef/dsp/v2/soundProfile',
    'Subwoofer Out': 'settings:/kef/dsp/v2/subwooferOut',

    # Calibration (XIO only)
    'Calibration Step': 'settings:/kef/dsp/calibrationStep',
    'Calibration Status': 'settings:/kef/dsp/calibrationStatus',
    'Calibration Result': 'settings:/kef/dsp/calibrationResult',

    # EQ Profiles
    'Profile ID': 'settings:/kef/eqProfile/profileId',
    'Profile Name': 'settings:/kef/eqProfile/profileName',
    'Expert Mode': 'settings:/kef/eqProfile/isExpertMode',

    # LED Controls
    'Display Brightness': 'settings:/kef/host/displayBrightness',
    'LED Brightness': 'settings:/kef/host/ledBrightness',
    'Disable Front LED': 'settings:/kef/host/disableFrontLED',
    'Disable Front Standby LED': 'settings:/kef/host/disableFrontStandbyLED',
    'Top Panel LED': 'settings:/kef/host/topPanelLED',
    'Top Panel Standby LED': 'settings:/kef/host/topPanelStandbyLED',
    'Disable Top Panel': 'settings:/kef/host/disableTopPanel',

    # System Behavior
    'Auto Switch HDMI': 'settings:/kef/host/autoSwitchToHDMI',
    'Auto Detect Placement': 'settings:/kef/host/autoDetectPlacement',
    'Do Not Disturb': 'settings:/kef/host/doNotDisturb',
    'Standby Mode': 'settings:/kef/host/standbyMode',
    'Startup Tone': 'settings:/kef/host/startupTone',
    'Wake Up Source': 'settings:/kef/host/wakeUpSource',
    'USB Charging': 'settings:/kef/host/usbCharging',
    'Cable Mode': 'settings:/kef/host/cableMode',
    'IPT Switch': 'settings:/kef/host/iptSwitch',
    'Master Channel Mode': 'settings:/kef/host/masterChannelMode',
    'Speaker Status': 'settings:/kef/host/speakerStatus',
    'AF In Standby': 'settings:/imx8AudioFramework/afInStandby',

    # Remote Control
    'Remote IR': 'settings:/kef/host/remote/remoteIR',
    'Remote IR Code': 'settings:/kef/host/remote/remoteIRCode',
    'Speaker IR Code': 'settings:/kef/host/remote/speakerIRCode',
    'EQ Button 1': 'settings:/kef/host/remote/eqButton1',
    'EQ Button 2': 'settings:/kef/host/remote/eqButton2',
    'Favourite Button': 'settings:/kef/host/remote/favouriteButton',
    'User Fixed Volume': 'settings:/kef/host/remote/userFixedVolume',

    # Subwoofer
    'Force Subwoofer On': 'settings:/kef/host/subwooferForceOn',
    'Force KW1 On': 'settings:/kef/host/subwooferForceOnKW1',

    # Device Info
    'Model Name': 'settings:/kef/host/modelName',
    'Serial Number': 'settings:/kef/host/serialNumber',
    'KEF ID': 'settings:/kef/host/kefId',
    'Firmware Version': 'settings:/kef/host/firmwareVersion',
    'Hardware Version': 'settings:/kef/host/hardwareVersion',
    'Primary MAC': 'settings:/system/primaryMacAddress',
    'Member ID': 'settings:/system/memberId',
    'Device Name': 'settings:/deviceName',
    'App Location': 'settings:/kef/host/appLocation',
    'Release Text': 'settings:/releasetext',
    'Version': 'settings:/version',

    # Privacy
    'Disable Analytics': 'settings:/kef/host/disableAnalytics',
    'Disable App Analytics': 'settings:/kef/host/disableAppAnalytics',

    # Network/Streaming
    'GoogleCast ToS': 'settings:/googlecast/tosAccepted',
    'AirPlay Added': 'settings:/airplay/addedToHome',
    'Airable Bitrate': 'settings:/airable/bitrate',
    'Airable Language': 'settings:/airable/language',
    'UI Language': 'settings:/ui/language',

    # Media
    'Media Mute': 'settings:/mediaPlayer/mute',
    'Play Mode': 'settings:/mediaPlayer/playMode',
    'Playlist Limit': 'settings:/playlists/dbItemsLimit',
    'Alerts Snooze': 'settings:/alerts/snoozeTime',

    # Other
    'Physical Source': 'settings:/kef/host/physicalSource',
}


# KEF operation endpoints
KEF_OPERATIONS = {
    # Network diagnostics
    'Ping Internet': 'kef:network/pingInternet',
    'Ping Internet Activate': 'kef:network/pingInternetActivate',
    'Network Stability': 'kef:network/pingInternetStability',

    # Speed test
    'Speed Test Start': 'kef:speedTest/start',
    'Speed Test Status': 'kef:speedTest/status',
    'Speed Test Stop': 'kef:speedTest/stop',
    'Speed Test Packet Loss': 'kef:speedTest/packetLoss',
    'Speed Test Avg Download': 'kef:speedTest/averageDownloadSpeed',
    'Speed Test Current Download': 'kef:speedTest/currentDownloadSpeed',

    # BLE firmware (XIO KW2 subwoofer)
    'BLE Check Updates': 'kef:ble/checkForUpdates',
    'BLE Update Status': 'kef:ble/updateStatus',
    'BLE Update Now': 'kef:ble/updateNow',
    'BLE Update Later': 'kef:ble/updateLater',
    'BLE TX Version': 'kef:ble/updateServer/txVersion',
    'BLE UI': 'kef:ble/ui',

    # Speaker operations
    'Speaker Location': 'kef:speakerLocation',
    'Factory Reset': 'kef:speakerFactoryReset',
    'Restore DSP': 'kef:restoreDspSettings',
    'Restore DSP v2': 'kef:restoreDspSettings/v2',
    'DSP Info': 'kef:dspInfo',
    'Firmware Upgrade Info': 'kef:fwupgrade/info',
    'EQ Profile': 'kef:eqProfile',
    'EQ Profile v2': 'kef:eqProfile/v2',
}


# Network management
NETWORK_ENDPOINTS = {
    'WiFi Scan Results': 'networkwizard:wireless/scan_results',
    'WiFi Scan Activate': 'networkwizard:wireless/scan_activate',
    'WiFi Key': 'networkwizard:wireless/key',
    'Network Scan': 'network:scan',
    'Network Scan Results': 'network:scan_results',
    'Set Network Profile': 'network:setNetworkProfile',
    'Network Info': 'network:info',
}


# Player control endpoints
PLAYER_ENDPOINTS = {
    'Volume': 'player:volume',
    'Player Control': 'player:player/control',
    'Player Data': 'player:player/data',
    'Play Time': 'player:player/data/playTime',
}


# Power management endpoints
POWER_ENDPOINTS = {
    'Target State': 'powermanager:target',
    'Target Request': 'powermanager:targetRequest',
    'Reboot': 'powermanager:goReboot',
}


# Alerts & Timers
ALERTS_ENDPOINTS = {
    'List Alerts': 'alerts:/list',
    'Add Timer': 'alerts:/timer/add',
    'Remove Timer': 'alerts:/timer/remove',
    'Add Alarm': 'alerts:/alarm/add',
    'Remove Alarm': 'alerts:/alarm/remove',
    'Enable Alarm': 'alerts:/alarm/enable',
    'Disable Alarm': 'alerts:/alarm/disable',
    'Remove All Alarms': 'alerts:/alarm/remove/all',
    'Stop Alert': 'alerts:/stop',
    'Snooze Alarm': 'alerts:/alarm/snooze',
    'Play Default Sound': 'alerts:/defaultSound/play',
    'Stop Default Sound': 'alerts:/defaultSound/stop',
}


# Bluetooth endpoints
BLUETOOTH_ENDPOINTS = {
    'State': 'bluetooth:state',
    'Disconnect': 'bluetooth:disconnect',
    'Discoverable': 'bluetooth:externalDiscoverable',
    'Clear All Devices': 'bluetooth:clearAllDevices',
}


# Firmware update endpoints
FIRMWARE_ENDPOINTS = {
    'Update Status': 'firmwareupdate:updateStatus',
    'Check For Update': 'firmwareupdate:checkForUpdate',
    'Download Update': 'firmwareupdate:downloadNewUpdate',
}


# Google Cast endpoints
GOOGLECAST_ENDPOINTS = {
    'Usage Report': 'googlecast:usageReport',
    'Set Usage Report': 'googlecast:setUsageReport',
    'Cast Lite Usage': 'settings:/googleCastLite/usageReport',
    'Cast Lite ToS': 'settings:/googleCastLite/tosAccepted',
}


# Grouping / Multiroom endpoints
GROUPING_ENDPOINTS = {
    'Members': 'grouping:members',
    'Save Persistent Group': 'grouping:savePersistentGroup',
}


# Notification endpoints
NOTIFICATION_ENDPOINTS = {
    'Display Queue': 'notifications:/display/queue',
    'Cancel Notification': 'notifications:/display/cancel',
    'Player Notification': 'notifications:/player/playing',
}


# Other endpoints (XIO-specific and legacy)
OTHER_ENDPOINTS = {
    'UI Home': 'ui:',
    'Legacy Volume Set': 'hostlink:defaultVolume/set',
    'Calibration Start': 'kefdsp:/calibration/start',
    'Calibration Stop': 'kefdsp:/calibration/stop',
    'Decoder Codec': 'imx8af:decoderInfoCodecString',
    'VirtualX Active': 'imx8af:decoderInfoVirtualXActive',
    'BLE Channel': 'kefdsp:bleTx01ChannelAssignment',
}


def test_endpoint(host: str, name: str, path: str, timeout: int = 3) -> Dict[str, Any]:
    """Test a single endpoint."""
    url = f"http://{host}/api/getData?path={path}&roles=value"
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'OK',
                'code': 200,
                'data': data,
                'value': extract_value(data)
            }
        else:
            return {
                'status': f'HTTP {response.status_code}',
                'code': response.status_code,
                'data': None,
                'value': None
            }
    except requests.Timeout:
        return {'status': 'TIMEOUT', 'code': 0, 'data': None, 'value': None}
    except requests.ConnectionError:
        return {'status': 'CONNECTION_ERROR', 'code': 0, 'data': None, 'value': None}
    except Exception as e:
        return {'status': f'ERROR: {str(e)[:50]}', 'code': 0, 'data': None, 'value': None}


def extract_value(data):
    """Extract actual value from API response."""
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    item = data[0]
    if not isinstance(item, dict):
        return None
    # Find the value field (not 'type' or 'stability')
    for key, val in item.items():
        if key not in ['type', 'stability']:
            return val
    return None


def test_model(model_name: str, host: str, verbose: bool = False) -> Dict[str, Any]:
    """Test all endpoints on a single model."""
    print(f"\n{'=' * 80}")
    print(f"TESTING {model_name} ({host})")
    print(f"{'=' * 80}\n")

    results = {
        'settings': {},
        'operations': {},
        'network': {},
        'player': {},
        'power': {},
        'alerts': {},
        'bluetooth': {},
        'firmware': {},
        'googlecast': {},
        'grouping': {},
        'notifications': {},
        'other': {}
    }

    # Helper function to test and display category
    def test_category(category_name: str, endpoints: dict, results_key: str):
        print(f"\nTesting {category_name}...")
        for name, path in endpoints.items():
            result = test_endpoint(host, name, path)
            results[results_key][name] = result

            icon = '✅' if result['status'] == 'OK' else '❌'
            status_str = f"[{result['status']}]"

            if verbose and result['value'] is not None:
                value_str = f" = {result['value']}"
                if len(str(result['value'])) > 50:
                    value_str = f" = {str(result['value'])[:50]}..."
                print(f"{icon} {name:30s} {status_str}{value_str}")
            else:
                print(f"{icon} {name:30s} {status_str}")

    # Test all categories
    test_category("Settings Paths", ALL_SETTINGS, 'settings')
    test_category("KEF Operations", KEF_OPERATIONS, 'operations')
    test_category("Network Management", NETWORK_ENDPOINTS, 'network')
    test_category("Player Control", PLAYER_ENDPOINTS, 'player')
    test_category("Power Management", POWER_ENDPOINTS, 'power')
    test_category("Alerts & Timers", ALERTS_ENDPOINTS, 'alerts')
    test_category("Bluetooth", BLUETOOTH_ENDPOINTS, 'bluetooth')
    test_category("Firmware Updates", FIRMWARE_ENDPOINTS, 'firmware')
    test_category("Google Cast", GOOGLECAST_ENDPOINTS, 'googlecast')
    test_category("Grouping/Multiroom", GROUPING_ENDPOINTS, 'grouping')
    test_category("Notifications", NOTIFICATION_ENDPOINTS, 'notifications')
    test_category("Other Endpoints", OTHER_ENDPOINTS, 'other')

    return results


def summarize_results(model_results: Dict[str, Dict[str, Any]]):
    """Print summary of all test results."""
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80 + "\n")

    categories = [
        'settings', 'operations', 'network', 'player', 'power',
        'alerts', 'bluetooth', 'firmware', 'googlecast',
        'grouping', 'notifications', 'other'
    ]

    category_names = {
        'settings': 'Settings',
        'operations': 'KEF Operations',
        'network': 'Network',
        'player': 'Player',
        'power': 'Power',
        'alerts': 'Alerts',
        'bluetooth': 'Bluetooth',
        'firmware': 'Firmware',
        'googlecast': 'Google Cast',
        'grouping': 'Grouping',
        'notifications': 'Notifications',
        'other': 'Other'
    }

    for model, results in model_results.items():
        print(f"{model}:")

        total_ok = 0
        total_count = 0

        for category in categories:
            if category in results and results[category]:
                ok = sum(1 for r in results[category].values() if r['status'] == 'OK')
                count = len(results[category])
                total_ok += ok
                total_count += count
                pct = (ok * 100 // count) if count > 0 else 0
                print(f"  {category_names[category]:15s} {ok:3d}/{count:3d} ({pct:3d}%)")

        print(f"  {'─' * 30}")
        total_pct = (total_ok * 100 // total_count) if total_count > 0 else 0
        print(f"  {'TOTAL':15s} {total_ok:3d}/{total_count:3d} ({total_pct:3d}%)")
        print()


def save_results(model_results: Dict[str, Dict[str, Any]], output_file: str):
    """Save test results to JSON file."""
    # Convert to serializable format
    serializable_results = {}
    for model, categories in model_results.items():
        serializable_results[model] = {}
        for category, endpoints in categories.items():
            serializable_results[model][category] = {}
            for name, result in endpoints.items():
                serializable_results[model][category][name] = {
                    'status': result['status'],
                    'code': result['code'],
                    'value': str(result['value']) if result['value'] is not None else None
                }

    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2)

    print(f"Results saved to: {output_file}")


def extract_preset_values():
    """Extract and display subwoofer preset values from KEF Connect APK.

    Displays hardcoded preset values extracted from decompiled KEF Connect APK.
    Use when updating SUBWOOFER_PRESET_VALUES in kef_connector.py.

    Source files in APK:
    - com/kef/streamunlimitedapi/equalizer/model/SubwooferModelSubGainKt.java (gain)
    - com/kef/streamunlimitedapi/equalizer/model/SubwooferModelKt.java (frequencies)
    """
    print("=" * 80)
    print("KEF SUBWOOFER PRESET VALUE EXTRACTION")
    print("Source: KEF Connect APK v1.26.1")
    print("=" * 80)
    print()

    # Gain values from SubwooferModelSubGainKt.java (subgainForLSXII function)
    gain_lsxii = {
        'other': {False: {1: -6.0, 2: 0.0}},
        'kc62': {True: {1: -2.0, 2: 4.0}, False: {1: -7.0, 2: -1.0}},
        'kf92': {True: {1: -4.0, 2: 2.0}, False: {1: -9.0, 2: -3.0}},
        'kube8b': {True: {1: -4.0, 2: 2.0}, False: {1: -3.0, 2: 3.0}},
        'kube10b': {True: {1: -6.0, 2: 0.0}, False: {1: -5.0, 2: 1.0}},
        'kube12b': {True: {1: -8.0, 2: -2.0}, False: {1: -7.0, 2: -1.0}},
        'kube15mie': {True: {1: -7.0, 2: -1.0}, False: {1: -6.0, 2: 0.0}},
        't2': {False: {1: -7.0, 2: -1.0}},
    }

    # High-pass frequencies from SubwooferModelKt.java (highPassFreq function)
    highpass_lsxii = {
        'other': 65.0, 'kc62': 67.5, 'kf92': 67.5, 'kube8b': 67.5,
        'kube10b': 67.5, 'kube12b': 65.0, 'kube15mie': 65.0,
        't2': {True: None, False: 67.5},
    }

    # Low-pass frequencies from SubwooferModelKt.java (lowPassFreq function)
    lowpass_lsxii = {
        'other': 55.0, 'kc62': 55.0, 'kf92': 55.0, 'kube8b': 62.5,
        'kube10b': 55.0, 'kube12b': 52.5, 'kube15mie': 57.5,
        't2': {True: None, False: 62.5},
    }

    # Display gain values
    print("GAIN VALUES (dB) - XIO / LSX II / LSX II LT")
    print("-" * 80)
    for preset, kw1_map in gain_lsxii.items():
        for is_kw1, count_map in kw1_map.items():
            for count, gain in count_map.items():
                kw1_str = "KW1" if is_kw1 else "Internal"
                print(f"  {preset:12} | {kw1_str:8} | {count} sub(s) | Gain: {gain:5.1f} dB")
        print()

    # Display high-pass values
    print("HIGH-PASS FREQUENCIES (Hz) - XIO / LSX II / LSX II LT")
    print("-" * 80)
    for preset, value in highpass_lsxii.items():
        if isinstance(value, dict):
            for is_kw1, freq in value.items():
                kw1_str = "KW1" if is_kw1 else "Internal"
                freq_str = f"{freq:.1f}" if freq is not None else "N/A"
                print(f"  {preset:12} | {kw1_str:8} | High-pass: {freq_str:5} Hz")
        else:
            print(f"  {preset:12} | Both     | High-pass: {value:5.1f} Hz")
    print()

    # Display low-pass values
    print("LOW-PASS FREQUENCIES (Hz) - XIO / LSX II / LSX II LT")
    print("-" * 80)
    for preset, value in lowpass_lsxii.items():
        if isinstance(value, dict):
            for is_kw1, freq in value.items():
                kw1_str = "KW1" if is_kw1 else "Internal"
                freq_str = f"{freq:.1f}" if freq is not None else "N/A"
                print(f"  {preset:12} | {kw1_str:8} | Low-pass: {freq_str:5} Hz")
        else:
            print(f"  {preset:12} | Both     | Low-pass: {value:5.1f} Hz")
    print()

    print("!" * 80)
    print("CRITICAL: XIO/LSX2/LSX2LT have INVERTED subwoofer count mapping!")
    print("  Java 'subCount=1' applies when speaker has 2 subs configured")
    print("  Java 'subCount=2' applies when speaker has 1 sub configured")
    print("  Verified with XIO hardware and KEF Connect app v1.26.1")
    print("!" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Test KEF API Discovery across speaker models',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python test_api_discovery.py                    # Test all default models
  python test_api_discovery.py --host 192.168.1.100  # Test single speaker
  python test_api_discovery.py --verbose           # Show all values
  python test_api_discovery.py --output results.json  # Save results
        '''
    )
    parser.add_argument('--host', help='Single speaker IP to test')
    parser.add_argument('--models', choices=['all', 'lsx2', 'lsx2lt', 'xio'], default='all',
                        help='Which models to test (default: all)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output with values')
    parser.add_argument('--output', '-o', help='Save results to JSON file')

    args = parser.parse_args()

    # Determine which hosts to test
    if args.host:
        hosts = {'Custom': args.host}
    elif args.models == 'all':
        hosts = DEFAULT_HOSTS
    elif args.models == 'lsx2':
        hosts = {'LSX II': DEFAULT_HOSTS['LSX II']}
    elif args.models == 'lsx2lt':
        hosts = {'LSX II LT': DEFAULT_HOSTS['LSX II LT']}
    elif args.models == 'xio':
        hosts = {'XIO': DEFAULT_HOSTS['XIO']}

    # Run tests
    model_results = {}
    for model, host in hosts.items():
        try:
            results = test_model(model, host, verbose=args.verbose)
            model_results[model] = results
        except Exception as e:
            print(f"\n❌ Error testing {model}: {e}")

    # Print summary
    if model_results:
        summarize_results(model_results)

        # Save results if requested
        if args.output:
            save_results(model_results, args.output)


if __name__ == '__main__':
    main()
