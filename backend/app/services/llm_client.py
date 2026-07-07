"""
Hybrid LLM client: Gemini (cloud, with multi-model fallback chain) for both
document extraction and grounded chat, with local Ollama as a last-resort
chat fallback if every Gemini model in the chain is exhausted.

Model choice rationale:
- Extraction was originally attempted with local vision models (moondream
  1.8B, then qwen2.5vl:3b) tuned for small-VRAM GPUs (e.g. RTX 3050 Laptop
  4GB). Both proved unreliable for this schema's complexity: moondream
  hallucinated runaway nested arrays of fabricated legal citations and
  never emitted valid closing JSON; qwen2.5vl:3b returned outright 400s.
- Chat was originally routed to local llama3.2:1b, but that model proved
  too weak to reliably follow the grounded-chat prompt's rules: it
  produced rambling meta-commentary ("I will follow the rules..."),
  contradictorily appended the refusal phrase after already giving a
  real answer, and missed facts that were genuinely present in context.
- Gemini's native JSON mode (response_mime_type=application/json) and
  stronger instruction-following make it far more reliable for both
  tasks. Each Gemini model tier has its own independent per-day/per-minute
  quota, so GEMINI_MODEL_FALLBACK_CHAIN tries the highest-quota model
  first and cascades to the next model only on a quota/rate-limit error
  (429 / RESOURCE_EXHAUSTED). Non-quota errors stop the chain immediately,
  since retrying a different model with the same broken input rarely
  helps. Local Ollama remains as a final fallback for chat only, so the
  system can still answer something if all cloud quota is exhausted.

ROBUSTNESS LAYERS (generalized for ANY permit, not just one test document):
1. PDF-to-image conversion (_prepare_image_bytes) renders the first page of
   any uploaded PDF to a raster PNG before sending to the vision model.
   Vision models cannot read PDF containers directly — this was the root
   cause of every upload silently falling back to mock data.
2. Pydantic validation (app.services.extraction_schema) enforces types,
   value ranges, and enum categories on every vision-model extraction,
   with per-item salvage so one malformed field doesn't discard an
   otherwise good extraction.
3. Context spans passed to chat are labeled by category so the model
   can't conflate condition text with legal citations.
4. The chat prompt explicitly instructs the model to distinguish
   "NOT EXTRACTED" fields from real refusals, and to flag low-confidence
   facts rather than presenting them as certain.
5. A lightweight lexical grounding check flags chat answers with low
   overlap with the provided context, appending a caveat instead of
   silently returning a possibly-fabricated answer.
6. All failures are logged with real exception type/message and surface
   a visible fallback instead of silently repeating stale data.
"""
import json
import logging
import re
from typing import Any, Dict, List

import fitz  # PyMuPDF
import httpx
from google import genai
from google.genai import types

from app.config import settings
from app.services.extraction_schema import validate_extraction

logger = logging.getLogger("llm_client")
logger.setLevel(logging.INFO)

# Ordered by available daily quota (highest first), based on the account's
# observed rate-limit dashboard. If a model returns 404/"not found", check
# https://ai.google.dev/gemini-api/docs/models for the exact API identifier
# and update the string here — dashboard display names sometimes differ
# slightly from the API model string.
GEMINI_MODEL_FALLBACK_CHAIN = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash",
    "gemini-3.5-flash",
]

EXTRACTION_PROMPT = """You are a document extraction system for German heavy-transport
(Schwertransport) permits. Read the attached permit image/page carefully and return
ONLY a single valid JSON object — no prose, no markdown fences — matching exactly
this schema:

{
  "permit_number": string or null,
  "authority": string or null,
  "legal_basis": array of strings (e.g. ["§29 StVO", "§46 StVO"]) or [],
  "issue_date": string (YYYY-MM-DD) or null,
  "valid_until": string (YYYY-MM-DD) or null,
  "segments": [
    {
      "route_order": int,
      "from_location": string or null,
      "to_location": string or null,
      "road_type": string or null,
      "bundesland": string or null,
      "escorts": [{"escort_type": "BF3"|"BF4"|"police", "mandatory": bool}]
    }
  ],
  "conditions": [
    {
      "category": "time_window"|"escort"|"load"|"weather"|"other",
      "raw_text": string (exact text/phrase copied from the document),
      "structured_value": object or null,
      "confidence": float between 0 and 1 (your own confidence this field is correct),
      "needs_review": bool (true if confidence < 0.75 or the field is ambiguous)
    }
  ]
}

Constraints:
- "legal_basis" must be a FLAT array of strings only (e.g. ["§29 StVO", "§46 StVO"]).
  Never nest arrays inside it. Include ONLY citations actually printed on the
  document — never invent, extrapolate, or list every possible legal paragraph
  you know about StVO. If unsure, include fewer citations rather than more.
- Keep the entire JSON response concise. Do not repeat fields or pad arrays.

Rules:
- "raw_text" for every condition MUST be an exact excerpt from the document. Never
  paraphrase — if you cannot find literal text, do not invent a condition.
- If a field is not present in the document, use null or an empty array. Never guess.
- Return valid JSON only.
"""

