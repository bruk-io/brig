"""E2E gateway test for `infra/proxy/program.py`'s reading of the host's own addresses
(TASK-0001.36): the decision refuses a name that resolves to one (decision-0009 item 4), and the
proxy reads them from `/proc/net`. The parse against recorded text, then against this host."""

from pathlib import Path

from brig.infra.proxy import program

_IF_INET6 = """\
00000000000000000000000000000001 01 80 10 80       lo
20010db8000000000000000000000042 02 40 00 00     eth0
garbage
"""

_FIB_TRIE = """\
Main:
  +-- 0.0.0.0/0 3 0 5
     |-- 0.0.0.0
        /0 universe UNICAST
     +-- 127.0.0.0/8 2 0 2
        +-- 127.0.0.0/31 1 0 0
           |-- 127.0.0.0
              /8 host LOCAL
           |-- 127.0.0.1
              /32 host LOCAL
     |-- 203.0.113.7
        /32 host LOCAL
     |-- 203.0.113.255
        /32 link BROADCAST
Local:
     |-- 203.0.113.7
        /32 host LOCAL
"""


def test_local_addresses_reads_each_interface_and_local_address_once() -> None:
    assert program.local_addresses(_IF_INET6, _FIB_TRIE) == (
        "::1",
        "2001:db8::42",
        "127.0.0.1",
        "203.0.113.7",
    )


def test_local_addresses_of_this_host_include_its_loopback() -> None:
    """`/proc/net/if_inet6` is absent on a host without IPv6 (this one, measured), which the
    proxy reads as no IPv6 address; `/proc/net/fib_trie` is always there with IPv4."""
    if_inet6 = Path("/proc/net/if_inet6")
    found = program.local_addresses(
        if_inet6.read_text() if if_inet6.exists() else "", Path("/proc/net/fib_trie").read_text()
    )

    assert "127.0.0.1" in found
