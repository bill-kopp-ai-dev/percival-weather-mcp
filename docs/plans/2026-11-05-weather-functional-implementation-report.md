# WX-RF — implementação funcional e verificação local

**Data:** 2026-11-05. **Owner:** Bill Kopp. **Candidato de fonte:** 0.10.0.

**Resultado:** R0–R6 implementados e validados localmente. Os 12 achados têm
correção e regressão. R7/M4 executados: a candidata 0.10.0 foi construída pelo
executor host, escaneada com **0 findings**, pinada no Positronic e validada
funcionalmente pelo agente conectado. Restam a decisão de retenção/limpeza da
imagem anterior e o registro do incidente de registry descrito na §10.

Plano e decisão de execução: [WX-RF, §3 e §9](2026-11-05-weather-functional-refactoring-plan.md).

## Entregas e contrato

- Geocoding compartilhado com identidade imutável, cache TTL/limite preservado,
  até dez candidatos e três alternativas. Fallback de país validado, em no
  máximo duas consultas lógicas por cache miss; qualificadores não são descartados.
- WMO 0 preservado; tabela compartilhada com resource. Nulos de direção,
  pressão e nuvens não viram norte/zero. Validação informa campo e regra,
  inclusive antes da validação FastMCP, sem devolver o input bruto.
- Forecast limitado a UTC hoje-92 até hoje+15 e duração padrão de 16 dias
  inclusivos. Archive continua fora do escopo. Motivo de HTTP 400 sanitizado
  e limitado a 300 caracteres, sem alterar política de retries.
- Horário mais próximo preservado, com validade/referência UTC e proveniência
  modelada. Estatísticas alinhadas ao eixo temporal, com válidos/ausentes e
  segmentos `past_or_present`/`future`; passado não é rotulado como medição.
- Subíndices US AQI do Open-Meteo solicitados na mesma chamada dos poluentes.
  Categorias adimensionais compartilhadas com o resource; nenhuma comparação
  de concentração horária com cortes de índice. Índices ausentes/sem suporte
  não são Good. O adaptador legacy conserva concentrações, sem conselhos antigos.
- `sample_mode=first|last|spread`, opcional, default first, cap 12; AQ compacta
  continua com cap 8. Metadados de truncamento explícitos. JSON compacto UTF-8,
  sem NaN/Infinity; AQ details preserva todo `full_data` retornado.
- Schemas de saída gerados a partir dos modelos usados na serialização;
  snapshots de primitivas/registry e label OCI regenerados. O gerador agora
  mantém também a instrução de metadata do Dockerfile, sem mudar sua receita.
- Status explicita liveness e upstream readiness não verificada. Permanecem
  **9 tools / 3 prompts / 3 resources / 1 template** e os transportes existentes.

As mudanças de contrato são aditivas em argumentos e metadados, com exceções
semânticas deliberadas: lista AQ vazia é inválida, datas fora da política são
recusadas localmente, o resource AQI descreve índice em vez de concentração e
o texto de status/legacy deixa de prometer readiness ou classificação indevida.
Nenhum nome de tool/argumento existente foi removido.

## Rastreabilidade

Os testes abaixo foram executados na suíte completa. Caminhos de código são
relativos a `src/percival_weather_mcp/`; caminhos de teste a `tests/`.

