# WX-RF — implementação funcional e verificação local

**Data:** 2026-11-05. **Owner:** Bill Kopp. **Candidato de fonte:** 0.10.0.

**Resultado:** R0–R6 implementados e validados localmente. Os 12 achados têm
correção e regressão. R7/M4 estão **parciais e bloqueados para aceite de imagem**:
Docker CLI não está disponível neste ambiente. Nenhuma issue foi encerrada
como resolvida em produção; nenhum pin foi atualizado.

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
