# Bateria de testes do servidor MCP Weather — registro da campanha

- **Status da campanha original:** concluída — 2026-11-05; 12 issues registradas.
- **Seguimento:** correções implementadas em WX-RF; a candidata 0.10.0
  (`sha256:40fa10fffabb0678fdbf584a3a2d4c6531f633b4f2282ab92b33fbc3568e3b25`)
  foi construída, escaneada sem findings, pinada e validada pelo agente
  conectado em 2026-11-06, com as **nove** tools exercitadas contra a
  candidata pinada. Permanece a decisão de retenção da imagem anterior.
  O levantamento da cobertura do `scripts/smoke-container.sh` e do
  `scripts/docker-ci-conformance.py` está em §10.4 do
  [relatório de implementação](../plans/2026-11-05-weather-functional-implementation-report.md):
  a validação funcional cobre o contrato stdio e o comportamento das tools,
  mas não as propriedades de runtime do container.
- **Executado por:** agente `<positronic>`, a pedido do owner
- **Alvo:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee`
  (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem
  `f62d4383c89b63db7328bbbbb1a65846dff31531`), servida pelo Positronic em
  transporte `stdio`, revisão 5 do servidor, `configurationId`
  `94813a6c-5181-47ab-be15-fc38da5308cc`, escopo global
- **Janela:** 2026-11-05, ~21:00–21:35 UTC
- **Upstream:** Open-Meteo (geocoding, forecast, archive, air-quality), sem API key
- **Escopo do pedido:** identificar problemas; **não corrigir**

## Objetivo e método

Exercitar sistematicamente as 9 tools expostas pela imagem pinada, buscando
erros de valor, inconsistência entre tools, entradas de borda, semântica de
erro e divergência entre o que a documentação promete e o que o servidor
entrega.

Todas as chamadas foram feitas pela superfície MCP em execução (mesmo image
ID em uso pelo Percival). Para estabelecer causa raiz, o upstream foi
consultado diretamente com os mesmos parâmetros que o servidor usa, e o
código do checkout (`f62d438`) foi lido. `docker` não está disponível no
shell desta sessão, portanto não houve execução local do contêiner: as
afirmações sobre comportamento vêm do binário em produção via MCP, e sobre
causa raiz, do código-fonte da revisão de origem da imagem.

## Cobertura

| tool | casos exercitados | resultado |
|---|---|---|
| `weather_get_current` | cidade simples, com qualificador, inexistente, ambígua, com caracteres proibidos, vazia, com espaços múltiplos, minúscula, não-latina, com 200+ caracteres | 3 issues |
| `weather_get_details` | `include_forecast` on/off, consistência com `get_current`, payload | 1 issue (compartilhada com `get_current`) |
| `weather_get_by_range` | válido de 1/7/16 dias, invertido, mesmo dia, > 16 dias, passado distante, futuro distante, datas no limite do upstream | 2 issues |
| `weather_get_air_quality` | padrão, variáveis explícitas, variáveis duplicadas, lista vazia, cidade inexistente, poluente com cauda nula | 2 issues |
| `weather_get_air_quality_details` | variáveis estendidas, tamanho do payload | 1 issue (compartilhada) |
| `weather_get_time` | IANA válido, inválido, minúsculo, com espaço, linha do limite de tamanho | sem issue própria |
| `weather_get_timezone` | IANA válido, DST, offset, abreviação | sem issue própria |
| `weather_convert_time` | `'now'`, ISO com `Z`, ISO com offset, sem offset (interpretado em `from_timezone`), só data, formato inválido, `z` minúsculo, horário inexistente na transição DST, fusos iguais | sem issue própria |
| `weather_get_status` | resposta única | 1 issue |
| recursos | `weather://codes`, `weather://aqi`, `weather://timezones`, `weather://schema/{tool_name}` (3 nomes válidos + 1 inválido) | 1 issue |
| concorrência | 4 chamadas simultâneas com cidades distintas | sem falha |

## Issues registradas

