# Imports da biblioteca padrão
import math
import os
import re
import string
import time
import copy
import queue
import shutil
import locale
import zipfile
import threading
import tempfile
import traceback
import mimetypes
import sqlite3
from pathlib import Path
from itertools import islice
from datetime import datetime
from os.path import isfile
import rarfile
import subprocess
import unicodedata
# Imports de bibliotecas externas
import requests
import ghostscript
import pypandoc
from PIL import Image
from unidecode import unidecode
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from PyPDF2 import PdfReader, PdfWriter
from urllib.parse import urlparse, parse_qs

# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from repositoriopncp import *
from drivers import *

def inicializar_pagina_mafre(edital, mostrar_browser = False):
    try:
        print(f"\nExecutando Processo na Mafre pro edital: {edital["Link"]}\n") 
       
        url_login = configuracoes.get("mafre", {}).get("url_login")
        driver_mafre, profile_dir = criar_driver(mostrar_browser)
        driver_mafre.get(url_login)
        
        processar_login_mafre(driver_mafre, edital)
  
    except Exception as ex:
        logs.error("inicializar_pagina_mafre - ", str(ex))
    finally:
        if driver_mafre:
            encerrar_driver_com_timeout(driver_mafre) 
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
    
   
def processar_login_mafre(driver_mafre, edital):
    try:
        user = configuracoes.get("mafre", {}).get("user_mafre")
        password = configuracoes.get("mafre", {}).get("password_mafre")
        
        controles_iniciais(driver_mafre)
        
        login_elemento = driver_mafre.find_elements(By.XPATH, "/html/body/form/div[3]/div/div/div[2]")
        
        usuario = login_elemento[0].find_element(By.XPATH, ".//table/tbody/tr[1]/td[2]/input")  
        senha = login_elemento[0].find_element(By.XPATH, ".//table/tbody/tr[2]/td[2]/input")  

        usuario.send_keys(user)
        senha.send_keys(password)

        botao_login = login_elemento[0].find_element(By.ID, "btnLogin")
        botao_login.click()
        
        try:
            elemento_pos_login = WebDriverWait(driver_mafre, 40).until(
                EC.presence_of_element_located((By.ID, "btnConfirmaTermos"))
            )
            
            print("✅ Login bem-sucedido")
            processar_pos_login(driver_mafre, edital)
           
        except:
            print("❌ Falha no login")

    except Exception as ex:
        logs.error("processar_login_mafre - ", str(ex))
        
def processar_pos_login(driver_mafre, edital):
    try:
        url_pos_login = configuracoes.get("mafre", {}).get("url_pos_login")
        
        driver_mafre.get(url_pos_login)
        
        elemento_consulta = driver_mafre.find_elements(By.ID, "UpdatePanel")
        
        filtro_pesquisa = elemento_consulta[0].find_element(By.ID, "cmbFilter")
        select_filtro = Select(filtro_pesquisa)
        select_filtro.select_by_value("cpf_cnpj")
        
        texto_pesquisa = elemento_consulta[0].find_element(By.ID, "txtFilter")
        cnpj_pesquisa = cnpj(edital.get("Cnpj", ""))
        texto_pesquisa.send_keys(cnpj_pesquisa)
        
        botao_filter = elemento_consulta[0].find_element(By.ID, "btnFilter")
        botao_filter.click()
        
        try:
            elemento_pos_filtro = WebDriverWait(driver_mafre, 40).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/form/div[3]/div/table/tbody/tr[4]/td/div/table/tbody/tr[2]"))
            )
            
            botao_reserva = driver_mafre.find_element(By.ID, "btnLicitacao")
            botao_reserva.click()
        
            elemento_reserva = WebDriverWait(driver_mafre, 40).until(
                EC.presence_of_element_located((By.ID, "btnNew"))
            )
            
            elemento_reserva.click()
            
            preencher_form_licitacao(driver_mafre, edital)
               
        except:
            print(f"❌ NÃO HÁ REGISTRO PARA ESSE CNPJ: {edital["Cnpj"]}")
            
    except Exception as ex:
        logs.error("processar_pos_login - ", str(ex))
        
