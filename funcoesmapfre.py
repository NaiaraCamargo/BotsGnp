from datetime import datetime
import re
import string
from funcoespncp import *
import unicodedata


# Função para limpar HTML e pontuação, deixar maiúsculo
def limpar_texto(texto):
    texto = re.sub(r'<.*?>', ' ', texto)          # remove tags HTML
    texto = texto.translate(str.maketrans('', '', string.punctuation))  # remove pontuação
    texto = remover_acentos(texto)                # remove acentos
    return texto.upper()     

def detectar_ramos(objeto_texto):
    try:
        texto = limpar_texto(objeto_texto)
        encontrados = set()
        
        for value, palavras in RAMOS.items():
            for palavra in palavras:
                palavra_normalizada = remover_acentos(palavra.upper())
                
                if value in RAMOS_COM_SEGURO:
                    # aceita "SEGURO VIDA", "SEGURO DE VIDA", "SEGURO PARA OS IMOVEIS" etc.
                    pattern = r'\bSEGUR\w*(?:\s+\w+){{0,3}}\s+{}(?:\s+\w+)*'.format(
                        re.escape(palavra_normalizada)
                    )              
                else:
                    # regra normal
                    pattern = r"\b{}\b".format(re.escape(palavra_normalizada))        
                
                if re.search(pattern, texto):
                    encontrados.add(value)
                    break  # evita duplicidade do mesmo ramo

        # regra especial do ramo 1 x 24
        if "1" in encontrados and "24" in encontrados:
            if not re.search(r"\bAERONAUTICO CASCO\b", texto) and not re.search(r"\bDRONE E CASCO\b", texto):
                encontrados.discard("24")
                    
        return encontrados

    except Exception as ex:
            logs.error("detectar_ramos - Erro: %s", str(ex))
            return ""  

def validar_criar_reserva(edital):
    try:
        data_fim = edital.get("DataFim", "")
        data_fim_dt = datetime.strptime(data_fim, "%d/%m/%Y")
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ramos_valores = detectar_ramos(edital.get("Descricao", ""))
        licitacao = edital.get("Licitacao", "").upper()
        
        if data_fim_dt < hoje:
            logs.warning("Data Abertura é menor que dia atual: '%s' | Link: %s", data_fim, edital.get("Link", ""))
            return False, f"Data Abertura é menor que dia atual;", []
        elif not any(modal in licitacao for modal in ["DISPENSA", "PREGÃO - ELETRÔNICO", "PREGÃO - PRESENCIAL"]):
            logs.warning("Modalidade não é valida para reserva : '%s' | Link: %s", licitacao, edital.get("Link", ""))
            return False, f"Modalidade não é valida para reserva;", []
        elif not ramos_valores:
            logs.warning("Nenhum ramo identificado no objeto: '%s' | Link: %s", edital.get("objeto", ""), edital.get("Link", ""))
            return False, f"Nenhum ramo identificado no objeto deste edital;", []
        elif '6' in ramos_valores:
            valor_estimado_str = edital.get("ValorTotalEstimadoCompra", "")
            valor_estimado = limpar_valor(valor_estimado_str)
            qtde_itens = int(edital.get("QuantidadeItens", 0))
            valido = False
            if valor_estimado == "SIGILOSO" and qtde_itens > 100:
                valido = True
            elif isinstance(valor_estimado, (int, float)) and valor_estimado >= 3600:
                valido = True

            if not valido:
                if set(ramos_valores) == {'6'}:
                    return False, "Ramo VIDA não atende aos critérios e é o único ramo;", []
                else:
                    ramos_valores = [r for r in ramos_valores if r != '6']
       
        return True, "", ramos_valores   
 
    except Exception as ex:
        logs.error("validar_criar_reserva - Erro: %s", str(ex))
        return "Erro ao validar reserva se atende requisitos, caiu no except;"  

