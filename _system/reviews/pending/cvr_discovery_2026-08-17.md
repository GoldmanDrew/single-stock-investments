# CVR discovery — 2026-08-17

**UTC:** 2026-08-17T15:27:12Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `SKYE/` (+ skeleton terms / evidence / manifest)
- `SUNE/` (+ skeleton terms / evidence / manifest)
- `DWTX/` (+ skeleton terms / evidence / manifest)
- `FBIO/` (+ skeleton terms / evidence / manifest)
- `STRR/` (+ skeleton terms / evidence / manifest)
- `ITGR/` (+ skeleton terms / evidence / manifest)
- `BLRK/` (+ skeleton terms / evidence / manifest)
- `DV/` (+ skeleton terms / evidence / manifest)
- `OMEX/` (+ skeleton terms / evidence / manifest)
- `VRME/` (+ skeleton terms / evidence / manifest)
- `OPFI/` (+ skeleton terms / evidence / manifest)
- `BKHA/` (+ skeleton terms / evidence / manifest)
- `BBCQ/` (+ skeleton terms / evidence / manifest)
- `HCAT/` (+ skeleton terms / evidence / manifest)
- `SRTA/` (+ skeleton terms / evidence / manifest)
- `USPH/` (+ skeleton terms / evidence / manifest)
- `ARRY/` (+ skeleton terms / evidence / manifest)
- `PPHC/` (+ skeleton terms / evidence / manifest)
- `IMDX/` (+ skeleton terms / evidence / manifest)
- `SCTH/` (+ skeleton terms / evidence / manifest)
- `SECZ/` (+ skeleton terms / evidence / manifest)
- `KUST/` (+ skeleton terms / evidence / manifest)
- `JOBY/` (+ skeleton terms / evidence / manifest)
- `OLOX/` (+ skeleton terms / evidence / manifest)
- `CYCU/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `SKYE` | sec_full_text | 8-K | 0001516551 | https://www.sec.gov/Archives/edgar/data/1516551/000162828026056966/ |
| `SUNE` | sec_full_text | 8-K | 0000022701 | https://www.sec.gov/Archives/edgar/data/22701/000121390026088491/ |
| `DWTX` | sec_full_text | 8-K | 0001818844 | https://www.sec.gov/Archives/edgar/data/1818844/000110465926095512/ |
| `FBIO` | sec_full_text | 8-K | 0001429260 | https://www.sec.gov/Archives/edgar/data/1429260/000110465926095931/ |
| `STRR` | sec_full_text | 8-K | 0001210708 | https://www.sec.gov/Archives/edgar/data/1210708/000121070826000080/ |
| `ITGR` | sec_full_text | 8-K | 0001114483 | https://www.sec.gov/Archives/edgar/data/1114483/000095010326011881/ |
| `BLRK` | sec_full_text | 8-K | 0002081532 | https://www.sec.gov/Archives/edgar/data/2081532/000121390026084282/ |
| `DV` | sec_full_text | 8-K | 0001819928 | https://www.sec.gov/Archives/edgar/data/1819928/000110465926092934/ |
| `OMEX` | sec_full_text | S-4/A | 0000798528 | https://www.sec.gov/Archives/edgar/data/798528/000119312526333491/ |
| `VRME` | sec_full_text | S-4/A | 0001104038 | https://www.sec.gov/Archives/edgar/data/1104038/000121465926009911/ |
| `OPFI` | sec_full_text | S-4/A | 0001818502 | https://www.sec.gov/Archives/edgar/data/1818502/000119312526335050/ |
| `BKHA` | sec_full_text | S-4/A | 0002000775 | https://www.sec.gov/Archives/edgar/data/2000775/000182912626008251/ |
| `BBCQ` | sec_full_text | DEFM14A | 0002088295 | https://www.sec.gov/Archives/edgar/data/2088295/000121390026085816/ |
| `HCAT` | sec_full_text | 8-K | 0001636422 | https://www.sec.gov/Archives/edgar/data/1636422/000163642226000091/ |
| `SRTA` | sec_full_text | 8-K | 0001779128 | https://www.sec.gov/Archives/edgar/data/1779128/000162828026052152/ |
| `USPH` | sec_full_text | 8-K | 0000885978 | https://www.sec.gov/Archives/edgar/data/885978/000088597826000048/ |
| `ARRY` | sec_full_text | 8-K | 0001820721 | https://www.sec.gov/Archives/edgar/data/1820721/000162828026053342/ |
| `PPHC` | sec_full_text | 8-K | 0001903508 | https://www.sec.gov/Archives/edgar/data/1903508/000162828026055194/ |
| `IMDX` | sec_full_text | 8-K | 0001642380 | https://www.sec.gov/Archives/edgar/data/1642380/000149315226036863/ |
| `SCTH` | sec_full_text | 8-K | 0001703157 | https://www.sec.gov/Archives/edgar/data/1703157/000101738626000107/ |
| `SECZ` | sec_full_text | 8-K/A | 0002094496 | https://www.sec.gov/Archives/edgar/data/2094496/000162828026056811/ |
| `KUST` | sec_full_text | 8-K | 0001342958 | https://www.sec.gov/Archives/edgar/data/1342958/000149315226035942/ |
| `JOBY` | sec_full_text | 8-K | 0001819848 | https://www.sec.gov/Archives/edgar/data/1819848/000181984826000432/ |
| `OLOX` | sec_full_text | 8-K/A | 0001023994 | https://www.sec.gov/Archives/edgar/data/1023994/000121390026087885/ |
| `CYCU` | sec_full_text | 8-K | 0001868419 | https://www.sec.gov/Archives/edgar/data/1868419/000149315226036024/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

