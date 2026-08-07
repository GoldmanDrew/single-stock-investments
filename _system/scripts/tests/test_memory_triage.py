"""Tests for the [PROPOSED] promotion queue builder.

Daily logs tag proposals two ways — as a heading and as an inline bullet — and a
bullet is often nested under a differently-tagged heading. Attributing bullets to
the enclosing heading filed company facts under MEMORY and made the queue
unreviewable lens by lens.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_memory_triage as triage  # noqa: E402


def _daily(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_heading_block_captures_following_bullets(tmp_path):
    path = _daily(tmp_path, "2026-08-05.md", """## [PROPOSED MUNGER]

- Inversion: ask what would make this fail first.
""")
    items = triage.parse_file(path)
    assert len(items) == 1
    assert items[0]["lens"] == "MUNGER"
    assert items[0]["day"] == "2026-08-05"


def test_inline_bullet_keeps_its_own_lens_inside_another_block(tmp_path):
    """The defect: a COMPANY bullet nested under a MEMORY heading was filed
    as MEMORY."""
    path = _daily(tmp_path, "2026-08-04.md", """## [PROPOSED MEMORY]

- [PROPOSED COMPANY] WHK: IPO'd 2026-06-10 at $26.00/share.
- [PROPOSED PABRAI] Downside bounded by franchise cash, not price.
""")
    lenses = sorted(i["lens"] for i in triage.parse_file(path))
    assert lenses == ["COMPANY", "PABRAI"], lenses


def test_untagged_heading_closes_a_block(tmp_path):
    path = _daily(tmp_path, "2026-08-03.md", """## [PROPOSED STAHL]

- Croupier economics take a toll without operating risk.

## CMI — contract backfill

- **Reason:** unrelated narrative that must not join the proposal.
""")
    items = triage.parse_file(path)
    assert len(items) == 1
    assert "toll" in items[0]["body"][0]
    assert not any("unrelated" in line for line in items[0]["body"])


def test_untagged_proposal_falls_back_to_generic(tmp_path):
    path = _daily(tmp_path, "2026-08-02.md", "- [PROPOSED] context only; do not promote.\n")
    items = triage.parse_file(path)
    assert items[0]["lens"] == "GENERIC"


def test_empty_blocks_are_dropped(tmp_path):
    path = _daily(tmp_path, "2026-08-01.md", "## [PROPOSED MUNGER]\n\n## Something else\n")
    assert triage.parse_file(path) == []


def test_duplicates_collapse_and_record_every_sighting():
    items = [
        {"lens": "PABRAI", "title": "", "day": "2026-08-01", "file": "a.md",
         "body": ["Same belief, restated."]},
        {"lens": "PABRAI", "title": "", "day": "2026-08-02", "file": "b.md",
         "body": ["Same belief, restated."]},
    ]
    deduped, dropped = triage.dedupe(items)
    assert len(deduped) == 1 and dropped == 1
    assert deduped[0]["also_seen"] == ["2026-08-02"]


def test_different_lenses_are_not_deduped_together():
    items = [
        {"lens": "PABRAI", "title": "", "day": "d", "file": "a.md", "body": ["Same text."]},
        {"lens": "MUNGER", "title": "", "day": "d", "file": "a.md", "body": ["Same text."]},
    ]
    deduped, dropped = triage.dedupe(items)
    assert len(deduped) == 2 and dropped == 0


def test_rendered_queue_promotes_nothing_and_says_so():
    items, _ = triage.dedupe([{"lens": "MUNGER", "title": "", "day": "2026-08-01",
                               "file": "a.md", "body": ["Invert."]}])
    text = triage.render(items, 0, None)
    assert "- [ ]" in text, "items must be unticked"
    assert "Only a human promotes" in text
