"""Tests for content type mapping, AcpPayload, TextContent, SystemEvent, SpawnConfig."""

import pytest
from zchat_protocol.content_type import short_to_mime, mime_to_short
from zchat_protocol.content_types.acp import AcpPayload
from zchat_protocol.content_types.text import TextContent
from zchat_protocol.content_types.system_event import SystemEvent
from zchat_protocol.content_types.spawn_config import SpawnConfig
from zchat_protocol.identity import Identity


# --- AcpPayload roundtrip ---

def test_acp_request_roundtrip():
    """AcpPayload request serializes and deserializes."""
    req = AcpPayload.request(method="tools/list", params={"cursor": None}, id="1")
    d = req.to_dict()
    assert d["jsonrpc"] == "2.0"
    assert d["method"] == "tools/list"
    restored = AcpPayload.from_dict(d)
    assert restored.method == "tools/list"
    assert restored.id == "1"


def test_acp_response_roundtrip():
    """AcpPayload response serializes and deserializes."""
    resp = AcpPayload.response(result={"tools": []}, id="1")
    d = resp.to_dict()
    assert "result" in d
    assert d["id"] == "1"
    restored = AcpPayload.from_dict(d)
    assert restored.result == {"tools": []}


def test_acp_json_roundtrip():
    """AcpPayload JSON string roundtrip."""
    req = AcpPayload.request(method="ping", id="2")
    json_str = req.to_json()
    restored = AcpPayload.from_json(json_str)
    assert restored.method == "ping"
    assert restored.id == "2"


# --- AcpPayload error ---

def test_acp_error_creation():
    """AcpPayload.error creates valid error response."""
    err = AcpPayload.error(code=-32600, message="Invalid Request", id="3")
    d = err.to_dict()
    assert d["error"]["code"] == -32600
    assert d["error"]["message"] == "Invalid Request"


def test_acp_error_no_result():
    """Error payloads have no result field."""
    err = AcpPayload.error(code=-32601, message="Method not found", id="4")
    d = err.to_dict()
    assert "result" not in d


# --- Content type mapping ---

def test_mime_passthrough():
    """Standard MIME types pass through unchanged."""
    assert short_to_mime("text/plain") == "text/plain"
    assert mime_to_short("text/plain") == "text/plain"


def test_zchat_custom_short_to_mime():
    """ZChat custom short names map to vnd.zchat namespace."""
    assert short_to_mime("spawn-config") == "application/vnd.zchat.spawn-config"


def test_zchat_custom_mime_to_short():
    """vnd.zchat MIME maps back to short name."""
    assert mime_to_short("application/vnd.zchat.spawn-config") == "spawn-config"


def test_ext_short_to_mime():
    """ext.* short names map to vnd.zchat-ext namespace."""
    assert short_to_mime("ext.my-plugin") == "application/vnd.zchat-ext.my-plugin"


def test_acp_session_prompt_mapping():
    """ACP namespace with 3+ segments: last dot becomes hyphen in MIME."""
    assert short_to_mime("acp.session.prompt") == "application/vnd.zchat.acp.session-prompt"
    assert mime_to_short("application/vnd.zchat.acp.session-prompt") == "acp.session.prompt"


# --- TextContent ---

def test_text_content():
    """TextContent holds text and has correct CONTENT_TYPE."""
    tc = TextContent(text="hello")
    assert tc.text == "hello"
    assert tc.CONTENT_TYPE == "text/plain"


# --- SystemEvent ---

def test_system_event_valid():
    """SystemEvent with valid event_type constructs correctly."""
    subj = Identity.parse("alice@onesyn")
    ev = SystemEvent(event_type="join", subject=subj, detail="joined room")
    assert ev.event_type == "join"
    assert ev.subject == subj
    assert ev.detail == "joined room"


def test_system_event_invalid_type():
    """SystemEvent rejects unknown event_type."""
    subj = Identity.parse("alice@onesyn")
    with pytest.raises(ValueError):
        SystemEvent(event_type="explode", subject=subj)


# --- SpawnConfig ---

def test_spawn_config_from_toml():
    """SpawnConfig parses a TOML string."""
    toml_str = '''
    name = "test-agent"
    model = "claude-3"
    system_prompt = "You are helpful."

    [skills]
    enabled = ["search", "code"]
    '''
    cfg = SpawnConfig.from_toml(toml_str)
    assert cfg.name == "test-agent"
    assert cfg.model == "claude-3"
    assert cfg.system_prompt == "You are helpful."
    assert cfg.skills == ["search", "code"]
