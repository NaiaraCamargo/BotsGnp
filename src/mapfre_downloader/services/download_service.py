import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from pncp_shared.config.controle_config import configuracoes
from pncp_shared.logs.controle_logs import logs


def nome_seguro(valor):
    try:
        valor = valor or ""
        valor = re.sub(r'[<>:"/\\|?*\r\n\t]+', " ", valor)
        valor = re.sub(r"\s+", " ", valor).strip()
        return valor or "sem_descricao"
    except Exception as ex:
        logs.error(f"ERRO ao limpar nome do arquivo: {ex}")
        return "sem_descricao"


def mensagem_resumida_erro(excecao, mensagem_padrao="Falha ao abrir ou baixar arquivo"):
    try:
        mensagem = str(excecao or "").strip()

        if "Stacktrace:" in mensagem:
            mensagem = mensagem.split("Stacktrace:")[0].strip()
        if "Message:" in mensagem:
            mensagem = mensagem.split("Message:", 1)[1].strip()

        if not mensagem:
            return mensagem_padrao

        mensagem_lower = mensagem.lower()

        if "target window already closed" in mensagem_lower or "web view not found" in mensagem_lower:
            return "Janela do arquivo foi fechada antes do download"
        if "target frame detached" in mensagem_lower or "cannot determine loading status" in mensagem_lower:
            return "Carregamento da aba do arquivo foi interrompido"
        if "failed to establish a new connection" in mensagem_lower or "max retries exceeded" in mensagem_lower:
            return "Sessao do navegador foi encerrada"
        if "invalid session id" in mensagem_lower:
            return "Sessao do navegador ficou invalida"
        if "timeout" in mensagem_lower:
            return "Tempo limite excedido ao abrir ou baixar arquivo"
        if "403" in mensagem_lower:
            return "Acesso negado ao baixar arquivo"
        if "404" in mensagem_lower:
            return "Arquivo nao encontrado para download"
        if "connection refused" in mensagem_lower:
            return "Conexao com o navegador foi recusada"

        mensagem = " ".join(mensagem.split())

        if mensagem.lower() in {"message:", "message", "stacktrace:"}:
            return mensagem_padrao

        return mensagem
    except Exception:
        return mensagem_padrao


def erro_transitorio_de_janela_ou_sessao(excecao):
    try:
        mensagem = str(excecao or "").lower()
        return (
            "target window already closed" in mensagem
            or "web view not found" in mensagem
            or "target frame detached" in mensagem
            or "cannot determine loading status" in mensagem
            or "invalid session id" in mensagem
            or "failed to establish a new connection" in mensagem
            or "max retries exceeded" in mensagem
            or "connection refused" in mensagem
        )
    except Exception:
        return False

def normalizar_valor_premio(valor):
    try:
        if valor is None:
            return 0

        if isinstance(valor, (int, float)):
            return float(valor)

        valor = str(valor).strip()
        valor = re.sub(r"[^\d,.-]", "", valor)

        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")

        return float(valor)
    except Exception as ex:
        logs.error(f"\nERRO ao normalizar valor do premio '{valor}': {ex}")
        return 0


