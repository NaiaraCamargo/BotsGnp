# Bots GNP

Bots em Python para consultar e processar editais do PNCP, baixar arquivos da Mapfre e gerar planilhas.

## Requisitos

- Windows 64 bits;
- Python 3;
- MySQL Server;
- Chrome instalado ou Chrome portátil;
- ChromeDriver compatível com a versão do Chrome;
- Ghostscript;
- Pandoc;
- UnRAR;
- wkhtmltopdf/wkhtmltoimage.

## Instalação

Execute na raiz do projeto:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

## Configuração

Cada bot utiliza um `config.json` com conexão do MySQL, caminhos, tokens e demais configurações.

Em desenvolvimento, os arquivos ficam em:

```text
src/pncp_bot_obra/config.json
src/pncp_bot_material_escolar/config.json
src/pncp_bot_seguro/config.json
src/mapfre_downloader/config.json
```

Quando compilado, coloque o `config.json` na mesma pasta do `.exe`.

Exemplo dos principais campos:

```json
{
  "conexao_banco": {
    "host": "localhost",
    "port": 3306,
    "user": "USUARIO",
    "password": "SENHA",
    "database": "BANCO"
  },
  "mysqldump_path": "C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqldump.exe",
  "UNRAR_TOOL": "C:/FERRAMENTAS/UnRAR/UnRAR.exe",
  "path_wkhtmltoimage": "C:/Program Files/wkhtmltopdf/bin/wkhtmltoimage.exe",
  "pasta_downloads": "C:/BOTGNP/downloads"
}
```

## Chrome portátil

O Chrome portátil não é incluído nos executáveis. A estrutura recomendada é compartilhar uma pasta entre os bots:

```text
CLIENTE/
├── pncp_shared/
│   └── resources/
│       └── browser/
│           ├── chrome-win64/
│           │   └── chrome.exe
│           └── chromedriver-win64/
│               └── chromedriver.exe
├── obra/
│   ├── bot_pncp_obra.exe
│   └── config.json
├── material_escolar/
│   ├── bot_pncp_material_escolar.exe
│   └── config.json
├── seguro/
│   ├── bot_pncp_seguro.exe
│   └── config.json
├── mapfre/
│   ├── bot_mapfre.exe
│   └── config.json
└── planilha/
    ├── gerar_planilha.exe
    └── config.json
```

Também é possível colocar `pncp_shared/resources/browser` dentro da pasta de cada executável.

Em desenvolvimento, use:

```text
src/pncp_shared/resources/browser/
├── chrome-win64/chrome.exe
└── chromedriver-win64/chromedriver.exe
```

Se o Chrome portátil não for encontrado, o bot tenta usar o Chrome instalado no Windows.

## Gerar os executáveis

Ative o ambiente virtual e execute os comandos na raiz do projeto. Os arquivos serão gerados em `dist/`.

### PNCP Obras

```powershell
py -m PyInstaller src/pncp_bot_obra/bots/bot_pncp_obra.py --onefile --paths src --hidden-import selenium.webdriver.chrome.webdriver --hidden-import selenium.webdriver.chrome.service --hidden-import selenium.webdriver.chrome.options --hidden-import pncp_shared.database.backup_bancos --add-data "src/pncp_shared/metadata/metadados.db;pncp_shared/metadata"
```

### PNCP Material Escolar

```powershell
py -m PyInstaller src/pncp_bot_material_escolar/bots/bot_pncp_material_escolar.py --onefile --paths src --hidden-import selenium.webdriver.chrome.webdriver --hidden-import selenium.webdriver.chrome.service --hidden-import selenium.webdriver.chrome.options --hidden-import pncp_shared.database.backup_bancos --add-data "src/pncp_shared/metadata/metadados.db;pncp_shared/metadata"
```

### PNCP Seguro

```powershell
py -m PyInstaller src/pncp_bot_seguro/bots/bot_pncp_seguro.py --onefile --paths src --hidden-import selenium.webdriver.chrome.webdriver --hidden-import selenium.webdriver.chrome.service --hidden-import selenium.webdriver.chrome.options --hidden-import pncp_shared.database.backup_bancos --add-data "src/pncp_shared/metadata/metadados.db;pncp_shared/metadata"
```

### Mapfre

```powershell
py -m PyInstaller src/mapfre_downloader/bots/bot_mapfre.py --onefile --paths src --hidden-import selenium.webdriver.chrome.webdriver --hidden-import selenium.webdriver.chrome.service --hidden-import selenium.webdriver.chrome.options
```

### Gerador de planilha

```powershell
py -m PyInstaller src/pncp_planilha_desktop/gerar_planilha.py --onefile --noconsole --paths src --add-data "src/pncp_planilha_desktop/gerar_planilha.html;pncp_planilha_desktop" --add-data "src/pncp_bot_obra/config.json;pncp_bot_obra" --add-data "src/pncp_shared/metadata/metadados.db;pncp_shared/metadata"
```

Esse comando gera `dist/gerar_planilha.exe` e incorpora a interface `gerar_planilha.html`.

Mesmo com o `config.json` incluído no comando, o código atual procura a configuração ao lado do executável quando está compilado. Portanto, copie para a pasta do `gerar_planilha.exe` o `config.json` correspondente ao banco que será consultado.

## Programas externos

Na máquina que executará os bots:

1. instale Ghostscript e Pandoc;
2. instale wkhtmltopdf e configure o caminho de `wkhtmltoimage.exe`;
3. copie ou instale UnRAR e configure o caminho de `UnRAR.exe`;
4. instale MySQL e configure o caminho de `mysqldump.exe`;
5. confirme que as pastas de downloads e backups existem.

## Entrega

Para instalar em outra máquina, copie:

- o `.exe` desejado;
- o `config.json` ao lado do `.exe`;
- a estrutura do Chrome portátil, se não utilizar o Chrome instalado;
- os programas externos necessários.

Na primeira execução, abra o bot pelo terminal para visualizar possíveis erros de configuração.
