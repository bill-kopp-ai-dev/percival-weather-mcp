# Classificação da qualidade do ar ausente nas tools e bands de AQI contraditórios com o classificador interno

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média — o agente recebe concentração bruta sem faixa de risco, e as duas fontes de verdade do repositório discordam entre si
- **Área:** semântica de qualidade do ar (faixas AQI/WHO) e consistência entre recurso, classificador interno e tools
- **Ferramentas afetadas:** `weather_get_air_quality`, `weather_get_air_quality_details`; recurso `weather://aqi`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

**Ressalva da triagem de execução:** PM2.5=300 é Hazardous nas duas versões
originais; as divergências reais incluem 35.4 e 250.4. PM10 usa a fronteira
424/425, não 355 no classificador. O adaptador legacy tem caller em
`AirQualityService.format_response`. A evidência original abaixo fica preservada,
com essas interpretações superadas conforme §2 do plano WX-RF.

As tools de qualidade do ar devolvem apenas concentrações numéricas, sem
faixa de risco nem recomendação. O servidor, porém, publica o recurso
`weather://aqi` com faixas WHO 2021/EPA e mantém um classificador interno
(`_pm25_level`, `_pm10_level`, `_health_advice`) com conselhos de saúde. O
classificador interno não é alcançável por nenhuma tool, e as duas tabelas de
faixas **não coincidem**.

## Evidência

Saída real de `weather_get_air_quality city="Berlin"` — sem faixa, sem
classificação, sem conselho:

```json
{
  "current_air_quality": {
    "time": "2026-11-05T21:00", "pm10": 15.3, "pm2_5": 11.8, "ozone": 25.0,
    "nitrogen_dioxide": 25.3, "carbon_monoxide": 235.0, "sulphur_dioxide": 2.5,
    "ammonia": 2.5, "dust": 0.0, "aerosol_optical_depth": 0.07
  },
  "summary": { "hourly_points": 120, "pollutants": { "pm2_5": { "min": 8.2, "max": 35.4, "avg": 17.66 }, … } }
}
```

Recurso `weather://aqi` (bands de `pm2_5`): 0–12 "Good", 12.1–35.4
"Moderate", 35.5–55.4 "Unhealthy for Sensitive Groups", 55.5–150.4
"Unhealthy", 150.5–250.4 "Very Unhealthy", 250.5–500.4 "Hazardous".

Classificador interno (`AirQualityFormatter._pm25_level`): ≤12 "Good", ≤35
"Moderate", ≤55 "Unhealthy for Sensitive Groups", ≤150 "Unhealthy", ≤250
"Very Unhealthy", >250 "Hazardous".

Consequências observáveis:

- **Contradição de rótulo:** uma concentração de PM2.5 = 300 µg/m³ é
  "Very Unhealthy" pelo recurso (`250.5–500.4`) e "Hazardous" pelo
  classificador interno (>250). O `pm10` tem o mesmo padrão de divergência
  (recurso: Hazardous a partir de 425; interno: a partir de 355).
- **Faixas mortas no recurso:** os limites não são contíguos
  (12 → 12.1, 35.4 → 35.5, 55.4 → 55.5, 150.4 → 150.5, 250.4 → 250.5). Um
  valor como 35.45 µg/m³ não pertence a nenhuma faixa do recurso.
- **Conselho de saúde inacessível:** `_health_advice` existe em
  `src/percival_weather_mcp/presentation/air_quality_formatter.py:41-60` e é
  usado apenas por `format_legacy` (`:80-91`), que nenhuma tool chama.
- Nenhuma tool nem o `README.md` orienta o agente a consultar `weather://aqi`
  ao receber as concentrações.

## Causa provável

- `src/percival_weather_mcp/tools/tools_air_quality.py:100-109` e `:162-170`
  montam a resposta com `current_air_quality` (números) e `full_data`
  (bruto) e chamam `AirQualityFormatter.format_comprehensive`, que delega a
  `src/percival_weather_mcp/utils.py:140-210` — nenhuma das duas rutas
  classifica os valores.
- `src/percival_weather_mcp/knowledge_base.py:53-140` (aqi_table, tabela do recurso
  `weather://aqi`) e
  `src/percival_weather_mcp/presentation/air_quality_formatter.py:18-38`
  (classificador) são duas fontes de verdade independentes, com breakpoints
  diferentes.

## Impacto

- O agente precisa classificar a concentração por conta própria, com
  matemática de faixas e risco de errar o rótulo — trabalho que o servidor
  já faz e não expõe.
- Quem consultar o recurso recebe um rótulo diferente do que a lógica
  interna do produto usaria: confiança indevida em uma das duas fontes.
- O recurso, que é a interface pública de referência, tem faixas mortas que
  podem deixar um valor sem classificação.

## Investigação necessária

1. Definir uma única tabela de faixas (WHO 2021 / EPA) como fonte de verdade e
   fazer recurso e classificador derivarem dela.
2. Expor a classificação no payload de `weather_get_air_quality`
   (por poluente: faixa + conselho), ou instruir explicitamente a tool a
   consultar `weather://aqi`.
3. Fechar as faixas mortas (usar `min`/`max` contíguos ou declarar
   explicitamente a regra de borda e semiabertos).
4. Decidir o destino de `format_legacy` (código morto) e do `_health_advice`.
5. Verificar se `dust`, `ammonia` e `aerosol_optical_depth` devem ter faixas
   próprias — hoje o recurso não as cobre, embora as tools as retornem.

## Critérios de resolução

- Recurso e classificador interno produzem o mesmo rótulo para os mesmos
  valores.
- Nenhum valor de concentração fica sem classificação por lacuna nas faixas.
- A tool de qualidade do ar entrega faixa e recomendação, ou aponta
  explicitamente o recurso a consultar.
- Regressão com valores de borda (12.0, 12.05, 35.4, 35.45, 250.4, 300).

## O que não foi verificado

- Não foi verificado o comportamento do servidor HTTP (`/metrics`, `/health`)
  nesse aspecto.
 - Não foi validado o texto dos conselhos de saúde contra a fonte original
   WHO 2021; a verificação aqui foi de consistência interna.
