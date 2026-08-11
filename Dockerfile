# "Ask Tapestry" RAG API. Ollama runs as a separate service (see docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

# deps first for layer caching
COPY requirements.txt requirements-core.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# TAPESTRY_DATA_DIR / OPENAI_BASE_URL etc. are provided by compose or the host env.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
