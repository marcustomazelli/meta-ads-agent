# Gestor de Tráfego — Meta Ads Agent

Agente LangChain (Python) que age como gestor de tráfego, projetado para conectar no MCP server oficial da Meta em `https://mcp.facebook.com/ads`. Usa Claude (Anthropic) como LLM e LangGraph para o loop ReAct.

> **⚠️ Status: bloqueado pela Meta.** A implementação está completa e funcional do nosso lado (OAuth flui, token é obtido), mas o endpoint `mcp.facebook.com/ads` rejeita requisições de clientes OAuth não pré-aprovados pela Meta. Hoje só Claude Desktop, claude.ai, ChatGPT, Cursor e Codex passam.

## Arquitetura

```
main.py            CLI: lê input, envia ao agente, imprime resposta
  └─ agent.py      build_agent(): conecta no MCP e cria o ReAct agent
       ├─ MultiServerMCPClient   (langchain-mcp-adapters)
       │     └→ https://mcp.facebook.com/ads  (streamable_http + OAuth)
       ├─ ChatAnthropic          (Claude Sonnet 4.6)
       └─ prompts.py             system prompt do "gestor de tráfego"
  └─ oauth.py      Fluxo OAuth 2.1 + PKCE para o MCP da Meta
       ├─ FileTokenStorage       persiste em .mcp_tokens.json
       ├─ redirect_handler       abre browser para login
       ├─ callback_handler       HTTP server local em :8765
       └─ monkeypatch            remove scope catalog_management
                                 (não aprovado pelo nosso app)
```

As tools do MCP são carregadas dinamicamente — qualquer tool exposta pelo servidor da Meta vira ferramenta disponível ao agente automaticamente, sem código adicional.

## Stack

- Python 3.12+ (gerenciado via `uv`)
- LangChain + LangGraph (ReAct agent)
- langchain-mcp-adapters (ponte LangChain ↔ MCP)
- mcp (SDK oficial Python do Model Context Protocol)
- langchain-anthropic + Claude Sonnet 4.6 (LLM)
- python-dotenv

## Setup

Pré-requisitos: `uv` instalado e Python 3.12 disponível.

```bash
# 1. instalar deps e fixar Python
uv python install 3.12
uv python pin 3.12
uv sync

# 2. configurar env
cp .env.example .env
# editar .env com as credenciais
```

### Variáveis de ambiente

| Var | Descrição |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da Anthropic (https://console.anthropic.com) |
| `ANTHROPIC_MODEL` | Modelo Claude. Padrão `claude-sonnet-4-6` |
| `META_MCP_URL` | Endpoint do MCP. Padrão `https://mcp.facebook.com/ads` |
| `META_APP_ID` | App ID do app criado em developers.facebook.com |
| `META_APP_SECRET` | App Secret correspondente |

### Configuração do app Meta

Necessário porque o MCP da Meta não suporta Dynamic Client Registration.

1. Criar app em https://developers.facebook.com/apps → tipo **Business**.
2. Adicionar produto **Facebook Login for Business** (ou Facebook Login).
3. Em `Facebook Login > Settings`:
   - Client OAuth Login: ON
   - Web OAuth Login: ON
   - Valid OAuth Redirect URIs: `http://localhost:8765/callback`
4. Copiar `App ID` e `App Secret` em `App Settings > Basic` para o `.env`.

## Rodar

```bash
uv run python main.py
```

**Primeira execução:**

1. Sobe HTTP server local em `localhost:8765`
2. Abre o browser numa página de login do Meta
3. Você autoriza os escopos (`ads_management`, `ads_read`, `business_management`, `pages_show_list`)
4. Callback recebe o code, troca por access_token, persiste em `.mcp_tokens.json`

**Execuções subsequentes** reusam o token do disco (com refresh automático).

## Estado atual e bloqueio

A pipeline técnica funciona ponta a ponta até o passo final:

```
[1] Conexão TCP em mcp.facebook.com/ads      ✓
[2] Fluxo OAuth 2.1 + PKCE                   ✓
[3] App pré-registrado (sem DCR)             ✓
[4] Scope catalog_management removido        ✓
[5] Browser login + autorização              ✓
[6] Token EAA... obtido (60d validade)       ✓
[7] Requisição inicialize() para o MCP       ✗  401 "restricted to certain users"
```

O 401 acontece porque a Meta verifica o `client_id` que emitiu o token e só aceita clientes específicos pré-acordados (Claude Desktop, claude.ai, ChatGPT, Cursor, Codex). Não há processo público para registrar `client_id` próprio.

Há ainda uma segunda camada: mesmo com cliente aprovado, a ad account precisa estar no rollout faseado (`is_ads_mcp_enabled`). Verificado via teste no claude.ai web — a conta usada lista tools mas não executa.


## Próximos passos sugeridos

Quando/se a Meta abrir uma das portas abaixo, o código já está pronto:

- **Registro público de clientes OAuth terceiros**: bastaria registrar nosso app e rodar.
- **Habilitação da ad account no rollout**: já valida que o produto opera fim a fim.

Caminhos alternativos avaliados (não implementados):

- Pivotar para `meta-ads-mcp` community (open-source), que usa Marketing API direto via Graph. Mesma estrutura LangChain, troca de `streamable_http` para `stdio`.
- Tools LangChain custom chamando Graph API direto (sem MCP).
- Anthropic API com `mcp_servers` connector — não resolve, pois ainda exige token de cliente OAuth aprovado pela Meta.

## Estrutura de arquivos

```
.
├── pyproject.toml         deps e config (uv)
├── uv.lock                lockfile
├── .env.example           template de env vars
├── .env                   credenciais (gitignored)
├── .mcp_tokens.json       token OAuth persistido (gitignored)
├── main.py                CLI de chat
├── agent.py               build do agente + cliente MCP
├── oauth.py               fluxo OAuth 2.1 + PKCE + monkeypatch
├── prompts.py             system prompt do gestor de tráfego
├── README.md              este arquivo
```
