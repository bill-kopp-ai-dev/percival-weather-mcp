# Recurso `weather://schema/weather_get_by_range` descreve incorretamente o payload

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média-baixa — o recurso que existe para orientar o agente descreve a saída de forma incorreta em três pontos
- **Área:** recurso `weather://schema/{tool_name}`
- **Ferramentas afetadas:** `weather_get_by_range` (documentação via recurso; o prompt `weather_analysis` referencia este recurso em `src/percival_weather_mcp/prompts.py:135`)
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

O recurso que documenta a saída de `weather_get_by_range` afirma três coisas
que a saída real não confirma.

## Evidência

Conteúdo publicado do recurso:

```json
{
  "tool": "weather_get_by_range",
  "top_level_keys": [
    "city", "latitude", "longitude", "start_date", "end_date",
    "summary (avg/min/max temperature, total precipitation, ...)",
    "hourly_sample (compact hourly observations, capped to a few hundred entries)"
  ],
  "notes": "The range is inclusive and capped at 16 days. Dates outside this window raise a ValueError."
}
```

Saída real (intervalo de 7 dias, `city="Berlin"`, `2026-10-30..2026-11-05`):

```json
{
  "city": "Berlin", "latitude": 52.52437, "longitude": 13.41053,
  "period": { "start_date": "2026-10-30", "end_date": "2026-11-05", "hourly_points": 168 },
  "summary": {
    "temperature_c": { "min": 3.8, "max": 11.4, "avg": 7.73 },
    "apparent_temperature_c": { "min": 1.0, "max": 9.1, "avg": 5.5 },
    "precipitation_mm": { "min": 0.0, "max": 0.1, "avg": 0.0 },
    "wind_speed_kmh": { "min": 1.3, "max": 15.0, "avg": 6.37 },
    "uv_index": { "min": 0.0, "max": 2.15, "avg": 0.37 },
    "top_conditions": [["Overcast", 60], ["Partly cloudy", 40], ["Clear sky", 23]]
  },
  "hourly_sample": [ …12 entradas… ]
}
```

Divergências:

1. **`hourly_sample` não tem "a few hundred entries"**: o cap é **12** entradas
   (`src/percival_weather_mcp/utils.py:135` — `weather_data[:12]`), para
   qualquer intervalo, inclusive o de 16 dias (384 pontos). Confirmado nas
   respostas de 7 e de 16 dias.
2. **Não existe "total precipitation"**: o summary traz min/máx/média de
   `precipitation_mm`; a soma (total do período) não é calculada. Com
   `precipitation_mm` máximo de 0.1 mm e média 0.0 no exemplo, um agente que
   procure "total precipitation" não encontra o campo.
3. **"Dates outside this window raise a ValueError"** não descreve o
   comportamento: intervalo com mais de 16 dias produz um erro genérico
   ("Invalid weather request…"), e datas fora da janela de disponibilidade do
   upstream produzem um erro 400 do upstream (ver
   `2026-11-05-weather-range-outside-upstream-window.md`).
4. A chave `period` existe na saída e não está listada em `top_level_keys`.

## Causa provável

`src/percival_weather_mcp/knowledge_base.py:232-242` descreve o payload de
forma estática, escrita à mão e não derivada do formatador real
(`src/percival_weather_mcp/utils.py:83-137`).

## Impacto

- O agente que consulta o recurso para planejar a extração espera uma série
  horária grande e recebe 12 pontos; pode concluir que o intervalo veio
  truncado ou que a chamada falhou.
- A documentação do recurso é contradita pela documentação da tool e pelo
  README, cada um com números diferentes sobre o volume entregue.

## Investigação necessária

1. Gerar o conteúdo do recurso a partir do formatador real (ou adicionar
   teste que compare o recurso com a saída efetiva), para evitar divergência
   futura.
2. Corrigir o cap real (12) e as chaves (`period`, `summary.*`,
   `hourly_sample`).
3. Decidir se "total precipitation" deve existir na saída — se sim, incluir;
   se não, remover do texto do recurso.
4. Revisar os demais recursos (`weather://codes`, `weather://aqi`,
   `weather://timezones`) contra a saída real.

## Critérios de resolução

- O recurso descreve exatamente as chaves e os limites da saída real.
- Existe teste automatizado que falha quando o formato muda.
- As descrições do recurso, da tool e do README concordam entre si.

## O que não foi verificado

- Não foi verificado o comportamento do template com `tool_name` fora da
  lista documentada: `weather://schema/weather_get_current` falha com
  "Failed to read MCP resource: weather/weather://schema/weather_get_current",
  sem indicar os nomes válidos (a descrição do template lista os três).
