"""Local JSON store for proposals, fills, positions, notes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import PKG_DIR
from .classify_positions import norm_sym
from .config_loader import load_config


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class SleeveStore:
    def __init__(self, root: Path | None = None):
        cfg = load_config()
        rel = str((cfg.get("paths") or {}).get("store_dir") or "data/local")
        self.root = Path(root) if root else (PKG_DIR / rel)
        self.root.mkdir(parents=True, exist_ok=True)
        self._proposals = self._read("proposals.json", [])
        self._fills = self._read("fills.json", [])
        self._positions = self._read("positions.json", [])
        self._notes = self._read("notes.json", [])
        self._ideas = self._read("ideas.json", [])
        self._cashflows = self._read("cashflows.json", [])
        self._audit = self._read("classifier_audit.json", [])
        self._tags = self._read("sleeve_tags.json", [])

    def _path(self, name: str) -> Path:
        return self.root / name

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return json.loads(json.dumps(default))
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, name: str, payload: Any) -> None:
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        tmp.replace(path)

    def save_proposal(self, proposal: Mapping[str, Any]) -> None:
        existing = [p for p in self._proposals if p.get("proposal_id") != proposal["proposal_id"]]
        existing.append(dict(proposal))
        self._proposals = existing
        self._write("proposals.json", self._proposals)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        for row in self._proposals:
            if row.get("proposal_id") == proposal_id:
                return dict(row)
        return None

    def used_proposal_ids(self) -> set[str]:
        used = {str(p["proposal_id"]) for p in self._proposals if p.get("status") in {"filled", "submitted"}}
        used.update(str(f["proposal_id"]) for f in self._fills if f.get("proposal_id"))
        return used

    def recent_ticker_at(self) -> dict[str, datetime]:
        out: dict[str, datetime] = {}
        for fill in self._fills:
            ticker = norm_sym(fill.get("ticker") or "")
            raw = fill.get("filled_at")
            if not ticker or not raw:
                continue
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            prev = out.get(ticker)
            if prev is None or ts > prev:
                out[ticker] = ts
        return out

    def pending_proposals(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._proposals if p.get("status") == "proposed"]

    def save_sleeve_tag(self, tag: Mapping[str, Any]) -> None:
        row = dict(tag)
        con_id = int(row.get("con_id") or row.get("conId") or 0)
        ticker = norm_sym(row.get("ticker") or row.get("symbol") or "")
        kept = []
        for existing in self._tags:
            same_con = con_id and int(existing.get("con_id") or 0) == con_id
            same_ticker = ticker and norm_sym(existing.get("ticker") or "") == ticker and existing.get("owner") == row.get("owner")
            if not (same_con or same_ticker):
                kept.append(existing)
        kept.append({
            "owner": row.get("owner"),
            "ticker": ticker,
            "con_id": con_id or None,
            "sec_type": row.get("sec_type") or "STK",
        })
        self._tags = kept
        self._write("sleeve_tags.json", self._tags)

    def sleeve_tags(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._tags]

    def record_submit(self, proposal: Mapping[str, Any], submitted: Mapping[str, Any]) -> None:
        proposal_row = dict(proposal)
        proposal_row["status"] = "submitted"
        proposal_row["ib_order_id"] = submitted.get("ib_order_id")
        proposal_row["submitted_at"] = submitted.get("submitted_at")
        self.save_proposal(proposal_row)
        self.save_sleeve_tag({
            "owner": proposal.get("owner"),
            "ticker": proposal.get("ticker"),
            "con_id": proposal.get("con_id") or submitted.get("con_id"),
            "sec_type": proposal.get("sec_type") or "STK",
        })

    def positions(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._positions]

    def replace_positions(self, rows: list[Mapping[str, Any]]) -> None:
        self._positions = [dict(r) for r in rows]
        self._write("positions.json", self._positions)

    def notes(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(n) for n in self._notes]
        if owner:
            rows = [n for n in rows if n.get("owner") == owner]
        return rows

    def add_note(self, note: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(note)
        row.setdefault("id", f"note-{len(self._notes) + 1}")
        self._notes.append(row)
        self._write("notes.json", self._notes)
        return row

    def ideas(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(i) for i in self._ideas]
        if owner:
            rows = [i for i in rows if i.get("owner") == owner]
        return rows

    def upsert_idea(self, idea: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(idea)
        key = (row.get("owner"), norm_sym(row.get("ticker") or ""))
        kept = [i for i in self._ideas if (i.get("owner"), norm_sym(i.get("ticker") or "")) != key]
        kept.append(row)
        self._ideas = kept
        self._write("ideas.json", self._ideas)
        return row

    def cashflows(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(c) for c in self._cashflows]
        if owner:
            rows = [c for c in rows if c.get("owner") == owner]
        return rows

    def record_fill(self, proposal: Mapping[str, Any], fill: Mapping[str, Any]) -> None:
        proposal_row = dict(proposal)
        proposal_row["status"] = "filled"
        self.save_proposal(proposal_row)
        self._fills.append(dict(fill))
        self._write("fills.json", self._fills)
        self.save_sleeve_tag({
            "owner": fill.get("owner"),
            "ticker": fill.get("ticker"),
            "con_id": proposal.get("con_id"),
            "sec_type": proposal.get("sec_type") or "STK",
        })
        signed = -abs(float(fill["qty"]) * float(fill["price"])) if fill["side"] == "BUY" else abs(float(fill["qty"]) * float(fill["price"]))
        self._cashflows.append({
            "owner": fill["owner"],
            "date": fill["filled_at"][:10],
            "ticker": fill["ticker"],
            "amount": signed,
            "kind": "buy" if fill["side"] == "BUY" else "sell",
        })
        self._write("cashflows.json", self._cashflows)
        qty = float(fill["qty"]) * (1 if fill["side"] == "BUY" else -1)
        found = False
        for pos in self._positions:
            if pos.get("owner") == fill["owner"] and norm_sym(pos.get("ticker") or pos.get("symbol") or "") == fill["ticker"]:
                pos["qty"] = float(pos.get("qty") or 0) + qty
                pos["mark"] = float(fill["price"])
                pos["marketValue"] = pos["qty"] * pos["mark"]
                found = True
                break
        if not found:
            self._positions.append({
                "owner": fill["owner"],
                "ticker": fill["ticker"],
                "symbol": fill["ticker"],
                "qty": qty,
                "mark": float(fill["price"]),
                "marketValue": qty * float(fill["price"]),
                "secType": proposal.get("sec_type") or "STK",
                "orderRef": proposal.get("order_ref"),
                "classification": {
                    "ticker": fill["ticker"],
                    "bucket": fill["owner"],
                    "reason": "drew_new" if fill["owner"] == "drew" else "michael_new",
                    "owner": fill["owner"],
                },
            })
        self._write("positions.json", self._positions)
        self.upsert_idea({
            "owner": fill["owner"],
            "ticker": fill["ticker"],
            "side": fill["side"],
            "status": "filled",
            "cluster": proposal.get("cluster") or "idiosyncratic",
            "conviction": proposal.get("conviction"),
            "plc_score": None,
            "plc_thesis": proposal.get("plc_thesis"),
            "holding_period_years": proposal.get("holding_period_years"),
            "entry_price": fill["price"],
            "shares": fill["qty"],
            "cost_usd": abs(float(fill["qty"]) * float(fill["price"])),
        })

    def append_audit(self, rows: list[Mapping[str, Any]]) -> None:
        as_of = _iso(datetime.now(timezone.utc))
        for row in rows:
            item = dict(row)
            item.setdefault("as_of", as_of)
            self._audit.append(item)
        self._write("classifier_audit.json", self._audit)

    def fills(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(f) for f in self._fills]
        if owner:
            rows = [f for f in rows if f.get("owner") == owner]
        return rows
