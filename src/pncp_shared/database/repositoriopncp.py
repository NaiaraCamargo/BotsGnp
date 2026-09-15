import mysql
from ast import literal_eval
from uuid import uuid4
import mysql.connector
import json
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta
import mysql.connector.plugins.mysql_native_password
from pncp_shared.config.controle_config import config
from pncp_shared.logs.controle_logs import logs
from pncp_shared.utils.funcoespncp import limpar_cnpj, validar_campo_banco


LIMITE_TERMOS_PROCESSO = 4000


def _conectar_banco():
    return mysql.connector.connect(host=config('host'), port=int(config('port')), user=config('user'),
                                   password=config("password"), database=config("database"), auth_plugin='mysql_native_password')


def retornar_urls(plataforma):
    try:
        retorno_aux = {}
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute('''SELECT pages.id AS pagina_id, pages.url, plataformas_page.data_ultima_busca,
                    usuarios_crawler_python.id_telegram, plataformas_page.qtd_registros FROM plataformas_page
                    INNER JOIN plataformas ON plataformas.id=plataformas_page.id_plataforma
                    INNER JOIN plataforma_page_usuarios ON plataforma_page_usuarios.id_plataforma_pages=plataformas_page.id
                        AND plataforma_page_usuarios.is_active=1
                    INNER JOIN usuarios_crawler_python
                        ON usuarios_crawler_python.id=plataforma_page_usuarios.id_usuario_crawler_python
                        AND usuarios_crawler_python.is_active=1
                    INNER JOIN pages ON pages.id=plataformas_page.id_page
                    WHERE plataformas_page.is_active=1 AND plataformas.descricao=%s
                        AND usuarios_crawler_python.id_telegram IS NOT NULL
                        AND TRIM(usuarios_crawler_python.id_telegram)<>'' ''', (plataforma,))

                for r in cursor.fetchall():
                    # r[1] é a url que esta sendo utilizada como chave
                    if r[1] not in retorno_aux:
                        retorno_aux[r[1]] = {
                            'id_pagina': r[0],
                            'ultima_data': r[2],
                            'ids_usuario': [r[3].strip()],
                            'qtd_registros': r[4]
                        }
                    else:
                        if r[3].strip() not in retorno_aux[r[1]]['ids_usuario']:
                            retorno_aux[r[1]]['ids_usuario'].append(r[3].strip())
        return retorno_aux

    except Exception as e:
        print(f"Erro ao retornar_urls - {str(e)}")
        logs.error(f"Erro ao retornar_urls - {str(e)}", exc_info=True )