def nome_faixa_premio(valor_premio):
    try:
        premio = normalizar_valor_premio(valor_premio)
        milhao = 1_000_000
        meio_milhao = 500_000
        cem_mil = 100_000

        if premio <= 0:
            return "SEM VALOR PREMIO"

        if premio <= cem_mil:
            return "ATE 100 MIL"

        if premio <= milhao:
            inicio = int((premio - 1) // cem_mil) * cem_mil
            fim = inicio + cem_mil
            return f"{inicio // cem_mil * 100} A {fim // cem_mil * 100} MIL"

        if premio <= 10 * milhao:
            inicio = int((premio - 1) // milhao) * milhao
            fim = inicio + milhao
            return f"{inicio // milhao} A {fim // milhao} MILHOES"

        inicio = int((premio - 1) // meio_milhao) * meio_milhao
        fim = inicio + meio_milhao

        inicio_milhoes = inicio / milhao
        fim_milhoes = fim / milhao

        return f"{inicio_milhoes:g} A {fim_milhoes:g} MILHOES"
    except Exception as ex:
        logs.error(f"\nERRO ao gerar faixa do premio: {ex}")
        return "PREMIO NAO IDENTIFICADO"


def obter_pasta_reserva(reserva, id_reserva, orgao):
    try:
        pasta_downloads = Path(configuracoes.get("pasta_downloads"))
        nome_aba_base = configuracoes.get("aba_base") or configuracoes.get("aba_excel") or "SEM ABA"
        premio = reserva.get("premio") or reserva.get("PREMIO") or reserva.get("PRÊMIO") or reserva.get("PRÃŠMIO") or 0

        pasta_aba = pasta_downloads / nome_seguro(nome_aba_base)
        pasta_faixa = pasta_aba / nome_seguro(nome_faixa_premio(premio))
        pasta_reserva = pasta_faixa / nome_seguro(f"{id_reserva}_{orgao}")

        pasta_reserva.mkdir(parents=True, exist_ok=True)

        logs.info(f"\nPasta da reserva preparada: {pasta_reserva}")
        return pasta_reserva
    except Exception as ex:
        logs.error(f"\nERRO ao obter/criar pasta da reserva: {ex}")
        raise

def extensao_por_content_type(content_type):
    try:
        content_type = (content_type or "").lower()

        if "pdf" in content_type:
            return ".pdf"
        if "zip" in content_type:
            return ".zip"
        if "msword" in content_type:
            return ".doc"
        if "wordprocessingml" in content_type:
            return ".docx"
        if "excel" in content_type or "spreadsheetml" in content_type:
            return ".xlsx"
        if "jpeg" in content_type:
            return ".jpg"
        if "png" in content_type:
            return ".png"

        return ""
    except Exception as ex:
        logs.error(f"\nERRO ao identificar extensao pelo content-type: {ex}")
        return ""


def extensao_por_url(url):
    try:
        caminho = unquote(urlparse(url).path)
        extensao = Path(caminho).suffix

        extensoes_ignoradas = {".aspx", ".ashx", ".php", ".html", ".htm"}

        if extensao and extensao.lower() not in extensoes_ignoradas:
            return extensao

        return ""
    except Exception as ex:
        logs.error(f"\nERRO ao identificar extensao pela URL: {ex}")
        return ""


def caminho_disponivel(destino):
    try:
        destino = Path(destino)

        if not destino.exists():
            return destino

        contador = 1
        while True:
            novo_destino = destino.with_name(f"{destino.stem}_{contador}{destino.suffix}")
            if not novo_destino.exists():
                return novo_destino
            contador += 1
    except Exception as ex:
        logs.error(f"\nERRO ao gerar caminho disponivel: {ex}")
        raise


def obter_pasta_download_driver(driver):
    try:
        download_dir = getattr(driver, "download_dir", "")
        if download_dir:
            pasta = Path(download_dir)
            pasta.mkdir(parents=True, exist_ok=True)
            return pasta

        pasta = Path.home() / "Downloads"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta
    except Exception as ex:
        logs.error(f"\nERRO ao obter pasta de download do driver: {ex}")
        raise


def capturar_estado_downloads(pasta_download):
    try:
        estado = {}
        for arquivo in Path(pasta_download).glob("*"):
            if arquivo.is_file():
                estado[arquivo.name] = arquivo.stat().st_size
        return estado
    except Exception as ex:
        logs.error(f"\nERRO ao capturar estado da pasta de downloads: {ex}")
        return {}


def aguardar_download_direto(driver, estado_antes, timeout=60):
    try:
        pasta_download = obter_pasta_download_driver(driver)
        fim = time.time() + timeout

        while time.time() < fim:
            arquivos_crdownload = list(pasta_download.glob("*.crdownload"))
            estado_depois = capturar_estado_downloads(pasta_download)

            novos_arquivos = []
            for nome_arquivo in estado_depois.keys():
                if nome_arquivo.endswith(".crdownload"):
                    continue
                if nome_arquivo not in estado_antes:
                    novos_arquivos.append(pasta_download / nome_arquivo)

            if novos_arquivos and not arquivos_crdownload:
                novos_arquivos.sort(key=lambda arquivo: arquivo.stat().st_mtime, reverse=True)
                return novos_arquivos[0]

            time.sleep(1.0)

        return None
    except Exception as ex:
        logs.error(f"\nERRO ao aguardar download direto: {ex}")
        return None


def obter_download_concluido_recente(driver, segundos=10):
    try:
        pasta_download = obter_pasta_download_driver(driver)
        arquivos = [arquivo for arquivo in pasta_download.glob("*") if arquivo.is_file() and not arquivo.name.endswith(".crdownload")]
        if not arquivos:
            return None

        agora = time.time()
        arquivos.sort(key=lambda arquivo: arquivo.stat().st_mtime, reverse=True)
        arquivo_recente = arquivos[0]

        if agora - arquivo_recente.stat().st_mtime <= segundos:
            return arquivo_recente

        return None
    except Exception as ex:
        logs.error(f"\nERRO ao localizar download concluido recente: {ex}")
        return None


def mover_download_direto_para_reserva(arquivo_origem, destino_base):
    try:
        arquivo_origem = Path(arquivo_origem)
        destino_base = Path(destino_base)
        extensao = arquivo_origem.suffix or ".pdf"
        destino_final = caminho_disponivel(destino_base.with_suffix(extensao))

        shutil.move(str(arquivo_origem), str(destino_final))

        if arquivo_origem.exists():
            try:
                arquivo_origem.unlink()
            except Exception:
                pass

        return str(destino_final)
    except Exception as ex:
        logs.error(f"\nERRO ao mover download direto para a pasta da reserva: {ex}")
        raise


def nome_zip_reserva(id_reserva, orgao):
    try:
        return nome_seguro(f"{id_reserva}_{orgao}") + ".zip"
    except Exception as ex:
        logs.error(f"\nERRO ao gerar nome do ZIP da reserva: {ex}")
        raise


def carregar_arquivos_do_zip_existente(pasta_reserva, id_reserva, orgao):
    try:
        pasta_reserva = Path(pasta_reserva)
        caminho_zip = pasta_reserva / nome_zip_reserva(id_reserva, orgao)

        if not caminho_zip.exists():
            return []

        with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
            zip_ref.extractall(pasta_reserva)

        arquivos_existentes = []
        for arquivo in pasta_reserva.iterdir():
            if arquivo.is_file() and arquivo.suffix.lower() != ".zip":
                arquivos_existentes.append({"arquivo": str(arquivo)})

        logs.info(f"\nZIP existente carregado para reaproveitamento: {caminho_zip}")
        return arquivos_existentes
    except Exception as ex:
        logs.error(f"\nERRO ao carregar arquivos do ZIP existente: {ex}")
        return []


def arquivo_ja_existe_na_reserva(nome_base, arquivos_baixados):
    try:
        for arquivo_info in arquivos_baixados:
            caminho_arquivo = Path(arquivo_info.get("arquivo", ""))
            if not caminho_arquivo.exists() or not caminho_arquivo.is_file():
                continue

            stem = caminho_arquivo.stem
            if stem == nome_base or stem.startswith(f"{nome_base}_"):
                return True

        return False
    except Exception as ex:
        logs.error(f"\nERRO ao verificar arquivo ja existente na reserva: {ex}")
        return False


def montar_nome_base_arquivo(id_reserva, arquivo_grid):
    try:
        partes_nome = [str(id_reserva), nome_seguro(arquivo_grid.get("numero")), nome_seguro(arquivo_grid.get("subtipo"))]
        if (arquivo_grid.get("descricao") or "").strip():
            partes_nome.append(nome_seguro(arquivo_grid.get("descricao")))
        return "_".join(partes_nome)
    except Exception as ex:
        logs.error(f"\nERRO ao montar nome base do arquivo: {ex}")
        raise


def preparar_grid_para_arquivo(driver_mapfre, aba_principal, url_arquivo, arquivo_grid):
    try:
        if aba_principal in driver_mapfre.window_handles:
            driver_mapfre.switch_to.window(aba_principal)

        time.sleep(0.5)
        driver_mapfre.get(url_arquivo)
        WebDriverWait(driver_mapfre, 20).until(EC.presence_of_element_located((By.ID, "grdDocs")))

        if not ir_para_pagina_grd_docs(driver_mapfre, arquivo_grid.get("pagina_grid", 1)):
            raise Exception(f"Nao foi possivel abrir a pagina {arquivo_grid.get('pagina_grid', 1)} da grid")

        xpath_link = f"//table[@id='grdDocs']//a[contains(@href, \"{arquivo_grid['target']}\")]"
        return WebDriverWait(driver_mapfre, 20).until(EC.element_to_be_clickable((By.XPATH, xpath_link)))
    except Exception as ex:
        logs.error(f"\nERRO ao preparar grid do arquivo numero={arquivo_grid.get('numero')} subtipo={arquivo_grid.get('subtipo')}: {mensagem_resumida_erro(ex)}")
        raise


def aguardar_evento_arquivo(driver_mapfre, abas_antes, estado_downloads_antes, timeout_aba=8, timeout_download=60):
    try:
        pasta_download = obter_pasta_download_driver(driver_mapfre)
        fim_aba = time.time() + timeout_aba

        while time.time() < fim_aba:
            try:
                if len(driver_mapfre.window_handles) > len(abas_antes):
                    nova_aba = next(aba for aba in driver_mapfre.window_handles if aba not in abas_antes)
                    return "aba", nova_aba
            except Exception:
                pass

            arquivo_direto = aguardar_download_direto(driver_mapfre, estado_downloads_antes, timeout=1)
            if arquivo_direto:
                return "download", arquivo_direto

            if list(pasta_download.glob("*.crdownload")):
                arquivo_direto = aguardar_download_direto(driver_mapfre, estado_downloads_antes, timeout=timeout_download)
                if arquivo_direto:
                    return "download", arquivo_direto

            time.sleep(0.5)

        arquivo_direto = aguardar_download_direto(driver_mapfre, estado_downloads_antes, timeout=3)
        if arquivo_direto:
            return "download", arquivo_direto

        return "", None
    except Exception as ex:
        logs.error(f"\nERRO ao aguardar abertura da aba ou download direto: {mensagem_resumida_erro(ex)}")
        return "", None


def baixar_arquivo_mapfre(driver_mapfre, aba_principal, url_arquivo, arquivo_grid, pasta_reserva, nome_base):
    nova_aba = None
    try:
        print(f"Abrindo arquivo {arquivo_grid.get('numero')} - {arquivo_grid.get('subtipo')}")
        link_ver_arquivo = preparar_grid_para_arquivo(driver_mapfre, aba_principal, url_arquivo, arquivo_grid)
        abas_antes = driver_mapfre.window_handles[:]
        estado_downloads_antes = capturar_estado_downloads(obter_pasta_download_driver(driver_mapfre))

        driver_mapfre.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_ver_arquivo)
        time.sleep(1.0)
        link_ver_arquivo.click()

        tipo_evento, evento = aguardar_evento_arquivo(driver_mapfre, abas_antes, estado_downloads_antes)

        if tipo_evento == "download":
            print(f"Download direto identificado para arquivo {arquivo_grid.get('numero')}")
            return mover_download_direto_para_reserva(evento, pasta_reserva / nome_base)

        if tipo_evento == "aba":
            nova_aba = evento
            print(f"Aba nova identificada para arquivo {arquivo_grid.get('numero')}")
            driver_mapfre.switch_to.window(nova_aba)
            time.sleep(1.0)
            WebDriverWait(driver_mapfre, 20).until(lambda driver: driver.current_url and driver.current_url != "about:blank")
            return baixar_url_com_cookies_do_selenium(driver_mapfre, driver_mapfre.current_url, pasta_reserva / nome_base)

        raise Exception("Nenhuma nova aba foi aberta e nenhum download direto foi identificado")
    finally:
        try:
            if nova_aba and nova_aba in driver_mapfre.window_handles:
                driver_mapfre.close()
            if aba_principal in driver_mapfre.window_handles:
                driver_mapfre.switch_to.window(aba_principal)
        except Exception as ex:
            logs.error(f"\nERRO ao fechar ou retornar aba do arquivo: {mensagem_resumida_erro(ex)}")


def baixar_url_com_cookies_do_selenium(driver, url, destino_base):
    try:
        logs.info(f"\nIniciando download da URL: {url}\n")
        sessao = requests.Session()

        for cookie in driver.get_cookies():
            sessao.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))

        resposta = sessao.get(url, stream=True, timeout=60)
        resposta.raise_for_status()

        destino_base = Path(destino_base)
        extensao = destino_base.suffix

        if not extensao:
            extensao = (
                extensao_por_content_type(resposta.headers.get("Content-Type", ""))
                or extensao_por_url(url)
                or ".pdf"
            )

        destino = caminho_disponivel(destino_base.with_suffix(extensao))

        with open(destino, "wb") as arquivo:
            for chunk in resposta.iter_content(chunk_size=1024 * 256):
                if chunk:
                    arquivo.write(chunk)
                    
        return str(destino)
    except Exception as ex:
        logs.error(f"\nERRO ao baixar arquivo da URL {url}: {ex}")
        raise


