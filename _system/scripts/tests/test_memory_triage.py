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


# --------------------------------------------------------------------------- #
# decision ledger — the queue must not re-surface work already decided
# --------------------------------------------------------------------------- #

def _item(lens="MUNGER", body=("Invert before you underwrite.",), day="2026-08-01"):
    return {"lens": lens, "title": "", "day": day, "file": f"{day}.md",
            "body": list(body), "also_seen": []}


def test_fingerprint_survives_the_same_belief_reproposed_on_a_later_day():
    assert triage.fingerprint(_item(day="2026-08-01")) == \
        triage.fingerprint(_item(day="2026-09-14"))


def test_fingerprint_separates_lenses_like_dedupe_does():
    assert triage.fingerprint(_item(lens="MUNGER")) != triage.fingerprint(_item(lens="STAHL"))


def test_rendered_row_carries_its_id_so_decisions_can_be_recorded():
    item = _item()
    assert triage.fingerprint(item) in triage.render([item], 0, None)


def test_mechanical_readouts_are_recognised_but_real_beliefs_are_not():
    """Per-ticker stance lines from a scoring run are observations, not beliefs."""
    assert triage.is_mechanical(_item(body=("AMZN: watch (3.2%, rel=0.5)",)))
    assert triage.is_mechanical(_item(body=("BN dissent: hold — archetype=platform",)))
    assert triage.is_mechanical(
        _item(body=("8697.T: lens consensus watch @ 1.78% blend (agreement 80%)",)))
    assert not triage.is_mechanical(
        _item(body=("Croupiers take a toll without putting principal at risk.",)))


def test_ingest_reads_promote_and_reject_ticks(tmp_path):
    path = tmp_path / "queue.md"
    path.write_text(
        "- [x] **2026-08-01**\n      Promote me.\n      `a.md` · `aaaaaaaaaaaa`\n\n"
        "- [-] **2026-08-02**\n      Reject me.\n      `b.md` · `bbbbbbbbbbbb`\n\n"
        "- [ ] **2026-08-03**\n      Leave me.\n      `c.md` · `cccccccccccc`\n",
        encoding="utf-8")
    assert triage.ingest(path) == {"aaaaaaaaaaaa": "promoted", "bbbbbbbbbbbb": "rejected"}


def test_already_in_memory_matches_a_promoted_belief_but_not_a_near_miss():
    memory = triage._normalize(
        "- Croupiers facilitate pecuniary transactions without putting principal "
        "capital at risk. — `stahl/Croupier.pdf`")
    hit = _item(body=("**Croupiers** facilitate pecuniary transactions without putting "
                      "principal capital at risk. — `stahl/Croupier.pdf`",))
    assert triage.already_in_memory(hit, memory)
    assert not triage.already_in_memory(_item(body=("A wholly different belief "
                                                    "about exchange fee models.",)), memory)


def test_a_short_proposal_never_auto_matches_memory():
    """A 60-char floor keeps one-liners from being suppressed by coincidence."""
    assert not triage.already_in_memory(_item(body=("Invert.",)), triage._normalize("Invert."))


# --------------------------------------------------------------------------- #
# reversing a decision, back-sync attribution, and checkable promotions
# --------------------------------------------------------------------------- #

def _ledger():
    return {"version": 1, "updated": None, "cadence": "monthly", "decisions": {}}


def test_reversing_a_decision_is_refused_out_loud(capsys):
    """The defect: re-ticking a row to reverse it was a silent no-op."""
    ledger, item = _ledger(), _item()
    assert triage.record(ledger, item, "promoted", "first pass", "human", "2026-08-09")
    assert not triage.record(ledger, item, "rejected", "on reflection", "human",
                             "2026-08-10")
    warning = capsys.readouterr().out
    assert "[warn]" in warning
    assert "already recorded as 'promoted'" in warning
    assert "NOT applied" in warning
    # and the ledger is unchanged, which is what the warning is warning about
    assert ledger["decisions"][triage.fingerprint(item)]["decision"] == "promoted"


def test_repeating_the_same_decision_does_not_warn(capsys):
    ledger, item = _ledger(), _item()
    triage.record(ledger, item, "rejected", "noise", "human", "2026-08-09")
    capsys.readouterr()
    assert not triage.record(ledger, item, "rejected", "noise", "human", "2026-08-10")
    assert "[warn]" not in capsys.readouterr().out


