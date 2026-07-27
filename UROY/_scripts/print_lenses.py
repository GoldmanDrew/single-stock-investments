import json
from pathlib import Path

l = json.loads(Path("UROY/research/lenses.json").read_text(encoding="utf-8"))
rows = l.get("lenses") or l.get("personas") or []
if isinstance(rows, dict):
    rows = [{"persona": k, **v} for k, v in rows.items() if isinstance(v, dict)]
for row in rows:
    if not isinstance(row, dict):
        continue
    print(
        f"{row.get('persona') or row.get('id')}: "
        f"rel={row.get('relevance')} "
        f"ret={row.get('annualized_return_pct') or row.get('return_pct')} "
        f"verdict={row.get('verdict')}"
    )
print("consensus", l.get("consensus") or l.get("blend") or l.get("lens_consensus"))
v = json.loads(Path("UROY/research/valuation.json").read_text(encoding="utf-8"))
print("implied_return", v.get("implied_return"))
print("stance", v.get("stance_proposal"))
print("route", json.loads(Path("UROY/research/valuation_route.json").read_text())["profile_id"])
