"""
AI Capability Demo — File Upload Processor
Multi-format parser: CSV, JSON, YAML, PDF, DOCX, text with encoding detection.
AGENTS.md Section 4.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Supported extensions (lowercase, with leading dot)
SUPPORTED_EXTENSIONS: Set[str] = {
    ".csv", ".json", ".yaml", ".yml", ".txt", ".log",
    ".pdf", ".docx", ".tf", ".conf",
}


class FileUploadProcessor:
    """Parse and validate uploaded files of various formats.

    Usage::

        processor = FileUploadProcessor()
        if processor.validate_upload(file, {".csv", ".json"}):
            result = processor.process(file)
    """

    # ── Public entry point ───────────────────────────────────────────────

    def process(self, uploaded_file: Any) -> Dict[str, Any]:
        """Route to the correct parser based on file extension.

        Returns a dict with keys:
            filename:  str
            extension: str
            type:      'dataframe' | 'dict' | 'text'
            data:      pd.DataFrame | dict | str
            rows:      int (if dataframe)
            columns:   int (if dataframe)
        """
        name: str = getattr(uploaded_file, "name", "unknown")
        ext = Path(name).suffix.lower()

        result: Dict[str, Any] = {
            "filename": name,
            "extension": ext,
        }

        try:
            if ext == ".csv":
                df = self.parse_csv(uploaded_file)
                result.update(type="dataframe", data=df, rows=len(df), columns=len(df.columns))
            elif ext == ".json":
                df = self.parse_json(uploaded_file)
                result.update(type="dataframe", data=df, rows=len(df), columns=len(df.columns))
            elif ext in {".yaml", ".yml"}:
                data = self.parse_yaml(uploaded_file)
                result.update(type="dict", data=data)
            elif ext == ".pdf":
                text = self.parse_pdf(uploaded_file)
                result.update(type="text", data=text)
            elif ext == ".docx":
                text = self.parse_docx(uploaded_file)
                result.update(type="text", data=text)
            elif ext in {".txt", ".log", ".tf", ".conf"}:
                text = self.parse_text(uploaded_file)
                result.update(type="text", data=text)
            else:
                result.update(type="error", data=f"Unsupported file extension: {ext}")

        except Exception as exc:
            logger.exception("Failed to process file %s", name)
            result.update(type="error", data=str(exc))

        return result

    # ── Individual parsers ───────────────────────────────────────────────

    def parse_csv(self, file: Any) -> pd.DataFrame:
        """Parse a CSV file into a DataFrame."""
        raw = self._read_bytes(file)
        encoding = self.detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        return pd.read_csv(io.StringIO(text))

    def parse_json(self, file: Any) -> pd.DataFrame:
        """Parse a JSON file into a DataFrame.

        Handles both a JSON array of objects and a single object (wrapped in a list).
        """
        raw = self._read_bytes(file)
        encoding = self.detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        payload = json.loads(text)

        if isinstance(payload, list):
            return pd.json_normalize(payload)
        if isinstance(payload, dict):
            # If the dict has a single key whose value is a list, normalise that
            for key, val in payload.items():
                if isinstance(val, list):
                    return pd.json_normalize(val)
            return pd.json_normalize([payload])
        return pd.DataFrame([{"value": payload}])

    def parse_yaml(self, file: Any) -> Dict[str, Any]:
        """Parse a YAML file into a dict."""
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML parsing. Install with: pip install pyyaml") from exc

        raw = self._read_bytes(file)
        encoding = self.detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {"data": data}

    def parse_pdf(self, file: Any) -> str:
        """Extract text from a PDF using PyMuPDF (fitz)."""
        try:
            import fitz  # PyMuPDF  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("PyMuPDF is required for PDF parsing. Install with: pip install pymupdf") from exc

        raw = self._read_bytes(file)
        doc = fitz.open(stream=raw, filetype="pdf")
        pages: List[str] = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
        doc.close()
        return "\n\n--- Page Break ---\n\n".join(pages)

    def parse_docx(self, file: Any) -> str:
        """Extract text from a DOCX using python-docx."""
        try:
            import docx  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("python-docx is required for DOCX parsing. Install with: pip install python-docx") from exc

        raw = self._read_bytes(file)
        doc = docx.Document(io.BytesIO(raw))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    def parse_text(self, file: Any) -> str:
        """Parse a plain-text file with auto-detected encoding."""
        raw = self._read_bytes(file)
        encoding = self.detect_encoding(raw)
        return raw.decode(encoding, errors="replace")

    # ── Encoding detection ───────────────────────────────────────────────

    def detect_encoding(self, raw_bytes: bytes) -> str:
        """Detect encoding of raw bytes. Prefers strict UTF-8 (the overwhelming
        majority of uploaded text/code/policy files) over chardet's statistical
        guess — chardet is unreliable on short, mostly-ASCII files with a
        handful of multi-byte UTF-8 characters (smart quotes, em dashes),
        often misdetecting them as Windows-1252 and producing mojibake."""
        if not raw_bytes:
            return "utf-8"

        try:
            raw_bytes.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            pass

        try:
            import chardet  # type: ignore[import-untyped]
        except ImportError:
            return "utf-8"

        result = chardet.detect(raw_bytes)
        encoding = result.get("encoding") or "utf-8"
        confidence = result.get("confidence", 0)

        # Fall back to UTF-8 for low-confidence results
        if confidence < 0.5:
            encoding = "utf-8"

        return encoding

    # ── Validation ───────────────────────────────────────────────────────

    def validate_upload(
        self,
        file: Any,
        allowed_extensions: Optional[Set[str]] = None,
    ) -> bool:
        """Validate an uploaded file against allowed extensions.

        Args:
            file: Streamlit UploadedFile or any object with a `name` attr.
            allowed_extensions: Set of extensions (with dot), e.g. {'.csv', '.json'}.
                                Defaults to SUPPORTED_EXTENSIONS.

        Returns:
            True if the file passes validation.
        """
        allowed = allowed_extensions or SUPPORTED_EXTENSIONS
        name: str = getattr(file, "name", "")
        if not name:
            logger.warning("Upload validation failed: file has no name attribute")
            return False

        ext = Path(name).suffix.lower()
        if ext not in allowed:
            logger.warning("Upload validation failed: %s not in %s", ext, allowed)
            return False

        # Basic size check (max 200 MB)
        size = getattr(file, "size", None)
        if size is not None and size > 200 * 1024 * 1024:
            logger.warning("Upload validation failed: file too large (%d bytes)", size)
            return False

        return True

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _read_bytes(file: Any) -> bytes:
        """Read raw bytes from a Streamlit UploadedFile or file-like object."""
        if hasattr(file, "getvalue"):
            return file.getvalue()
        if hasattr(file, "read"):
            pos = file.tell() if hasattr(file, "tell") else 0
            data = file.read()
            if hasattr(file, "seek"):
                file.seek(pos)
            return data if isinstance(data, bytes) else data.encode("utf-8")
        raise TypeError(f"Cannot read bytes from {type(file).__name__}")
