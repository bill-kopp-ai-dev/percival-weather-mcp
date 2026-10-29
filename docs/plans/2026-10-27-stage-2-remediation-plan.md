# Stage-2 — Remediação do Percival Weather MCP

**Data / revisão:** emissão 2026-10-27; atualização 2026-10-29 / 1.1.
**ID / estado:** S2-WX / execução local parcial; gates técnicos remotos e
validação externa pendentes.
**Checkout executor:** `/home/bill/Projects/percival-weather-mcp`.  
**Responsável:** Bill Kopp, owner único do servidor MCP e da infraestrutura IaC
da Positronic Bean Labs; decisão final sobre a aplicação e a infraestrutura.

## 1. Objetivo, fontes e fronteira

Tratar os 16 achados da **seção 6** do
[relatório Weather](../../../positronic-bean-IaC/docs/reports/2026-10-27-percival-weather-mcp-iac-readiness-report.md#6-achados-issues-e-inconsistências),
com ações/revalidação nas seções 7/9: 12 ações (1 P1, 6 P2, 5 P3), sem P0.
Baseline e HEAD na emissão: `144dd44078bea4c7ba35111e15442cfc6bf14398`.
Nota `docs/issues/2026-10-10-f3-status.md` localmente excluída antes da campanha;
preservar a exclusão. `R-05` define `pblabs-mcp-index` como tracker F3 canônico
por imagem, sem manter cópia concorrente neste checkout.

[Coordenador stage-2](../../../positronic-bean-IaC/docs/plans/2026-10-27-iac-v1-stage-2-remediation-plan.md)
— retorno S2-WX, seções 3 e 7. Referências:
[consolidação](../../../positronic-bean-IaC/docs/reports/2026-10-26-stage-1-consolidated-readiness-report.md)
e [D-01..D-06](../../../positronic-bean-IaC/docs/decisions/2026-10-27-iac-stage-1-scope-and-pilot-decisions.md).

Emissão documental; execução futura local. Preservar 9 tools, prompts/resources e
template, transportes/perfis suportados, sanitização e provider Open-Meteo. Não é
o piloto inicial D-01. Mock não é homologação de upstream real. Nenhum build/teste
ou contato com serviço público é executado pela emissão deste plano.

## 2. Preparação e decisões

- [x] Ler instruções/README/CI/config atuais; registrar SHA/worktree e contratos.
  Preservar alterações locais e registrar o destino da nota de segurança.
  — SHA inicial `5943642b6f9b98591f867258a167a461ba332cfd`; uma decisão anterior
  previa restaurar a nota como espelho F3, mas `R-05` a substitui: o tracker
  canônico fica em `pblabs-mcp-index`, por imagem, sem espelho concorrente neste
  checkout. O OpenVEX específico do artefato permanece em `docs/security/`.
- [x] Reconstruir matriz upstream com fixture TLS/host aliases controlados;
  conferir roteamento antes de iniciar para evitar egresso acidental (E-042).
  — CA local e rede `iac-wx-net` recriadas; o roteamento foi conferido
  **antes** de qualquer chamada (os três hostnames públicos resolvem para
  172.31.88.10 e o pedido aparece no log do mock). Nenhum serviço real
  exercitado.
- [ ] Alinhar lifecycle/sinais com S2-C01 e metadata/scan com S2-C03; fixes
  locais de erro/config não esperam contrato completo.
  — **Parcial**: as correções locais de erro, configuração, lifecycle e
  metadados foram feitas sem esperar o contrato; o alinhamento formal com
  S2-C01 (sinais/drain) e o aceite direto de Bill seguem para o fechamento do
  gate, sem exigir pacote separado de evidências de aprovação. O formato
  S2-C03 foi decidido em `R-06`; materialização/versionamento do schema e
  validação dos manifests continuam pendentes.
- [x] Atualização de decisão do operador em 2026-10-29: `R-10` supersede `R-02`
  quanto ao default do broker Percival, que permanece amplo conforme B14/B22/B23–B25.
  O perfil Weather deve declarar explicitamente `mounts=[]` quando não precisa de
  binds; ampliar perfil restrito exige confirmação e auditoria. `R-03` remove a
  exigência de estimar esforço, custo ou prazo;
  `R-05` centraliza F3 em `pblabs-mcp-index`, por imagem publicada; `R-06` adota
  schema externo de `server.json`, extensão operacional `pblabs.app.yaml` e
  destino `pblabs-mcp-index`, sem dependência do Docker MCP Catalog; `R-07`
  exige VEX por CVE ligado ao image ID e assinado pelo owner, com CVEs da imagem
  base tratados por herança; `R-08` fixa pin aprovado e operação em janela única
  datada. A política de `/metrics` permanece registrada separadamente em
  `docs/decisions/2026-10-28-http-endpoint-auth-policy.md`. Em 2026-10-29,
  Bill confirmou as decisões complementares registradas na seção 6.4.

## 3. Backlog integral e aceite

Todas as ações **executadas em 2026-10-28** (ver o registro por ação na
seção 6); prioridades de origem preservadas.

| Ação | Achados / P | Trabalho e áreas previstas | Dependência / dono externo | Critério verificável |
|---|---|---|---|---|
| A-001 | F-001 / P1 | Separar erro upstream de entrada inválida em http_client/handlers, preservando distinção para entrada e resultado vazio | S2-C01 como referência | Matriz 429/500/404/timeout com causa externa explícita e orientação coerente; erro validado localmente continua entrada inválida; 200 vazio não confundido com falha |
| A-002 | F-002 / P2 | Retry só para recuperáveis, limitado e com backoff; não repetir 4xx não recuperável | Política corrente por cliente/handler | 400/404 causam uma requisição; 429/5xx/timeout respeitam limite configurado (baseline 3 tentativas), sem multiplicação oculta entre camadas |
| A-003 | F-003, F-004 / P2 | Recusar transporte desconhecido e validar retries/timeout/porta no bootstrap | Perfil de configuração do produto | MCP_TRANSPORT=htpp, retries negativos e números inválidos falham com exit não zero/mensagem controlada; sem fallback silencioso para stdio |
| A-004 | F-005 / P2 | Corrigir source.commit e referência da imagem/metadados em `server.yaml`; preparar manifest conforme `R-06` para o índice | S2-C03; publicação e etapas 2/4 IaC | SHA real e identidade/versão/transporte coerentes; schema externo de `server.json` validado, extensão `pblabs.app.yaml` e destino `pblabs-mcp-index`; imagem acessível por manifesto/digest na homologação; Docker MCP Catalog não é dependência |
| A-005 | F-006, F-015 / P2 | Publicar orientação sanitizada em documentação versionada: perfil de mounts explicitamente sem bind e resources/prompts existentes mas limitados pelo consumidor | Bill Kopp; `R-10` | Perfil Weather configura explicitamente `mounts=[]` (nenhum bind), sem depender do default amplo do broker; ampliar perfil restrito exige confirmação/auditoria; sem `mounts=["/"]`; resource weather://timezones provado; limites do MCPProvider explicados sem negar existência da capacidade |
| A-006 | F-007, F-014 / P2 | Normalizar timestamps/cache/logs no build e passar VERSION/GIT_SHA no caminho local documentado | Mesmas entradas/builder; etapa 2 IaC | Dois builds sem cache do mesmo SHA com image ID igual; versão/revisão corretas; comparação por arquivo/camada e parâmetros registrados |
| A-007 | F-008 / P3 | Derivar versão do produto no serverInfo | Fonte única da versão | Initialize informa versão do pacote (0.9.0 só se vigente), não 1.30.0 do SDK histórico |
| A-008 | F-009 / P3 | Compartilhar cache de geocoding entre handlers com lifecycle adequado | Concorrência/TTL preservados | Quatro consultas lógicas para a mesma cidade em duas tools fazem uma geocodificação no cenário controlado; expiração/concorrência não causam contaminação. A prova deve usar exatamente esse cenário |
| A-009 | F-010, F-011 / P3 | Tratar SIGINT e investigar variabilidade no EOF, fechar clientes/tarefas | S2-C01; aceite direto de Bill Kopp | SIGINT encerra; o processo do servidor encerra em até 1 s em 20 execuções com EOF. Registrar separadamente a latência do teardown do container; SIGTERM/exit/log observados sem corromper stdout ou deixar tarefa órfã |
| A-010 | F-012, F-013 / P3 | Erro de validação para prompts sem argumento e resource template desconhecido | Contrato MCP/SDK efetivamente usado | Falha distinguível de resposta vazia/sucesso, com envelope de erro correto para cada método; testes wire-level e casos válidos preservados |
| A-011 | F-016 / P3 | Documentar séries de métricas após primeira chamada e decidir bearer/bypass de metrics/health | Decisão de política pelo owner | Decisão datada e docs/testes auth versus health/metrics; se bypass mantido, alcance/exposição explícitos; vazio inicial explicado |
| A-012 | DIST-01, DIST-02 / P2 | Scan no builder CI e triagem/VEX próprios por artefato conforme `R-07`; completar metadata conforme `R-06` | S2-C03 e candidato; etapas 2/4 IaC | DB/data/SHA/image ID/manifest digest quando existir; VEX por CVE ligado ao image ID e assinado pelo owner; CVEs da imagem base tratados por herança; schema/metadata válidos e CI com evidência própria |

**Ajuste de interpretação de A-010:** `isError` é o campo de resultado de tool;
`prompts/get` e `resources/read` devem usar o erro previsto para seus métodos no
schema MCP/SDK vigente. O texto de origem pede `isError=true` também ali. Na
execução, validar o schema, registrar a decisão de equivalência de aceite com o
owner e comprovar erro no wire; não inventar um campo não permitido para seguir a
recomendação literal. O objetivo F-012/F-013 permanece: não apresentar erro como sucesso.

## 4. Lotes e retornos externos

1. **WX-1:** A-001/A-002/A-003, matriz de erro/retry/config e contratos públicos.
2. **WX-2:** A-005/A-007/A-008/A-009/A-010/A-011; publicar a orientação
   versionada e fechar lifecycle/cache conforme as decisões do owner já registradas.
3. **WX-3:** A-006/A-004/A-012, candidato/scan/metadados e etapas 2/4. O harness
   deste produto é versionado e não depende de arquivo temporário; a consolidação
   comum S2-C04 foi adiada para decisão separada, fora do aceite deste produto.

Runtime antigo/hardening observado em LIFE-01 não é resolvido pelo código Weather:
encaminhar a S2-AP-X01 e S2-NB A-007, receber inventário/candidato/postura de cada
gestor. Repin deve usar imagem aprovada e ocorrer em janela única datada e
autorizada (`R-08`). O checkout não altera registry/config alheios. `R-03` remove
o dimensionamento prévio de esforço, custo ou prazo; publicação e prova vertical
têm escopo/autorizações próprios.

Riscos: taxonomia nova pode mudar reação do agente, cache comum precisa de isolamento
por parâmetros/TTL, handler de sinal pode disputar loop. Testar caminhos alcançáveis
e comportamento normal, sem esconder timeout/retry com fallback silencioso.

## 5. Qualificação futura local e externa

- [x] `uv run pytest` offline com respx; lint/format check e mypy no escopo CI
  vigente; regressões dos casos observados falham antes e passam depois.
  — **222 testes verdes** (baseline 149), cobertura 74 % (baseline 67 %),
  `ruff check` e `ruff format --check` limpos, `mypy src/percival_weather_mcp`
  sem issues em 27 arquivos. Regressão verificada contra o código anterior:
  os testes novos **falham** em `144dd44` (17 falhas + 3 erros de coleta) e
  passam em `c82f07c`.
- [x] Build/candidato rastreável; stdio e HTTP separados: stdout só JSON-RPC,
  init único, autenticação HTTP aplicável e probes reais do perfil.
  — Candidato `sha256:821ea0f6761f7cd3d98f5737afc4753060a5eeb87e335aeaf2be23c50d007a58`,
  rótulos `version=0.9.0` e `revision=ed2caa8…`; sessão stdio com 14 linhas
  de stdout, todas JSON-RPC, saída 0; HTTP com 401 sem bearer, 200 com
  bearer e 429 no estouro do orçamento.
- [x] Reexecutar matriz upstream/config/cache/resources e lifecycle com 20 EOF;
  medir contagem de requisições sem atingir Open-Meteo real.
  — 9 cenários de falha, 10 de ambiente + 9 de entrada, cache, resources e
  prompts, 20 execuções com EOF, SIGTERM, SIGINT e `docker stop`. Nenhuma
  chamada ao Open-Meteo real (ver README das evidências).
- [x] Revalidar `V-BUILD`, `V-RUN`, `V-CONFIG`, `V-MCP`, `V-FUNC` afetados;
  `V-DATA` não aplicável ao estado persistente; `V-PILOT`/`V-REUSE` com prova
  própria. Health HTTP verde sozinho não é readiness MCP.
  — Ver a tabela de vereditos na seção 6.
- [ ] CI remoto/publicação/pull por digest e validação controlada do upstream
  real são verificações próprias; resultado de scan 0/0 antigo não qualifica
  novo candidato.
  — **Parcial**: o scan local do candidato novo é 0/0 com base de 2026-10-28
  (próprio). O CI remoto com o novo passo de scan, o push/pull por digest e
  a publicação continuam **pendentes**: o push para `origin/main` foi feito
  (`c82f07c`), mas o CI só roda no GitHub e a imagem ainda não está
  publicada (`mcp/percival-weather-mcp` responde `unauthorized`). Bill autorizou
  a validação controlada contra Open-Meteo; ela ainda precisa ser executada.

Aceites de owner são decisões diretas de Bill Kopp e não exigem pacote separado
de evidências de aprovação. Isso não substitui evidências técnicas de CI, scan,
publicação, comportamento do servidor ou validação upstream.

## 6. Penúltima etapa — documentar execução neste plano

- [x] Registrar por ação data/owner, SHA inicial/final, mudanças, comandos/ambiente,
  testes, evidências locais sanitizadas e vereditos `V-*`; registrar decisão A-010.
- [x] Documentar riscos/pendências com dono; complementar seção 9 do relatório IaC
  quando autorizado, sem reescrever baseline ou omitir o egresso histórico E-042.

**Data:** 2026-10-28; decisões complementares em 2026-10-29. **Owner:** Bill Kopp.
**Executor:** agente
`<positronic>` no checkout do produto.

**SHA inicial:** `5943642b6f9b98591f867258a167a461ba332cfd` (plano, sem execução).
**SHA final:** `c82f07c` em `main`, publicado em `origin/main`
(`144dd44..c82f07c`). **Revisão citada pelo catálogo:** `ed2caa8`
(commit a partir do qual o candidato auditado foi construído).

**Candidato auditado:** `percival-weather-mcp:stage2-candidate`, image ID
`sha256:821ea0f6761f7cd3d98f5737afc4753060a5eeb87e335aeaf2be23c50d007a58`
(`linux/amd64`), rótulos `version=0.9.0` e `revision=ed2caa8…`.
**Evidências sanitizadas:**
`positronic-bean-IaC/docs/reports/evidence/percival-weather-mcp/ed2caa8cfd22/`.
**Harness versionado no produto:** `scripts/verification/` (8 scripts + README
de execução), independente da recomendação de consolidação comum S2-C04, ainda
pendente de aceite.

### 6.1 Registro por ação

| Ação | Achado / P | Estado | Mudança | Evidência |
|---|---|---|---|---|
| A-001 | F-001 / P1 | **verificada** | Taxonomia nova (`errors.py`): `InvalidRequestError` (validação local), `NoDataError` (resposta vazia) e `UpstreamError` (status, timeout, rede, circuito). A falha de upstream não é mais rotulada como entrada inválida; o serviço que falhou é nomeado pela URL. | `failure-matrix.json` (9 cenários), `tests/test_error_taxonomy.py` |
| A-002 | F-002 / P2 | **verificada** | Retry só para recuperáveis: 429, 5xx, timeout e erro de transporte. 4xx não recuperável (400, 404) responde na primeira tentativa. Sem multiplicação entre camadas: um cliente por chamada lógica. | `failure-matrix.json` (400 → 1, 404 → 1, 429 → 3, 500 → 3, timeout c/ 2 retries → 3) |
| A-003 | F-003, F-004 / P2 | **verificada** | `MCP_TRANSPORT` desconhecido → exit 2 com recusa explícita no entrypoint. Validação de faixa no bootstrap (`PORT`, timeout, retries, concorrência, rate limit) → exit 1 com mensagem de operador. `ConfigurationError` controlled; sem traceback cru. | `config-matrix.json`, `tests/test_config_validation.py`, `tests/test_entrypoint_script.py` |
| A-004 | F-005 / P2 | **parcial** | `server.yaml` passa a citar o commit real `ed2caa8…` no lugar da versão `0.9.0`. Materialização/validação do schema S2-C03, CI remoto, publicação e pull por digest ainda pendentes. Bill autorizou publicar após schema válido e CI remoto aprovado, no destino `pblabs-mcp-index`, sem dependência do Docker MCP Catalog; data da janela será definida para a execução. | `docs/mcp/percival-weather-mcp/server.yaml`, `tests/test_catalog_metadata.py`; CI e digest pendentes |
| A-005 | F-006, F-015 / P2 | **parcial** | A nota local `docs/percival-integration.md` passa a usar `mounts=[]` (o broker **rejeita** `mounts=["/"]`) e a descrever corretamente o mecanismo: os resources e prompts **existem** no MCP e respondem; o que o `MCPProvider` do Percival não expõe ao agente é a lista de resources/prompts. O `weather://timezones` está registrado e responde. A orientação sanitizada ainda precisa ser publicada em documentação versionada. | `docs/percival-integration.md` (nota local, gitignored), `resources-probe.json`; publicação documental pendente |
| A-006 | F-007, F-014 / P2 | **verificada** | Build reprodutível: `SOURCE_DATE_EPOCH` no cache key, timestamps normalizados, `uv_cache.json` e logs apt/dpkg/ldconfig removidos, provenance desativado, destinos do `COPY` criados com o timestamp. Caminho documentado: `scripts/docker-build.sh`. | Build limpo e build com cache do mesmo SHA → **mesmo image ID** `sha256:821ea0f6…`; comparação por arquivo: 8.189 arquivos, 0 divergentes |
| A-007 | F-008 / P3 | **verificada** | `serverInfo.version` = versão do produto (`0.9.0`), não a do SDK (`1.30.0`). | `session-ok.json` (stdio) e `http-mode.json` (HTTP) |
| A-008 | F-009 / P3 | **parcial** | Cache de geocoding passa a ser um componente de processo (`GeocodingCache`), com TTL e limite de tamanho preservados e acesso protegido por lock. A evidência atual registra duas geocodificações; falta executar/registrar exatamente quatro consultas à mesma cidade em duas tools para comprovar o critério. | `cache-probe.json`: 4 consultas lógicas em 2 tools → **2** geocodificações (baseline: 3); prova do cenário de aceite pendente |
| A-009 | F-010, F-011 / P3 | **verificada** | SIGINT encerra o container (exit 130 em 0,59 s) com log de shutdown; SIGTERM mantém exit 143 e passa a registrar o shutdown. EOF: saída 0 em 20/20 com log de shutdown. Pelo critério aceito, o tempo do servidor é a medida de aceite: **0,10 s a 0,32 s**. O atraso de até ~14 s observado pelo harness é teardown do container pelo daemon e deve ser reportado separadamente. | `lifecycle.json`, `lifecycle-sigterm.json`, `eof-server-side.txt` |
| A-010 | F-012, F-013 / P3 | **verificada** (com correção de registro) | `resources/read` com alvo desconhecido → erro JSON-RPC **-32002** (era leitura bem-sucedida com payload de erro). `prompts/get` sem argumento obrigatório → erro JSON-RPC **-32602** (antes: código 0, não conformante). **Correção do registro:** o texto do relatório de origem afirma que `prompts/get` devolvia `{"messages": []}` sem erro; a evidência bruto (`resources-probe.json` da Etapa 1) mostra `rpc_error: "Missing required arguments: {'city'}"` — o servidor já respondia com erro, e o relatório confundiu `message_count: 0` com ausência de erro. O defeito de F-012 era o **código** não conformante, não a ausência de erro. | `resources-probe.json` (com `rpc_error_code`), `tests/test_mcp_wire_contract.py` |
| A-011 | F-016 / P3 | **verificada** (decisão do owner) | `/healthz` e `/health` seguem abertos; `/metrics` passa a exigir o bearer quando há token configurado. Decisão datada e registrada; o vazio inicial de `/metrics` está explicado nos docs. | `http-mode.json` (401 sem bearer, 200 com bearer), `docs/decisions/2026-10-28-http-endpoint-auth-policy.md`, `tests/test_metrics_auth.py` |
| A-012 | DIST-01, DIST-02 / P2 | **parcial** | O passo Trivy está implementado no CI e falha o job quando aplicável; evidência local do candidato novo: **0 vulnerabilidades** em todas as severidades, base de 2026-10-28. O CI remoto ainda precisa executar. OpenVEX próprio em `docs/security/openvex.json`, válido contra o schema 0.2.0, com 8 statements ligados ao artefato; Bill assinará o VEX quando necessário, após a publicação/digest. | `trivy-raw.json`, `docs/security/openvex.json`, `docs/security/README.md`; CI remoto, assinatura e digest publicado pendentes |

### 6.2 Vereditos `V-*`

| Cenário | Estado | Base |
|---|---|---|
| `V-BUILD` | **aprovado** | Build limpo e build com cache do mesmo SHA produzem o **mesmo image ID**; rótulos `version`/`revision` corretos; conteúdo idêntico (8.189 arquivos, 0 divergentes); sem `RepoDigest` (imagem ainda não publicada) |
| `V-RUN` | **aprovado** | EOF → 0 em 20/20 com log de shutdown; `SIGINT` → 130 em 0,59 s; `SIGTERM` → 143 em 0,22 s; `docker stop` → 143 em 0,49 s; latência EOF→exit do servidor ≤ 0,32 s |
| `V-CONFIG` | **aprovado** | 10 combinações de ambiente e 9 entradas inválidas; transporte desconhecido, retries negativos, timeout/porta inválidos e rate limit zero falham fechados com mensagem de operador |
| `V-DATA` | **não aplicável** | Servidor sem estado (inalterado) |
| `V-MCP` | **aprovado** | `initialize` → `notifications/initialized` → `tools/list` → `tools/call`; 9/9 com `isError=false`; 3 prompts, 3 resources e 1 template; stdout só JSON-RPC; `serverInfo.version=0.9.0`; erros de `prompts/get` e `resources/read` no wire com códigos padrão |
| `V-FUNC` | **aprovado localmente; real pendente** | 9 tools contra upstream **simulado**; 9 cenários de falha com causa explícita e contagem de requisições; cache compartilhado; Bill autorizou validação controlada, ainda não executada |
| `V-PILOT` | **não avaliado** | O par piloto continua sendo Percival + Notes (D-01); este checkout não é piloto |
| `V-REUSE` | **aprovado no escopo Weather** | Bill aceita o harness versionado no próprio produto (`scripts/verification/`) para concluir o Weather; consolidação comum entre MCPs fica adiada para decisão separada e não bloqueia este plano |

### 6.3 Riscos, pendências e responsáveis

| Pendência | Responsável | Observação |
|---|---|---|
| Publicação da imagem e `RepoDigest`; PR no índice PBLabs | Bill Kopp, owner único (Etapa 2) | Autorizada após schema válido e CI remoto aprovado; destino `pblabs-mcp-index`, sem Docker MCP Catalog. Definir a janela datada na execução; imagem ainda não publicada |
| Materialização/validação do schema S2-C03 e alinhamento S2-C01 | Bill Kopp, owner único | Formato do schema decidido em `R-06`; implementar/validar. Aceite S2-C01 será direto por Bill, sem pacote separado de evidências de aprovação |
| Validação controlada do Open-Meteo real | Bill Kopp autorizou | Autorizada; ainda precisa ser executada e registrada como evidência técnica |
| Assinatura VEX e associação ao artefato publicado | Bill Kopp | Bill assinará quando necessário; associar ao digest publicado após publicação |
| Perfil de mounts do broker (`R-10`) e regressões mounts/secrets/lifecycle | Bill Kopp, owner único da infraestrutura | Decisão de política já tomada: default amplo conforme B14/B22/B23–B25; Weather usa explicitamente `mounts=[]`. Implementação e comprovação continuam pendentes |
| Orientação sanitizada em documentação versionada | Bill Kopp | Decidido publicar; a nota atual é gitignored e não satisfaz a publicação versionada |
| Prova exata de cache A-008 | Bill Kopp aceitou o fechamento | Executar as quatro consultas à mesma cidade em duas tools e registrar uma geocodificação |
| `V-REUSE` comum entre MCPs | Decisão futura separada | Fora do bloqueio deste plano; harness próprio aceito para o escopo Weather |
| `E-042` (egresso histórico) | — | **Não reescrito**: o registro da Etapa 1 permanece como está. Nesta campanha nenhum serviço real foi exercitado; o único egresso deliberado foi o download do banco do Trivy e o push para `origin` |

### 6.4 Decisões do owner registradas

1. **Tracker F3** → `R-05` substitui o espelho local pelo canônico
   `pblabs-mcp-index`, organizado por imagem; o OpenVEX específico do artefato
   permanece em `docs/security/`.
2. **Taxonomia de erro** → hierarquia de exceções com causa explícita na
   mensagem, preservando "Invalid weather request" para a validação local.
3. **Equivalência de A-010** → erro no wire do método (`prompts/get` e
   `resources/read`); `isError` permanece exclusivo do resultado de tool.
4. **Política de `/metrics`** → `/healthz` aberto, `/metrics` com bearer.
5. **Harness** → versionado em `scripts/verification/` do próprio produto;
   aceito para concluir Weather. Consolidação S2-C04 adiada para decisão separada.
6. **Commit e push** → commits locais por área e **push para `origin/main`**;
   no checkout do IaC centralizado, apenas commit.
7. **Owner e autoridade** → Bill Kopp (`bill.kopp.dev@gmail.com`) é o owner
   único do servidor MCP e da infraestrutura IaC da Positronic Bean Labs; sua
   decisão é final. Site da empresa: `labs.positronicbean.com` (em desenvolvimento).
   Aceites de owner podem ser dados diretamente, sem pacote separado de evidências
   de aprovação.
8. **Publicação/homologação** → autorizadas após schema validado e CI remoto
   aprovado; usar `pblabs-mcp-index`, sem dependência do Docker MCP Catalog.
   Bill definirá a janela datada da publicação e do pull por digest.
9. **VEX** → Bill Kopp assinará quando necessário para a imagem publicada.
10. **S2-C01** → Bill Kopp dará o aceite diretamente quando necessário; sua
    palavra é suficiente para a aprovação, sem exigência de evidência adicional
    de aprovação.
11. **Open-Meteo real** → validação controlada autorizada por Bill Kopp.
12. **Documentação de integração** → publicar orientação sanitizada em arquivo
    versionado, preservando `mounts=[]`; a nota local ignorada pelo Git não basta.
13. **Fechamentos técnicos aceitos** → comprovar A-008 com quatro consultas à
    mesma cidade em duas tools; em A-009 usar o tempo de encerramento do processo
    do servidor (limite de 1 s em 20 execuções EOF) como critério e reportar
    separadamente o teardown do container; corrigir a contagem do resumo.

| Data / owner | Ações / achados | SHA inicial → final | Mudanças / evidências locais | Resultado / V-* / pendências |
|---|---|---|---|---|
| 2026-10-28 / Bill Kopp (owner), agente `<positronic>` (execução); decisões adicionais 2026-10-29 | A-001 a A-012 executadas: 1 P1, 6 P2, 5 P3. F-012 corrigido no registro (o erro existia, o código não era conformante). | Inicial `5943642b6f9b98591f867258a167a461ba332cfd` → final `c82f07c` (publicado em `origin/main`); candidato construído de `ed2caa8` | 12 commits; 222 testes verdes (baseline 149), cobertura 74 %; ruff e mypy limpos; regressão verificada contra `144dd44` (17 falhas + 3 erros de coleta); candidato `sha256:821ea0f6…`; 9 cenários de falha, 19 de config/entrada, cache, resources/prompts, 20 EOF, SIGTERM/SIGINT/`docker stop`; Trivy local 0/0 com base de 2026-10-28 | **8 de 12 ações verificadas; 4 parciais** (A-004, A-005, A-008 e A-012). `V-BUILD`, `V-RUN`, `V-CONFIG`, `V-MCP` aprovados; `V-FUNC` aprovado localmente, validação real autorizada e pendente; `V-DATA` não aplicável; `V-PILOT` não avaliado; `V-REUSE` aceito no escopo Weather. Pendências listadas em 6.3. |

## 7. Última etapa — atualizar o plano coordenador

- [x] Reler o [stage-2 geral](../../../positronic-bean-IaC/docs/plans/2026-10-27-iac-v1-stage-2-remediation-plan.md),
  atualizar **S2-WX na seção 3** e acrescentar retorno na **seção 7**, com contagens,
  SHA/evidência, aceites locais/externos, dependências liberadas e bloqueios.
- [x] Preservar outros retornos e indicar efeito nas etapas 2/4/5; sem acesso à
  IaC, fornecer resumo e manter **aguardando sincronização**. Concluído exige
  aceites e retorno efetivos; transferência não é correção demonstrada.

**Status:** retorno original concluído em 2026-10-28. O plano coordenador foi
atualizado naquele momento no checkout `positronic-bean-IaC` (commit local,
sem push, conforme decisão do owner): linha S2-WX da seção 3 e entrada na
tabela da seção 7. As decisões complementares de Bill, registradas neste plano
em 2026-10-29, ainda precisam ser sincronizadas no coordenador quando esse
checkout estiver disponível. O estado atual deste plano é **8 de 12 ações
verificadas e 4 parciais**.

**Efeito nas etapas 2/4/5 do roadmap geral:** nenhum gate é liberado. A Etapa 2
(publicação) aguarda schema validado e CI remoto aprovado; depois, a publicação
autorizada no `pblabs-mcp-index` e o pull por digest na janela definida por Bill.
O Docker MCP Catalog não é dependência. A Etapa 4 (índice) depende de S2-C03;
a Etapa 5 depende da conclusão dos gates técnicos e do aceite direto de Bill,
sem pacote separado de evidências de aprovação. O candidato local é rastreável,
reprodutível e sem vulnerabilidades conhecidas no scan local; esses resultados
não substituem CI remoto, publicação, assinatura VEX nem validação controlada
do upstream real.
