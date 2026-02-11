-- Migration: Add trades table for TastyTrade audit logging
-- Version: 003
-- Date: 2026-02-11

-- =============================================================================
-- TRADES TABLE
-- =============================================================================

-- Stores executed trades for audit logging
CREATE TABLE IF NOT EXISTS trades (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    date DATE REFERENCES days(date) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(50) NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    order_id VARCHAR(100),
    status VARCHAR(20),
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('market', 'limit')),
    price DECIMAL(12, 4),
    instrument_type VARCHAR(20) DEFAULT 'equity' CHECK (instrument_type IN ('equity', 'option')),
    option_symbol VARCHAR(50),
    account_number VARCHAR(50),
    mode VARCHAR(10) DEFAULT 'sandbox' CHECK (mode IN ('sandbox', 'live')),
    related_interaction_id VARCHAR(255) REFERENCES interactions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades(order_id);

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE trades IS 'Audit log of executed trades through TastyTrade integration';
COMMENT ON COLUMN trades.mode IS 'Whether trade was executed in sandbox or live mode';
COMMENT ON COLUMN trades.option_symbol IS 'Full OCC option symbol for option trades';