def compactar_arquivos_baixados(arquivos_baixados, pasta_downloads, id_reserva, orgao):
    try:
        if not arquivos_baixados:
            logs.info("\nNenhum arquivo baixado para compactar.")
            return ""

        arquivos_para_zip = []

        for arquivo_info in arquivos_baixados:
            try:
                caminho_arquivo = Path(arquivo_info.get("arquivo", ""))

                if not caminho_arquivo.exists() or not caminho_arquivo.is_file():
                    logs.info(f"\nArquivo ignorado na compactacao, nao encontrado: {caminho_arquivo}")
                    continue

                arquivos_para_zip.append(caminho_arquivo)
            except Exception as ex_arquivo:
                logs.error(f"\nERRO ao preparar arquivo para compactacao: {ex_arquivo}")
                continue

        if not arquivos_para_zip:
            logs.info("\nNenhum arquivo valido encontrado para gerar ZIP.")
            return ""

        pasta_downloads = Path(pasta_downloads)
        nome_zip = nome_zip_reserva(id_reserva, orgao)
        caminho_zip = pasta_downloads / nome_zip

        if caminho_zip.exists():
            try:
                caminho_zip.unlink()
                logs.info(f"\nZIP antigo removido para recriacao: {caminho_zip}")
            except Exception as ex_zip_antigo:
                logs.error(f"\nERRO ao excluir ZIP antigo {caminho_zip}: {ex_zip_antigo}")
                caminho_zip = caminho_disponivel(caminho_zip)
                logs.info(f"\nNovo caminho de ZIP gerado apos falha ao excluir o antigo: {caminho_zip}")

        logs.info(f"\nIniciando compactacao de {len(arquivos_para_zip)} arquivo(s): {caminho_zip}\n")

        arquivos_zipados = []

        with zipfile.ZipFile(caminho_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,) as zip_ref:
            for caminho_arquivo in arquivos_para_zip:
                try:
                    zip_ref.write(caminho_arquivo, arcname=caminho_arquivo.name)
                    arquivos_zipados.append(caminho_arquivo)
                    logs.info(f"\nArquivo adicionado ao ZIP: {caminho_arquivo}")
                except Exception as ex_zip_arquivo:
                    logs.error(f"\nERRO ao adicionar arquivo ao ZIP {caminho_arquivo}: {ex_zip_arquivo}")
                    continue

        if len(arquivos_zipados) != len(arquivos_para_zip):
            logs.error("\nERRO ao compactar: nem todos os arquivos foram adicionados ao ZIP.")
            try:
                if caminho_zip.exists():
                    caminho_zip.unlink()
            except Exception as ex_zip_incompleto:
                logs.error(f"\nERRO ao excluir ZIP incompleto {caminho_zip}: {ex_zip_incompleto}")
            return ""

        tamanho_original = sum(arquivo.stat().st_size for arquivo in arquivos_zipados)
        tamanho_zip = caminho_zip.stat().st_size
        
        logs.info( "\nZIP criado: %s | original=%s bytes | zip=%s bytes", caminho_zip, tamanho_original, tamanho_zip,)
        
        for caminho_arquivo in arquivos_zipados:
            try:
                if caminho_arquivo.exists() and caminho_arquivo.is_file():
                    caminho_arquivo.unlink()
            except Exception as ex_excluir:
                logs.error(f"\nERRO ao excluir arquivo original {caminho_arquivo}: {ex_excluir}")
                continue

        return str(caminho_zip)
    except Exception as ex:
        logs.error(f"\nERRO ao compactar arquivos baixados: {ex}")
        return ""
        
