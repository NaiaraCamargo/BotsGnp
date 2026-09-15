import threading
from sys import argv
import asyncio
import time
import uuid
from urllib.parse import urlparse, parse_qs, unquote_plus
import re
import traceback
import schedule
from datetime import datetime, timedelta

from pncp_bot_obra.crawlers.crawler_pncp import *
from pncp_bot_obra.controllers.controle_planilha_bool import (
    gerar_excel_botbool_dia_anterior,
    enviar_email_com_planilha,
)
from pncp_bot_obra.database.repositorio_relatorio_botbool import (
    retornar_emails_planilha_botbool, retornar_processos_botbool_periodo,
)

from pncp_shared.database.repositoriopncp import *
from pncp_shared.database.backup_bancos import executar_backup_se_necessario
from pncp_shared.utils.funcoespncp import *
from pncp_shared.utils.asyncio_utils import executar_com_timeout_suave
from pncp_shared.logs.controle_logs import *
from pncp_shared.config.controle_config import *
from pncp_bot_obra.database.repositorio_filtros_obras import retornar_dicionario_filtros_obras
from pncp_bot_obra.services.roteamento_bots import normalizar_codigo_bot

_backup_lock = threading.Lock()


def iniciar_backup_banco_periodico(plataforma):
    if _backup_lock.locked():
        return

    def rotina_backup():
        with _backup_lock:
            try:
                dias_intervalo = int(configuracoes.get("dias_intervalo_bkp", 2))
                resultado = executar_backup_se_necessario(plataforma=plataforma, dias_intervalo=dias_intervalo)
                if resultado.status == "ok":
                    logs.info(resultado.mensagem)
                    print(resultado.mensagem)
                elif resultado.status != "ignorado":
                    logs.error(resultado.mensagem)
                else:
                    logs.info(resultado.mensagem)
            except Exception as e:
                logs.exception(f"Erro ao executar backup do banco ({plataforma}): {e}")

    threading.Thread(target=rotina_backup, daemon=True).start()


def iniciar_agendador_planilha():
    while True:
        schedule.run_pending()
        time.sleep(1)

def rotina_envio_planilha_botbool_7h():
    try:
        hoje = datetime.now().date()

        if hoje.weekday() == 6:
            logs.info("Envio da planilha BotBool ignorado aos domingos.")
            return

        # Na segunda-feira, consolida sábado e domingo, pois não há envio no domingo.
        dias_periodo = 2 if hoje.weekday() == 0 else 1
        data_inicial = hoje - timedelta(days=dias_periodo)
        data_final = hoje - timedelta(days=1)

        processos = retornar_processos_botbool_periodo(data_inicial, hoje)
        
        if not processos:
            logs.info("Nenhum processo BotBool do período de "
                      f"{data_inicial.strftime('%d/%m/%Y')} a {data_final.strftime('%d/%m/%Y')} para enviar por e-mail.")
            return

        caminho, total = gerar_excel_botbool_dia_anterior(processos,data_inicial=data_inicial,data_final=data_final)

        if not caminho or total == 0:
            logs.info("Nenhum edital BotBool do período para enviar por e-mail.")
            return

        emails_destino = retornar_emails_planilha_botbool()

        if not emails_destino:
            logs.error("Nenhum e-mail ativo configurado para receber a planilha BotBool.")
            return

        config_email = configuracoes["email_planilha_botbool"]

        periodo = data_inicial.strftime("%d/%m/%Y")
        if data_final != data_inicial:
            periodo += f" a {data_final.strftime('%d/%m/%Y')}"

        assunto = f"Relatório Licitações de OBRAS - {periodo} - GNP CONSULTORIA"

        corpo = f"""Bom dia,

    Segue em anexo a planilha com os editais BotBool do período informado.

    Período de referência: {periodo}
    Quantidade de editais: {total}

    Atenciosamente,
    Bot PNCP
    """

        enviado = enviar_email_com_planilha(caminho, emails_destino, assunto, corpo, config_email["email_remetente"],
                                            config_email["senha_email"], config_email.get("smtp_host", "smtp.gmail.com"), int(config_email.get("smtp_port", 587)))

        if enviado:
            logs.info(f"Planilha BotBool enviada com sucesso: {caminho}")
            limpar_arquivo(caminho)
        else:
            logs.error("Não foi possível enviar a planilha BotBool.")
    except Exception as e:
        logs.exception(f"Erro na rotina de envio da planilha BotBool: {e}")


