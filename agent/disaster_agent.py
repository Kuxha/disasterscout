# agent/disaster_agent.py

import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


app = MCPApp(name="disasterscout_agent")


async def main() -> None:
    async with app.run():
        agent = Agent(
            name="disasterscout_agent",
            instruction=(
                "You are DisasterScout, a crisis intelligence assistant. "
                "Generate a concise crisis situation report for the user "
                "using your LLM capabilities."
            ),
            # No MCP servers for now – keep this empty to avoid registry errors
            server_names=[],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)

            prompt = (
                "Generate a daily brief for Brooklyn, NY about flooding. "
                "Return a concise crisis situation report."
            )

            result = await llm.generate_str(prompt)

            print("\n=== Agent Response (LastMile mcp-agent) ===\n")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