def extrair_arquivos_grd_docs(driver_mapfre, pagina_grid=1):
    try:
        WebDriverWait(driver_mapfre, 20).until(EC.presence_of_element_located((By.ID, "grdDocs")))

        linhas = driver_mapfre.find_elements(By.CSS_SELECTOR, "#grdDocs tr")
        arquivos = []

        for indice, linha in enumerate(linhas[1:], start=1):
            try:
                colunas = linha.find_elements(By.TAG_NAME, "td")

                if len(colunas) < 8:
                    logs.info(f"\nLinha {indice} ignorada: quantidade de colunas invalida.")
                    continue

                numero_arquivo = colunas[1].text.strip()
                tipo = colunas[2].text.strip()
                subtipo = colunas[3].text.strip()
                descricao = colunas[4].text.strip()
                data_inclusao = colunas[6].text.strip()

                if not numero_arquivo.isdigit():
                    logs.info(f"\nLinha {indice} ignorada: numero de arquivo invalido: {numero_arquivo}")
                    continue

                if tipo.upper() != "ARQUIVO":
                    logs.info(f"\nLinha {indice} ignorada: tipo invalido: {tipo}")
                    continue

                if subtipo.isdigit():
                    logs.info(f"\nLinha {indice} ignorada: subtipo invalido: {subtipo}")
                    continue

                coluna_link = colunas[7]
                links = coluna_link.find_elements(By.TAG_NAME, "a")

                if not links:
                    time.sleep(0.5)
                    links = coluna_link.find_elements(By.TAG_NAME, "a")

                if not links:
                    logs.info(f"\nLinha {indice} ignorada: link do arquivo nao encontrado.")
                    print(f"\nLinha {indice} ignorada: link do arquivo nao encontrado.")
                    continue

                link_ver_arquivo = links[0]
                href = link_ver_arquivo.get_attribute("href")

                match = re.search(r"__doPostBack\('([^']+)'\s*,\s*'([^']*)'\)", href)

                if not match:
                    logs.info(f"Linha {indice} ignorada: postback nao encontrado.")
                    continue

                arquivos.append({
                    "numero": str(numero_arquivo).strip(),
                    "pagina_grid": pagina_grid,
                    "subtipo": subtipo,
                    "descricao": descricao,
                    "data_inclusao": data_inclusao,
                    "target": match.group(1),
                    "argument": match.group(2),
                })
                
            except Exception as ex_linha:
                logs.error(f"\nERRO ao extrair linha {indice} da grid: {ex_linha}")
                continue

        return arquivos
    except Exception as ex:
        logs.error(f"\nERRO ao extrair arquivos da grid: {ex}")
        return []


