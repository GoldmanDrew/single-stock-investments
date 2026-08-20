# Cloud Grok — VIC drop (one screen)

Read `_system/agents/GROK.md` and follow it. Short form:

- Preflight: `python _system/scripts/materialize_drive_credentials.py --require`. Stop if it fails.
- VIC → Drive `Admin/Intake/VIC/{TICKER}/` via `python _system/scripts/drive_intake_drop.py --kind VIC --ticker TICKER file.pdf`
- Skip `unknown_ticker`. Never create ticker folders. Numeric names need the exchange suffix already used in this repo (`0388.HK`, not `9909`).
- JSON status `uploaded` or `already_present` means the Drive handoff succeeded. List every other result as skipped/failed.
- Daily 14:00 UTC Data Pipeline → SSI `{TICKER}/third-party-analyses/vic/`. **Not** research-vault. Do not claim the scheduled import already happened.
- Text-only → `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md`, then `python _system/scripts/third_party_inventory.py TICKER` (pending repo change).
- Secret: `GOOGLE_APPLICATION_CREDENTIALS_JSON` on [Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents).
