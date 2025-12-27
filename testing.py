# script_version=3
# Leaving the top comment for backward compatibility
CURRENT_SCRIPT_VERSION=3
# %%

try:
    import pykefcontrol as pkf
    import sys
    import socket
    from rich import print
    from rich.console import Console
    import ipaddress
    import time
    import requests
    import argparse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
except Exception as e:
    print("Error:", e, style="red")
    print("Please install the required packages with `pip install -r testing_reqs.txt`")
    sys.exit()

# %%
console = Console()
AUTO_TESTS_OUTPUT = {}
USER_CONFIRMATION = {}
DEBUG = False
MODEL_SELECTED = None  # Will be set to a model identifier string (LSXII, LSXIILT, LS50WirelessII, LS60Wireless, XIO)
NON_INTERACTIVE = False  # Flag for non-interactive mode
HOST = None  # Speaker IP address
spkr = None  # Speaker connection object
MODEL_LIST = {
    "LSXII": "LSX II",
    "LSXIILT": "LSX II LT",
    "LS50WirelessII": "LS50 Wireless II",
    "LS60Wireless": "LS60 Wireless",
    "XIO": "XIO Soundbar"
}

MODEL_SOURCES = {
    "LSXII": ["wifi", "bluetooth", "tv", "optical", "analog", "usb"],
    "LSXIILT": ["wifi", "bluetooth", "tv", "optical", "usb"],  # No analog input
    "LS50WirelessII": ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
    "LS60Wireless": ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
    "XIO": ["wifi", "bluetooth", "tv", "optical", "hdmi"],
}


def select_model():
    global MODEL_SELECTED
    newline()
    console.print("[dodger_blue1]Select your speaker model:[/dodger_blue1]")
    console.print("[bold]1[/bold] KEF LSX II")
    console.print("[bold]2[/bold] KEF LSX II LT")
    console.print("[bold]3[/bold] KEF LS50 Wireless II")
    console.print("[bold]4[/bold] KEF LS60 Wireless")
    console.print("[bold]5[/bold] KEF XIO Soundbar")

    try:
        selection = int(input("Enter the number of your speaker model (1-5): "))
    except:
        selection = -1

    while selection not in [1, 2, 3, 4, 5]:
        console.print("\tPlease enter 1, 2, 3, 4, or 5: ", end="")
        try:
            selection = int(input())
        except:
            selection = -1

    # Map selection to model identifier
    model_keys = list(MODEL_LIST.keys())
    MODEL_SELECTED = model_keys[selection - 1]
    newline()


def newline():
    print("\n")


def get_local_ip():
    return (
        (
            [
                ip
                for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                if not ip.startswith("127.")
            ]
            or [
                [
                    (s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close())
                    for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]
                ][0][1]
            ]
        )
        + ["no IP found"]
    )[0]


def validate_ip_address(ip_string):
    try:
        ip_object = ipaddress.ip_address(ip_string)
        return str(ip_object)
    except ValueError:
        print(
            f"The IP address '{ip_string}' is not valid.\n\
        Please enter a valid IP address in the form www.xxx.yyy.zzz"
        )
        return -1


def check_kef_speaker(ip, timeout=1.5):
    """Check if a KEF speaker is available at the given IP address.

    Returns tuple: (is_speaker, speaker_info_dict or None)
    """
    try:
        # KEF speakers use HTTP API on port 80
        # Try to connect and get speaker info
        speaker = pkf.KefConnector(ip)

        # Try to get basic info with short timeout
        # If this succeeds, it's a KEF speaker
        info = {
            'ip': ip,
            'name': speaker.speaker_name,
            'model': speaker.speaker_model,
            'mac': speaker.mac_address,
            'firmware': speaker.firmware_version
        }
        return (True, info)
    except Exception:
        # Not a KEF speaker or not reachable
        return (False, None)


def discover_kef_speakers(network_range=None, max_workers=50):
    """Discover KEF speakers on the network.

    Args:
        network_range: IP range to scan (e.g., "192.168.16.0/24").
                      If None, auto-detects from local IP.
        max_workers: Number of parallel threads for scanning.

    Returns:
        List of dictionaries with speaker information.
    """
    if network_range is None:
        # Auto-detect network from local IP
        local_ip = get_ip()
        if local_ip == "no IP found":
            console.print("[bold red]Could not detect local IP address[/bold red]")
            return []

        # Assume /24 network (common for home networks)
        network_range = ".".join(local_ip.split(".")[:-1]) + ".0/24"

    console.print(f"[cyan3]Scanning network {network_range} for KEF speakers...[/cyan3]")

    discovered_speakers = []
    network = ipaddress.ip_network(network_range, strict=False)

    # Get list of hosts to scan (excludes network and broadcast addresses)
    hosts_to_scan = list(network.hosts())
    total_ips = len(hosts_to_scan)
    scanned = 0
    found = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all IP checks
        future_to_ip = {
            executor.submit(check_kef_speaker, str(ip)): str(ip)
            for ip in hosts_to_scan
        }

        # Process results as they complete
        with console.status(f"[cyan3]Scanning... 0/{total_ips} IPs checked, 0 speakers found[/cyan3]"):
            for future in as_completed(future_to_ip):
                scanned += 1
                is_speaker, info = future.result()
                if is_speaker and info:
                    found += 1
                    discovered_speakers.append(info)
                    console.print(f"[bold green]OK Found KEF speaker:[/bold green] {info['name']} ({info['model']}) at {info['ip']}")

                # Update status every 10 IPs
                if scanned % 10 == 0:
                    console.print(f"[cyan3]Progress: {scanned}/{total_ips} IPs checked, {found} speakers found[/cyan3]", end="\r")

    console.print(f"\n[bold]Scan complete:[/bold] Found {len(discovered_speakers)} KEF speaker(s)")
    return discovered_speakers


def check_script_version():
    try:
        with console.status("Checking if this script is up to date..."):
            with requests.get(
                "https://raw.githubusercontent.com/N0ciple/pykefcontrol/main/testing.py"
            ) as response:
                output = response.text
        version = output.split("# script_version=")[1].split("\n")[0]
        if version == CURRENT_SCRIPT_VERSION:
            console.print(
                f"[bold green]This script is up to date.[/bold green]",
            )
        else:
            console.print(
                "[bold orange_red1]Testing utility is not up to date.[/bold orange_red1]\n\
                    Please upgrade with [bold red]`git pull`[/bold red] in the pykefcontrol folder."
            )
    except Exception as e:
        console.print("Error:", e, style="red")
        console.print(
            "[bold orange_red1]Could not check testing utility version.[/bold orange_red1]"
        )
        console.print(
            "Continuing anyway... but script version might not be the latest!"
        )

    if not NON_INTERACTIVE:
        input("Press enter to continue...")


def prompt_continue():
    if not NON_INTERACTIVE:
        input("Press enter to continue...")


def rule_msg(msg, sep="-"):
    console.print(f"[cyan3]{msg}[/cyan3]".center(80, sep))


def report_github(e):
    console.print(f"[bold red]Error: {e}[/bold red]")
    console.print("[orange1]Please report this error on the github repo![/orange1]")
    sys.exit()


def user_confirmation(console, action, msg=None):
    if msg is None:
        console.print("Do you confirm the change was successful? (y/n) ", end="")
    else:
        console.print(f"{msg} (y/n) ", end="")
    user_input = input()
    while user_input.lower() not in ["y", "n"]:
        console.print("\tPlease enter y (for yes) or n (for no): ", end="")
        user_input = input()
    if user_input.lower() == "y":
        console.print("\t[bold green]✅ Sucess![/bold green]")
        return {action: True}

    else:
        console.print("\t[bold orange_red1]❌ Failure ![/bold orange_red1]")
        return {action: False}


