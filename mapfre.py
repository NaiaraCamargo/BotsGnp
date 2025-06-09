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
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from PyPDF2 import PdfReader, PdfWriter
from urllib.parse import urlparse, parse_qs

# Imports de módulos locais
from funcoespncp import *
from gerar_planilha import *
from repositoriopncp import *
from crowlerpncp import *

def inicializar_pagina_mafre(mostrar_browser = False):
    try:
        url_mafre_login = "https://negociospublicos.mapfre.com.br/Default.aspx"
        driver, profile_dir = criar_driver(mostrar_browser)
        driver.get(url_mafre_login)
        controles_iniciais(driver)
    except Exception as ex:
        logs.error("inicializar_pagina_mafre- ", str(ex))
    finally:
        if driver:
            encerrar_driver_com_timeout(driver) 
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
    
     


