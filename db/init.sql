-- Projeto Maeve: Script de Inicialização do Banco de Dados (Supabase/PostgreSQL)

-- 1. Extensões (Habilitar se necessário)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Tabela de Conversas (Threads)
-- Armazena os metadados de cada sessão de chat.
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY, -- ID da thread (vinda do Telegram ou Gerada)
    user_id TEXT NOT NULL,
    title TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabelas do LangGraph Checkpointer
-- Nota: O LangGraph (AsyncPostgresSaver) cria automaticamente as tabelas 
-- 'checkpoints', 'checkpoint_blobs', 'checkpoint_writes' e 'checkpoint_metadata'.
-- No entanto, deixamos o schema aqui para referência ou criação manual se necessário.

-- 4. Tabela de Preferências do Usuário
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    preferences JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Índices para Performance
CREATE INDEX IF NOT EXISTS idx_threads_user_id ON threads(user_id);

-- 6. Trigger para atualização automática do updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;    
END;
$$ language 'plpgsql';

CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON threads FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
