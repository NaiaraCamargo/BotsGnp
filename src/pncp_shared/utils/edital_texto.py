import re
from decimal import Decimal, InvalidOperation

from unidecode import unidecode
from pncp_shared.utils.funcoespncp import limpar_para_mysql, formatar_valor_sigilo, formatar_data_hora_string, separar_data_hora, destacar_palavras


ROTULOS = {
    'ultima atualizacao', 'data de divulgacao no pncp', 'id contratacao pncp', 'situacao', 'modalidade de contratacao',
    'amparo legal', 'modo de disputa', 'srp', 'fonte orcamentaria', 'orgao', 'unidade', 'localidade da unidade',
    'orgao/entidade sub-rogado', 'unidade sub-rogada', 'localidade da unidade sub-rogada',
    'data de inicio de recebimento de propostas', 'data de fim de recebimento de propostas', 'fonte/plataforma',
    'objeto', 'valor total estimado/avaliado', 'valor total estimado', 'valor total homologado',
    'informacao complementar', 'informacoes complementares', 'tipo', 'data de publicacao no pncp',
}

class TextoEditalIncompleto(ValueError):
    pass

def normalizar_rotulo(valor):
    return re.sub(r'\s+', ' ', unidecode(valor).lower()).strip().rstrip(':').strip()

def extrair_campos_rotulados(texto):
    """Reconhece rotulos completos e preserva valores multilinha e dois-pontos no objeto."""
    campos, atual = {}, None
    for linha in str(texto or '').replace('\r\n', '\n').splitlines():
        linha = linha.strip()
        if not linha:
            continue
        rotulo, separador, valor = linha.partition(':')
        chave = normalizar_rotulo(rotulo)
        if chave == 'modalidade da contratacao':
            chave = 'modalidade de contratacao'
        if separador and chave in ROTULOS:
            atual = chave
            campos[atual] = valor.strip()
        elif atual:
            campos[atual] = '\n'.join(filter(None, (campos[atual], linha)))
    return campos

def normalizar_valor_monetario(valor):
    texto = str(valor if valor is not None else '').strip()
    if normalizar_rotulo(texto) in {'', 'nao informado', 'nao informada', 'nao se aplica', '-'}:
        return None
    if normalizar_rotulo(texto) in {'sigiloso', 'valor sigiloso'}:
        return 'SIGILOSO'
    numero = re.sub(r'\s+', '', texto.removeprefix('R$')).replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', numero):
        raise TextoEditalIncompleto(f'Valor monetario invalido: {texto!r}')
    try:
        valor_decimal = Decimal(numero)
    except InvalidOperation as exc:
        raise TextoEditalIncompleto(f'Valor monetario invalido: {texto!r}') from exc
    return formatar_valor_sigilo(valor_decimal)

def extrair_dados_edital(texto, link=None, palavras_destacadas=None, incluir_homologado=False):
    """Retorna o edital com nomes e formatos finais, pronto para receber itens e complementos."""
    campos = extrair_campos_rotulados(texto)
    obrigatorios = ('id contratacao pncp', 'localidade da unidade', 'modalidade de contratacao', 'orgao', 'objeto', 'situacao')
    ausentes = [campo for campo in obrigatorios if not campos.get(campo)]
    if ausentes:
        raise TextoEditalIncompleto(f'Campos obrigatorios ausentes: {", ".join(ausentes)}')
    identificador = re.fullmatch(r'(\d{14})-\d+-(\d+)/(\d{4})', campos['id contratacao pncp'])
    titulo = re.search(r'(?im)^[^\n:]*?\bn[º°o.]\.?\s*([^\n:]+?)/(\d{4})\s*$', texto)
    if not identificador or not titulo:
        raise TextoEditalIncompleto('Identificador PNCP ou numero do edital invalido.')
    cnpj, sequencial, ano = identificador.groups()
    link_edital = f'https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(sequencial)}'
    if link and link.rstrip('/') != link_edital:
        raise TextoEditalIncompleto(f'Link divergente do identificador PNCP: {link}')
    localidade = re.fullmatch(r'(.+)/([A-Za-z]{2})', campos['localidade da unidade'].strip())
    if not localidade:
        raise TextoEditalIncompleto('Localidade da unidade invalida.')
    municipio, uf = localidade.groups()
    fim = formatar_data_hora_string(campos.get('data de fim de recebimento de propostas'), incluir_segundos=False)
    data_fim, hora_fim = separar_data_hora(fim)
    valor = campos.get('valor total estimado/avaliado', campos.get('valor total estimado'))
    numero = titulo[1].strip()
    
    edital = {
        'Link': link_edital, 
        'Numero': f'{numero}/{titulo.group(2)}',
        'NumeroAux': numero, 
        'IdContratacaoPncp': campos['id contratacao pncp'], #'18140756000100-1-000289/2026'
        'Licitacao': campos['modalidade de contratacao'], #'Pregão - Eletrônico'
        'Data': formatar_data_hora_string(campos.get('data de divulgacao no pncp', campos.get('data de publicacao no pncp')), incluir_segundos=False),
        'Orgao': re.sub(r'^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\s*-\s*', '', campos['orgao']), # 'MUNICIPIO DE ARAXA'
        'Municipio': f'{municipio.strip()}/{uf.upper()}', #'Araxá/MG'
        'Uf': uf.upper(), #MG
        'Cnpj': cnpj, #'18140756000100'
        'Descricao': destacar_palavras(limpar_para_mysql(campos['objeto']), palavras_destacadas),
        #[Publicenter] - CONCESSÃO ONEROSA DO ESPAÇO FÍSICO PARA CAFETERIA/LANCHONETE NO PARQUE DO CRISTO DO MUNICÍPIO DE ARAXÁ/MG', 
        'DataInicioRecebimentoProposta': formatar_data_hora_string(campos.get('data de inicio de recebimento de propostas'), incluir_segundos=False),
        'DataFimRecebimentoProposta': fim, #'2026-11-18T13:05:00', 
        'DataFim': data_fim or None, #2026-11-18
        'HoraFim': hora_fim, #13:05
        'CodigoUnidadeCompradora': campos.get('unidade', '').split(' - ', 1)[0].strip(), #'23301'
        'ModoDeDisputa': campos.get('modo de disputa'),  # 'Aberto', 
        'Situacao': campos['situacao'], #'Divulgada no PNCP', 
        'ValorTotalEstimadoCompra': normalizar_valor_monetario(valor) or formatar_valor_sigilo(None), #16800.0,
        'FontesOrcamentarias': campos.get('fonte orcamentaria', ''), 
        'fonte_plataforma': campos.get('fonte/plataforma', ''),
    }
    
    if incluir_homologado:
        edital['ValorTotalHomologado'] = normalizar_valor_monetario(campos.get('valor total homologado'))
        
    return edital

