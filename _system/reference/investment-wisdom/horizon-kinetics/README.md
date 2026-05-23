# Horizon Kinetics — curated extracts

Text extracts from the full HK vault for Marvin's **Tier 3 mental models** (equity yield curve, predictive attributes, time arbitrage).

**Full vault (400+ PDFs):** `C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\`  
**Framework:** `_system/frameworks/mental_models.md`

These are **text extracts** (not PDFs) copied from `hk_pdfs/book/build/text/` for agent readability. Re-copy when updated commentaries are added to the vault.

| File | Source | Use when |
|------|--------|----------|
| `Stahl-Equity-Yield-Curve-extract.txt` | Compilation of Murray Stahl's Writings (© 2011 HK) | Plotting equity yield curve; time arbitrage mechanics |
| `HK-Q1-2025-Commentary-extract.txt` | Q1 2025 Market Commentary (Apr 2025) | Predictive attributes; SJT, Mesabi, HE case studies |
| `HK-Q3-2025-Commentary-extract.txt` | Q3 2025 Market Commentary (Oct 2025) | SJT NPI deficit; royalty trusts |
| `HK-Q1-2026-Commentary-extract.txt` | Q1 2026 Market Commentary (Apr 2026) | Royalty trust market-structure discounts |
| `Stahl-Worth-The-Time-Predictive-Attributes-extract.txt` | Worth The Time interview (Feb 2024) | Predictive vs descriptive attributes |

**Shelf PDFs (Stahl essays):** `_system/reference/investment-wisdom/stahl/`

**Refresh extracts:**

```powershell
$hk = "C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\book\build\text"
$dest = "_system/reference/investment-wisdom/horizon-kinetics"
Copy-Item "$hk\Q1-2025-Horizon-Kinetics-Commentary_Final.txt" "$dest\HK-Q1-2025-Commentary-extract.txt"
# … repeat for other files; see INDEX.md
```
