"""The real address of the person making a request (spec 13.1, 13.4; HIMS-SEC-014).

Anyone can send an X-Forwarded-For header, so it is believed only when the request arrived from
one of our own proxies (HIMS_TRUSTED_PROXIES, e.g. the load balancer's network). Each proxy adds
the address it saw to the right-hand end, so we walk from the right, skip our own proxies and stop
at the first address that is not ours. Everything further left was written by the sender.

Audit records, the sign-in register, rate limits, the console lock-out and the console's address
allow-list (HIMS-SEC-015) all use this function.
"""

import ipaddress
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=8)
def _networks(entries: tuple[str, ...]) -> tuple:
    return tuple(ipaddress.ip_network(entry.strip(), strict=False) for entry in entries)


def _parse(value: str):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    return getattr(address, "ipv4_mapped", None) or address


def _is_trusted(address, networks: tuple) -> bool:
    return any(address in network for network in networks)


def validate_trusted_proxies(entries: list[str]) -> None:
    """Raises ValueError for an entry that is not an address or network."""
    _networks(tuple(entries))


def validate_console_networks(entries: list[str]) -> None:
    """Raises ValueError for an entry that is not an address or network, or that lets every
    address in (HIMS_ADMIN_ALLOWED_NETWORKS, HIMS-SEC-015)."""
    for network in _networks(tuple(entries)):
        if network.prefixlen == 0:
            raise ValueError(f"{network} would let every address in")


def console_allows(address: str | None) -> bool:
    """True when the admin console may answer this address (HIMS-SEC-015).

    The address must be in HIMS_ADMIN_ALLOWED_NETWORKS. One of our own proxies is never enough:
    client_ip() returns a proxy only when it could not find the real sender.
    """
    parsed = _parse(address) if address else None
    if parsed is None:
        return False
    if _is_trusted(parsed, _networks(tuple(settings.HIMS_TRUSTED_PROXIES))):
        return False
    return _is_trusted(parsed, _networks(tuple(settings.HIMS_ADMIN_ALLOWED_NETWORKS)))


def client_ip(request) -> str | None:
    remote = request.META.get("REMOTE_ADDR") or None
    networks = _networks(tuple(settings.HIMS_TRUSTED_PROXIES))
    remote_address = _parse(remote) if remote else None
    if remote_address is None or not _is_trusted(remote_address, networks):
        return remote
    for hop in reversed(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        address = _parse(hop)
        if address is None:
            return remote  # our proxy would not write this, so it cannot be relied on
        if not _is_trusted(address, networks):
            return str(address)
    return remote
