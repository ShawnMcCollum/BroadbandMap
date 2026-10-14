# Development image for the Streamlit dashboard.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

# Keep the virtual environment outside /app, so the source bind mount used in
# development does not hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.runOnSave=true", "--server.fileWatcherType=poll", "--browser.gatherUsageStats=false"]
