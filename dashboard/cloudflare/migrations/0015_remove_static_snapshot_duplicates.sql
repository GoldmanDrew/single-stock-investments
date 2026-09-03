-- These series are already published as versioned static dashboard shards and
-- have no D1 API readers. Drop the duplicate copies and their indexes without
-- touching operational, portfolio, or live market-risk data.
DROP TABLE IF EXISTS price_observations;
DROP TABLE IF EXISTS ohlcv_observations;
DROP TABLE IF EXISTS technical_snapshots;
DROP TABLE IF EXISTS capitulation_snapshots;
DROP TABLE IF EXISTS market_context_snapshots;
DROP TABLE IF EXISTS market_structure_snapshots;
