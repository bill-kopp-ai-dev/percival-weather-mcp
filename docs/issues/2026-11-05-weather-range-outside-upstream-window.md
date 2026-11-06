# Intervalo de datas sem validação da janela do upstream: erro HTTP 400 opaco, e o endpoint de arquivo histórico não é usado

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média-alta — a ferramenta aceita entradas que sempre falham no upstream, devolve um 400 sem causa e atribui a falha ao nome da cidade; histórico além de ~3 meses é recusado mesmo existindo endpoint próprio para isso
- **Área:** `weather_get_by_range` — validação de intervalo e janela de disponibilidade
- **Ferramentas afetadas:** `weather_get_by_range` (e, por extensão, qualquer agente que peça histórico)
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

A validação local da ferramenta cobre apenas a **extensão** do intervalo
(máximo de 16 dias). Ela não verifica a **posição** dele em relação a hoje.
Um intervalo de 7 dias em 2020 e outro em 2030 passam pela validação local e
morrem no upstream com HTTP 400, cuja mensagem é traduzida para texto que
atribui a falha ao nome da cidade.

## Evidência

```
weather_get_by_range city="Berlin" start_date="2020-01-01" end_date="2020-01-07"
→ Error: Upstream Open-Meteo weather forecast returned HTTP 400 (Bad Request).
  The request was rejected upstream; check the location name and the requested parameters.

weather_get_by_range city="Berlin" start_date="2030-01-01" end_date="2030-01-07"
→ Error: Upstream Open-Meteo weather forecast returned HTTP 400 (Bad Request). …
```

Corpo real da resposta do upstream (mesmos parâmetros do servidor):

```
GET https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41
    &hourly=temperature_2m&timezone=GMT&start_date=2020-01-01&end_date=2020-01-07
→ HTTP 400 {"reason":"Parameter 'start_date' is out of allowed range from 2026-08-04 to 2026-11-20",
            "error":true}
```

O mesmo dado histórico está disponível no endpoint de arquivo, que o servidor
nunca consulta:

```
GET https://archive-api.open-meteo.com/v1/archive?latitude=52.52&longitude=13.41
    &hourly=temperature_2m&timezone=GMT&start_date=2020-01-01&end_date=2020-01-07
→ HTTP 200 (série horária completa de 2020-01-01)
```

Casos que funcionam (16 dias, dentro da janela): `2026-10-20..2026-11-04`
(384 pontos) e `2026-11-05..2026-11-20` (384 pontos, no limite superior do
upstream).

## Causa provável

- `src/percival_weather_mcp/tools/weather_service.py:95-112`
  (`_validate_date_range`) valida formato, ordem e extensão, mas não a janela
  de disponibilidade do upstream (na data da bateria: 2026-08-04 a 2026-11-20,
  isto é, ~93 dias no passado e 15 dias à frente).
- `src/percival_weather_mcp/tools/weather_service.py:246-323`
  (`get_weather_by_date_range`) consulta sempre `BASE_WEATHER_URL`
  (`https://api.open-meteo.com/v1/forecast`, `:26`) e nunca o endpoint de
  arquivo, mesmo para datas históricas.
- `src/percival_weather_mcp/http_client.py:235-244` transforma o 400 em
  `UpstreamError`; o texto é gerado em `errors.upstream_http_error` e não
  carrega o corpo da resposta do upstream, que continha a causa exata.

## Impacto

- O agente recebe "check the location name" quando a cidade está correta e o
  problema é a data — diagnóstico que direciona a investigação para o lado
  errado.
- Chamadas que poderiam ser atendidas (histórico via archive) falham sempre.
- Como o 400 é não-recuperável (`is_retryable_status` em
  `http_client.py:62-68`), não há retry: cada chamada mal formulada é um
  erro definitivo.

## Investigação necessária

1. Definir a política de janela: ou validar localmente (passado ≤ N dias,
   futuro ≤ M dias) e devolver erro de requisição com a janela explícita, ou
   rotear datas históricas para `archive-api.open-meteo.com` e datas futuras
   para `forecast`.
2. Preservar a causa do upstream no erro: incluir o campo `reason` do corpo da
   resposta do 400 na mensagem sanitizada (sem dados sensíveis) ou, no mínimo,
   parar de sugerir o nome da cidade.
3. Documentar a janela disponível na descrição da tool e no recurso
   `weather://schema/weather_get_by_range`.
4. Verificar se a política deve ser configurável (variável de ambiente) e
   qual o padrão adequado para o uso do gateway.

## Critérios de resolução

- Intervalos fora da janela suportada falham localmente, com mensagem que
  informa a janela válida e não atribui o erro à cidade.
- Intervalos históricos dentro da janela do endpoint de arquivo são atendidos
  (ou a recusa é explícita e documentada).
- A mensagem de erro para HTTP 400 do upstream não menciona o nome da cidade
  quando a causa é a data.
- Regressão cobre: intervalo no passado distante, no futuro distante, no
  limite exato e dentro da janela.

## O que não foi verificado

- Não foi verificado o comportamento quando o upstream está degradado (5xx),
  que segue caminho de retry distinto.
- Não foi verificado se `past_days`/`forecast_days` offers do upstream
  alterariam a janela observada.
- Não foi verificado o comportamento do circuit breaker de geocoding sob
  repetição de erros.
