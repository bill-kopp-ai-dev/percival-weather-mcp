# Céu limpo (WMO 0) é reportado como "Unknown weather condition"

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** alta — a condição mais frequente do conjunto de dados é reportada como desconhecida na ferramenta mais usada
- **Área:** mapeamento de `weather_code` → descrição textual
- **Ferramentas afetadas:** `weather_get_current`, `weather_get_details` (bloco `current` e array `forecast`)
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

Quando o código WMO da hora corrente é `0` (céu limpo), o campo
`weather_description` recebe a string `"Unknown weather condition"` em vez de
`"Clear sky"`. O mesmo dado, lido pela ferramenta de intervalo, sai correto —
o defeito está na camada de serviço compartilhada e se manifesta de forma
inconsistente entre ferramentas.

## Evidência

`weather_get_current` com `city="Berlin"` (2026-11-05 ~21:16 UTC):

> The weather in Berlin is **Unknown weather condition** with a temperature of 4.7°C (feels like 2.4°C), … Atmospheric pressure is 1030.5 hPa with **0% cloud cover**. Visibility is 22.8 km.

`weather_get_details` com `city="Berlin"` (mesma hora):

```json
{
  "time": "2026-11-05T21:00",
  "weather_code": 0,
  "weather_description": "Unknown weather condition",
  "cloud_cover_percent": 0,
  "precipitation_mm": 0.0
}
```

`weather_get_by_range` com `city="Berlin"`, `start_date=2026-11-05`,
`end_date=2026-11-05` — o mesmo código `0` aparece corretamente:

```json
{
  "time": "2026-11-05T02:00",
  "weather_code": 0,
  "weather_description": "Clear sky",
  "cloud_cover_percent": 0
}
```

Reproduzido com pelo menos quatro cidades na janela de teste: Berlin
(`weather_code` 0), Springfield US (0), Madrid (0) e Oslo (0). Todas
reportaram "Unknown weather condition" com cobertura de nuvem 0%.

## Causa provável

Em Python, `0` é falsy. O serviço usa o valor do código como sentinela de
"ausente":

- `src/percival_weather_mcp/tools/weather_service.py:194-198` (bloco `current`)
  e `:222-225` (bloco `forecast`) usam
  `utils.weather_descriptions.get(_value("weather_code", …) or -1, …)`;
- `src/percival_weather_mcp/tools/weather_service.py:295-298` (intervalo) usa
  `weather_code if weather_code is not None else -1` — a forma correta, que
  explica a diferença de comportamento observada.

Quando `weather_code` é `0`, `0 or -1` avalia `-1`, que não existe na tabela
`utils.weather_descriptions` (`src/percival_weather_mcp/utils.py:236-265`) e
cai no texto padrão "Unknown weather condition".

O defeito atinge o array `forecast` de `weather_get_details` pelo mesmo
caminho, e o texto em prosa de `weather_get_current` apenas reflete o valor já
errado (`src/percival_weather_mcp/presentation/weather_formatter.py:73`).

## Impacto

- O agente recebe a condição errada justamente no caso mais comum (céu limpo),
  que corresponde a boa parte das horas diurnas em cidades de clima seco.
- A leitura errada pode ser propagada como erro do usuário ("está nublado"
  quando o dado diz 0% de nuvem) ou gerar alerta falso/omissão de alerta.
- Como o defeito depende do valor, ele é **intermitente por natureza**: um
  teste que roda em hora nublada passa e não detecta a regressão.

## Investigação necessária

1. Corrigir o tratamento de sentinela em `weather_service.py` (`:194-198`,
   `:222-225`) usando `is not None`, alinhando com `:295-298`.
2. Adicionar teste de regressão que fixe `weather_code = 0` → "Clear sky" em
   `weather_get_current`, `weather_get_details` (bloco `current` e `forecast`)
   e `weather_get_by_range`.
3. Auditar os demais usos de `or` como sentinela numérica no pacote
   (`utils.py`, `presentation/*`, `tools/*`) e verificar se algum outro zero
   legítimo é convertido em ausência.
4. Verificar se a tabela `utils.weather_descriptions` e o recurso
   `weather://codes` continuam alinhados (ver issue
   `2026-11-05-weather-schema-resource-range-inaccurate.md` para o caso
   análogo de documentação).

## Critérios de resolução

- `weather_code = 0` produz "Clear sky" em todas as ferramentas de clima.
- O array `forecast` não apresenta "Unknown weather condition" para código 0.
- Teste de regressão cobre o valor 0 nos três caminhos de saída.
- Nenhuma alteração de pin/configuração do MCP é necessária para o efeito.

## O que não foi verificado

- Não foi executado o container localmente: `docker` não está disponível no
  shell desta sessão, então a análise é sobre o binário em execução via
  Positronic (mesmo image ID) e sobre o código do checkout, que é a revisão de
  origem da imagem.
- Não foi verificado o comportamento do log de eventos/observabilidade para
  esses casos.
- Não foi verificado se o defeito já foi corrigido em alguma branch posterior
  à revisão `f62d438`.