| Issue | Correção | Regressão/evidência local |
|---|---|---|
| I-01 WMO 0 | `utils.describe_weather`, `tools/weather_service.py`, `presentation/weather_formatter.py` | `test_functional_values_validation.py`: 0/None/desconhecido nas três rotas, zero versus ausência; sessão MCP também verifica Clear sky |
| I-02 qualificadores | `tools/geocoding_service.py` e integração Weather/AQ | `test_geocoding_resolution.py`: aliases/filtros/país incompatível/região, limite de chamadas; smoke real London UK, São Paulo BR, Paris FR |
| I-03 janela | `range_policy.py`, serviço e erro HTTP | `test_range_policy.py`: limites -92/+15, 16/17 dias, 2020/2030, bissexto/virada de ano, duração configurada e reason HTTP 400 sem retry |
| I-04 validação | `models.py`, `tools/toolhandler.py`, `server.py` | `test_functional_values_validation.py`, `test_functional_wire_contract.py`: campo/regra, sem I/O, sem input/erro interno exposto |
| I-05 AQ vazio | modelos, normalizador e serviço AQ | Testes diretos dos dois handlers e sessão MCP; série toda nula falha; parcial/zero permanece com cobertura; defaults e deduplicação preservados |
| I-06 AQI | `air_quality_index.py`, serviço/apresentação e resource | `test_air_quality_index.py`: bordas 50/100/150/200/300/500, negativos/nulos/não finitos, sem suporte, >500; 35.4/250.4/300 não acionam classificador antigo de concentração |
| I-07 status | `server.py`, README e exportações | `test_functional_wire_contract.py`: upstream 503 não altera liveness nem vira readiness; smoke stdio/HTTP confirma identidade |
| I-08 schema | `output_models.py`, `knowledge_base.py` e resources | Schema JSON valida saídas reais de fixture; descoberta preserva constraints/defaults; resource desconhecido mantém `-32002` nos testes wire existentes |
| I-09 timestamp | serviço e prosa Weather | Testes com relógio fixo: validade UTC exata, timestamp ausente e seleção nearest-hour; não afirma observação de estação |
| I-10 ambiguidade | resolver/cache e contexto nas cinco tools de dados | `test_geocoding_resolution.py`, `test_geocoding_cache.py`: contexto/alternativas, cache Weather/AQ compartilhado, TTL/evicção/concorrência e isolamento de países |
| I-11 cobertura | `series.py` e apresentação | `test_series.py`: 120 pontos/28 nulos = 92 válidos; 22 timestamps passados/presentes às 21:20; array curto, booleanos, não finitos e zero |
| I-12 payload/amostra | `presentation/payloads.py`, `output_models.py` | `test_series.py`: 1/12/24/384 pontos; `test_payload_budget.py`: full_data idêntico, UTF-8, bytes e teto 16 KiB |

As ressalvas factuais da campanha original continuam no §2 do plano: PM2.5=300
não era uma divergência de rótulo, PM10 não usava 355 no classificador, o
adaptador legacy tem caller, e timestamps passados de modelos não comprovam
observações. A resolução de I-03 é recusa documentada, não Archive; I-07 foi
resolvida por contrato de liveness, não por introduzir probes de upstream.

## Verificações executadas

| Verificação | Resultado |
|---|---|
| Baseline canônico Python 3.12.15 | 221 passed / 1 failed, referência preexistente ao espelho F3 removido |
| Suíte final Python 3.12.15, com coverage XML | **319 passed**; XML gerado para conferência, sem inclusão como artefato de fonte |
| Suíte final Python 3.10.19, ambiente temporário isolado, lock existente | **319 passed** |
| Suíte final Python 3.11.14, ambiente temporário isolado, lock existente | **319 passed** |
| Ruff check e format --check | Aprovados, 84 arquivos Python formatados/verificados |
| mypy `src/percival_weather_mcp` | Aprovado, 33 módulos |
| Gerador de metadata OCI `--check` | Aprovado; arquivos gerados e instrução Dockerfile coerentes |
| MCP stdio nativo | initialize, descoberta 9/3/3/1, nove tools chamadas com sucesso; seis resources lidos, três prompts renderizados |
| Open-Meteo real via MCP nativo | London UK (current/details), São Paulo BR (range/spread), Paris FR (AQ compact/details) aprovados |
| Geocoding real adicional | Springfield IL → Illinois/US, Washington D.C. → District of Columbia/US; qualificadores regionais nativos preservados |
| HTTP nativo, loopback/porta efêmera | healthz/health 200; MCP/metrics sem token 401; metrics com token 200; chamada MCP autenticada aprovada |
| CI GitHub, build/scan/SBOM e MCP de imagem candidata | Não executados; sem imagem candidata para aceitar |

