#!/usr/bin/env python3
"""
KEF API Discovery - Comprehensive Testing Suite

This script tests all discovered KEF API endpoints across multiple speaker models.
Use this to verify API compatibility on your KEF speakers.

Usage:
    python test_api_discovery.py
    python test_api_discovery.py --host 192.168.1.100
    python test_api_discovery.py --models all
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
        'network': {}
    }

    # Test settings
    print("Testing Settings Paths...")
    for name, path in ALL_SETTINGS.items():
        result = test_endpoint(host, name, path)
        results['settings'][name] = result

        icon = '✅' if result['status'] == 'OK' else '❌'
        status_str = f"[{result['status']}]"

        if verbose and result['value'] is not None:
            value_str = f" = {result['value']}"
            if len(str(result['value'])) > 50:
                value_str = f" = {str(result['value'])[:50]}..."
            print(f"{icon} {name:30s} {status_str}{value_str}")
        else:
            print(f"{icon} {name:30s} {status_str}")

    # Test KEF operations
    print("\nTesting KEF Operations...")
    for name, path in KEF_OPERATIONS.items():
        result = test_endpoint(host, name, path)
        results['operations'][name] = result

        icon = '✅' if result['status'] == 'OK' else '❌'
        print(f"{icon} {name:30s} [{result['status']}]")

    # Test network endpoints
    print("\nTesting Network Management...")
    for name, path in NETWORK_ENDPOINTS.items():
        result = test_endpoint(host, name, path)
        results['network'][name] = result

        icon = '✅' if result['status'] == 'OK' else '❌'
        print(f"{icon} {name:30s} [{result['status']}]")

    return results


def summarize_results(model_results: Dict[str, Dict[str, Any]]):
    """Print summary of all test results."""
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80 + "\n")

    for model, results in model_results.items():
        settings_ok = sum(1 for r in results['settings'].values() if r['status'] == 'OK')
        settings_total = len(results['settings'])
        operations_ok = sum(1 for r in results['operations'].values() if r['status'] == 'OK')
        operations_total = len(results['operations'])
        network_ok = sum(1 for r in results['network'].values() if r['status'] == 'OK')
        network_total = len(results['network'])

        total_ok = settings_ok + operations_ok + network_ok
        total = settings_total + operations_total + network_total

        print(f"{model}:")
        print(f"  Settings:   {settings_ok}/{settings_total} ({settings_ok*100//settings_total}%)")
        print(f"  Operations: {operations_ok}/{operations_total} ({operations_ok*100//operations_total}%)")
        print(f"  Network:    {network_ok}/{network_total} ({network_ok*100//network_total}%)")
        print(f"  TOTAL:      {total_ok}/{total} ({total_ok*100//total}%)")
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
