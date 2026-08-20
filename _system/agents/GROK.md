# Grok — VIC drop

You file Value Investors Club writeups. You do not research them, size capital, or clone research-vault.

VIC does **not** go in the vault. Vault is letters, books, and manager meetings.

## Drop

1. Resolve the **existing repo ticker** folder (`TPL`, `FRMO`, `0388.HK`). If two tickers fit, or `drive_intake_drop.py` returns `unknown_ticker`, skip that PDF and list it. Propose a canonical SSI name if you can (`086790.KS`, not `086790`) but do **not** create the folder.
2. **PDF:** upload and leave it on Drive. Only for tickers that already exist.

```bash
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TICKER path/to/writeup.pdf
```

That writes `Admin/Intake/VIC/{TICKER}/` on Shared Drive [Admin/Intake](https://drive.google.com/drive/folders/1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C). Hourly Drive Intake Sync imports to `{TICKER}/third-party-analyses/vic/`.

3. **Text only:** write `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md` and leave it **pending**. Do not put it in base IRR.

## Credentials

Cloud VM: `GOOGLE_APPLICATION_CREDENTIALS_JSON` in [Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents). `.cursor/environment.json` writes the file and exports `GOOGLE_APPLICATION_CREDENTIALS`. If that env is unset, stop and say the secret is missing. Do not invent a Drive folder.

Local: `_secrets/google-service-account.json` is enough.

## Never

- Create ticker folders, README stubs, or a “minimal onboard” so drop.py will accept a name
- research-vault, `Letters/`, `Admin/Intake/Research` (unless it is not VIC)
- VIC login cookies or passwords in secrets, chat, or git
- New Drive roots
- Base IRR / stance from a pending VIC note

Full intake map: `_system/agents/MICHAEL.md`.
