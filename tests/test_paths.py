from __future__ import annotations

import re

from pykefcontrol import paths

ALL = {k: v for k, v in vars(paths).items() if k.isupper() and isinstance(v, str)}


def test_names_are_upper_snake() -> None:
    for name in ALL:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", name), name


def test_known_paths() -> None:
    assert paths.PHYSICAL_SOURCE == "settings:/kef/play/physicalSource"
    assert paths.HOME == "ui:"
    assert paths.KW2B_CHECK_FOR_UPDATES == "kef:ble/checkForUpdates"
    assert paths.WEBSERVER_ADD_USER == "webserver:addUser"
    assert paths.VERIFY_KEY_RESULT == "kef:verifyKey/result"
    assert paths.PLAYLIST_ROOT == "playlists:pl/root"
    assert paths.PLAY_QUEUE == "playlists:pq/getitems"


def test_duplicates_kept() -> None:
    assert paths.DEVICE_ID == paths.MEMBER_ID == "settings:/system/memberId"


def test_count_and_format() -> None:
    assert len(ALL) >= 200
    for value in ALL.values():
        assert ":" in value
