# Decisão — política de autenticação dos endpoints HTTP

**Data:** 2026-10-28
**Status:** vigente
**Decisor:** bill (owner do `percival-weather-mcp`)
**Registrado por:** agente `<positronic>`, durante a campanha stage-2 (S2-WX)
**Achado de origem:** F-016 / ação A-011 do
[plano de remediação stage-2](../../docs/plans/2026-10-27-stage-2-remediation-plan.md)

## Contexto

O servidor expõe três endpoints HTTP fora do middleware de autenticação:
`/healthz`, `/health` e `/metrics`. O bypass foi deliberado — está descrito
no `README.md` e no `docs/docker-mcp-packaging.md` — para que orquestradores
e coletores pudessem sondá-los sem possuir o token.

A observação do diagnóstico (F-016) foi que o efeito prático é mais largo
que o pretendido:

- qualquer cliente que alcance a porta lê a versão do produto e o uptime sem
  credencial;
- `/metrics` expõe contadores operacionais (chamadas de tool, requisições e
  erros ao upstream) sem credencial;
- `/metrics` nasce **vazio**: os labels Prometheus só existem após o primeiro
  incremento, o que costuma ser lido como "métricas quebradas".

## Decisão

**`/healthz` e `/health` permanecem sem autenticação. `/metrics` passa a
exigir o bearer token sempre que um token estiver configurado.**

Justificativa por endpoint:

| Endpoint | Antes | Decisão | Motivo |
|---|---|---|---|
| `/healthz`, `/health` | aberto | **aberto** | Probe de liveness. Expõe apenas nome, versão e uptime — o mesmo dado que o `serverInfo` do handshake MCP já publica — e é usado por orquestradores que não recebem o token. |
| `/metrics` | aberto | **token obrigatório** | Contadores operacionais: volume de chamadas, tráfego ao upstream e taxa de erro. Não é um probe de liveness e não precisa estar legível por quem não opera o serviço. |

Quando o servidor roda **sem** token configurado (desenvolvimento em
loopback), `/metrics` continua aberto: não há credencial a apresentar, e o
comportamento é coerente com o resto da superfície HTTP naquele modo, em que
`/mcp` também não exige autenticação.

## Consequências e escopo

- O healthcheck do `docker-compose.yml` e a verificação do CI usam
  `/healthz`; ambos seguem inalterados.
- O scrape do Prometheus precisa enviar o token:
  `authorization: Bearer <MCP_WEATHER_AUTH_TOKEN>`.
- Nenhum consumidor automatizado de `/metrics` foi identificado na frota.
  A mudança é compatível com o broker do Percival e com o gestor MCP do
  Positronic, que consomem MCP, não Prometheus.
- A decisão é do produto e **não** altera o contrato de lifecycle do broker
  (S2-C01), que segue pendente de revisão na coordenação IaC.

## Evidência

- `tests/test_metrics_auth.py` — 401 sem token, 401 com token errado, 200 com
  o token correto, 200 sem token configurado, `/healthz` sempre aberto.
- `scripts/verification/wx_http_mode.py` — prova contra a imagem construída.
