# `weather_get_status` devolve texto estático, não um health check

- **Status:** correção implementada; candidata 0.10.0 construída, escaneada sem findings, pinada e validada pelo agente conectado; aberta para a decisão de retenção — [WX-RF](../plans/2026-11-05-weather-functional-implementation-report.md)
- **Reportado em:** 2026-11-05
- **Severidade proposta:** média-baixa — a tool promete "status operacional" e o README a classifica como "Liveness/readiness", mas ela não verifica nada; em transporte stdio não existe outro sinal de saúde
- **Área:** tool de status e coerência com os endpoints `/healthz` e `/health` do modo HTTP
- **Ferramentas afetadas:** `weather_get_status`
- **Alvo testado:** imagem `sha256:680872039a8f530f7feb53610478087c5271d5a5aec451c1f668f799e0e8a0ee` (tag `percival-weather-mcp:0.9.0-f62d438`, revisão de origem `f62d4383c89b63db7328bbbbb1a65846dff31531`), transporte `stdio`

## Sintoma

`weather_get_status` responde sempre a mesma frase, com nome e versão, sem
qualquer verificação de dependência. Em transporte `stdio` — o modo em que o
servidor roda no gateway — essa é a única superfície de status disponível
para o agente.

## Evidência

```
weather_get_status
→ Percival Weather MCP Server operational. Name: percival-weather-mcp Version: 0.9.0
```

A resposta é idêntica em qualquer estado. O código confirma:

- `src/percival_weather_mcp/server.py:299-309` — a tool é uma função que
  concatena constantes (`SERVER_NAME`, `__version__`); não há I/O, nem
  probe, nem cache de estado.
- O `README.md` (tabela "Status") descreve a tool como "Liveness/readiness —
  name and version of the running server"; readiness, no sentido usual, inclui
  a capacidade de atender as dependências.
- O modo HTTP tem probes reais (`/healthz`, `/health`, `/metrics` em
  `src/percival_weather_mcp/server.py:441-490`), mas eles não existem no
  modo stdio.

## Causa provável

A tool foi implementada como um espelho do `serverInfo` do handshake MCP
(mesma informação de versão), sem um caminho de verificação de prontidão
aproveitado no modo stdio.

## Impacto

- Um agente ou operador não consegue distinguir "servidor vivo" de "servidor
  vivo mas sem Open-Meteo" — a falha de dependência só aparece na primeira
  chamada de dados, como erro de requisição.
- A descrição e a tabela do README prometem um sinal de prontidão que não
  existe, o que induz à leitura de que a tool é mais informativa do que é.

## Investigação necessária

1. Definir o que a tool deve checar: versão/config do processo, ou também a
   conectividade com o upstream (com um probe leve e cacheado, para não
   duplicar chamadas ao Open-Meteo a cada consulta de status).
2. Se permanecer como espelho de versão, renomear/reformular a descrição e a
   linha do README para dizer exatamente o que ela informa.
3. Verificar se existe endpoint equivalente acessível em stdio (por exemplo,
   via `prompts`/`resources`) ou se vale expor `weather://health`.

## Critérios de resolução

- A descrição da tool e a linha do README correspondem ao comportamento real.
- Ou a tool passa a reportar um estado de prontidão verificável, ou o texto
  deixa de prometer readiness.
- Teste cobre o estado saudável e um estado de dependência indisponível (por
  simulação).

## O que não foi verificado

- Não foi verificado o comportamento dos endpoints `/healthz` e `/health` no
  modo HTTP: `docker` não está disponível nesta sessão e o servidor foi
  exercitado apenas via stdio.
- Não foi verificado se o gateway Docker MCP Toolkit usa a tool de status para
  decidir o estado do contêiner.