def preencher_form_licitacao(driver_mafre, edital):
    try:
        msg = ""
        link =[]
        elementos_form = driver_mafre.find_elements(By.ID, "uptPnlForm")
        
        ramo = elementos_form[0].find_element(By.ID, "idramo")
        select_ramo = Select(ramo)
        ramos_valores = detectar_ramos(edital.get("Objeto", ""))
        
        if not ramos_valores:
            logs.warning("Nenhum ramo identificado no objeto: '%s' | Link: %s", edital.get("objeto", ""), edital.get("Link", ""))
            msg = "Edital nao Cadastrado (Ramo nao detectado)"
            return msg , link
        
        for ramo in ramos_valores:
            select_ramo.select_by_value(ramo)
            
            solicitante = elementos_form[0].find_element(By.ID, "idsolicitante_txtDescript")
            solicitante.send_keys("R.B.GNP")
            
            prestador = elementos_form[0].find_element(By.ID, "idcorretor_txtDescript")
            prestador.send_keys("GNP CORRETORA DE SEGUROS")
            
            territorial = elementos_form[0].find_element(By.ID, "idterritorial_txtDescript")
            territorial.send_keys("RIO GRANDE DO SUL")
            
            modalidade = elementos_form[0].find_element(By.ID, "modalidade")
            select_modalidade = Select(modalidade)
            licitacao = edital.get("Licitacao", "")
            licitacao = licitacao.replace("-", "").strip()
            select_modalidade.select_by_value("licitacao")
            
            data_abertura = elementos_form[0].find_element(By.ID, "dataabertura")
            data_fim = edital.get("DataFim", "")
            data_abertura.send_keys(data_fim)
             
            numero_edital = elementos_form[0].find_element(By.ID, "edital")
            numero = edital.get("Numero", "")
            numero_edital.send_keys(numero)
            
            botao_gravar = elementos_form[0].find_element(By.ID, "btnUpdate")
            botao_gravar.click()
            id_licitacao = elementos_form[0].find_element(By.ID, "idlicitacao").get_attribute("value")
            
            url_antes = driver_mafre.current_url

            botao_anexar_arquivos = elementos_form[0].find.element(By.ID, "btnArquivoDigital")
            botao_anexar_arquivos.click()
            
            WebDriverWait(driver_mafre, 10).until(EC.url_changes(url_antes))
            link.append(url_arquivos = driver_mafre.current_url)
           
            msg =+ anexar_arquivos_mafre(driver_mafre, edital)            
        
        msg = "Edital castrado para o(s) ramo(s): {ramos_valores}"
        
        return msg, link
 
    except Exception as ex:
        logs.error("preencher_form_licitacao - ", str(ex))

