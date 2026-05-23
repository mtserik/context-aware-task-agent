-- Projeto Maeve: Configurações de Segurança e Row Level Security (RLS)
-- Este script configura o acesso granular aos dados baseando-se no user_id.

-- 1. Habilitar RLS em todas as tabelas
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Nota: As tabelas criadas automaticamente pelo LangGraph (checkpoints, etc) 
-- também devem ter RLS habilitado se forem expostas via API PostgREST.
-- Para o uso atual via Connection String direta (psycopg), o RLS se aplica 
-- se conectarmos com roles limitadas.

-- 2. Políticas para a tabela 'threads'
-- Permite que o usuário veja apenas suas próprias threads
CREATE POLICY "Users can view their own threads" 
ON threads FOR SELECT 
USING (auth.uid()::text = user_id OR (current_setting('app.current_user_id', true) = user_id));

-- Permite que o usuário insira suas próprias threads
CREATE POLICY "Users can insert their own threads" 
ON threads FOR INSERT 
WITH CHECK (auth.uid()::text = user_id OR (current_setting('app.current_user_id', true) = user_id));

-- Permite que o usuário atualize suas próprias threads
CREATE POLICY "Users can update their own threads" 
ON threads FOR UPDATE 
USING (auth.uid()::text = user_id OR (current_setting('app.current_user_id', true) = user_id));

-- 3. Políticas para a tabela 'user_preferences'
CREATE POLICY "Users can manage their own preferences" 
ON user_preferences FOR ALL 
USING (auth.uid()::text = user_id OR (current_setting('app.current_user_id', true) = user_id));

-- 4. Criar Role de Aplicação (Opcional - para uso em deploys cloud)
-- Se você quiser usar um usuário com menos privilégios que o 'postgres'
-- CREATE ROLE maeve_app_user NOLOGIN;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO maeve_app_user;
