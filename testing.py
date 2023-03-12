# script_version=2
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
except Exception as e:
    print("Error:", e, style="red")
    print("Please install the required packages with `pip install -r testing_reqs.txt`")
    sys.exit()

# %%
console = Console()
AUTO_TESTS_OUTPUT = {}
USER_CONFIRMATION = {}
DEBUG = False
MODEL_SELECTED = -1
MODEL_LIST = ["LSX 2", "LS50 Wireless 2", "LS60"]
MODEL_SOURCES = {
    # LSX 2
    0: ["wifi", "bluetooth", "tv", "optical", "analog", "usb"],
    # LS50 Wireless 2
    1: ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
    # LS60
    2: ["wifi", "bluetooth", "tv", "optical", "coaxial", "analog"],
}


def select_model():
    global MODEL_SELECTED
    newline()
    console.print("[dodger_blue1]Select your speaker model:[/dodger_blue1]")
    console.print("[bold]1[/bold] KEF LSX 2")
    console.print("[bold]2[/bold] KEF LS50 Wireless 2")
    console.print("[bold]3[/bold] KEF LS60")

    try:
        MODEL_SELECTED = (
            int(input("Enter the number of your speaker model (1/2/3): ")) - 1
        )
    except:
        MODEL_SELECTED = -1
    while MODEL_SELECTED not in [0, 1, 2]:
        console.print("\tPlease enter 1, 2 or 3: ", end="")
        MODEL_SELECTED = int(input()) - 1
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


def check_script_version():
    try:
        with console.status("Checking if this script is up to date..."):
            with requests.get(
                "https://raw.githubusercontent.com/N0ciple/pykefcontrol/main/testing.py"
            ) as response:
                output = response.text
        version = output.split("# script_version=")[1].split("\n")[0]
        if version == "1":
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

    input("Press enter to continue...")


def prompt_continue():
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
                "Verify that your speaker is plugged in 🔌 and connected to the network."
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
        console.print("[bold green]All power tests passed ! 🎉[/bold green]")


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
        console.print("[bold green]All source tests passed ! 🎉[/bold green]")


def sumup():

    rule_msg("Sum Up")
    console.print("[bold]Speaker version:[/bold]")
    console.print(f"\t[dodger_blue1]{MODEL_LIST[MODEL_SELECTED]}[/dodger_blue1]")
    console.print("[bold]Working features:[/bold]")
    for feature in USER_CONFIRMATION:
        if USER_CONFIRMATION[feature]:
            console.print(f"\t[green]✓[/green] {feature}")
    console.print("[bold]Non working features:[/bold]")
    for feature in USER_CONFIRMATION:
        if not USER_CONFIRMATION[feature]:
            console.print(f"\t[red]✗[/red] {feature}")


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
        console.print("[bold green]All volume tests passed ! 🎉[/bold green]")


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
        "[bold red]the song should be playing via Chormecast, Airplay, Spotify Connect or DLNA.[/bold red]"
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
        console.print("[bold green]All song info tests passed ! 🎉[/bold green]")


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
        console.print("[bold green]All track control tests passed ! 🎉[/bold green]")


if __name__ == "__main__":
    # ====== Check testing utility version ======
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
        \n\t- [bold]Track control[/bold] (next/prev/play/pause)"
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
    sumup()
    rule_msg("End of tests")
    console.print("Thanks for using this script !")
    console.print(
        "Please copy the content of the [dodger_blue1]Sum Up[/dodger_blue1] section"
    )
    console.print(
        "and [bold red]report it to GitHub[/bold red]. Even if all the tests passed ! 👌"
    )
    console.print(
        "[bold red] Report here: https://github.com/N0ciple/pykefcontrol/issues/2[/bold red]"
    )
    console.print(
        "[bold green]Thanks for helping improving Pykefcontrol ! 🤗[/bold green]"
    )

sys.exit()
