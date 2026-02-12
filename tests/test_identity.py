"""Tests for holons.identity — HOLON.md parser."""

from holons.identity import parse_holon


def test_parse_holon(tmp_path):
    holon_md = tmp_path / "HOLON.md"
    holon_md.write_text(
        '---\n'
        'uuid: "abc-123"\n'
        'given_name: "test-holon"\n'
        'family_name: "Test"\n'
        'motto: "A test holon."\n'
        'composer: "Tester"\n'
        'clade: "deterministic/pure"\n'
        'status: draft\n'
        'born: "2026-01-01"\n'
        'lang: "python"\n'
        'parents: []\n'
        'reproduction: "manual"\n'
        'generated_by: "sophia-who"\n'
        'proto_status: draft\n'
        '---\n'
        '# test-holon\n'
    )

    identity = parse_holon(holon_md)
    assert identity.uuid == "abc-123"
    assert identity.given_name == "test-holon"
    assert identity.family_name == "Test"
    assert identity.motto == "A test holon."
    assert identity.clade == "deterministic/pure"
    assert identity.lang == "python"


def test_parse_holon_missing_fields(tmp_path):
    holon_md = tmp_path / "HOLON.md"
    holon_md.write_text(
        '---\n'
        'uuid: "minimal"\n'
        '---\n'
        '# Minimal\n'
    )

    identity = parse_holon(holon_md)
    assert identity.uuid == "minimal"
    assert identity.given_name == ""


def test_parse_holon_missing_frontmatter(tmp_path):
    holon_md = tmp_path / "HOLON.md"
    holon_md.write_text("# No frontmatter\n")

    try:
        parse_holon(holon_md)
        assert False, "should have raised"
    except ValueError as e:
        assert "frontmatter" in str(e)
