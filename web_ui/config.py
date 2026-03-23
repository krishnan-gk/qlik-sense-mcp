"""Configuration for the Qlik MCP Chat Web UI."""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv


@dataclass
class WebUIConfig:
    # --- Auth mode: "anthropic" (API key) or "bedrock" (AWS) ---
    anthropic_api_key: str = ""       # set ANTHROPIC_API_KEY in .env
    aws_region: str = "us-west-2"
    bedrock_model: str = "us.anthropic.claude-sonnet-4-6-20250514"
    claude_model: str = "claude-sonnet-4-6"  # used when ANTHROPIC_API_KEY is set
    max_tokens: int = 4096

    @property
    def use_anthropic_direct(self) -> bool:
        return bool(self.anthropic_api_key)

    # --- Qlik MCP server settings ---
    qlik_server_url: str = ""
    qlik_user_directory: str = ""
    qlik_user_id: str = ""
    qlik_client_cert_path: str = ""
    qlik_client_key_path: str = ""
    qlik_ca_cert_path: str = ""
    qlik_verify_ssl: str = "false"
    qlik_repository_port: str = "4242"
    qlik_proxy_port: str = "4243"
    qlik_engine_port: str = "4747"
    qlik_http_port: str = "443"

    # --- UI settings ---
    app_title: str = "Qlik Sense AI Assistant"
    page_icon: str = "📊"

    @classmethod
    def from_env(cls, dotenv_path: Optional[str] = None) -> "WebUIConfig":
        load_dotenv(dotenv_path or ".env")
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            aws_region=os.getenv("AWS_REGION", "us-west-2"),
            bedrock_model=os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6-20250514"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            max_tokens=int(os.getenv("BEDROCK_MAX_TOKENS", "4096")),
            qlik_server_url=os.getenv("QLIK_SERVER_URL", ""),
            qlik_user_directory=os.getenv("QLIK_USER_DIRECTORY", ""),
            qlik_user_id=os.getenv("QLIK_USER_ID", ""),
            qlik_client_cert_path=os.getenv("QLIK_CLIENT_CERT_PATH", ""),
            qlik_client_key_path=os.getenv("QLIK_CLIENT_KEY_PATH", ""),
            qlik_ca_cert_path=os.getenv("QLIK_CA_CERT_PATH", ""),
            qlik_verify_ssl=os.getenv("QLIK_VERIFY_SSL", "false"),
            qlik_repository_port=os.getenv("QLIK_REPOSITORY_PORT", "4242"),
            qlik_proxy_port=os.getenv("QLIK_PROXY_PORT", "4243"),
            qlik_engine_port=os.getenv("QLIK_ENGINE_PORT", "4747"),
            qlik_http_port=os.getenv("QLIK_HTTP_PORT", "443"),
        )

    def to_qlik_env(self) -> dict:
        """Return env vars dict for the MCP server subprocess."""
        env = {
            "QLIK_SERVER_URL": self.qlik_server_url,
            "QLIK_USER_DIRECTORY": self.qlik_user_directory,
            "QLIK_USER_ID": self.qlik_user_id,
            "QLIK_CLIENT_CERT_PATH": self.qlik_client_cert_path,
            "QLIK_CLIENT_KEY_PATH": self.qlik_client_key_path,
            "QLIK_CA_CERT_PATH": self.qlik_ca_cert_path,
            "QLIK_VERIFY_SSL": self.qlik_verify_ssl,
            "QLIK_REPOSITORY_PORT": self.qlik_repository_port,
            "QLIK_PROXY_PORT": self.qlik_proxy_port,
            "QLIK_ENGINE_PORT": self.qlik_engine_port,
            "QLIK_HTTP_PORT": self.qlik_http_port,
        }
        return {k: v for k, v in env.items() if v}