def rodar_crawler(url: str, filtros_locais: dict, notificacao_config: dict, mostrar_browser: bool):
    crawler(url, filtros=filtros_locais, notificacao_config=notificacao_config,mostrar_browser=mostrar_browser)

def executar_url(url: str, dados_url: dict, plataforma: str, filtros: dict, mostrar_browser: bool, data_inicial: str, data_final: str, format_data: str):

    try:
        qs = parse_qs(urlparse(url).query)
        qu = unquote_plus((qs.get("q", [""])[0] or "")).strip().lower()
        q = remover_acentos(qu)
    except Exception:
        q = ""
        
    q = re.sub(r"\s+", "_", q)
    palavra_chave = (q + '*') if q else ''
            
    filtros_locais = {
        'banco': {
            'palavraschave': retornar_dicionario_filtros_obras(palavra_chave, manter_word=True),
            'ultima_data': formatar_data(dados_url.get('ultima_data', ''), padrao=format_data)
        }
    }

    filtros_locais['banco'].update({
        "data_inicial": data_inicial or filtros_locais['banco']["ultima_data"],
        "data_final": data_final or formatar_data(limpar=False, padrao=format_data),
        "qtd_registros": dados_url.get("qtd_registros", 0),
        "filter": dados_url.get("filter", ""),
        "codigo_executor": dados_url.get("codigo_executor"),
        "destinos": dados_url.get("destinos", []),
        "destinatarios": dados_url.get("destinatarios", []),
    })

    notificacao_config = {
        'id_pagina': dados_url['id_pagina'],
        'ids_usuarios': dados_url['ids_usuario'],
        'plataforma': plataforma,
        'primeira_execucao': not dados_url.get("ultima_data", '')
    }

    rodar_crawler(url, filtros_locais, notificacao_config, mostrar_browser)
    

async def executar_job_async(job: dict, plataforma: str, filtros: dict, mostrar_browser: bool,
                            data_inicial: str, data_final: str, format_data: str):
    
    dados_url = {
        "id_pagina": job["id_page"],
        "ultima_data": job.get("ultima_data"),
        "ids_usuario": job.get("ids_usuario", []),
        "qtd_registros": job.get("qtd_registros", 0),
        "filter": job.get("filter", ""),
        "codigo_executor": job.get("codigo_executor"),
        "destinos": job.get("destinos", []),
        "destinatarios": job.get("destinatarios", []),
    }

    # roda função bloqueante num thread do asyncio
    await asyncio.to_thread(executar_url, job["url"], dados_url, plataforma, filtros, mostrar_browser,
                            data_inicial, data_final, format_data)