def retornar_dicionario_filtros(word, manter_word=False):
    try:
        filtros_aux = {}
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""SELECT word, exceptions FROM terms
                    WHERE is_active=1 AND LOWER(TRIM(word))=LOWER(TRIM(%s))""", (word,))
                termos = cursor.fetchall()

                for termo in termos:
                    palavra = termo[0].strip() if manter_word else termo[0].replace("*", "").strip()
                    filtros_aux[palavra] = _carregar_lista_json(termo[1])

        return filtros_aux
    except Exception as e:
        logs.error(f"Nao foi possivel carregar os filtros do Banco: {e}", exc_info=True)
        return {}


def _carregar_lista_json(valor):
    if valor in (None, ""):
        return []

    if isinstance(valor, list):
        return valor

    try:
        carregado = json.loads(valor)
    except (TypeError, ValueError):
        try:
            carregado = literal_eval(str(valor))
        except (TypeError, ValueError, SyntaxError):
            return []

    return carregado if isinstance(carregado, list) else []

def atualizar_ultima_data(id_pagina):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(f"""UPDATE plataformas_page SET data_ultima_busca = '{datetime.now()}' 
                                   WHERE id_page = {id_pagina};""")
                conexao.commit()

    except Exception as e:
        logs.error(f"Erro ao atualizar a ultima data: {str(datetime.now())} - pagina: {str(id_pagina)} - {str(e)}")

def atualizar_envio_notificacao(novo_id, cursor, editalnovo):
    try:
        cursor.execute(f"""UPDATE processos SET 
                                envio_notificacao = '{datetime.now()}'
                            WHERE id = '{novo_id}'""")
    except Exception as e:
        logs.info(f"""Erro ao atualizar data de envio da notificação - {str(editalnovo)} - {str(e)}""")


def retornar_plataformas(id_plat=''):
    plataformas = {}
    with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute(f"""SELECT plataformas.id AS id_plataforma, plataformas.descricao AS descricao_plataforma,
                    plataformas_page.id AS id_plataforma_page, plataformas_page.id_page AS id_page,
                    plataformas_page.referencia_codigo AS instrucao, plataformas_page.is_active AS pagina_plataforma_ativa,
                    usuarios_crawler_python.id AS usuario_id, usuarios_crawler_python.nome AS usuario_nome,
                    usuarios_crawler_python.is_active AS usuario_ativo, usuarios_crawler_python.id_telegram AS usuario_id_telegram,
                    usuarios_crawler_python.email AS usuario_email, pages.url AS url FROM plataformas
                    INNER JOIN plataformas_page ON plataformas.id=plataformas_page.id_plataforma
                    INNER JOIN plataforma_page_usuarios ON plataformas_page.id=plataforma_page_usuarios.id_plataforma_pages
                    INNER JOIN usuarios_crawler_python ON plataforma_page_usuarios.id_usuario_crawler_python=usuarios_crawler_python.id
                    INNER JOIN pages ON pages.id=plataformas_page.id_page
                    {'' if id_plat == '' else f'AND plataformas.id = {id_plat}'}""")
                for r in cursor.fetchall():
                    if r['id_plataforma'] not in plataformas:
                        plataformas[r['id_plataforma']] = {
                            'id_plataforma': r['id_plataforma'],
                            'nome': r['descricao_plataforma'],
                            'urls': {
                                r['url']: {
                                    'id_page': r['id_page'],
                                    'ativo': 'true' if r['pagina_plataforma_ativa'] == 1 else 'false',
                                    'id_plataforma_page': r['id_plataforma_page'],
                                    'instrucao': r['instrucao'],
                                    'usuarios': [r['usuario_id_telegram']]
                                }
                            }
                        }
                    else:
                        if r['url'] not in plataformas[r['id_plataforma']]['urls']:
                            plataformas[r['id_plataforma']]['urls'][r['url']] = {
                                'id_page': r['id_page'],
                                'ativo': 'true' if r['pagina_plataforma_ativa'] == 1 else 'false',
                                'id_plataforma_page': r['id_plataforma_page'],
                                'instrucao': r['instrucao'],
                                'usuarios': [r['usuario_id_telegram']]
                            }
                        elif r['usuario_id_telegram'] not in plataformas[r['id_plataforma']]['urls'][r['url']]['usuarios']:
                            plataformas[r['id_plataforma']]['urls'][r['url']]['usuarios'].append(r['usuario_id_telegram'])

    return plataformas


def retornar_usuarios():
    usuarios = {}
    with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""SELECT usuarios_crawler_python.id AS id_usuario, usuarios_crawler_python.nome AS nome_usuario,
                    usuarios_crawler_python.is_active AS usuario_ativo, usuarios_crawler_python.id_telegram AS id_telegram,
                    usuarios_crawler_python.email AS email, plataforma_page_usuarios.is_active AS usuario_pagina_ativo,
                    plataformas_page.id_plataforma AS id_plataforma, pages.id AS pagina_id, pages.url AS url
                    FROM usuarios_crawler_python
                    INNER JOIN plataforma_page_usuarios
                        ON plataforma_page_usuarios.id_usuario_crawler_python=usuarios_crawler_python.id
                    INNER JOIN plataformas_page ON plataformas_page.id=plataforma_page_usuarios.id_plataforma_pages
                    INNER JOIN pages ON plataformas_page.id_page=pages.id""")

                for r in cursor.fetchall():
                    if r["id_usuario"] not in usuarios:
                        usuarios[r["id_usuario"]] = {
                            "nome": r['nome_usuario'],
                            "id_usuario": r["id_usuario"],
                            "id_telegram": r['id_telegram'],
                            "ativo": 'false' if r['usuario_ativo'] is None or r['usuario_ativo'] == 0 else 'true',
                            "urls": {
                                r['url']: {
                                    'pagina_ativo': 'false' if r['usuario_pagina_ativo'] is None or r['usuario_pagina_ativo'] == 0 else 'true',
                                    'id_url': r['pagina_id'],
                                    'id_plataforma': r['id_plataforma']
                                }
                            }
                        }
                    else:
                        usuarios[r["id_usuario"]]["urls"][r['url']] = {
                            'pagina_ativo': 'false' if r['usuario_pagina_ativo'] is None or r['usuario_pagina_ativo'] == 0 else 'true',
                            'id_url': r['pagina_id'],
                            'id_plataforma': r['id_plataforma']
                        }
    return usuarios


def retornar_paginas(url=''):
    paginas = []
    with _conectar_banco() as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            cursor.execute(f"""select * from pages {'' if url == '' else f" WHERE pages.url = '{url}'"}""")
            for pagina in cursor.fetchall():
                paginas.append(pagina)

    return paginas
       
def atualizar_heuristica(id_pagina: int, qtd_itens: int):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                # Atualiza e registra se realmente afetou linha
                cursor.execute("""UPDATE plataformas_page SET qtd_registros=%s WHERE id_page=%s""",
                               (int(qtd_itens), int(id_pagina)))

                afetadas = cursor.rowcount
            conexao.commit()

        if afetadas == 0:
            logs.error(f"[heuristica] UPDATE sem efeito (id_page não encontrado?) id_page={id_pagina}, qtd={qtd_itens}")

    except Exception as e:
        logs.error(f"[heuristica] Erro ao atualizar id_page={id_pagina}, qtd={qtd_itens} -> {e}", exc_info=True)

