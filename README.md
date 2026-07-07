# Logistisy Permit Copilot (MVP)

AI-assisted workspace that turns heavy-transport (Schwertransport) permit documents into
structured, actionable data — route restrictions, escort requirements, time windows, and
a grounded chat assistant that answers questions using only the permit's own text.

Runs entirely on **local, open-source LLMs via Ollama** — no API keys, no cloud cost,
no data leaving your machine. Styled after logistisy.com (navy + gold).

## Stack

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **Queue/cache:** Redis
- **AI (fully local):**
  - **Llama 3.2 Vision** (via Ollama) — reads the permit image/PDF page directly and
    extracts structured JSON in a single call (OCR + extraction combined)
  - **Llama 3.1** (via Ollama) — grounded Q&A over the extracted permit text
  - Swap `OLLAMA_VISION_MODEL=qwen2.5-vl` in `.env` for higher extraction accuracy
    if your hardware supports a larger model (see SYSTEM_DESIGN.md for benchmarks)
- **Infra:** Docker Compose (one command to run everything)

## Why Llama 3.2 Vision over Gemma 3

Benchmarked document-to-JSON extraction accuracy showed Gemma 3 underperforming
(~43%) with more hallucinations and omitted fields, while Llama 3.2 Vision handles
OCR and structured extraction reliably in one pass. Full rationale in
`SYSTEM_DESIGN.md`.

## Architecture

```
frontend (React) --> backend (FastAPI) --> Postgres
                             |--> Redis (job status)
                             |--> Ollama (Llama 3.2 Vision: extraction)
                             |--> Ollama (Llama 3.1: grounded chat)
```

## Project Structure

```
logistisy-permit-copilot/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routers/
│   │   │   ├── documents.py
│   │   │   ├── permits.py
│   │   │   └── chat.py
│   │   └── services/
│   │       ├── ocr_service.py        # file validation + checksum dedup
│   │       ├── extraction_service.py # orchestrates vision-model extraction -> DB
│   │       └── llm_client.py         # Ollama client (Llama 3.2 Vision + Llama 3.1)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── src/ (components, api client, theme.css)
├── docker-compose.yml   # includes db, redis, ollama, backend, frontend
└── SYSTEM_DESIGN.md
```

## Running locally

```bash
cp backend/.env.example backend/.env

docker compose up --build

# In a separate terminal, pull the models into the Ollama container (first run only):
docker compose exec ollama ollama pull llama3.2-vision
docker compose exec ollama ollama pull llama3.1
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Ollama API: http://localhost:11434

**No GPU?** Remove the `deploy.resources` GPU block in `docker-compose.yml` — Ollama
will run on CPU (extraction will be slower, ~1-2 minutes per document, still fine
for a live interview demo with 1-2 sample permits).

## Core flow

1. Upload a permit PDF/image → `POST /documents`
2. Llama 3.2 Vision reads the image and extracts structured data in one call
3. Dashboard shows structured conditions, route segments, escort requirements,
   confidence scores
4. Ask the copilot questions — Llama 3.1 answers are grounded strictly in the
   permit's own extracted text

## Edge cases handled (see SYSTEM_DESIGN.md)

- Duplicate upload detection (checksum)
- Unsupported/empty file rejection
- Low-confidence fields flagged for human review
- Expired permit detection
- Multiple legal bases per permit
- Hallucination containment in chat ("not specified in this permit")
- Ollama unreachable → deterministic fallback instead of a crash
- Malformed LLM JSON output → defensive parsing strips markdown fences

## Next steps beyond MVP

- Multi-page PDF splitting and per-page extraction merge
- Auth (JWT) + multi-tenant scoping
- Background job queue (Celery/RQ) instead of synchronous processing
- Multi-Bundesland cross-permit validation
- Streaming Ollama responses for better perceived latency
