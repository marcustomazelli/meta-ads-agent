"""CLI simples para conversar com o gestor de tráfego."""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import build_agent

load_dotenv()


def _print_assistant(msg: AIMessage) -> None:
    if isinstance(msg.content, str):
        print(f"\nagente > {msg.content}\n")
        return

    parts: list[str] = []
    for block in msg.content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    print(f"\nagente > {''.join(parts).strip()}\n")


def _trace_tool_calls(messages) -> None:
    """Mostra as tool calls feitas no último turn (útil para debug)."""
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            for call in m.tool_calls:
                print(f"  · tool: {call['name']}({call.get('args', {})})")
        elif isinstance(m, ToolMessage):
            preview = (m.content or "")[:200]
            print(f"  · result: {preview}{'...' if len(m.content or '') > 200 else ''}")


async def chat() -> None:
    print("Inicializando agente e conectando no MCP do Meta Ads...")
    agent, _client, tools = await build_agent()
    print(f"Pronto. {len(tools)} tools carregadas. Digite 'sair' para encerrar.\n")

    history: list = []
    while True:
        try:
            user_input = input("você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"sair", "exit", "quit"}:
            break

        previous_len = len(history)
        history.append(HumanMessage(content=user_input))

        result = await agent.ainvoke({"messages": history})
        history = result["messages"]

        new_messages = history[previous_len + 1 :]
        _trace_tool_calls(new_messages)

        last = history[-1]
        if isinstance(last, AIMessage):
            _print_assistant(last)


if __name__ == "__main__":
    asyncio.run(chat())