def test_bulk_paths_can_suppress_the_warning(capsys):
    ledger, item = _ledger(), _item()
    triage.record(ledger, item, "promoted", "", "human", "2026-08-09")
    capsys.readouterr()
    triage.record(ledger, item, "rejected", "", "human", "2026-08-10", quiet=True)
    assert capsys.readouterr().out == ""


def test_dropped_is_a_recordable_decision():
    """A merged or dropped proposal must be sayable without claiming a belief."""
    assert "dropped" in triage.DECISIONS
    ledger, item = _ledger(), _item()
    triage.record(ledger, item, "dropped", "merged into a neighbouring belief",
                  "agent", "2026-08-09")
    assert ledger["decisions"][triage.fingerprint(item)]["decision"] == "dropped"


def test_back_sync_is_not_attributed_to_whoever_ran_it():
    """The 21 May-2026 human promotions were back-marked `by: agent`, so a
    wholesale reversal of agent decisions would have unwound the human's work."""
    assert triage.BACKFILL_BY != "agent" and triage.BACKFILL_BY != "human"


def test_promoted_without_a_belief_or_anchor_is_flagged():
    ledger, item = _ledger(), _item(body=("A belief that never reached MEMORY.md, "
                                          "at length enough to match on text.",))
    triage.record(ledger, item, "promoted", "", "agent", "2026-08-09")
    orphans = triage.audit_promoted(ledger, {triage.fingerprint(item): item},
                                    "# Memory\n\nSomething else entirely.\n")
    assert [i for i, _, _ in orphans] == [triage.fingerprint(item)]


def test_an_anchor_clears_a_merged_promotion():
    ledger, item = _ledger(), _item(body=("Merged into a broader belief during the "
                                          "pass, so the text will not match.",))
    triage.record(ledger, item, "promoted", "", "agent", "2026-08-09",
                  anchor='MEMORY.md :: Munger :: "Invert before you underwrite"')
    memory = '- Invert before you underwrite. — `munger.pdf` `[active 2026-08-09]`\n'
    assert triage.audit_promoted(ledger, {triage.fingerprint(item): item}, memory) == []


def test_an_anchor_quoting_a_deleted_belief_breaks_loudly():
    """An anchor that cannot go stale is decoration, not a check."""
    ledger, item = _ledger(), _item()
    triage.record(ledger, item, "promoted", "", "agent", "2026-08-09",
                  anchor='MEMORY.md :: Munger :: "a belief since edited away"')
    orphans = triage.audit_promoted(ledger, {triage.fingerprint(item): item},
                                    "- Some other belief entirely.\n")
    assert len(orphans) == 1
    assert "anchor quotes not in MEMORY.md" in orphans[0][2]


def _bare_path_anchor_case():
    """A backfill row: anchored at the file, not at a belief, and text-matchable."""
    belief = ("Croupiers facilitate pecuniary transactions without putting "
              "principal capital at risk.")
    ledger, item = _ledger(), _item(lens="STAHL", body=(belief,))
    triage.record(ledger, item, "promoted", "text already present in MEMORY.md",
                  triage.BACKFILL_BY, "2026-08-09",
                  anchor="_system/memory/MEMORY.md")
    return ledger, item, belief


def test_a_bare_path_anchor_does_not_excuse_the_text_check():
    """The regression: `memory_anchor: "_system/memory/MEMORY.md"` names no
    belief, so every belief satisfies it. The audit short-circuited on the field
    being set, and deleting the belief changed nothing."""
    ledger, item, belief = _bare_path_anchor_case()
    by_id = {triage.fingerprint(item): item}

    present = f"## Stahl\n\n- {belief} - `stahl/Croupier.pdf` `[active 2026-05-21]`\n"
    assert triage.audit_promoted(ledger, by_id, present) == []

    # Delete the belief outright: the orphan count must rise.
    deleted = "## Stahl\n\n- Some wholly unrelated belief about fee models.\n"
    orphans = triage.audit_promoted(ledger, by_id, deleted)
    assert [i for i, _, _ in orphans] == [triage.fingerprint(item)]
    assert "anchor names no belief" in orphans[0][2]