def chave_unica_arquivo_grid(arquivo):
    try:
        return "|".join([
            str(arquivo.get("numero", "")).strip(),
            str(arquivo.get("subtipo", "")).strip(),
            str(arquivo.get("descricao", "")).strip(),
            str(arquivo.get("data_inclusao", "")).strip(),
            str(arquivo.get("target", "")).strip(),
            str(arquivo.get("argument", "")).strip(),
        ])
    except Exception as ex:
        logs.error(f"\nERRO ao montar chave unica do arquivo da grid: {ex}")
        return ""


def extrair_paginas_grd_docs(driver_mapfre):
    try:
        paginas = set()
        links_paginacao = driver_mapfre.find_elements(By.CSS_SELECTOR, "#grdDocs a[href*=\"Page$\"]")

        for link in links_paginacao:
            href = link.get_attribute("href") or ""
            match = re.search(r"__doPostBack\('grdDocs','Page\$(\d+)'\)", href)
            if match:
                paginas.add(int(match.group(1)))

        return sorted(paginas)
    except Exception as ex:
        logs.error(f"\nERRO ao extrair paginacao da grid: {ex}")
        return []


def obter_assinatura_grd_docs(driver_mapfre):
    try:
        linhas = driver_mapfre.find_elements(By.CSS_SELECTOR, "#grdDocs tr")
        assinatura = []

        for linha in linhas[1:]:
            try:
                colunas = linha.find_elements(By.TAG_NAME, "td")
                if len(colunas) < 8:
                    continue

                numero = colunas[1].text.strip()
                subtipo = colunas[3].text.strip()
                data_inclusao = colunas[6].text.strip()
                href = colunas[7].find_element(By.TAG_NAME, "a").get_attribute("href") or ""

                assinatura.append(f"{numero}|{subtipo}|{data_inclusao}|{href}")
            except Exception:
                continue

        return "||".join(assinatura)
    except Exception:
        return ""


