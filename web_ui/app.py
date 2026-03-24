"""Qlik Sense AI Assistant — Streamlit Chat UI powered by Claude via Bedrock."""

import asyncio
import json

import streamlit as st

from web_ui.config import WebUIConfig
from web_ui.mcp_bridge import MCPBridge
from web_ui.bedrock_client import chat_with_tools, SYSTEM_PROMPT
from web_ui import db




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_event_loop():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def init_session_state():
    defaults = {
        "logged_in":     False,
        "user_name":     "",
        "user_email":    "",
        "session_id":    db.new_session_id(),
        "messages":      [],       # display messages [{role, content}]
        "chat_messages": [],       # API-format messages for Claude
        "mcp_bridge":    None,
        "mcp_tools":     [],
        "mcp_connected": False,
        "qlik_apps":     [],       # [{"id": ..., "name": ...}]
        "apps_loaded":   False,
        "selected_app":  "(All apps)",
        "show_admin":    False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Auto-login from URL query params (persists across page refreshes)
    if not st.session_state.logged_in:
        saved_email = st.query_params.get("qe", "")
        saved_name  = st.query_params.get("qn", "")
        if saved_email and saved_name:
            db.upsert_user(saved_name, saved_email)
            st.session_state.user_name  = saved_name
            st.session_state.user_email = saved_email
            st.session_state.logged_in  = True


async def ensure_mcp_connected(config: WebUIConfig) -> MCPBridge:
    if st.session_state.mcp_bridge and st.session_state.mcp_connected:
        return st.session_state.mcp_bridge

    bridge = MCPBridge(config.to_qlik_env())
    await bridge.connect()
    tools = await bridge.list_tools()

    st.session_state.mcp_bridge    = bridge
    st.session_state.mcp_tools     = tools
    st.session_state.mcp_connected = True
    return bridge


async def load_qlik_apps(bridge: MCPBridge) -> list[dict]:
    """Fetch ALL apps from Qlik via paginated MCP calls (published + unpublished)."""
    all_apps: dict[str, dict] = {}  # keyed by guid to deduplicate

    for published_flag in [True, False]:
        offset = 0
        while True:
            try:
                raw = await bridge.call_tool("get_apps", {
                    "limit": 1000,
                    "offset": offset,
                    "published": published_flag,
                })
                data = json.loads(raw)
                if isinstance(data, dict):
                    page     = data.get("apps", [])
                    has_more = data.get("pagination", {}).get("has_more", False)
                else:
                    page, has_more = (data if isinstance(data, list) else []), False

                for item in page:
                    if not isinstance(item, dict):
                        continue
                    app_id = item.get("guid") or item.get("id") or item.get("appId") or item.get("qDocId", "")
                    if not app_id or app_id in all_apps:
                        continue
                    all_apps[app_id] = {
                        "id":     app_id,
                        "name":   item.get("name") or item.get("appName") or app_id,
                        "stream": item.get("stream") or "",
                    }

                if not has_more:
                    break
                offset += 50
            except Exception:
                break

    return list(all_apps.values())


def build_system_prompt() -> str:
    """Inject selected-app context into the base system prompt."""
    app = st.session_state.selected_app
    if app and app != "(All apps)":
        apps = st.session_state.qlik_apps
        app_obj = next((a for a in apps if a["name"] == app), None)
        extra = f"\n\nThe user has selected the Qlik app: **{app}**"
        if app_obj:
            extra += f" (ID: {app_obj['id']})"
        extra += ". Focus all queries on this app unless the user explicitly asks about another."
        return SYSTEM_PROMPT + extra
    return SYSTEM_PROMPT


async def handle_user_message(user_input: str, config: WebUIConfig):
    bridge = await ensure_mcp_connected(config)

    # Load app list once after first MCP connection
    if not st.session_state.apps_loaded:
        apps = await load_qlik_apps(bridge)
        st.session_state.qlik_apps  = apps
        st.session_state.apps_loaded = True

    st.session_state.chat_messages.append({"role": "user", "content": user_input})

    response_text, updated_messages, usage = await chat_with_tools(
        messages=st.session_state.chat_messages,
        tools=st.session_state.mcp_tools,
        mcp=bridge,
        anthropic_api_key=config.anthropic_api_key,
        aws_region=config.aws_region,
        model=config.claude_model,
        bedrock_model=config.bedrock_model,
        max_tokens=config.max_tokens,
        system_prompt=build_system_prompt(),
    )

    st.session_state.chat_messages = updated_messages

    # Persist to SQLite
    selected = st.session_state.selected_app
    apps     = st.session_state.qlik_apps
    app_obj  = next((a for a in apps if a["name"] == selected), None)

    db.log_message(
        session_id    = st.session_state.session_id,
        user_email    = st.session_state.user_email,
        user_name     = st.session_state.user_name,
        question      = user_input,
        answer        = response_text,
        input_tokens  = usage["input_tokens"],
        output_tokens = usage["output_tokens"],
        qlik_app_id   = app_obj["id"]   if app_obj else "",
        qlik_app_name = app_obj["name"] if app_obj else "",
    )

    return response_text


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------

def show_login(config: WebUIConfig):
    st.set_page_config(
        page_title=config.app_title,
        page_icon=config.page_icon,
        layout="centered",
    )
    st.title(f"{config.page_icon} {config.app_title}")
    st.subheader("Sign in to continue")
    st.caption("Enter your name and work email — no password required.")

    with st.form("login_form"):
        name  = st.text_input("Your Name",   placeholder="e.g. Krishnan Govindan")
        email = st.text_input("Work Email",  placeholder="you@ispot.tv")
        submitted = st.form_submit_button("Continue →", use_container_width=True)

    if submitted:
        name  = name.strip()
        email = email.strip()
        if not name:
            st.error("Please enter your name.")
        elif not email or "@" not in email:
            st.error("Please enter a valid work email.")
        else:
            db.upsert_user(name, email)
            st.session_state.user_name  = name
            st.session_state.user_email = email
            st.session_state.logged_in  = True
            # Persist login in URL — survives page refreshes
            st.query_params["qe"] = email
            st.query_params["qn"] = name
            st.rerun()


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

def show_admin_panel(config: WebUIConfig):
    st.title("Admin Panel — App Access Control")
    col_back, col_refresh = st.columns([1, 1])
    with col_back:
        if st.button("← Back to Chat"):
            st.session_state.show_admin = False
            st.rerun()
    with col_refresh:
        if st.button("🔄 Refresh app list from Qlik"):
            st.session_state.apps_loaded = False
            st.rerun()
    st.caption("Enable or disable Qlik apps visible to users. Changes take effect immediately.")

    all_apps = db.get_all_apps()
    if not all_apps:
        st.warning("No apps loaded yet. Go back to chat — apps sync automatically on first load.")
        return

    # Stream filter
    streams = sorted(set(a["stream"] or "(No stream)" for a in all_apps))
    selected_stream = st.selectbox("Filter by stream", ["(All streams)"] + streams)

    # Bulk actions
    enabled_count = sum(1 for a in all_apps if a['enabled'])
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"**{len(all_apps)} apps total** — {enabled_count} enabled")
    with col2:
        btn_label = f"Enable stream" if selected_stream != "(All streams)" else "Enable all"
        if st.button(btn_label, key="btn_enable"):
            target_apps = [a for a in all_apps if selected_stream == "(All streams)"
                           or (a["stream"] or "(No stream)") == selected_stream]
            for a in target_apps:
                db.set_app_enabled(a["id"], True)
            st.rerun()
    with col3:
        btn_label2 = f"Disable stream" if selected_stream != "(All streams)" else "Disable all"
        if st.button(btn_label2, key="btn_disable"):
            target_apps = [a for a in all_apps if selected_stream == "(All streams)"
                           or (a["stream"] or "(No stream)") == selected_stream]
            for a in target_apps:
                db.set_app_enabled(a["id"], False)
            st.rerun()

    st.divider()

    # App list with toggles
    filtered = [a for a in all_apps
                if selected_stream == "(All streams)"
                or (a["stream"] or "(No stream)") == selected_stream]

    for app in filtered:
        col_name, col_stream, col_toggle = st.columns([4, 2, 1])
        with col_name:
            st.markdown(f"**{app['name']}**")
        with col_stream:
            st.caption(app["stream"] or "(No stream)")
        with col_toggle:
            new_val = st.toggle("", value=app["enabled"], key=f"toggle_{app['id']}")
            if new_val != app["enabled"]:
                db.set_app_enabled(app["id"], new_val)
                st.rerun()


