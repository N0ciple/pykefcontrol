"""Command line interface: ``pykefcontrol <command> ...`` (or ``python -m pykefcontrol``).

Run ``pykefcontrol --help`` for the list of commands. ``pykefcontrol diag <ip>``
produces a report that helps validate a speaker model / firmware: please attach
it to bug reports.
"""

from __future__ import annotations

import argparse
import json
import logging
import ssl
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from . import KefClient, Source, __version__, _protocol, _tls, const, paths
from ._auth import Credentials, add_user_payload, sign
from ._sync.backend import SyncBackend
from .exceptions import KefError
from .models import Subscription
from .values import ValueType, encode

# --- output helpers -----------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items() if k != "raw"}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _print(obj: Any) -> None:
    if isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(_jsonable(obj), indent=2, ensure_ascii=False, default=str))


def _client(args: argparse.Namespace) -> KefClient:
    return KefClient(args.host, transport=args.transport, verify_ssl=not args.no_verify)


# --- commands -----------------------------------------------------------------------


def cmd_discover(args: argparse.Namespace) -> int:
    from .discovery import discover_blocking

    speakers = discover_blocking(args.timeout)
    if not speakers:
        print("No speaker found.", file=sys.stderr)
        return 1
    for s in speakers:
        version = s.firmware or "?"
        print(
            f"{s.host:<16} {s.name or '?':<24} {s.marketing_name:<18} fw {version}  {s.mac_address}"
        )
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        info = speaker.get_device_info()
        caps = speaker.get_capabilities()
        _print(
            {
                "device": info,
                "transport": "https" if speaker.is_secure else "http",
                "sources": caps.sources,
                "network": speaker.get_network_info(),
            }
        )
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        _print(speaker.get_state())
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        try:
            for state in speaker.watch(track_position=args.position):
                if state is None:
                    print("-- speaker unavailable, reconnecting --")
                    continue
                track = state.track
                title = f"{track.artist or '?'} - {track.title or '?'}" if track else "-"
                print(
                    f"{state.status} source={state.source} vol={state.volume} "
                    f"muted={state.muted} {state.playback_state} {title} pos={state.position_ms}"
                )
        except KeyboardInterrupt:
            pass
    return 0