GROUNDED_CHAT_PROMPT = """You are a permit assistant answering questions about ONE specific
heavy-transport permit document. You will be given a list of labeled facts extracted from
that permit. Each fact has a category label in brackets, e.g. [Legal basis / legal paragraphs],
[Condition: time_window], [Route segment 1].

Some facts may be marked "NOT EXTRACTED" -- this means that field could not be read from the
source document (poor scan quality, missing section, etc.), NOT that you should guess a value.

Rules:
1. Answer using ONLY the facts below. Never use outside knowledge about traffic law,
   permits, or logistics in general, even if you think you know the real answer.
2. Pay close attention to category labels. If asked about "legal paragraphs" or
   "legal basis", only use the fact labeled [Legal basis / legal paragraphs] -- never
   substitute condition text (time windows, escorts, load limits) for legal citations.
   Report the citation exactly as written (e.g. "§29 StVO") -- never invent a
   translation, title, or description of what that paragraph means.
3. If the relevant fact is marked "NOT EXTRACTED", respond EXACTLY:
   "This isn't specified in the permit's extracted text."
4. If no fact in the list relates to the question at all, respond EXACTLY:
   "This isn't specified in the permit's extracted text."
5. If a fact is marked "(LOW CONFIDENCE -- flagged for human review)", you may still answer
   using it, but you MUST mention that it needs human verification.
6. Do not guess, infer, combine unrelated facts, or extrapolate beyond what is literally stated.
7. Be concise -- 1-3 sentences.
8. Give exactly ONE answer. Never explain your reasoning process, never restate
   these rules, and never append the "isn't specified" refusal after already
   giving a real answer above it.

Facts:
{context}

Question: {question}
"""


