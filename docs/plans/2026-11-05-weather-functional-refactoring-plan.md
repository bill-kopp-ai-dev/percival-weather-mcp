# Weather MCP — plano de refatoração funcional

**ID / revisão:** WX-RF / 1.2 — 2026-11-05, atualizado em 2026-11-06.

**Estado:** R0–R6 implementados e validados localmente; R7 executado para a
candidata 0.10.0 (build, scan sem findings, pin e validação pelo agente
conectado). M4 aguarda a decisão de retenção da imagem anterior.

**Dependência de retomada:** [Positronic issue 0028 — ciclo de vida de imagens e containers](../../../alternative-positronic/positronic/docs/issues/0028-oci-agent-cannot-maintain-container-image-lifecycle.md).
A capacidade de manutenção foi implantada e está funcional. Bill determinou
resolver essa issue antes de finalizar WX-RF; o ciclo de imagem está
registrado em [§10 do relatório de implementação](2026-11-05-weather-functional-implementation-report.md).

**Owner e decisor único:** Bill Kopp. Executor proposto: agente Positronic.

**Objetivo:** resolver os 12 achados da bateria funcional com correções
rastreáveis, contratos coerentes e regressões determinísticas.

## 1. Baseline, escopo e resultado esperado

Origem: [registro da bateria de 2026-11-05](../issues/2026-11-05-weather-test-battery.md).
Imagem exercitada na campanha: `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`,
tag `percival-weather-mcp:0.9.0-f62d438`, fonte
`f62d4383c89b63db7328bbbbb1a65846dff31531`.
Checkout inspecionado nesta análise:
`ff21777e6956b208ce541d40b42f44878577b14c`; as 12 issues e o registro da
campanha estão não rastreados. O pin da campanha é evidência histórica, não
inventário atual de nenhum gestor.

O trabalho entrega correções de código, regressões, documentação/exportações
consistentes e aceite vinculado à imagem efetivamente testada. Preservar as
9 tools, 3 prompts, 3 resources, 1 resource template, os transportes existentes,
a fonte Open-Meteo e os nomes dos argumentos já aceitos. As três tools de tempo
ficam cobertas pela regressão de compatibilidade.

A emissão inicial planejou o trabalho; o pedido posterior de execução está
registrado uma vez em §3/§9. A revisão 1.1 incorpora o resultado local e os
limites de integração. Não houve atualização de pin ou publicação.
F3, distribuição, catálogo e a divergência de mounts do Percival continuam
nos registros próprios; não são dependências para escrever as correções locais.

## 2. Revisão crítica das issues

As issues são evidência de sintomas e propostas de investigação, não uma
especificação a implementar literalmente. A leitura do código atual exige
os seguintes ajustes de interpretação, a incorporar na triagem de execução:

| Achado | Conclusão da análise e consequência para o plano |
|---|---|
| I-01: WMO 0 | Defeito confirmado em `WeatherService.get_current_weather`: `value or -1` apaga zero. A afirmação de que céu limpo é a condição mais frequente não foi demonstrada e não é necessária para justificar a correção. |
| I-02: cidade qualificada | Sintoma confirmado pela campanha. A documentação atual do geocoder já especifica qualificadores e `countryCode`; a causa não deve ser reduzida a “vocabulário não documentado”. Revalidar documentação versus serviço real. `Lisbon, UK` não deve ser convertido silenciosamente em Lisboa, Portugal: corrigir o exemplo para uma localização inequivocamente pretendida. |
| I-03: janela de datas | Bug de validação/orientação confirmado. Adicionar archive é ampliação funcional, não pré-requisito: a própria issue admite recusa explícita e documentada. Recomenda-se essa opção para este ciclo (§3). |
| I-04/I-05: validação | Confirmados. `errors.py` já distingue entrada inválida, ausência de dados e upstream; ampliar a aplicação dessa taxonomia em vez de criar uma paralela. `variables=[]` em details era inferência pelo caminho compartilhado e precisa de teste direto. |
| I-06: AQI | A evidência “PM2.5=300 difere” está errada: `aqi_table()` e `_pm25_level(300)` dão **Hazardous**. PM10 também usa a fronteira 424/425 nas duas versões; a fronteira 355 atribuída ao classificador não está no código. Divergências reais incluem PM2.5=35.4 (Moderate no recurso, Unhealthy for Sensitive Groups no classificador) e 250.4 (Very Unhealthy no recurso, Hazardous no classificador). Unidades, médias temporais e versão do padrão são problemas adicionais que impedem apenas unificar números. |
| I-07: status | A tool é estática, mas os endpoints HTTP também são **liveness**, não probes de Open-Meteo: ver `_ASGIWrapper` em `server.py`. Há resolução válida por correção de contrato/documentação, sem novo probe. |
| I-08: schema | Confirmado: recurso manual descreve chaves/limites inexistentes. Erro de template desconhecido já tem testes wire-level com código `-32002` e nomes válidos; mensagem opaca do proxy não prova novo defeito no servidor. |
| I-09/I-11: tempo | Timestamp ausente na prosa e denominadores ausentes confirmados. Entretanto, “timestamp no passado” **não comprova observação de estação**. Forecast API e CAMS oferecem dados de modelos; usar posição temporal e proveniência, não `observed_points` inferido pelo relógio. |
| I-10: ambiguidade | O cache conserva apenas coordenadas e a resposta perde contexto. A amostra de população não estabelece uma regra universal de ordenação do upstream. Tratar como “primeiro candidato do provedor”, não “maior população”. |
| I-12: payload | Corte fixo nas 12 primeiras horas confirmado. ~25 KB é estimativa, não benchmark; medir bytes UTF-8 com fixture antes de fixar orçamento. JSON sem indentação é uma melhoria de serialização, não perda de dados. |

