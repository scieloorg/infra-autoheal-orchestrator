from __future__ import annotations

from app.rules.router import _normalize_instance


def test_normalize_instance_strips_single_host_port():
    assert _normalize_instance("db-node-01.example.local:9104") == "db-node-01.example.local"


def test_normalize_instance_strips_bracketed_ipv6_port():
    assert _normalize_instance("[2001:db8::1]:9104") == "2001:db8::1"


def test_normalize_instance_keeps_unbracketed_ipv6():
    assert _normalize_instance("2001:db8::1") == "2001:db8::1"