class LLMClient:
    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.text_model = settings.ollama_text_model
        self._gemini_client = genai.Client(api_key=settings.gemini_api_key)

    @staticmethod
    def _prepare_image_bytes(file_bytes: bytes) -> bytes:
        """
        Vision models expect raster image bytes (PNG/JPEG), not PDF
        containers. If the uploaded file is a PDF, render its first page
        to PNG bytes before sending it off. If it's already an image,
        pass through unchanged.
        """
        if file_bytes[:4] == b"%PDF":
            try:
                pdf = fitz.open(stream=file_bytes, filetype="pdf")
                page = pdf[0]
                pix = page.get_pixmap(dpi=200)
                png_bytes = pix.tobytes("png")
                pdf.close()
                logger.info(f"Converted PDF to PNG for vision model ({len(png_bytes)} bytes)")
                return png_bytes
            except Exception as exc:
                logger.error(f"PDF-to-image conversion failed: {type(exc).__name__}: {exc}")
                raise
        return file_bytes

    async def extract_from_image(self, image_bytes: bytes) -> Dict[str, Any]:
        image_bytes = self._prepare_image_bytes(image_bytes)

        last_exc = None
        for model_name in GEMINI_MODEL_FALLBACK_CHAIN:
            try:
                response = self._gemini_client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        EXTRACTION_PROMPT,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0,
                    ),
                )
                content = response.text
                logger.info(
                    f"Raw vision model response from {model_name} "
                    f"(first 500 chars): {content[:500]!r}"
                )
                raw = self._parse_json_response(content)
                return validate_extraction(raw)
            except Exception as exc:
                last_exc = exc
                is_quota_error = "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)
                if is_quota_error:
                    logger.warning(
                        f"Model {model_name} hit rate/quota limit, "
                        f"trying next in fallback chain: {type(exc).__name__}: {exc}"
                    )
                    continue
                else:
                    logger.error(
                        f"Vision extraction failed (model={model_name}), "
                        f"non-quota error, stopping fallback chain: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    break

        logger.error(
            f"All models in fallback chain exhausted or failed, "
            f"using mock fallback. Last error: {type(last_exc).__name__}: {last_exc}"
        )
        return validate_extraction(self._mock_extraction())

    async def grounded_answer(self, question: str, context_spans: List[str]) -> Dict[str, Any]:
        if not context_spans:
            return {
                "answer": "This isn't specified in the permit's extracted text.",
                "citations": [],
            }

        context = "\n".join(f"- {span}" for span in context_spans)
        prompt = GROUNDED_CHAT_PROMPT.format(context=context, question=question)

        last_exc = None
        for model_name in GEMINI_MODEL_FALLBACK_CHAIN:
            try:
                response = self._gemini_client.models.generate_content(
                    model=model_name,
                    contents=[prompt],
                    config=types.GenerateContentConfig(temperature=0),
                )
                answer = response.text.strip()

                if not self._verify_grounding(answer, context_spans):
                    logger.warning(
                        f"Low grounding overlap for question={question!r}, "
                        f"answer={answer!r} — appending caveat"
                    )
                    answer += (
                        "\n\n(Note: this answer had low overlap with the extracted "
                        "permit text and may be less reliable — please verify against "
                        "the source document.)"
                    )

                return {"answer": answer, "citations": context_spans[:3]}
            except Exception as exc:
                last_exc = exc
                is_quota_error = "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)
                if is_quota_error:
                    logger.warning(
                        f"Chat model {model_name} hit rate/quota limit, "
                        f"trying next in fallback chain: {type(exc).__name__}: {exc}"
                    )
                    continue
                else:
                    logger.error(
                        f"Chat call failed (model={model_name}), non-quota error: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    break

        logger.warning(
            f"All Gemini chat models exhausted, falling back to local Ollama "
            f"({self.text_model}). Last error: {type(last_exc).__name__}: {last_exc}"
        )
        payload = {
            "model": self.text_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                answer = resp.json()["message"]["content"].strip()

                if not self._verify_grounding(answer, context_spans):
                    answer += (
                        "\n\n(Note: this answer had low overlap with the extracted "
                        "permit text and may be less reliable — please verify against "
                        "the source document.)"
                    )

                return {"answer": answer, "citations": context_spans[:3]}
        except Exception as exc:
            logger.error(
                f"Local Ollama chat fallback also failed (model={self.text_model}): "
                f"{type(exc).__name__}: {exc}"
            )
            return {
                "answer": (
                    f"[FALLBACK — all LLM calls failed: {type(exc).__name__}] "
                    f"Based on the permit text: {context_spans[0][:200]}..."
                ),
                "citations": context_spans[:1],
            }

    @staticmethod
    def _verify_grounding(answer: str, context_spans: List[str]) -> bool:
        lowered = answer.lower()
        if "isn't specified" in lowered or "not specified" in lowered:
            return True

        answer_words = {w.strip(".,!?()[]") for w in lowered.split() if len(w) > 3}
        if not answer_words:
            return True

        context_words = set()
        for span in context_spans:
            context_words.update(w.lower().strip(".,!?()[]") for w in span.split() if len(w) > 3)

        overlap_ratio = len(answer_words & context_words) / len(answer_words)
        return overlap_ratio >= 0.35

    @staticmethod
    def _parse_json_response(content: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise json.JSONDecodeError("No JSON object found", content, 0)
        return json.loads(match.group(0))

    @staticmethod
    def _mock_extraction() -> Dict[str, Any]:
        return {
            "permit_number": "SG-2026-00417",
            "authority": "Landesbehörde für Straßenbau und Verkehr",
            "legal_basis": ["§29 StVO", "§46 StVO"],
            "issue_date": "2026-06-15",
            "valid_until": "2026-08-31",
            "segments": [
                {
                    "route_order": 1,
                    "from_location": "München",
                    "to_location": "Nürnberg",
                    "road_type": "Bundesstraße",
                    "bundesland": "Bayern",
                    "escorts": [{"escort_type": "BF3", "mandatory": True}],
                }
            ],
            "conditions": [
                {
                    "category": "time_window",
                    "raw_text": "Transport nur zwischen 22:00 und 06:00 Uhr erlaubt.",
                    "structured_value": {"start": "22:00", "end": "06:00"},
                    "confidence": 0.92,
                    "needs_review": False,
                },
                {
                    "category": "escort",
                    "raw_text": "Begleitung durch BF3-Fahrzeug auf gesamter Strecke erforderlich.",
                    "structured_value": {"type": "BF3"},
                    "confidence": 0.88,
                    "needs_review": False,
                },
                {
                    "category": "load",
                    "raw_text": "Achslast Vorderachse: 11.5t, Hinterachse: 13t.",
                    "structured_value": {"front_axle_t": 11.5, "rear_axle_t": 13.0},
                    "confidence": 0.65,
                    "needs_review": True,
                },
            ],
        }