As frases “nenhuma alteração de pin/configuração necessária” em I-01/I-02
não dispensam novo build e pin: containers imutáveis só recebem o fix mediante
substituição da imagem pelo gestor. Revisar esse critério no fechamento.
O registro da bateria também não permite chamar de “sadias” todas as referências
AQI nem afirmar correção de todos os valores por ausência de erro.

## 3. Escolhas de projeto recomendadas

Escolhas de §3 adotadas pelo pedido de Bill de executar este plano em
2026-11-05, registrado uma única vez aqui: janela Forecast limitada,
primeiro candidato com contexto, US AQI do provedor, liveness,
`sample_mode=first|last|spread` e versão candidata 0.10.0.

| Tema | Recomendação | Trade-off e alternativa |
|---|---|---|
| Histórico e previsão | Manter `weather_get_by_range` no Forecast API neste ciclo, com janela local explícita: política conservadora de `today_utc - 92 dias` a `today_utc + 15 dias`, intervalo inclusivo de no máximo 16 dias. | Resolve o erro opaco com menor mudança. Não promete histórico de 2020. Archive fica como ampliação separada, com variáveis próprias, atraso de disponibilidade e proveniência de reanálise; nunca basta trocar a URL e reutilizar `HOURLY_VARIABLES`. |
| Desambiguação | Preservar escolha do primeiro candidato para entrada sem qualificador, mas expor identidade selecionada, candidatos limitados e sinal de ambiguidade. Qualificador fornecido nunca pode ser descartado para obter “alguma” cidade. | Mantém uso simples; não exige confirmação interativa a cada chamada. Erro obrigatório para toda ambiguidade seria alteração mais disruptiva. |
| AQI | Usar subíndices `us_aqi_*` calculados por Open-Meteo para os poluentes solicitados que tenham suporte; classificar o **índice**, não concentração horária bruta. Informar sistema, provedor e método/versão documentada. | Mantém categorias em inglês próximas às atuais e delega médias/conversões ao provedor. European AQI é alternativa válida, mas não deve ser misturado nem escolhido implicitamente por país. A escolha US AQI não afirma equivalência ao padrão brasileiro. |
| Status | Manter resposta textual de liveness/identidade; declarar explicitamente que upstream readiness não é verificada. | Sem tráfego extra, cache de probe ou nova tool/resource. Readiness ativa seria outro requisito, com timeout e estado stale próprios. |
| Amostragem | Preservar `sample_mode="first"` por padrão e propor `first\|last\|spread`, opcional, só em `weather_get_by_range`; limite 12. | Compatível com chamadas existentes; `last` resolve acesso à cauda e `spread` representa o período. Série completa de clima não é requisito desta issue. |
| Versão | Candidato **0.10.0** adotado para o conjunto com argumento opcional e metadados novos. | Não equivale a release ou promoção; consumidores continuam na imagem anterior até R7. |

O limite conservador de 92 dias é uma política proposta do produto, baseada
na documentação `past_days=0..92`, não reprodução exata de todo comportamento
do provedor. A bateria observou até 93 dias atrás via `start_date`. Fixar a
política documentada evita transformar essa observação isolada em garantia.
Mesmo dentro da janela, variáveis podem estar ausentes; isso exige metadados
de cobertura, não promessa de 384 valores válidos por campo.

## 4. Estrutura técnica proposta

Refatorar pelas fronteiras existentes, sem framework genérico ou nova camada
de transporte. Nomes abaixo são alvos propostos, não arquivos já implementados.

| Responsabilidade | Alvo |
|---|---|
| Validação pública | `models.py` e `ToolHandler.parse_args`; erros seguros em `errors.py`. Validadores de domínio emitem `InvalidRequestError`; falhas inesperadas mantêm mensagem controlada. |
| Resolução geográfica | Extrair `GeocodingService` para `tools/geocoding_service.py`; resultado tipado `ResolvedLocation`, incluindo candidatos/contexto. `WeatherService.get_coordinates` pode permanecer como adaptador interno de tupla para compatibilidade. |
| Cache geográfico | `GeocodingCache` armazena resultado tipado imutável, TTL e limite atuais; chave inclui consulta normalizada e filtros/idioma efetivamente usados. Preservar compartilhamento entre clima e AQ. |
| Tempo e agregação | Helpers puros em `series.py`: relógio UTC injetável, leitura alinhada de séries, validade numérica, contagens, cortes temporais e seleção de amostra. |
| Saídas compactas | Modelos de resposta em `output_models.py`; montar objetos na apresentação e serializar uma vez. `utils.format_*` delega durante a transição, preservando callers atuais. |
| Referências | Tabela WMO única e catálogo de categorias de índice em `knowledge_base.py` ou módulo dedicado pequeno; resources e apresentação derivam da mesma definição. |
| JSON público | Serialização compacta UTF-8 compartilhada; `full_data` continua bruto e completo em AQ details. Não impor reconstrução destrutiva de campos desconhecidos do upstream. |

Não mover todo `utils.py` de uma vez. Extrair apenas funções usadas por estas
correções, mantendo adaptadores até verificar referências e testes. Distinguir
modelos de entrada, objetos internos e representação JSON evita que uma
alteração de cache modifique acidentalmente o contrato MCP.

## 5. Pacotes de trabalho e sequência

R0–R6 estão **implementados e validados localmente**; R7 está **parcial**, com
matriz Python e integração nativa aprovadas, mas sem aceite de imagem.
Evidências e rastreabilidade: [relatório de implementação](2026-11-05-weather-functional-implementation-report.md).
Dependência indica ordem técnica, não necessidade de agentes paralelos. Sem
prazo, esforço ou custo estimado; segue a disciplina R-03 do plano Stage-2.