def verificar_existencia_edital_new(link):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                resultado = None

                # Buscar por link
                if link != "":
                    cursor.execute("""SELECT p.id, p.termos, p.id_page, pg.filter FROM processos p
                        LEFT JOIN pages pg ON pg.id=p.id_page WHERE p.link=%s
                        ORDER BY p.created_at ASC, p.id ASC LIMIT 1""", (link,))
                    resultado = cursor.fetchone()
                   
            return resultado
               
    except Exception as e:
        logs.info(f"""Erro verificar_existencia_edital_new nao foi possivel conectar ao banco - {str(e)}""")
        return None


@contextmanager
def bloquear_processamento_edital(link: str, timeout_segundos: int = 0):
    """Impede que executaveis diferentes processem o mesmo link ao mesmo tempo."""
    conexao = None
    nome_lock = "pncp_edital_" + hashlib.sha256(str(link or "").strip().encode("utf-8")).hexdigest()[:40]
    adquirido = False

    try:
        conexao = _conectar_banco()
        with conexao.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (nome_lock, int(timeout_segundos)))
            row = cursor.fetchone()
            adquirido = bool(row and row[0] == 1)

        yield adquirido
    finally:
        if conexao:
            if adquirido:
                try:
                    with conexao.cursor() as cursor:
                        cursor.execute("SELECT RELEASE_LOCK(%s)", (nome_lock,))
                        cursor.fetchone()
                except Exception:
                    pass
            conexao.close()


def retornar_destinos_enviados(id_processo):
    if not id_processo:
        return set()

    try:
        sql = """SELECT b.codigo FROM processo_bot_envios e
            INNER JOIN bot_tipos b ON b.id=e.id_bot_destino
            WHERE e.id_processo=%s AND e.status='enviado'"""

        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, (id_processo,))
                registros = cursor.fetchall()

        return {str(registro[0]).strip().upper() for registro in registros}
    except Exception as e:
        logs.error(f"Erro retornar_destinos_enviados: {e}", exc_info=True)
        return set()



def retornar_destinos_processados(id_processo):
    """Destinos que ja foram enviados ou avaliados sem necessidade de envio."""
    if not id_processo:
        return set()

    try:
        sql = """SELECT b.codigo FROM processo_bot_envios e
            INNER JOIN bot_tipos b ON b.id=e.id_bot_destino
            WHERE e.id_processo=%s AND e.status IN ('enviado', 'ignorado')"""

        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, (id_processo,))
                registros = cursor.fetchall()

        return {str(registro[0]).strip().upper() for registro in registros}
    except Exception as e:
        logs.error(f"Erro retornar_destinos_processados: {e}", exc_info=True)
        return set()


def registrar_resultado_envio_bot(id_processo, codigo_destino, status, erro=""):
    if not id_processo:
        return False

    status = str(status or "").strip().lower()
    if status not in {"enviado", "erro", "ignorado"}:
        raise ValueError(f"Status de envio invalido: {status!r}")

    try:
        sql = """INSERT INTO processo_bot_envios
            (id_processo, id_bot_destino, status, attempts, last_error, enviado_em, created_at, updated_at)
            SELECT %s, b.id, %s, 1, %s, CASE WHEN %s=1 THEN NOW() ELSE NULL END, NOW(), NOW()
            FROM bot_tipos b WHERE b.codigo=%s ON DUPLICATE KEY UPDATE
            status=CASE WHEN processo_bot_envios.status='enviado' THEN 'enviado' ELSE VALUES(status) END,
            attempts=processo_bot_envios.attempts + 1,
            last_error=CASE WHEN processo_bot_envios.status='enviado' THEN processo_bot_envios.last_error ELSE VALUES(last_error) END,
            enviado_em=CASE WHEN VALUES(status)='enviado' THEN NOW() ELSE processo_bot_envios.enviado_em END,
            updated_at=NOW()"""
        valores = (id_processo, status, None if status != "erro" else str(erro or "")[:4000],
                   1 if status == "enviado" else 0, str(codigo_destino).strip().upper())

        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, valores)
                afetadas = cursor.rowcount
            conexao.commit()

        return afetadas > 0
    except Exception as e:
        logs.error(f"Erro registrar_resultado_envio_bot: {e}", exc_info=True)
        return False


