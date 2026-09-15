-- Use somente quando migracao_canais_e_historico_bots.sql ja criou
-- id_bot_destino e processo_bot_envios, mas parou no erro de collation 1267.

USE gnpobras;

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

-- Esperado: tres linhas ativas com destinos GNP, BOOL e EDIT.
SELECT
    u.id,
    u.nome,
    u.id_telegram,
    u.is_active,
    b.codigo AS destino
FROM usuarios_crawler_python u
INNER JOIN bot_tipos b ON b.id = u.id_bot_destino
WHERE BINARY TRIM(u.id_telegram) IN (
    BINARY '-1002657878005',
    BINARY '-1004295198662',
    BINARY '-1003923426481'
)
ORDER BY b.codigo;
