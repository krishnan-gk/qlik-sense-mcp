#!/usr/bin/env python3
"""
New user setup validator for Qlik Sense MCP + Gemini.

Run this after filling in your .env file:
    python setup/new_user.py
"""

import os
import sys
import asyncio
from pathlib import Path

# ── Ensure we run from the repo root ──────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))


def _ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m  {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m  {msg}")


def _warn(msg: str) -> None:
    print(f"  \033[33m⚠\033[0m  {msg}")


def _section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")
    print("─" * 50)


# ── 1. Check .env exists ───────────────────────────────────────────────────────

def check_env_file() -> bool:
    _section("1. Environment file")
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        _ok(f".env found at {env_path}")
        return True
    else:
        _fail(".env not found — copy .env.example to .env and fill in your credentials")
        return False


# ── 2. Check required env vars ────────────────────────────────────────────────

def check_env_vars() -> bool:
    _section("2. Required environment variables")
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env", override=False)

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")

    required = {
        "QLIK_SERVER_URL": "Qlik Sense server URL (e.g. https://qlik-dev.ispot.tv)",
        "QLIK_USER_DIRECTORY": "User directory (e.g. ANALYTICSUSERS)",
        "QLIK_USER_ID": "Your Qlik user ID (e.g. firstname.lastname@company.com)",
    }
    if use_vertex:
        required["GOOGLE_CLOUD_PROJECT"] = "Google Cloud project ID"
    else:
        required["GEMINI_API_KEY"] = "Google Gemini API key"

    optional = {
        "QLIK_CLIENT_CERT_PATH": "Client certificate (.pem)",
        "QLIK_CLIENT_KEY_PATH": "Client private key (.pem)",
        "QLIK_CA_CERT_PATH": "CA certificate (.pem)",
    }

    all_ok = True
    for var, desc in required.items():
        val = os.getenv(var, "")
        if val and val not in ("your-gemini-api-key-here", "your-username", "COMPANY"):
            _ok(f"{var} = {val[:40]}{'...' if len(val) > 40 else ''}")
        else:
            _fail(f"{var} not set — {desc}")
            all_ok = False

    if use_vertex:
        _ok("Gemini auth: Vertex AI (company Google Cloud account)")
    else:
        _ok("Gemini auth: API key")

    for var, desc in optional.items():
        val = os.getenv(var, "")
        if val:
            _ok(f"{var} = {val}")
        else:
            _warn(f"{var} not set ({desc}) — SSL verification will be disabled")

    return all_ok


# ── 3. Check cert files exist (if configured) ─────────────────────────────────

def check_cert_files() -> bool:
    _section("3. Certificate files")
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env", override=False)

    cert_vars = [
        "QLIK_CLIENT_CERT_PATH",
        "QLIK_CLIENT_KEY_PATH",
        "QLIK_CA_CERT_PATH",
    ]

    any_configured = False
    all_ok = True

    for var in cert_vars:
        path_str = os.getenv(var, "")
        if not path_str:
            continue
        any_configured = True
        p = Path(path_str)
        if p.exists() and p.stat().st_size > 0:
            _ok(f"{var}: {path_str}")
        elif p.exists():
            _fail(f"{var}: file is empty — {path_str}")
            all_ok = False
        else:
            _fail(f"{var}: file not found — {path_str}")
            all_ok = False

    if not any_configured:
        _warn("No certificate paths configured — will connect without mTLS (SSL verify disabled)")

    return all_ok


# ── 4. Test Qlik connection ────────────────────────────────────────────────────

def check_qlik_connection() -> bool:
    _section("4. Qlik Sense connection")
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env", override=False)

    try:
        import httpx
    except ImportError:
        _fail("httpx not installed — run: pip install httpx")
        return False

    server_url = os.getenv("QLIK_SERVER_URL", "").rstrip("/")
    user_dir = os.getenv("QLIK_USER_DIRECTORY", "")
    user_id = os.getenv("QLIK_USER_ID", "")
    client_cert = os.getenv("QLIK_CLIENT_CERT_PATH")
    client_key = os.getenv("QLIK_CLIENT_KEY_PATH")
    repo_port = int(os.getenv("QLIK_REPOSITORY_PORT", "4242"))

    if not server_url:
        _fail("QLIK_SERVER_URL not set — skipping connection test")
        return False

    # Extract host without scheme
    from urllib.parse import urlparse
    parsed = urlparse(server_url)
    host = parsed.hostname

    url = f"https://{host}:{repo_port}/qrs/about"
    headers = {
        "X-Qlik-User": f"UserDirectory={user_dir};UserId={user_id}",
        "X-Qlik-Xrfkey": "abcdefghijklmnop",
    }
    params = {"xrfkey": "abcdefghijklmnop"}

    cert = None
    if client_cert and client_key and Path(client_cert).exists() and Path(client_key).exists():
        cert = (client_cert, client_key)

    try:
        with httpx.Client(cert=cert, verify=False, timeout=10.0) as client:
            resp = client.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            data = resp.json()
            version = data.get("buildVersion", "unknown")
            _ok(f"Connected to Qlik Sense — version {version}")
            return True
        else:
            _fail(f"HTTP {resp.status_code} from {url}")
            _fail(f"Response: {resp.text[:200]}")
            return False
    except httpx.ConnectError as e:
        _fail(f"Cannot reach {url}: {e}")
        return False
    except Exception as e:
        _fail(f"Connection error: {e}")
        return False


# ── 5. Test Gemini API key ─────────────────────────────────────────────────────

def check_gemini_key() -> bool:
    _section("5. Gemini authentication")
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env", override=False)

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
    api_key = os.getenv("GEMINI_API_KEY", "")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    try:
        from google import genai as google_genai
    except ImportError:
        _fail("google-genai not installed — run: pip install 'qlik-sense-mcp-server[gemini]'")
        return False

    if use_vertex:
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            _fail("GOOGLE_GENAI_USE_VERTEXAI=true but GOOGLE_CLOUD_PROJECT is not set")
            return False
        _ok(f"Vertex AI mode — project={project}, location={location}")
        try:
            client = google_genai.Client(vertexai=True, project=project, location=location)
            client.models.generate_content(model=model_name, contents="Say 'ok'.")
            _ok(f"Vertex AI connection valid — model {model_name} responded")
            return True
        except Exception as e:
            _fail(f"Vertex AI error: {e}")
            _fail("Run: gcloud auth application-default login")
            return False
    else:
        if not api_key or api_key == "your-gemini-api-key-here":
            _fail("GEMINI_API_KEY not set")
            _fail("Set GEMINI_API_KEY in .env, or use Vertex AI (see .env.example)")
            return False
        try:
            client = google_genai.Client(api_key=api_key)
            client.models.generate_content(model=model_name, contents="Say 'ok'.")
            _ok(f"Gemini API key valid — model {model_name} responded")
            return True
        except Exception as e:
            _fail(f"Gemini API error: {e}")
            return False


# ── 6. Check google-adk is installed ──────────────────────────────────────────

def check_adk_installed() -> bool:
    _section("6. Google ADK + genai (agent framework)")
    import importlib.metadata
    all_ok = True
    for pkg in ("google-adk", "google-genai"):
        try:
            version = importlib.metadata.version(pkg)
            _ok(f"{pkg} {version} installed")
        except importlib.metadata.PackageNotFoundError:
            _fail(f"{pkg} not installed — run: pip install 'qlik-sense-mcp-server[gemini]'")
            all_ok = False
    return all_ok


# ── 7. Check MCP server is importable ─────────────────────────────────────────

def check_mcp_server() -> bool:
    _section("7. Qlik MCP server package")
    try:
        import qlik_sense_mcp_server  # noqa: F401
        import importlib.metadata
        version = importlib.metadata.version("qlik-sense-mcp-server")
        _ok(f"qlik-sense-mcp-server {version} installed")
        return True
    except ImportError:
        _fail("qlik-sense-mcp-server not installed")
        _fail("Run: pip install -e '.[gemini]' from the repo root")
        return False


# ── Summary ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n\033[1mQlik Sense MCP + Gemini — Setup Validator\033[0m")
    print("=" * 50)

    checks = [
        ("Environment file", check_env_file),
        ("Environment variables", check_env_vars),
        ("Certificate files", check_cert_files),
        ("Qlik connection", check_qlik_connection),
        ("Gemini API key", check_gemini_key),
        ("Google ADK", check_adk_installed),
        ("MCP server package", check_mcp_server),
    ]

    results = []
    for name, fn in checks:
        try:
            results.append((name, fn()))
        except Exception as e:
            _fail(f"Unexpected error in {name}: {e}")
            results.append((name, False))

    _section("Summary")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {status}  {name}")

    print()
    if passed == total:
        print(f"\033[32mAll {total} checks passed! Run: qlik-gemini\033[0m")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"\033[31m{failed}/{total} checks failed. Fix the issues above, then re-run.\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
