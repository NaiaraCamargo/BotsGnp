-- Complemento obrigatorio para executar o codigo com os bots GNP, BOOL e EDIT.
-- Execute uma unica vez em cada banco (local e cliente), depois da migracao
-- migracao_bots_gnp_bool_edit.sql.

USE gnpobras;

-- Cada usuario/canal pertence a um destino. NULL significa ainda nao configurado
-- e nao recebera mensagens do crawler de obras.
ALTER TABLE usuarios_crawler_python
ADD COLUMN id_bot_destino TINYINT UNSIGNED NULL AFTER id_telegram,
ADD KEY idx_usuarios_bot_destino (id_bot_destino),
ADD CONSTRAINT fk_usuarios_bot_destino
    FOREIGN KEY (id_bot_destino)
    REFERENCES bot_tipos(id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

-- Historico independente por processo e destino. Ele evita que executaveis
-- concorrentes repitam uma notificacao ja entregue.
CREATE TABLE processo_bot_envios (
    id_processo VARCHAR(36)
        CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL,
    id_bot_destino TINYINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    enviado_em DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_processo, id_bot_destino),
    KEY idx_processo_bot_envios_destino_status
        (id_bot_destino, status),
    CONSTRAINT fk_processo_bot_envios_processo
        FOREIGN KEY (id_processo)
        REFERENCES processos(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,
    CONSTRAINT fk_processo_bot_envios_destino
        FOREIGN KEY (id_bot_destino)
        REFERENCES bot_tipos(id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Canais oficiais GNP, BOOL e EDIT.
UPDATE usuarios_crawler_python u
INNER JOIN (
    SELECT 'GNP' AS codigo, 'GrupoObras' AS nome, '-1002657878005' AS id_telegram
    UNION ALL SELECT 'BOOL', 'GrupoObrasBool', '-1004295198662'
    UNION ALL SELECT 'EDIT', 'GrupoObrasEdit', '-1003923426481'
) canal ON BINARY canal.id_telegram = BINARY TRIM(u.id_telegram)
INNER JOIN bot_tipos b ON BINARY b.codigo = BINARY canal.codigo
SET u.nome = canal.nome,
    u.is_active = 1,
    u.id_bot_destino = b.id;

INSERT INTO usuarios_crawler_python
    (nome, is_active, id_telegram, email, id_bot_destino)
SELECT
    canal.nome, 1, canal.id_telegram, NULL, b.id
FROM (
    SELECT 'GNP' AS codigo, 'GrupoObras' AS nome, '-1002657878005' AS id_telegram
    UNION ALL SELECT 'BOOL', 'GrupoObrasBool', '-1004295198662'
    UNION ALL SELECT 'EDIT', 'GrupoObrasEdit', '-1003923426481'
) canal
INNER JOIN bot_tipos b ON BINARY b.codigo = BINARY canal.codigo
WHERE NOT EXISTS (
    SELECT 1
    FROM usuarios_crawler_python u
    WHERE BINARY TRIM(u.id_telegram) = BINARY canal.id_telegram
);

-- Confira os IDs dos usuarios/canais antes de classifica-los.
SELECT
    u.id,
    u.nome,
    u.id_telegram,
    u.is_active,
    b.codigo AS destino_atual
FROM usuarios_crawler_python u
LEFT JOIN bot_tipos b ON b.id = u.id_bot_destino
ORDER BY u.id;

-- Esperado: GNP, BOOL e EDIT com pelo menos um canal ativo antes de ligar
-- todos os executaveis. Nao e necessario repetir o vinculo em cada pagina.
SELECT
    b.codigo,
    COUNT(u.id) AS canais_ativos
FROM bot_tipos b
LEFT JOIN usuarios_crawler_python u
    ON u.id_bot_destino = b.id
   AND u.is_active = 1
   AND u.id_telegram IS NOT NULL
   AND TRIM(u.id_telegram) <> ''
WHERE b.codigo IN ('GNP', 'BOOL', 'EDIT')
GROUP BY b.id, b.codigo
ORDER BY b.codigo;

-- Conferencia final da estrutura: esperado 2 colunas e 1 tabela.
SELECT
    (SELECT COUNT(*)
     FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'usuarios_crawler_python'
       AND column_name = 'id_bot_destino') AS coluna_destino_usuario,
    (SELECT COUNT(*)
     FROM information_schema.tables
     WHERE table_schema = DATABASE()
       AND table_name = 'processo_bot_envios') AS tabela_historico,
    (SELECT COUNT(*)
     FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'processo_bot_envios'
       AND column_name IN ('id_processo', 'id_bot_destino', 'status'))
        AS colunas_principais_historico;
