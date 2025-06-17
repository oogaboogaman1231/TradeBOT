DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS broker_configs;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

CREATE TABLE broker_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    broker_name TEXT NOT NULL,
    api_key TEXT NOT NULL,
    secret_key TEXT NOT NULL,
    -- NOVO: Adicionamos a chave da OpenAI aqui
    openai_api_key TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Adicione um índice para garantir unicidade por user_id e broker_name
CREATE UNIQUE INDEX idx_user_broker ON broker_configs (user_id, broker_name);