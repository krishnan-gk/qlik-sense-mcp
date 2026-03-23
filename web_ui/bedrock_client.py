"""Claude client with tool-use loop — supports Anthropic API key OR AWS Bedrock."""

from anthropic import Anthropic, AnthropicBedrock

from web_ui.mcp_bridge import MCPBridge

SYSTEM_PROMPT = """You are a Qlik Sense analytics assistant for iSpot.tv.

You have access to Qlik Sense tools that let you query apps, fields, data, and more.

Guidelines:
- Always use get_apps first if the user hasn't specified an app
- For data queries, use engine_create_hypercube with relevant dimensions and measures
- Present data clearly — use markdown tables and structured lists
- Note that Section Access restricts your data view to apps and data you're authorized for
- When asked about brands, reach, frequency, or impressions — look for apps with those fields
- If a tool returns an error, explain it simply and suggest alternatives
"""


def _make_client(*, anthropic_api_key: str = "", aws_region: str = "us-west-2"):
    """Return the right Anthropic client based on available credentials."""
    if anthropic_api_key:
        return Anthropic(api_key=anthropic_api_key)
    return AnthropicBedrock(aws_region=aws_region)


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    mcp: MCPBridge,
    *,
    anthropic_api_key: str = "",
    aws_region: str = "us-west-2",
    model: str = "claude-sonnet-4-6",
    bedrock_model: str = "us.anthropic.claude-sonnet-4-6-20250514",
    max_tokens: int = 4096,
    system_prompt: str = SYSTEM_PROMPT,
) -> tuple[str, list[dict], dict]:
    """Send messages to Claude, handle tool calls, return final response.

    Auto-selects backend:
      - ANTHROPIC_API_KEY set → uses Anthropic API directly (direct API key)
      - Otherwise            → uses AWS Bedrock (IAM role / access keys)

    Returns:
        (response_text, updated_messages, usage)
        where usage = {"input_tokens": int, "output_tokens": int}
    """
    client = _make_client(anthropic_api_key=anthropic_api_key, aws_region=aws_region)
    active_model = model if anthropic_api_key else bedrock_model

    total_input  = 0
    total_output = 0

    # Agentic loop — keep going until Claude gives a final text response
    while True:
        response = client.messages.create(
            model=active_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Accumulate token usage across all turns
        total_input  += getattr(response.usage, "input_tokens",  0)
        total_output += getattr(response.usage, "output_tokens", 0)

        # Collect the assistant's content blocks
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        messages.append({"role": "assistant", "content": assistant_content})

        # If no tool calls, we're done
        if response.stop_reason != "tool_use":
            text_parts = [b.text for b in response.content if b.type == "text"]
            usage = {"input_tokens": total_input, "output_tokens": total_output}
            return "\n".join(text_parts), messages, usage

        # Execute each tool call and build tool_result messages
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result_text = await mcp.call_tool(block.name, block.input)
            except Exception as e:
                result_text = f"Error calling {block.name}: {e}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})
