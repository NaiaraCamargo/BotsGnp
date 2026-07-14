import re
import requests
import math
import os
import re
import shutil
import zipfile
import mimetypes
import rarfile
import subprocess
import requests
import ghostscript
import pypandoc
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
import os
import pandas as pd

from pncp_shared.logs.controle_logs import *
from pncp_shared.utils.funcoespncp import *

PNCP = "https://pncp.gov.br/api/pncp/v1"

def get_json(url, params=None, timeout=30):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        
        try:
            return r.json()
        except ValueError:
            logs.error(f"[ERRO JSON] Resposta não é JSON válido - URL: {url}")
            return None

    except requests.exceptions.Timeout:
        logs.error(f"[TIMEOUT get_json] URL: {url}")
        return None

    except requests.exceptions.ConnectionError:
        logs.error(f"[ERRO CONEXÃO get_json] URL: {url}")
        return None

    except requests.exceptions.HTTPError as e:
        logs.error(f"[ERRO HTTP get_json] {e} - URL: {url}")
        return None

    except requests.exceptions.RequestException as e:
        logs.error(f"[ERRO REQUEST get_json] {e} - URL: {url}")
        return None

def buscar_arquivos(cnpj: str, ano: int, sequencial: int, link, timeout=30):
    try:
        arquivos_url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos"
        arquivos_response = get_json(arquivos_url, params={"pagina": 1}, timeout=timeout)
        
        if arquivos_response is None:
                return []
            
        arquivos = []
        for arquivo in arquivos_response:
            if not isinstance(arquivo, dict) or not arquivo.get("statusAtivo", True):
                continue

            doc_id = arquivo.get("sequencialDocumento")
            if doc_id is None:
                continue

            arquivos.append({
                "doc_id": int(doc_id),
                "nome": arquivo.get("titulo") or "Desconhecido",
                "tipo": arquivo.get("tipoDocumentoNome") or arquivo.get("tipoDocumentoDescricao") or "",
                "data": arquivo.get("dataPublicacaoPncp") or "",
                "url": arquivo.get("url") or arquivo.get("uri"), 
                "meta": arquivo
            })

        return arquivos

    except Exception as e:
        logs.error(f"[ERRO AO BUSCAR ARQUIVOS] {link} - {e}")
        return []

