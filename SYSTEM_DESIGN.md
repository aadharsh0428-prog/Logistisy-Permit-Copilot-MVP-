# System Design — Logistisy Permit Copilot

See README.md for setup. This documents the architecture rationale, model choice,
and edge cases handled.

## Model choice: Gemini, with an ensemble fallback

Evaluated Gemini vs Gemma 3 vs Qwen2.5-VL for document OCR + structured extraction:

| Model | Document JSON extraction accuracy | Deployment | Notes |
|---|---|---|---|
| Gemini 2.5 Flash | Highest accuracy of models evaluated | Cloud API | Best structured-field accuracy, strong JSON adherence, but subject to free-tier rate limits |
| Gemma 3 (27B) | ~43% (benchmarked) | Local (Ollama) | Weak on structured fields — hallucinations, omitted values, swapped words |
| Qwen2.5-VL (32B/72B) | ~75% (benchmarked, highest of open models) | Local (Ollama) | Good accuracy but heavy hardware requirement, ruled out to keep infra simple |

**Decision:** Use Gemini for both extraction and grounded chat, since it gave the
most reliable structured output with the least hallucination in testing. The
tradeoff is Gemini's free tier enforcing per-minute and per-day request quotas,
which risks failed requests during a demo or any burst of uploads.

## Why an ensemble instead of a single API key/model

Rather than upgrading to a paid tier immediately, the backend implements a
lightweight **ensemble client** in `llm_client.py`:

- Holds a pool of Gemini API keys (`GEMINI_API_KEYS`, comma-separated) and a pool
  of model variants (`GEMINI_MODEL_POOL`, e.g. `gemini-2.5-flash`, `gemini-2.0-flash`,
  `gemini-1.5-flash`)
- On a successful call, the response is used as-is
- On an HTTP 429 (rate limited) or 503 (overloaded) response, the client rotates
  to the next key/model combination in the pool and retries, with exponential
  backoff between attempts
- Only after every key/model combination in the pool has been exhausted does the
  client fall back to a deterministic short-circuit response, so the demo never
  hard-crashes on a rate limit
- This effectively multiplies the usable free-tier quota by the number of keys
  and models in the pool, since each key/model pair has its own independent
  rate-limit bucket on Google's side

**Why not just use one key and accept occasional failures:** for a live interview
or demo setting, a single rate-limited request mid-demo looks like a broken
product. The ensemble adds resilience for near-zero additional cost, at the price
of slightly more complex client code.

**Why not go straight to local models (Llama/Gemma) instead:** Gemini's accuracy
in testing was meaningfully higher, particularly for reliably filling every
structured field without hallucinating values, which matters more for a permit
compliance tool than avoiding cloud dependency at the MVP stage. Local models
remain documented as a future option if data-residency requirements become a
hard constraint for a customer.

## End-to-end flow

1. Upload → `POST /documents` (dedup via checksum, format validation)
2. Ensemble client picks the first available Gemini key/model, sends the image →
   returns structured JSON in one call (permit metadata, route segments, escorts,
   conditions with confidence scores)
3. If rate-limited, ensemble client rotates to the next key/model and retries
4. Structured data written to `permits`, `permit_segments`, `permit_conditions`,
   `escort_requirements`
5. Confidence scoring per condition → `needs_review` flag drives dashboard warnings
6. Grounded chat (Gemini, same ensemble client) → answers built strictly from
   `permit_conditions.raw_text` spans, with a hard-coded refusal
   ("This isn't specified...") when no matching context exists

## Key edge cases in this codebase

- Duplicate upload detection via SHA-256 checksum (`documents.checksum`)
- Unsupported file type / empty file rejected before processing
- Low-confidence extracted fields flagged `needs_review=True`, surfaced with a
  warning in the UI
- Expired permit detection compares `valid_until` against current date in the dashboard
- Multiple legal bases stored as an array (`legal_basis` JSONB), not a single enum
- Chat falls back to "not specified in this permit" when no grounding context exists
- Failed processing sets `document.status = failed` with `error_message`, never a
  silent crash
- **LLM output parsing edge case:** the extraction prompt enforces raw JSON output,
  but `_parse_json_response` strips markdown fences defensively in case the model
  wraps its answer in ```json blocks
- **Gemini rate-limit edge case:** the ensemble client catches 429/503 responses
  per key/model pair and rotates through the pool with exponential backoff before
  falling back to a deterministic response, so hitting a free-tier quota never
  crashes the demo mid-interview
- **Hallucinated raw_text edge case:** extraction prompt requires `raw_text` to be
  an exact excerpt from the document, not a paraphrase — reduces fabricated
  conditions

## Not yet implemented (documented as next steps)

- Multi-page PDF handling (currently assumes single-page/single-image upload;
  production would split PDF pages and merge per-page extractions)
- Auth/JWT + multi-tenant scoping
- Background job queue (Celery/RQ) — MVP runs extraction synchronously on upload
  for demo simplicity
- Multi-Bundesland cross-permit validation
- Streaming responses from Gemini for perceived latency improvement in the UI
- Paid-tier Gemini quota as a longer-term replacement for the free-tier ensemble
