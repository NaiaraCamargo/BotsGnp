import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


SRC_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = SRC_DIR.parent
DEFAULT_BACKUP_DIR = Path("C:/BOTGNP/bkp")


PLATAFORMAS = {
    "obra": "pncp_bot_obra",
    "materialescolar": "pncp_bot_material_escolar",
    "seguro": "pncp_bot_seguro",
    "mapfre": "mapfre_downloader",
}


ALIASES_PLATAFORMAS = {
    "obra": "obra",
    "materialescolar": "materialescolar",
    "seguro": "seguro",
}


@dataclass
class ResultadoBackup:
    plataforma: str
    status: str
    mensagem: str
    arquivo: Optional[str] = None


def normalizar_plataforma(nome):
    nome = str(nome or "").strip().lower()
    return ALIASES_PLATAFORMAS.get(nome, nome)


def carregar_config(plataforma):
    pacote = PLATAFORMAS[plataforma]
    caminho = SRC_DIR / pacote / "config.json"

    if not caminho.is_file():
        return caminho, None

    with caminho.open("r", encoding="utf-8") as arquivo:
        return caminho, json.load(arquivo)


def validar_conexao(plataforma, config):
    conexao = (config or {}).get("conexao_banco")
    if not isinstance(conexao, dict):
        return None, f"{plataforma}: config sem conexao_banco"

    obrigatorios = ["host", "port", "user", "password", "database"]
    faltando = [campo for campo in obrigatorios if conexao.get(campo) in (None, "")]
    if faltando:
        return None, f"{plataforma}: conexao_banco incompleta ({', '.join(faltando)})"

    return conexao, None


def pasta_backup_config(config):
    caminho = (config or {}).get("caminho_bkp") or DEFAULT_BACKUP_DIR
    return Path(caminho).expanduser().resolve()


def mysqldump_config(config, caminho_informado=None):
    return caminho_informado or (config or {}).get("mysqldump_path")


def backup_mais_recente(pasta_plataforma):
    if not pasta_plataforma.is_dir():
        return None

    arquivos = list(pasta_plataforma.glob("*_full.sql.gz"))
    if not arquivos:
        return None

    return max(arquivos, key=lambda arquivo: arquivo.stat().st_mtime)


def backup_dentro_do_prazo(pasta_plataforma, dias_intervalo):
    ultimo_backup = backup_mais_recente(pasta_plataforma)
    if not ultimo_backup:
        return False, None

    criado_em = datetime.fromtimestamp(ultimo_backup.stat().st_mtime)
    limite = datetime.now() - timedelta(days=dias_intervalo)
    return criado_em >= limite, ultimo_backup


def localizar_mysqldump(caminho_informado=None):
    if caminho_informado:
        caminho = Path(caminho_informado)
        if caminho.is_file():
            return str(caminho)
        raise FileNotFoundError(f"mysqldump nao encontrado em: {caminho}")

    encontrado = shutil.which("mysqldump")
    if encontrado:
        return encontrado

    candidatos = [
        Path("C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqldump.exe"),
        Path("C:/Program Files/MySQL/MySQL Server 5.7/bin/mysqldump.exe"),
        Path("C:/xampp/mysql/bin/mysqldump.exe"),
        Path("C:/wamp64/bin/mysql/mysql8.0.31/bin/mysqldump.exe"),
    ]

    for candidato in candidatos:
        if candidato.is_file():
            return str(candidato)

    raise FileNotFoundError(
        "mysqldump nao foi encontrado. Instale o MySQL Client ou informe --mysqldump."
    )


def escrever_defaults_temporario(conexao):
    conteudo = "\n".join(
        [
            "[client]",
            f"host={conexao['host']}",
            f"port={int(conexao['port'])}",
            f"user={conexao['user']}",
            f"password={conexao['password']}",
            "",
        ]
    )

    temporario = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".cnf",
        prefix="mysql-backup-",
        delete=False,
    )
    try:
        temporario.write(conteudo)
        return Path(temporario.name)
    finally:
        temporario.close()


def compactar_sql(origem_sql, destino_gz):
    with origem_sql.open("rb") as entrada:
        with gzip.open(destino_gz, "wb", compresslevel=6) as saida:
            shutil.copyfileobj(entrada, saida)


def gravar_manifesto(destino_gz, plataforma, conexao):
    manifesto = {
        "plataforma": plataforma,
        "database": conexao["database"],
        "host": conexao["host"],
        "port": int(conexao["port"]),
        "arquivo": destino_gz.name,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "tipo": "full",
    }
    caminho_manifesto = destino_gz.with_suffix(destino_gz.suffix + ".json")
    with caminho_manifesto.open("w", encoding="utf-8") as arquivo:
        json.dump(manifesto, arquivo, indent=4, ensure_ascii=False)