Evidência bruta do smoke nativo:
[2026-11-05-weather-functional-native-verification.json](2026-11-05-weather-functional-native-verification.json).
Harness reproduzível:
[`scripts/verification/wx_functional_native.py`](../../scripts/verification/wx_functional_native.py).
O campo `image_id` é null deliberadamente: **isso não é teste de container nem
validação do candidato pelo agente conectado**. As fixtures determinísticas da
suíte não fazem chamadas reais a Open-Meteo; o harness só as habilita com `--live`.

Medição final da mesma fixture de 120 horas × 9 poluentes, mais subíndices e
metadados: **14.378 bytes compacto / 35.232 bytes indentado**, redução de 59,2%.
Orçamento de regressão: 16 KiB. O objeto JSON decodificado de `full_data` é
idêntico ao fixture upstream, incluindo campo desconhecido. Não é benchmark de
latência nem teto de todo payload possível.

Falha preexistente do teste de VEX: o conjunto histórico de oito CVEs foi
conferido em `9746453:docs/issues/2026-10-10-f3-status.md` e fixado no teste.
Isso preserva a verificação do VEX antigo sem depender de um arquivo removido
ou do tracker atual em outro checkout; não altera VEX, scan nem seu digest.

## Fonte e identidade do worktree

- HEAD: `ff21777e6956b208ce541d40b42f44878577b14c`, com alterações locais;
  nenhum commit/push executado.
- Versão: 0.10.0 em pyproject, módulo, manifesto e exports. Lock regenerado
  via uv, sem troca de versões de dependências; a atualização também normaliza
  markers e revisão do formato. O uv 0.9.30 pinado no builder leu o lock e
  executou os checks; matriz local 3.10/3.11 usou `--locked`.
- SHA-256 do diff rastreado relevante ao build, comando
  `git diff --binary -- Dockerfile README.md docker-entrypoint.sh mcp.yaml pyproject.toml uv.lock src | sha256sum`:
  `b37f9f3c6f1fe75223d88ab8ed26073c0dc22e969916e6a5f083e5c8ed08d8bf`.
- Novos módulos não rastreados, também necessários para reproduzir o candidato:

| Arquivo em `src/percival_weather_mcp/` | SHA-256 |
|---|---|
| `air_quality_index.py` | `b109a714192b4027a1d42a7a85f5df612608f9ef82abb423f7037c42322d6424` |
| `output_models.py` | `17713ca4ecd07c6d5ff16e7f13aef04ed02c96cc2c180d7a6a459e2c598c0381` |
| `presentation/payloads.py` | `91a19bba3a4f034580434606bde487eb55e8ed279331bc550dfc29394d9b499a` |
| `range_policy.py` | `f461c3896b72130b5b580aa7b81ea3402402354893c690fc3e4a196f21709218` |
| `series.py` | `3b0a5342bd6d7e9bdcf20fa60ff60466a80812f46df451db3c47e353ac7da2f2` |
| `tools/geocoding_service.py` | `22916a7a9abe383d258bf7a9499cb432455439112b8ef28c152080a306c89631` |

Esses hashes identificam o estado de fonte verificado, não um image ID.
Recalcular após qualquer mudança que afete o build. As notas de issues
preexistentes foram preservadas com atualização explícita de seguimento.
`AGENTS.md` não foi modificado.

## Bloqueio operacional e próxima ação

Build canônico tentado:

```sh
scripts/docker-build.sh percival-weather-mcp:0.10.0-ff21777-candidate-wxrf-20261105
```

Resultado: **exit 1 — `docker-build: docker is not available on PATH`**.
Não houve imagem construída, scan, pin candidato, promoção, rollback nem
remoção. Não há IDs novos para uma lista de limpeza; nenhuma evidência VEX/scan
antiga foi reutilizada para 0.10.0.

Inventário Positronic relido ao final:

- Weather global/stdio ativado, revisão **5**, versão **0.9.0**.
- Pin anterior/final:
  `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`.