def obter_html_grd_docs(driver_mapfre):
    try:
        return driver_mapfre.find_element(By.ID, "grdDocs").get_attribute("innerHTML") or ""
    except Exception:
        return ""


def ir_para_pagina_grd_docs(driver_mapfre, pagina_destino):
    try:
        pagina_destino = int(pagina_destino or 1)

        if pagina_destino <= 1:
            return True

        WebDriverWait(driver_mapfre, 20).until(EC.presence_of_element_located((By.ID, "grdDocs")))

        for tentativa in range(1, 4):
            try:
                html_anterior = obter_html_grd_docs(driver_mapfre)
                assinatura_anterior = obter_assinatura_grd_docs(driver_mapfre)

                driver_mapfre.execute_script("__doPostBack('grdDocs', arguments[0]);", f"Page${pagina_destino}")

                WebDriverWait(driver_mapfre, 20).until(
                    lambda driver: obter_html_grd_docs(driver) != html_anterior or obter_assinatura_grd_docs(driver) != assinatura_anterior
                )

                time.sleep(1.0)

                assinatura_nova = obter_assinatura_grd_docs(driver_mapfre)
                if assinatura_nova and assinatura_nova != assinatura_anterior:
                    logs.info(f"\nGrid grdDocs posicionada na pagina {pagina_destino}.")
                    return True
            except Exception as ex_tentativa:
                logs.error(f"\nERRO ao ir para pagina {pagina_destino} da grid tentativa={tentativa}: {mensagem_resumida_erro(ex_tentativa)}")
                time.sleep(1.0)

        logs.error(f"\nERRO ao navegar para pagina {pagina_destino} da grid.")
        return False
    except Exception as ex:
        logs.error(f"\nERRO ao preparar navegacao da pagina {pagina_destino} da grid: {mensagem_resumida_erro(ex)}")
        return False


