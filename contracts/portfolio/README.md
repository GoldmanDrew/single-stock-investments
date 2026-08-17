# Portfolio hub contracts

These JSON Schemas are the versioned boundary between the IBKR bridge, strategy producers, the local ledger, and the hosted read model.

Numbers that participate in reconciliation are decimal strings. Instrument identity is `account_alias + conid + model_code`; ticker is display metadata only. A snapshot with `complete=false` means unknown/incomplete, never an empty account. Strategy rows declare their reconciliation role and exposure basis so overlays and research products cannot be silently added to broker totals.