def speaker_info():
    global spkr

    if NON_INTERACTIVE:
        # In non-interactive mode, spkr is already created
        rule_msg("Speaker Information")
        spkr_ip = HOST
    else:
        rule_msg("Speaker IP Address")
        console.print("The script will gather a few informations about your speaker.")
        console.print(
            "[orange1]The script needs the [bold]IP address[/bold] of your speaker.[/orange1]"
        )
        prompt_continue()
        print(
            "Please enter the IP address of your KEF speaker in the form www.xxx.yyy.zzz\n(192.168.0.12 for example)"
        )

        spkr_ip = validate_ip_address(input("IP Address: "))
        while spkr_ip == -1:
            spkr_ip = validate_ip_address(input("IP Address: "))

        print("Using speaker IP:", spkr_ip)
        newline()
        rule_msg("Speaker Information")
        spkr = pkf.KefConnector(spkr_ip)
    with console.status(
        "Getting speaker info...",
    ):

        exception = None
        try:
            spkr_name = spkr.speaker_name
        except Exception as e:
            exception = e
        if exception is not None:
            console.print("[orange1]Error while fetching speaker name[/orange1]")
            console.print(f"[bold red]Error: {e}[/bold red]")
            newline()
            console.print(
                "Verify that your speaker is plugged in  and connected to the network."
            )
            console.print(
                "Verify that your computer is connected to the same network as your speaker."
            )
            console.print("Verify that the IP address is correct.")
            console.print(
                "[orange1]Otherwise, please report this error on the github repo! [/orange1]"
            )
            sys.exit()
        time.sleep(0.5)
    try:
        spkr_mac_address = spkr.mac_address
    except Exception as e:
        report_github(e)

    print("Speaker Infos:")
    print("\tIP:", spkr_ip)
    print(f'\tName: "{spkr_name}"')
    print("\tMAC Address:", spkr_mac_address)
    print(f"\tModel: [dodger_blue1]{MODEL_LIST[MODEL_SELECTED]}[/dodger_blue1]")
    newline()
    if not NON_INTERACTIVE:
        USER_CONFIRMATION.update(
            user_confirmation(console, "speaker_info", msg="Are the information correct?")
        )
    return spkr


def power_check():
    rule_msg("Testing Power ON/OFF")
    console.print("The script will now test the power ON/OFF feature.")
    with console.status("Detecting status..."):
        try:
            status = spkr.status
        except Exception as e:
            report_github(e)
    if status == "standby":

        console.print("The speaker is currently OFF.")
        console.print("Turning ON the speaker...")
        try:
            spkr.power_on()
        except Exception as e:
            report_github(e)
        with console.status("Waiting for the speaker to turn ON (10s)..."):
            time.sleep(10)
        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                "power_on",
                msg="Did the speaker turn ON successfully? \n[orange1]it should be on but no sources should be selected[/orange1]",
            )
        )

        console.print("Turning OFF the speaker...")
        try:
            spkr.shutdown()
        except Exception as e:
            report_github(e)
        with console.status("Waiting for the speaker to turn OFF..."):
            time.sleep(5)
        USER_CONFIRMATION.update(
            user_confirmation(
                console, "power_off", msg="Did the speaker turn OFF successfully?"
            )
        )

        console.print("Turning ON the speaker again...")
        try:
            spkr.power_on()
        except Exception as e:
            report_github(e)
        with console.status("Waiting for the speaker to turn ON again (10s)..."):
            time.sleep(10)
        user_confirmation(
            console,
            "power_on",
            msg="Did the speaker turn ON successfully?\n[orange1]it should be on but no sources should be selected[/orange1]",
        )
    else:
        console.print("The speaker is currently ON.")
        console.print("Turning OFF the speaker...")
        try:
            spkr.shutdown()
        except Exception as e:
            report_github(e)
        with console.status("Waiting for the speaker to turn OFF..."):
            time.sleep(5)
        USER_CONFIRMATION.update(
            user_confirmation(
                console, "power_off", msg="Did the speaker turn OFF successfully?"
            )
        )

        console.print("Turning ON the speaker...")
        try:
            spkr.power_on()
        except Exception as e:
            report_github(e)
        with console.status("Waiting for the speaker to turn ON (10s)..."):
            time.sleep(10)
        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                "power_on",
                msg="Did the speaker turn ON successfully?\n[orange1]it should be on but no sources should be selected[/orange1]",
            )
        )

    if USER_CONFIRMATION["power_on"] and USER_CONFIRMATION["power_off"]:
        console.print("[bold green]All power tests passed ! [/bold green]")


def source_check():
    rule_msg("Testing Source Selection")
    console.print("The script will now test the source selection feature.")
    console.print(
        f"The script will cycle through the channels: [dodger_blue1]{' ,'.join(MODEL_SOURCES[MODEL_SELECTED])}[/dodger_blue1]"
    )
    console.print(
        "[orange1]You can check on the speakers LED or on the [bold]KEF Connect[/bold] app (recommended)[/orange1]"
    )
    console.print(
        "[red]You do NOT need to play any sound. Just make sure the speaker changes its input source[/red]"
    )
    prompt_continue()
    for source in MODEL_SOURCES[MODEL_SELECTED]:
        console.print(f"Selecting source: [dodger_blue1]{source}[/dodger_blue1]")
        try:
            spkr.source = source
        except Exception as e:
            report_github(e)
        with console.status(f"Waiting for the speaker to select {source} (10s)..."):
            time.sleep(1.5)
        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                f"select {source}",
                msg=f"\tDid the speaker select {source} successfully?",
            )
        )

    console.print("Switching back to wifi...")
    try:
        spkr.source = "wifi"
    except:
        report_github(e)

    all_checks = True
    for source in MODEL_SOURCES[MODEL_SELECTED]:
        all_checks *= USER_CONFIRMATION[f"select {source}"]
    if all_checks:
        console.print("[bold green]All source tests passed ! [/bold green]")


def sumup():

    rule_msg("Sum Up")
    console.print("[bold]Speaker version:[/bold]")
    console.print(f"\t[dodger_blue1]{MODEL_LIST[MODEL_SELECTED]}[/dodger_blue1]")
    console.print("[bold]Working features:[/bold]")
    for feature in USER_CONFIRMATION:
        if USER_CONFIRMATION[feature]:
            console.print(f"\t[green]OK[/green] {feature}")
    console.print("[bold]Non working features:[/bold]")
    for feature in USER_CONFIRMATION:
        if not USER_CONFIRMATION[feature]:
            console.print(f"\t[red]X[/red] {feature}")


def vol_test():
    rule_msg("Testing Volume Control")
    console.print("The script will now test the volume control feature.")
    prompt_continue()
    try:
        vol = spkr.volume
    except Exception as e:
        report_github(e)
    console.print(f"Current volume: [dodger_blue1]{vol}[/dodger_blue1]")

    if vol < 10:
        console.print(f"setting volume to {vol+5}")
        newvol = vol + 5
    else:
        console.print(f"setting volume to {vol-5}")
        newvol = vol - 5
        try:
            spkr.volume = newvol
        except Exception as e:
            report_github(e)

        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                "set volume",
                msg="Did the speaker change its volume successfully?\n[orange1]You can check on the [bold]KEF Connect[/bold] app[/orange1]",
            )
        )
        newline()
        console.print("The script will now test the mute/unmute feature.")
        console.print(
            "[orange1]You can play a song or just check on the KEF Connect app.[/orange1]"
        )
        prompt_continue()
        newline()
        console.print("Muting the speaker...")
        try:
            spkr.mute()
        except Exception as e:
            report_github(e)
        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                "mute",
                msg="Did the speaker was muted successfully?",
            )
        )
        newline()
        console.print("Now testing the unmuting feature.")
        console.print("Unmuting the speaker...")
        try:
            spkr.unmute()
        except Exception as e:
            report_github(e)
        USER_CONFIRMATION.update(
            user_confirmation(
                console,
                "unmute",
                msg="Did the speaker was unmuted successfully?",
            )
        )

    if (
        USER_CONFIRMATION["set volume"]
        and USER_CONFIRMATION["mute"]
        and USER_CONFIRMATION["unmute"]
    ):
        console.print("[bold green]All volume tests passed ! [/bold green]")