def gravar_processo(cursor, edital):
    try:
        novo_id = None  # Variável para armazenar o id do novo processo
        novo_id = str(uuid4())
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sql = """INSERT INTO processos
            (id, id_page, link, descricao, numero, data, municipio, uf, licitacao, situacao, orgao, termos,
             created_at, updated_at, envio_notificacao, numero_aux)
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        valores = (
            novo_id, edital['id_pagina'], validar_campo_banco('Link', edital, 400),
            validar_campo_banco('Descricao', edital, 600), validar_campo_banco('Numero', edital, 60),
            validar_campo_banco('Data', edital, 60), validar_campo_banco('Municipio', edital, 200),
            validar_campo_banco('Uf', edital, 2), validar_campo_banco('Licitacao', edital, 100),
            validar_campo_banco('Situacao', edital, 100), validar_campo_banco('Orgao', edital, 200),
            validar_campo_banco('termo_busca', edital, LIMITE_TERMOS_PROCESSO), now, now,
            edital.get("envio_notificacao"), edital.get("NumeroAux")
        )

        cursor.execute(sql, valores)
        return novo_id
    except Exception as ex:
        logs.error(f"Erro ao inserir processo - {edital['Link']} \n ERROR: {ex}")
        raise


def gravar_processo_pncp(cursor, edital, id_processo, plataforma=None):
    try:
        id_pncp = str(uuid4())
        edital['Cnpj'] = limpar_cnpj(edital['Cnpj'])

        campos = ["id", "id_processo", "id_contratacao_pncp", "cnpj", "valor_total_estimado_compra", "quantidade_total_itens",
                  "data_inicio_recebimento_proposta", "data_fim_recebimento_proposta", "codigo_unidade_compradora", "link_auxiliar", "created_at"]

        valores = [id_pncp, id_processo, validar_campo_banco('IdContratacaoPncp', edital, 256), validar_campo_banco('Cnpj', edital, 14),
                   validar_campo_banco('ValorTotalEstimadoCompra', edital, 100), validar_campo_banco('QuantidadeItens', edital, 100),
                   validar_campo_banco('DataInicioRecebimentoProposta', edital, 60), validar_campo_banco('DataFimRecebimentoProposta', edital, 60),
                   validar_campo_banco('CodigoUnidadeCompradora', edital, 50), edital.get("LinkBotao"), datetime.now().strftime('%Y-%m-%d %H:%M:%S')]

        if str(plataforma or "").strip().lower() == "seguro":
            campos.insert(5, "valor_total_homologado")
            valores.insert(5, validar_campo_banco('ValorTotalHomologado', edital, 100))

        sql = f"INSERT INTO processos_pncp ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))})"
        cursor.execute(sql, tuple(valores))
    
    except Exception as ex:
        logs.error(f"Erro ao inserir processo pncp - {edital['Link']} \n ERROR: {ex}")
        raise  

def gravar_processo_itens(cursor, itens, id_processo):
    sql_item = """INSERT INTO processos_itens(id, id_processo, numero_item, descricao_item,
        quantidade_item, valor_unit_item, valor_total_item) VALUES(%s, %s, %s, %s, %s, %s, %s)"""

    for idx, item in enumerate(itens, start=1):
        try:
            valores_item = (str(uuid4()), id_processo, item.get("numeroItem"), item.get("descricaoItem"),
                            item.get("quantidadeItem"), item.get("valorUnitItem"), item.get("valorTotalItem"))

            cursor.execute(sql_item, valores_item)

        except Exception as e:
            logs.error("Erro ao inserir item | indice=%s | numeroItem=%s | descricaoItem=%r | erro=%s",
                       idx, item.get("numeroItem"), item.get("descricaoItem"), str(e))
            raise
      
def gravar_novo_processo(editalnovo, plataforma = None):
    link = editalnovo.get("Link", "").rstrip("/")

    print(f"\nGravar novo processo (por link): {link or 'Link não encontrado'}")

    if not link:
        logs.error("\nErro ao gravar novo processo: Link não encontrado no edital.")
        return None

    conexao = None

    try:
        conexao = _conectar_banco()

        with conexao.cursor() as cursor:

            # Verifica duplicidade e retorna o ID já existente
            cursor.execute("""SELECT id FROM processos WHERE link=%s
                ORDER BY created_at ASC, id ASC LIMIT 1""", (link,))

            processo_existente = cursor.fetchone()

            if processo_existente:
                id_existente = processo_existente[0]

                print(f"\nEdital já existe no banco (por link), ignorando: {link} - {id_existente}")
                logs.info(f"\nEdital já existe no banco (por link), ignorando: {link} - {id_existente}\n")

                return id_existente

            # Grava novo processo
            id_processo = gravar_processo(cursor, editalnovo)

            if not id_processo:
                logs.error(f"\nNão foi possível obter o id_processo ao gravar: {link}\n")
                conexao.rollback()
                return None

            gravar_processo_pncp(cursor, editalnovo, id_processo, plataforma)

            if "itens_dados" in editalnovo and editalnovo["itens_dados"] and (plataforma is None or plataforma.lower() != "seguro"):
                gravar_processo_itens(cursor, editalnovo["itens_dados"], id_processo)

            # Atualiza envio de notificação antes do commit
            if editalnovo.get("notificar_retorno") is True:
                atualizar_envio_notificacao(id_processo, cursor, editalnovo)

            conexao.commit()

            print(f"Edital salvo no banco (por link): {link} - {id_processo}\n")
            logs.info(f"\nEdital salvo no banco (por link): {link} - {id_processo}")

            return id_processo

    except Exception as ex:
        logs.error(f"Erro ao gravar novo processo - {link} \n ERROR: {ex}", exc_info=True)

        if conexao:
            try:
                conexao.rollback()
            except Exception:
                pass

        return None

    finally:
        if conexao:
            try:
                conexao.close()
            except Exception:
                pass
              
def retornar_registro_paginas(idPagina, idPlataforma):
  try:
    with _conectar_banco() as conexao:
        with conexao.cursor(dictionary=True) as cursor:
            query = """SELECT qtd_registros FROM plataformas_page WHERE id_page=%s AND id_plataforma=%s"""
            cursor.execute(query, (idPagina, idPlataforma))
            resultado = cursor.fetchone()  # Retorna um único registro
        
    return resultado["qtd_registros"] if resultado else None

  except Exception as e:
        logs.info(f"""Erro retornar_registro_paginas nao foi possivel conectar ao banco - {str(e)}""")

def salvar_urls_com_erro_api(lista_erros_api, id_pagina=None, plataforma=None):
    if not lista_erros_api:
        return 0

    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                sql = """INSERT INTO urls_erros_api(id_pagina, plataforma, url, params, tipo_erro,
                    mensagem, link_origem, data_erro, status, attempts)
                    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, 'pendente', 0)"""

                dados = []

                for erro in lista_erros_api:
                    dados.append((id_pagina, plataforma, erro.get("url"), erro.get("params"), erro.get("tipo_erro"),
                                  erro.get("mensagem"), erro.get("link_origem"), erro.get("data_erro")))

                cursor.executemany(sql, dados)

            conexao.commit()

        total = len(lista_erros_api)
        lista_erros_api.clear()

        logs.info(f"{total} URLs com erro de API salvas no banco. plataforma={plataforma}, id_pagina={id_pagina}")

        return total

    except Exception as e:
        logs.error(f"Erro ao salvar URLs com erro de API: {e}", exc_info=True)
        return 0
    
def retornar_qtd_registros_heuristica_busca(id_page: int, id_plataforma: int, termo_busca: str) -> int:
    termo_busca = str(termo_busca or "").strip().lower()

    if not termo_busca:
        termo_busca = "sem_termo"

    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""SELECT qtd_registros FROM plataformas_page_heuristica_busca
                    WHERE id_page=%s AND id_plataforma=%s AND termo_busca=%s LIMIT 1""",
                               (id_page, id_plataforma, termo_busca))

                row = cursor.fetchone()

                if not row:
                    return 0

                return int(row[0] or 0)

    except Exception as e:
        logs.error(f"Erro retornar_qtd_registros_heuristica_busca: {e}", exc_info=True)
        return 0
    
