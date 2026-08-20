# Cloud Grok — VIC drop (one screen)

Read `_system/agents/GROK.md` and follow it. Short form:

- VIC → Drive `Admin/Intake/VIC/{TICKER}/` via `python _system/scripts/drive_intake_drop.py --kind VIC --ticker TICKER file.pdf`
- Skip `unknown_ticker`. Never create ticker folders. Numeric names need the exchange suffix already used in this repo (`0388.HK`, not `9909`).
- Then SSI `{TICKER}/third-party-analyses/vic/` (Drive Intake Sync). **Not** research-vault.
- Text-only → `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md` (pending).
- Secret: `GOOGLE_APPLICATION_CREDENTIALS_JSON` on [Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents).
