"""TLS configuration for the speaker's secure API (HTTPS, port 4430).

Recent firmware serves a certificate issued by a private KEF root CA (embedded in
the official app, and below). The official app trusts *only* that CA, and checks
that the speaker's IP address is listed in the certificate's subjectAltName.

Building an :class:`ssl.SSLContext` loads certificates, which Home Assistant flags
as blocking I/O in the event loop. The async client therefore builds it in an
executor; :func:`create_ssl_context` can also be called by the application (in an
executor) and the result passed to the client.
"""

from __future__ import annotations

import ipaddress
import ssl
from functools import cache
from typing import Final

#: KEF private root CA (``C=HK, O=KEF, CN=KEF-CA``, valid 2025-04-16 → 2045-04-11,
#: SHA-256 fingerprint:
#: E5:F2:CE:C7:92:26:CC:3E:3C:88:24:38:74:7B:4F:BD:AE:89:33:86:BD:40:DA:7F:1C:13:FC:7D:7C:B1:E4:5B).
KEF_ROOT_CA_PEM: Final = """\
-----BEGIN CERTIFICATE-----
MIIDiTCCAnGgAwIBAgIUPdcMVcifwg5uyfe947k0f9j84wswDQYJKoZIhvcNAQEL
BQAwVDELMAkGA1UEBhMCSEsxEjAQBgNVBAgMCUhvbmcgS29uZzESMBAGA1UEBwwJ
SG9uZyBLb25nMQwwCgYDVQQKDANLRUYxDzANBgNVBAMMBktFRi1DQTAeFw0yNTA0
MTYxMTIxMjRaFw00NTA0MTExMTIxMjRaMFQxCzAJBgNVBAYTAkhLMRIwEAYDVQQI
DAlIb25nIEtvbmcxEjAQBgNVBAcMCUhvbmcgS29uZzEMMAoGA1UECgwDS0VGMQ8w
DQYDVQQDDAZLRUYtQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCv
W6BZZo6/yXIKnW/MjfH98poFgqeU1LD2OuSotMJ7wK6Zs3gvrQwNxBhjLYyxnY8x
TkWndjn2ZO9f4MNs+KfJKQAGs9bnBmOyR86iPIoGKQeVlbxvMqijR107Qm6/Nc5q
NuzpwvVQP4Y8fHSLlLckUjwPQXJVDp8jXzC42Ksc1QdFXU5RB3WW4ZJ2/An6dlEQ
X63e1YbroXf8PNCsJCtL8cTM4L4tOVGX7fkSbd1evIT5ov6Y64NW2Vfn8GoLMxtN
voFI03SqnZtyQFse1e/qz4zEPg4st8R4mHLvAElVRgIXFoRr8GgghlpKs2dwgGPQ
yaQp5GxyDxhE7OmCJeuhAgMBAAGjUzBRMB0GA1UdDgQWBBR04vp9Ece9c2/Ozmhc
PtBNFZR7AjAfBgNVHSMEGDAWgBR04vp9Ece9c2/OzmhcPtBNFZR7AjAPBgNVHRMB
Af8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAl//C1SiRnENWzAY5tr2GxS9pS
lf4HeizrJQ5jKB/8Vmk1dxJJsX0OGHAgOJC73mHppi2nxOkwf5q5sYZwPVMXD4os
L0D4qzIB175CyGMaW2GqUkevlUdjjjA9CGZEinRrL1Qic97nGVUA8icqHmJVV2Dp
syjh2wkNhoInk8acLeWzPGTNhoywLFNTXdPaxzjHFgqYFcf4p72QLb7u+3l17OS1
gjd3nDle9sS+8jXgaPudOZg16DbgXUMF6R1oI+Gi2VueBjEz2zq598uSTX4VbEuN
Ej0PUhU5xbB2eTeE+jqBlizhVwkeKyFAm5/7tXA3PH9xLY1rM7kJb7phrvir
-----END CERTIFICATE-----
"""


def is_ip_address(host: str) -> bool:
    """Whether ``host`` is an IPv4/IPv6 literal (brackets allowed)."""
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def create_ssl_context(
    *, verify: bool = True, check_hostname: bool = True, ca_pem: str = KEF_ROOT_CA_PEM
) -> ssl.SSLContext:
    """Build an SSL context for the speaker's secure API (blocking: loads a CA).

    :param verify: verify the certificate chain against the KEF root CA. ``False``
        disables all verification (troubleshooting only).
    :param check_hostname: also require the host (an IP address) to be listed in
        the certificate. Must be ``False`` when connecting with a host *name*,
        because speaker certificates only carry IP addresses; the chain is still
        verified against the KEF CA.
    :param ca_pem: root CA(s) to trust (tests use their own).

    ``ssl.SSLContext`` is used directly instead of ``create_default_context`` so
    that no public CA is trusted and ``VERIFY_X509_STRICT`` (Python ≥ 3.13
    default) is not enabled.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    ctx.load_verify_locations(cadata=ca_pem)
    ctx.check_hostname = check_hostname
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


@cache
def default_ssl_context(*, verify: bool, check_hostname: bool) -> ssl.SSLContext:
    """Process-wide cached context with the KEF CA (blocking on first call)."""
    return create_ssl_context(verify=verify, check_hostname=check_hostname)
