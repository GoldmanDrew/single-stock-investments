from pathlib import Path

from _system.scripts.validate_portfolio_private_boundary import validate


def test_clean_public_bundle_passes(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("public research", encoding="utf-8")
    assert validate(tmp_path) == []


def test_private_payload_and_account_identifier_fail(tmp_path: Path) -> None:
    private = tmp_path / "data" / "sleeves_drew.json"
    private.parent.mkdir()
    private.write_text('{"account":"DU1234567"}', encoding="utf-8")
    failures = validate(tmp_path)
    assert any("forbidden private artifact" in row for row in failures)
    assert any("broker account identifier" in row for row in failures)


def test_configured_live_identifier_is_rejected_without_broad_u_prefix_false_positives(tmp_path: Path) -> None:
    (tmp_path / "safe.json").write_text('{"research":"U123456 is not necessarily an account"}', encoding="utf-8")
    assert validate(tmp_path) == []
    assert any("configured private identifier" in row for row in validate(tmp_path, ("U123456",)))
