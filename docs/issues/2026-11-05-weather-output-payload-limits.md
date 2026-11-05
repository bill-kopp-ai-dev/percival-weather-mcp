# `weather_get_by_range` entrega apenas as 12 primeiras horas do período e `weather_get_air_quality_details` devolve payload de ~25 KB

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** baixa — duas limitações de contrato de saída que limitam o uso analítico das tools
- **Área:** formato de saída das tools de análise
- **Ferramentas afetadas:** `weather_get_by_range` (amostra), `weather_get_air_quality_details` (tamanho do payload)
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

Duas limitações observadas na camada de saída:

1. A amostra horária do intervalo de clima é sempre o **início** do período
   (12 horas a partir de 00:00 do `start_date`), independentemente de o
   período ser passado ou futuro. Não há forma de obter as horas mais
   recentes de um período, nem a série completa.
2. A variante de detalhes da qualidade do ar devolve as 120 horas × 9
   variáveis em JSON com indentação, o que produz um payload de cerca de 25 KB
   por chamada.

## Evidência

**(1)** `weather_get_by_range city="Berlin" start_date="2026-11-05"
end_date="2026-11-05"` — a amostra começa em 00:00 do dia, com o período
inteiro coberto por 24 pontos:

```json
"hourly_points": 24,
"hourly_sample": [ { "time": "2026-11-05T00:00", … }, { "time": "2026-11-05T01:00", … }, … ]
```

Para o intervalo de 16 dias `2026-11-05..2026-11-20` (384 pontos), a amostra
continua sendo as 12 primeiras horas do dia 05/11 — o resto do período não é
acessível por nenhuma tool.

**(2)** `weather_get_air_quality_details city="Berlin"` (variáveis estendidas)
devolve `full_data.hourly` com 120 timestamps e 9 arrays de 120 valores, mais
`hourly_units`, em JSON indentado com 2 espaços — com as unidades em escape
Unicode (`"\u03bcg/m\u00b3"`).

## Causa provável

- `src/percival_weather_mcp/utils.py:135` — `"hourly_sample": weather_data[:12]`,
  corte fixo no início da lista.
- `src/percival_weather_mcp/tools/tools_air_quality.py:170` —
  `json.dumps(response_data, indent=2)` sobre o payload bruto completo.

## Impacto

- Análises que exigem as horas mais recentes de um intervalo (ou o perfil
  horário, em vez das 12 primeiras) não são possíveis pela superfície MCP.
- O payload de ~25 KB por chamada de detalhes de qualidade do ar tem custo
  de contexto relevante para agentes, para um ganho pequeno frente à tool
  compacta — que já entrega resumo e amostra.

## Investigação necessária

1. Definir o contrato desejado da amostra: beginning, end, evenly spaced ou
   um parâmetro explícito (`sample=first|last|spread`) com padrão documentado.
2. Verificar se a tool de intervalo deve aceitar uma janela de "últimas N
   horas" (o que é a pergunta mais comum depois de "como está agora").
3. Oferecer a variante de detalhes com JSON compacto (sem `indent=2`) ou com
   uma seleção de campos/horas, mantendo `full_data` completo como opção
   explícita.
4. Medir o tamanho real do payload de detalhes (a medição desta bateria foi
   por observação do retorno, sem contagem de bytes exata).

## Critérios de resolução

- A documentação e a saída concordam sobre quantas horas a amostra contém e
  quais horas são.
- O agente consegue obter as horas mais recentes de um intervalo.
- A variante de detalhes tem custo de payload previsível e documentado.

## O que não foi verificado

- Não foi medido o payload em bytes com precisão (a estimativa vem da leitura
  do retorno).
- Não foi verificado se algum consumidor já depende da posição da amostra
  (as tools `weather_analysis` do prompt podem assumir o início do período).
