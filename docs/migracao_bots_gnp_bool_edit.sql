-- Migracao completa do banco gnpobras para os executores/destinos
-- GNP, BOOL e EDIT.
--
-- Premissas verificadas no banco de desenvolvimento:
--   pages.id                         INT UNSIGNED
--   plataformas.id                   MEDIUMINT
--   terms.id                         INT UNSIGNED
--   plataforma de obras              id = 4
--
-- Este arquivo NAO usa tabela temporaria nem variaveis de sessao.
-- As oito paginas novas do EDIT sao criadas inativas e sem jobs na fila.

USE gnpobras;

-- ============================================================================
-- 0. PRE-CHECKS: os resultados destas consultas devem estar vazios.
--    Se houver registros, interrompa a migracao e trate as duplicidades/orfaos.
-- ============================================================================

SELECT id_plataforma, id_page, COUNT(*) AS quantidade
FROM plataformas_page
GROUP BY id_plataforma, id_page
HAVING COUNT(*) > 1;

SELECT id_plataforma, id_page, COUNT(*) AS quantidade
FROM plataformas_page_queue
GROUP BY id_plataforma, id_page
HAVING COUNT(*) > 1;

SELECT id_page, id_plataforma, termo_busca, COUNT(*) AS quantidade
FROM plataformas_page_heuristica_busca
GROUP BY id_page, id_plataforma, termo_busca
HAVING COUNT(*) > 1;

SELECT q.id, q.id_plataforma, q.id_page
FROM plataformas_page_queue q
LEFT JOIN plataformas_page pp
  ON pp.id_plataforma = q.id_plataforma
 AND pp.id_page = q.id_page
WHERE pp.id IS NULL;

SELECT h.id, h.id_plataforma, h.id_page, h.termo_busca
FROM plataformas_page_heuristica_busca h
LEFT JOIN plataformas_page pp
  ON pp.id_plataforma = h.id_plataforma
 AND pp.id_page = h.id_page
WHERE pp.id IS NULL;

-- ============================================================================
-- 1. TABELA DE BOTS
-- ============================================================================

