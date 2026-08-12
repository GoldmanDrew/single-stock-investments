from unittest.mock import patch

from _system.scripts import ssi_adjudicate as adjudicate


def test_queue_is_bounded_diverse_and_never_infers_verdicts():
    alerts = [
        {"claim_id": f"c{i}", "issuer": "AAA" if i % 2 else "BBB",
         "statement": "claim", "evidence_ref": {"source_path": "filing"}}
        for i in range(8)
    ]
    with patch.object(adjudicate, "_pending_gold", return_value=[{"claim_id": "g1"}]), \
         patch.object(adjudicate, "_adjudicated_alert_ids", return_value={"c0"}), \
         patch.object(adjudicate, "_emitted_alerts", return_value=alerts):
        payload = adjudicate.queue_payload(gold_limit=5, alert_limit=3)
    assert len(payload["gold_sample"]) == 1
    assert len(payload["alert_sample"]) == 3
    assert all("adjudication" not in row for row in payload["alert_sample"])
    assert payload["human_ground_truth_required"] is True
