# O formato de cidade documentado "Cidade, País" falha, e a mensagem de erro recomenda justamente a forma que falha

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** alta — os exemplos publicados no schema, no README e nos prompts do produto falham, e o erro orienta o agente para uma correção que não resolve
- **Área:** geocoding (resolução de cidade) e texto de erro de "cidade não encontrada"
- **Ferramentas afetadas:** todas as que recebem `city` — `weather_get_current`, `weather_get_details`, `weather_get_by_range`, `weather_get_air_quality`, `weather_get_air_quality_details`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

A documentação do produto recomenda o formato `Cidade, País` para
desambiguar, com os exemplos `"London, UK"` e `"São Paulo, BR"`. Esses dois
exemplos — e o comando de smoke test do próprio README — **não localizam a
cidade**. A mensagem de erro devolvida recomenda "adicionar um qualificador de
país/região", que é exatamente o passo que continua falhando.

## Evidência

Falhas (mensagem literal do servidor):

```
weather_get_current city="London, UK"     → No location found for city 'London, UK' …
weather_get_current city="São Paulo, BR"   → No location found for city 'São Paulo, BR' …
weather_get_current city="Lisbon, UK"      → No location found for city 'Lisbon, UK' …
weather_get_current city="Berlin Germany"  → No location found …
weather_get_current city="Tokyo Japan"     → No location found …
```

Sucessos, com o mesmo formato de entrada:

```
"Lisbon, Portugal" ✓   "Berlin, Germany" ✓   "Paris, France" ✓
"São Paulo, Brazil" ✓  "New York, US" ✓      "Tokyo, JP" ✓
"London, England" ✓   "London, GB" ✓        "Springfield, US" ✓
"Washington, D.C." ✓  "Berlin" ✓            "São Paulo" ✓
```

Verificação direta no upstream (mesmos parâmetros que o servidor usa:
`name`, `count=1`, `language=en`, `format=json`):

| consulta | resultado |
|---|---|
| `name=London, UK` | HTTP 200, sem `results` |
| `name=London, GB` | HTTP 200, London/England/United Kingdom |
| `name=São Paulo, BR` | HTTP 200, sem `results` |
| `name=Sao Paulo, Brazil` | HTTP 200, São Paulo/Brazil |
| `name=Paris, FR` | HTTP 200, sem `results` |

Ou seja: o upstream aceita o qualificador apenas para um vocabulário
inconsistente (nome completo do país costuma funcionar; código de duas letras
funciona para `US`, `JP`, `GB`, mas não para `UK`, `BR`, `FR`).

O comando de verificação publicado no `README.md:142` é afetado:

```
percival-weather-mcp_weather_get_current city="Lisbon, UK"
→ Error: No location found for city 'Lisbon, UK' …
```

Outros pontos que publicam o formato quebrado:

- `src/percival_weather_mcp/models.py:25,27,36,39,150` — exemplos `"London, UK"`,
  `"São Paulo, BR"`;
- `docs/tools.json:222,233,235,375` — snapshot publicado das ferramentas;
- `src/percival_weather_mcp/prompts.py:45-46,55` — prompts `weather_quick_answer`
  e `weather_analysis`.

## Causa provável

- `src/percival_weather_mcp/tools/weather_service.py:62-73` envia a string
  inteira como `name` para o geocoder, sem separar o qualificador. O
  resultado depende, portanto, do vocabulário do upstream, que é inconsistente
  e não está documentado em lugar nenhum.
- `src/percival_weather_mcp/tools/weather_service.py:80-83` compõe a mensagem
  de `NoDataError` com a dica "add a country/region qualifier", sugerida sem
  qualquer verificação de que a forma sugerida funcione.

## Impacto

- Falha imediata no primeiro uso por qualquer agente que siga os exemplos
  publicados — inclusive o smoke test do README.
- O agente tende a tentar novamente com o mesmo formato ("São Paulo, Brazil" em vez
  de "São Paulo, BR"), gastando chamadas até acertar por tentativa.
- A mensagem de erro ensina um padrão que falha em casos frequentes, o que
  produz laços de tentativa em agentes e ruído desnecessário contra um
  upstream público e limitado por taxa.

## Investigação necessária

1. Definir e documentar o formato suportado. Opções a avaliar: separar o
   qualificador no servidor e passá-lo como filtro de país/estado sobre os
   resultados (`count>1`), ou normalizar o qualificador para o nome completo do
   país antes de consultar o upstream.
2. Corrigir a mensagem de "cidade não encontrada": deixar de recomendar uma
   forma não verificada e listar os formatos que de fato funcionam
   (ex.: `Cidade`, `Cidade, NomeCompletoDoPaís`, `Cidade, US`).
3. Corrigir os exemplos em `models.py`, `docs/tools.json`, `prompts.py` e no
   `README.md`, e alinhar o comando de smoke test a um caso que funcione.
4. Validar o comportamento para nomes de país em português (o operador e o
   público-alvo escrevem "Alemanha", "Japão", "Brasil") — o upstream com
   `language=en` não resolve "Berlin, Alemanha".
5. Considerar expor país/região no payload de saída (ver
   `2026-11-05-weather-city-ambiguity-not-reported.md`).

## Critérios de resolução

- Todos os exemplos publicados nas ferramentas, nos prompts, no snapshot
  `docs/tools.json` e no README resolvem para a cidade pretendida.
- A mensagem de cidade não encontrada é acionável e não indica formas que
  falham.
- Testes cobrem: nome simples, `Cidade, NomeCompletoDoPaís`, `Cidade, US`,
  qualificador inexistente e nome em português.
- Nenhuma alteração de pin/configuração do MCP é necessária para o efeito.

## O que não foi verificado

- Não foi testado o geocoder em outros idiomas (`language=pt` etc.), pois o
  servidor fixa `language=en`.
- Não foi verificado o comportamento do cache de geocoding diante de entradas
  que falham (a falha não é cacheada, pelo código).
- Não foi verificado o comportamento sob indisponibilidade do geocoder.
