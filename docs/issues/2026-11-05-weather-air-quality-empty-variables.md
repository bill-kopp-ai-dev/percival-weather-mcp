# `variables: []` é aceito e devolve sucesso sem nenhum dado de poluente

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média — entrada vazia produz resposta bem-sucedida e sem conteúdo, que o agente pode interpretar como "qualidade do ar sem poluentes"
- **Área:** validação do argumento `variables` nas tools de qualidade do ar
- **Ferramentas afetadas:** `weather_get_air_quality`, `weather_get_air_quality_details`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

Uma lista `variables` vazia passa pela validação e produz uma resposta de
sucesso cuja única informação é o carimbo de tempo: nenhum poluente é
reportado, o dicionário `summary.pollutants` fica vazio e as linhas de
amostra contêm apenas `time`.

## Evidência

```
weather_get_air_quality city="Berlin" variables=[]
```

```json
{
  "city": "Berlin",
  "latitude": 52.52437,
  "longitude": 13.41053,
  "current_air_quality": { "time": "2026-11-05T21:00" },
  "summary": { "hourly_points": 120, "pollutants": {} },
  "hourly_sample": [
    { "time": "2026-11-05T00:00" },
    { "time": "2026-11-05T01:00" },
    …
  ]
}
```

A chamada **não** falha: o status é sucesso e o payload parece normal, apenas
vazio. Compare com o mesmo tool sem `variables` (conjunto padrão de 5
poluentes), que retorna valores.

## Causa provável

- `src/percival_weather_mcp/tools/tools_air_quality.py:29-54`
  (`_normalize_aq_variables`) valida tipo, tamanho máximo e pertencimento ao
  conjunto permitido, mas **não** rejeita lista vazia: `raw_variables == []` é
  uma lista válida e sobra como `[]`.
- Com a lista vazia, `src/percival_weather_mcp/tools/air_quality_service.py:31`
  monta `hourly=""` e o upstream responde 200 com a série temporal, mas sem
  nenhuma variável de poluente.
- `src/percival_weather_mcp/utils.py:186-208` monta a amostra horária por
  poluente, resultando em linhas só com `time`.

## Impacto

- Resposta vazia com sucesso é o pior modo de falha para um agente: ele pode
  concluir "sem poluentes" ou "sem dados de qualidade do ar" sem sinal de
  erro.
- Em fluxos automatizados, a ausência de poluente pode ser lida como "ar
  limpo" (o oposto de "indisponível").

## Investigação necessária

1. Rejeitar lista vazia na validação, com mensagem específica ("variables must
   contain at least one pollutant").
2. Verificar se o mesmo caminho é alcançável por duplicação/typo do cliente
   e se o caso "lista só com poluentes sem dado na região" (por exemplo,
   `dust` em uma área sem poeira) produz payload vazio equivalente.
3. Avaliar devolver um marcador explícito de "sem dados" quando a série vem
   sem variáveis, em vez de um objeto vazio.

## Critérios de resolução

- `variables: []` falha com erro de requisição claro.
- Nenhuma resposta bem-sucedida sai com `summary.pollutants` vazio.
- Regressão para lista vazia e para lista com poluentes sem dado local.

## O que não foi verificado

- Não foi verificado o comportamento de `weather_get_air_quality_details` com
  `variables: []` (caminho de código equivalente, não exercitado diretamente).
- Não foi verificado se o cliente MCP ou o proxy rejeita listas vazias antes
  de chegar ao servidor em outros clientes.