def anexar_arquivos_mafre(drive_mafre, edital):
    try:
        msg = ""
        caminho_arquivos = edital.get("pasta_download", "")
        palavras_arquivos_exececoes = configuracoes.get("mafre", {}).get("palavras_arquivos_exececoes")
        if not caminho_arquivos:
            logs.warning(f"Caminho dos arquivos em branco para o edital: {edital["Link"]}\n")
            msg = f"Caminho dos arquivos em branco para o edital: {edital.get('Link', '')}"
            return msg
        
        quantidade_arquivos = len([
            f for f in os.listdir(caminho_arquivos)
            if os.path.isfile(os.path.join(caminho_arquivos, f))
        ])

        if quantidade_arquivos == 0:
            logs.warning(f"Diretório sem arquivos: {caminho_arquivos} - Link: {edital.get('Link', '')}")
            msg = f"Nenhum arquivo encontrado em: {caminho_arquivos} - Edital: {edital.get('Link', '')}"
            return msg
        
        elemento_inserir_arquivos = drive_mafre.find_elements(By.ID, "uptPnlForm")
        botao_escolher_arquivos = elemento_inserir_arquivos[0].find_element(By.ID, "fUpload")
        
        if quantidade_arquivos > 1:
            for item in os.listdir(caminho_arquivos):
                caminho_item = os.path.join(caminho_arquivos, item)
                if os.path.isfile(caminho_item) and "edital" in item.lower():
                    botao_escolher_arquivos.send_keys(caminho_item)
                    break  
                elif os.path.isfile(caminho_item) and palavras_arquivos_exececoes not in item.lower():
                    botao_escolher_arquivos.send_keys(caminho_item)
                    break  
        else:
            arquivos = [f for f in os.listdir(caminho_arquivos) if os.path.isfile(os.path.join(caminho_arquivos, f))]
            if arquivos:
                caminho_item = os.path.join(caminho_arquivos, arquivos[0])
                botao_escolher_arquivos.send_keys(caminho_item)
            
           
    except Exception as ex:
        logs.error("anexar_arquivos_mafre - ", str(ex))

def detectar_ramos(objeto_texto):
    texto = objeto_texto.upper()
    encontrados = set()
    
    for value, palavras in RAMOS.items():
        for palavra in palavras:
            if palavra.upper() in texto:
                encontrados.add(value)
                break  # Evita repetir o mesmo ramo por várias palavras

RAMOS = {
    # AERONÁUTICO
    "5": ["AERONÁUTICO", "DRONE"],
    # AERONÁUTICO CASCO
    "24": ["CASCO", "AERONÁUTICO CASCO", "DRONE e CASCO"],
    # AERONÁUTICO RETA
    "23": ["RETA", "R.E.T.A", "AERONÁUTICO e R.E.T.A", "DRONE e R.E.T.A"],
    # AUTOMÓVEIS
    "1": ["FROTA", "CARRO", "VEÍCULO", "VEICULAR", "AUTOMOTIVO", "AUTOMÓVEL", "AUTOMÓVEIS","AMBULÂNCIA", 
          "SAMU", "ÔNIBUS", "VANS", "CAMINHÃO", "VIATURA","COMPREENSIVA", "COMPREENSIVO", " RCF", " RCO", "MAQUINA"],
    # CASCO MARÍTIMO-EMBARCAÇÃO
    "20": ["MARÍTIMO", "BARCO", "EMBARCAÇÃO"],
    # DIFERENCIADOS (> 15 MI)
    "2": ["PRÉDIOS", "PREDIAL", "PATRIMONIAL", "PATRIMÔNIO", "PATRIMONIAIS", "EMPRESARIAL","IMÓVEL", "IMÓVEIS","EDIFÍCIO",
          "IMOBILIÁRIO", "LOCAL", "LOCAIS"],
    # MÁQUINAS E EQUIPAMENTOS
    "25": ["MAQUINA", "EQUIPAMENTO", "EQUIPAMENTOS", "TRATOR", "ESCAVADEIRA","ROLO COMPACTADOR", "RETROESCAVADEIRA", "PATROLA"],
    # MASSIFICADOS (< 15 MI)
    "3": ["PRÉDIOS", "PREDIAL", "PATRIMONIAL", "PATRIMÔNIO", "PATRIMONIAIS", "EMPRESARIAL","IMÓVEL", "IMÓVEIS", "EDIFÍCIO",
          "IMOBILIÁRIO", "LOCAL", "LOCAIS" ],
    # RESPONSABILIDADE CIVIL
    "9": ["RESPONSABILIDADE CIVIL"],
    # VIDA
    "6": ["VIDA", "PESSOAIS", "COLETIVO", "ACIDENTES", "ESTAGIÁRIOS", "ESTÁGIO","ESTUDANTES", "ALUNO", "FUNERAL"],
}