RAMOS = {
    # AUTOMÓVEIS
    "1": [
        "FROTA", "FROTAS",
        "CARRO", "CARROS",
        "VEICULO", "VEICULOS", "VEICULAR",
        "AUTOMOTIVO", "AUTOMOTIVOS",
        "AUTOMOVEL", "AUTOMOVEIS",
        "AMBULANCIA", "AMBULANCIAS",
        "SAMU",
        "ÔNIBUS", "ÔNIBUS",   # mesmo no plural
        "VAN", "VANS",
        "CAMINHÃO", "CAMINHÕES",
        "VIATURA", "VIATURAS",
        "COMPREENSIVA", "COMPREENSIVO", "COMPREENSIVAS", "COMPREENSIVOS",
        "RCF", "RCO",
        "MAQUINA", "MAQUINAS",
        "MÁQUINA", "MÁQUINAS"
    ],
    
    # DIFERENCIADOS (> 30 MI)
    "2": [
        "PRÉDIO", "PRÉDIOS",
        "PREDIAL", "PREDIAIS",
        "PATRIMONIAL", "PATRIMONIAIS",
        "PATRIMÔNIO", "PATRIMÔNIOS",
        "EMPRESARIAL", "EMPRESARIAIS",
        "IMÓVEL", "IMÓVEIS",
        "EDIFÍCIO", "EDIFÍCIOS",
        "IMOBILIÁRIO", "IMOBILIÁRIOS",
        "LOCAL", "LOCAIS"
    ],
     # MASSIFICADOS (< 30 MI)
    "3": [
        "PRÉDIO", "PRÉDIOS",
        "PREDIAL", "PREDIAIS",
        "PATRIMONIAL", "PATRIMONIAIS",
        "PATRIMÔNIO", "PATRIMÔNIOS",
        "EMPRESARIAL", "EMPRESARIAIS",
        "IMÓVEL", "IMÓVEIS",
        "EDIFÍCIO", "EDIFÍCIOS",
        "IMOBILIÁRIO", "IMOBILIÁRIOS",
        "LOCAL", "LOCAIS"
    ],
     # AERONÁUTICO
    "5": [
        "AERONÁUTICO", "AERONÁUTICOS",
        "DRONE", "DRONES",
        "AERONAVE", "AERONAVES"
    ],
    # VIDA
    "6": [
        "VIDA", "VIDAS",
        "PESSOAL", "PESSOAIS",
        "COLETIVO", "COLETIVOS",
        "ACIDENTE", "ACIDENTES",
        "ESTAGIÁRIO", "ESTAGIÁRIOS",
        "ESTÁGIO", "ESTÁGIOS",
        "ESTUDANTE", "ESTUDANTES",
        "ALUNO", "ALUNOS",
        "FUNERAL", "FUNERAIS"
    ],
   # RESPONSABILIDADE CIVIL
    "9": [
        "RESPONSABILIDADE CIVIL", "RESPONSABILIDADES CIVIS"
    ],
    # CASCO MARÍTIMO-EMBARCAÇÃO
    "20": [
        "MARÍTIMO", "MARÍTIMOS",
        "BARCO", "BARCOS",
        "EMBARCAÇÃO", "EMBARCAÇÕES"
    ],
    # AERONÁUTICO RETA
    "23": [
        "RETA", "RETAS",
        "R.E.T.A", "R.E.T.AS",
        "AERONÁUTICO E R.E.T.A", "AERONÁUTICOS E R.E.T.AS",
        "DRONE E R.E.T.A", "DRONES E R.E.T.AS"
    ],    
    # AERONÁUTICO CASCO
    "24": [
        "CASCO", "CASCOS",
        "AERONÁUTICO CASCO", "AERONÁUTICOS CASCOS",
        "DRONE E CASCO", "DRONES E CASCOS"
    ],
    # MÁQUINAS E EQUIPAMENTOS
    "25": [
        "MAQUINA", "MAQUINAS",
        "MÁQUINA", "MÁQUINAS",
        "EQUIPAMENTO", "EQUIPAMENTOS",
        "TRATOR", "TRATORES",
        "ESCAVADEIRA", "ESCAVADEIRAS",
        "ROLO COMPACTADOR", "ROLOS COMPACTADORES",
        "RETROESCAVADEIRA", "RETROESCAVADEIRAS",
        "PATROLA", "PATROLAS"
    ], 
    # D&O
    "27": ["D&O"]
}

CAPITAIS = [
    "RIO BRANCO", "MACAPA", "MANAUS", "BELEM", "PORTO VELHO", "BOA VISTA", "PALMAS",
    "MACEIO", "SALVADOR", "FORTALEZA", "SAO LUIS", "JOAO PESSOA", "RECIFE", "TERESINA",
    "NATAL", "ARACAJU", "BRASILIA", "GOIANIA", "CUIABA", "CAMPO GRANDE", "VITORIA",
    "BELO HORIZONTE", "RIO DE JANEIRO", "SAO PAULO", "CURITIBA", "FLORIANOPOLIS", "PORTO ALEGRE"
]

# Mapeamento centralizado de UF para Territorial
mapeamento_territorial = {
    "DF": "CENTRO OESTE",
    "GO": "CENTRO OESTE",
    "MT": "CENTRO OESTE",
    "MS": "CENTRO OESTE",
    "MG": "MINAS GERAIS",
    "AC": "NORTE E NORDESTE",
    "AL": "NORTE E NORDESTE",
    "AP": "NORTE E NORDESTE",
    "AM": "NORTE E NORDESTE",
    "BA": "NORTE E NORDESTE",
    "CE": "NORTE E NORDESTE",
    "MA": "NORTE E NORDESTE",
    "PA": "NORTE E NORDESTE",
    "PB": "NORTE E NORDESTE",
    "PE": "NORTE E NORDESTE",
    "PI": "NORTE E NORDESTE",
    "RN": "NORTE E NORDESTE",
    "RO": "NORTE E NORDESTE",
    "RR": "NORTE E NORDESTE",
    "SE": "NORTE E NORDESTE",
    "TO": "NORTE E NORDESTE",
    "PR": "PARANA",
    "ES": "RIO DE JANEIRO",
    "RJ": "RIO DE JANEIRO",
    "RS": "RIO GRANDE DO SUL",
    "SC": "RIO GRANDE DO SUL",
    "SP": "SÃO PAULO CAPITAL",
}

# ramos que exigem "seguro de", "seguro para" ou "seguro X"
RAMOS_COM_SEGURO = {"2", "3", "6", "9", "23", "25"}

# Cria um dicionário com os nomes principais por código
NOMES_RAMO = {
    "1": "AUTOMÓVEIS",
    "2": "PATRIMONIAL",
    "3": "MASSIFICADOS",
    "5": "AERONÁUTICO",
    "6": "VIDA",
    "9": "RESPONSABILIDADE CIVIL",
    "20": "EMBARCAÇÃO",
    "23": "AERONÁUTICO RETA",
    "24": "AERONÁUTICO CASCO",
    "25": "MÁQUINAS E EQUIPAMENTOS"
}
    