### R0 — Baseline e contrato de compatibilidade

**Depende de:** nada. **Entrega:** baseline reproduzível e escolhas de §3
confirmadas uma vez com Bill, incluindo `sample_mode`, AQI e janela.

- Registrar SHA/worktree, preservar as 13 notas não rastreadas e capturar o
  documento de primitivas atual via `build_primitives_document()`.
- Executar suíte canônica e checks de lint/tipos; separar falhas preexistentes
  sem reescrever testes apenas para torná-los verdes.
- Levantar callers de `get_coordinates`, cache e formatadores legacy nos dois
  pacotes (`percival_weather_mcp`, `mcp_weather_server`) e em `tests/`.
- Congelar fixtures e relógio de referência, por exemplo
  `2026-11-05T21:20:00Z`; testes não dependem da data de execução.
- Registrar as ressalvas de §2 na triagem das issues, preservando a evidência
  original. A escolha por janela limitada fecha I-03 com recusa documentada,
  não como implementação de archive.

**Aceite:** baseline e diff esperado de contrato conhecidos; nenhuma mudança
obrigatória de argumento ou remoção de primitiva planejada inadvertidamente.

### R1 — Correção de valores e validação acionável

**Depende de:** R0. **Cobre:** I-01, I-04, I-05.

- Introduzir função única de descrição WMO, tratando `0`, `None` e código
  desconhecido distintamente; usar em current, forecast e range. Derivar
  `weather://codes` da mesma tabela, preservando `utils.weather_descriptions`
  como alias se houver callers.
- Auditar sentinelas numéricas nas áreas tocadas: zero de precipitação, vento
  e cobertura de nuvem é dado válido; `None` não vira zero físico nem “N”.
  Cobrir especialmente pressão/nuvens/direção em `WeatherFormatter`.
- Capturar `ValidationError` no parsing e compor campo/regra usando detalhes
  conhecidos, sem expor `input`, traceback ou dump do modelo. Validação de
  domínio emite `InvalidRequestError` diretamente; `ValueError` desconhecido
  mantém fallback controlado. Não basta devolver `str(exc)` indiscriminadamente.
- Preservar `WeatherMCPError` nas cinco tools de dados. Para o proxy FastMCP,
  testar também rejeições anteriores ao handler: ele reconstrói assinatura e
  hoje não propaga todos os metadados `Field`, como limites de listas.
- Rejeitar `variables=[]` nos dois modelos e no caminho direto de normalização,
  antes de geocoding; `None`/omitido mantém os defaults. Deduplicar valores
  preservando ordem e limite do conjunto aceito.
- Para séries sem qualquer número válido dos poluentes pedidos, emitir
  `NoDataError`; se só parte faltar, preservar nulos e sinalizar cobertura.

**Aceite:** WMO 0 correto nas três rotas; erros citam campo/regra e limite;
vazio falha sem I/O; não há sucesso interpretável como “zero poluição” quando
não existem dados. Regressões mantêm 400 sem retry e 429/5xx/timeout com
orçamento atual.

### R2 — Geocoding com identidade, filtros e cache coerentes

**Depende de:** R1. **Cobre:** I-02, I-10.

- Extrair resolução compartilhada por Weather e AQ; consultar conjunto limitado
  de candidatos (`count=10`) e preservar `name`, `country`, `country_code`,
  `admin1`, `timezone`, `feature_code`, ID e coordenadas. Campos opcionais
  ausentes continuam ausentes/nulos, não inventados.
- Primeiro respeitar a sintaxe nativa de consulta qualificada. Se não resolver,
  permitir fallback limitado a país reconhecido: normalizar alias documentado
  (`UK -> GB`, códigos como BR/FR e nomes/aliases pt-BR explicitamente
  suportados), pesquisar o nome da cidade com `countryCode` e validar o país
  retornado. Não usar geocoding sem filtro como fallback de uma localização
  qualificada. Lista de aliases tem fonte/versionamento e teste; não prometer
  suporte irrestrito a traduções.
- Preservar casos `Washington, D.C.` e `Springfield, IL`: duas letras podem
  significar região, não país. Não reinterpretar toda sigla automaticamente
  como ISO nem fazer split cego de toda vírgula. Casos desconhecidos retornam
  orientação verificável; documentar precedência.
- Manter primeiro candidato do provedor para consulta simples; adicionar
  `location` com resultado selecionado e `resolution` com ambiguidade detectada,
  número de candidatos retornados e até 3 alternativas. `count=10` é limite de
  busca, não prova de unicidade global; expor essa limitação.
- Adaptar cache para guardar o resultado completo e os filtros, preservando
  TTL, limite, isolamento e compartilhamento. Retorno do cache não pode perder
  país nem trocar candidatos entre consultas qualificadas distintas.
- Propagar contexto nas cinco tools de dados; a prosa identifica cidade,
  região/país e informa alternativas quando necessário. Preservar `city`,
  `latitude` e `longitude` existentes; não confundir coordenada geocodificada
  com centro da célula de modelo retornado pelo provedor.
- Atualizar exemplos do README/modelos/prompts: usar `London, UK`,
  `São Paulo, BR` após regressão do resolver; substituir smoke `Lisbon, UK`
  por `Lisbon, Portugal`. País/região incompatível deve falhar, não “acertar”
  uma cidade de outro país.

**Aceite:** exemplos documentados resolvem para a identidade pretendida;
Springfield mostra contexto/ambiguidade; resultados cacheados preservam o
mesmo contexto; uma consulta inválida não gera sequência ilimitada de fallbacks.
Orçamento proposto: no máximo 2 consultas lógicas ao geocoder por cache miss,
cada uma sujeita ao retry já existente.

