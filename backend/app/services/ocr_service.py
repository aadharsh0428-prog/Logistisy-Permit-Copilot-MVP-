"""
File utilities. With Llama 3.2 Vision handling OCR + extraction in one call
(see llm_client.py), this service is now responsible only for checksum-based
dedup and basic file validation — not text extraction.
"""
import hashlib


class OCRService:
    @staticmethod
    def checksum(file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def is_supported_type(filename: str) -> bool:
        return filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
