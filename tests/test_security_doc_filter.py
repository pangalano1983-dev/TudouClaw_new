"""app.security — leak detection with documentation-example filter.

Covers the new behavior added by the doc-example markers (RFC 2606 +
common placeholders), plus regression coverage for the underlying
scan_for_leaks / detect_env_value_leaks / full_leak_check API.

Goal: real leaks still trip; doc placeholders don't.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from app.security import (
    scan_for_leaks,
    detect_env_value_leaks,
    full_leak_check,
)


# ── real leaks must still trip ────────────────────────────────────────


@pytest.mark.parametrize("leak,expected_type", [
    ("API key sk-" + "A" * 48,                       "api_key"),
    ("Got sk-ant-" + "B" * 40 + " yesterday",        "api_key"),
    ("AKIA" + "C" * 16,                              "aws_key"),
    ("token ghp_" + "x" * 36,                        "github"),
    ("github_pat_" + "y" * 22 + "abc",               "github"),
    ("xoxb-" + "z" * 12,                             "slack"),
    ("Authorization: Bearer " + "y" * 40,            "bearer"),
    ("ssh deploy@10.0.0.5",                          "ssh_target"),
    ("ssh ops@server.acme.com",                      "ssh_target"),
    ("Server is at 192.168.1.1:8080",                "internal_ip"),
    ("from /Users/realname/secret.txt",              "local_path"),
    ("password=correct-horse-battery-staple",        "password"),
])
def test_real_leak_still_trips(leak, expected_type):
    out = scan_for_leaks(leak)
    assert out["found"], f"missed leak: {leak!r}"
    types = [l["type"] for l in out["leaks"]]
    assert expected_type in types, (
        f"expected type {expected_type} in {types} for {leak!r}"
    )


# ── doc-example markers must NOT trip ────────────────────────────────


@pytest.mark.parametrize("doc_text", [
    "Contact alice@example.com for help",
    "Configure user@example.org as admin",
    "Default placeholder yourname@example.net works",
    "connect to admin@localhost for testing",
    "login as your_username@host.com",
    "use {your_email}@something for placeholder",
    "see <your-email>@host for the real address",
    "deploy to user@host.example for staging",
    "tools support .test domains like x@my.test",
    "use *.invalid for examples per RFC 2606",
])
def test_doc_examples_do_not_trip(doc_text):
    out = scan_for_leaks(doc_text)
    leak_values = [l["value"] for l in out["leaks"]]
    assert not out["found"], (
        f"false positive on doc text {doc_text!r}: {leak_values}"
    )


def test_doc_marker_does_not_swallow_real_leak_in_same_text():
    """A doc placeholder appearing alongside a real leak must NOT mask it."""
    text = (
        "Contact alice@example.com for help. Real key: sk-" + "A" * 48
    )
    out = scan_for_leaks(text)
    assert out["found"]
    types = [l["type"] for l in out["leaks"]]
    assert "api_key" in types
    # And the example email must NOT be present
    values = [l["value"] for l in out["leaks"]]
    assert not any("alice@example.com" in v for v in values)


# ── full_leak_check combines pattern + env-value scan ────────────────


def test_full_leak_check_finds_pattern_leaks():
    out = full_leak_check("text with sk-" + "Z" * 48)
    assert out["found"]
    assert any(l["type"] == "api_key" for l in out["leaks"])


def test_full_leak_check_finds_env_value_leaks(monkeypatch):
    # Inject a fake env var with a non-trivial value, then check that
    # putting the value in content trips env_value_leak.
    monkeypatch.setenv("FAKE_PROD_TOKEN", "supersecret_random_value_42")
    out = full_leak_check(
        "config snippet: token=supersecret_random_value_42 in prod"
    )
    assert out["found"]
    types = [l["type"] for l in out["leaks"]]
    assert "env_value_leak" in types


def test_full_leak_check_skips_universal_env_keys(monkeypatch):
    """PATH / HOME / SHELL etc. should never count as a leak even if their
    values appear in content (they'd be too noisy)."""
    monkeypatch.setenv("PATH", "/usr/bin:/usr/local/bin:/some/special/path")
    out = full_leak_check("PATH includes /usr/bin:/usr/local/bin:/some/special/path now")
    types = [l.get("type") for l in out.get("leaks", [])]
    assert "env_value_leak" not in types or all(
        l.get("env_key") != "PATH" for l in out["leaks"]
    )


# ── empty / non-string inputs are safe ───────────────────────────────


@pytest.mark.parametrize("inp", [None, "", 0, [], {}])
def test_scan_handles_empty_or_nonstring(inp):
    out = scan_for_leaks(inp)
    assert out == {"found": False, "leaks": []}