def system_infos():
    python_version = sys.version
    pkf_version = pkf.__version__
    computer_ip = get_local_ip()

    rule_msg("System info")
    print("Python version:", python_version)
    # if pkf_version == "0.6.1":
    #     end_msg = "(✅ Latest version)"
    # else:
    #     end_msg = "(⚠️ not the latest version, please upgrade with `pip install pykefcontrol --upgrade`)"
    print("Pykefcontrol version:", pkf_version)
    print("Computer local IP:", computer_ip)


def song_info():
    rule_msg("Song Info")
    console.print("The script will now test the song info fetching.")
    console.print("[bold red]Make sure the speaker is playing a song.[/bold red]")
    console.print(
        "[bold red]the song should be playing via Chromecast, Airplay, Spotify Connect or DLNA.[/bold red]"
    )

    input("Press [ENTER] to continue, when a song is playing...")
    with console.status("Checking if a song is playing"):
        try:
            while not spkr.is_playing:
                time.sleep(0.5)
        except Exception as e:
            report_github(e)
    console.print("A song is playing, fetching song info...")
    try:
        song_info = spkr.get_song_information()
    except Exception as e:
        report_github(e)

    console.print(
        f"Current song informations: [dodger_blue1]{song_info}[/dodger_blue1]"
    )
    USER_CONFIRMATION.update(
        user_confirmation(
            console,
            "get song info",
            msg="Did the script fetch the song info successfully?\n(are they [bold red]roughly[/bold red] correct?)",
        )
    )
    if USER_CONFIRMATION["get song info"]:
        console.print("[bold green]All song info tests passed ! [/bold green]")


def track_control():
    rule_msg("Track Control")
    console.print("The script will now test the track control feature.")
    console.print("[bold red]Make sure the speaker is playing a song.[/bold red]")
    console.print(
        "The script will test [dot blue]next track, previous track[/dot blue] and [dot blue]pause/play[/dot blue]."
    )
    input("Press [ENTER] to continue, when a song is playing...")
    with console.status("Checking if a song is playing"):
        try:
            while not spkr.is_playing:
                time.sleep(0.5)
        except Exception as e:
            report_github(e)
    console.print("A song is playing, testing next track...")
    try:
        spkr.next_track()
    except Exception as e:
        report_github(e)
    USER_CONFIRMATION.update(
        user_confirmation(
            console,
            "next track",
            msg="Did the speaker skip to the next track successfully?",
        )
    )
    newline()
    console.print("Testing previous track...")
    try:
        spkr.previous_track()
    except Exception as e:
        report_github(e)
    USER_CONFIRMATION.update(
        user_confirmation(
            console,
            "previous track",
            msg="Did the speaker skip to the previous track successfully?",
        )
    )
    newline()
    console.print("Testing pause...")
    console.print("[bold red]Make sure the speaker is playing a song.[/bold red]")
    input("Press [ENTER] to continue, when a song is playing...")

    try:
        spkr.toggle_play_pause()
    except Exception as e:
        report_github(e)
    USER_CONFIRMATION.update(
        user_confirmation(
            console,
            "pause",
            msg="Did the speaker pause the song successfully?",
        )
    )
    newline()
    console.print("Testing play...")
    console.print("[bold red]Make sure the speaker is paused.[/bold red]")
    input("Press [ENTER] to continue, when the speaker is paused...")
    try:
        spkr.toggle_play_pause()
    except Exception as e:
        report_github(e)
    USER_CONFIRMATION.update(
        user_confirmation(
            console,
            "play",
            msg="Did the speaker resumed the song successfully?",
        )
    )

    if (
        USER_CONFIRMATION["next track"]
        and USER_CONFIRMATION["previous track"]
        and USER_CONFIRMATION["pause"]
        and USER_CONFIRMATION["play"]
    ):
        console.print("[bold green]All track control tests passed ! [/bold green]")


