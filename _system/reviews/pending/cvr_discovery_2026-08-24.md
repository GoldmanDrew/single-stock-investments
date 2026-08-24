# CVR discovery — 2026-08-24

**UTC:** 2026-08-24T15:40:44Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 26  
**Stubs created:** 26  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `HOWL/` (+ skeleton terms / evidence / manifest)
- `CHRS/` (+ skeleton terms / evidence / manifest)
- `SBMT/` (+ skeleton terms / evidence / manifest)
- `SNTI/` (+ skeleton terms / evidence / manifest)
- `WEAV/` (+ skeleton terms / evidence / manifest)
- `UTZ/` (+ skeleton terms / evidence / manifest)
- `NTWO/` (+ skeleton terms / evidence / manifest)
- `TMS/` (+ skeleton terms / evidence / manifest)
- `LFTO/` (+ skeleton terms / evidence / manifest)
- `AVEX/` (+ skeleton terms / evidence / manifest)
- `VOYG/` (+ skeleton terms / evidence / manifest)
- `OPTT/` (+ skeleton terms / evidence / manifest)
- `QTI/` (+ skeleton terms / evidence / manifest)
- `SWAG/` (+ skeleton terms / evidence / manifest)
- `PARK/` (+ skeleton terms / evidence / manifest)
- `STXS/` (+ skeleton terms / evidence / manifest)
- `NHIC/` (+ skeleton terms / evidence / manifest)
- `LUNR/` (+ skeleton terms / evidence / manifest)
- `ELUT/` (+ skeleton terms / evidence / manifest)
- `CECO/` (+ skeleton terms / evidence / manifest)
- `DCGO/` (+ skeleton terms / evidence / manifest)
- `DH/` (+ skeleton terms / evidence / manifest)
- `ONDS/` (+ skeleton terms / evidence / manifest)
- `ALTI/` (+ skeleton terms / evidence / manifest)
- `PUSA/` (+ skeleton terms / evidence / manifest)
- `IPEX/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `HOWL` | sec_full_text | 8-K | 0001785530 | https://www.sec.gov/Archives/edgar/data/1785530/000119312526360059/ |
| `CHRS` | sec_full_text | 8-K | 0001512762 | https://www.sec.gov/Archives/edgar/data/1512762/000110465926097951/ |
| `SBMT` | sec_full_text | 8-K | 0002067674 | https://www.sec.gov/Archives/edgar/data/2067674/000153949726002331/ |
| `SNTI` | sec_full_text | 8-K | 0001854270 | https://www.sec.gov/Archives/edgar/data/1854270/000162828026058258/ |
| `WEAV` | sec_full_text | 8-K | 0001609151 | https://www.sec.gov/Archives/edgar/data/1609151/000160915126000100/ |
| `UTZ` | sec_full_text | PREM14A | 0001739566 | https://www.sec.gov/Archives/edgar/data/1739566/000119312526361757/ |
| `NTWO` | sec_full_text | 8-K | 0002028027 | https://www.sec.gov/Archives/edgar/data/2028027/000121390026090994/ |
| `TMS` | sec_full_text | 8-K | 0002048951 | https://www.sec.gov/Archives/edgar/data/2048951/000204895126000013/ |
| `LFTO` | sec_full_text | 8-K | 0001850351 | https://www.sec.gov/Archives/edgar/data/1850351/000162828026056173/ |
| `AVEX` | sec_full_text | 8-K | 0002096300 | https://www.sec.gov/Archives/edgar/data/2096300/000209630026000023/ |
| `VOYG` | sec_full_text | 8-K | 0001788060 | https://www.sec.gov/Archives/edgar/data/1788060/000162828026057100/ |
| `OPTT` | sec_full_text | 8-K | 0001378140 | https://www.sec.gov/Archives/edgar/data/1378140/000149315226039793/ |
| `QTI` | sec_full_text | 8-K | 0001844505 | https://www.sec.gov/Archives/edgar/data/1844505/000162828026056179/ |
| `SWAG` | sec_full_text | 8-K | 0001872525 | https://www.sec.gov/Archives/edgar/data/1872525/000121390026087819/ |
| `PARK` | sec_full_text | 8-K | 0002069604 | https://www.sec.gov/Archives/edgar/data/2069604/000110465926093050/ |
| `STXS` | sec_full_text | 8-K | 0001289340 | https://www.sec.gov/Archives/edgar/data/1289340/000149315226037113/ |
| `NHIC` | sec_full_text | DEFM14A | 0002043699 | https://www.sec.gov/Archives/edgar/data/2043699/000114036126032067/ |
| `LUNR` | sec_full_text | 8-K | 0001844452 | https://www.sec.gov/Archives/edgar/data/1844452/000162828026056476/ |
| `ELUT` | sec_full_text | 8-K | 0001708527 | https://www.sec.gov/Archives/edgar/data/1708527/000110465926099731/ |
| `CECO` | sec_full_text | 8-K | 0000003197 | https://www.sec.gov/Archives/edgar/data/3197/000119312526341191/ |
| `DCGO` | sec_full_text | 8-K | 0001822359 | https://www.sec.gov/Archives/edgar/data/1822359/000162828026057387/ |
| `DH` | sec_full_text | 8-K | 0001861795 | https://www.sec.gov/Archives/edgar/data/1861795/000119312526342384/ |
| `ONDS` | sec_full_text | 8-K | 0001646188 | https://www.sec.gov/Archives/edgar/data/1646188/000119312526347973/ |
| `ALTI` | sec_full_text | 8-K | 0001838615 | https://www.sec.gov/Archives/edgar/data/1838615/000162828026055192/ |
| `PUSA` | sec_full_text | S-4/A | 0002009312 | https://www.sec.gov/Archives/edgar/data/2009312/000149315226036713/ |
| `IPEX` | google_news_rss | — | — | Inflection Point Acquisition (NASDAQ: IPEX) updates GOWell earnout structure ... |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