def salvar_arquivos_api(arquivos, edital, plataforma, cnpj, ano, sequencial):
    try:
        arquivos_baixados = 0
        compactado = False

        pasta_edital, pasta_dia, pasta_comprimidos = obter_caminho_edital(edital, plataforma)

        os.makedirs(pasta_dia, exist_ok=True)
        os.makedirs(pasta_edital, exist_ok=True)

        quantidadeTipoEdital = sum(
            1 for a in arquivos if str(a.get("tipo","")).strip().lower() == "edital"
        )

        for arquivo in arquivos:
            try:
                tipo = str(arquivo.get("tipo", ""))
                titulo = str(arquivo.get("nome", "Desconhecido")).strip()
                nome_limpo = re.sub(r'[\\/:*?"<>|]', '_', titulo)

                doc_id = arquivo.get("doc_id")
                if not doc_id:
                    continue

                for tentativa in range(1, 3):
                    try:
                        resp = baixar_arquivo_api(cnpj, ano, sequencial, int(doc_id), edital.get("Link"))
                        if not resp:
                            continue

                        base_nome, ext = obter_extensao_response(resp, nome_limpo)

                        if not base_nome:
                            base_nome = nome_limpo.replace('.', '-')
                        else:
                            base_nome = str(base_nome).replace('.', '-')

                        if "edital" in tipo.lower():
                            if quantidadeTipoEdital > 1:
                                nome_arquivo = f"1-{base_nome}{ext}"
                            else:
                                nome_arquivo = f"1-Edital{ext}"
                        else:
                            nome_arquivo = f"{base_nome}{ext}"

                        nome_arquivo = re.sub(r'[\\/:*?"<>|]', '_', nome_arquivo)
                        caminho_completo = os.path.join(pasta_edital, nome_arquivo)
                        caminho_em_compactados = os.path.join(pasta_edital, "compactados", nome_arquivo)

                        if os.path.exists(caminho_completo) or os.path.exists(caminho_em_compactados):
                            if os.path.exists(caminho_completo):
                                print(f"O arquivo {nome_arquivo} já existe no caminho {caminho_completo}.\n")
                            if os.path.exists(caminho_em_compactados):
                                print(f"O arquivo {nome_arquivo} já existe no caminho {caminho_em_compactados}.\n")  
                            break

                        with open(caminho_completo, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=1024 * 256):
                                if chunk:
                                    f.write(chunk)

                        arquivos_baixados += 1
                        print(f"[ARQUIVO SALVO VIA API]: {caminho_completo}\n")
                        logs.info(f"[ARQUIVO SALVO VIA API]: {caminho_completo}\n")

                        executar_verificacao_arquivos(caminho_completo, ext, pasta_edital, nome_arquivo)
                        break

                    except Exception as e_download:
                        logs.error(f"[ERRO DOWNLOAD TENTATIVA {tentativa}] doc_id={doc_id} link={edital.get('Link')} erro={e_download}")

            except Exception as e_item:
                logs.error(f"[ERRO PROCESSAR ARQUIVO] {edital.get('Link')} erro={e_item}")

        if arquivos_baixados > 0:
            try:
                compactado = compactar_arquivos(pasta_edital, pasta_comprimidos)
            except Exception as e_zip:
                logs.error(f"[ERRO COMPACTAR] {edital.get('Link')} erro={e_zip}")

        return arquivos_baixados > 0, compactado

    except Exception as e:
        logs.error(f"[ERRO GERAL SALVAR_ARQUIVOS_API] {edital.get('Link')} erro={e}")
        return False

def baixar_arquivo_api(cnpj: str, ano: int, sequencial: int, doc_id: int, link="", timeout=120):
    try:                
        url = f"{PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos/{doc_id}"
        r = requests.get(url, stream=True, timeout=timeout)

        if r.status_code == 200:
            return r
          
        logs.error(f"[FALHA DOWNLOAD] doc_id={doc_id} link={link}")
        return None

    except Exception as e:
        logs.error(f"[ERRO GERAL DOWNLOAD] doc_id={doc_id} link={link} erro={e}")
        return None

def compactar_arquivos(pasta_edital, pasta_compridos):
    try:
        nome_pasta = os.path.basename(pasta_edital)
        zip_path = os.path.join(pasta_compridos, f"{nome_pasta}.zip")

        # Cria o destino, se não existir
        if not os.path.exists(pasta_compridos):
            os.makedirs(pasta_compridos)

        if os.path.exists(zip_path):
            print(f"O arquivo {nome_pasta}.zip já existe no caminho {zip_path}.")
            return
            
        # Remove a pasta "compactados" de dentro da origem, se existir
        #caminho_compactados = os.path.join(pasta_edital, 'compactados')
        #if os.path.exists(caminho_compactados):
            #shutil.rmtree(caminho_compactados)

        # Conta os arquivos, ignorando a pasta "compactados"
        total_arquivos = 0
        for raiz, _, arquivos in os.walk(pasta_edital):
            if 'compactados' in raiz:
                continue
            total_arquivos += len(arquivos)

        if total_arquivos <= 1:
            print(f"Não há mais de 1 arquivo em '{pasta_edital}', não será compactado.")
            return True
        
        # Cria o arquivo ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for raiz, _, arquivos in os.walk(pasta_edital):
                if 'compactados' in raiz:
                    continue
                for arquivo in arquivos:
                    caminho_completo = os.path.join(raiz, arquivo)
                    caminho_relativo = os.path.relpath(caminho_completo, pasta_edital)
                    zipf.write(caminho_completo, arcname=caminho_relativo)

        print(f"Pasta '{pasta_edital}' compactada como '{zip_path}'.")
        logs.info(f"Pasta '{pasta_edital}' compactada como '{zip_path}'")
        return True
                
    except Exception as e:
        logs.error(f"Erro ao compactar arquivos, error: {str(e)}")
        return False

