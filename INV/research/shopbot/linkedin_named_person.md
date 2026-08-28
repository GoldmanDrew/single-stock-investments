# Vicki brief: named-person LinkedIn check (not a crawl)

**When to use:** After GTC, Hot Chips, or OCP, if the mechanical watch has no rank 1–3 hit and you want a human-initiated look at a **named** person.

**Do not:** scrape LinkedIn HTML, log in, walk employee feeds, or put this on a cron.

## People (only these)

- Ali Heydari (NVIDIA thermal / OMNICOOL PI)
- Yaman Manaserh (NVIDIA)
- Josh Claman (Accelsius)
- Greg Busch (Vertiv on OMNICOOL)
- Sukhvinder Kang (Boyd)

## What to capture

Public post URL, date, quote (≤280 chars), whether Accelsius / Vertiv / Boyd / ZutaCore is **named**, and whether a hyperscaler production MW is claimed.

Write the result into `INV/research/evidence/two_phase_watch_YYYY-MM-DD.md` under a “Vicki named-person” heading. Rank 5–6 unless Accelsius + named hyperscaler production is explicit **and** an IR/SEC/OEM URL confirms it.
