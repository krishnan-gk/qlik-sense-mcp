"""Configuration for Qlik Sense Gemini Adapter."""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv


@dataclass
class GeminiAdapterConfig:
    """Configuration combining Gemini credentials and Qlik connection settings."""

    # Gemini settings
    # One of gemini_api_key OR (use_vertex_ai + vertex_project + vertex_location) is required
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Vertex AI settings (use company Google Cloud account — no API key needed)
    use_vertex_ai: bool = False
    vertex_project: Optional[str] = None
    vertex_location: str = "us-central1"

    # Qlik connection (mirrors QLIK_* env vars)
    server_url: str = ""
    user_directory: str = ""
    user_id: str = ""
    client_cert_path: Optional[str] = None
    client_key_path: Optional[str] = None
    ca_cert_path: Optional[str] = None
    repository_port: int = 4242
    proxy_port: int = 4243
    engine_port: int = 4747
    http_port: Optional[int] = None
    verify_ssl: bool = False
    http_timeout: float = 10.0
    ws_timeout: float = 8.0
    ws_retries: int = 2

    @classmethod
    def from_env(cls, dotenv_path: Optional[str] = None) -> "GeminiAdapterConfig":
        """Load configuration from environment variables / .env file."""
        load_dotenv(dotenv_path or ".env", override=False)

        use_vertex_ai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() in ("true", "1")
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        vertex_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        vertex_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        if use_vertex_ai:
            if not vertex_project:
                raise ValueError(
                    "GOOGLE_CLOUD_PROJECT is required when GOOGLE_GENAI_USE_VERTEXAI=true.\n"
                    "Set it to your Google Cloud project ID in your .env file.\n"
                    "Then run: gcloud auth application-default login"
                )
        elif not gemini_api_key:
            raise ValueError(
                "Either set GEMINI_API_KEY (personal API key from aistudio.google.com/apikey)\n"
                "or set GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT to use your\n"
                "company Google Cloud account (no API key needed)."
            )

        server_url = os.getenv("QLIK_SERVER_URL", "")
        user_directory = os.getenv("QLIK_USER_DIRECTORY", "")
        user_id = os.getenv("QLIK_USER_ID", "")

        missing = [k for k, v in [
            ("QLIK_SERVER_URL", server_url),
            ("QLIK_USER_DIRECTORY", user_directory),
            ("QLIK_USER_ID", user_id),
        ] if not v]
        if missing:
            raise ValueError(f"Missing required Qlik env vars: {', '.join(missing)}")

        http_port_str = os.getenv("QLIK_HTTP_PORT")

        return cls(
            gemini_api_key=gemini_api_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            use_vertex_ai=use_vertex_ai,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
            server_url=server_url,
            user_directory=user_directory,
            user_id=user_id,
            client_cert_path=os.getenv("QLIK_CLIENT_CERT_PATH"),
            client_key_path=os.getenv("QLIK_CLIENT_KEY_PATH"),
            ca_cert_path=os.getenv("QLIK_CA_CERT_PATH"),
            repository_port=int(os.getenv("QLIK_REPOSITORY_PORT", "4242")),
            proxy_port=int(os.getenv("QLIK_PROXY_PORT", "4243")),
            engine_port=int(os.getenv("QLIK_ENGINE_PORT", "4747")),
            http_port=int(http_port_str) if http_port_str else None,
            verify_ssl=os.getenv("QLIK_VERIFY_SSL", "false").lower() == "true",
            http_timeout=float(os.getenv("QLIK_HTTP_TIMEOUT", "10.0")),
            ws_timeout=float(os.getenv("QLIK_WS_TIMEOUT", "8.0")),
            ws_retries=int(os.getenv("QLIK_WS_RETRIES", "2")),
        )

    def to_qlik_env(self) -> dict:
        """Return a dict of QLIK_* env vars to pass to the MCP server subprocess."""
        env = {
            "QLIK_SERVER_URL": self.server_url,
            "QLIK_USER_DIRECTORY": self.user_directory,
            "QLIK_USER_ID": self.user_id,
            "QLIK_REPOSITORY_PORT": str(self.repository_port),
            "QLIK_PROXY_PORT": str(self.proxy_port),
            "QLIK_ENGINE_PORT": str(self.engine_port),
            "QLIK_VERIFY_SSL": str(self.verify_ssl).lower(),
            "QLIK_HTTP_TIMEOUT": str(self.http_timeout),
            "QLIK_WS_TIMEOUT": str(self.ws_timeout),
            "QLIK_WS_RETRIES": str(self.ws_retries),
        }
        if self.client_cert_path:
            env["QLIK_CLIENT_CERT_PATH"] = self.client_cert_path
        if self.client_key_path:
            env["QLIK_CLIENT_KEY_PATH"] = self.client_key_path
        if self.ca_cert_path:
            env["QLIK_CA_CERT_PATH"] = self.ca_cert_path
        if self.http_port:
            env["QLIK_HTTP_PORT"] = str(self.http_port)
        return env

    def summary(self) -> str:
        """Human-readable config summary (no secrets)."""
        if self.use_vertex_ai:
            auth_line = f"Gemini Auth : Vertex AI (project={self.vertex_project}, location={self.vertex_location})"
        else:
            auth_line = "Gemini Auth : API key"
        return (
            f"Qlik Server : {self.server_url}\n"
            f"User        : {self.user_directory}/{self.user_id}\n"
            f"Gemini Model: {self.gemini_model}\n"
            f"{auth_line}\n"
            f"SSL Verify  : {self.verify_ssl}\n"
            f"Certs       : {'configured' if self.client_cert_path else 'not set'}"
        )
