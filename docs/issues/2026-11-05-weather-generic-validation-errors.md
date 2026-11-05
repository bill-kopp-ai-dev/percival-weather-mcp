# Detalhes de validação são descartados: todo erro de entrada vira "Invalid weather request"

- **Status:** correção implementada e validada localmente; aberta para aceite da imagem — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média — o servidor produz mensagens específicas e as substitui por texto genérico, tirando do agente a informação que ele precisa para se corrigir
- **Área:** taxonomia de erros da camada de tools
- **Ferramentas afetadas:** `weather_get_current`, `weather_get_details`, `weather_get_by_range`, `weather_get_air_quality`, `weather_get_air_quality_details`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

As mensagens de erro de entrada que o servidor constrói com cuidado —
"end_date must be on or after start_date", "Date range exceeds 16 days. Please
use a shorter interval", "City contains unsupported characters", "Unsupported
air quality variable: X" — nunca chegam ao agente. Todas viram a mesma frase
genérica, que não diz **qual** argumento estava errado nem **qual** é o limite.

## Evidência

```
weather_get_by_range city="Berlin" start_date="2026-11-05" end_date="2026-10-30"
→ Error: Invalid weather request. Check input values and try again.

weather_get_by_range city="Berlin" start_date="2026-11-01" end_date="2026-11-30"
→ Error: Invalid weather request. Check input values and try again.

weather_get_current city="São<Paulo>"
→ Error: Invalid weather request. Check input values and try again.

weather_get_air_quality city="Berlin" variables=["pm25"]   (barrado antes, no cliente)
```

O código-fonte mostra que a informação existia em dois níveis e foi perdida
em ambos:

| origem | mensagem real | o que o agente recebe |
|---|---|---|
| `weather_service.py:103` | `end_date must be on or after start_date.` | genérica |
| `weather_service.py:107-110` | `Date range exceeds 16 days. Please use a shorter interval.` | genérica |
| `utils.py:46` | `City contains unsupported characters.` | genérica |
| `tools_air_quality.py:52` | `Unsupported air quality variable: pm25` | genérica |
| `models.py:82` | `Dates must use YYYY-MM-DD format.` | genérica |

## Causa provável

Em `src/percival_weather_mcp/tools/tools_weather.py:121-125` (e equivalentes
em `:68-72`, `:183-187`) e em
`src/percival_weather_mcp/tools/tools_air_quality.py:114-118` (e `:181-185`),
o `except ValueError` do bloco de tool converte **qualquer** `ValueError` em
`InvalidRequestError("Invalid weather request. Check input values and try
again.")`.

Como a `ValidationError` do Pydantic herda de `ValueError`, erros de schema
(`pattern`, `min_length`, `max_length`) e erros de regra de negócio
(`end_date < start_date`, faixa > 16 dias) caem no mesmo caminho e perdem o
detalhe.

## Impacto

- O agente não sabe qual campo corrigir e tende a repetir a chamada com os
  mesmos valores, gastando chamadas e taxa contra o upstream.
- O limite de 16 dias — restrição real e documentada — não aparece em nenhum
  caminho observável, exceto na descrição do schema.
- A perda de detalhe também apaga a distinção entre entrada inválida e
  resultado vazio, o que é justamente a separação que a taxonomia de erros do
  projeto (`errors.py`) procura manter.

## Investigação necessária

1. Preservar a mensagem original no erro devolvido, com uma allowlist por
   tipo de falha conhecida (mensagens internas do pacote) e uma mensagem
   genérica apenas para `ValueError` de origem desconhecida.
2. Verificar se o `ValidationError` do Pydantic pode ser separado do
   `ValueError` de regra de negócio, para preservar também o nome do campo
   e o limite violado.
3. Padronizar o comportamento entre as cinco tools: hoje o texto genérico
   varia ("Invalid weather request", "Invalid air quality request") sem que
   isso traga informação.
4. Incluir o limite de 16 dias na mensagem de erro e na descrição da tool.

## Critérios de resolução

- Um intervalo invertido informa que `end_date` deve ser ≥ `start_date`.
- Uma faixa de 17+ dias informa o limite de 16 dias.
- Um caractere proibido no nome da cidade informa o que foi encontrado.
- Um `variables` inválido nomeia a variável rejeitada.
- Regressão por tool cobrindo ao menos um erro de schema e um de regra.

## O que não foi verificado

- Não foi verificado como o cliente MCP específico do gateway (Docker MCP
  Toolkit) apresenta o erro; aqui a mensagem chega pelo proxy, que a repassa
  sem alteração.
- Não foi verificado se `errors.py` já oferece um campo estruturado para o
  detalhe (a inspeção do módulo ficou fora desta bateria).