CREATE TABLE bot_tipos (
    id TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo VARCHAR(10) NOT NULL,
    descricao VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_bot_tipos_codigo (codigo)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

INSERT INTO bot_tipos (codigo, descricao, is_active)
VALUES
    ('GNP',  'Bot Obras GNP', 1),
    ('BOOL', 'Bot Bool', 1),
    ('EDIT', 'Bot Edit', 1);

-- ============================================================================
-- 2. EXECUTOR UNICO EM pages
-- ============================================================================

ALTER TABLE pages
ADD COLUMN id_bot_executor TINYINT UNSIGNED NULL AFTER `filter`,
ADD KEY idx_pages_bot_executor (id_bot_executor),
ADD CONSTRAINT fk_pages_bot_executor
    FOREIGN KEY (id_bot_executor)
    REFERENCES bot_tipos(id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

UPDATE pages p
INNER JOIN bot_tipos b
    ON b.codigo = CASE
        WHEN UPPER(TRIM(p.`filter`)) = 'BOOL' THEN 'BOOL'
        WHEN UPPER(TRIM(p.`filter`)) = 'EDIT' THEN 'EDIT'
        WHEN UPPER(TRIM(p.`filter`)) IN ('GNP', 'ALL') THEN 'GNP'
    END
SET p.id_bot_executor = b.id
WHERE UPPER(TRIM(p.`filter`)) IN ('GNP', 'BOOL', 'EDIT', 'ALL');

-- Deve retornar vazio antes do MODIFY NOT NULL.
SELECT id, name, `filter`
FROM pages
WHERE id_bot_executor IS NULL;

ALTER TABLE pages
MODIFY COLUMN id_bot_executor TINYINT UNSIGNED NOT NULL;

-- ============================================================================
-- 3. DESTINOS DAS PAGINAS
-- ============================================================================

CREATE TABLE page_bot_destinos (
    id_page INT UNSIGNED NOT NULL,
    id_bot_destino TINYINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_page, id_bot_destino),
    KEY idx_page_bot_destinos_bot (id_bot_destino),
    CONSTRAINT fk_page_bot_destinos_page
        FOREIGN KEY (id_page)
        REFERENCES pages(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,
    CONSTRAINT fk_page_bot_destinos_bot
        FOREIGN KEY (id_bot_destino)
        REFERENCES bot_tipos(id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- GNP: paginas GNP e os ALL antigos.
INSERT INTO page_bot_destinos (id_page, id_bot_destino)
SELECT p.id, b.id
FROM pages p
INNER JOIN bot_tipos b ON b.codigo = 'GNP'
WHERE UPPER(TRIM(p.`filter`)) IN ('GNP', 'ALL');

-- BOOL: paginas BOOL e os ALL antigos.
INSERT INTO page_bot_destinos (id_page, id_bot_destino)
SELECT p.id, b.id
FROM pages p
INNER JOIN bot_tipos b ON b.codigo = 'BOOL'
WHERE UPPER(TRIM(p.`filter`)) IN ('BOOL', 'ALL');

-- EDIT: somente paginas explicitamente EDIT. ALL antigo nao inclui EDIT.
INSERT INTO page_bot_destinos (id_page, id_bot_destino)
SELECT p.id, b.id
FROM pages p
INNER JOIN bot_tipos b ON b.codigo = 'EDIT'
WHERE UPPER(TRIM(p.`filter`)) = 'EDIT';

-- ============================================================================
-- 4. PERFIS DE VALIDACAO E RELACAO COM terms
-- ============================================================================

CREATE TABLE term_validation_profiles (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    valid JSON NOT NULL,
    valid_hash CHAR(64) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_term_validation_profiles_hash (valid_hash)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

ALTER TABLE terms
ADD COLUMN id_validation_profile INT UNSIGNED NULL AFTER `valid`,
ADD KEY idx_terms_validation_profile (id_validation_profile),
ADD CONSTRAINT fk_terms_validation_profile
    FOREIGN KEY (id_validation_profile)
    REFERENCES term_validation_profiles(id)
    ON UPDATE RESTRICT
    ON DELETE SET NULL;

-- ============================================================================
-- 5. AJUSTES DE INTEGRIDADE DA FILA E DA HEURISTICA
-- ============================================================================

ALTER TABLE plataformas_page_queue
MODIFY COLUMN id_plataforma MEDIUMINT NOT NULL,
MODIFY COLUMN id_page INT UNSIGNED NOT NULL;

ALTER TABLE plataformas_page
ADD CONSTRAINT uq_plataformas_page
UNIQUE (id_plataforma, id_page);

ALTER TABLE plataformas_page_queue
ADD CONSTRAINT uq_queue_plataforma_page
UNIQUE (id_plataforma, id_page);

ALTER TABLE plataformas_page_queue
ADD CONSTRAINT fk_queue_plataforma_page
FOREIGN KEY (id_plataforma, id_page)
REFERENCES plataformas_page (id_plataforma, id_page)
ON UPDATE RESTRICT
ON DELETE CASCADE;

ALTER TABLE plataformas_page_heuristica_busca
ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER termo_busca;

ALTER TABLE plataformas_page_heuristica_busca
ADD CONSTRAINT fk_heuristica_plataforma_page
FOREIGN KEY (id_plataforma, id_page)
REFERENCES plataformas_page (id_plataforma, id_page)
ON UPDATE RESTRICT
ON DELETE CASCADE;

-- ============================================================================
-- 6. OITO PAGINAS EXCLUSIVAS DO EDIT (INATIVAS)
-- ============================================================================

START TRANSACTION;

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20',
    'Agregados, pedra e material granular', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20',
    'Artefatos de concreto e drenagem', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20',
    'Asfalto, concreto e estabilizacao', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=saneamento&status=recebendo_proposta&tam_pagina=20',
    'Saneamento', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=saneamento&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20',
    'Maquinas e servicos por hora', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=conserva%C3%A7%C3%A3o%20vi%C3%A1ria&status=recebendo_proposta&tam_pagina=20',
    'Conservacao viaria', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=conserva%C3%A7%C3%A3o%20vi%C3%A1ria&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20',
    'Terraplenagem e preparacao', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20'
  );

INSERT INTO pages
    (url, name, status, is_active, created_at, updated_at, `filter`, id_bot_executor)
SELECT
    'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20',
    'Urbanizacao e infraestrutura urbana', 1, 0, NOW(), NOW(), 'EDIT', b.id
FROM bot_tipos b
WHERE b.codigo = 'EDIT'
  AND NOT EXISTS (
      SELECT 1 FROM pages p
      WHERE p.url = 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20'
  );

-- Relacao com a plataforma 4, ainda inativa.
INSERT IGNORE INTO plataformas_page
    (id_plataforma, id_page, data_ultima_busca, referencia_codigo, is_active, qtd_registros)
SELECT 4, p.id, NULL, '', 0, 0
FROM pages p
INNER JOIN bot_tipos b
  ON b.id = p.id_bot_executor
 AND b.codigo = 'EDIT'
WHERE p.url IN (
    'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=saneamento&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=conserva%C3%A7%C3%A3o%20vi%C3%A1ria&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20'
);

-- Destino EDIT das novas paginas.
INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=saneamento&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=conserva%C3%A7%C3%A3o%20vi%C3%A1ria&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
VALUES (
    (SELECT id FROM pages WHERE url = 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20' LIMIT 1),
    (SELECT id FROM bot_tipos WHERE codigo = 'EDIT' LIMIT 1)
);

-- ============================================================================
-- 7. VARIANTES SEGURAS DAS OITO PAGINAS NOVAS
-- ============================================================================

INSERT IGNORE INTO plataformas_page_heuristica_busca
    (id_page, id_plataforma, termo_busca, is_active, qtd_registros,
     data_ultima_busca, created_at, updated_at)
SELECT p.id, 4, v.termo_busca, 1, 0, NULL, NOW(), NOW()
FROM (
    SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20' AS url,
           'agregados' AS termo_busca
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20', 'pedra'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=agregados,%20pedra%20e%20material%20granular&status=recebendo_proposta&tam_pagina=20', 'material granular'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20', 'artefatos de concreto'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=artefatos%20de%20concreto%20e%20drenagem&status=recebendo_proposta&tam_pagina=20', 'artefatos de drenagem'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20', 'concreto e estabilizacao'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20', 'concreto'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=asfalto&status=recebendo_proposta&tam_pagina=20', 'estabilizacao'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20', 'maquinas'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=maquinas%20e%20servi%C3%A7os%20por%20hora&status=recebendo_proposta&tam_pagina=20', 'servicos por hora'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=conserva%C3%A7%C3%A3o%20vi%C3%A1ria&status=recebendo_proposta&tam_pagina=20', 'pavimentação'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20', 'terraplenagem'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=terraplenagem%20e%20prepara%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20', 'preparacao'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20', 'urbanização e vias'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20', 'urbanização'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20', 'infraestrutura urbana'
    UNION ALL SELECT 'https://pncp.gov.br/app/editais?pagina=1&q=urbaniza%C3%A7%C3%A3o%20e%20infraestrutura%20urbana&status=recebendo_proposta&tam_pagina=20', 'vias'
) v
INNER JOIN pages p ON p.url = v.url;

-- ============================================================================
-- 8. TRES PAGINAS BOOL COMPARTILHADAS COM EDIT
-- ============================================================================

UPDATE pages p
INNER JOIN bot_tipos b ON b.codigo = 'BOOL'
SET p.id_bot_executor = b.id
WHERE p.url IN (
    'https://pncp.gov.br/app/editais?pagina=1&q=drenagem&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=projeto%20de%20pavimenta%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=urbanistico&status=recebendo_proposta&tam_pagina=20'
);

INSERT IGNORE INTO page_bot_destinos (id_page, id_bot_destino)
SELECT p.id, b.id
FROM pages p
CROSS JOIN bot_tipos b
WHERE p.url IN (
    'https://pncp.gov.br/app/editais?pagina=1&q=drenagem&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=projeto%20de%20pavimenta%C3%A7%C3%A3o&status=recebendo_proposta&tam_pagina=20',
    'https://pncp.gov.br/app/editais?pagina=1&q=urbanistico&status=recebendo_proposta&tam_pagina=20'
)
AND b.codigo IN ('BOOL', 'EDIT');

-- ============================================================================
-- 9. NOVE PERFIS DE VALIDACAO (INSERT DIRETO, SEM @PROFILE)
-- ============================================================================

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Agregados, pedra e material granular' AS name,
           JSON_ARRAY(
             'BRITA','BRITA 0','BRITA 1','BRITA 2','BRITA 3','PO DE PEDRA',
             'PEDRISCO','RACHAO','PEDRA DETONADA','BASALTO','MATERIAL BRITADO',
             'AGREGADO','AGREGADOS','SAIBRO','CASCALHO','ARGILA','AREIA',
             'AREIA MEDIA','AREIA GROSSA','BASE DE BRITA GRADUADA',
             'SUB-BASE DE BRITA','MATERIAL PARA ATERRO','MATERIAL PARA BASE',
             'MATERIAL PARA SUB-BASE'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Artefatos de concreto e drenagem' AS name,
           JSON_ARRAY(
             'TUBO DE CONCRETO','TUBOS DE CONCRETO ARMADO','ADUELA',
             'ADUELAS DE CONCRETO','BLOCO DE CONCRETO','BLOCOS INTERTRAVADOS',
             'PISO INTERTRAVADO','MEIO-FIO DE CONCRETO','GUIA DE CONCRETO',
             'CORDAO DE CONCRETO','SARJETA DE CONCRETO',
             'BOCA DE LOBO PRE-MOLDADA','CAIXA DE CONCRETO',
             'POCO DE VISITA PRE-MOLDADO'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Asfalto, concreto e estabilizacao' AS name,
           JSON_ARRAY('CONCRETO','CONCRETO USINADO',
                      'CONCRETO COMPACTADO A ROLO','CCR') AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Drenagem e saneamento' AS name,
           JSON_ARRAY(
             'DRENAGEM PLUVIAL','REDE DE DRENAGEM','GALERIA PLUVIAL',
             'GALERIAS PLUVIAIS','MICRODRENAGEM','MACRODRENAGEM','DRENOS',
             'DRENO PROFUNDO','BOCA DE LOBO','BOCAS DE LOBO','CAIXA COLETORA',
             'CAIXA DE INSPECAO','CAIXA DE PASSAGEM','POCO DE VISITA','PV',
             'TUBULACAO PLUVIAL','TUBOS DE CONCRETO','ADUELAS','BUEIRO',
             'BUEIROS','TRAVESSIA','TRAVESSIA DE DRENAGEM','CANALIZACAO',
             'CANALIZACAO DE ARROIO','DESASSOREAMENTO','LIMPEZA DE VALAS',
             'LIMPEZA DE CORREGOS','REDE DE ESGOTO','ESGOTAMENTO SANITARIO',
             'REDE COLETORA','REDE DE AGUA','ABASTECIMENTO DE AGUA','ADUTORA',
             'DISTRIBUICAO DE AGUA','POCO TUBULAR','PERFURACAO DE POCO'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Maquinas e servicos por hora' AS name,
           JSON_ARRAY(
             'LOCACAO DE MAQUINAS','LOCACAO DE EQUIPAMENTOS',
             'LOCACAO DE ESCAVADEIRA','LOCACAO DE RETROESCAVADEIRA',
             'LOCACAO DE MOTONIVELADORA','LOCACAO DE ROLO COMPACTADOR',
             'LOCACAO DE PA CARREGADEIRA','LOCACAO DE CAMINHAO BASCULANTE',
             'LOCACAO DE TRATOR DE ESTEIRA','ESCAVADEIRA HIDRAULICA',
             'RETROESCAVADEIRA','MOTONIVELADORA','PATROLA','ROLO COMPACTADOR',
             'PA CARREGADEIRA','CAMINHAO BASCULANTE','CAMINHAO TRUCK',
             'CAMINHAO CACAMBA','CAMINHAO PIPA',
             'TRANSPORTE COM CAMINHAO BASCULANTE','SERVICOS COM ESCAVADEIRA',
             'SERVICOS COM RETROESCAVADEIRA','SERVICOS COM MOTONIVELADORA',
             'SERVICOS COM ROLO COMPACTADOR','SERVICOS COM CAMINHAO',
             'HORA MAQUINA','HORA CAMINHAO',
             'REGISTRO DE PRECOS PARA HORAS MAQUINA',
             'REGISTRO DE PRECOS PARA LOCACAO DE MAQUINAS'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Pavimentacao e conservacao viaria' AS name,
           JSON_ARRAY(
             'PAVIMENTACAO COM BLOCO INTERTRAVADO','BLOCO INTERTRAVADO',
             'PAVER','PAVS','PVS','PAVIMENTACAO EM PEDRA','PARALELEPIPEDO',
             'CALCAMENTO','RESTAURACAO DE PAVIMENTO',
             'RECOMPOSICAO DE PAVIMENTO','MANUTENCAO VIARIA',
             'CONSERVACAO DE VIAS','CONSERVACAO DE ESTRADAS',
             'CONSERVACAO DE ESTRADAS VICINAIS',
             'MANUTENCAO DE ESTRADAS VICINAIS','MELHORIA DE ESTRADAS',
             'REVESTIMENTO PRIMARIO','ENSAIBRAMENTO','PATROLAMENTO',
             'ENCASCALHAMENTO','MACADAME','BRITA GRADUADA',
             'BRITA GRADUADA SIMPLES','BGS'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Terraplenagem e preparacao' AS name,
           JSON_ARRAY(
             'TERRAPLANAGEM','TERRAPLENAGEM','MOVIMENTACAO DE TERRA','ESCAVACAO',
             'COMPACTACAO','NIVELAMENTO','CORTE E ATERRO','LIMPEZA DE TERRENO',
             'SERVICOS DE TERRAPLENAGEM','SERVICOS DE TERRAPLANAGEM',
             'EXECUCAO DE TERRAPLENAGEM','EXECUCAO DE TERRAPLANAGEM',
             'MOVIMENTO DE TERRA','MOVIMENTOS DE TERRA','ATERRO',
             'ATERRO COMPACTADO','ATERRO MECANICAMENTE COMPACTADO',
             'ESCAVACAO MECANICA','ESCAVACAO EM SOLO','ESCAVACAO EM ROCHA',
             'ESCAVACAO DE VALAS','REATERRO','REATERRO COMPACTADO',
             'CARGA E TRANSPORTE DE MATERIAL','TRANSPORTE DE MATERIAL',
             'BOTA-FORA','DESTINACAO DE MATERIAL','DESMONTE DE ROCHA',
             'REGULARIZACAO DO SUBLEITO','PREPARO DO SUBLEITO','SUBLEITO',
             'SUB-LEITO','BASE E SUB-BASE','BASE GRANULAR','SUB-BASE GRANULAR',
             'REFORCO DO SUBLEITO','RECOMPOSICAO DE ESTRADAS',
             'PATRULHA AGRICOLA','PATRULHA MECANIZADA','SERVICOS COM MAQUINAS',
             'HORAS MAQUINA'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Urbanizacao e infraestrutura urbana' AS name,
           JSON_ARRAY(
             'URBANIZACAO','REURBANIZACAO','INFRAESTRUTURA',
             'OBRAS DE INFRAESTRUTURA','INFRAESTRUTURA DE LOTEAMENTO',
             'IMPLANTACAO DE INFRAESTRUTURA','LOTEAMENTO URBANO',
             'ABERTURA DE RUA','ABERTURA DE RUAS','ABERTURA DE ESTRADA',
             'IMPLANTACAO DE VIA','IMPLANTACAO DE VIAS','SISTEMA VIARIO',
             'MALHA VIARIA','PROLONGAMENTO DE RUA','ALARGAMENTO DE VIA',
             'REQUALIFICACAO URBANA','PASSEIO PUBLICO','CALCADA','ACESSIBILIDADE',
             'MEIO-FIO','MEIO FIO','CORDAO','GUIA','SARJETA',
             'MEIO-FIO E SARJETA','CICLOVIA','CICLOFAIXA','PRACA',
             'PARQUE LINEAR','AREA DE LAZER','PAISAGISMO','CONTENCAO',
             'MURO DE CONTENCAO','GABIAO','ENROCAMENTO'
           ) AS valid
) d;

INSERT INTO term_validation_profiles (name, valid, valid_hash, is_active)
SELECT d.name, d.valid, SHA2(CAST(d.valid AS CHAR), 256), 1
FROM (
    SELECT 'EDIT - Urbanizacao e vias' AS name,
           JSON_ARRAY('LOTEAMENTO','ARRUAMENTO','PAVIMENTACAO','DRENAGEM',
                      'INFRAESTRUTURA URBANA','ABERTURA DE VIAS',
                      'ESTRADAS VICINAIS','REGULARIZACAO FUNDIARIA') AS valid
) d;

-- ============================================================================
-- 10. TERMS: ATUALIZA OS EXISTENTES E INSERE OS AUSENTES DIRETAMENTE
-- ============================================================================

-- Atualiza qualquer termo que ja exista, sem duplicar.
UPDATE terms t
INNER JOIN (
    SELECT 'agregados,_pedra_e_material_granular*' AS word, 'EDIT - Agregados, pedra e material granular' AS profile_name
    UNION ALL SELECT 'agregados*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'pedra*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'material_granular*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'artefatos_de_concreto_e_drenagem*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'artefatos_de_concreto*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'artefatos_de_drenagem*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'asfalto*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'concreto_e_estabilizacao*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'concreto*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'estabilizacao*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'drenagem*', 'EDIT - Drenagem e saneamento'
    UNION ALL SELECT 'saneamento*', 'EDIT - Drenagem e saneamento'
    UNION ALL SELECT 'maquinas_e_servicos_por_hora*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'maquinas*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'servicos_por_hora*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'conservacao_viaria*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'pavimentacao*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'projeto_de_pavimentacao*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'terraplenagem_e_preparacao*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'terraplenagem*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'preparacao*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'urbanistico*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao_e_infraestrutura_urbana*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'infraestrutura_urbana*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao_e_vias*', 'EDIT - Urbanizacao e vias'
    UNION ALL SELECT 'vias*', 'EDIT - Urbanizacao e vias'
) m ON LOWER(TRIM(t.word)) = LOWER(TRIM(m.word))
INNER JOIN term_validation_profiles p ON p.name = m.profile_name
SET t.id_validation_profile = p.id,
    t.is_active = 1,
    t.updated_at = NOW();

-- Insere os termos que ainda nao existem.
INSERT INTO terms
    (word, exceptions, valid, id_validation_profile, is_active, created_at, updated_at)
SELECT m.word, JSON_ARRAY(), JSON_ARRAY(), p.id, 1, NOW(), NOW()
FROM (
    SELECT 'agregados,_pedra_e_material_granular*' AS word, 'EDIT - Agregados, pedra e material granular' AS profile_name
    UNION ALL SELECT 'agregados*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'pedra*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'material_granular*', 'EDIT - Agregados, pedra e material granular'
    UNION ALL SELECT 'artefatos_de_concreto_e_drenagem*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'artefatos_de_concreto*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'artefatos_de_drenagem*', 'EDIT - Artefatos de concreto e drenagem'
    UNION ALL SELECT 'asfalto*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'concreto_e_estabilizacao*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'concreto*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'estabilizacao*', 'EDIT - Asfalto, concreto e estabilizacao'
    UNION ALL SELECT 'drenagem*', 'EDIT - Drenagem e saneamento'
    UNION ALL SELECT 'saneamento*', 'EDIT - Drenagem e saneamento'
    UNION ALL SELECT 'maquinas_e_servicos_por_hora*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'maquinas*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'servicos_por_hora*', 'EDIT - Maquinas e servicos por hora'
    UNION ALL SELECT 'conservacao_viaria*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'pavimentacao*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'projeto_de_pavimentacao*', 'EDIT - Pavimentacao e conservacao viaria'
    UNION ALL SELECT 'terraplenagem_e_preparacao*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'terraplenagem*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'preparacao*', 'EDIT - Terraplenagem e preparacao'
    UNION ALL SELECT 'urbanistico*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao_e_infraestrutura_urbana*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'infraestrutura_urbana*', 'EDIT - Urbanizacao e infraestrutura urbana'
    UNION ALL SELECT 'urbanizacao_e_vias*', 'EDIT - Urbanizacao e vias'
    UNION ALL SELECT 'vias*', 'EDIT - Urbanizacao e vias'
) m
INNER JOIN term_validation_profiles p ON p.name = m.profile_name
WHERE NOT EXISTS (
    SELECT 1 FROM terms t
    WHERE LOWER(TRIM(t.word)) = LOWER(TRIM(m.word))
);

COMMIT;

-- ============================================================================
-- 11. VERIFICACAO FINAL
-- ============================================================================

SELECT COUNT(*) AS bots FROM bot_tipos;

SELECT COUNT(*) AS paginas_exclusivas_edit
FROM pages p
INNER JOIN bot_tipos b ON b.id = p.id_bot_executor
WHERE b.codigo = 'EDIT';

SELECT COUNT(*) AS perfis_edit
FROM term_validation_profiles
WHERE name LIKE 'EDIT - %';

SELECT COUNT(*) AS terms_edit
FROM terms t
INNER JOIN term_validation_profiles p ON p.id = t.id_validation_profile
WHERE p.name LIKE 'EDIT - %';

SELECT COUNT(*) AS variantes_edit
FROM plataformas_page_heuristica_busca h
INNER JOIN pages p ON p.id=h.id_page
INNER JOIN bot_tipos b ON b.id=p.id_bot_executor
WHERE b.codigo='EDIT' AND h.id_plataforma=4;

SELECT p.id, p.name, p.is_active, e.codigo AS executor,
       GROUP_CONCAT(d.codigo ORDER BY d.codigo) AS destinos
FROM pages p
INNER JOIN bot_tipos e ON e.id = p.id_bot_executor
LEFT JOIN page_bot_destinos pd ON pd.id_page = p.id
LEFT JOIN bot_tipos d ON d.id = pd.id_bot_destino
GROUP BY p.id, p.name, p.is_active, e.codigo
ORDER BY p.id;

-- Esperado:
--   bots                    = 3
--   paginas_exclusivas_edit = 8 (todas inativas)
--   perfis_edit             = 9
--   terms_edit              = 28
--   variantes_edit          = 17
--   ALL antigos             = destinos BOOL,GNP (nunca EDIT)
--   Drenagem, Urbanistico e Projeto de pavimentacao = BOOL,EDIT

-- NAO ativar as oito paginas e NAO criar seus jobs antes da atualizacao
-- do codigo para separar os executores GNP, BOOL e EDIT.
