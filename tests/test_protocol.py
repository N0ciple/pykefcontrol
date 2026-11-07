"""Tests for the sans-I/O protocol layer (pykefcontrol._protocol)."""

from __future__ import annotations

import json

import pytest

from pykefcontrol import KefProtocolError, Subscription, SubscriptionType, const
from pykefcontrol import _protocol as p
from pykefcontrol.enums import EventType
from pykefcontrol.models import Event


def test_get_data_request() -> None:
    req = p.get_data("player:volume")
    assert (req.method, req.endpoint, req.body) == ("GET", "/api/getData", None)
    assert req.params == (("path", "player:volume"), ("roles", "value"))
    assert req.target == "/api/getData?path=player%3Avolume&roles=value"


def test_set_data_uses_role_key_and_compact_json() -> None:
    req = p.set_data("player:volume", {"type": "i32_", "i32_": 5})
    assert req.method == "POST"
    assert req.body == b'{"path":"player:volume","role":"value","value":{"type":"i32_","i32_":5}}'
    assert req.target == "/api/setData"
    assert b"roles" not in req.body


def test_dumps_keeps_unicode() -> None:
    assert p.dumps({"a": "é"}) == '{"a":"é"}'.encode()


def test_activate_default_value_is_empty_object() -> None:
    req = p.activate("powermanager:goReboot")
    assert json.loads(req.body or b"") == {
        "path": "powermanager:goReboot",
        "role": "activate",
        "value": {},
    }
    assert json.loads(p.activate("x", {"control": "pause"}).body or b"")["value"] == {
        "control": "pause"
    }


def test_get_rows_params() -> None:
    req = p.get_rows("kef:dsp/editValue", 2, 10)
    assert req.params == (
        ("path", "kef:dsp/editValue"),
        ("roles", "@all"),
        ("from", "2"),
        ("to", "10"),
    )
    assert req.endpoint == "/api/getRows"


@pytest.mark.parametrize(("start", "end"), [(-1, 3), (5, 4)])
def test_get_rows_invalid_range(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="row range"):
        p.get_rows("x", start, end)


def test_modify_queue_queue_id_only_when_set() -> None:
    sub = Subscription("player:volume")
    old = Subscription("a", SubscriptionType.ITEM)
    new = json.loads(p.modify_queue([sub]).body or b"")
    assert new == {
        "subscribe": [{"path": "player:volume", "type": "itemWithValue"}],
        "unsubscribe": [],
    }
    again = json.loads(p.modify_queue([sub], [old], "{abc}").body or b"")
    assert again["queueId"] == "{abc}"
    assert again["unsubscribe"] == [{"path": "a", "type": "item"}]
    assert next(iter(again)) == "queueId"


def test_poll_queue_timeout_margin() -> None:
    req = p.poll_queue("{q}", 7)
    assert req.params == (("queueId", "{q}"), ("timeout", "7"))
    assert req.timeout == 7 + const.POLL_HTTP_MARGIN
    assert p.poll_queue("{q}").params[1] == ("timeout", str(const.POLL_TIMEOUT))
    with pytest.raises(ValueError, match="timeout"):
        p.poll_queue("{q}", -1)


def test_loads() -> None:
    assert p.loads(b"") is None
    assert p.loads(b"  \n") is None
    assert p.loads(b'[{"a":1}]') == [{"a": 1}]
    with pytest.raises(KefProtocolError):
        p.loads(b"<html>")


def test_parse_get_data() -> None:
    assert p.parse_get_data([{"type": "i32_", "i32_": 1}]) == {"type": "i32_", "i32_": 1}
    assert p.parse_get_data({"a": 1}) == {"a": 1}
    for bad in ([], "x", None, 3):
        with pytest.raises(KefProtocolError):
            p.parse_get_data(bad, "path")


def test_parse_rows() -> None:
    assert p.parse_rows({"rows": []}) == {"rows": []}
    with pytest.raises(KefProtocolError):
        p.parse_rows([])


def test_parse_queue_id() -> None:
    assert p.parse_queue_id("{abc}") == "{abc}"
    for bad in ("", None, 3, ["x"]):
        with pytest.raises(KefProtocolError):
            p.parse_queue_id(bad)


def test_parse_events() -> None:
    assert p.parse_events(None) == []
    assert p.parse_events([]) == []
    events = p.parse_events([{"path": "a", "itemType": "update"}, "junk", 3])
    assert [e.path for e in events] == ["a"]
    with pytest.raises(KefProtocolError):
        p.parse_events({"path": "a"})


def test_latest_per_path_keeps_last_and_orders_by_last_occurrence() -> None:
    def ev(path: str, n: int) -> Event:
        return Event(path, EventType.UPDATE, n, True)

    out = p.latest_per_path([ev("a", 1), ev("b", 2), ev("a", 3), ev("c", 4)])
    assert [(e.path, e.value) for e in out] == [("b", 2), ("a", 3), ("c", 4)]
    assert p.latest_per_path([]) == []


def test_error_message_extraction() -> None:
    body = (
        b'{"error":{"name":"CMAbstractWorker::invalidPath",'
        b'"message":"Node at path \'kef:eqProfile\' does not exist","title":"Error"}}'
    )
    assert p.error_message(body) == (
        "Node at path 'kef:eqProfile' does not exist (CMAbstractWorker::invalidPath)"
    )
    assert p.error_message(b'{"error":{"message":"boom"}}') == "boom"
    assert p.error_message(b"plain text\n") == "plain text"
    assert p.error_message(b'{"other":1}') == '{"other":1}'
    assert p.error_message(b"") == ""
