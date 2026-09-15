-- Execute somente depois de:
--   1) aplicar migracao_canais_e_historico_bots.sql;
--   2) cadastrar o canal EDIT em usuarios_crawler_python.id_bot_destino;

USE gnpobras;

START TRANSACTION;

UPDATE pages p
INNER JOIN bot_tipos b
    ON b.id = p.id_bot_executor
   AND b.codigo = 'EDIT'
SET p.is_active = 1,
    p.updated_at = NOW();

UPDATE plataformas_page pp
INNER JOIN pages p ON p.id = pp.id_page
INNER JOIN bot_tipos b
    ON b.id = p.id_bot_executor
   AND b.codigo = 'EDIT'
SET pp.is_active = 1;

INSERT INTO plataformas_page_queue
    (id_plataforma, id_page, prioridade, status, attempts, max_attempts,
     next_run_at, created_at, updated_at)
SELECT
    pp.id_plataforma,
    pp.id_page,
    100,
    'queued',
    0,
    3,
    NOW(),
    NOW(),
    NOW()
FROM plataformas_page pp
INNER JOIN pages p ON p.id = pp.id_page
INNER JOIN bot_tipos b
    ON b.id = p.id_bot_executor
   AND b.codigo = 'EDIT'
WHERE pp.id_plataforma = 4
  AND pp.is_active = 1
  AND NOT EXISTS (
      SELECT 1
      FROM plataformas_page_queue q
      WHERE q.id_plataforma = pp.id_plataforma
        AND q.id_page = pp.id_page
  );

COMMIT;

-- Esperado: todas as paginas EDIT ativas e com uma linha de fila.
SELECT
    p.id,
    p.name,
    p.is_active AS page_ativa,
    pp.is_active AS plataforma_page_ativa,
    q.status AS status_fila
FROM pages p
INNER JOIN bot_tipos b
    ON b.id = p.id_bot_executor
   AND b.codigo = 'EDIT'
LEFT JOIN plataformas_page pp
    ON pp.id_page = p.id
   AND pp.id_plataforma = 4
LEFT JOIN plataformas_page_queue q
    ON q.id_page = p.id
   AND q.id_plataforma = 4
ORDER BY p.name;