def atualizar_heuristica_busca(id_page: int, id_plataforma: int, termo_busca: str, qtd_registros: int):
    termo_busca = str(termo_busca or "").strip().lower()

    if not termo_busca:
        termo_busca = "sem_termo"

    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""INSERT INTO plataformas_page_heuristica_busca
                    (id_page, id_plataforma, termo_busca, qtd_registros, data_ultima_busca, created_at, updated_at)
                    VALUES(%s, %s, %s, %s, NOW(), NOW(), NOW()) ON DUPLICATE KEY UPDATE
                    qtd_registros=VALUES(qtd_registros), data_ultima_busca=NOW(), updated_at=NOW()""",
                               (id_page, id_plataforma, termo_busca, int(qtd_registros or 0)))

            conexao.commit()

    except Exception as e:
        logs.error(f"Erro atualizar_heuristica_busca: {e}", exc_info=True)

def retornar_buscas_adicionais(id_page):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                cursor.execute("""SELECT id, nome, parametros_url, qtd_registros
                    FROM plataformas_page_heuristica_busca WHERE is_active=1 AND id_page=%s ORDER BY id""", (id_page,))

                return cursor.fetchall()

    except Exception as e:
        logs.error(f"Erro retornar_buscas_adicionais: {e}", exc_info=True)
        return []


def atualizar_heuristica_busca_filtro(id_busca: int, qtd_registros: int):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""UPDATE plataformas_page_heuristica_busca
                    SET qtd_registros=%s, data_ultima_busca=NOW() WHERE id=%s""",
                               (int(qtd_registros or 0), int(id_busca)))
                afetadas = cursor.rowcount
            conexao.commit()

        if afetadas == 0:
            logs.error(f"[heuristica filtro] Busca não encontrada: id_busca={id_busca}")

    except Exception as e:
        logs.error(
            f"Erro atualizar_heuristica_busca_filtro id_busca={id_busca}: {e}",
            exc_info=True
        )


def retornar_destinatarios_filtros_seguro(id_busca: int, id_processo=None):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:
                query = """SELECT u.id, u.id_telegram FROM usuarios_crawler_python u
                    WHERE u.is_active=1 AND u.recebe_filtros_seguro=1
                    AND u.id_telegram IS NOT NULL AND TRIM(u.id_telegram)<>''"""
                parametros = []

                if id_processo:
                    query += """ AND NOT EXISTS (SELECT 1 FROM processos_busca_notificacoes n
                        WHERE n.id_processo=%s AND n.id_busca=%s AND n.id_usuario_crawler_python=u.id)"""
                    parametros.extend([id_processo, id_busca])

                query += " ORDER BY u.id"
                cursor.execute(query, tuple(parametros))
                return cursor.fetchall()

    except Exception as e:
        logs.error(f"Erro retornar_destinatarios_filtros_seguro: {e}", exc_info=True)
        return []


