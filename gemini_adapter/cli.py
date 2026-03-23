"""CLI entry point for the Qlik Sense Gemini Adapter."""

import asyncio
import sys


def main() -> None:
    """Run the interactive Qlik Gemini agent."""
    try:
        from .config import GeminiAdapterConfig
        from .agent import QlikGeminiAgent
    except ImportError as e:
        print(f"Error: Missing dependencies — {e}")
        print("Run: pip install 'qlik-sense-mcp-server[gemini]'")
        sys.exit(1)

    try:
        config = GeminiAdapterConfig.from_env()
    except ValueError as e:
        print(f"Configuration error:\n  {e}")
        print("\nCopy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    agent = QlikGeminiAgent(config)

    try:
        asyncio.run(agent.run_interactive())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
