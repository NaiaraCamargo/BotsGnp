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

from pncp_shared.database.repositoriopncp import *
from pncp_shared.utils.funcoespncp import *
from pncp_shared.logs_pncp.controle_logs import *
from pncp_shared.config.controle_config import *

def iniciar_agendador_planilha():
    while True:
        schedule.run_pending()
        time.sleep(1)

def rotina_envio_planilha_botbool_7h():
    try:
        ontem = (datetime.now() - timedelta(days=1)).date()
        
        processos = retornar_processos_botbool_ontem()
        
        if not processos:
            logs.info("Nenhum processo BotBool do dia anterior para enviar por e-mail.")
            return

        caminho, total = gerar_excel_botbool_dia_anterior(processos)

        if not caminho or total == 0:
            logs.info("Nenhum edital BotBool do dia anterior para enviar por e-mail.")
            return

        emails_destino = retornar_emails_planilha_botbool()

        if not emails_destino:
            logs.error("Nenhum e-mail ativo configurado para receber a planilha BotBool.")
            return

        config_email = configuracoes["email_planilha_botbool"]

        assunto = f"Relatório Licitações de OBRAS - {ontem.strftime('%d/%m/%Y')} - GNP CONSULTORIA"

        corpo = f"""Bom dia,

    Segue em anexo a planilha com os editais BotBool do dia anterior.

    Data de referência: {ontem.strftime('%d/%m/%Y')}
    Quantidade de editais: {total}

    Atenciosamente,
    Bot PNCP
    """

        enviado = enviar_email_com_planilha(
            caminho_arquivo=caminho,
            emails_destino=emails_destino,
            assunto=assunto,
            corpo=corpo,
            email_remetente=config_email["email_remetente"],
            senha_email=config_email["senha_email"],
            smtp_host=config_email.get("smtp_host", "smtp.gmail.com"),
            smtp_port=int(config_email.get("smtp_port", 587))
        )

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
            'palavraschave': retornar_dicionario_filtros(palavra_chave),
            'ultima_data': formatar_data(dados_url.get('ultima_data', ''), padrao=format_data)
        }
    }

    filtros_locais['banco'].update({
        "data_inicial": data_inicial or filtros_locais['banco']["ultima_data"],
        "data_final": data_final or formatar_data(limpar=False, padrao=format_data),
        "qtd_registros": dados_url.get("qtd_registros", 0),
        "filter": dados_url.get("filter", "")
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
    }

    # roda função bloqueante num thread do asyncio
    await asyncio.to_thread(
        executar_url,
        job["url"],
        dados_url,
        plataforma,
        filtros,
        mostrar_browser,
        data_inicial,
        data_final,
        format_data
    )

async def bot_async(plataforma: str, filtros: dict | None = None, mostrar_browser: bool = False, rodar_infinito: bool = True, data_inicial: str = "",
                    data_final: str = "", format_data: str = "universal", min_interval: float = 0.5, idle_sleep: float = 0.2, intervalo_sucesso_seg: int = 180,
                    timeout_job_seg: int = 45 * 60, limpar_a_cada_seg: int = 10 * 60  ):
    filtros = filtros or {}
    worker_id = f"{plataforma}-async-{uuid.uuid4().hex[:8]}"

    limpar_console()
    carregar_configuracoes(plataforma)
    controle_logs()
    print(f"[{worker_id}] bot_async iniciado (1 por vez)")

    ultima_limpeza = time.time()
    
    try:
        requeue_jobs_orfaos(plataforma)
    except Exception:
        pass

    try:
        requeue_sem_heartbeat(plataforma, minutos_sem_heartbeat=10)
    except Exception:
        pass

    schedule.every().day.at("07:00").do(rotina_envio_planilha_botbool_7h)
    #schedule.every(10).seconds.do(rotina_envio_planilha_botbool_7h)

    threading.Thread(
        target=iniciar_agendador_planilha,
        daemon=True
    ).start()
        
    while True:
        try:  
            # limpeza/refresh de config a cada X tempo (AGORA FAZ SENTIDO)
            if time.time() - ultima_limpeza >= limpar_a_cada_seg:
                try:
                    limpar_console()
                    carregar_configuracoes(plataforma)
                finally:
                    ultima_limpeza = time.time()
            
            # pega 1 job
            job = pegar_proximo_job(plataforma, worker_id)
            if not job:
                requeue_jobs_orfaos(plataforma)
                requeue_sem_heartbeat(plataforma, minutos_sem_heartbeat=10)
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
                # timeout duro do job (se selenium travar, não derruba o bot inteiro)
                await asyncio.wait_for(
                    executar_job_async(job, plataforma, filtros, mostrar_browser, data_inicial, data_final, format_data),
                    timeout=timeout_job_seg
                )

                finalizar_job_queue(job["job_id"])

                dur = time.time() - started
                print(f"[{worker_id}] OK job={job['job_id']} duracao={dur:.1f}s")
                logs.info(f"[{worker_id}] OK job={job['job_id']} duracao={dur:.1f}s")

            except asyncio.TimeoutError:
                dur = time.time() - started
                err = f"Timeout do job após {timeout_job_seg}s (duracao={dur:.1f}s)"
                logs.error(f"[{worker_id}] TIMEOUT job={job['job_id']} page={job['id_page']} nome={job['name']} {err}")
                falhar_job_queue(job["job_id"], err)

            except Exception as e:
                dur = time.time() - started
                logs.exception(f"[{worker_id}] ERRO job={job['job_id']} duracao={dur:.1f}s: {e}")
                falhar_job_queue(job["job_id"], str(e))
                
            finally:
                heartbeat_stop.set()
                hb_task.cancel()

            if not rodar_infinito:
                break
            
            print(f"[{worker_id}] aguardando {intervalo_sucesso_seg}s antes do próximo job...")
            await asyncio.sleep(intervalo_sucesso_seg)

        except Exception:
            logs.exception(f"[{worker_id}] erro no loop principal; reiniciando em 10s...")
            await asyncio.sleep(10)

def bot(plataforma: str, filtros: dict | None = None, mostrar_browser: bool = False, rodar_infinito: bool = True, data_inicial: str = "",
        data_final: str = "", format_data: str = "universal"):
    try:
        asyncio.run(
            bot_async(
                plataforma=plataforma,
                filtros=filtros,
                mostrar_browser=mostrar_browser,
                rodar_infinito=rodar_infinito,
                data_inicial=data_inicial,
                data_final=data_final,
                format_data=format_data,
                min_interval=0.0,
                idle_sleep=0.2,
                intervalo_sucesso_seg=180,
                timeout_job_seg=45 * 60
            )
        )
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
            
            