def extrair_todos_arquivos_grd_docs(driver_mapfre):
    try:
        arquivos = []
        paginas_visitadas = {1}
        chaves_ja_vistas = set()

        WebDriverWait(driver_mapfre, 20).until(EC.presence_of_element_located((By.ID, "grdDocs")))

        arquivos_pagina_1 = extrair_arquivos_grd_docs(driver_mapfre, pagina_grid=1)
        for arquivo in arquivos_pagina_1:
            chave = chave_unica_arquivo_grid(arquivo)
            if chave and chave not in chaves_ja_vistas:
                arquivos.append(arquivo)
                chaves_ja_vistas.add(chave)
        print(f"Grid pagina 1: {len(arquivos_pagina_1)} itens lidos | {len(arquivos)} unicos acumulados")
        paginas_pendentes = extrair_paginas_grd_docs(driver_mapfre)

        while paginas_pendentes:
            pagina = paginas_pendentes.pop(0)

            if pagina in paginas_visitadas:
                continue

            if not ir_para_pagina_grd_docs(driver_mapfre, pagina):
                logs.error(f"\nERRO ao carregar pagina {pagina} da grid grdDocs.")
                continue

            arquivos_pagina = extrair_arquivos_grd_docs(driver_mapfre, pagina_grid=pagina)
            adicionados_pagina = 0
            for arquivo in arquivos_pagina:
                chave = chave_unica_arquivo_grid(arquivo)
                if chave and chave not in chaves_ja_vistas:
                    arquivos.append(arquivo)
                    chaves_ja_vistas.add(chave)
                    adicionados_pagina += 1
            print(f"Grid pagina {pagina}: {len(arquivos_pagina)} itens lidos | {adicionados_pagina} novos | {len(arquivos)} unicos acumulados")
            paginas_visitadas.add(pagina)

            novas_paginas = extrair_paginas_grd_docs(driver_mapfre)
            for nova_pagina in novas_paginas:
                if nova_pagina not in paginas_visitadas and nova_pagina not in paginas_pendentes:
                    paginas_pendentes.append(nova_pagina)

        logs.info(f"\nTotal de arquivos unicos extraidos da grid: {len(arquivos)}")
        return arquivos
    except Exception as ex:
        logs.error(f"\nERRO ao extrair todos os arquivos da grid: {ex}")
        return []

     