def executar_backup(plataforma, mysqldump=None, pasta_bkp=None, manter_sql=False):
    caminho_config, config = carregar_config(plataforma)
    if config is None:
        return ResultadoBackup(
            plataforma=plataforma,
            status="ignorado",
            mensagem=f"{plataforma}: config nao encontrado em {caminho_config}",
        )

    conexao, erro = validar_conexao(plataforma, config)
    if erro:
        return ResultadoBackup(plataforma=plataforma, status="ignorado", mensagem=erro)

    mysqldump = localizar_mysqldump(mysqldump_config(config, mysqldump))
    pasta_bkp = Path(pasta_bkp).resolve() if pasta_bkp else pasta_backup_config(config)
    pasta_plataforma = pasta_bkp / plataforma
    pasta_plataforma.mkdir(parents=True, exist_ok=True)

    agora = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_base = f"{plataforma}_{conexao['database']}_{agora}_full"
    destino_sql = pasta_plataforma / f"{nome_base}.sql"
    destino_gz = pasta_plataforma / f"{nome_base}.sql.gz"

    defaults = escrever_defaults_temporario(conexao)
    comando = [
        mysqldump,
        f"--defaults-extra-file={defaults}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--default-character-set=utf8mb4",
        f"--result-file={destino_sql}",
        "--databases",
        str(conexao["database"]),
    ]

    try:
        subprocess.run(comando, check=True, capture_output=True, text=True)
        compactar_sql(destino_sql, destino_gz)
        gravar_manifesto(destino_gz, plataforma, conexao)
    except subprocess.CalledProcessError as erro_execucao:
        stderr = (erro_execucao.stderr or "").strip()
        mensagem = stderr.splitlines()[-1] if stderr else str(erro_execucao)
        return ResultadoBackup(plataforma=plataforma, status="erro", mensagem=mensagem)
    finally:
        try:
            defaults.unlink(missing_ok=True)
        finally:
            if destino_sql.exists() and not manter_sql:
                destino_sql.unlink()

    tamanho_mb = destino_gz.stat().st_size / 1024 / 1024
    return ResultadoBackup(
        plataforma=plataforma,
        status="ok",
        mensagem=f"{plataforma}: backup full criado ({tamanho_mb:.2f} MB)",
        arquivo=str(destino_gz),
    )


def executar_backup_se_necessario(plataforma, dias_intervalo=2, mysqldump=None, pasta_bkp=None, manter_sql=False):
    caminho_config, config = carregar_config(plataforma)
    if config is None:
        return ResultadoBackup(
            plataforma=plataforma,
            status="ignorado",
            mensagem=f"{plataforma}: config nao encontrado em {caminho_config}",
        )

    pasta_bkp = Path(pasta_bkp).resolve() if pasta_bkp else pasta_backup_config(config)
    pasta_plataforma = pasta_bkp / plataforma
    dentro_do_prazo, ultimo_backup = backup_dentro_do_prazo(pasta_plataforma, dias_intervalo)

    if dentro_do_prazo:
        criado_em = datetime.fromtimestamp(ultimo_backup.stat().st_mtime)
        return ResultadoBackup(
            plataforma=plataforma,
            status="ignorado",
            mensagem=(
                f"{plataforma}: backup ainda dentro do prazo "
                f"({criado_em.strftime('%d/%m/%Y %H:%M')})"
            ),
            arquivo=str(ultimo_backup),
        )

    return executar_backup(
        plataforma=plataforma,
        mysqldump=mysqldump_config(config, mysqldump),
        pasta_bkp=pasta_bkp,
        manter_sql=manter_sql,
    )


def plataformas_para_backup(selecionadas):
    if not selecionadas:
        return list(PLATAFORMAS.keys())

    plataformas = []
    invalidas = []
    for nome in selecionadas:
        plataforma = normalizar_plataforma(nome)
        if plataforma in PLATAFORMAS:
            plataformas.append(plataforma)
        else:
            invalidas.append(nome)

    if invalidas:
        raise ValueError(
            "Plataforma invalida: "
            + ", ".join(invalidas)
            + ". Opcoes: "
            + ", ".join(PLATAFORMAS.keys())
        )

    return list(dict.fromkeys(plataformas))


def criar_parser():
    parser = argparse.ArgumentParser(
        description="Gera backup full dos bancos MySQL dos bots por plataforma."
    )
    parser.add_argument(
        "plataformas",
        nargs="*",
        help="Plataformas para backup: obra, materialescolar, seguro, mapfre. Sem valor faz todas.",
    )
    parser.add_argument(
        "--pasta",
        help="Pasta raiz dos backups. Se nao informar, usa caminho_bkp do config.json.",
    )
    parser.add_argument(
        "--mysqldump",
        help="Caminho do mysqldump.exe, se ele nao estiver no PATH.",
    )
    parser.add_argument(
        "--manter-sql",
        action="store_true",
        help="Mantem tambem o .sql sem compactar.",
    )
    parser.add_argument(
        "--dias-intervalo",
        type=int,
        default=0,
        help="Se maior que zero, so gera novo backup quando o ultimo tiver essa idade em dias.",
    )
    return parser


def main(argv=None):
    parser = criar_parser()
    args = parser.parse_args(argv)

    pasta_bkp = Path(args.pasta).resolve() if args.pasta else None
    plataformas = plataformas_para_backup(args.plataformas)
    if args.dias_intervalo > 0:
        resultados = [
            executar_backup_se_necessario(
                plataforma=plataforma,
                dias_intervalo=args.dias_intervalo,
                mysqldump=args.mysqldump,
                pasta_bkp=pasta_bkp,
                manter_sql=args.manter_sql,
            )
            for plataforma in plataformas
        ]
    else:
        resultados = [
            executar_backup(
                plataforma=plataforma,
                mysqldump=args.mysqldump,
                pasta_bkp=pasta_bkp,
                manter_sql=args.manter_sql,
            )
            for plataforma in plataformas
        ]

    houve_erro = False
    for resultado in resultados:
        print(f"[{resultado.status.upper()}] {resultado.mensagem}")
        if resultado.arquivo:
            print(f"       {resultado.arquivo}")
        houve_erro = houve_erro or resultado.status == "erro"

    return 1 if houve_erro else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        raise SystemExit(1)
