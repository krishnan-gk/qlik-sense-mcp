"""Qlik Sense Gemini Agent using Google ADK + MCP toolset."""

import asyncio
import os
import sys
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)
from google.genai import types

from .config import GeminiAdapterConfig

SYSTEM_INSTRUCTION = """You are a Qlik Sense analytics assistant for iSpot.tv.

You have access to the following Qlik Sense tools:
- get_apps: List all apps you have access to
- get_app_details: Get metadata, fields, tables, and master items for an app
- get_app_script: Get the load script for an app
- get_app_field_statistics: Analyze field values (min, max, avg, cardinality)
- engine_create_hypercube: Query data from an app using dimensions and measures
- get_app_field: Get field values with optional wildcard search
- get_app_variables: List variables defined in an app
- get_app_sheets: List all sheets in an app
- get_app_sheet_objects: List objects (charts, tables) on a specific sheet
- get_app_object: Get the layout of a specific object

Guidelines:
- Always use get_apps first if the user hasn't specified an app
- For data queries, use engine_create_hypercube with relevant dimensions and measures
- Present data clearly — use tables and structured lists when appropriate
- Note that Section Access restricts your data view to apps and data you're authorized for
- When asked about brands, reach, frequency, or impressions — look for apps with those fields
"""


class QlikGeminiAgent:
    """Gemini agent that uses the Qlik Sense MCP server as its toolset."""

    def __init__(self, config: GeminiAdapterConfig):
        self.config = config
        self._runner: Optional[InMemoryRunner] = None
        self._session_id = "qlik-session-001"
        self._user_id = config.user_id

    async def _build_runner(self) -> InMemoryRunner:
        """Build the ADK runner with MCP toolset."""
        mcp_env = {**os.environ, **self.config.to_qlik_env()}

        toolset = MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "qlik_sense_mcp_server.server"],
                    env=mcp_env,
                )
            )
        )

        agent = Agent(
            model=self.config.gemini_model,
            name="qlik_analyst",
            instruction=SYSTEM_INSTRUCTION,
            tools=[toolset],
        )

        return InMemoryRunner(agent=agent, app_name="qlik-gemini")

    async def initialize(self) -> None:
        """Initialize the agent and MCP connection."""
        if self.config.use_vertex_ai:
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", self.config.vertex_project or "")
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", self.config.vertex_location)
        else:
            os.environ.setdefault("GOOGLE_API_KEY", self.config.gemini_api_key)
        self._runner = await self._build_runner()
        await self._runner.session_service.create_session(
            app_name="qlik-gemini",
            user_id=self._user_id,
            session_id=self._session_id,
        )

    async def chat(self, message: str) -> str:
        """Send a message and get a response."""
        if not self._runner:
            await self.initialize()

        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )

        response_text = ""
        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=self._session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                response_text = "".join(
                    p.text for p in event.content.parts if hasattr(p, "text")
                )

        return response_text or "(No response)"

    async def run_interactive(self) -> None:
        """Run an interactive REPL session."""
        print("\n" + "=" * 60)
        print("  Qlik Sense Analytics Agent (powered by Gemini)")
        print("=" * 60)
        print(self.config.summary())
        print("\nType your question. Commands: 'exit', 'quit', 'clear'")
        print("-" * 60 + "\n")

        print("Connecting to Qlik Sense MCP server...", end="", flush=True)
        try:
            await self.initialize()
            print(" connected.\n")
        except Exception as e:
            print(f" FAILED\nError: {e}")
            return

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            if user_input.lower() == "clear":
                self._session_id = f"qlik-session-{asyncio.get_event_loop().time():.0f}"
                await self._runner.session_service.create_session(
                    app_name="qlik-gemini",
                    user_id=self._user_id,
                    session_id=self._session_id,
                )
                print("(Conversation cleared)\n")
                continue

            print("Agent: ", end="", flush=True)
            try:
                response = await self.chat(user_input)
                print(response)
            except Exception as e:
                print(f"Error: {e}")
            print()