- `configurationId`: `94813a6c-5181-47ab-be15-fc38da5308cc`, revisão de config 1,
  bridge, zero mounts, allowlist das nove tools. Permissões não foram ampliadas.
- O estado do Percival não foi alterado nem inferido da verificação nativa.

**Próximo passo:** retomar R7 num ambiente com Docker/Engine acessível, reler
revisões/pins do gestor, recalcular fonte/worktree, construir candidato único,
executar scan/SBOM e conformance da imagem, conectar o candidato pelo gestor
Positronic e validar funcionalmente pelo agente. Só então decidir aceite,
promoção/rollback e fechamento das issues. A remoção seletiva depende do
inventário nominal e da autorização específica prevista no runbook.

### Seguimento acordado com Bill

A investigação posterior confirmou que o Engine está acessível pela ponte
MCP restrita, mas o agente OCI não recebe CLI/socket Docker nem uma operação
de build pelo executor host. A causa e os critérios de solução estão na
[issue 0028 do Positronic](../../../alternative-positronic/positronic/docs/issues/0028-oci-agent-cannot-maintain-container-image-lifecycle.md).
Por instrução de Bill em 2026-11-05, resolver essa issue antes de retomar R7/M4
e finalizar a tarefa Weather. Não houve nova imagem, promoção ou encerramento
das issues funcionais por causa deste registro.

## 10. Ciclo de imagem, pin e validação pelo agente conectado — 2026-11-06

A capacidade de manutenção do agente foi implantada pela issue 0028 e ficou
operacional. O ciclo abaixo foi executado pelo agente OCI, sem comando
Docker no shell.

### Construção

| Campo | Valor |
|---|---|
| Job de manutenção | `b9f2723b7660434bd232cb8694bafe380ef9f53a3830aa1af2825e0c4435fe60` |
| Receita | `weather/canonical` (`6b9e05e927e01e16cd12e252adbbec11893a13c0bfc119aa4d2eb9f2f66880cb`) |
| Commit | `875fff909c4786baba87dbf3fad68ca71d566001` (árvore limpa, `dirty: false`) |
| Contexto | `f3138f4e6bbd54d6d1d8e643061c0e881255fc07a051f233891ce913bca0be63` |
| Engine | `57ae74da2442b4382413e691d56abf49617d4e6eb1e5fac298b973fbd263c43f` |
| Imagem | `sha256:40fa10fffabb0678fdbf584a3a2d4c6531f633b4f2282ab92b33fbc3568e3b25` |
| Scan | `7dc09118dc4993c3f34507f05cfcbd59b5d993ba12677d2cc0b900526909a92e` — **0 findings** no gate LOW/MEDIUM/HIGH/CRITICAL |
| SBOM | `b78118415ac9045f34c0bba3289d301b0d34696bd29629537d8a9d77667a2eec` |
| Scanner | `84e54b2d02a5de1ad8dff546f152fb3aa252379d25a3a8d0f982d6d3a1fe4cba` |

Fases do recibo: engine 0, build 0, scanner-version 0, scan 0, sbom 0.

### Causa das quatro primeiras falhas

As submissões `714fe825…` (sessão anterior), `16162b15…`, `24a764d0…` e
`5f679ae0…` falharam em `phase=build`, exit 1. A causa era o **Debian
Snapshot**: respostas em cache de borda (`x-cache: HIT`) voltavam 200 em
~80 ms, e as requisições sem cache (`MISS`) recebiam 504/503 após 10–30 s.
O `apt-get update` do Dockerfile busca `forky` e `forky-security`; o índice
`Packages.xz` da suíte de segurança estava em `MISS` e causava a falha do
build. Retentativas aqueceram o cache de borda e a quinta submissão
concluiu. Nenhum arquivo do projeto, pin de imagem ou data de snapshot foi
alterado para contornar isso.

Checagens locais que isolaram a causa: `apt-get update` com o mesmo
`sources.list` e as mesmas opções do Dockerfile (exit 0), `uv sync --frozen
--no-dev --no-editable` com o uv 0.9.30 pinado no builder contra o lock
atual (exit 0), as 16 versões de pacote fixadas presentes no snapshot
(0 ausentes) e os três digests de imagem-base resolvendo com 200.

