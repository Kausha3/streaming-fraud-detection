CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    transaction_id UUID NOT NULL,
    user_id TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    merchant TEXT NOT NULL,
    location TEXT NOT NULL,
    device_id TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    is_fraud BOOLEAN,
    fraud_score DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_tx_id ON transactions(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
