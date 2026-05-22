"""Constrói o agente LangGraph + Meta Ads MCP."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from oauth import make_oauth_provider
from prompts import SYSTEM_PROMPT

TOKEN_FILE = Path(".mcp_tokens.json")


async def build_agent():
    """Conecta no MCP do Meta Ads, carrega as tools e devolve um agente ReAct."""
    url = os.environ.get("META_MCP_URL", "https://mcp.facebook.com/ads")
    auth = await make_oauth_provider(url, TOKEN_FILE)

    client = MultiServerMCPClient(
        {
            "meta_ads": {
                "url": url,
                "transport": "streamable_http",
                "auth": auth,
            }
        }
    )
    tools = await client.get_tools()

    model = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        max_tokens=8192,
        timeout=120,
    )

    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )

    return agent, client, tools
