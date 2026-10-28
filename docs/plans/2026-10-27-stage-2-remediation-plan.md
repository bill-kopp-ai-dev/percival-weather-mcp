# Stage-2 — Remediação do Percival Weather MCP

**Data / revisão:** 2026-10-27 / 1.0.  
**ID / estado:** S2-WX / planejado; execução não iniciada.  
**Checkout executor:** `/home/bill/Projects/percival-weather-mcp`.  
**Responsável:** executor Weather a designar por bill; política HTTP e gestores com seus donos.

## 1. Objetivo, fontes e fronteira

Tratar os 16 achados da **seção 6** do
[relatório Weather](../../../positronic-bean-IaC/docs/reports/2026-10-27-percival-weather-mcp-iac-readiness-report.md#6-achados-issues-e-inconsistências),
com ações/revalidação nas seções 7/9: 12 ações (1 P1, 6 P2, 5 P3), sem P0.
Baseline e HEAD na emissão: `144dd44078bea4c7ba35111e15442cfc6bf14398`.
Nota `docs/issues/2026-10-10-f3-status.md` localmente excluída antes da campanha;
preservar e reconciliar destino com owner.

[Coordenador stage-2](../../../positronic-bean-IaC/docs/plans/2026-10-27-iac-v1-stage-2-remediation-plan.md)
— retorno S2-WX, seções 3 e 7. Referências:
[consolidação](../../../positronic-bean-IaC/docs/reports/2026-10-26-stage-1-consolidated-readiness-report.md)
e [D-01..D-06](../../../positronic-bean-IaC/docs/decisions/2026-10-27-iac-stage-1-scope-and-pilot-decisions.md).

Emissão documental; execução futura local. Preservar 9 tools, prompts/resources e
template, transportes/perfis suportados, sanitização e provider Open-Meteo. Não é
o piloto inicial D-01. Mock não é homologação de upstream real. Nenhum build/teste
ou contato com serviço público é executado pela emissão deste plano.

## 2. Preparação e decisões

- [ ] Ler instruções/README/CI/config atuais; registrar SHA/worktree e contratos.
  Preservar alterações locais e acordar destino da nota de segurança removida.
- [ ] Reconstruir matriz upstream com fixture TLS/host aliases controlados;
  conferir roteamento antes de iniciar para evitar egress acidental (E-042).
- [ ] Alinhar taxonomia de erro/lifecycle/mount com S2-C01 e metadata/scan com
  S2-C03; fixes locais de erro/config não esperam contrato completo.
- [ ] Owner decide política de `/metrics` e limites/perfis; estimar lotes com bill
  (D-06). Broker/piloto depende de P0 Percival e receita autorizada (D-05).

## 3. Backlog integral e aceite

Todas as ações **não iniciadas**; prioridades de origem preservadas.

| Ação | Achados / P | Trabalho e áreas previstas | Dependência / dono externo | Critério verificável |
|---|---|---|---|---|
| A-001 | F-001 / P1 | Separar erro upstream de entrada inválida em http_client/handlers, preservando distinção para entrada e resultado vazio | S2-C01 como referência | Matriz 429/500/404/timeout com causa externa explícita e orientação coerente; erro validado localmente continua entrada inválida; 200 vazio não confundido com falha |
| A-002 | F-002 / P2 | Retry só para recuperáveis, limitado e com backoff; não repetir 4xx não recuperável | Política corrente por cliente/handler | 400/404 causam uma requisição; 429/5xx/timeout respeitam limite configurado (baseline 3 tentativas), sem multiplicação oculta entre camadas |
| A-003 | F-003, F-004 / P2 | Recusar transporte desconhecido e validar retries/timeout/porta no bootstrap | Perfil de configuração do produto | MCP_TRANSPORT=htpp, retries negativos e números inválidos falham com exit não zero/mensagem controlada; sem fallback silencioso para stdio |
| A-004 | F-005 / P2 | Corrigir source.commit e referência da imagem/metadados em server.yaml; preparar integração no índice | S2-C03; publicação e etapas 2/4 IaC | SHA real e identidade/versão/transporte coerentes; imagem acessível por manifesto/digest na homologação; nunca usar versão de pacote como commit |
| A-005 | F-006, F-015 / P2 | Corrigir nota local: mounts=[] e resources/prompts existem no MCP mas são limitados pelo consumidor | S2-NB-X01/A-010 e docs versionadas | Receita sem mounts=["/"] nem bind do host; resource weather://timezones provado; limites do MCPProvider explicados sem negar existência da capacidade |
| A-006 | F-007, F-014 / P2 | Normalizar timestamps/cache/logs no build e passar VERSION/GIT_SHA no caminho local documentado | Mesmas entradas/builder; etapa 2 IaC | Dois builds sem cache do mesmo SHA com image ID igual; versão/revisão corretas; comparação por arquivo/camada e parâmetros registrados |
| A-007 | F-008 / P3 | Derivar versão do produto no serverInfo | Fonte única da versão | Initialize informa versão do pacote (0.9.0 só se vigente), não 1.30.0 do SDK histórico |
| A-008 | F-009 / P3 | Compartilhar cache de geocoding entre handlers com lifecycle adequado | Concorrência/TTL preservados | Quatro consultas lógicas para mesma cidade em duas tools fazem uma geocodificação no cenário controlado; expiração/concorrência não causam contaminação |
| A-009 | F-010, F-011 / P3 | Tratar SIGINT e investigar variabilidade no EOF, fechar clientes/tarefas | S2-C01 e contrato do gestor | SIGINT encerra; EOF sai em até 1 s em 20 execuções conforme origem; SIGTERM/exit/log observados sem corromper stdout ou deixar tarefa órfã |
| A-010 | F-012, F-013 / P3 | Erro de validação para prompts sem argumento e resource template desconhecido | Contrato MCP/SDK efetivamente usado | Falha distinguível de resposta vazia/sucesso, com envelope de erro correto para cada método; testes wire-level e casos válidos preservados |
| A-011 | F-016 / P3 | Documentar séries de métricas após primeira chamada e decidir bearer/bypass de metrics/health | Decisão de política pelo owner | Decisão datada e docs/testes auth versus health/metrics; se bypass mantido, alcance/exposição explícitos; vazio inicial explicado |
| A-012 | DIST-01, DIST-02 / P2 | Scan no builder CI e triagem/VEX próprios por artefato; completar metadata aplicável/server.json | S2-C03 e candidato; etapas 2/4 IaC | DB/data/SHA/image ID/manifest digest quando existir; decisão VEX por CVE com campos aplicáveis, sem inventar findings; schema/metadata válidos e CI com evidência própria |

**Ajuste de interpretação de A-010:** `isError` é o campo de resultado de tool;
`prompts/get` e `resources/read` devem usar o erro previsto para seus métodos no
schema MCP/SDK vigente. O texto de origem pede `isError=true` também ali. Na
execução, validar o schema, registrar a decisão de equivalência de aceite com o
owner e comprovar erro no wire; não inventar um campo não permitido para seguir a
recomendação literal. O objetivo F-012/F-013 permanece: não apresentar erro como sucesso.

## 4. Lotes e retornos externos

1. **WX-1:** A-001/A-002/A-003, matriz de erro/retry/config e contratos públicos.
2. **WX-2:** A-005/A-007/A-008/A-009/A-010/A-011; revisar lifecycle/cache e
   compatibilidade de respostas do consumidor, com decisão do owner para auth.
3. **WX-3:** A-006/A-004/A-012, candidato/scan/metadados e etapas 2/4. Harness
   deve ser versionado/adotado com S2-C04 e não depender de arquivo temporário.

Runtime antigo/hardening observado em LIFE-01 não é resolvido pelo código Weather:
encaminhar a S2-AP-X01 e S2-NB A-007, receber inventário/candidato/postura de cada
gestor. O checkout não altera registry/config alheios. Sem prazos/horas assumidos;
publicação e prova vertical têm escopo/autorizações próprios.

Riscos: taxonomia nova pode mudar reação do agente, cache comum precisa de isolamento
por parâmetros/TTL, handler de sinal pode disputar loop. Testar caminhos alcançáveis
e comportamento normal, sem esconder timeout/retry com fallback silencioso.

## 5. Qualificação futura local e externa

- [ ] `uv run pytest` offline com respx; lint/format check e mypy no escopo CI
  vigente; regressões dos casos observados falham antes e passam depois.
- [ ] Build/candidato rastreável; stdio e HTTP separados: stdout só JSON-RPC,
  init único, autenticação HTTP aplicável e probes reais do perfil.
- [ ] Reexecutar matriz upstream/config/cache/resources e lifecycle com 20 EOF;
  medir contagem de requisições sem atingir Open-Meteo real.
- [ ] Revalidar `V-BUILD`, `V-RUN`, `V-CONFIG`, `V-MCP`, `V-FUNC` afetados;
  `V-DATA` não aplicável ao estado persistente; `V-PILOT`/`V-REUSE` com prova
  própria. Health HTTP verde sozinho não é readiness MCP.
- [ ] CI remoto/publicação/pull por digest e eventual upstream real são evidências
  próprias; resultado de scan 0/0 antigo não qualifica novo candidato.

Aceite local pode ser parcial; retorno de gestores/catálogo/CI pendente não se
fecha por transferência ou por arquivo de plano existente.

## 6. Penúltima etapa — documentar execução neste plano

- [ ] Registrar por ação data/owner, SHA inicial/final, mudanças, comandos/ambiente,
  testes, evidências locais sanitizadas e vereditos `V-*`; registrar decisão A-010.
- [ ] Documentar riscos/pendências com dono; complementar seção 9 do relatório IaC
  quando autorizado, sem reescrever baseline ou omitir o egresso histórico E-042.

| Data / owner | Ações / achados | SHA inicial → final | Mudanças / evidências locais | Resultado / V-* / pendências |
|---|---|---|---|---|
| Pendente | A-001–A-012 | A registrar | Nenhuma execução nesta emissão | Não iniciada |

## 7. Última etapa — atualizar o plano coordenador

- [ ] Reler o [stage-2 geral](../../../positronic-bean-IaC/docs/plans/2026-10-27-iac-v1-stage-2-remediation-plan.md),
  atualizar **S2-WX na seção 3** e acrescentar retorno na **seção 7**, com contagens,
  SHA/evidência, aceites locais/externos, dependências liberadas e bloqueios.
- [ ] Preservar outros retornos e indicar efeito nas etapas 2/4/5; sem acesso à
  IaC, fornecer resumo e manter **aguardando sincronização**. Concluído exige
  aceites e retorno efetivos; transferência não é correção demonstrada.
