"""Pure helpers for validating URLs against an explicit trusted-host policy.

The functions in this module deliberately do not read environment variables, perform
network I/O, or contain provider-specific policy.  Callers own the list of trusted
hosts and can use these helpers before making any outbound request.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit


DEFAULT_HTTPS_PORT = 443


class TrustedUrlError(ValueError):
    """Raised when a URL cannot satisfy a trusted HTTPS endpoint policy."""


def normalize_trusted_hosts(hosts: Iterable[str]) -> frozenset[str]:
    """Normalize an explicit host allowlist and reject ambiguous host entries.

    Hosts, rather than URL prefixes or suffix wildcards, are accepted intentionally:
    a policy must opt in to each network destination exactly.
    """

    normalized = frozenset(_normalize_host(host) for host in hosts)
    if not normalized:
        raise TrustedUrlError("At least one trusted host is required.")
    return normalized


def validate_trusted_https_url(
    value: str,
    *,
    trusted_hosts: Iterable[str],
    allow_query: bool = True,
    allow_fragment: bool = False,
    allowed_ports: Iterable[int] = (DEFAULT_HTTPS_PORT,),
) -> str:
    """Return a normalized HTTPS URL only when its host is explicitly trusted.

    Direct IP destinations, user-info URL forms, non-standard ports, fragments, and
    untrusted hosts are refused.  Query strings remain optional because signed
    download URLs commonly need them.
    """

    if not isinstance(value, str) or not value:
        raise TrustedUrlError("Trusted URL must be a non-empty string.")
    if _contains_unsafe_url_character(value):
        raise TrustedUrlError("Trusted URL contains unsafe control, whitespace, or backslash characters.")

    allowed_hosts = normalize_trusted_hosts(trusted_hosts)
    normalized_ports = _normalize_allowed_ports(allowed_ports)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise TrustedUrlError(f"Malformed trusted URL: {value!r}") from error

    if parsed.scheme.lower() != "https":
        raise TrustedUrlError("Trusted URL must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise TrustedUrlError("Trusted URL must not include user information.")
    if not parsed.hostname:
        raise TrustedUrlError("Trusted URL must include a hostname.")
    host = _normalize_host(parsed.hostname)
    if host not in allowed_hosts:
        raise TrustedUrlError(f"URL host is not trusted: {host}")
    if port is not None and port not in normalized_ports:
        raise TrustedUrlError(f"URL port is not trusted: {port}")
    if not allow_query and parsed.query:
        raise TrustedUrlError("Trusted URL must not include a query string.")
    if not allow_fragment and parsed.fragment:
        raise TrustedUrlError("Trusted URL must not include a fragment.")

    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def resolve_trusted_redirect_url(
    current_url: str,
    location: str,
    *,
    trusted_hosts: Iterable[str],
    allowed_ports: Iterable[int] = (DEFAULT_HTTPS_PORT,),
) -> str:
    """Resolve a redirect and validate its final target before following it."""

    if not isinstance(location, str) or not location:
        raise TrustedUrlError("Redirect response did not include a Location URL.")
    if _contains_unsafe_url_character(location):
        raise TrustedUrlError(
            "Redirect Location contains unsafe control, whitespace, or backslash characters."
        )
    return validate_trusted_https_url(
        urljoin(current_url, location),
        trusted_hosts=trusted_hosts,
        allowed_ports=allowed_ports,
    )


def same_url_origin(left: str, right: str) -> bool:
    """Compare URL origins without making network requests.

    This is useful for dropping credentials on a trusted cross-origin redirect.
    The caller should validate both URLs against its policy first.
    """

    return _origin(left) == _origin(right)


def _contains_unsafe_url_character(value: str) -> bool:
    return any(
        character == "\\" or ord(character) <= 0x20 or ord(character) == 0x7F
        for character in value
    )


def _origin(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise TrustedUrlError(f"Malformed URL: {value!r}") from error
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise TrustedUrlError("Origin comparison requires an absolute HTTPS URL.")
    return ("https", _normalize_host(parsed.hostname), port or DEFAULT_HTTPS_PORT)


def _normalize_allowed_ports(ports: Iterable[int]) -> frozenset[int]:
    normalized: set[int] = set()
    for port in ports:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise TrustedUrlError("Trusted URL ports must be integers in the range 1..65535.")
        normalized.add(port)
    if not normalized:
        raise TrustedUrlError("At least one trusted URL port is required.")
    return frozenset(normalized)


def _normalize_host(value: str) -> str:
    if not isinstance(value, str):
        raise TrustedUrlError("Trusted host must be a string.")
    raw = value.strip().rstrip(".").lower()
    if not raw:
        raise TrustedUrlError("Trusted host is invalid.")
    if any(character.isspace() for character in raw) or any(
        character in raw for character in ":/@?#[]\\"
    ):
        raise TrustedUrlError("Trusted host must be a hostname, not a URL or address literal.")
    try:
        host = raw.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise TrustedUrlError("Trusted host cannot be normalized with IDNA.") from error
    _validate_dns_hostname(host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TrustedUrlError("Trusted host must not be a direct IP address.")
    if _looks_like_noncanonical_ip(host):
        raise TrustedUrlError("Trusted host must not be a numeric IP address form.")
    return host


def _validate_dns_hostname(host: str) -> None:
    if len(host) > 253:
        raise TrustedUrlError("Trusted host is too long.")
    labels = host.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or any(not (character.isascii() and (character.isalnum() or character == "-")) for character in label)
        for label in labels
    ):
        raise TrustedUrlError("Trusted host is not a valid DNS hostname.")


def _looks_like_noncanonical_ip(host: str) -> bool:
    labels = host.split(".")
    return bool(labels) and all(
        label.isdigit()
        or (label.startswith("0x") and len(label) > 2 and all(
            character in "0123456789abcdef" for character in label[2:]
        ))
        for label in labels
    )
