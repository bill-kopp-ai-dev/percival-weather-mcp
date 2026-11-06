# Resolução silenciosa de cidades ambíguas: o resultado não informa país ou região

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** baixa — o servidor escolhe um entre muitos homônimos e não expõe o contexto da escolha
- **Área:** geocoding — seleção de resultado e metadados de saída
- **Ferramentas afetadas:** todas as que recebem `city`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

O geocoding do upstream retorna vários candidatos para nomes ambíguos. O
servidor usa `results[0]` e devolve apenas latitude/longitude, sem país ou
região. O agente recebe dados meteorológicos corretos de **uma** cidade, mas
não tem como saber qual — nem detectar que a escolha é ambígua.

## Evidência

Consulta direta ao upstream com `count=5` para "Springfield":

```
Springfield, Missouri,  United States, 170188
Springfield, Illinois, United States, 114394
Springfield, Massachusetts, United States, 154341
Springfield, Ohio,      United States,  59680
Springfield, Tennessee, United States,  16808
```

Pelo servidor, `city="Springfield"` resolve para Missouri
(`latitude 37.21533`, `longitude -93.29824`) — o primeiro resultado, sem
qualquer indicação de que há outros quatro. O payload traz só:

```json
{ "city": "Springfield", "latitude": 37.21533, "longitude": -93.29824, … }
```

E `city="Springfield, IL"` resolve corretamente para Illinois (12.8 °C,
dados distintos), o que mostra que a desambiguação por qualificador funciona
**quando o formato é aceito** (ver
`2026-11-05-weather-city-qualifier-format-fails.md`).

Observação correlata: o upstream ordena por população, então "Springfield"
devolve Missouri (170k) e não Massachusetts (154k) — a escolha é razoável,
mas implícita.

## Causa provável

- `src/percival_weather_mcp/tools/weather_service.py:85-89` lê
  `results[0]` e guarda apenas `latitude`/`longitude` no cache
  (`http_client.py:272-315`).
- O payload de saída (`weather_service.py:185-210` e `:316-322`) não inclui
  `country`, `admin1` nem `timezone`, que o upstream já devolve.

## Impacto

- Para perguntas sobre homônimos, o agente responde sobre a cidade "certa"
  sem saber qual escolheu — e não pode avisar o usuário de que a ambiguidade
  foi resolvida por população.
- Sem `timezone` no payload, o agente também não consegue relate o horário
  local a partir de uma resposta de clima.

## Investigação necessária

1. Expor no payload os metadados de contexto do resultado: `country`,
  `country_code`, `admin1`, `timezone` e a feature (`feature_code`).
2. Definir a política de desambiguação: manter "primeiro por população" ou
   sinalizar ambiguidade quando há mais de um candidato com o mesmo nome
   (por exemplo, `ambiguous: true` + lista de candidatos).
3. Verificar se o cache de geocoding deve guardar também esses metadados
   (hoje guarda só a tupla de coordenadas).

## Critérios de resolução

- A resposta identifica país e região da cidade medida.
- A ambiguidade é detectável pelo agente.
- Teste cobre um nome ambíguo e um nome inequívoco.

## O que não foi verificado

- Não foi verificado o critério exato de ordenação do upstream além da
  observação de população nesta amostra.
- Não foi verificada a existência de ambiguidades além de homônimos
  (por exemplo, nomes idênticos em países diferentes).
