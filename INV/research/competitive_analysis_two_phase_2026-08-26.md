# INV: Accelsius two-phase cooling competitive analysis

**Date:** 2026-08-26
**Agent:** Marvin
**Stance (unchanged):** watch. Capital authority remains `human_decision.json`.
**Companion:** [two_phase_cooling_watch.md](two_phase_cooling_watch.md)

This note updates the July 28 dive with the Q2 2026 10-Q (filed 2026-08-13), Accelsius commercial announcements, and NVIDIA's own two-phase research trail. It is not a replacement deep dive and does not rewrite `valuation.json`.

**Price used:** $1.51 Nasdaq close 2026-08-21 (Yahoo / Macrotrends). Live tape on 2026-08-26 was in the mid-$1.50s. July 28 dive used $2.96.

---

## Bottom line

Accelsius does **not** sell cooling systems to NVIDIA or AMD as customers. Those firms set thermal envelopes and bless reference designs. Accelsius sells **kits and rack systems** to data-center operators, server OEMs and value-added resellers, and it wants facility OEMs (Johnson Controls, Legrand) as channels. Vertiv sits on the other side of the table: it is the incumbent thermal OEM, and it is NVIDIA's named partner on the Department of Energy two-phase research program. That is the most important competitive fact in this file.

The two-phase physics story is real. GPU power is heading toward 1,500–2,500 watts, where single-phase water starts to struggle. NVIDIA engineers (Ali Heydari, Yaman Manaserh) have published that path. The leap from "NVIDIA is studying two-phase" to "Accelsius wins" is not automatic. NVIDIA's own OMNICOOL team is Vertiv plus Boyd, not Accelsius.

The public equity is a thin claim on that option. Innventure LLC owns **43.2%** of Accelsius (10-K as of 2026-03-23). Q2 cash is **$41.5 million** unrestricted against **$59.5 million** of operating cash used in the first half. Management says it needs **at least $50 million** at the parent plus **up to $25 million** for subsidiaries over the next twelve months, and it has disclosed **substantial doubt** about continuing as a going concern. Common shares went from 67.7 million at year-end 2025 to **84.6 million** on 2026-08-07. The stock is about half the July 28 price. Dilution is not a side risk. It is the main way this option gets paid for.

---

## 1. What Innventure is (and is not)

Innventure founds, funds, and operates companies around technology taken from large corporations. Public INV is the consolidating parent after the Learn CW combination (closed 2024-10-02). Three operating companies sit under it:

| Company | What it does | Innventure LLC economic ownership (2026-03-23) | Voting control |
|---------|--------------|-----------------------------------------------|----------------|
| Accelsius | Two-phase, direct-to-chip liquid cooling (NeuCool), IP from Nokia, productized as a pumped system | 43.2% | 58.8% |
| AeroFlexx | Flexible liquid packaging from P&G IP | 37.1% | 42.3% |
| Refinity | Plastic-waste-to-olefins process from VTT, Dow as collaborator | 68.5% of Refinity Holdings | 92.9% |

Directors, officers, employees and consultants own another 26.6% of Accelsius. The Innventus ESG Fund owns 3.4%. The rest is outside capital, including Johnson Controls and Legrand from the January 2026 Series B.

GAAP consolidates Accelsius with a large noncontrolling interest and about $323 million of goodwill. The economic claim on Accelsius is the **43.2% look-through**, not 100% of the subsidiary. PureCycle was an earlier Innventure company and is a separate public ticker. It is not in INV's equity claim.

CEO transition: Gregory Haskell retires as CEO and director effective 2026-10-01. William Grieco (Refinity CEO, Accelsius director, former Innventure CTO) becomes CEO. That is a plastics-and-process background at the parent, not a data-center cooling operator.

---

## 2. How NeuCool works

NeuCool is a closed-loop, two-phase, direct-to-chip system. A dielectric refrigerant boils on a cold plate sitting on the CPU or GPU. Vapor carries heat to a condenser. Liquid is pumped back. Water never touches the electronics. Accelsius says the design is field-serviceable and retrofit-ready in a standard rack, tied into existing facility water.