def registrar_notificacoes_busca(id_processo: str, id_busca: int, destinatarios, chats_enviados):
    chats_enviados = {str(chat) for chat in (chats_enviados or [])}
    registros = [(id_processo, id_busca, destinatario["id"]) for destinatario in (destinatarios or [])
                 if str(destinatario.get("id_telegram")) in chats_enviados]

    if not registros:
        return 0

    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.executemany("""INSERT IGNORE INTO processos_busca_notificacoes
                    (id_processo, id_busca, id_usuario_crawler_python, enviado_em)
                    VALUES(%s, %s, %s, NOW())""", registros)
            conexao.commit()
        return len(registros)

    except Exception as e:
        logs.error(f"Erro registrar_notificacoes_busca: {e}", exc_info=True)
        return 0

def retornar_termos_busca_by_id_page(id_pagina):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""SELECT termo_busca FROM plataformas_page_heuristica_busca
                    WHERE id_page=%s AND is_active=1""", (id_pagina,))
                return {linha[0].strip().lower() for linha in cursor.fetchall() if linha[0]}

    except Exception as e:
        logs.error(f"Erro retornar_termos_busca_by_id_page: {e}", exc_info=True)
        return set()

def gravar_processo_botbool_envio(id_processo):
    try:
        if not id_processo:
            return False

        with _conectar_banco() as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""INSERT IGNORE INTO processos_botbool_envio(id_processo, data_registro, enviado_email)
                    VALUES(%s, NOW(), 0)""", (str(id_processo),))

                conexao.commit()

        return True

    except Exception as e:
        logs.error(f"Erro ao gravar processo BotBool para envio: {e}", exc_info=True)
        return False

