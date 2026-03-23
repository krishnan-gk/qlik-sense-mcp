"""Qlik Sense AI Assistant — Streamlit Chat UI powered by Claude via Bedrock."""

import asyncio
import streamlit as st

from web_ui.config import WebUIConfig
from web_ui.mcp_bridge import MCPBridge
from web_ui.bedrock_client import chat_with_tools


def get_event_loop():
    """Get or create an asyncio event loop for Streamlit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def init_session_state(config: WebUIConfig):
    """Initialize Streamlit session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []  # API-format messages for Bedrock
    if "mcp_bridge" not in st.session_state:
        st.session_state.mcp_bridge = None
    if "mcp_tools" not in st.session_state:
        st.session_state.mcp_tools = []
    if "mcp_connected" not in st.session_state:
        st.session_state.mcp_connected = False


async def ensure_mcp_connected(config: WebUIConfig) -> MCPBridge:
    """Connect to the MCP server if not already connected."""
    if st.session_state.mcp_bridge and st.session_state.mcp_connected:
        return st.session_state.mcp_bridge

    bridge = MCPBridge(config.to_qlik_env())
    await bridge.connect()
    tools = await bridge.list_tools()

    st.session_state.mcp_bridge = bridge
    st.session_state.mcp_tools = tools
    st.session_state.mcp_connected = True
    return bridge


async def handle_user_message(user_input: str, config: WebUIConfig):
    """Process a user message through Claude + MCP tools."""
    bridge = await ensure_mcp_connected(config)

    # Add user message to API history
    st.session_state.chat_messages.append({
        "role": "user",
        "content": user_input,
    })

    response_text, updated_messages = await chat_with_tools(
        messages=st.session_state.chat_messages,
        tools=st.session_state.mcp_tools,
        mcp=bridge,
        anthropic_api_key=config.anthropic_api_key,
        aws_region=config.aws_region,
        model=config.claude_model,
        bedrock_model=config.bedrock_model,
        max_tokens=config.max_tokens,
    )

    st.session_state.chat_messages = updated_messages
    return response_text


def main():
    config = WebUIConfig.from_env()

    st.set_page_config(
        page_title=config.app_title,
        page_icon=config.page_icon,
        layout="wide",
    )

    st.title(f"{config.page_icon} {config.app_title}")

    init_session_state(config)

    # --- Sidebar ---
    with st.sidebar:
        st.header("Settings")
        st.text_input("Qlik User ID", value=config.qlik_user_id, disabled=True)
        st.text_input("Qlik Server", value=config.qlik_server_url, disabled=True)
        if config.use_anthropic_direct:
            st.text_input("Claude Model", value=config.claude_model, disabled=True)
            st.text_input("Auth", value="Anthropic API key", disabled=True)
        else:
            st.text_input("Claude Model", value=config.bedrock_model, disabled=True)
            st.text_input("Auth", value=f"AWS Bedrock ({config.aws_region})", disabled=True)

        st.divider()

        # Connection status
        if st.session_state.mcp_connected:
            st.success(f"MCP connected ({len(st.session_state.mcp_tools)} tools)")
        else:
            st.info("MCP: not connected yet (connects on first message)")

        st.divider()

        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.session_state.chat_messages = []
            st.rerun()

        st.divider()
        backend = "Anthropic API" if config.use_anthropic_direct else "Amazon Bedrock"
        st.caption(f"Powered by Claude ({backend}) + Qlik Sense MCP")

    # --- Chat history ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Chat input ---
    if user_input := st.chat_input("Ask about your Qlik data..."):
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Get response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                loop = get_event_loop()
                try:
                    response = loop.run_until_complete(
                        handle_user_message(user_input, config)
                    )
                except Exception as e:
                    response = f"Error: {e}"

            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