# ---------------------------------------------------------------------------
# Main chat UI
# ---------------------------------------------------------------------------

def show_chat(config: WebUIConfig):
    if st.session_state.get("show_admin"):
        show_admin_panel(config)
        return
    st.set_page_config(
        page_title=config.app_title,
        page_icon=config.page_icon,
        layout="wide",
    )
    st.title(f"{config.page_icon} {config.app_title}")

    loop = get_event_loop()

    # Eagerly connect MCP and load app list on page render
    if not st.session_state.apps_loaded:
        with st.spinner("Connecting to Qlik..."):
            try:
                bridge   = loop.run_until_complete(ensure_mcp_connected(config))
                all_apps = loop.run_until_complete(load_qlik_apps(bridge))
                if all_apps:
                    db.sync_apps(all_apps)          # sync all apps into allowlist DB
                # Users only see enabled apps
                st.session_state.qlik_apps   = db.get_enabled_apps()
                st.session_state.apps_loaded = True
                st.rerun()
            except Exception:
                pass  # Will retry on first message

    # --- Sidebar ---
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.user_name}**")
        st.caption(st.session_state.user_email)
        st.divider()

        # Qlik app selector with search (type to filter)
        app_names = ["(All apps)"] + [a["name"] for a in st.session_state.qlik_apps]
        selected = st.selectbox(
            "Focus on Qlik App",
            options=app_names,
            index=app_names.index(st.session_state.selected_app)
                  if st.session_state.selected_app in app_names else 0,
            help="Type to search apps",
        )
        if selected != st.session_state.selected_app:
            st.session_state.selected_app = selected
            st.rerun()

        st.divider()

        # Connection status
        if st.session_state.mcp_connected:
            st.success(f"MCP connected ({len(st.session_state.mcp_tools)} tools)")
        else:
            st.info("MCP connects on first message")

        st.divider()

        # Session cost
        totals = db.session_totals(st.session_state.session_id)
        st.metric("Session cost", f"${totals['cost_usd']:.4f}")
        total_tokens = totals["input_tokens"] + totals["output_tokens"]
        st.caption(f"{total_tokens:,} tokens · {totals['exchanges']} exchanges")

        st.divider()

        # Auth info
        if config.use_anthropic_direct:
            st.caption(f"Claude: {config.claude_model}")
            st.caption("Auth: Anthropic API key")
        else:
            st.caption(f"Claude: {config.bedrock_model}")
            st.caption(f"Auth: AWS Bedrock ({config.aws_region})")

        st.divider()

        if st.button("Clear conversation"):
            st.session_state.messages      = []
            st.session_state.chat_messages = []
            st.session_state.session_id    = db.new_session_id()
            st.rerun()

        if st.button("Sign out"):
            st.query_params.clear()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        # Admin panel button — visible only to admin emails
        if st.session_state.user_email.lower() in [e.lower() for e in config.admin_emails]:
            st.divider()
            if st.button("Admin Panel"):
                st.session_state.show_admin = True
                st.rerun()

    # --- App selector bar (inline, above chat) ---
    app_names = ["(All apps)"] + [a["name"] for a in st.session_state.qlik_apps]
    col_label, col_select = st.columns([1, 4])
    with col_label:
        st.markdown("**App focus:**")
    with col_select:
        inline_selected = st.selectbox(
            "Select app",
            options=app_names,
            index=app_names.index(st.session_state.selected_app)
                  if st.session_state.selected_app in app_names else 0,
            label_visibility="collapsed",
            key="inline_app_select",
            help="Type to search — switch app focus mid-conversation",
        )
        if inline_selected != st.session_state.selected_app:
            st.session_state.selected_app = inline_selected
            st.rerun()

    if st.session_state.selected_app != "(All apps)":
        st.info(f"Asking about: **{st.session_state.selected_app}**", icon="🎯")

    st.divider()

    # --- Chat history ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Chat input ---
    app = st.session_state.selected_app
    placeholder = f"Ask about {app}..." if app != "(All apps)" else "Ask about your Qlik data..."
    if user_input := st.chat_input(placeholder):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                try:
                    response = loop.run_until_complete(
                        handle_user_message(user_input, config)
                    )
                except Exception as e:
                    response = f"Error: {e}"
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()  # refresh sidebar cost metrics


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    db.init_db()
    config = WebUIConfig.from_env()
    init_session_state()

    if not st.session_state.logged_in:
        show_login(config)
    else:
        show_chat(config)


if __name__ == "__main__":
    main()