### R3 — Política temporal, proveniência e cobertura estatística

**Depende de:** R1 e R2 para integração de localização. **Cobre:** I-03,
I-09, I-11; prepara I-08/I-12.

- Centralizar o relógio de referência UTC e os limites inclusivos. Validar
  ordem, duração e posição do intervalo antes de qualquer I/O. Usar os limites
  de §3 e o limite configurado de duração como fonte única, sem número
  independente escrito no schema. Revalidar capacidades reais antes do aceite.
- HTTP 400 mantém status/taxonomia de upstream. Extrair `reason` conhecido
  como detalhe limitado/sanitizado (por exemplo, até 300 caracteres sem
  controles), com fallback se corpo não for JSON ou formato inesperado.
  Corpo é dado externo, nunca instrução. Remover orientação genérica que
  atribui qualquer recusa à cidade; preservar retries atuais.
- Manter seleção atual da hora mais próxima para evitar mudança implícita de
  valores; informar `selection_method="nearest_hour"`, `reference_time` UTC
  e `valid_time`/fuso. Na prosa usar “dado do modelo válido em ... UTC”, não
  “medição observada”. Se timestamp faltar, dizer indisponível.
- Adicionar metadados de fonte/modelo quando disponíveis; não fabricar
  `model_run_at` nem equiparar `generationtime_ms` a idade do dado.
- Para range e AQ, separar contagens e estatísticas em `past_or_present`
  (`valid_time <= reference_time`) e `future`. Manter resumo de janela total
  por compatibilidade, explicitamente identificado como tal; posição temporal
  não muda `data_kind="model"` em dados do Forecast API/CAMS.
- Por variável e por segmento: `valid_points`, `missing_points`, min/max/avg;
  denominador é o eixo temporal esperado retornado. Arrays curtos não podem
  deslocar valores no tempo; nulos, não finitos e booleanos não são números
  válidos. Toda estatística vazia fica nula, com zero pontos válidos.
- Expor início/fim UTC, total retornado, esperado quando determinável e
  cobertura parcial. Não inferir hora de corte pela posição de um array.
  Na amostra AQ de referência, 21:00 está no segmento passado/presente:
  22 timestamps de 00:00 a 21:00, não as “21 observações” citadas na issue.

**Aceite:** datas fora da política falham com janela explícita sem I/O;
timestamp/fuso visíveis; sumários permitem distinguir passado/futuro sem
atribuir caráter observacional; fixture ammonia de 120 pontos e 28 nulos
informa 92 válidos e 28 ausentes, com estatísticas sobre os 92.

### R4 — AQI consistente com unidades e método

**Depende de:** R1 e R3. **Cobre:** I-06.

- Remover a aplicação dos limiares antigos a concentrações horárias. Não
  tratar WHO 2021 e EPA AQI como uma tabela única: são referências distintas,
  com unidades e períodos de integração diferentes. A documentação atual de
  Open-Meteo distingue PM/CO/O3/SO2/NO2 e a EPA registra revisão AQI em 2024.
- Solicitar internamente apenas os subíndices US AQI correspondentes aos
  poluentes pedidos e suportados; manter o argumento público `variables`
  restrito ao conjunto atual. Não duplicar HTTP para calcular classificação.
- Entregar bloco `air_quality_index` com sistema (`us_aqi`), valor por
  poluente, categoria, provedor, timestamp, referências e método temporal.
  Se houver índice agregado, identificar se cobre todos os componentes do
  provedor ou só um subconjunto; nunca nomear máximo parcial como índice
  global completo. Sem dado ou sem índice para ammonia/dust/AOD resulta em
  `unavailable`/`not_supported`, não “Good”.
- Uma definição versionada de categorias **do índice** alimenta resposta e
  `weather://aqi`. Fixar regras de borda 50/100/150/200/300, valor >500, nulo,
  negativo e não finito. Documentar a versão metodológica do provedor sem
  fingir auditoria independente de seu cálculo de concentração para AQI.
- O recurso explica unidades, médias temporais, referências e limitações.
  Não acrescentar aconselhamento de saúde derivado dos antigos limiares;
  a tool aponta explicitamente para o recurso, conforme permite I-06.
- Auditar callers de `format_legacy` e `AirQualityService.format_response`:
  este último já delega ao primeiro, então ausência de uso nas tools não
  prova inexistência de compatibilidade externa. Remover limiares/conselhos
  duplicados; preservar adaptador de concentrações, ou descontinuar de forma
  explícita se não houver obrigação de compatibilidade identificada em R0.

**Aceite:** rótulos de índice e recurso concordam nas bordas; concentrações
não são comparadas a limites em ppb/ppm sem conversão; nenhum risco é inferido
de ausência de dados. Fixtures testam também os contraexemplos verdadeiros
35.4/250.4 ao retirar o caminho antigo, sem perpetuar o falso caso 300.

### R5 — Amostragem e payload previsíveis

**Depende de:** R3; integrar R4 antes de medir o payload final. **Cobre:** I-12.

- Adicionar `sample_mode` opcional com default `first`; `last` devolve as
  últimas 12 linhas disponíveis e `spread` até 12 índices determinísticos
  incluindo primeiro/último, sem duplicação. Respostas permanecem em ordem
  temporal. Para séries de até 12 pontos, entregar todos.
- Adicionar metadados de amostra: modo, limite, pontos retornados, total e
  truncamento. Sem pretensão de série completa se houve amostragem. A AQ
  compacta pode manter limite 8, explicitamente documentado.
