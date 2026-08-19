# Portfolio paper order entry

`Portfolio > Orders` includes an owner-locked paper order queue. It does not have an IBKR, Gateway, Python bridge, or live-order binding.

## Authorization

Cloudflare Access is the authority. The verified Access email is mapped server-side with two fail-closed secrets:

- `PORTFOLIO_DREW_ACCESS_EMAILS`
- `PORTFOLIO_MICHAEL_ACCESS_EMAILS`

Each value is a comma-separated email list. An email in neither list is read-only. An email in both lists is treated as a configuration error. The browser never chooses the authoritative owner.

For localhost testing only, `PORTFOLIO_AUTH_MODE=development` and `PORTFOLIO_DEVELOPMENT_OWNER=drew|michael` can create a local owner identity. The ordinary development bypass remains read-only when the second setting is absent.

## Paper-only boundary

- The Pages Function writes only to `portfolio_paper_orders` and append-only `portfolio_paper_order_events`.
- Stored rows are hard-coded to `mode=paper` and `transmitted=0`.
- The write endpoint accepts same-origin JSON requests with the explicit paper-mode header.
- Tickets are owner-filtered and idempotent. Cross-owner create returns `403`; cross-owner lookup/cancel returns `404`.
- Only exact IB contract IDs, positive quantities, positive limit prices, and DAY limit orders are accepted.
- The current release is a queue, not a fill simulator. It does not invent quotes, margin, fills, or P&L.

Future quote, what-if, policy-preview, and deterministic-fill work should remain in the private Portfolio Hub and use its `PaperOrderBroker`. It must not give the hosted Pages Function a live broker route.