async def bot_async(plataforma: str, codigo_executor: str = "GNP", filtros: dict | None = None, mostrar_browser: bool = False, rodar_infinito: bool = True, data_inicial: str = "",
                    data_final: str = "", format_data: str = "universal", min_interval: float = 0.5, idle_sleep: float = 0.2, intervalo_sucesso_seg: int = 5,
                    timeout_job_seg: int = 45 * 60, limpar_a_cada_seg: int = 10 * 60  ):
    filtros = filtros or {}
    codigo_executor = normalizar_codigo_bot(codigo_executor)
    worker_id = f"{plataforma}-{codigo_executor}-async-{uuid.uuid4().hex[:8]}"

    limpar_console()
    carregar_configuracoes(plataforma)
    controle_logs(codigo_executor)
    if codigo_executor == "GNP":
        iniciar_backup_banco_periodico(plataforma)
    print(f"[{worker_id}] bot_async iniciado (1 por vez)")

    ultima_limpeza = time.time()
    
    try:
        requeue_jobs_orfaos(plataforma, codigo_executor=codigo_executor)
    except Exception:
        pass

    try:
        requeue_sem_heartbeat(plataforma, minutos_sem_heartbeat=10, codigo_executor=codigo_executor)
    except Exception:
        pass

    if codigo_executor == "BOOL":
        schedule.every().day.at("07:00").do(rotina_envio_planilha_botbool_7h).tag("planilha_botbool")
        threading.Thread(target=iniciar_agendador_planilha, daemon=True).start()
        
    while True:
        try:  
            # limpeza/refresh de config a cada X tempo (AGORA FAZ SENTIDO)
            if time.time() - ultima_limpeza >= limpar_a_cada_seg:
                try:
                    limpar_console()
                    carregar_configuracoes(plataforma)
                    if codigo_executor == "GNP":
                        iniciar_backup_banco_periodico(plataforma)
                finally:
                    ultima_limpeza = time.time()
            
            # pega 1 job
            job = pegar_proximo_job(plataforma, worker_id, codigo_executor=codigo_executor)
            if not job:
                requeue_jobs_orfaos(plataforma, codigo_executor=codigo_executor)
                requeue_sem_heartbeat(plataforma, minutos_sem_heartbeat=10, codigo_executor=codigo_executor)
                await asyncio.sleep(idle_sleep)
                continue

            started = time.time()
            print(f"[{worker_id}] START job={job['job_id']} page={job['id_page']} nome={job['name']} url={job['url']}")
            logs.info(f"[{worker_id}] START job={job['job_id']} page={job['id_page']} nome={job['name']} url={job['url']}")
            
            heartbeat_stop = asyncio.Event()
            
            async def heartbeat_loop():
                # renova a cada 3 min (menor que 10min)
                while not heartbeat_stop.is_set():
                    try:
                        renovar_lock_job(job["job_id"], worker_id)
                    except Exception:
                        pass
                    await asyncio.sleep(180)

            hb_task = asyncio.create_task(heartbeat_loop())

            try:
                # O limite gera aviso; a thread precisa terminar antes de liberar ou reenfileirar o job.
                descricao_job = f"job={job['job_id']} page={job['id_page']} nome={job['name']}"
                await executar_com_timeout_suave(executar_job_async(job, plataforma, filtros, mostrar_browser, data_inicial, data_final, format_data),
                                                  timeout_job_seg, descricao_job)

                finalizar_job_queue(job["job_id"])

                dur = time.time() - started
                print(f"[{worker_id}] OK job={job['job_id']} duracao={dur:.1f}s")
                logs.info(f"[{worker_id}] OK job={job['job_id']} duracao={dur:.1f}s")

            except Exception as e:
                dur = time.time() - started
                logs.exception(f"[{worker_id}] ERRO job={job['job_id']} duracao={dur:.1f}s: {e}")
                falhar_job_queue(job["job_id"], str(e))
                
            finally:
                heartbeat_stop.set()
                hb_task.cancel()
                await asyncio.gather(hb_task, return_exceptions=True)

            if not rodar_infinito:
                break
            
            print(f"[{worker_id}] aguardando {intervalo_sucesso_seg}s antes do próximo job...")
            await asyncio.sleep(intervalo_sucesso_seg)

        except Exception:
            logs.exception(f"[{worker_id}] erro no loop principal; reiniciando em 10s...")
            await asyncio.sleep(10)

def bot(plataforma: str, codigo_executor: str = "GNP", filtros: dict | None = None, mostrar_browser: bool = False, rodar_infinito: bool = True, data_inicial: str = "",
        data_final: str = "", format_data: str = "universal"):
    try:
        execucao = bot_async(plataforma, codigo_executor, filtros, mostrar_browser, rodar_infinito, data_inicial, data_final,
                             format_data, min_interval=0.0, idle_sleep=0.2, intervalo_sucesso_seg=5, timeout_job_seg=45 * 60)
        asyncio.run(execucao)
    except Exception as e:
        print(f"Erro fatal no bot: {e}")
        traceback.print_exc()
        logs.exception(f"Erro fatal no bot: {e}")
        raise

if __name__ == '__main__':
    print(len(argv))
    '''if len(argv) > 1:
        if len(argv) == 3:
            bot(argv[1], argv[2])
        elif len(argv) == 4:
            argv[3] = argv[3].lower()
            primeira_exe = False
            if argv[3] == "true" or argv[3] == "t" or argv[3] == "1":
                primeira_exe = True
            bot(argv[1], argv[2], primeira_exe)'''
            
            