def obter_extensao_response(response, nome_limpo):
    try:
        # Lista de extensões conhecidas
        extensoes_validas = configuracoes.get("extensoes_validas")
        
        # 1.Verifica se nome do arquivo ja termina com extensão válida
        tem_extensao_valida = any(nome_limpo.lower().endswith(ext) for ext in extensoes_validas)
        if tem_extensao_valida:
            base, ext = os.path.splitext(nome_limpo)
            return base, ext.lower()
        
        # 2. Verifica se vem no Content-Disposition
        cd = response.headers.get("Content-Disposition")
        if cd:
            match = re.findall('filename="?([^"]+)"?', cd)
            if match:
                _, ext = os.path.splitext(match[0])
                if ext:
                    return None, ext.lower()

        # 3. Tenta adivinhar via mimetype
        content_type = response.headers.get("Content-Type")
        if content_type:
            ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if ext:
                return None, ext.lower()

        # 4. Usa .pdf como fallback
        return None, ".pdf"
    
    except Exception as e:
        logs.error("Erro ao obter_extensao_response arquivos - ", str(e))
        return None, ".pdf"

def comprimir_pdf(caminho_pdf):
    try:
        novo_pdf = f"{os.path.splitext(caminho_pdf)[0]}_comprimido.pdf"
        args = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={novo_pdf}",
            caminho_pdf
        ]
        ghostscript.Ghostscript(*args)
        print(f"PDF {caminho_pdf} comprimido e salvo como {novo_pdf}")
        logs.info(f"PDF comprimido: {caminho_pdf}")
        return novo_pdf      
    except Exception as e:  
        print(f"Erro ao comprimir {caminho_pdf} com Ghostscript: {e}")
        logs.error(f"Erro ao comprimir {caminho_pdf}: {str(e)}")
        return caminho_pdf

def mover_campactados(caminho_compactado, pasta_edital,nome_arquivo):
    # Mover o ZIP ou RAR original para a pasta 'compactados'   
    pasta_compactados = os.path.join(pasta_edital, 'compactados')
    if not os.path.exists(pasta_compactados):
        os.makedirs(pasta_compactados, exist_ok=True)   
    destino = os.path.join(pasta_compactados, nome_arquivo)
    shutil.move(caminho_compactado, destino)
    print(f"Arquivo compactado movido para: {destino}")
    logs.info(f"Arquivo compactado movido para: {destino}")

def mover_arquivos(caminho, pasta_edital):
     # Verifica se é um diretório
    if os.path.isdir(caminho):
        # Move todos os arquivos de dentro do diretório para a pasta raiz
        for raiz, _, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                origem = os.path.join(raiz, arquivo)
                destino = os.path.join(pasta_edital, arquivo)
                shutil.move(origem, destino)  # Move o arquivo para a raiz

        # Após mover, remove o diretório original vazio
        shutil.rmtree(caminho)
              