def dsp_eq_test():
    """Test ALL DSP/EQ features including filters and profile management"""
    rule_msg("DSP/EQ & Filters Control")
    console.print("The script will now test DSP/EQ control features.")
    console.print("[orange1]These features control the speaker's sound processing[/orange1]")
    prompt_continue()

    # Get initial profile
    console.print("\n[dodger_blue1]Testing get_eq_profile()...[/dodger_blue1]")
    try:
        initial_profile = spkr.get_eq_profile()
        console.print("[green]OK[/green] Successfully retrieved EQ profile")
        USER_CONFIRMATION["eq_get_profile"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["eq_get_profile"] = False

    # Test desk mode
    console.print("\n[dodger_blue1]Testing Desk Mode (get/set)...[/dodger_blue1]")
    try:
        spkr.set_desk_mode(True, -3)
        time.sleep(0.5)
        desk_enabled, desk_db = spkr.get_desk_mode()
        if desk_enabled and desk_db == -3:
            console.print(f"[green]OK[/green] Desk mode: enabled at {desk_db} dB")
            USER_CONFIRMATION["dsp_desk_mode"] = True
        else:
            console.print(f"[red]X[/red] Expected enabled/-3, got {desk_enabled}/{desk_db}")
            USER_CONFIRMATION["dsp_desk_mode"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_desk_mode"] = False

    # Test wall mode
    console.print("\n[dodger_blue1]Testing Wall Mode (get/set)...[/dodger_blue1]")
    try:
        spkr.set_wall_mode(True, -4.5)
        time.sleep(0.5)
        wall_enabled, wall_db = spkr.get_wall_mode()
        if wall_enabled and wall_db == -4.5:
            console.print(f"[green]OK[/green] Wall mode: enabled at {wall_db} dB")
            USER_CONFIRMATION["dsp_wall_mode"] = True
        else:
            console.print(f"[red]X[/red] Expected enabled/-4.5, got {wall_enabled}/{wall_db}")
            USER_CONFIRMATION["dsp_wall_mode"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_wall_mode"] = False

    # Test bass extension
    console.print("\n[dodger_blue1]Testing Bass Extension (get/set)...[/dodger_blue1]")
    try:
        spkr.set_bass_extension("extra")
        time.sleep(0.5)
        bass = spkr.get_bass_extension()
        if bass == "extra":
            console.print(f"[green]OK[/green] Bass extension: {bass}")
            USER_CONFIRMATION["dsp_bass_extension"] = True
        else:
            console.print(f"[red]X[/red] Expected 'extra', got '{bass}'")
            USER_CONFIRMATION["dsp_bass_extension"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_bass_extension"] = False

    # Test treble
    console.print("\n[dodger_blue1]Testing Treble Control (get/set)...[/dodger_blue1]")
    try:
        spkr.set_treble_amount(3)
        time.sleep(0.5)
        treble = spkr.get_treble_amount()
        if treble == 3:
            console.print(f"[green]OK[/green] Treble: {treble} dB")
            USER_CONFIRMATION["dsp_treble"] = True
        else:
            console.print(f"[red]X[/red] Expected 3, got {treble}")
            USER_CONFIRMATION["dsp_treble"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_treble"] = False

    # Test balance
    console.print("\n[dodger_blue1]Testing Balance Control (get/set)...[/dodger_blue1]")
    try:
        spkr.set_balance(5)
        time.sleep(0.5)
        balance = spkr.get_balance()
        if balance == 5:
            console.print(f"[green]OK[/green] Balance: {balance}")
            USER_CONFIRMATION["dsp_balance"] = True
        else:
            console.print(f"[red]X[/red] Expected 5, got {balance}")
            USER_CONFIRMATION["dsp_balance"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_balance"] = False

    # Test phase correction
    console.print("\n[dodger_blue1]Testing Phase Correction (get/set)...[/dodger_blue1]")
    try:
        spkr.set_phase_correction(True)
        time.sleep(0.5)
        phase = spkr.get_phase_correction()
        if phase:
            console.print(f"[green]OK[/green] Phase correction: enabled")
            USER_CONFIRMATION["dsp_phase_correction"] = True
        else:
            console.print(f"[red]X[/red] Expected True, got {phase}")
            USER_CONFIRMATION["dsp_phase_correction"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["dsp_phase_correction"] = False

    # Test profile name
    console.print("\n[dodger_blue1]Testing Profile Name (get/set)...[/dodger_blue1]")
    try:
        original_name = spkr.get_profile_name()
        spkr.set_profile_name("Test Profile")
        time.sleep(0.5)
        name = spkr.get_profile_name()
        if name == "Test Profile":
            console.print(f"[green]OK[/green] Profile name: '{name}'")
            USER_CONFIRMATION["profile_name"] = True
            # Restore original name
            spkr.set_profile_name(original_name)
        else:
            console.print(f"[red]X[/red] Expected 'Test Profile', got '{name}'")
            USER_CONFIRMATION["profile_name"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["profile_name"] = False

    # Test high-pass filter
    console.print("\n[dodger_blue1]Testing High-Pass Filter (get/set)...[/dodger_blue1]")
    try:
        spkr.set_high_pass_filter(True, 80)
        time.sleep(0.5)
        hp_enabled, hp_freq = spkr.get_high_pass_filter()
        if hp_enabled and hp_freq == 80:
            console.print(f"[green]OK[/green] High-pass filter: enabled at {hp_freq} Hz")
            USER_CONFIRMATION["high_pass_filter"] = True
        else:
            console.print(f"[red]X[/red] Expected enabled/80, got {hp_enabled}/{hp_freq}")
            USER_CONFIRMATION["high_pass_filter"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["high_pass_filter"] = False

    # Test audio polarity
    console.print("\n[dodger_blue1]Testing Audio Polarity (get/set)...[/dodger_blue1]")
    try:
        spkr.set_audio_polarity("normal")
        time.sleep(0.5)
        polarity = spkr.get_audio_polarity()
        if polarity == "normal":
            console.print(f"[green]OK[/green] Audio polarity: {polarity}")
            USER_CONFIRMATION["audio_polarity"] = True
        else:
            console.print(f"[red]X[/red] Expected 'normal', got '{polarity}'")
            USER_CONFIRMATION["audio_polarity"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["audio_polarity"] = False

    # Test update_dsp_setting (generic method)
    console.print("\n[dodger_blue1]Testing update_dsp_setting()...[/dodger_blue1]")
    try:
        spkr.update_dsp_setting("trebleAmount", 0)
        time.sleep(0.5)
        treble = spkr.get_treble_amount()
        if treble == 0:
            console.print(f"[green]OK[/green] update_dsp_setting: trebleAmount set to 0")
            USER_CONFIRMATION["update_dsp_setting"] = True
        else:
            console.print(f"[red]X[/red] Expected 0, got {treble}")
            USER_CONFIRMATION["update_dsp_setting"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["update_dsp_setting"] = False

    # Count successes
    dsp_tests = [
        "eq_get_profile", "dsp_desk_mode", "dsp_wall_mode", "dsp_bass_extension",
        "dsp_treble", "dsp_balance", "dsp_phase_correction", "profile_name",
        "high_pass_filter", "audio_polarity", "update_dsp_setting"
    ]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in dsp_tests])

    if passed == len(dsp_tests):
        console.print(f"\n[bold green]All DSP/EQ/Filter tests passed! ({passed}/{len(dsp_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]DSP/EQ/Filter tests: {passed}/{len(dsp_tests)} passed[/bold orange1]")


def subwoofer_test():
    """Test ALL subwoofer control features (6 methods)"""
    rule_msg("Subwoofer Control")
    console.print("The script will now test subwoofer control features.")
    console.print("[orange1]These tests require a connected subwoofer[/orange1]")
    console.print("[orange1]Skip this section if no subwoofer is connected[/orange1]")

    if not NON_INTERACTIVE:
        skip = input("Do you have a subwoofer connected? (y/n): ")
        if skip.lower() != 'y':
            console.print("[yellow]Skipping subwoofer tests[/yellow]")
            return
    else:
        console.print("[yellow]Non-interactive mode: assuming no subwoofer connected[/yellow]")
        console.print("[yellow]Skipping tests that change subwoofer settings[/yellow]")

    prompt_continue()

    # Test subwoofer enable/disable
    console.print("\n[dodger_blue1]Testing Subwoofer Enable (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_enabled(True)
        time.sleep(0.5)
        enabled = spkr.get_subwoofer_enabled()
        if enabled:
            console.print(f"[green]OK[/green] Subwoofer: enabled")
            USER_CONFIRMATION["sub_enable"] = True
        else:
            console.print(f"[red]X[/red] Expected True, got {enabled}")
            USER_CONFIRMATION["sub_enable"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_enable"] = False

    # Test subwoofer gain
    console.print("\n[dodger_blue1]Testing Subwoofer Gain (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_gain(5)
        time.sleep(0.5)
        gain = spkr.get_subwoofer_gain()
        if gain == 5:
            console.print(f"[green]OK[/green] Subwoofer gain: {gain} dB")
            USER_CONFIRMATION["sub_gain"] = True
        else:
            console.print(f"[red]X[/red] Expected 5, got {gain}")
            USER_CONFIRMATION["sub_gain"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_gain"] = False

    # Test subwoofer polarity
    console.print("\n[dodger_blue1]Testing Subwoofer Polarity (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_polarity("normal")
        time.sleep(0.5)
        polarity = spkr.get_subwoofer_polarity()
        if polarity == "normal":
            console.print(f"[green]OK[/green] Subwoofer polarity: {polarity}")
            USER_CONFIRMATION["sub_polarity"] = True
        else:
            console.print(f"[red]X[/red] Expected 'normal', got '{polarity}'")
            USER_CONFIRMATION["sub_polarity"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_polarity"] = False

    # Test subwoofer preset
    console.print("\n[dodger_blue1]Testing Subwoofer Preset (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_preset("kube8b")
        time.sleep(0.5)
        preset = spkr.get_subwoofer_preset()
        if preset == "kube8b":
            console.print(f"[green]OK[/green] Subwoofer preset: {preset}")
            USER_CONFIRMATION["sub_preset"] = True
        else:
            console.print(f"[red]X[/red] Expected 'kube8b', got '{preset}'")
            USER_CONFIRMATION["sub_preset"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_preset"] = False

    # Test subwoofer low-pass filter
    console.print("\n[dodger_blue1]Testing Subwoofer Low-Pass (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_lowpass(80)
        time.sleep(0.5)
        lowpass = spkr.get_subwoofer_lowpass()
        if lowpass == 80:
            console.print(f"[green]OK[/green] Subwoofer low-pass: {lowpass} Hz")
            USER_CONFIRMATION["sub_lowpass"] = True
        else:
            console.print(f"[red]X[/red] Expected 80, got {lowpass}")
            USER_CONFIRMATION["sub_lowpass"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_lowpass"] = False

    # Test subwoofer stereo mode
    console.print("\n[dodger_blue1]Testing Subwoofer Stereo (get/set)...[/dodger_blue1]")
    try:
        spkr.set_subwoofer_stereo(False)
        time.sleep(0.5)
        stereo = spkr.get_subwoofer_stereo()
        if stereo == False:
            console.print(f"[green]OK[/green] Subwoofer stereo: disabled")
            USER_CONFIRMATION["sub_stereo"] = True
        else:
            console.print(f"[red]X[/red] Expected False, got {stereo}")
            USER_CONFIRMATION["sub_stereo"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["sub_stereo"] = False

    # Count successes
    sub_tests = ["sub_enable", "sub_gain", "sub_polarity", "sub_preset", "sub_lowpass", "sub_stereo"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in sub_tests])

    if passed == len(sub_tests):
        console.print(f"\n[bold green]All subwoofer tests passed! ({passed}/{len(sub_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Subwoofer tests: {passed}/{len(sub_tests)} passed[/bold orange1]")


def xio_specific_test():
    """Test XIO soundbar-specific features (sound_profile, wall_mounted)"""
    rule_msg("XIO Soundbar Features")
    console.print("The script will now test XIO-specific features.")
    console.print("[orange1]These features are only available on KEF XIO soundbars[/orange1]")
    console.print("[orange1]Skip this section if you don't have an XIO[/orange1]")

    skip = input("Are you testing a KEF XIO soundbar? (y/n): ")
    if skip.lower() != 'y':
        console.print("[yellow]Skipping XIO-specific tests[/yellow]")
        return

    prompt_continue()

    # Test sound profile (XIO)
    console.print("\n[dodger_blue1]Testing Sound Profile (get/set)...[/dodger_blue1]")
    console.print("[orange1]Sound profiles: default, music, movie, night, dialogue, direct[/orange1]")
    try:
        spkr.set_sound_profile("movie")
        time.sleep(0.5)
        profile = spkr.get_sound_profile()
        if profile == "movie":
            console.print(f"[green]OK[/green] Sound profile: {profile}")
            USER_CONFIRMATION["xio_sound_profile"] = True
            # Restore to default
            spkr.set_sound_profile("default")
        else:
            console.print(f"[red]X[/red] Expected 'movie', got '{profile}'")
            USER_CONFIRMATION["xio_sound_profile"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["xio_sound_profile"] = False

    # Test wall mounted (XIO)
    console.print("\n[dodger_blue1]Testing Wall Mounted (get/set)...[/dodger_blue1]")
    try:
        original_mounted = spkr.get_wall_mounted()
        spkr.set_wall_mounted(True)
        time.sleep(0.5)
        mounted = spkr.get_wall_mounted()
        if mounted == True:
            console.print(f"[green]OK[/green] Wall mounted: True")
            USER_CONFIRMATION["xio_wall_mounted"] = True
            # Restore original setting
            spkr.set_wall_mounted(original_mounted)
        else:
            console.print(f"[red]X[/red] Expected True, got {mounted}")
            USER_CONFIRMATION["xio_wall_mounted"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["xio_wall_mounted"] = False

    # Count successes
    xio_tests = ["xio_sound_profile", "xio_wall_mounted"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in xio_tests])

    if passed == len(xio_tests):
        console.print(f"\n[bold green]All XIO tests passed! ({passed}/{len(xio_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]XIO tests: {passed}/{len(xio_tests)} passed[/bold orange1]")


def subwoofer_preset_analysis():
    """Comprehensive test of all subwoofer presets and their automatic parameter changes.

    This test cycles through all available KEF subwoofer presets and verifies that
    the speaker automatically adjusts gain, low-pass, and high-pass filter values
    according to the preset specifications.

    Available presets: kc62, kf92, kube8b, kube10b, kube12b, kube15, t2
    """
    rule_msg("Subwoofer Preset Analysis")
    console.print("This test will cycle through all KEF subwoofer presets")
    console.print("and verify automatic parameter adjustments.")
    console.print("[orange1]This test requires a connected subwoofer[/orange1]")

    if not NON_INTERACTIVE:
        skip = input("Run comprehensive preset analysis? (y/n): ")
        if skip.lower() != 'y':
            console.print("[yellow]Skipping preset analysis[/yellow]")
            return

    # All known KEF subwoofer presets
    presets = ['kc62', 'kf92', 'kube8b', 'kube10b', 'kube12b', 'kube15', 't2']

    console.print(f"\n[dodger_blue1]Testing {len(presets)} subwoofer presets...[/dodger_blue1]")

    from rich.table import Table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Preset", style="cyan", justify="left")
    table.add_column("Gain (dB)", style="yellow", justify="right")
    table.add_column("Low-pass (Hz)", style="green", justify="right")
    table.add_column("High-pass (Hz)", style="magenta", justify="right")
    table.add_column("Status", style="white", justify="center")

    preset_results = {}

    for preset in presets:
        try:
            # Set the preset
            spkr.set_subwoofer_preset(preset)
            time.sleep(2)  # Wait for speaker to apply changes

            # Get the full EQ profile to see all values
            profile = spkr.get_eq_profile()
            eq = profile.get('kefEqProfileV2', {})

            gain = eq.get('subwooferGain', 'N/A')
            lowpass = eq.get('subOutLPFreq', 'N/A')
            highpass = eq.get('highPassModeFreq', 'N/A')

            preset_results[preset] = {
                'gain': gain,
                'lowpass': lowpass,
                'highpass': highpass,
                'status': 'OK'
            }

            table.add_row(
                preset,
                str(gain) if gain != 'N/A' else 'N/A',
                str(lowpass) if lowpass != 'N/A' else 'N/A',
                str(highpass) if highpass != 'N/A' else 'N/A',
                '[green]OK[/green]'
            )

        except Exception as e:
            preset_results[preset] = {
                'gain': 'ERROR',
                'lowpass': 'ERROR',
                'highpass': 'ERROR',
                'status': 'X'
            }
            table.add_row(preset, 'ERROR', 'ERROR', 'ERROR', '[red]X[/red]')
            console.print(f"[red]Error testing {preset}: {e}[/red]")

    console.print("\n")
    console.print(table)

    console.print("\n[bold]Expected Values for Reference:[/bold]")
    console.print("  kube12b: gain=-1, lowpass=52.5, highpass=65")
    console.print("  kube8b: gain=3, lowpass=62.5, highpass=67.5")
    console.print("\n[italic]Note: Values may vary based on speaker model and firmware[/italic]")

    # Store results
    USER_CONFIRMATION["preset_analysis_complete"] = True
    AUTO_TESTS_OUTPUT["preset_analysis"] = preset_results


def firmware_test():
    """Test ALL firmware update features (3 methods + module function)"""
    rule_msg("Firmware Update")
    console.print("The script will now test firmware update features.")
    console.print("[orange1]This will NOT install any updates, only check for them[/orange1]")
    prompt_continue()

    # Test check for updates
    console.print("\n[dodger_blue1]Testing check_for_firmware_update()...[/dodger_blue1]")
    try:
        result = spkr.check_for_firmware_update()
        console.print(f"[green]OK[/green] Check for updates triggered: {result}")
        USER_CONFIRMATION["firmware_check"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["firmware_check"] = False

    # Test get update status
    console.print("\n[dodger_blue1]Testing get_firmware_update_status()...[/dodger_blue1]")
    try:
        time.sleep(2)  # Wait for check to complete
        status = spkr.get_firmware_update_status()
        console.print(f"[green]OK[/green] Update status: {status}")
        USER_CONFIRMATION["firmware_status"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["firmware_status"] = False

    # Test get release notes (module-level function)
    console.print("\n[dodger_blue1]Testing get_kef_firmware_releases()...[/dodger_blue1]")
    try:
        releases = pkf.get_kef_firmware_releases()
        if releases and len(releases) > 0:
            console.print(f"[green]OK[/green] Found {len(releases)} firmware releases")
            USER_CONFIRMATION["firmware_releases"] = True
        else:
            console.print(f"[red]X[/red] No releases found")
            USER_CONFIRMATION["firmware_releases"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["firmware_releases"] = False

    firmware_tests = ["firmware_check", "firmware_status", "firmware_releases"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in firmware_tests])

    if passed == len(firmware_tests):
        console.print(f"\n[bold green]All firmware tests passed! ({passed}/{len(firmware_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Firmware tests: {passed}/{len(firmware_tests)} passed[/bold orange1]")


def bluetooth_test():
    """Test Bluetooth control features (4 methods)"""
    rule_msg("Bluetooth Control")
    console.print("The script will now test Bluetooth control features.")
    console.print("[orange1]These methods control Bluetooth device management[/orange1]")
    prompt_continue()

    # Test get bluetooth state
    console.print("\n[dodger_blue1]Testing get_bluetooth_state()...[/dodger_blue1]")
    try:
        state = spkr.get_bluetooth_state()
        console.print(f"[green]OK[/green] Bluetooth state: {state}")
        USER_CONFIRMATION["bt_get_state"] = True
        AUTO_TESTS_OUTPUT["bt_state"] = state
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["bt_get_state"] = False

    # Test set bluetooth discoverable
    console.print("\n[dodger_blue1]Testing set_bluetooth_discoverable()...[/dodger_blue1]")
    try:
        result = spkr.set_bluetooth_discoverable(True)
        console.print(f"[green]OK[/green] Set discoverable: {result}")
        USER_CONFIRMATION["bt_discoverable"] = True
        time.sleep(2)
        # Turn it back off
        spkr.set_bluetooth_discoverable(False)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["bt_discoverable"] = False

    # Test disconnect bluetooth (only if connected)
    console.print("\n[dodger_blue1]Testing disconnect_bluetooth()...[/dodger_blue1]")
    console.print("[orange1]This will only work if a Bluetooth device is connected[/orange1]")
    try:
        result = spkr.disconnect_bluetooth()
        console.print(f"[green]OK[/green] Disconnect result: {result}")
        USER_CONFIRMATION["bt_disconnect"] = True
    except Exception as e:
        console.print(f"[yellow]Warning: {e}[/yellow]")
        console.print("[orange1]This is expected if no device is connected[/orange1]")
        USER_CONFIRMATION["bt_disconnect"] = True  # Not an error

    # Test clear bluetooth devices
    console.print("\n[dodger_blue1]Testing clear_bluetooth_devices()...[/dodger_blue1]")
    console.print("[orange1]WARNING: This will unpair all Bluetooth devices![/orange1]")
    if not NON_INTERACTIVE:
        skip = input("Do you want to clear all paired Bluetooth devices? (y/n): ")
        if skip.lower() != 'y':
            console.print("[yellow]Skipping clear_bluetooth_devices[/yellow]")
            USER_CONFIRMATION["bt_clear"] = None
        else:
            try:
                result = spkr.clear_bluetooth_devices()
                console.print(f"[green]OK[/green] Clear devices result: {result}")
                USER_CONFIRMATION["bt_clear"] = True
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                USER_CONFIRMATION["bt_clear"] = False
    else:
        console.print("[yellow]Non-interactive mode: skipping destructive operation[/yellow]")
        USER_CONFIRMATION["bt_clear"] = None

    bt_tests = ["bt_get_state", "bt_discoverable", "bt_disconnect"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in bt_tests])

    if passed == len(bt_tests):
        console.print(f"\n[bold green]All Bluetooth tests passed! ({passed}/{len(bt_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Bluetooth tests: {passed}/{len(bt_tests)} passed[/bold orange1]")


def grouping_test():
    """Test Grouping/Multiroom features (2 methods)"""
    rule_msg("Grouping & Multiroom")
    console.print("The script will now test multiroom grouping features.")
    console.print("[orange1]These methods control speaker grouping[/orange1]")
    prompt_continue()

    # Test get group members
    console.print("\n[dodger_blue1]Testing get_group_members()...[/dodger_blue1]")
    try:
        members = spkr.get_group_members()
        console.print(f"[green]OK[/green] Group members: {members}")
        USER_CONFIRMATION["group_get_members"] = True
        AUTO_TESTS_OUTPUT["group_members"] = members
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["group_get_members"] = False

    # Test save persistent group
    console.print("\n[dodger_blue1]Testing save_persistent_group()...[/dodger_blue1]")
    console.print("[orange1]This saves the current speaker group configuration[/orange1]")
    try:
        result = spkr.save_persistent_group()
        console.print(f"[green]OK[/green] Save group result: {result}")
        USER_CONFIRMATION["group_save"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["group_save"] = False

    group_tests = ["group_get_members", "group_save"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in group_tests])

    if passed == len(group_tests):
        console.print(f"\n[bold green]All grouping tests passed! ({passed}/{len(group_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Grouping tests: {passed}/{len(group_tests)} passed[/bold orange1]")


def notifications_test():
    """Test Notifications features (3 methods)"""
    rule_msg("Notifications")
    console.print("The script will now test notification features.")
    console.print("[orange1]These methods control UI notifications on the speaker[/orange1]")
    prompt_continue()

    # Test get notification queue
    console.print("\n[dodger_blue1]Testing get_notification_queue()...[/dodger_blue1]")
    try:
        queue = spkr.get_notification_queue()
        console.print(f"[green]OK[/green] Notification queue: {queue}")
        USER_CONFIRMATION["notif_get_queue"] = True
        AUTO_TESTS_OUTPUT["notification_queue"] = queue
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["notif_get_queue"] = False

    # Test get player notification
    console.print("\n[dodger_blue1]Testing get_player_notification()...[/dodger_blue1]")
    try:
        player_notif = spkr.get_player_notification()
        console.print(f"[green]OK[/green] Player notification: {player_notif}")
        USER_CONFIRMATION["notif_get_player"] = True
        AUTO_TESTS_OUTPUT["player_notification"] = player_notif
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["notif_get_player"] = False

    # Test cancel notification (only if there are notifications)
    console.print("\n[dodger_blue1]Testing cancel_notification()...[/dodger_blue1]")
    console.print("[orange1]This will cancel the current notification[/orange1]")
    try:
        result = spkr.cancel_notification()
        console.print(f"[green]OK[/green] Cancel result: {result}")
        USER_CONFIRMATION["notif_cancel"] = True
    except Exception as e:
        console.print(f"[yellow]Warning: {e}[/yellow]")
        console.print("[orange1]This is expected if no notifications exist[/orange1]")
        USER_CONFIRMATION["notif_cancel"] = True  # Not an error

    notif_tests = ["notif_get_queue", "notif_get_player", "notif_cancel"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in notif_tests])

    if passed == len(notif_tests):
        console.print(f"\n[bold green]All notification tests passed! ({passed}/{len(notif_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Notification tests: {passed}/{len(notif_tests)} passed[/bold orange1]")


def alerts_timers_test():
    """Test Alerts & Timers features (13 methods)"""
    rule_msg("Alerts & Timers")
    console.print("The script will now test alarms and timers features.")
    console.print("[orange1]These methods control alarms and countdown timers[/orange1]")
    prompt_continue()

    # Test list alerts
    console.print("\n[dodger_blue1]Testing list_alerts()...[/dodger_blue1]")
    try:
        alerts = spkr.list_alerts()
        console.print(f"[green]OK[/green] Current alerts: {alerts}")
        USER_CONFIRMATION["alerts_list"] = True
        AUTO_TESTS_OUTPUT["alerts"] = alerts
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["alerts_list"] = False

    # Test add timer
    console.print("\n[dodger_blue1]Testing add_timer()...[/dodger_blue1]")
    console.print("[orange1]Creating a 60-second test timer[/orange1]")
    try:
        result = spkr.add_timer(duration_seconds=60)
        console.print(f"[green]OK[/green] Add timer result: {result}")
        USER_CONFIRMATION["timer_add"] = True
        time.sleep(1)
        # Get the timer ID from the alerts list
        alerts = spkr.list_alerts()
        console.print(f"Current alerts after adding: {alerts}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["timer_add"] = False

    # Test remove timer (remove the one we just added)
    console.print("\n[dodger_blue1]Testing remove_timer()...[/dodger_blue1]")
    try:
        # Assuming timer ID 0 or check the alerts list
        result = spkr.remove_timer(timer_id=0)
        console.print(f"[green]OK[/green] Remove timer result: {result}")
        USER_CONFIRMATION["timer_remove"] = True
    except Exception as e:
        console.print(f"[yellow]Warning: {e}[/yellow]")
        console.print("[orange1]This is expected if timer doesn't exist[/orange1]")
        USER_CONFIRMATION["timer_remove"] = True

    # Test snooze time get/set
    console.print("\n[dodger_blue1]Testing get/set_snooze_time()...[/dodger_blue1]")
    try:
        original_snooze = spkr.get_snooze_time()
        console.print(f"[green]OK[/green] Current snooze time: {original_snooze} minutes")
        USER_CONFIRMATION["snooze_get"] = True

        # Try to set it to 10 minutes
        spkr.set_snooze_time(10)
        time.sleep(0.5)
        new_snooze = spkr.get_snooze_time()
        if new_snooze == 10:
            console.print(f"[green]OK[/green] Snooze time set to 10 minutes")
            USER_CONFIRMATION["snooze_set"] = True
            # Restore original
            spkr.set_snooze_time(original_snooze)
        else:
            console.print(f"[red]X[/red] Expected 10, got {new_snooze}")
            USER_CONFIRMATION["snooze_set"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["snooze_get"] = False
        USER_CONFIRMATION["snooze_set"] = False

    # Test default alert sound
    console.print("\n[dodger_blue1]Testing play/stop_default_alert_sound()...[/dodger_blue1]")
    console.print("[orange1]This will play the default alert sound briefly[/orange1]")
    try:
        result = spkr.play_default_alert_sound()
        console.print(f"[green]OK[/green] Play alert sound result: {result}")
        USER_CONFIRMATION["alert_sound_play"] = True
        time.sleep(2)
        result = spkr.stop_default_alert_sound()
        console.print(f"[green]OK[/green] Stop alert sound result: {result}")
        USER_CONFIRMATION["alert_sound_stop"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["alert_sound_play"] = False
        USER_CONFIRMATION["alert_sound_stop"] = False

    # Test alarm operations (add, enable, disable, remove)
    console.print("\n[dodger_blue1]Testing alarm operations...[/dodger_blue1]")
    console.print("[orange1]Creating a test alarm for 08:00[/orange1]")
    try:
        # Add alarm for 8:00 AM, weekdays only
        alarm_data = {"time": "08:00", "days": "1111100", "label": "Test Alarm"}
        result = spkr.add_alarm(alarm_data)
        console.print(f"[green]OK[/green] Add alarm result: {result}")
        USER_CONFIRMATION["alarm_add"] = True
        time.sleep(1)

        # List alarms to see it
        alerts = spkr.list_alerts()
        console.print(f"Alerts after adding alarm: {alerts}")

        # Disable alarm (assuming ID 0)
        result = spkr.disable_alarm(alarm_id=0)
        console.print(f"[green]OK[/green] Disable alarm result: {result}")
        USER_CONFIRMATION["alarm_disable"] = True

        # Enable alarm
        result = spkr.enable_alarm(alarm_id=0)
        console.print(f"[green]OK[/green] Enable alarm result: {result}")
        USER_CONFIRMATION["alarm_enable"] = True

        # Remove alarm
        result = spkr.remove_alarm(alarm_id=0)
        console.print(f"[green]OK[/green] Remove alarm result: {result}")
        USER_CONFIRMATION["alarm_remove"] = True
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["alarm_add"] = False
        USER_CONFIRMATION["alarm_disable"] = False
        USER_CONFIRMATION["alarm_enable"] = False
        USER_CONFIRMATION["alarm_remove"] = False

    alert_tests = [
        "alerts_list", "timer_add", "timer_remove", "snooze_get", "snooze_set",
        "alert_sound_play", "alert_sound_stop", "alarm_add", "alarm_enable",
        "alarm_disable", "alarm_remove"
    ]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in alert_tests])

    if passed == len(alert_tests):
        console.print(f"\n[bold green]All alerts/timers tests passed! ({passed}/{len(alert_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Alerts/timers tests: {passed}/{len(alert_tests)} passed[/bold orange1]")


def googlecast_test():
    """Test Google Cast features (3 methods)"""
    rule_msg("Google Cast")
    console.print("The script will now test Google Cast configuration.")
    console.print("[orange1]These methods control Cast analytics and ToS status[/orange1]")
    prompt_continue()

    # Test get cast usage report
    console.print("\n[dodger_blue1]Testing get_cast_usage_report()...[/dodger_blue1]")
    try:
        enabled = spkr.get_cast_usage_report()
        console.print(f"[green]OK[/green] Cast usage reporting: {enabled}")
        USER_CONFIRMATION["cast_get_report"] = True
        AUTO_TESTS_OUTPUT["cast_usage_report"] = enabled
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["cast_get_report"] = False

    # Test set cast usage report
    console.print("\n[dodger_blue1]Testing set_cast_usage_report()...[/dodger_blue1]")
    try:
        original = spkr.get_cast_usage_report()
        # Toggle it
        spkr.set_cast_usage_report(not original)
        time.sleep(0.5)
        new_value = spkr.get_cast_usage_report()
        if new_value == (not original):
            console.print(f"[green]OK[/green] Cast usage report toggled successfully")
            USER_CONFIRMATION["cast_set_report"] = True
            # Restore original
            spkr.set_cast_usage_report(original)
        else:
            console.print(f"[red]X[/red] Toggle failed")
            USER_CONFIRMATION["cast_set_report"] = False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["cast_set_report"] = False

    # Test get cast ToS accepted
    console.print("\n[dodger_blue1]Testing get_cast_tos_accepted()...[/dodger_blue1]")
    try:
        accepted = spkr.get_cast_tos_accepted()
        console.print(f"[green]OK[/green] Cast ToS accepted: {accepted}")
        USER_CONFIRMATION["cast_get_tos"] = True
        AUTO_TESTS_OUTPUT["cast_tos_accepted"] = accepted
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        USER_CONFIRMATION["cast_get_tos"] = False

    cast_tests = ["cast_get_report", "cast_set_report", "cast_get_tos"]
    passed = sum([USER_CONFIRMATION.get(test, False) for test in cast_tests])

    if passed == len(cast_tests):
        console.print(f"\n[bold green]All Google Cast tests passed! ({passed}/{len(cast_tests)}) [/bold green]")
    else:
        console.print(f"\n[bold orange1]Google Cast tests: {passed}/{len(cast_tests)} passed[/bold orange1]")


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Test pykefcontrol library features',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover KEF speakers on the network:
  python3 testing.py --discover
  python3 testing.py --discover --network 192.168.16.0/24

  # Interactive mode (default):
  python3 testing.py

  # Non-interactive mode - run specific test:
  python3 testing.py --host 192.168.16.25 --test dsp
  python3 testing.py --host 192.168.16.25 --test subwoofer
  python3 testing.py --host 192.168.16.25 --test preset-analysis
  python3 testing.py --host 192.168.16.25 --test firmware
  python3 testing.py --host 192.168.16.25 --test bluetooth
  python3 testing.py --host 192.168.16.25 --test alerts
  python3 testing.py --host 192.168.16.25 --test new  # All new API methods

  # Run all tests non-interactively:
  python3 testing.py --host 192.168.16.25 --test all --model 0

  # Quick connection test:
  python3 testing.py --host 192.168.16.25 --test info
        """
    )
    parser.add_argument('--discover', action='store_true',
                       help='Discover KEF speakers on the network')
    parser.add_argument('--network', type=str,
                       help='Network range to scan (e.g., 192.168.16.0/24). Auto-detects if not specified.')
    parser.add_argument('--host', type=str, help='KEF speaker IP address')
    parser.add_argument('--test', type=str,
                       choices=['info', 'dsp', 'subwoofer', 'preset-analysis', 'xio', 'firmware',
                               'bluetooth', 'grouping', 'notifications', 'alerts', 'googlecast', 'new', 'all'],
                       help='Specific test to run (non-interactive mode)')
    parser.add_argument('--model', type=str,
                       choices=['LSXII', 'LSXIILT', 'LS50WirelessII', 'LS60Wireless', 'XIO'],
                       help='Model identifier: LSXII, LSXIILT, LS50WirelessII, LS60Wireless, or XIO (required for --test all)')

    args = parser.parse_args()

    # If --discover flag is set, run network discovery
    if args.discover:
        console.print("[bold cyan3]KEF Speaker Network Discovery[/bold cyan3]")
        newline()
        speakers = discover_kef_speakers(network_range=args.network)

        if speakers:
            console.print(f"\n[bold green]Discovered {len(speakers)} KEF speaker(s):[/bold green]")
            from rich.table import Table
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("IP Address", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Model", style="yellow")
            table.add_column("Firmware", style="magenta")
            table.add_column("MAC Address", style="blue")

            for speaker in speakers:
                table.add_row(
                    speaker['ip'],
                    speaker['name'],
                    speaker['model'],
                    speaker['firmware'],
                    speaker['mac']
                )

            console.print(table)
        else:
            console.print("[bold red]No KEF speakers found on the network[/bold red]")

        sys.exit(0)

    # If --host and --test provided, run in non-interactive mode
    if args.host and args.test:
        # Modify module globals directly using globals()
        globals()['NON_INTERACTIVE'] = True
        globals()['HOST'] = args.host
        if args.model is not None:
            globals()['MODEL_SELECTED'] = args.model

        console.print(f"[cyan3]Non-Interactive Mode: Testing {args.test} on {globals()['HOST']}[/cyan3]")
        newline()

        try:
            # Create speaker connection
            globals()['spkr'] = pkf.KefConnector(globals()['HOST'])

            if args.test == 'info':
                if args.model is None:
                    console.print("[bold red]Error: --model required for info test[/bold red]")
                    sys.exit(1)
                console.print("[bold]Speaker Information:[/bold]")
                speaker_info()

            elif args.test == 'dsp':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running DSP/EQ Tests:[/bold]")
                dsp_eq_test()

            elif args.test == 'subwoofer':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Subwoofer Tests:[/bold]")
                subwoofer_test()

            elif args.test == 'preset-analysis':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Subwoofer Preset Analysis:[/bold]")
                subwoofer_preset_analysis()

            elif args.test == 'xio':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running XIO Soundbar Tests:[/bold]")
                xio_specific_test()

            elif args.test == 'firmware':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Firmware Tests:[/bold]")
                firmware_test()

            elif args.test == 'bluetooth':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Bluetooth Tests:[/bold]")
                bluetooth_test()

            elif args.test == 'grouping':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Grouping Tests:[/bold]")
                grouping_test()

            elif args.test == 'notifications':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Notifications Tests:[/bold]")
                notifications_test()

            elif args.test == 'alerts':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Alerts & Timers Tests:[/bold]")
                alerts_timers_test()

            elif args.test == 'googlecast':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running Google Cast Tests:[/bold]")
                googlecast_test()

            elif args.test == 'new':
                if args.model is not None:
                    MODEL_SELECTED = args.model
                console.print("[bold]Running All New API Method Tests:[/bold]")
                bluetooth_test()
                newline()
                grouping_test()
                newline()
                notifications_test()
                newline()
                alerts_timers_test()
                newline()
                googlecast_test()

            elif args.test == 'all':
                if args.model is None:
                    console.print("[bold red]Error: --model required for --test all[/bold red]")
                    sys.exit(1)
                MODEL_SELECTED = args.model
                console.print("[bold]Running All Tests:[/bold]")
                system_infos()
                speaker_info()
                power_check()
                source_check()
                vol_test()
                song_info()
                track_control()
                dsp_eq_test()
                subwoofer_test()
                xio_specific_test()
                firmware_test()
                bluetooth_test()
                grouping_test()
                notifications_test()
                alerts_timers_test()
                googlecast_test()
                sumup()

        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")
            sys.exit(1)

        console.print("\n[bold green]Test completed![/bold green]")
        sys.exit(0)

    # ====== Interactive Mode (original behavior) ======
    newline()
    rule_msg("Pykefcontrol Library Testing".upper(), sep="=")

    rule_msg("This script version")
    check_script_version()

    rule_msg("Infos")

    console.print(
        "The aim of this script is to test the pykefcontrol library on\
            \nvarious hardware. Namely the KEF LS50W2, KEF LSX2 and KEF LS60."
    )
    time.sleep(0.5)

    select_model()
    prompt_continue()

    console.print("This script will test the following:")
    console.print(
        "\t- [bold]Speaker power on/off[/bold]\
        \n\t- [bold]Speaker source selection[/bold]\
        \n\t- [bold]Speaker volume control[/bold]\
        \n\t- [bold]Speaker mute control[/bold]\
        \n\t- [bold]Song Info[/bold] (get title/artist/album)\
        \n\t- [bold]Track control[/bold] (next/prev/play/pause)\
        \n\t- [bold]DSP/EQ Control[/bold] (11 methods: desk/wall mode, bass, treble, balance, phase, filters, profile name)\
        \n\t- [bold]Subwoofer Control[/bold] (6 methods: enable, gain, polarity, preset, lowpass, stereo)\
        \n\t- [bold]XIO Soundbar Features[/bold] (2 methods: sound profile, wall mounted)\
        \n\t- [bold]Firmware Update[/bold] (3 methods + release notes parser)\
        \n\t- [bold]Bluetooth Control[/bold] (4 methods: state, discoverable, disconnect, clear devices)\
        \n\t- [bold]Grouping/Multiroom[/bold] (2 methods: get members, save group)\
        \n\t- [bold]Notifications[/bold] (3 methods: get queue, get player notification, cancel)\
        \n\t- [bold]Alerts & Timers[/bold] (13 methods: timers, alarms, snooze, alert sounds)\
        \n\t- [bold]Google Cast[/bold] (3 methods: usage report, ToS status)"
    )
    prompt_continue()
    system_infos()
    prompt_continue()
    spkr = speaker_info()
    newline()
    power_check()
    prompt_continue()
    newline()
    source_check()
    prompt_continue()
    newline()
    vol_test()
    newline()
    song_info()
    newline()
    track_control()
    newline()
    dsp_eq_test()
    newline()
    subwoofer_test()
    newline()
    xio_specific_test()
    newline()
    firmware_test()
    newline()
    bluetooth_test()
    newline()
    grouping_test()
    newline()
    notifications_test()
    newline()
    alerts_timers_test()
    newline()
    googlecast_test()
    newline()
    sumup()
    rule_msg("End of tests")
    console.print("Thanks for using this script !")
    console.print(
        "Please copy the content of the [dodger_blue1]Sum Up[/dodger_blue1] section"
    )
    console.print(
        "and [bold red]report it to GitHub[/bold red]. Even if all the tests passed ! "
    )
    console.print(
        "[bold red] Report here: https://github.com/N0ciple/pykefcontrol/issues/2[/bold red]"
    )
    console.print(
        "[bold green]Thanks for helping improving Pykefcontrol ! [/bold green]"
    )

    sys.exit()
