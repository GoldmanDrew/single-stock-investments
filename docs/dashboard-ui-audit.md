# Dashboard front page and valuation UI audit

## Executive finding

The dashboard has strong data density and a coherent research-console visual
language, but it gives infrastructure, decision state, and research detail
nearly equal visual weight. Its single job should be clearer:

> Show the next investable decision and the next machine action required to
> make that decision trustworthy.

The recommended signature element is a **decision spine**:

```text
Ticker -> Power Zone -> Approved method -> Evidence gate -> Value/return -> Next machine action
```

Keep the current dark research-terminal identity. Spend color only on state:
cyan for route/method, amber for unreviewed routes, red for blockers, and green
only for decision-grade output.

## Highest-priority findings

### P0 — modeled details render after the entire table

`dashboard/index.html:453` changes a selected modeled security to a one-column
layout. The detail panel then appears after all 757 table rows. In the live
test, Citigroup's detail started roughly 49,000 px below the top of the page.
Selecting a queue item did not bring the user to the detail.

**Recommendation:** make modeled detail a right-side drawer or a dedicated
ticker route. Keep a sticky decision spine at the top and leave the holdings
list in place. As an interim fix, scroll the detail into view after selection.

### P0 — the visible valuation queue is not the full recovery queue

The valuation page shows 30 curated queue names and 11 blocked names, while the
new all-universe recovery build finds 731 blocked tickers and 2,182 blockers.
The current page therefore reads like an operational queue but represents a
smaller rollout/validation queue.

**Recommendation:** separate two concepts:

- **Decision queue:** names close enough to evaluate.
- **Evidence operations:** every blocked ticker, due collector, retry time,
  terminal unavailable state, and source failure.

Use the D1 task API as the source for the second view.

### P1 — mobile is not usable as an operating view

At a 390 px viewport, the page had 542 px of horizontal content. The summary
strip consumed about 755 px vertically and the filters another 510 px before
the table. The primary navigation also ran off screen.

**Recommendation:** on mobile show only 4 decision KPIs, move remaining
infrastructure metrics behind “System health,” and put filters in a drawer.
Use a contained horizontal table scroller so the whole page never overflows.

### P1 — valuation is not a valid deep link

`dashboard/index.html:1128` recognizes Insights, Activist, and Darwin routes but
omits Valuation. A refresh or direct visit to `#/valuation` does not restore the
valuation page.

**Recommendation:** include `valuation` in the route parser and add a route
test for every top-level tab.

### P1 — clickable rows are inaccessible

The holdings rows and valuation queue rows are `<tr>` elements with click
listeners (`dashboard/valuation-viz.js:633`). They are absent from the
interactive accessibility tree and cannot be opened by keyboard.

**Recommendation:** put a real ticker link/button inside the first cell. Keep
row-wide pointer behavior only as an enhancement.

## Front page hierarchy

### Replace the top seven cards

The seven `dashboard/index.html:68` cards wrap with the last card orphaned at
common laptop widths, creating a large empty block. Most cards describe
repository infrastructure rather than decisions.

Lead with:

1. **Due now** — eligible evidence tasks.
2. **Route review** — default Power Zone routes.
3. **Compiler ready** — complete typed evidence, awaiting valuation run.
4. **Decision-grade** — current trustworthy values.
5. **Stale** — facts/price/model outside freshness policy.

Move PDFs, README coverage, research directories, and model counts into a
compact “System health” disclosure.

### Reduce filter weight

The current market, sleeve, valuation, and optional-column filters occupy three
full rows and compete with the table.

- Keep search plus 3 high-frequency views: **Due**, **Blocked**, **Decision-grade**.
- Put Market, Sleeve, Method, Power Zone, and Columns in a filter panel.
- Show active filters as removable chips.
- Persist view/filter/sort state in the URL.
- Add a results count and “clear filters” action.

### Clarify return columns

“vs price” and “IRR” can display different concepts, including a house thesis
IRR when the workbench return is missing. Rename and qualify:

- **Value vs price** — low/base/high value gap.
- **Expected annual return** — method, horizon, and as-of date visible.
- Show `—` for a blocked, non-comparable fallback instead of making two
  different return concepts look equivalent.

## Valuation page hierarchy

### Proposed operating layout

```text
+-----------------------------------------------------------------------+
| Due now  | Route review | Compiler ready | Decision-grade | Stale     |
+-----------------------------------------------------------------------+
| Search | Status | Power Zone | Method | Collector | Due | More filters |
+-----------------------------------------------------------------------+
| Priority | Ticker | Route -> method | Evidence progress | Next action |
| Critical | C      | Credit -> excess return | 4/7 | Retry SEC facts  |
| High     | TPL    | Scarce -> NAV + royalty | 8/12| Fetch unit data  |
+------------------------------------------------------+----------------+
| Queue                                                | Decision spine |
|                                                      | selected name  |
+------------------------------------------------------+----------------+
```

### Show route and method separately

The current Method column often displays a broad profile. Show:

- Power Zone profile and route confidence/status;
- exact approved compiler method and version;
- composite components for scarce-asset names;
- whether the route is reviewed or `default_needs_review`.

### Make the next action executable

Replace dense gap prose with:

- short acceptance-test title;
- source collector;
- attempt count and next retry;
- last error;
- evidence freshness;
- “View sources” and “View proof” actions.

### Compress ticker detail

The selected-security detail repeats decision metrics and exposes nine
workbench tabs plus additional long sections. Reduce the primary structure to:

1. **Decision**
2. **Evidence**
3. **Model & proof**
4. **History**

The decision spine stays visible across all four. Power Zone should name the
route and method, not repeat a long persona-chip inventory above the workbench.

## Accessibility and interface-quality findings

- `dashboard/index.html:99` removes the search outline without an equivalent
  focus-visible ring.
- The main search has no programmatic label or `name`.
- Onboarding form labels at `dashboard/index.html:781` are not associated with
  their controls.
- Workbench buttons have `role="tablist"` but no `role="tab"`,
  `aria-selected`, or keyboard arrow behavior.
- There is no skip link, semantic main landmark, or page-level heading.
- Large tables render hundreds of rows without virtualization or
  `content-visibility`.
- Numeric columns should consistently use tabular numerals.
- Add `color-scheme: dark`, a matching theme color, and preconnects for the
  Google font origin.

## Recommended implementation sequence

1. Fix the detail-panel position, valuation deep link, keyboard row actions,
   and focus states.
2. Replace the top strip with decision KPIs and move infrastructure to System
   health.
3. Add the D1-powered evidence operations queue.
4. Add Power Zone -> method -> evidence progress to each valuation row.
5. Make mobile filters a drawer and constrain table overflow.
6. Consolidate ticker detail into the four-section decision spine.
