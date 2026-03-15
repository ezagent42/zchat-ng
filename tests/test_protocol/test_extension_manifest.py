"""Tests for ExtensionManifest TOML parsing."""

from zchat_protocol.extension_manifest import ExtensionManifest


def test_extension_manifest_basic():
    """ExtensionManifest parses basic fields from TOML."""
    toml_str = '''
    name = "my-ext"
    version = "1.0.0"
    description = "A test extension"
    requires_core = ">=0.0.6"
    '''
    m = ExtensionManifest.from_toml(toml_str)
    assert m.name == "my-ext"
    assert m.version == "1.0.0"
    assert m.description == "A test extension"
    assert m.requires_core == ">=0.0.6"


def test_extension_manifest_with_hooks_and_indexes():
    """ExtensionManifest parses hooks and indexes from TOML."""
    toml_str = '''
    name = "rich-ext"
    version = "2.0.0"

    content_types = ["ext.rich-text", "ext.card"]

    [[hooks]]
    trigger = "on_msg"
    handler = "rich_handler"
    runtime = "python"

    [[indexes]]
    pattern = "room:*:rich"
    queryable = true
    '''
    m = ExtensionManifest.from_toml(toml_str)
    assert m.name == "rich-ext"
    assert m.content_types == ["ext.rich-text", "ext.card"]
    assert len(m.hooks) == 1
    assert m.hooks[0].trigger == "on_msg"
    assert len(m.indexes) == 1
    assert m.indexes[0].pattern == "room:*:rich"
    assert m.indexes[0].queryable is True