Claimed operating points (Accelsius site, not filing-audited): more than 4,500 watts per socket thermal headroom, 0.020 °C/W thermal resistance at 700 watts-plus, rack products IR150 (150 kW integrated rack) and MR250 (250 kW-plus row CDU). The 10-K says high-performance AI GPUs expected in 2026 may approach 2,000 watts per device, with packages projected toward 2,500 watts.

Go-to-market in the 10-K: **partnerships**. Accelsius delivers kitted systems for inclusion in partner servers. Some parts are common across CPUs and GPUs. Other parts are customized per server design. Typical commercial path: assessment, initial deployment, scaled deployment, ongoing service. Named commercial counterparties in filings are described only as OEMs, resellers, and operators. Named public counterparts from Accelsius IR: DarkNX (operator), Equus, Computacenter, IM Data Centers, lab deployments at Equinix Virginia, Telehouse London, Park Place Cleveland.

---

## 3. Who would they sell to?

**Not NVIDIA. Not AMD.** Those companies sell chips. They do not buy rack CDUs as a line of business. They publish cooling requirements, qualify vendors into MGX / Instinct reference architectures, and sometimes fund research. Accelsius being in **NVIDIA Inception** and listing H100, H200, B200, MI325X, and MI355X as *supported silicon* is a compatibility claim. It is not a purchase order.

The buying stack, top to bottom:

| Layer | Role vs Accelsius | Examples | What a "win" looks like |
|-------|-------------------|----------|-------------------------|
| Chip vendors | Specifiers, not customers | NVIDIA, AMD, Intel | Named in a chip-maker reference design or MGX/Instinct thermal guide |
| Thermal / facility OEMs | Channel **or** competitor | Vertiv, Johnson Controls, Legrand, nVent, CoolIT, Boyd, STULZ | OEM resale of NeuCool, or JCI/Legrand bundling with chillers and racks |
| Server OEMs / ODMs / VARs | Direct kit customers | Super Micro, Dell, HPE, Equus, Computacenter | Factory-integrated two-phase SKU |
| Operators | Direct system customers | Hyperscalers, neoclouds, colos, DarkNX | Production MW, not a lab rack |
| Hyperscalers | The reference customer that re-rates the stock | AWS, Google, Microsoft, Meta, Oracle | Named production deployment |

**Johnson Controls is the real strategic channel.** JCI led Accelsius's $65 million Series B (January 2026). Legrand joined. DarkNX's 300 MW Ontario campus announcement pairs NeuCool at the chip with JCI chillers at the facility. That is Closed Loop in the Innventure sense: the MNC is supposed to open a path to market.

**Vertiv is not that partner.** Accelsius co-sponsored a networking event with Vertiv at Data Centre World London 2025. That is hospitality, not distribution. Vertiv already sells liquid cooling at scale (including MegaMod HDX-style prefabricated modules). NVIDIA's ARPA-E OMNICOOL two-phase program names Vertiv and Boyd as co-PIs. If two-phase becomes required, Vertiv is the default incumbent to copy or absorb it.

**DarkNX is the largest announced operator win, and it is not a hyperscaler.** November 2025: agreement to deploy NeuCool across a planned 300 MW AI campus in Ontario. First two halls at 65 MW each, targeted 2026 and 2027. Magis onsite notes (2026-04-17) described a DarkNX contract around $55 million. The INV board treated a binding Accelsius contract **above $15 million** as Earnout milestone one (8-K / Q2 10-Q), issuing 1,999,854 common shares on 2026-04-17. Treat 300 MW as campus capacity, $15 million-plus as the filing-verified contract floor, and $55 million as Magis diligence for contract value. None of that is recognized H1 2026 revenue.

HyperStart (Data Center World 2026): Accelsius says "several" hyperscale AI cloud providers are in a structured validation program. No names. That is the right hunting ground. It is not yet a customer.

---

## 4. Two-phase landscape (who Accelsius actually fights)

The 10-K's own competitive map is still the cleanest:

