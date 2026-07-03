import time
import traceback

from pncp_shared.utils.funcoespncp import *
from pncp_shared.logs.controle_logs import *
from pncp_shared.config.controle_config import *

from mapfre_downloader.services.excel_service import ler_links_excel, atualizar_planilha
from mapfre_downloader.services.mapfre_service import processar_login_mafre
from pncp_shared.utils.drivers import criar_driver, finalizar_driver
from mapfre_downloader.services.download_service import processar_reserva_arquivos

def executar_bot_mapfre():
    try:
        limpar_console()
        carregar_configuracoes(nome_pacote="mapfre_downloader")
        controle_logs()

        caminho_excel = config("caminho_excel")
        tempo_renovar_sessao = config("tempo_de_login", texto=False)

        reservas = ler_links_excel(caminho_excel)

        if not reservas:
            logs.info("\nNenhuma reserva encontrado no Excel.")
            return
        try:
            driver_mapfre, profile_dir_mapfre = None, None
            driver_mapfre, profile_dir_mapfre = setup_driver_mapfre()   
            instante_ultimo_login = time.time()

            for indice, reserva in enumerate(reservas, start=1):
                try:
                    separador = "=" * 90
                    id_reserva = reserva.get("reserva", "")

                    try:
                        if not driver_mapfre:
                            raise RuntimeError("Driver Mapfre inexistente")
                        _ = driver_mapfre.current_url
                        _ = driver_mapfre.window_handles
                    except Exception:
                        logs.error("ERRO - Driver Mapfre ficou indisponivel. Recriando sessao.")
                        print("ERRO - Driver Mapfre ficou indisponivel. Recriando sessao.")
                        driver_mapfre, profile_dir_mapfre = renovar_driver_mapfre(
                            driver_mapfre,
                            profile_dir_mapfre,
                        )
                        instante_ultimo_login = time.time()

                    if time.time() - instante_ultimo_login >= tempo_renovar_sessao:
                        logs.info("Renovando sessao Mapfre por tempo de uso.")
                        print("Renovando sessao Mapfre por tempo de uso.")
                        driver_mapfre, profile_dir_mapfre = renovar_driver_mapfre(
                            driver_mapfre,
                            profile_dir_mapfre,
                        )
                        instante_ultimo_login = time.time()

                    print(f"\n\n{separador}")
                    print(f"Iniciando reserva {indice}/{len(reservas)}: {id_reserva}")
                    print(f"{separador}\n")
                    logs.info(f"\n\n{separador}")
                    logs.info(f"Iniciando reserva {indice}/{len(reservas)}: {id_reserva}")
                    logs.info(f"{separador}\n")
                    
                    print("Entrando em processar_reserva_arquivos")
                    logs.info("\nEntrando em processar_reserva_arquivos")
                    quantidade_arquivos, quantidade_baixado, orgao, link, processou, msg = processar_reserva_arquivos(driver_mapfre, reserva)
                    print("Saiu de processar_reserva_arquivos")
                    logs.info("\nSaiu de processar_reserva_arquivos")

                    texto_msg = str(msg).lower()
                    if (
                        not processou
                        and (
                            "janela do arquivo foi fechada antes do download" in texto_msg
                            or "carregamento da aba do arquivo foi interrompido" in texto_msg
                            or "sessao do navegador foi encerrada" in texto_msg
                            or "sessao do navegador ficou invalida" in texto_msg
                            or "conexao com o navegador foi recusada" in texto_msg
                        )
                    ):
                        logs.error("\nERRO - Falha transitoria detectada. Recriando sessao e tentando a reserva novamente.")
                        print("\nERRO - Falha transitoria detectada. Recriando sessao e tentando a reserva novamente.")
                        driver_mapfre, profile_dir_mapfre = renovar_driver_mapfre(
                            driver_mapfre,
                            profile_dir_mapfre,
                        )
                        instante_ultimo_login = time.time()
                        print("Entrando em processar_reserva_arquivos - retry")
                        logs.info("\nEntrando em processar_reserva_arquivos - retry")
                        quantidade_arquivos, quantidade_baixado, orgao, link, processou, msg = processar_reserva_arquivos(driver_mapfre, reserva)
                        print("Saiu de processar_reserva_arquivos - retry")
                        logs.info("\nSaiu de processar_reserva_arquivos - retry")
                    
                    print("Entrando em atualizar_planilha")
                    logs.info("\nEntrando em atualizar_planilha")
                    atualizar_planilha(quantidade_arquivos, quantidade_baixado, orgao, link, caminho_excel, id_reserva,  processou, msg)
                    print("Saiu de atualizar_planilha")
                    logs.info("\nSaiu de atualizar_planilha")
                    
                    print(f"\nReserva finalizada {indice}/{len(reservas)}: {id_reserva}")
                    print(f"{separador}\n")
                    logs.info(f"\nReserva finalizada {indice}/{len(reservas)}: {id_reserva}")
                    logs.info(f"{separador}\n")
                except Exception as ex_link:
                    msg = f"ERRO - Ao processar reserva: {ex_link}"
                    id_reserva = reserva.get("reserva", "")
                    traceback_reserva = traceback.format_exc()

                    logs.error(f"\nERRO - Ao processar reserva {indice}/{len(reservas)}: {reserva} - {ex_link}\n")
                    logs.error(traceback_reserva)
                    print(f"ERRO - Ao processar reserva {indice}/{len(reservas)}: {ex_link}")
                    print(traceback_reserva)

                    texto_erro = str(ex_link).lower()
                    if (
                        "failed to establish a new connection" in texto_erro
                        or "max retries exceeded" in texto_erro
                        or "connection refused" in texto_erro
                        or "invalid session id" in texto_erro
                        or "web view not found" in texto_erro
                        or "target window already closed" in texto_erro
                    ):
                        try:
                            logs.error("\nERRO - Sessao do driver perdida. Recriando driver Mapfre.")
                            print("\nERRO - Sessao do driver perdida. Recriando driver Mapfre.")
                            driver_mapfre, profile_dir_mapfre = renovar_driver_mapfre(driver_mapfre,profile_dir_mapfre)
                            instante_ultimo_login = time.time()
                        except Exception as ex_renovar:
                            logs.error(f"\nERRO - Nao foi possivel recriar o driver Mapfre: {ex_renovar}")

                    atualizar_planilha(0, 0, "", "", caminho_excel, id_reserva, False, msg)
                    continue

            logs.info("\nBot Mapfre finalizado.\n")
            
        except Exception as drive_ex:
            logs.error(f"\nERRO - Ao acessar driver: {drive_ex}")
            logs.error(traceback.format_exc())
            print(f"ERRO FATAL NO DRIVER: {drive_ex}")
            print(traceback.format_exc())
        
        finally:
            finalizar_driver(driver_mapfre, profile_dir_mapfre, contexto="driver Mapfre")

    except Exception as ex:
        logs.error(f"\nERRO - Ao executar o bot Mapfre: {ex}")
        logs.error(traceback.format_exc())
        print(f"ERRO FATAL - Ao executar o bot Mapfre: {ex}")
        print(traceback.format_exc())
        

def renovar_driver_mapfre(driver_mapfre, profile_dir_mapfre):
    finalizar_driver(driver_mapfre, profile_dir_mapfre, contexto="driver Mapfre")

    return setup_driver_mapfre()


def setup_driver_mapfre():
    driver, profile_dir = criar_driver(mostrar_browser=False)
    url_login = configuracoes.get("mafre", {}).get("url_login")
    driver.get(url_login)
    if not processar_login_mafre(driver):
        raise RuntimeError("\nERRO - Login Mapfre nao foi realizado")
    return driver, profile_dir