def test_a_parenthetical_anchor_is_also_not_a_check():
    """`MEMORY.md (company-specific table, WHK row)` quotes nothing either."""
    ledger, item, belief = _bare_path_anchor_case()
    ledger["decisions"][triage.fingerprint(item)]["memory_anchor"] = (
        "_system/memory/MEMORY.md (Stahl / Croupier business model)")
    orphans = triage.audit_promoted(ledger, {triage.fingerprint(item): item},
                                    "- An unrelated belief.\n")
    assert len(orphans) == 1


def test_a_quoted_anchor_still_short_circuits_the_text_check():
    """A merged promotion has no matching text by construction; the quote is the
    check, and it must not be weakened by the fix above."""
    ledger, item = _ledger(), _item(body=("Merged into a broader belief during "
                                          "the pass, so text will not match.",))
    triage.record(ledger, item, "promoted", "", "agent", "2026-08-09",
                  anchor='MEMORY.md :: Munger :: "Invert before you underwrite"')
    memory = "- Invert before you underwrite. - `munger.pdf` `[active 2026-08-09]`\n"
    assert triage.audit_promoted(ledger, {triage.fingerprint(item): item}, memory) == []


def test_a_reversal_carries_the_row_it_replaced():
    """Prose in `reason` is not history; the ledger is untracked by git."""
    ledger, item = _ledger(), _item()
    prior = {"decision": "promoted", "date": "2026-08-09", "by": "agent",
             "reversed_on": "2026-08-09", "reversed_by": "agent"}
    triage.record(ledger, item, "rejected", "contradicts a promoted belief",
                  "agent", "2026-08-09", previous=prior)
    entry = ledger["decisions"][triage.fingerprint(item)]
    assert entry["previous_decision"]["decision"] == "promoted"
    assert entry["previous_decision"]["reversed_by"] == "agent"


def test_rejected_and_dropped_rows_are_not_audited_as_promotions():
    ledger = _ledger()
    for decision in ("rejected", "dropped"):
        triage.record(ledger, _item(body=(f"{decision} proposal text, long enough "
                                          "to be matchable against memory.",)),
                      decision, "", "agent", "2026-08-09")
    assert triage.audit_promoted(ledger, {}, "# Memory\n") == []


# --------------------------------------------------------------------------- #
# CLI: a refused reversal must not exit 0
# --------------------------------------------------------------------------- #

def _cli_sandbox(tmp_path, monkeypatch):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-01.md").write_text(
        "- [PROPOSED MUNGER] Invert before you underwrite.\n", encoding="utf-8")
    monkeypatch.setattr(triage, "DAILY", daily)
    monkeypatch.setattr(triage, "LEDGER", tmp_path / "triage_ledger.json")
    item = triage.parse_file(daily / "2026-08-01.md")[0]
    return triage.fingerprint({**item, "also_seen": []})


def test_mark_exits_nonzero_when_a_reversal_is_refused(tmp_path, monkeypatch, capsys):
    ident = _cli_sandbox(tmp_path, monkeypatch)
    assert triage.main(["--mark", "promoted", "--ids", ident]) == 0
    capsys.readouterr()
    # The append-only ledger refuses this; the run used to still exit 0.
    assert triage.main(["--mark", "rejected", "--ids", ident]) == 1
    out = capsys.readouterr().out
    assert "NOT changed" in out


def test_mark_repeating_the_same_decision_still_exits_zero(tmp_path, monkeypatch):
    ident = _cli_sandbox(tmp_path, monkeypatch)
    assert triage.main(["--mark", "promoted", "--ids", ident]) == 0
    assert triage.main(["--mark", "promoted", "--ids", ident]) == 0


def test_mark_records_previous_decision_from_the_cli(tmp_path, monkeypatch):
    import json as _json
    ident = _cli_sandbox(tmp_path, monkeypatch)
    assert triage.main([
        "--mark", "rejected", "--ids", ident, "--by", "agent",
        "--previous-decision",
        '{"decision": "promoted", "date": "2026-08-09", "by": "agent"}']) == 0
    ledger = _json.loads(triage.LEDGER.read_text(encoding="utf-8"))
    prior = ledger["decisions"][ident]["previous_decision"]
    assert prior["decision"] == "promoted"
    assert prior["reversed_by"] == "agent"      # stamped from --by
