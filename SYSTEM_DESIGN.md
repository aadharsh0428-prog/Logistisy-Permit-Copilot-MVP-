# System Design — Logistisy Permit Copilot

See README.md for setup. This documents the architecture rationale, model choice,
and edge cases handled.

## Local LLM choice: Llama 3.2 Vision (via Ollama)

Evaluated Llama 3.2 Vision vs Gemma 3 for document OCR + structured extraction:

| Model | Document JSON extraction accuracy | Notes |
|---|---|---|
| Llama 3.2 Vision (11B) | Solid, single-call OCR+extraction | Slower (~seconds/page on CPU) but reliable, no separate OCR step needed |
| Gemma 3 (27B) | ~43% (benchmarked) | Surprisingly weak on structured fields — hallucinations, omitted values, swapped words |
| Qwen2.5-VL (32B/72B) | ~75% (benchmarked, highest of open models) | Best accuracy but heavier hardware requirement — documented as a drop-in upgrade |

**Decision:** Default to Llama 3.2 Vision for the MVP (best balance of accuracy and
resource requirements for a laptop/demo environment). Qwen2.5-VL is a one-line
config swap (`OLLAMA_VISION_MODEL=qwen2.5-vl`) if better hardware is available.

Grounded chat uses Llama 3.1 (text-only) since it only reasons over already-extracted
permit text, not images — cheaper and faster than routing through the vision model.

**Why local instead of a cloud API:** No API key, no per-request cost, and — importantly
for a compliance/permit product — the document never leaves the local/self-hosted
infrastructure. That's a genuine selling point for logistics companies handling
sensitive route and cargo data.

## Flow

1. Upload → `POST /documents` (dedup via checksum, format validation)
2. Llama 3.2 Vision reads the image directly → returns structured JSON in one call
   (permit metadata, route segments, escorts, conditions with confidence scores)
3. Structured data written to `permits`, `permit_segments`, `permit_conditions`,
   `escort_requirements`
4. Confidence scoring per condition → `needs_review` flag drives dashboard warnings
5. Grounded chat (Llama 3.1) → answers built strictly from `permit_conditions.raw_text`
   spans, with a hard-coded refusal ("This isn't specified...") when no matching
   context exists

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
- **Ollama unreachable edge case:** both `extract_from_image` and `grounded_answer`
  catch `httpx.HTTPError` and fall back to a deterministic mock/short-circuit answer,
  so a stopped Ollama container never crashes the demo mid-interview
- **Hallucinated raw_text edge case:** extraction prompt requires `raw_text` to be an
  exact excerpt from the document, not a paraphrase — reduces fabricated conditions

## Not yet implemented (documented as next steps)

- Multi-page PDF handling (currently assumes single-page/single-image upload;
  production would split PDF pages and merge per-page extractions)
- Auth/JWT + multi-tenant scoping
- Background job queue (Celery/RQ) — MVP runs extraction synchronously on upload
  for demo simplicity (acceptable since Llama 3.2 Vision inference is already the
  bottleneck)
- Multi-Bundesland cross-permit validation
- Streaming responses from Ollama for perceived latency improvement in the UI