def processar_arquivos_compactados(caminho_compactado, pasta_edital, nome_arquivo, ext):
    try:
        if ext == '.zip':
            with zipfile.ZipFile(caminho_compactado, 'r') as zip_ref:
                zip_ref.extractall(pasta_edital)
                print(f"ZIP extraído para: {pasta_edital}")
                logs.info(f"ZIP extraído: {caminho_compactado}")
        elif ext == '.rar':
            try:
                unrar_path = configuracoes.get("UNRAR_TOOL")
                rarfile.UNRAR_TOOL = unrar_path
                with rarfile.RarFile(caminho_compactado, 'r') as rar_ref:
                        rar_ref.extractall(pasta_edital)
                        print(f"RAR extraído para: {pasta_edital}")
                        logs.info(f"RAR extraído: {caminho_compactado}")
            except rarfile.RarCannotExec as e:
                print("Erro: 'unrar.exe' não encontrado.")
                logs.error(f"Erro ao extrair RAR: {e}")
                return
        else:
            print("Formato não suportado.")
            logs.warning(f"Formato não suportado: {caminho_compactado}")
            return

        mover_campactados(caminho_compactado, pasta_edital, nome_arquivo)

         # Primeira iteração: mover os diretórios
        for item in list(os.listdir(pasta_edital)):
            caminho_item = os.path.join(pasta_edital, item)
            if os.path.isdir(caminho_item) and item != 'compactados':
                mover_arquivos(caminho_item, pasta_edital)

        # Segunda iteração: processar os arquivos agora que tudo está na raiz
        for item in os.listdir(pasta_edital):
            caminho_item = os.path.join(pasta_edital, item)
            ext = os.path.splitext(item)[1].lower()
            if item == 'compactados':
                continue
            executar_verificacao_arquivos(caminho_item, ext, pasta_edital, item)
            
    except zipfile.BadZipFile:
        print(f"Erro: {nome_arquivo} não é um ZIP válido.")
        logs.error(f"Erro ao extrair ZIP: {caminho_compactado}")
    except rarfile.Error as e:
        print(f"Erro ao extrair RAR: {e}")
        logs.error(f"Erro ao extrair RAR: {caminho_compactado}")
          
def executar_verificacao_arquivos(caminho_completo, ext, pasta_edital, nome_arquivo):
    try:
        extensoes_imgs = configuracoes.get("extensoes_imgs", [])
        extensoes_panilhas = configuracoes.get("extensoes_planilhas", [])
        formatos_para_docx = configuracoes.get("formatos_para_docx", [])
        if ext.lower() == ".zip" or ext.lower() == ".rar" :
            processar_arquivos_compactados(caminho_completo, pasta_edital, nome_arquivo, ext)
        elif ext.lower() == ".pdf":
            verificacao_comprimir_arquivo(caminho_completo)         
        elif ext.lower() in formatos_para_docx:
            converter_para_docx(caminho_completo)   
        elif ext.lower() in extensoes_imgs:
            converter_para_pdf(nome_arquivo, pasta_edital)
        elif ext.lower() in extensoes_panilhas:
            converter_para_xlsx(caminho_completo)
            
    except Exception as e:
        logs.error("Erro ao executar_verificacao_arquivos - ", str(e))

def converter_para_xlsx(arquivo_origem):
    nome_arquivo_sem_extensao, ext = os.path.splitext(arquivo_origem)
    novo_arquivo_xlsx = f"{nome_arquivo_sem_extensao}.xlsx"

    if ext == '.csv':
        try:
            df = pd.read_csv(arquivo_origem)
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Convertido para .xlsx: {arquivo_origem}")
            logs.info(f"Convertido para .xlsx: {arquivo_origem}")
        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Arquivo está vazio, mas foi convertido para .xlsx:{arquivo_origem}")
            logs.info(f"Arquivo está vazio, mas foi convertido para .xlsx:{arquivo_origem}")
        except Exception as e:
            print(f"Erro ao converter {arquivo_origem}: {e}")
    elif ext in ['.xlsm', '.ods']:
        try:
            df = pd.read_excel(arquivo_origem, engine='odf' if ext == '.ods' else None)
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Convertido para .xlsx:  {arquivo_origem}")
            logs.info(f"Convertido para .xlsx:  {arquivo_origem}")
        except Exception as e:
            df = pd.DataFrame()
            df.to_excel(novo_arquivo_xlsx, index=False)
            print(f"Arquivo está vazio ou ocorreu um erro, mas foi convertido para .xlsx:  {arquivo_origem} - error: {e}")
            logs.info(f"Arquivo está vazio ou ocorreu um erro, mas foi convertido para .xlsx:  {arquivo_origem} - error: {e}")
            
