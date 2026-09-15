# Preferencias de codigo do projeto

- Em Python, mantenha chamadas de funcoes e metodos em uma unica linha sempre que possivel.
- Quando uma chamada ficar muito grande, use no maximo duas linhas: inicio da chamada na primeira e continuacao na segunda.
- Nao coloque cada argumento da chamada em uma linha separada.
- Mantenha assinaturas de funcoes e metodos em uma linha ou, quando necessario, em no maximo duas linhas.
- Escreva SQL de forma compacta: agrupe campos, JOINs e condicoes relacionados, evitando uma linha para cada coluna ou condicao.
- Use o estilo de `retornar_urls` em `repositoriopncp.py` como referencia de equilibrio: mantenha separacao entre SELECT, JOINs, WHERE e blocos logicos, mas nao quebre cada campo ou atribuicao em uma linha.
- Centralize configuracoes repetidas de acesso ao banco em helpers privados quando isso reduzir ruido sem alterar o comportamento.
- Mantenha em `pncp_shared` somente codigo realmente usado por mais de um modulo; consultas exclusivas de uma funcionalidade devem ficar no repositorio do proprio modulo.
- Ao compactar SQL, preserve espacos entre palavras, clausulas e partes dinamicas para nao formar tokens invalidos como `NULLWHERE` ou `1AND`.
- Scripts SQL de manutencao e migracao serao executados manualmente no DBeaver. Prefira comandos diretos e independentes, com `SELECT` de conferencia antes/depois e ordem de execucao indicada; nao use variaveis de sessao, `PREPARE`, procedures auxiliares ou tabelas temporarias sem pedido explicito.
- Aplique esse estilo ao codigo novo ou alterado, sem reformatar arquivos fora do escopo da tarefa.
