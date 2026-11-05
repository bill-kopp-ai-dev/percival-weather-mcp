# Sumário mistura hora observada com hora prevista e não informa a contagem de pontos válidos

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** baixa-média — as estatísticas são calculadas sobre uma janela que mistura passado e futuro, e o payload sugere cobertura completa mesmo quando há buracos
- **Área:** semântica das janelas de dados e das estatísticas agregadas
- **Ferramentas afetadas:** `weather_get_air_quality`, `weather_get_air_quality_details`, `weather_get_by_range`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

A janela padrão de qualidade do ar é de 120 horas começando **hoje à 00:00
UTC**: 21 horas já observadas e 99 previstas. As estatísticas (`min`, `max`,
`avg`) são calculadas sobre a janela inteira, sem separar o que foi medido do
que é previsão, e o payload informa `hourly_points: 120` como se houvesse 120
pontos válidos para cada poluente — o que não é verdade.

## Evidência

`weather_get_air_quality city="Berlin"` (2026-11-05 ~21:20 UTC):

```json
{
  "current_air_quality": { "time": "2026-11-05T21:00", "pm10": 15.3, "pm2_5": 11.8, … },
  "summary": {
    "hourly_points": 120,
    "pollutants": {
      "pm2_5": { "min": 8.2, "max": 35.4, "avg": 17.66 },
      "ammonia": { "min": 0.2, "max": 3.6, "avg": 1.64 }
    }
  }
}
```

Na variante `details` (mesma cidade, variáveis estendidas), a série de
`ammonia` termina com **28 valores nulos** (de 2026-11-06T21:00 em diante),
enquanto as outras variáveis têm 120 valores:

```json
"ammonia": [ … 92 valores …, null, null, null, … (28 nulls) ]
```

A estatística de amônia (min 0.2 / max 3.6 / avg 1.64) foi calculada sobre os
~92 pontos válidos, mas nada no payload indica essa diferença: `hourly_points`
diz 120.

A mesma mistura ocorre em `weather_get_by_range`: um intervalo que termina
hoje contém observações até a hora corrente e previsão depois dela, com as
estatísticas calculadas sobre o conjunto.

## Causa provável

- `src/percival_weather_mcp/tools/air_quality_service.py:39-44` chama o
  upstream sem `past_days`/`forecast_days`, aceitando a janela padrão de 5
  dias.
- `src/percival_weather_mcp/utils.py:150-208` (`format_air_quality_data`)
  calcula as estatísticas com `_numeric_series`, que descarta silenciosamente
  valores não numéricos, e reporta `len(times)` como `hourly_points`.
- `src/percival_weather_mcp/utils.py:83-137` (`format_get_weather_bytime`)
  tem o mesmo desenho para o intervalo de clima.

## Impacto

- O agente não distingue "média medida" de "média prevista" — diferença
  material em qualquer análise de tendência.
- O `hourly_points` é lido como cobertura completa de cada poluente; com
  buracos, as estatísticas ficam sem denominador conhecido.
- Para poluentes com modelo mais curto (amônia), a diferença entre 92 e 120
  pontos é de ~23% da janela — o suficiente para distorcer uma leitura de
  tendência.

## Investigação necessária

1. Separar explicitamente o que é observado e o que é previsto na resposta
   (por exemplo, `observed_points` / `forecast_points`, ou uma marca por
   linha).
2. Informar a contagem de pontos válidos por poluente junto de cada estatística.
3. Marcar no payload quando a janela inclui previsão (e, no caso do intervalo
   de clima, indicar a fronteira "agora").
4. Verificar se o número de pontos válidos deve ser exposto também no
   `weather://schema/*`.

## Critérios de resolução

- O payload distingue valores observados de previstos.
- Cada estatística traz a contagem de pontos que a originou.
- Regressão para um poluente com cauda nula (ammonia).

## O que não foi verificado

- Não foi verificada a exata política de "pontos válidos" do modelo de amônia
  no upstream (a cauda nula observada sugere horizonte mais curto).
- Não foi verificado se o comportamento muda com `past_days`/`forecast_days`
  configuráveis.