- Serializar JSON uma vez, sem indentação e com `ensure_ascii=False`, válido
  em UTF-8; rejeitar NaN/Infinity na serialização. Preservar todas as chaves e
  todos os arrays `full_data` da tool de detalhes. A seleção `variables` já
  existente é o mecanismo para reduzir campos; não truncar detalhes escondido.
- Medir `len(text.encode("utf-8"))` em fixture fixa de 120 horas × 9 variáveis,
  incluindo os novos metadados/índices. Registrar tamanho compacto versus
  indentado **do mesmo objeto**; uma regressão de bytes deve usar orçamento
  derivado dessa medição, não a estimativa histórica de 25 KB. Documentar
  crescimento O(horas × variáveis) e limitação do payload detalhado.

**Aceite:** chamada antiga preserva início da amostra; `last` permite obter
a cauda, `spread` cobre os extremos; JSON decodificado de details não perde
dados; medição reproduzível e teto por fixture registrados.

### R6 — Contratos, resources, prompts e status

**Depende de:** R1–R5 para contrato final. **Cobre:** I-07, I-08; consolida
documentação de todas as demais.

- Gerar a estrutura dos schemas de saída a partir dos modelos usados pelo
  formatador, mantendo descrições semânticas explícitas e testadas. Corrigir
  `period`, nomes das estatísticas, contagens e caps. `full_data` bruto pode
  ter propriedades adicionais; não prometer schema fechado do provedor.
- Neste ciclo, remover a promessa de `total precipitation`; conservar
  min/max/avg documentados. Um total acumulado exigiria definir intervalos
  da precipitação e cobertura faltante antes de somar; não é necessário para
  fechar a divergência documental.
- `weather_get_status` e README passam a informar liveness/identidade e
  “upstream readiness not checked”. Preservar nome, argumentos vazios e tipo
  textual. Uma falha upstream simulada não altera o sinal de processo vivo;
  a chamada de dados continua reportando sua falha própria.
- Revisar prompts e descrições sobre timestamp, modelos, janela, contexto
  geográfico, amostra e recurso AQI. Nenhum prompt promete histórico ilimitado,
  observação direta ou série completa quando a tool entrega amostra.
- Regenerar `docs/tools.json` pela função/CLI `tool_export`, nunca com edição
  manual divergente. Conferir as exportações existentes de registry/labels
  que dependem desse snapshot, sem publicar ou operar outro repositório.
- Testar modelo de entrada versus schema realmente descoberto por FastMCP:
  opcionais/defaults, enums, `minItems`, limites e ausência de `kwargs`.
  Serializar a partir dos modelos de resposta e validar fixtures contra eles;
  apenas listar chaves no resource não constitui JSON Schema validado.

**Aceite:** descoberta/exportação/README/prompts/resources descrevem o mesmo
contrato; 9/3/3/1 preservados; resource desconhecido continua erro MCP
`-32002`, sem sucesso contendo um objeto de erro.

### R7 — Integração, imagem candidata e encerramento

**Depende de:** R1–R6. **Cobre:** aceite integrado das 12 issues.

- Executar regressões de §6 e suíte completa, lint/format/tipos. Confirmar
  Python 3.10–3.12 na matriz suportada; resultado CI remoto só pode ser
  afirmado quando efetivamente executado para a fonte candidata.
- Atualizar changelog/versão conforme contrato acordado. Registrar fonte,
  worktree e hash de alterações relevantes se não houver commit solicitado.
- Seguir o ciclo de runtime do `AGENTS.md` e o
  [runbook de operação](../../../nanobot/docs/operations/mcp-docker-local-runbook.md):
  reler o inventário do gestor dono e preservar o pin anterior para rollback;
  build canônico com `scripts/docker-build.sh <tag-do-candidato>`; registrar
  image ID completo, versão e labels. Scan/SBOM e critérios de segurança do
  projeto continuam ligados ao artefato novo, sem reutilizar scan/VEX antigo.
- Com autorização aplicável, pinar o candidato por image ID imutável no
  Positronic usando a CLI suportada, revision atual e reconfiguração prevista;
  confirmar imagem efetiva, reconectar e testar pelo agente. Não substituir
  o launcher `positronic` por alias `opencode`.
- Fazer `initialize -> tools/list -> tools/call`, leitura de resources e
  renderização dos 3 prompts. Para erro determinístico WMO 0/nulos/HTTP 400,
  usar fixture do provedor; clima real isolado não garante essa condição.
  Repetir smoke real de localização/dados contra Open-Meteo e distinguir essa
  prova da fixture. Usar cliente MCP de teste para primitivas não expostas
  pelo proxy do agente.
- Se HTTP for afetado, fixture em loopback verifica auth, `/healthz`,
  `/health`, `/metrics` e chamada MCP autenticada; health não substitui teste
  funcional. Stdio permanece sem porta e stdout reservado ao JSON-RPC.
- Em reprovação/incompletude, restaurar último pin bom e verificar chamada
  MCP. Em aceite autorizado, promover o mesmo image ID testado. Percival só
  recebe atualização se incluído na autorização e pelo seu próprio gestor,
  com validação própria. Reter/remover imagens seletivamente conforme runbook
  e autorização de limpeza; nunca usar prune global.
- Fechar cada issue apenas com links para fix, regressão e evidência do image
  ID aceito. Registrar qualquer critério reinterpretado, como I-03/I-07, e
  limitações pendentes. Limpeza bloqueada ou consumidor não atualizado fica
  explícito como conclusão parcial do ciclo operacional.

**Aceite:** código, contrato e comportamento do candidato demonstrados;
rollback disponível; nenhum “resolvido em produção” baseado só em pytest.

## 6. Matriz de rastreabilidade e regressão

