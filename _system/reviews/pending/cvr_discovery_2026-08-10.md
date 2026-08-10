# CVR discovery — 2026-08-10

**UTC:** 2026-08-10T16:02:21Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `JSPR/` (+ skeleton terms / evidence / manifest)
- `GRTX/` (+ skeleton terms / evidence / manifest)
- `LNTH/` (+ skeleton terms / evidence / manifest)
- `OBX/` (+ skeleton terms / evidence / manifest)
- `ATAI/` (+ skeleton terms / evidence / manifest)
- `TBPH/` (+ skeleton terms / evidence / manifest)
- `SEER/` (+ skeleton terms / evidence / manifest)
- `RNAZ/` (+ skeleton terms / evidence / manifest)
- `CORZ/` (+ skeleton terms / evidence / manifest)
- `NXTC/` (+ skeleton terms / evidence / manifest)
- `RNAC/` (+ skeleton terms / evidence / manifest)
- `GEN/` (+ skeleton terms / evidence / manifest)
- `OSRH/` (+ skeleton terms / evidence / manifest)
- `BMY/` (+ skeleton terms / evidence / manifest)
- `ALKS/` (+ skeleton terms / evidence / manifest)
- `ZVRA/` (+ skeleton terms / evidence / manifest)
- `LGND/` (+ skeleton terms / evidence / manifest)
- `AMZN/` (+ skeleton terms / evidence / manifest)
- `SMTI/` (+ skeleton terms / evidence / manifest)
- `MDXG/` (+ skeleton terms / evidence / manifest)
- `ZBH/` (+ skeleton terms / evidence / manifest)
- `ALOT/` (+ skeleton terms / evidence / manifest)
- `LGMK/` (+ skeleton terms / evidence / manifest)
- `TYFG/` (+ skeleton terms / evidence / manifest)
- `HBT/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `JSPR` | sec_full_text | 8-K | 0001788028 | https://www.sec.gov/Archives/edgar/data/1788028/000121390026083563/ |
| `GRTX` | sec_full_text | 8-K | 0001563577 | https://www.sec.gov/Archives/edgar/data/1563577/000119312526328716/ |
| `LNTH` | sec_full_text | 8-K | 0001521036 | https://www.sec.gov/Archives/edgar/data/1521036/000119312526336771/ |
| `OBX` | sec_full_text | 8-K | 0002130606 | https://www.sec.gov/Archives/edgar/data/2130606/000119312526330810/ |
| `ATAI` | sec_full_text | DEFM14A | 0002081043 | https://www.sec.gov/Archives/edgar/data/2081043/000114036126030109/ |
| `TBPH` | sec_full_text | 8-K | 0001583107 | https://www.sec.gov/Archives/edgar/data/1583107/000110465926093066/ |
| `SEER` | sec_full_text | 8-K | 0001726445 | https://www.sec.gov/Archives/edgar/data/1726445/000119312526328733/ |
| `RNAZ` | sec_full_text | 8-K | 0001829635 | https://www.sec.gov/Archives/edgar/data/1829635/000110465926089805/ |
| `CORZ` | sec_full_text | 8-K | 0001839341 | https://www.sec.gov/Archives/edgar/data/1839341/000183934126000013/ |
| `NXTC` | sec_full_text | 8-K | 0001661059 | https://www.sec.gov/Archives/edgar/data/1661059/000110465926092025/ |
| `RNAC` | sec_full_text | 8-K | 0001453687 | https://www.sec.gov/Archives/edgar/data/1453687/000145368726000100/ |
| `GEN` | sec_full_text | 8-K | 0000849399 | https://www.sec.gov/Archives/edgar/data/849399/000084939926000028/ |
| `OSRH` | sec_full_text | 8-K | 0001840425 | https://www.sec.gov/Archives/edgar/data/1840425/000121390026086599/ |
| `BMY` | sec_full_text | 8-K | 0000014272 | https://www.sec.gov/Archives/edgar/data/14272/000001427226000018/ |
| `ALKS` | sec_full_text | 8-K | 0001520262 | https://www.sec.gov/Archives/edgar/data/1520262/000119312526318844/ |
| `ZVRA` | sec_full_text | 8-K | 0001434647 | https://www.sec.gov/Archives/edgar/data/1434647/000143464726000067/ |
| `LGND` | sec_full_text | 8-K | 0000886163 | https://www.sec.gov/Archives/edgar/data/886163/000088616326000041/ |
| `AMZN` | sec_full_text | S-4 | 0001018724 | https://www.sec.gov/Archives/edgar/data/1018724/000110465926089294/ |
| `SMTI` | sec_full_text | 8-K | 0000714256 | https://www.sec.gov/Archives/edgar/data/714256/000149315226035196/ |
| `MDXG` | sec_full_text | 8-K | 0001376339 | https://www.sec.gov/Archives/edgar/data/1376339/000137633926000070/ |
| `ZBH` | sec_full_text | 8-K | 0001136869 | https://www.sec.gov/Archives/edgar/data/1136869/000119312526335108/ |
| `ALOT` | sec_full_text | DEFM14A | 0000008146 | https://www.sec.gov/Archives/edgar/data/8146/000119312526326441/ |
| `LGMK` | sec_full_text | 8-K | 0001566826 | https://www.sec.gov/Archives/edgar/data/1566826/000121390026084705/ |
| `TYFG` | sec_full_text | 8-K | 0001725262 | https://www.sec.gov/Archives/edgar/data/1725262/000149315226036754/ |
| `HBT` | sec_full_text | 8-K | 0000775215 | https://www.sec.gov/Archives/edgar/data/775215/000077521526000076/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

