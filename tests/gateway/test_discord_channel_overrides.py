"""Tests for Discord per-channel system prompt overrides."""

import pytest

# Reuse fixtures and helpers from the free-response test module so we get
# the same discord-mock bootstrap and Fake* channel classes.
from tests.gateway.test_discord_free_response import (  # noqa: F401
    _ensure_discord_mock,
    FakeDMChannel,
    FakeTextChannel,
    FakeThread,
    FakeForumChannel,
    adapter,
    make_message,
)

from gateway.platforms import discord as discord_platform


@pytest.mark.asyncio
async def test_channel_override_applied_to_text_channel(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    monkeypatch.setenv("DISCORD_AUTO_THREAD", "false")
    adapter._channel_overrides = {"123": {"extra_system_prompt": "FOOD_PROMPT"}}

    message = make_message(channel=FakeTextChannel(channel_id=123), content="hi")
    await adapter._handle_message(message)

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.extra_system_prompt == "FOOD_PROMPT"


@pytest.mark.asyncio
async def test_channel_override_not_applied_when_no_match(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    monkeypatch.setenv("DISCORD_AUTO_THREAD", "false")
    adapter._channel_overrides = {"123": {"extra_system_prompt": "FOOD_PROMPT"}}

    message = make_message(channel=FakeTextChannel(channel_id=999), content="hi")
    await adapter._handle_message(message)

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.extra_system_prompt is None


@pytest.mark.asyncio
async def test_channel_override_thread_inherits_parent(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    monkeypatch.setenv("DISCORD_AUTO_THREAD", "false")
    adapter._channel_overrides = {"123": {"extra_system_prompt": "PARENT_PROMPT"}}

    parent = FakeTextChannel(channel_id=123, name="food")
    thread = FakeThread(channel_id=456, name="dinner planning", parent=parent)
    message = make_message(channel=thread, content="hi from thread")
    await adapter._handle_message(message)

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.extra_system_prompt == "PARENT_PROMPT"


@pytest.mark.asyncio
async def test_channel_override_dm_channel(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    adapter._channel_overrides = {"789": {"extra_system_prompt": "DM_PROMPT"}}

    # Matching DM
    message = make_message(channel=FakeDMChannel(channel_id=789), content="hi dm")
    await adapter._handle_message(message)

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.extra_system_prompt == "DM_PROMPT"

    # Non-matching DM resets to None
    adapter.handle_message.reset_mock()
    message2 = make_message(channel=FakeDMChannel(channel_id=111), content="other")
    await adapter._handle_message(message2)
    adapter.handle_message.assert_awaited_once()
    event2 = adapter.handle_message.await_args.args[0]
    assert event2.extra_system_prompt is None


@pytest.mark.asyncio
async def test_channel_override_malformed_value_skipped(adapter, monkeypatch):
    """A malformed override value must not raise inside _handle_message."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    monkeypatch.setenv("DISCORD_AUTO_THREAD", "false")
    # Bypass the loader by stuffing a bad value directly — _resolve_channel_override
    # must defend against this so a stale in-memory state can't crash dispatch.
    adapter._channel_overrides = {"123": "not a dict"}

    message = make_message(channel=FakeTextChannel(channel_id=123), content="hi")
    await adapter._handle_message(message)  # must not raise

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.extra_system_prompt is None


def test_load_channel_overrides_normalizes_keys(adapter, monkeypatch):
    """Loader should normalise int channel-id keys to strings."""
    fake_cfg = {
        "discord": {
            "channel_overrides": {
                123: {"extra_system_prompt": "x"},
                "456": {"extra_system_prompt": "y"},
            }
        }
    }

    import gateway.run as gateway_run
    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: fake_cfg)

    adapter._load_channel_overrides()
    assert adapter._channel_overrides == {
        "123": {"extra_system_prompt": "x"},
        "456": {"extra_system_prompt": "y"},
    }


def test_load_channel_overrides_skips_non_dict_values(adapter, monkeypatch):
    """Loader should drop non-dict override values with a warning, not raise."""
    fake_cfg = {
        "discord": {
            "channel_overrides": {
                "123": "not a dict",
                "456": None,
                "789": {"extra_system_prompt": "ok"},
            }
        }
    }

    import gateway.run as gateway_run
    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: fake_cfg)

    adapter._load_channel_overrides()
    assert adapter._channel_overrides == {"789": {"extra_system_prompt": "ok"}}


def test_load_channel_overrides_handles_missing_section(adapter, monkeypatch):
    import gateway.run as gateway_run
    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {})
    adapter._load_channel_overrides()
    assert adapter._channel_overrides == {}
