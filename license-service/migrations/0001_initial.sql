CREATE TABLE IF NOT EXISTS licenses (
    license_hash TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    max_devices INTEGER NOT NULL DEFAULT 3 CHECK (max_devices BETWEEN 1 AND 3),
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS activations (
    activation_id TEXT PRIMARY KEY,
    license_hash TEXT NOT NULL REFERENCES licenses(license_hash) ON DELETE CASCADE,
    device_hash TEXT NOT NULL,
    device_name TEXT NOT NULL DEFAULT '',
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    UNIQUE (license_hash, device_hash)
);

CREATE INDEX IF NOT EXISTS idx_activations_token_hash
    ON activations(token_hash);