Os IDs I-01..I-12 são locais a este plano; não são números de GitHub.
Reutilizar testes existentes e criar módulos novos apenas quando o domínio
extraído justificar. Cada fix deve ter regressão que falhe antes do patch.

| Issue | Pacote | Casos mínimos e evidência de resolução | Base de testes a estender |
|---|---|---|---|
| [I-01 — WMO 0](../issues/2026-11-05-weather-clear-sky-reported-as-unknown.md) | R1 | 0/None/código desconhecido em current, forecast e range; zeros físicos versus nulos no formatador; resource WMO alinhado | `test_handlers.py`, `test_formatters.py`, `test_formatter_none_handling.py`, `test_primitives.py` |
| [I-02 — qualificadores](../issues/2026-11-05-weather-city-qualifier-format-fails.md) | R2 | London UK/GB, São Paulo BR/Brazil/Brasil, Paris FR, cidade simples, país incompatível, Washington D.C., Springfield IL, aliases pt-BR suportados; assert de filtros HTTP e identidade, não só sucesso | `test_geocoding_cache.py`, `test_handlers.py`, `test_docstring_quality.py`; novo `test_geocoding_resolution.py` |
| [I-03 — janela](../issues/2026-11-05-weather-range-outside-upstream-window.md) | R3 | Mesmo dia, duração 16/17, inversão, ano bissexto, `today-92`/anterior, `today+15`/posterior, 2020/2030 e virada UTC com relógio fixo; falha local sem I/O; reason 400 sanitizado, inválido e ausente | `test_date_range_validator.py`, `test_error_taxonomy.py`, `test_http_client.py` |
| [I-04 — erros genéricos](../issues/2026-11-05-weather-generic-validation-errors.md) | R1 | Campo ausente, data inválida/invertida, duração, city vazia/longa/proibida, variável inválida; erro específico pelos handlers e sessão MCP; erro desconhecido sem vazamento | `test_error_taxonomy.py`, `test_tool_schemas.py`, `test_mcp_wire_contract.py` |
| [I-05 — variables vazio](../issues/2026-11-05-weather-air-quality-empty-variables.md) | R1 | `[]` rejeitado nas duas tools sem chamadas; omitido/None mantém default; duplicadas; série toda nula versus parcialmente nula, zero legítimo preservado | `test_tool_schemas.py`, `test_air_quality_integration.py`, `test_error_taxonomy.py` |
| [I-06 — AQI](../issues/2026-11-05-weather-aqi-bands-contradiction.md) | R4 | Categorias nas bordas de índice e fora da faixa; índices ausentes; subíndices conforme seleção; unidade/média/fonte; resource e resposta iguais; sem usar concentração como índice | `test_formatters.py`, `test_air_quality_integration.py`, `test_primitives.py`; novo `test_air_quality_index.py` |
| [I-07 — status](../issues/2026-11-05-weather-status-tool-not-a-health-check.md) | R6 | Status declara somente liveness/readiness não verificada; upstream simulado indisponível não vira alegação de prontidão; identidade/versão corretas | `test_mcp_wire_contract.py`, `test_tool_export.py`, `test_server_metrics.py` |
| [I-08 — schema](../issues/2026-11-05-weather-schema-resource-range-inaccurate.md) | R6 | Schema valida saída real de fixture; caps e `period` corretos; sem total inexistente; template desconhecido mantém erro; exportação bate com descoberta | `test_primitives.py`, `test_mcp_wire_contract.py`, `test_tool_export.py`, `test_input_schema_fix.py` |
| [I-09 — timestamp](../issues/2026-11-05-weather-current-snapshot-without-timestamp.md) | R3 | Prosa com timestamp UTC exato; timestamp ausente; hora mais próxima à frente; relógio fixo; não afirmar observação de estação | `test_formatters.py`, `test_utils.py` |
| [I-10 — ambiguidade](../issues/2026-11-05-weather-city-ambiguity-not-reported.md) | R2 | Springfield com candidatos, cidade inequívoca, identidade parcial, cache hit/miss/TTL/evicção/concorrência; países distintos não contaminam chave | `test_geocoding_cache.py`, novo `test_geocoding_resolution.py` |
| [I-11 — resumo/cobertura](../issues/2026-11-05-weather-summary-mixes-observed-and-forecast.md) | R3 | 120 timestamps/28 nulos -> 92 válidos; array curto, booleano/não finito, todos nulos e zero; split no instante de referência, resumo total compatível; proveniência model | `test_air_quality_integration.py`, `test_formatters.py`; novo `test_series.py` |
| [I-12 — amostra/payload](../issues/2026-11-05-weather-output-payload-limits.md) | R5 | first/last/spread em 1/12/24/384 pontos; extremos, ordenação e sem duplicatas; UTF-8, equivalência do objeto details antes/depois da compactação; bytes da fixture final | `test_formatters.py`, `test_air_quality_integration.py`, `test_proxy_defaults.py`, novo `test_series.py` |

CI funcional usa `respx`, sem rede real. Executar casos pelos handlers e por
sessão MCP, porque a validação pode ocorrer no proxy antes de chegar ao handler.
Manter isolamento de estado via `reset_shared_state` e evitar sleeps/datas
reais quando relógio injetável resolver.

