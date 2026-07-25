# Activist registry candidates

**Date:** 2026-07-25
**Registry path:** `_system/frameworks/activist_firm_registry.json`

## Ingest config audit

- OK — site_index/press_wire firms have domains or aliases.

## Unknown / SEC filer IDs (top counts)

| Firm ID | Hits |
|---------|------|
| `sec_filer:brookfield_asset_management_inc` | 78 |
| `sec_filer:berkshire_hathaway_inc` | 27 |
| `sec_filer:warren_e_buffett` | 27 |
| `sec_filer:mjh_partners_ii_llc` | 25 |
| `sec_filer:mantle_ridge_lp` | 24 |
| `sec_filer:8194` | 15 |
| `sec_filer:s_advance_publications_inc` | 15 |
| `sec_filer:riot_platforms_inc` | 14 |
| `sec_filer:bbai_ultimate_holdings_llc_8199` | 11 |
| `sec_filer:camac_partners_llc` | 11 |
| `sec_filer:i_r_s_identification_nos_of_above_persons_entities_only_gabelli_funds_llc_i_d_no` | 11 |
| `sec_filer:s_i_r_s_identification_nos_of_above_persons_entities_only_fairholme_capital_mana` | 11 |
| `sec_filer:s_general_electric_company` | 10 |
| `sec_filer:bam_partners_trust` | 10 |
| `sec_filer:s_s_or` | 10 |
| `sec_filer:bitfury_group_limited` | 10 |
| `sec_filer:walgreens_boots_alliance_holdings_llc` | 10 |
| `sec_filer:rc_ventures_llc` | 10 |
| `sec_filer:kulayba_llc` | 10 |
| `sec_filer:fca_us_llc` | 9 |
| `sec_filer:i_r_s_identification_no_of_above_person_entities_only_berkshire_hathaway_inc` | 9 |
| `sec_filer:melinda_gates_foundation_trust` | 9 |
| `sec_filer:qvt_financial_lp` | 9 |
| `sec_filer:jhl_capital_group_llc` | 8 |
| `sec_filer:alibaba_group_holding_limited` | 7 |
| `sec_filer:ghaffarian_enterprises_llc` | 7 |
| `sec_filer:leon_d_black` | 6 |
| `sec_filer:berkshire_hathaway_inc_8199` | 6 |
| `sec_filer:cerberus_capital_management_ii_l_p` | 6 |
| `sec_filer:s_b_riley_financial_inc` | 6 |

## Sample unresolved rows

- **ACGL** `sec_filer:arch_capital_group_ltd_2` (sec_edgar) 2021-07-07
- **ACGL** `sec_filer:arch_capital_group_ltd_2` (sec_edgar) 2021-02-19
- **ACHR** `sec_filer:i_r_s_identification_nos_of_above_persons_entities_only_capri_growth_llc` (sec_edgar) 2024-11-18
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2024-07-03
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2024-03-15
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2024-03-08
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2024-01-10
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2023-10-18
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2023-07-20
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2023-06-27
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2023-05-22
- **ACHR** `sec_filer:fca_us_llc` (sec_edgar) 2023-05-09
- **ACHR** `sec_filer:i_r_s_identification_nos_of_above_persons_entities_only_capri_growth_llc` (sec_edgar) 2022-06-28
- **ACHR** `sec_filer:i_r_s_identification_nos_of_above_persons_entities_only_hight_drive_growth_llc` (sec_edgar) 2022-05-20
- **ACHR** `sec_filer:adam_goldstein` (sec_edgar) 2021-09-27
- **ACHR** `sec_filer:brett_adcock` (sec_edgar) 2021-09-27
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2024-10-29
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2024-10-08
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2023-07-18
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2023-06-13

## Inactive registry firms still indexed

- `citron` — review or remove from indexes

## Suggested JSON stub (human applies)

```json
{ "id": "new_firm_id", "name": "Publisher Name", "side": "short", "active": true, "ingest_methods": ["site_index"], "ingest_method": "site_index" }
```