def processar_reserva_arquivos(driver_mapfre, reserva):
    try:
        id_reserva = reserva.get("reserva") or ""
        
        if id_reserva == "":
            msg = "ID da reserva veio vazio"
            logs.info(f"################# {msg.upper()} ###################")
            return 0, 0, "", "", False, msg
            
        url_arquivo_digital = configuracoes.get("mafre", {}).get("url_arquivo_digital")
        url_arquivo = re.sub(r"id=\d+", f"id={id_reserva}", url_arquivo_digital)
        driver_mapfre.get(url_arquivo)
        
        WebDriverWait(driver_mapfre, 20).until(EC.presence_of_all_elements_located((By.ID, "uptPnlForm")))
        
        arquivos_grid = extrair_todos_arquivos_grd_docs(driver_mapfre)
        
        orgao_campo = WebDriverWait(driver_mapfre, 20).until(EC.presence_of_element_located((By.NAME, "cliente")))
        orgao = orgao_campo.get_attribute("value")
        pasta_reserva = obter_pasta_reserva(reserva, id_reserva, orgao)
        
        if not arquivos_grid:
            msg = "\nNenhum arquivo encontrado na grid grdDocs"
            logs.info(msg)
            return 0, 0, orgao, url_arquivo, False, msg

        arquivos_baixados = carregar_arquivos_do_zip_existente(pasta_reserva, id_reserva, orgao)
        erros_download = []
        aba_principal = driver_mapfre.current_window_handle

        for indice, arquivo_grid in enumerate(arquivos_grid, start=1):
            nome_base = montar_nome_base_arquivo(id_reserva, arquivo_grid)
            baixou_com_sucesso = False
            ultimo_erro = ""

            if arquivo_ja_existe_na_reserva(nome_base, arquivos_baixados):
                logs.info("\nArquivo Mapfre %s/%s ja existente no ZIP/pasta da reserva: %s", indice, len(arquivos_grid), nome_base)
                print("Ja existente:", nome_base)
                continue

            for tentativa in range(1, 3):
                try:
                    print(f"\nProcessando arquivo {indice}/{len(arquivos_grid)} numero={arquivo_grid.get('numero')} subtipo={arquivo_grid.get('subtipo')} tentativa={tentativa}")
                    
                    caminho_baixado = baixar_arquivo_mapfre(driver_mapfre, aba_principal, url_arquivo, arquivo_grid, pasta_reserva, nome_base)
                    arquivos_baixados.append({
                        "numero": arquivo_grid["numero"], 
                        "subtipo": arquivo_grid["subtipo"], 
                        "descricao": arquivo_grid["descricao"], 
                        "arquivo": caminho_baixado
                        })
                    
                    logs.info("\nArquivo Mapfre baixado %s/%s: %s", indice, len(arquivos_grid), caminho_baixado)
                    print(f"Baixado: {caminho_baixado} \n")
                    baixou_com_sucesso = True
                    break

                except Exception as ex_arquivo:
                    ultimo_erro = mensagem_resumida_erro(ex_arquivo)
                    logs.error("\nERRO ao baixar arquivo Mapfre %s/%s numero=%s subtipo=%s pagina=%s tentativa=%s: %s", indice, len(arquivos_grid), arquivo_grid.get("numero"), arquivo_grid.get("subtipo"), arquivo_grid.get("pagina_grid"), tentativa, ultimo_erro)

                    if tentativa == 1 and erro_transitorio_de_janela_ou_sessao(ex_arquivo):
                        arquivo_direto = obter_download_concluido_recente(driver_mapfre, segundos=10)
                        if arquivo_direto:
                            try:
                                caminho_baixado = mover_download_direto_para_reserva(arquivo_direto, pasta_reserva / nome_base)
                                arquivos_baixados.append({
                                    "numero": arquivo_grid["numero"], 
                                    "subtipo": arquivo_grid["subtipo"], 
                                    "descricao": arquivo_grid["descricao"], 
                                    "arquivo": caminho_baixado
                                    })
                                
                                logs.info("\nArquivo Mapfre recuperado por download direto apos erro de janela %s/%s: %s", indice, len(arquivos_grid), caminho_baixado)
                                print("Baixado apos erro de janela:", caminho_baixado)
                                baixou_com_sucesso = True
                                break
                            except Exception:
                                pass
                        continue
                    
                    break

            if not baixou_com_sucesso:
                erros_download.append("Arquivo numero="f"{arquivo_grid.get('numero')} "f"subtipo={arquivo_grid.get('subtipo')}: "f"{ultimo_erro or 'Falha ao abrir ou baixar arquivo'}")
                continue

        caminho_zip = compactar_arquivos_baixados(arquivos_baixados, pasta_reserva, id_reserva, orgao)
        quantidade_arquivos = len(arquivos_grid)
        quantidade_baixado = len(arquivos_baixados)

        if quantidade_arquivos == 0:
            msg = "Nenhum arquivo foi baixado com sucesso"
            logs.error(msg)
            return 0, quantidade_baixado, orgao, url_arquivo, False, msg

        if not caminho_zip:
            msg = "ERRO - Arquivos baixados, mas ZIP nao foi criado"
            logs.error(msg)
            return quantidade_arquivos, quantidade_baixado, orgao, url_arquivo, False, msg

        if erros_download:
            msg = "ERRO - Alguns arquivos nao foram baixados: " + " | ".join(erros_download)
            logs.error(msg)
            return quantidade_arquivos, quantidade_baixado, orgao, url_arquivo, False, msg
    
        logs.info(f"Arquivos da reserva {id_reserva} compactados em: {caminho_zip}")
        print("\nZIP criado:", caminho_zip)

        return quantidade_arquivos, quantidade_baixado, orgao, url_arquivo, True, ""
    
    except Exception as ex:
        msg = f"ERRO - Ao processar a url dos arquivos: {ex}"
        logs.error(msg)
        return 0, 0, "", "", False, msg