Checks canônicos no fechamento de código, conforme CI atual:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/percival_weather_mcp
uv run pytest --cov=percival_weather_mcp --cov-report=xml
```

Documentação e schemas são validados pelo seu conteúdo/contrato, não pela
presença de palavras-chave. Suíte verde não substitui integração da imagem.

## 7. Marcos, riscos e condição de conclusão

**Sequência recomendada:** R0 -> R1 -> R2 -> R3 -> R4 -> R5 -> R6 -> R7.
R1 oferece um candidato corretivo pequeno; o restante pode seguir em mudanças
locais coesas, com documentação atualizada junto de cada contrato. Um novo
build/promoção é necessário por candidato que se pretenda aceitar em runtime,
não por cada edição intermediária.

| Marco | Evidência exigida |
|---|---|
| M1 — correções centrais | R1 demonstrado com regressões de zeros/erros/lista vazia; nenhuma nova promessa geográfica ou histórica |
| M2 — semântica consistente | R2–R5 demonstrados, incluindo identidade, tempo, cobertura, AQI e custo de payload |
| M3 — contrato consolidado | R6, diff de schemas explícito e 9/3/3/1 preservados |
| M4 — aceite operacional | R7 com fonte/image ID, integração, decisão técnica, pin final e rollback; fechamento das issues com evidência |

| Risco ou incerteza | Controle e impacto |
|---|---|
| Consumidor depende da posição/chave da amostra ou do texto literal | Defaults preservados; argumento novo opcional; diff de contrato e smoke no consumidor. Remoção/rename de chave exige decisão explícita de migração. |
| Geocoder/documentação mudam ou aliases colidem com regiões | Fixtures de filtros e identidade, fallback limitado e smoke real; não inferir ISO de toda sigla. |
| Janela local diverge do upstream | Política conservadora documentada; reason upstream preservado; revalidar limites na integração e tratar lacunas como indisponibilidade. |
| Classificação AQI incorreta por unidade/média/versão | Usar índice do provedor, referência metodológica datada e catálogo único; não aplicar antigos limiares brutos nem inventar faixas de ammonia/dust/AOD. |
| Aditivos tornam payload grande | Seleção de variáveis, alternativas limitadas, JSON compacto e benchmark por fixture após todos os metadados. |
| Docker, autorização ou acesso ao gestor indisponível | Resolvido em 2026-11-06: o executor host entrega build, scan e SBOM sem CLI Docker no agente. A limitação persistente é a ausência de fase de verificação — o executor não roda o smoke nem a conformance do projeto, e por isso as propriedades de runtime do container (transportes HTTP, usuário efetivo, manifesto embutido) ficam sem evidência na imagem candidata. Ver §10.4 do relatório. |
| Recursos/prompts ocultos pelo proxy | Fixture/cliente MCP suportado e evidência explícita; não atribuir falha de apresentação automaticamente ao servidor. |

Conclusão requer todas as 12 issues com critério atendido ou decisão explícita
de escopo, testes pertinentes e evidência do candidato. “Janela documentada”
e “status como liveness” são resoluções alternativas permitidas pelas issues;
se Bill escolher archive ou readiness ativa, revisar dependências/testes antes
da execução. Essas ampliações acrescentam políticas de fonte, disponibilidade,
timeout e integração; não são simples ajustes de texto.

**Próxima ação:** M4 depende de duas decisões de Bill. A primeira é a
retenção da imagem anterior — a promoção da candidata já está efetivada e
verificada. A segunda é como fechar a lacuna de verificação de runtime do
container: executar o smoke e a conformance no host contra a candidata
pinada, ou acrescentar uma fase de verificação ao executor host. Até uma das
duas, o aceite declara as verificações 3, 4, 6 e 7 do smoke como não
executadas, sem afirmar cobertura que não existe.

## 8. Fontes e verificação desta emissão

Código consultado: `tools/weather_service.py`, `tools/tools_weather.py`,
`tools/air_quality_service.py`, `tools/tools_air_quality.py`, `tools/toolhandler.py`,
`http_client.py`, `errors.py`, `models.py`, `utils.py`, `presentation/*`,
`knowledge_base.py`, `server.py`, `resources.py` (registro/erros via busca),
`tool_export.py` e testes/CI citados. Caminhos relativos ao pacote
`src/percival_weather_mcp/`, salvo testes e CI.

Fontes primárias consultadas em **2026-11-05** para orientar o desenho:

1. [Open-Meteo — Geocoding API](https://open-meteo.com/en/docs/geocoding-api):
   qualificadores, idioma de saída, `countryCode`, precedência de abreviações
   e metadados. Documentação atual não substitui revalidação do serviço real.
2. [Open-Meteo — Forecast API](https://open-meteo.com/en/docs): dados de modelos,
   `past_days` até 92, previsão até 16 dias, nulos por variável e semântica
   horária; base da política conservadora proposta, não garantia universal.
3. [Open-Meteo — Air Quality API](https://open-meteo.com/en/docs/air-quality-api):
   CAMS, janela padrão de 5 dias desde 00:00, ammonia apenas Europa, unidades,
   índices US/European e respectivas médias temporais. Citar Open-Meteo/CAMS
   conforme requisitos de atribuição ao documentar a nova proveniência.
4. [EPA — reconsideração PM e AQI](https://www.epa.gov/pm-pollution/final-reconsideration-national-ambient-air-quality-standards-particulate-matter-pm):
   revisão AQI anunciada em 2024; página atualizada em 2026-04-14. Não usar
   norma anual de concentração como se fosse corte de índice horário.
5. [WHO — diretrizes globais 2021](https://www.who.int/publications/i/item/9789240034228):
   identificação da referência e escopo das diretrizes. O texto integral de
   290 páginas não foi auditado nesta emissão; não valida os conselhos legacy.

Além das fontes, foram revisadas as 12 issues, instruções do projeto, plano
Stage-2 e runbook. Nesta emissão não foram executados testes funcionais,
benchmark de payload, Docker ou operações em gestores. A verificação do plano
é documental: coerência, rastreabilidade das 12 issues, referências locais e
diff. Nenhuma issue está resolvida pela criação deste documento.

## 9. Registro de execução

- Fonte inicial: `ff21777e6956b208ce541d40b42f44878577b14c`, sem diff rastreado;
  preservadas as 13 notas e este plano, previamente não rastreados.
- Baseline canônico com `uv run pytest` em Python 3.12.15: **221 passaram / 1 falhou**.
  Falha preexistente: `test_every_cve_of_the_f3_gate_has_a_statement` lê nota
  removida pelo fechamento F3. A correção de manutenção preservará o conjunto
  histórico de CVEs da revisão `9746453`, sem usar o tracker vivo para alterar
  o escopo de um VEX antigo. Execução inicial direta fora de `uv run` também
  falhou ao localizar `python` em subprocesso; a execução canônica resolve isso.
- Baseline Ruff check/format e mypy: aprovados (27 módulos de origem).
- Snapshot `build_primitives_document()`, JSON com `sort_keys=True` e
  `ensure_ascii=False`, SHA-256:
  `349e94b539607e51214215fa24872db874fc01066cc5b4460c50ae2de6a0ad39`.
  Contagens: 9 tools / 3 prompts / 3 resources / 1 template.
- Inventário Positronic relido: Weather global, stdio, revisão 5,
  configuração `94813a6c-5181-47ab-be15-fc38da5308cc`, pin
  `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`.
  Rede bridge, sem mounts/env; allowlist das nove tools preservada.
- Ambiente de execução atual: Docker CLI ausente; não houve build, mudança de
  pin, promoção ou limpeza. R7/M4 permanecem pendentes dessa dependência.
- Implementação local concluída: **319 testes aprovados em cada uma das versões
  Python 3.10.19, 3.11.14 e 3.12.15**, Ruff check/format e mypy aprovados.
  Nova sessão MCP stdio nativa exercitou as nove tools, com Open-Meteo real;
  fixture HTTP autenticada em loopback aprovada. Ver
  [relatório técnico](2026-11-05-weather-functional-implementation-report.md) e
  [evidência nativa](2026-11-05-weather-functional-native-verification.json).
- Tentativa de build canônico terminou com exit 1: Docker não está em PATH.
  Inventário final mantém o pin/revisão inicial. As 12 issues receberam
  seguimento de correção local, mas continuam abertas para aceite da imagem.
- **2026-11-06 — ciclo de imagem executado.** A capacidade de manutenção do
  agente (issue 0028) está operacional: a candidata
  `sha256:40fa10fffabb0678fdbf584a3a2d4c6531f633b4f2282ab92b33fbc3568e3b25`
  foi construída a partir do commit `875fff909c4786baba87dbf3fad68ca71d566001`
  com árvore limpa, escaneada com **0 findings** no gate
  LOW/MEDIUM/HIGH/CRITICAL, autorizada, pinada e validada pelo agente
  conectado (status, descoberta e as três tools de dados com conteúdo
  conferido). As quatro primeiras submissões falharam por indisponibilidade
  transitória do Debian Snapshot (503/504 em cache de borda); nenhuma mudança
  de fonte, pin ou snapshot foi feita para contornar isso. Um incidente
  distinto no registry do gestor, causado pela flag `--version` do comando
  `mcp server metadata`, foi reparado e registrado na
  [issue 0029 do Positronic](../../../alternative-positronic/positronic/docs/issues/0029-mcp-metadata-version-flag-corrupts-the-registry.md).
  Evidência completa em [§10 do relatório](2026-11-05-weather-functional-implementation-report.md).
- **2026-11-06 — varredura funcional completa e avaliação de cobertura.** As
  nove tools da candidata pinada foram exercitadas pelo agente conectado;
  `get_details`, `get_air_quality_details`, `get_time`, `get_timezone` e
  `convert_time` completaram as quatro anteriores. O levantamento do que
  `scripts/smoke-container.sh` e `scripts/docker-ci-conformance.py` verificam
  mostrou que a validação funcional cobre o contrato stdio do gateway e o
  comportamento das tools — com mais profundidade que o smoke — mas não as
  propriedades de runtime do container: transportes HTTP, usuário efetivo e
  manifesto embutido não foram verificados nesta candidata. Checagens
  estáticas fecharam parte da lacuna: label do Dockerfile × tools
  descobertas, `build_oci_label.py --check` e validade do `mcp.yaml` no
  repositório. Detalhes em §10.4 do relatório.
- **2026-11-06 — promoção verificada e health check.** O caminho do gestor é
  `update-image` → `configure` → `activate`, e as três etapas já estavam
  executadas desde o ciclo de imagem. A promoção foi reconfirmada sem mutar
  estado: `activate weather 7` resolveu a imagem pinada no host e devolveu o
  servidor inalterado; `show weather` confirma `version 0.10.0`,
  `imageId sha256:40fa10ff…`, `activated: true`, `scope: global`, revisão 7,
  configuração revisão 1, zero mounts, env vazio e as nove tools na allowlist;
  `local-images` confirma a revisão de autorização 7 com a candidata autorizada
  e a imagem anterior ainda autorizada para rollback. Health check: status de
  liveness com `Version: 0.10.0`, `get_current` com dados reais de São Paulo
  e `valid_time`, e `discover` com as nove tools por handshake novo. A
  candidata é a imagem viva; o que faltava era a evidência registrada. Ver
  §10.5 do relatório.
- **Pendências:** decisão de retenção da imagem anterior
  `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`
  (ainda autorizada para rollback; remoção exige lista nominal e autorização
  específica), decisão sobre como fechar a lacuna de verificação de runtime
  (§10.4), fechamento das 12 issues e fechamento formal da issue 0028.