def converter_para_pdf(imagem, pasta_edital):
        try:
            img = Image.open(imagem).convert('RGB')
            nome_arquivo_sem_extensao = os.path.splitext(os.path.basename(imagem))[0]
            nome_arquivo_saida = os.path.join(pasta_edital, f"{nome_arquivo_sem_extensao}.pdf")
            img.save(nome_arquivo_saida)
            print(f"Convertido {imagem} para PDF em {nome_arquivo_saida}")
            logs.info(f"Convertido {imagem} para PDF em {nome_arquivo_saida}")
        except Exception as e:
            print(f"Erro ao converter {imagem} para PDF: {e}")
            logs.error(f"Erro ao converter {imagem} para PDF: {e}")

def verificacao_comprimir_arquivo(caminho_completo):
    limite_kb = configuracoes.get("limite_kb")
    tamanho_arquivo = os.path.getsize(caminho_completo)
    if tamanho_arquivo / 1024 > limite_kb:
        comprimido = comprimir_pdf(caminho_completo)
        tamanho_novo = os.path.getsize(comprimido)

        if tamanho_novo / 1024 > limite_kb:
            dividir_pdf_em_partes(comprimido, limite_kb)
            
def dividir_pdf_em_partes(caminho_pdf, limite_kb):
    try:
        reader = PdfReader(caminho_pdf)
        total_paginas = len(reader.pages)
        tamanho_total_kb = os.path.getsize(caminho_pdf) / 1024

        partes_necessarias = math.ceil(tamanho_total_kb / limite_kb)
        paginas_por_parte = total_paginas // partes_necessarias
        
        for i in range(partes_necessarias):
            writer = PdfWriter()
            
            inicio = i * paginas_por_parte
            fim = (i + 1) * paginas_por_parte if i < partes_necessarias - 1 else total_paginas

            for j in range(inicio, fim):
                writer.add_page(reader.pages[j])

            caminho_parte = caminho_pdf.replace('.pdf', f'_parte{i+1}.pdf')
            with open(caminho_parte, 'wb') as f:
                writer.write(f)

        # Exclui o arquivo original após a divisão
        os.remove(caminho_pdf)
        print(f"PDF {caminho_pdf} dividido em {partes_necessarias} parte(s) com sucesso.")
        
    except Exception as e:
        print(f"Erro ao dividr pdf {caminho_pdf} erro: {e}")
        logs.error(f"Erro ao dividr pdf {caminho_pdf} erro: {e}")
   
def converter_para_docx(arquivo_origem):
    nome_arquivo_sem_extensao, ext = os.path.splitext(arquivo_origem)
    novo_arquivo_docx = f"{nome_arquivo_sem_extensao}.docx"

    try:
        if ext.lower() == ".doc":
            # Usa LibreOffice para converter .doc em .docx
            subprocess.run([
                "soffice", "--headless", "--convert-to", "docx", arquivo_origem, "--outdir", os.path.dirname(arquivo_origem)
            ], check=True)
            print(f"Convertido {arquivo_origem} para {novo_arquivo_docx} usando LibreOffice")
            logs.info(f"Convertido {arquivo_origem} para {novo_arquivo_docx} usando LibreOffice")
        else:
            # Usa pypandoc para outros formatos válidos (ex: .md, .odt, .txt, etc)
            pypandoc.convert_file(arquivo_origem, 'docx', outputfile=novo_arquivo_docx)
            print(f"Convertido {arquivo_origem} para {novo_arquivo_docx} com Pandoc")
            logs.info(f"Convertido {arquivo_origem} para {novo_arquivo_docx} com Pandoc")
    except Exception as e:
        print(f"Erro ao converter {arquivo_origem} para DOCX: {e}")
        logs.error(f"Erro ao converter {arquivo_origem} para DOCX: {e}")