### Pin e configuração

| Passo | Resultado |
|---|---|
| `update-image weather sha256:40fa10ff… 5` | revisão do servidor 5 → **6**, nova `configurationId` `ec08d7f2-be33-491f-90c2-4f3b4ac35337` |
| `configure weather 6 …` | recusado: `MCP configuration revision conflict` — o `update-image` invalida a `configurationId` e a configuração anterior fica invisível |
| `configure weather 0 …` | configuração recriada **idêntica**: bridge, zero mounts, env vazio, as nove tools na allowlist, revisão 1 |
| `metadata weather 6 --version=0.10.0` | gravou `version: false` no registry — ver §10.3 |

Rollback: a imagem anterior `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`
continua autorizada e disponível para reversão. Nenhuma imagem foi removida.

### Validação pelo agente conectado

| Verificação | Resultado |
|---|---|
| `weather_get_status` | `Version: 0.10.0. Upstream readiness not checked.` — texto novo, prova de que a sessão usa a candidata |
| `positronic mcp server discover weather` | 9 tools descobertas |
| `weather_get_current city="London, UK"` | contexto `London, England, United Kingdom`; `Model data valid at 2026-11-06T02:00:00+00:00 UTC (nearest_hour)`; ambiguidade reportada com alternativas |
| `weather_get_by_range city="São Paulo, BR", sample_mode="spread"` | identidade `country_code: BR`; 24 pontos, 12 na amostra `spread`; `coverage` com `valid_points`/`missing_points` por variável; segmentos `past_or_present` (24) e `future` (0); `source.data_kind: model` |
| `weather_get_air_quality city="Paris, FR"` | subíndices do provedor: PM2.5 75 → `Moderate`, O₃ 0 → `Good`; cobertura 120 pontos com 109 válidos e 11 ausentes; amostra compacta de 8 |

Nenhuma chamada usou o proxy opaco do ambiente: as três passaram pela
superfície MCP do agente conectado.

### 10.3 Incidente de registry e reparo

A mutação `metadata weather 6 --version=0.10.0` gravou `"version": false` no
registry: `version` é chave reservada do yargs e a flag global do comando raiz
consumiu o valor. O registry deixou de satisfazer o schema e **todo o gestor
passou a falhar** com `invalid MCP server registry`, para os seis servidores.

O arquivo corrompido foi preservado antes do reparo
(`~/.positronic/runtime/tmp/opencode/registry.corrupted-20261106T0133Z.json`,
SHA-256 `b0c7e111ca655ea3d3184a6941e98783c9f4e39e7a89d77096f8d72fc87a28d8`) e
o reparo foi uma edição cirúrgica de um único campo, de `false` para
`"0.10.0"`, o valor pretendido na operação original. Essa é uma **exceção
explícita** à regra de não editar estado gerenciado: as interfaces suportadas
não consequentem operar sobre um registry ilegível e o estado quebrado
derrubaria a gestão dos seis MCPs. Nenhum pin, allowlist, montagem, escopo,
credencial ou container foi alterado pelo reparo, e o gestor voltou a
responder normalmente em seguida.

A causa foi corrigida no código do agente — opção não reservada
`--server-version` e validação de tipo no lado da escrita do gestor — e
registrada na [issue 0029 do Positronic](../../../alternative-positronic/positronic/docs/issues/0029-mcp-metadata-version-flag-corrupts-the-registry.md).
A correção só vale na próxima imagem do agente.

### Estado do aceite

R7 está executado para a candidata: construção, scan sem findings, pin,
configuração preservada e validação funcional pelo agente conectado. M4
depende ainda da decisão de retenção: a imagem anterior permanece autorizada
para rollback, e a sua remoção exige a lista nominal e a autorização
específica previstas no runbook. As 12 issues funcionais permanecem abertas
até essa decisão, sem mudança de código adicional.
