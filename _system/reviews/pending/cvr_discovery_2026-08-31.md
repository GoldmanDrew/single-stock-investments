# CVR discovery — 2026-08-31

**UTC:** 2026-08-31T20:42:36Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `RLYB/` (+ skeleton terms / evidence / manifest)
- `SOWG/` (+ skeleton terms / evidence / manifest)
- `CYCN/` (+ skeleton terms / evidence / manifest)
- `AON/` (+ skeleton terms / evidence / manifest)
- `INDV/` (+ skeleton terms / evidence / manifest)
- `CBZ/` (+ skeleton terms / evidence / manifest)
- `ATKR/` (+ skeleton terms / evidence / manifest)
- `LXFR/` (+ skeleton terms / evidence / manifest)
- `TEM/` (+ skeleton terms / evidence / manifest)
- `MBUU/` (+ skeleton terms / evidence / manifest)
- `NVTS/` (+ skeleton terms / evidence / manifest)
- `AIRT/` (+ skeleton terms / evidence / manifest)
- `FCCN/` (+ skeleton terms / evidence / manifest)
- `HL/` (+ skeleton terms / evidence / manifest)
- `RUM/` (+ skeleton terms / evidence / manifest)
- `PRTH/` (+ skeleton terms / evidence / manifest)
- `LUCK/` (+ skeleton terms / evidence / manifest)
- `FTW/` (+ skeleton terms / evidence / manifest)
- `BTGO/` (+ skeleton terms / evidence / manifest)
- `INV/` (+ skeleton terms / evidence / manifest)
- `SLE/` (+ skeleton terms / evidence / manifest)
- `ALIS/` (+ skeleton terms / evidence / manifest)
- `AIB/` (+ skeleton terms / evidence / manifest)
- `DVLT/` (+ skeleton terms / evidence / manifest)
- `LFVN/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `RLYB` | sec_full_text | S-4/A | 0001739410 | https://www.sec.gov/Archives/edgar/data/1739410/000119312526368568/ |
| `SOWG` | sec_full_text | 8-K | 0001490161 | https://www.sec.gov/Archives/edgar/data/1490161/000182912626009427/ |
| `CYCN` | sec_full_text | 8-K | 0001755237 | https://www.sec.gov/Archives/edgar/data/1755237/000119312526365150/ |
| `AON` | sec_full_text | 8-K | 0000315293 | https://www.sec.gov/Archives/edgar/data/315293/000119312526375328/ |
| `INDV` | sec_full_text | S-4 | 0001625297 | https://www.sec.gov/Archives/edgar/data/1625297/000110465926103278/ |
| `CBZ` | sec_full_text | PREM14A | 0000944148 | https://www.sec.gov/Archives/edgar/data/944148/000119312526371546/ |
| `ATKR` | sec_full_text | PREM14A | 0001666138 | https://www.sec.gov/Archives/edgar/data/1666138/000114036126034771/ |
| `LXFR` | sec_full_text | PREM14A | 0001096056 | https://www.sec.gov/Archives/edgar/data/1096056/000207709626000240/ |
| `TEM` | sec_full_text | S-4 | 0001717115 | https://www.sec.gov/Archives/edgar/data/1717115/000119312526376895/ |
| `MBUU` | sec_full_text | 8-K/A | 0001590976 | https://www.sec.gov/Archives/edgar/data/1590976/000159097626000040/ |
| `NVTS` | sec_full_text | 8-K | 0001821769 | https://www.sec.gov/Archives/edgar/data/1821769/000110465926100478/ |
| `AIRT` | sec_full_text | 8-K/A | 0000353184 | https://www.sec.gov/Archives/edgar/data/353184/000035318426000088/ |
| `FCCN` | sec_full_text | 8-K | 0001131903 | https://www.sec.gov/Archives/edgar/data/1131903/000121390026093516/ |
| `HL` | sec_full_text | 8-K | 0000719413 | https://www.sec.gov/Archives/edgar/data/719413/000119312526374615/ |
| `RUM` | sec_full_text | 8-K/A | 0001830081 | https://www.sec.gov/Archives/edgar/data/1830081/000121390026095047/ |
| `PRTH` | sec_full_text | 8-K | 0001653558 | https://www.sec.gov/Archives/edgar/data/1653558/000165355826000134/ |
| `LUCK` | sec_full_text | 8-K | 0001840572 | https://www.sec.gov/Archives/edgar/data/1840572/000162828026059178/ |
| `FTW` | sec_full_text | 8-K | 0002083125 | https://www.sec.gov/Archives/edgar/data/2083125/000121390026090532/ |
| `BTGO` | sec_full_text | 8-K | 0001740604 | https://www.sec.gov/Archives/edgar/data/1740604/000174060426000056/ |
| `INV` | sec_full_text | 8-K | 0002001557 | https://www.sec.gov/Archives/edgar/data/2001557/000162828026057840/ |
| `SLE` | sec_full_text | 8-K | 0001621672 | https://www.sec.gov/Archives/edgar/data/1621672/000143774926028267/ |
| `ALIS` | sec_full_text | S-4/A | 0002026767 | https://www.sec.gov/Archives/edgar/data/2026767/000149315226038568/ |
| `AIB` | sec_full_text | 8-K | 0002070542 | https://www.sec.gov/Archives/edgar/data/2070542/000121390026091419/ |
| `DVLT` | sec_full_text | 8-K | 0001682149 | https://www.sec.gov/Archives/edgar/data/1682149/000110465926098833/ |
| `LFVN` | sec_full_text | 8-K | 0000849146 | https://www.sec.gov/Archives/edgar/data/849146/000119312526371265/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

