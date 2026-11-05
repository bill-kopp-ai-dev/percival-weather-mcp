# `weather_get_current` não informa o horário da observação

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** baixa — o snapshot é correto nos valores, mas o agente não consegue saber a idade do dado
- **Área:** formato de saída de `weather_get_current`
- **Ferramentas afetadas:** `weather_get_current`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

A tool "concise snapshot" devolve temperatura, umidade, vento, pressão,
precipitação, UV e visibilidade em prosa, mas não o instante da observação.
Como os dados são horários, o valor pode ser da hora anterior, corrente ou
até da próxima hora, e nada disso é visível na resposta.

## Evidência

```
weather_get_current city="Berlin"
→ The weather in Berlin is Unknown weather condition with a temperature of 4.7°C
  (feels like 2.4°C), relative humidity at 88%, and dew point at 2.9°C. Wind is
  blowing from the E at 4.7 km/h with gusts up to 11.2 km/h. Atmospheric pressure
  is 1030.5 hPa with 0% cloud cover. Visibility is 22.8 km.
```

A chamada ocorreu em 2026-11-05 ~21:16 UTC. O mesmo dado em
`weather_get_details` traz o carimbo:

```json
{ "time": "2026-11-05T21:00", "temperature_c": 4.7, … }
```

Ou seja, o instantâneo corresponde à hora 21:00 UTC — 16 minutos antes da
consulta, mas o texto não diz isso. Em `weather_get_details` o campo existe;
em `weather_get_current` ele é descartado no formatador.

## Causa provável

- `src/percival_weather_mcp/tools/weather_service.py:185-210` monta o
  campo `time` no payload do serviço.
- `src/percival_weather_mcp/presentation/weather_formatter.py:41-115`
  (`format_current`) não lê `time` ao montar o texto.

## Impacto

- Para uma pergunta do tipo "como está o tempo agora?", o agente não pode
  qualificar a resposta ("dado das 21:00 UTC") nem perceber que está
  olhando para a hora anterior em uma consulta feita logo após a virada.
- Em séries de consultas, o agente não consegue alinhar dois snapshots à
  mesma hora de observação.

## Investigação necessária

1. Incluir o horário da observação no texto (por exemplo, "as of 21:00 UTC") ou
   em um campo estruturado no retorno.
2. Decidir o fuso a exibir: o dado vem em GMT (`timezone=GMT` na chamada
   upstream), enquanto o usuário pode estar em qualquer fuso — o formato
   `weather_get_time`/`weather_get_timezone` existe para essa conversão.
3. Avaliar se o snapshot deve indicar que a hora escolhida é a mais próxima
   (e pode estar no futuro em até ~30 min).

## Critérios de resolução

- A resposta informa o instante da observação e o fuso.
- Regressão verificando que o texto inclui o timestamp.

## O que não foi verificado

- Não foi verificado se o formato em prosa é consumido por outro componente
  (a tool `weather_quick_answer` do prompt pode depender dele).
- Não foi verificado o comportamento no caso de o dado estar ausente
  (campo `time` nulo).