def atualizar_termos_edital(id_processo, termos):
    try:
        with _conectar_banco() as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""UPDATE processos SET termos=%s, updated_at=NOW() WHERE id=%s""",
                               (validar_campo_banco('termos', {'termos': termos}, LIMITE_TERMOS_PROCESSO), id_processo))

                conexao.commit()

        return True

    except Exception as e:
        logs.error(f"Erro ao atualizar termos do edital: {e}", exc_info=True)
        return False
    
#####################################################################################
######## METODOS PARA FUNCIONALIDADE COM QUEUE(FILA) ################################
#####################################################################################


LOCK_SECONDS = 10 * 60   # 20 min

CODIGOS_EXECUTOR_OBRAS = {"GNP", "BOOL", "EDIT"}


def _normalizar_codigo_executor(codigo_executor):
    if codigo_executor is None:
        return None

    codigo = str(codigo_executor).strip().upper()
    if codigo not in CODIGOS_EXECUTOR_OBRAS:
        raise ValueError(f"Codigo executor invalido: {codigo_executor!r}")
    return codigo

def _calcular_prioridade(url: str, id_page: int) -> int:
    return 30

def pegar_proximo_job(plataforma: str, worker_id: str, codigo_executor=None):
    try:
        codigo_executor = _normalizar_codigo_executor(codigo_executor)
        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:

                # 1. Busca a plataforma
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))

                p = cursor.fetchone()

                if not p:
                    logs.warning(f"[PEGAR JOB] Plataforma não encontrada: {plataforma}")
                    return None

                id_plataforma = int(p["id"])
                lock_until = datetime.now() + timedelta(seconds=LOCK_SECONDS)

                # 2. Descobre qual job está elegível
                join_executor = ""
                filtro_executor = ""
                parametros_job = [id_plataforma]

                if codigo_executor:
                    join_executor = "INNER JOIN bot_tipos executor ON executor.id=pg.id_bot_executor"
                    filtro_executor = " AND executor.codigo = %s"
                    parametros_job.append(codigo_executor)

                sql_proximo = f"""SELECT q.id AS job_id FROM plataformas_page_queue q
                    INNER JOIN plataformas_page pp ON pp.id_plataforma=q.id_plataforma AND pp.id_page=q.id_page AND pp.is_active=1
                    INNER JOIN pages pg ON pg.id=q.id_page AND pg.is_active=1 {join_executor}
                    WHERE q.id_plataforma=%s {filtro_executor} AND q.status='queued' AND q.next_run_at<=NOW()
                    AND (q.lock_until IS NULL OR q.lock_until<NOW())
                    ORDER BY q.prioridade, q.next_run_at, q.id LIMIT 1"""
                cursor.execute(sql_proximo, tuple(parametros_job))

                row = cursor.fetchone()

                if not row:
                    logs.info(f"[PEGAR JOB] Nenhum job elegível para plataforma={plataforma}")
                    return None

                job_id = row["job_id"]

                # 3. Tenta travar exatamente esse job
                sql_lock = """UPDATE plataformas_page_queue SET status='running', locked_by=%s, lock_until=%s
                    WHERE id=%s AND id_plataforma=%s AND status='queued' AND next_run_at<=NOW()
                    AND (lock_until IS NULL OR lock_until<NOW())"""
                cursor.execute(sql_lock, (worker_id, lock_until, job_id, id_plataforma))

                conexao.commit()

                if cursor.rowcount != 1:
                    logs.info(f"[PEGAR JOB] Job {job_id} não foi travado. " f"Provavelmente outro worker pegou antes.")
                    return None

                # 4. Busca os dados completos do job travado
                campos_executor = "NULL AS codigo_executor, NULL AS destinos"
                joins_destinos = ""
                grupo_executor = ""
                campo_usuarios = "GROUP_CONCAT(DISTINCT u.id_telegram SEPARATOR ',') AS ids_usuarios"
                joins_usuarios = """LEFT JOIN plataforma_page_usuarios ppu ON ppu.id_plataforma_pages=pp.id AND ppu.is_active=1
                    LEFT JOIN usuarios_crawler_python u ON u.id=ppu.id_usuario_crawler_python AND u.is_active=1"""

                if codigo_executor:
                    campos_executor = "executor.codigo AS codigo_executor, GROUP_CONCAT(DISTINCT destino.codigo ORDER BY destino.codigo) AS destinos"
                    joins_destinos = """INNER JOIN bot_tipos executor ON executor.id=pg.id_bot_executor
                        LEFT JOIN page_bot_destinos pd ON pd.id_page=pg.id LEFT JOIN bot_tipos destino ON destino.id=pd.id_bot_destino"""
                    grupo_executor = ", executor.codigo"
                    campo_usuarios = "NULL AS ids_usuarios"
                    joins_usuarios = ""

                sql_dados = f"""SELECT q.id AS job_id, q.id_plataforma, q.id_page, q.prioridade, q.attempts, q.max_attempts,
                    pg.url, pg.filter, pg.name, {campos_executor}, pp.data_ultima_busca AS ultima_data, pp.qtd_registros, {campo_usuarios}
                    FROM plataformas_page_queue q
                    INNER JOIN plataformas_page pp ON pp.id_plataforma=q.id_plataforma AND pp.id_page=q.id_page AND pp.is_active=1
                    INNER JOIN pages pg ON pg.id=q.id_page AND pg.is_active=1 {joins_destinos} {joins_usuarios}
                    WHERE q.id=%s AND q.status='running' AND q.locked_by=%s
                    GROUP BY q.id, q.id_plataforma, q.id_page, q.prioridade, q.attempts, q.max_attempts, pg.url, pg.filter,
                    pg.name, pp.data_ultima_busca, pp.qtd_registros {grupo_executor} LIMIT 1"""
                cursor.execute(sql_dados, (job_id, worker_id))

                job = cursor.fetchone()

                # 5. Se marcou running mas não conseguiu buscar, libera o job
                if not job:
                    logs.error(f"[PEGAR JOB] Job {job_id} foi marcado como running, mas o SELECT final não retornou dados. Liberando job.")

                    cursor.execute("UPDATE plataformas_page_queue SET status='queued', locked_by=NULL, lock_until=NULL WHERE id=%s", (job_id,))
                    conexao.commit()
                    return None

                # 6. Calcula prioridade dinâmica
                prioridade = _calcular_prioridade(job["url"], job["id_page"])

                cursor.execute("UPDATE plataformas_page_queue SET prioridade=%s WHERE id=%s", (prioridade, job_id))
                conexao.commit()

                # 7. Prepara lista de usuários
                ids = []

                if job.get("ids_usuarios"):
                    ids = [s.strip() for s in job["ids_usuarios"].split(",") if s.strip()]

                job["prioridade"] = prioridade
                job["ids_usuario"] = ids

                if codigo_executor:
                    sql_destinatarios = """SELECT u.id, u.id_telegram, destino.codigo AS codigo_destino FROM usuarios_crawler_python u
                        INNER JOIN bot_tipos destino ON destino.id=u.id_bot_destino WHERE u.is_active=1 AND destino.is_active=1
                        AND u.id_telegram IS NOT NULL AND TRIM(u.id_telegram)<>'' ORDER BY u.id"""
                    cursor.execute(sql_destinatarios)
                    job["destinatarios"] = cursor.fetchall()
                    job["destinos"] = [item.strip() for item in (job.get("destinos") or "").split(",") if item.strip()]
                    job["ids_usuario"] = [str(item["id_telegram"]).strip() for item in job["destinatarios"] if item.get("codigo_destino") in job["destinos"]]
                else:
                    job["destinatarios"] = [{"id": None, "id_telegram": id_telegram, "codigo_destino": None} for id_telegram in ids]
                
                return job

    except Exception as e:
        logs.error(f"Erro pegar_proximo_job: {e}", exc_info=True)
        return None
    
def finalizar_job_queue(job_id: int):
    """
    Sucesso: volta para o fim da fila elegivel e zera falhas consecutivas.
    """
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""UPDATE plataformas_page_queue SET status='queued', next_run_at=NOW(), locked_by=NULL,
                    lock_until=NULL, last_error=NULL, attempts=0 WHERE id=%s AND status='running'""", (job_id,))
            conexao.commit()
    except Exception as e:
        logs.error(f"Erro finalizar_job_queue(requeue): {e}", exc_info=True)