def cmd_volume(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        if args.value is not None:
            speaker.set_volume(args.value)
        print(speaker.get_volume())
    return 0


def cmd_mute(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        if args.state is not None:
            speaker.set_mute(args.state == "on")
        print("on" if speaker.get_mute() else "off")
    return 0


def cmd_source(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        if args.value is not None:
            speaker.set_source(args.value)
        print(speaker.get_source())
    return 0


def cmd_power(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        if args.state == "on":
            speaker.power_on(Source(args.source) if args.source else None)
        elif args.state == "off":
            speaker.power_off()
        print(speaker.get_status())
    return 0


def _simple(action: Callable[[KefClient], Any]) -> Callable[[argparse.Namespace], int]:
    def run(args: argparse.Namespace) -> int:
        with _client(args) as speaker:
            action(speaker)
        return 0

    return run


def cmd_eq(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        _print({"version": speaker.get_eq_version(), "profile": speaker.get_eq_profile()})
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        _print(speaker.get_data(args.path, args.roles))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    value = json.loads(args.value)
    with _client(args) as speaker:
        _print(speaker.set_value(args.path, args.type, value))
    return 0


def cmd_rows(args: argparse.Namespace) -> int:
    with _client(args) as speaker:
        _print(speaker.get_rows(args.path, args.start, args.end))
    return 0


# --- diagnostics --------------------------------------------------------------------


class _Diag:
    """Low-level probes, independent of the client's own transport choice."""

    IDENTITY = (
        paths.MODEL_NAME,
        paths.FIRMWARE_TEXT,
        paths.DEVICE_VERSION,
        paths.FIRMWARE_VERSION,
        paths.HARDWARE_VERSION,
        paths.SERIAL_NUMBER,
        paths.SPEAKER_STATUS,
        paths.PHYSICAL_SOURCE,
    )

    def __init__(self, host: str, write: bool) -> None:
        self.host = host
        self.write = write
        self.backend = SyncBackend()
        self.creds = Credentials.default()
        self.report: dict[str, Any] = {"pykefcontrol": __version__, "host": host}
        self.http = f"http://{host}"
        self.https = f"https://{host}:{const.HTTPS_PORT}"
        self.verified = _tls.create_ssl_context(check_hostname=_tls.is_ip_address(host))

    def send(
        self,
        base: str,
        request: _protocol.Request,
        ctx: ssl.SSLContext | None = None,
        auth: bool = False,
    ) -> tuple[int, Any]:
        headers = {"Content-Type": const.JSON_CONTENT_TYPE} if request.body is not None else {}
        if auth:
            headers["Authorization"] = sign(self.creds, base + request.target, request.body)
        resp = self.backend.send(
            request.method,
            base + request.target,
            body=request.body,
            headers=headers,
            ssl_context=ctx,
            timeout=request.timeout or 5.0,
        )
        try:
            body: Any = _protocol.loads(resp.body)
        except KefError:
            body = resp.body[:300].decode("utf-8", "replace")
        return resp.status, body

    def attempt(self, label: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run one probe, recording its result (or the error) under ``label``."""
        try:
            result = func(*args, **kwargs)
        except Exception as err:  # diagnostics: record everything
            result = f"ERROR {type(err).__name__}: {err}"
        self.report[label] = result
        return result

    def peer_certificate(self) -> dict[str, Any]:
        import socket

        with (
            socket.create_connection((self.host, const.HTTPS_PORT), timeout=5) as sock,
            self.verified.wrap_socket(sock, server_hostname=self.host) as tls,
        ):
            cert = tls.getpeercert() or {}
            return {
                "subject": cert.get("subject"),
                "issuer": cert.get("issuer"),
                "subjectAltName": cert.get("subjectAltName"),
                "notAfter": cert.get("notAfter"),
                "tls_version": tls.version(),
            }

    def run(self) -> dict[str, Any]:
        probe = _protocol.get_data(const.PROBE_PATH)
        http_ok = not isinstance(self.attempt("http_80", self.send, self.http, probe), str)
        https = self.attempt("https_4430_verified", self.send, self.https, probe, self.verified)
        https_ok = not isinstance(https, str)
        if https_ok:
            self.attempt("https_certificate", self.peer_certificate)
        else:
            unverified = _tls.create_ssl_context(verify=False)
            self.attempt("https_4430_unverified", self.send, self.https, probe, unverified)
        bases: list[tuple[str, ssl.SSLContext | None, str]] = []
        if https_ok:
            bases.append((self.https, self.verified, "https"))
        if http_ok:
            bases.append((self.http, None, "http"))
        if not bases:
            self.report["conclusion"] = "speaker unreachable on HTTP:80 and HTTPS:4430"
            return self.report
        base, ctx, _ = bases[0]
        for path in (*self.IDENTITY, paths.EQ_PROFILE_V2, paths.EQ_PROFILE):
            self.attempt(f"get {path}", self.send, base, _protocol.get_data(path), ctx)
        subscribe = _protocol.modify_queue([Subscription(paths.VOLUME)])
        queue = self.attempt("modifyQueue", self.send, base, subscribe, ctx, ctx is not None)
        if isinstance(queue, tuple) and isinstance(queue[1], str):
            self.attempt("pollQueue", self.send, base, _protocol.poll_queue(queue[1], 1), ctx)
        if self.write:
            for base, ctx, name in bases:
                self.write_tests(base, ctx, name)
        return self.report

    def write_tests(self, base: str, ctx: ssl.SSLContext | None, name: str) -> None:
        """Re-write the current volume (no audible change) in several ways."""
        status, body = self.send(base, _protocol.get_data(paths.VOLUME), ctx)
        if status != 200:
            self.report[f"write {name}"] = f"cannot read volume: {status} {body}"
            return
        current = _protocol.parse_get_data(body)
        volume = current.get("i32_") if isinstance(current, dict) else None
        if not isinstance(volume, int):
            self.report[f"write {name}"] = f"unexpected volume value: {current!r}"
            return
        value = encode(ValueType.I32, volume)
        with_role = _protocol.set_data(paths.VOLUME, value)
        with_roles = _protocol.Request(
            "POST",
            const.ENDPOINT_SET_DATA,
            body=_protocol.dumps({"path": paths.VOLUME, "roles": "value", "value": value}),
        )
        secure = ctx is not None
        if secure:
            add_user = _protocol.Request(
                "POST", const.ENDPOINT_SET_DATA, body=_protocol.dumps(add_user_payload(self.creds))
            )
            self.attempt(f"write {name} provision", self.send, base, add_user, ctx)
            self.attempt(f"write {name} unsigned (role)", self.send, base, with_role, ctx)
        self.attempt(f"write {name} role", self.send, base, with_role, ctx, secure)
        self.attempt(f"write {name} roles", self.send, base, with_roles, ctx, secure)


def cmd_diag(args: argparse.Namespace) -> int:
    report = _Diag(args.host, args.write).run()
    _print(report)
    return 0


# --- parser -------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pykefcontrol", description="Control KEF W2 speakers.")
    parser.add_argument("--version", action="version", version=f"pykefcontrol {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func: Callable[[argparse.Namespace], int], help_: str) -> Any:
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        if name != "discover":
            p.add_argument("host", help="speaker IP address")
            p.add_argument(
                "--transport", choices=[m.value for m in const.TransportMode], default="auto"
            )
            p.add_argument("--no-verify", action="store_true", help="skip TLS verification")
        return p

    add("discover", cmd_discover, "find speakers (needs the [discovery] extra)").add_argument(
        "--timeout", type=float, default=3.0
    )
    add("info", cmd_info, "device information")
    add("state", cmd_state, "current state")
    add("watch", cmd_watch, "follow changes live").add_argument(
        "--position", action="store_true", help="also follow the play position"
    )
    add("volume", cmd_volume, "get or set the volume").add_argument("value", nargs="?", type=int)
    add("mute", cmd_mute, "get or set mute").add_argument("state", nargs="?", choices=["on", "off"])
    add("source", cmd_source, "get or set the source").add_argument(
        "value", nargs="?", choices=[s.value for s in Source]
    )
    power = add("power", cmd_power, "power on / standby")
    power.add_argument("state", nargs="?", choices=["on", "off"])
    power.add_argument("--source", choices=[s.value for s in Source if s != Source.STANDBY])
    add("play", _simple(lambda s: s.play()), "resume playback")
    add("pause", _simple(lambda s: s.pause()), "pause playback")
    add("next", _simple(lambda s: s.next_track()), "next track")
    add("previous", _simple(lambda s: s.previous_track()), "previous track")
    add("eq", cmd_eq, "show the EQ profile")
    get = add("get", cmd_get, "raw getData")
    get.add_argument("path")
    get.add_argument("--roles", default="value")
    set_ = add("set", cmd_set, "raw setData of a typed value")
    set_.add_argument("path")
    set_.add_argument("type", help="value type, e.g. i32_, bool_, string_, kefPhysicalSource")
    set_.add_argument("value", help="JSON value, e.g. 30, true, '\"wifi\"'")
    rows = add("rows", cmd_rows, "raw getRows")
    rows.add_argument("path")
    rows.add_argument("--start", type=int, default=0)
    rows.add_argument("--end", type=int, default=19)
    add("diag", cmd_diag, "diagnostic report for bug reports").add_argument(
        "--write",
        action="store_true",
        help="also test writes (re-writes the current volume; no audible change)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    try:
        result: int = args.func(args)
    except KefError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return result


if __name__ == "__main__":
    sys.exit(main())
