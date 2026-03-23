FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY qlik_sense_mcp_server/ ./qlik_sense_mcp_server/
COPY web_ui/ ./web_ui/

# Install dependencies (core + web UI)
RUN pip install --no-cache-dir -e ".[bedrock-ui]"

EXPOSE 8501

# Streamlit config: disable browser auto-open, bind to all interfaces
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

CMD ["python", "-m", "streamlit", "run", "web_ui/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true"]