| # | arquivo | severidade proposta | tema |
|---|---|---|---|
| 1 | `2026-11-05-weather-clear-sky-reported-as-unknown.md` | alta | código WMO 0 reportado como "Unknown weather condition" |
| 2 | `2026-11-05-weather-city-qualifier-format-fails.md` | alta | formato documentado "Cidade, País" falha; erro orienta para a forma que falha |
| 3 | `2026-11-05-weather-range-outside-upstream-window.md` | média-alta | intervalo sem validação da janela do upstream; 400 opaco; archive API não usada |
| 4 | `2026-11-05-weather-generic-validation-errors.md` | média | detalhes de validação descartados ("Invalid weather request") |
| 5 | `2026-11-05-weather-air-quality-empty-variables.md` | média | `variables: []` devolve sucesso sem poluentes |
| 6 | `2026-11-05-weather-aqi-bands-contradiction.md` | média | sem faixa de risco na saída; bands do recurso contradizem o classificador interno |
| 7 | `2026-11-05-weather-status-tool-not-a-health-check.md` | média-baixa | tool de status é texto estático |
| 8 | `2026-11-05-weather-schema-resource-range-inaccurate.md` | média-baixa | recurso `weather://schema/weather_get_by_range` descreve a saída incorretamente |
| 9 | `2026-11-05-weather-current-snapshot-without-timestamp.md` | baixa | snapshot sem horário da observação |
| 10 | `2026-11-05-weather-city-ambiguity-not-reported.md` | baixa | homônimos resolvidos em silêncio, sem país/região na saída |
| 11 | `2026-11-05-weather-summary-mixes-observed-and-forecast.md` | baixa-média | sumário mistura observado e previsto; sem contagem de pontos válidos |
| 12 | `2026-11-05-weather-output-payload-limits.md` | baixa | amostra fixa nas 12 primeiras horas; payload de detalhes ~25 KB |

## Achados que se confirmaram sadios

Registrado para evitar retrabalho e para delimitar o que **não** está quebrado:

- as três tools de tempo (fuso, offset, conversão) respondem corretamente,
  incluindo hora sem offset (interpretada em `from_timezone`), `Z`, data pura,
  horário inexistente na transição DST (resolvido sem aviso — limitação
  aceita, não registrada como issue) e fusos idênticos (diferença 0);
- o `weather_code` é mapeado corretamente pela tool de intervalo, o que
  isola a causa do issue 1 na camada de serviço;
- a normalização de entrada funciona: espaços extras, tabs e espaços nas
  pontas são normalizados ("New   York" → "New York");
- caracteres especiais são tratados como texto (nenhuma execução de
  comando: "Beijing; ls -la /etc" foi tratado como nome de cidade);
- a faixa de datas de 16 dias funciona nos dois sentidos (passado e futuro),
  inclusive exatamente no limite superior do upstream;
- chamadas concorrentes com cidades distintas não falharam;
- os três recursos estáticos são coerentes com a tabela interna de códigos
  WMO (mesmo conjunto de 28 códigos, apenas wording diferente).

## Não verificado

- execução local do contêiner (`docker` ausente no shell);
- transporte HTTP: `/healthz`, `/health`, `/metrics`, rate limiting e bearer
  token;
- os 3 prompts MCP (`weather_quick_answer`, `weather_analysis`,
  `weather_unit_conversion`): não expostos pela ferramenta de teste usada;
- comportamento sob indisponibilidade, 5xx, timeout e abertura do circuit
  breaker;
- medição precisa de latência e de tamanho de payload em bytes;
- caminhos de código alcançados apenas por cliente (o proxy desta sessão
  rejeitou `variables: ["pm25"]` antes do servidor).

> **Atualizado em 2026-11-06:** o transporte HTTP foi verificado **em fonte**
> (fixture nativa em loopback, sem bearer 401 e com token 200) e o contrato
> stdio foi verificado **na candidata pinada**, pelo agente conectado, com as
> nove tools. Continuam sem verificação **na imagem 0.10.0** as propriedades
> que exigem executar o contêiner: transportes HTTP, usuário efetivo,
> manifesto embutido e materialidade da label OCI. Ver §10.4 do relatório.

## Próxima ação

Executar o ciclo de imagem/gestor de R7 quando Docker estiver disponível.
As ressalvas factuais da campanha (AQI, proveniência modelada, contagens e
limites do proxy) estão registradas no §2 do plano WX-RF e no relatório de
implementação. As seções anteriores preservam o registro original da campanha,
não representam garantia atual nem aceite de runtime da versão 0.10.0.