def falhar_job_queue(job_id: int, err: str):
    try:
        with _conectar_banco() as conexao:
            with conexao.cursor(dictionary=True) as cursor:

                cursor.execute("""SELECT attempts, max_attempts FROM plataformas_page_queue WHERE id=%s LIMIT 1""", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return

                attempts = int(row["attempts"] or 0) + 1
                max_attempts = int(row["max_attempts"] or 5)

                status = "queued" if attempts < max_attempts else "failed"

                cursor.execute("""UPDATE plataformas_page_queue SET status=%s, next_run_at=NOW(), locked_by=NULL,
                    lock_until=NULL, last_error=%s, attempts=%s, updated_at=NOW() WHERE id=%s""",
                               (status, (err or "")[:4000], attempts, job_id))

            conexao.commit()

    except Exception as e:
        logs.error(f"Erro falhar_job_queue: {e}", exc_info=True)
        
def requeue_jobs_orfaos(plataforma: str, motivo: str = "Requeue de lock expirado", codigo_executor=None):
    try:
        codigo_executor = _normalizar_codigo_executor(codigo_executor)
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))
                row = cursor.fetchone()
                if not row:
                    return 0
                id_plataforma = int(row[0])

                if codigo_executor:
                    cursor.execute("""UPDATE plataformas_page_queue q INNER JOIN pages pg ON pg.id=q.id_page
                        INNER JOIN bot_tipos executor ON executor.id=pg.id_bot_executor
                        SET q.status='queued', q.next_run_at=NOW(), q.locked_by=NULL, q.lock_until=NULL,
                            q.last_error=%s, q.updated_at=NOW()
                        WHERE q.id_plataforma=%s AND executor.codigo=%s AND q.status='running'
                            AND (q.lock_until IS NULL OR q.lock_until<NOW())""",
                                   (motivo[:4000], id_plataforma, codigo_executor))
                else:
                    cursor.execute("""UPDATE plataformas_page_queue SET status='queued', next_run_at=NOW(), locked_by=NULL,
                        lock_until=NULL, last_error=%s, updated_at=NOW() WHERE id_plataforma=%s AND status='running'
                        AND (lock_until IS NULL OR lock_until<NOW())""", (motivo[:4000], id_plataforma))
                afetadas = cursor.rowcount
            conexao.commit()
            return afetadas
    except Exception as e:
        logs.error(f"Erro requeue_jobs_orfaos: {e}", exc_info=True)
        return 0
        
def renovar_lock_job(job_id: int, worker_id: str):
    try:
        lock_until = datetime.now() + timedelta(seconds=LOCK_SECONDS)
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("""UPDATE plataformas_page_queue SET lock_until=%s, updated_at=NOW()
                    WHERE id=%s AND status IN ('running', 'failed') AND locked_by=%s""", (lock_until, job_id, worker_id))
            conexao.commit()
    except Exception as e:
        logs.error(f"Erro renovar_lock_job: {e}", exc_info=True)
        
def requeue_sem_heartbeat(plataforma: str, minutos_sem_heartbeat: int = 10, motivo: str = "Requeue sem heartbeat", codigo_executor=None):
    try:
        codigo_executor = _normalizar_codigo_executor(codigo_executor)
        with _conectar_banco() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT id FROM plataformas WHERE descricao=%s LIMIT 1", (plataforma,))
                row = cursor.fetchone()
                if not row:
                    return 0
                id_plataforma = int(row[0])

                if codigo_executor:
                    cursor.execute("""UPDATE plataformas_page_queue q INNER JOIN pages pg ON pg.id=q.id_page
                        INNER JOIN bot_tipos executor ON executor.id=pg.id_bot_executor
                        SET q.status='queued', q.next_run_at=NOW(), q.locked_by=NULL, q.lock_until=NULL,
                            q.last_error=%s, q.updated_at=NOW()
                        WHERE q.id_plataforma=%s AND executor.codigo=%s AND q.status='running'
                            AND q.updated_at<(NOW() - INTERVAL %s MINUTE)""",
                                   (motivo[:4000], id_plataforma, codigo_executor, int(minutos_sem_heartbeat)))
                else:
                    cursor.execute("""UPDATE plataformas_page_queue SET status='queued', next_run_at=NOW(), locked_by=NULL,
                        lock_until=NULL, last_error=%s, updated_at=NOW() WHERE id_plataforma=%s AND status='running'
                        AND updated_at<(NOW() - INTERVAL %s MINUTE)""",
                                   (motivo[:4000], id_plataforma, int(minutos_sem_heartbeat)))

                afetadas = cursor.rowcount
            conexao.commit()
            return afetadas
    except Exception as e:
        logs.error(f"Erro requeue_sem_heartbeat: {e}", exc_info=True)
        return 0