| Technology | Accelsius view of the problem | Named peers |
|------------|-------------------------------|-------------|
| Single-phase immersion | Costly tanks, server warranty, service pain, limited headroom | LiquidStack, GRC, TMGCore |
| Two-phase immersion | Cost, trapped vapor, PFAS optics | LiquidStack, TMGCore, Submer |
| Single-phase direct-to-chip (water) | Leak risk, biofouling, high flow at high TDP | CoolIT, STULZ |
| Two-phase direct-to-chip (refrigerant) | Accelsius says only it and ZutaCore have **sold** this in market | ZutaCore; others expected |

That last sentence is the moat claim, and it is already aging. NVIDIA, Vertiv, and Boyd are building pumped two-phase cold plates and CDUs under OMNICOOL. JetCool, nVent, and others are in the high-TDP cold-plate race. IDTechEx's 2024-25 interviews put two-phase direct-to-chip volume "no earlier than 2026 and 2027," with single-phase struggling around 1,500 watts and hitting a wall near 2,000 watts.

**Why Accelsius could still matter:** dielectric fluid (no water on the board), retrofit in existing racks, claimed TCO edge vs single-phase (Jacobs analysis on Accelsius's site, third-party pending), and JCI/Legrand equity. Nokia-origin patents plus nine Accelsius-filed applications (10-K).

**Why it may not:** conservative buyers; Vertiv distribution; NVIDIA's research partners are not Accelsius; ZutaCore already sells two-phase; hyperscalers can dual-source; Accelsius is early-revenue with Austin fabrication that the 10-K says covers demand only through 2026.

---

## 5. NVIDIA and AMD: what they have actually said

### NVIDIA employees (this is the paper trail)

The "NVIDIA employees wrote about two-phase" point is true. It is public engineering, not a secret Accelsius endorsement.

| Person | Role | Artifact | Accelsius mentioned? |
|--------|------|----------|----------------------|
| Ali Heydari | NVIDIA Distinguished Engineer / Technical Director, data center cooling | Hot Chips 2024 tutorial "Next-Generation Cooling For NVIDIA Accelerated Computing"; ARPA-E OMNICOOL PI | No |
| Yaman Manaserh | NVIDIA Senior Mechanical Engineer | OMNICOOL 2026 slides; co-author on NSF two-phase D2C experiment paper | No |
| OMNICOOL team | NVIDIA + Vertiv + Boyd + Durbin Group + Binghamton + Villanova | DOE ARPA-E COOLERCHIPS; hybrid pumped two-phase + immersion; target >1 MW/rack, PUE <1.05, GWP <1 refrigerant | No. Partners are Vertiv and Boyd. |

Heydari's Hot Chips deck is the important one: NVIDIA treats liquid cooling as the path for accelerated computing, and two-phase as a research/next-gen architecture, while today's shipping high-end GPUs are still largely single-phase direct-to-chip. Jensen's 2026 comments that Vera Rubin is designed for liquid cooling with warm facility water (up to 45 °C) raise the whole liquid-cooling tide. They do not pick Accelsius.

Accelsius debuted the IR150 at NVIDIA GTC 2026 as an Inception member. That is booth proximity.

### AMD

Accelsius lists AMD EPYC Genoa/Turin and Instinct MI325X / MI355X as supported. No AMD reference-design press release was found in this pass. AMD is the second specifier to watch, and in some ways the more open one: Instinct deployments are less locked to NVIDIA's MGX/OEM stack. A named AMD thermal reference that includes NeuCool would be a real signal. It does not exist in our files today.

### What would actually move INV

1. NVIDIA or AMD **reference design** that names two-phase and a vendor (Accelsius, Vertiv, Boyd, ZutaCore).
2. A **named hyperscaler production** deployment, not a lab.
3. Vertiv **reselling** NeuCool (bull) versus Vertiv **shipping its own** two-phase at scale (bear).
4. Accelsius **revenue** catching up to the DarkNX headline.

Until (1) or (2), NVIDIA two-phase papers are industry tailwind, not an Accelsius contract.

---

## 6. Revenue, cash, debt, dilution (updated through Q2 2026)

Figures from the Q2 2026 10-Q (period ended 2026-06-30, filed 2026-08-13) unless noted. Dollar amounts in millions.

### Operating snapshot

| | Q1 2026 | Q2 2026 | H1 2026 | H1 2025 |
|--|---------|---------|---------|---------|
| Revenue | 1.44 | 0.95 | 2.40 | 0.70 |
| Operating loss | | (31.5) | (58.8) | (403.8)* |
| Net loss | (27.8) | (34.9) | (62.7) | (394.9)* |
| Net loss to INV stockholders | (20.8) | (26.5) | (47.3) | (227.2) |
| Adjusted EBITDA (company) | | (22.6) | (41.0) | (38.0) |
| Operating cash used | | | (59.5) | (36.8) |

\*Prior-year operating loss includes large goodwill impairments ($113 million in Q2 2025, $347 million H1 2025). Those are non-cash. Cash burn is the live constraint.

Q1 10-Q product split (XBRL): about **$1.32 million** of the $1.44 million was Accelsius-class product. Q2 sequential revenue **fell**. DarkNX is not yet a run-rate.

FY 2025 revenue was $2.06 million. Trailing twelve months around $3.8 million (StockAnalysis). Versus a ~$60 million half-year cash burn, Accelsius is still a prototype P&L.

### Balance sheet oxygen (2026-06-30)

| Item | Amount | Note |
|------|--------|------|
| Unrestricted cash | $41.5 | Down from $60.4 at year-end 2025 and $55.4 at Q1 |
| Restricted cash | $5.0 | WTI Facility minimum-cash covenant |
| Working capital | $11.7 | |
| Notes payable (carrying) | ~$29.0 | See debt table |
| Warrant liability | $28.7 | Mark-to-market; earnings noise |
| Earnout liability | $4.8 | |
| Goodwill / intangibles | $323.5 / $149.7 | GAAP, not cash |
| Accumulated deficit | $418.9 | |
| Common shares (2026-08-07) | 84,612,657 | 67.7 million at 2025-12-31 |

Management: **at least $50 million** needed at Innventure over the next 12 months, **plus up to $25 million** if subsidiaries do not raise on their own. Substantial doubt about going concern within one year of issuance.

H1 2026 already raised **$40.0 million** via registered common stock and **$13.3 million** under the Yorkville standby equity purchase agreement (SEPA). That is why share count jumped. SEPA is an ATM-like facility: cash today, dilution tomorrow, at the then market price.

### Debt (principal / carrying, Q2 10-Q)

| Instrument | Rate | Maturity | Amount | Dilution vector |
|------------|------|----------|--------|-----------------|
| WTI Facility (first tranche; later tranches no longer available) | 13.5% floor, prime+5 | 2028 amortizing | $16.5 million outstanding | Warrants at $0.01 (2024 and 2025 WTI warrants); $5 million cash lockbox |
| Accelsius term convertible notes | ~4% AFR | 2026-12-31 | $8.0 million | Converts into **Accelsius Series A units at $12.175**, not INV common, while WTI is outstanding |
| Accelsius related-party convertibles | 4–15% | 2026-12-31 | $4.4 million | Same Accelsius unit conversion |
| Yorkville convertible debentures | OID 10%, 5% payment premium historically | various | largely repaid/converted in 2025-26 | Converts into INV common; remaining access is a stated risk factor |

The Accelsius notes are the quiet ownership leak: about $12.4 million converting into Accelsius at the old Series A price. Versus a post-Series-B company that Magis marked in the low hundreds of millions, that is a few points of extra Accelsius dilution, not a wipeout. **Parent SEPA and primary equity are the large dilution.**

### Share-count path (already happened)

| Date | Common shares | What happened |
|------|---------------|---------------|
| 2025-12-31 | 67.7 million | Year-end |
| 2026-03-31 | 80.1 million | Primary issuance (~11.5 million shares, ~$37 million net in Q1 equity roll-forward) |
| 2026-04-17 | +2.0 million | Earnout milestone one (Accelsius contract >$15 million) |
| 2026-05-11 | 84.0 million | Q1 10-Q cover |
| 2026-08-07 | 84.6 million | Q2 10-Q cover; more SEPA / converts |

Antidilutive securities excluded from Q1 EPS (still overhang): preferred, warrants, options, earnout remainder, on the order of **tens of millions** of potential shares. Series B/C preferred pay 8% PIK. WTI warrants are $0.01 exercise.

July 28 model assumed 77.8 million weighted-average shares today and 100 million in year 5. Reality is already 84.6 million issued, with $50–75 million more capital needed at a ~$1.50 stock. At $1.50, $50 million of common is **33 million shares**. Year-5 100 million is too low unless Accelsius self-funds and the parent stops using SEPA.

---

## 7. Upside versus dilution (re-cut at $1.51)

July 28 `valuation.json` (not updated here): price $2.96, year-5 payoff $5.20, base **12%** per year, bull 30%, bear −21%. Stance watch. Accelsius year-5 enterprise value $1.2 billion at 40% ownership, 100 million shares.

**What changed:** price −49%, shares +25% vs year-end and +9% vs the July WASO, cash −$14 million from Q1, going-concern language, Q2 revenue down sequentially, NVIDIA-Vertiv-Boyd research stack confirmed.

### Look-through math (illustrative, not a new contract)

Assume year-5 diluted INV shares **120 million** (84.6 million plus ~35 million more from parent capital and leftover warrants/earnout). Accelsius ownership **35%** (from 43.2%, after convertibles and a further Accelsius round if needed). Residual AeroFlexx/Refinity $45 million, year-5 net cash $10 million, holdco drag −$20 million.

| Case | Accelsius EV | INV claim | Equity value | Per share | 5-year annualized vs $1.51 |
|------|--------------|-----------|--------------|-----------|----------------------------|
| Bear | $200 million (near post-Series-B) | $70 million | ~$70 million | ~$0.58 | about **−17%** per year |
| Base | $1.2 billion (July Magis-below-midpoint) | $420 million | ~$455 million | ~$3.80 | about **20%** per year |
| Bull | $2.5 billion (Magis high band) | $875 million at 35% | ~$910 million | ~$7.60 | about **38%** per year |

The July base return was 12% at $2.96. The stock is cheaper, so the **same Accelsius success** now implies a higher mechanical return. That is not a free lunch. Three things have to stay true:

1. Accelsius still reaches something like a $1 billion-plus franchise (DarkNX plus unnamed hyperscalers, not lab racks).
2. INV keeps roughly a third of Accelsius, not 15% after distressed parent raises and Accelsius Series C.
3. The parent does not issue 80 million more shares at $1.20 because SEPA is the only bid.

**Probability should be lower than July.** Q2 revenue did not inflect. NVIDIA's two-phase partners are Vertiv and Boyd. DarkNX is not AWS. Going concern is now in the 10-Q in so many words. Dhando remains **none**: the bear is still a cash-burn stub.

Cash floor today: $41.5 million / 84.6 million = **$0.49 per share**, and that cash is spoken for by burn. It is not a margin of safety.

If Accelsius were taken out tomorrow at Magis's $1–3 billion talk with INV at 43.2% and no extra parent dilution, the claim would be $430 million to $1.3 billion, or **$5 to $15 per INV share** on 84.6 million shares. That is the lottery ticket people are buying. It is also why Accelsius management and strategics may prefer a **private exit** of Accelsius rather than optimizing the public parent's per-share claim (July dive inversion, still live).

---

## 8. Inversion: how this fails

1. **Two-phase is right, Accelsius is not the vendor.** Vertiv/Boyd/ZutaCore take the NVIDIA/AMD reference. Accelsius remains a niche retrofit kit.
2. **Single-phase lasts longer.** Cold-plate and CDU improvements keep water viable through 2,000-watt parts. Two-phase stays "2028+."
3. **DarkNX slips or shrinks.** 300 MW campus headlines do not convert to Accelsius billings. Earnout already issued; revenue does not follow.
4. **Parent dilutes the option away.** SEPA plus another primary at $1.50, plus Accelsius raising without INV, takes the look-through under 25% with no cash proceeds (the July falsifier).
5. **Going concern becomes action.** Cost cuts hit Accelsius's 2027 capacity plan. WTI covenant ($5 million restricted cash) becomes binding.
6. **Incentives diverge.** Accelsius Series B strategics (JCI, Legrand) and Accelsius management optimize for a private strategic sale. Public INV holders keep the leftover.

---

## 9. What would make this "huge"

In order of how much it would change the INV equity, not how likely:

1. Named **hyperscaler production** (AWS, Google, Microsoft, Meta, Oracle, CoreWeave-class) with Accelsius as the two-phase vendor.
2. **NVIDIA or AMD reference design** that names NeuCool, or Vertiv OEM-reselling NeuCool.
3. Accelsius **revenue** run-rate that makes the $15 million earnout look small (tens of millions per quarter, not $1 million).
4. Accelsius **self-funded** so INV stops using SEPA. Ownership holds near 40%.
5. Strategic **exit** of Accelsius in the Magis $1–3 billion band while INV still owns ~40%.

Items 1–2 are what a NVIDIA/AMD watch is for. They are leading indicators. Item 3 is the only number that pays the parent bills.

---

## 10. Classification (unchanged)

| Field | Value |
|-------|-------|
| Archetype | holding_co |
| Moat | unproven |
| Dhando | none |
| Stance proposal | watch |
| Payoff lens | asset |
| Predictive attribute | Accelsius commercial adoption (hyperscaler or OEM reference, then revenue) |

`valuation.json` is stale (2026-07-28, $2.96, 77.8 million WASO). Do not use its 12% figure as live. Refresh after the Q2 10-Q is in the local folder.

---

## Sources

- INV FY2025 10-K (filed 2026-03-30): business, ownership, NeuCool, competition
- INV Q1 2026 10-Q (filed 2026-05-14): cash $55.4 million, WASO 77.8 million, going concern
- INV Q2 2026 10-Q (filed 2026-08-13): cash $41.5 million, H1 revenue $2.4 million, H1 operating cash use $59.5 million, $50 million / $25 million funding need, debt table, earnout
- INV 8-K 2026-06-30: Haskell retirement, Grieco CEO
- Magis Accelsius onsite 2026-04-17 (`INV/investor-documents/research-notes/2026-04-17_Accelsius.pdf`): Series A/B, DarkNX, exit talk
- Accelsius IR: Series B, DarkNX, IR150/GTC, HyperStart, supported silicon
- NVIDIA / ARPA-E: Heydari Hot Chips 2024; OMNICOOL slides 2025-26 (Manaserh); NSF two-phase D2C paper
- July 28 dive, thesis, `valuation.json`

**Third party:** Magis notes are Magis diligence (used in July valuation). Accelsius site Jacobs TCO claim and AAIG Substack are **[PENDING APPROVAL]** and not in any base return here.

---

## Addendum (same day): Q2 10-Q now local; 19 Aug board letter

Local harvest completed 2026-08-26. New files in `INV/investor-documents/sec-edgar/`:

- `10-Q_20260813_rpt20260630_acc0002001557_26_000154.htm` (Q2)
- `8-K_20260813_..._000152.htm` (Q2 earnings press)
- `8-K_20260819_..._057840.htm` (board letter, Item 7.01)

Primary text of the letter: https://www.innventure.com/news/innventure-board-issues-letter-to-shareholders

**DarkNX booking was removed.** The earnout shares issued on the Accelsius purchase order from DarkNX are being forfeited by senior management and directors. The Board says the shares were issued properly under 2023 contracts, then the booking that satisfied the milestone was taken off. That cuts the largest named Accelsius commercial win from "binding contract above $15 million" (Q2 10-Q) to a press-release campus that no longer supports the earnout. Treat DarkNX as a **broken booking**, not as contracted Accelsius revenue, until a replacement PO is filed.

Other board actions (capital, not cooling physics):

- Parent cash expense, excluding debt service, **$7.5 million to $4.5 million** per quarter. New company formation spend stops. Parent R&D goes to zero.
- AeroFlexx: advisors hired; strategic monetization and outside interim capital.
- Refinity: off the Innventure balance sheet after Q3 2026.
- Parent still exploring debt, equity, and asset sales. Dilution is not cancelled; the Board is trying to slow it.
- Accelsius scaled revenue "potentially as early as 2027." Board cites a two-phase direct-to-chip market of about **$500 million in 2027** growing to about **$3.8 billion in 2029**. Those are market estimates, not Accelsius guidance.

This strengthens the inversion in section 8: two-phase can still be the right industry bet while Accelsius's first large PO does not stick. It also concentrates remaining parent cash on Accelsius, which is the only remaining look-through that matters.
