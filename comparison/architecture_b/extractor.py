"""
File ingestion / extraction layer.

Detects the uploaded file's type and routes it to the right extractor.
Every extractor returns the same normalized shape:

{
    "text": "...all extracted text...",
    "tables": [...],
    "metadata": {
        "filename": "...",
        "pages": ...,
        ...
    }
}
"""

import os
import mimetypes
from pathlib import Path
from typing import Any, Dict, List

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".csv",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".txt",
}

# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def extract(file_path: str) -> Dict[str, Any]:
    """
    Detect the file type and dispatch to the matching extractor.
    Returns the normalized {text, tables, metadata} dict.
    """
    file_path = str(file_path)
    ext = Path(file_path).suffix.lower()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    
    dispatch = {
        ".pdf": extract_pdf,
        ".docx": extract_docx,
        ".xlsx": extract_excel,
        ".xls": extract_excel,
        ".csv": extract_csv,
        ".png": extract_image,
        ".jpg": extract_image,
        ".jpeg": extract_image,
        ".tiff": extract_image,
        ".tif": extract_image,
        ".txt": extract_txt,   # <-- add this line
    }
    
    

    handler = dispatch.get(ext)
    if handler is None:
        # fall back to mimetype sniffing for weird/missing extensions
        mime, _ = mimetypes.guess_type(file_path)
        raise ValueError(
            f"Unsupported file type '{ext}' (mimetype guess: {mime}) for {file_path}"
        )

    return handler(file_path)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def extract_txt(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    return {
        "text": text.strip(),
        "tables": [],
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": 1,
            "source_type": "txt",
        },
    }
def extract_pdf(file_path: str) -> Dict[str, Any]:
    import pdfplumber

    text_parts: List[str] = []
    tables: List[Dict[str, Any]] = []

    with pdfplumber.open(file_path) as pdf:
        num_pages = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

            for table_index, table in enumerate(page.extract_tables()):
                tables.append({
                    "page": page_num,
                    "table_index": table_index,
                    "data": table,  # list of rows, each row a list of cell strings
                })

        pdf_metadata = pdf.metadata or {}

    # If no text layer was found at all, this is likely a scanned PDF.
    combined_text = "\n\n".join(text_parts).strip()
    is_scanned = len(combined_text) == 0

    result = {
        "text": combined_text,
        "tables": tables,
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": num_pages,
            "source_type": "pdf",
            "is_scanned": is_scanned,
            "title": pdf_metadata.get("Title"),
            "author": pdf_metadata.get("Author"),
        },
    }

    if is_scanned:
        # Fall back to OCR per page for scanned/raster PDFs
        result = _ocr_pdf_fallback(file_path, result)

    return result


def _ocr_pdf_fallback(file_path: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """OCR each page of a scanned PDF via pypdfium2 + pytesseract."""
    import pypdfium2 as pdfium
    import pytesseract

    pdf = pdfium.PdfDocument(file_path)
    ocr_text_parts = []
    for page in pdf:
        bitmap = page.render(scale=200 / 72)  # ~200 DPI
        pil_image = bitmap.to_pil()
        ocr_text_parts.append(pytesseract.image_to_string(pil_image))

    result["text"] = "\n\n".join(ocr_text_parts).strip()
    result["metadata"]["ocr_applied"] = True
    return result


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def extract_docx(file_path: str) -> Dict[str, Any]:
    from docx import Document

    doc = Document(file_path)

    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]

    tables: List[Dict[str, Any]] = []
    for table_index, table in enumerate(doc.tables):
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        tables.append({"table_index": table_index, "data": rows})

    return {
        "text": "\n".join(text_parts),
        "tables": tables,
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": None,  # docx has no fixed page count without rendering
            "source_type": "docx",
            "paragraph_count": len(doc.paragraphs),
        },
    }


# ---------------------------------------------------------------------------
# Excel (.xlsx / .xls)
# ---------------------------------------------------------------------------

def extract_excel(file_path: str) -> Dict[str, Any]:
    import pandas as pd

    sheets = pd.read_excel(file_path, sheet_name=None)  # dict of {sheet_name: df}

    tables: List[Dict[str, Any]] = []
    text_parts: List[str] = []

    for sheet_name, df in sheets.items():
        tables.append({
            "sheet_name": sheet_name,
            "data": df.fillna("").values.tolist(),
            "columns": df.columns.tolist(),
        })
        # Flattened text representation, useful for embedding/search
        text_parts.append(f"--- Sheet: {sheet_name} ---\n{df.to_string(index=False)}")

    return {
        "text": "\n\n".join(text_parts),
        "tables": tables,
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": len(sheets),  # treat each sheet as a "page"
            "source_type": "excel",
            "sheet_names": list(sheets.keys()),
        },
    }


def extract_csv(file_path: str) -> Dict[str, Any]:
    import pandas as pd

    df = pd.read_csv(file_path)

    return {
        "text": df.to_string(index=False),
        "tables": [{"data": df.fillna("").values.tolist(), "columns": df.columns.tolist()}],
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": 1,
            "source_type": "csv",
            "row_count": len(df),
        },
    }


# ---------------------------------------------------------------------------
# Images (OCR)
# ---------------------------------------------------------------------------

def extract_image(file_path: str) -> Dict[str, Any]:
    import pytesseract
    from PIL import Image

    image = Image.open(file_path)
    text = pytesseract.image_to_string(image)

    return {
        "text": text.strip(),
        "tables": [],
        "metadata": {
            "filename": os.path.basename(file_path),
            "pages": 1,
            "source_type": "image",
            "dimensions": image.size,  # (width, height)
        },
    }


# ---------------------------------------------------------------------------
# Structured JSON claim extraction
# ---------------------------------------------------------------------------
#
# Whatever format the claim comes in (pdf, docx, image, scanned page...),
# extract() above already turns it into raw text via the right path (text
# layer, OCR fallback, etc). The function below takes that raw text and
# asks the LLM to turn it into ONE valid JSON object matching the claim
# schema, regardless of how the original document was laid out.

import json
import re


CLAIM_JSON_SCHEMA_PROMPT = """You are a data extraction engine for healthcare claims.

You will be given raw text extracted from a claim document (it may be messy,
OCR'd, or oddly formatted). Extract the claim information into EXACTLY this
JSON structure. Use null for any field you cannot find in the text -- never
invent or guess a value.

{
  "claim_id": "string or null",
  "patient": {"id": "string or null", "name": "string or null"},
  "provider": {"id": "string or null", "name": "string or null"},
  "facility": "string or null",
  "encounter": {"id": "string or null", "date": "string or null"},
  "service_date": "string or null",
  "coverage": {"payer": "string or null", "start_date": "string or null", "end_date": "string or null"},
  "authorization": {"id": "string or null", "status": "string or null"},
  "diagnoses": ["string", "..."],
  "procedures": [{"code": "string", "description": "string or null"}],
  "claim_lines": [{"line_id": "string or null", "procedure_code": "string or null", "quantity": "number or null", "amount": "number or null"}],
  "amounts": {"total_billed": "number or null"},
  "attachments": ["string", "..."]
}

Return ONLY the JSON object. No markdown fences, no explanation, no extra text.

RAW EXTRACTED TEXT:
---
{raw_text}
---
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def build_local_llm(max_tokens: int = 800):
    """The same local Ollama endpoint Architecture A's own OllamaExplanationProvider
    uses (src/llm_adapter.py) -- gemma3:4b, fully offline, no API key leaves
    this machine. Swapped in here so both systems in the comparison run the
    literal same model instance; nothing else about extraction changes."""
    from langchain_openai import ChatOpenAI
    # Default: local Ollama gemma3:4b (the original comparison). The harness can repoint BOTH
    # systems at one other model via COMPARISON_PROVIDER=featherless + COMPARISON_LLM_MODEL
    # (see scripts/run_architecture_comparison.py); nothing else about extraction changes.
    if os.environ.get("COMPARISON_PROVIDER") == "featherless":
        base_url = "https://api.featherless.ai/v1"
        api_key = os.environ["FEATHERLESS_API_KEY"]
        model = os.environ["COMPARISON_LLM_MODEL"]
    else:
        base_url = "http://localhost:11434/v1"
        api_key = "ollama-local"  # Ollama ignores the key; a placeholder, not a secret
        model = "gemma3:4b"
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        temperature=0,
    )


def extract_claim_json(file_path: str, llm=None, max_retries: int = 1) -> Dict[str, Any]:
    """
    Full pipeline: extract() the file (whatever format it is) -> raw text ->
    LLM turns that raw text into ONE valid JSON object matching the claim
    schema. Returns a plain Python dict guaranteed to be valid JSON.

    llm: any object with an .invoke(str) -> response with .content (e.g. the
    build_local_llm() instance already used in agent.py). If not passed,
    one is created here pointed at the local gemma3:4b Ollama endpoint.
    """
    raw = extract(file_path)
    raw_text = raw.get("text", "")

    if not raw_text.strip():
        # Nothing was extracted at all (e.g. OCR found nothing) -- don't
        # send an empty prompt to the LLM, surface this clearly instead.
        raise ValueError(
            f"No text could be extracted from {file_path}; cannot build a claim JSON from it."
        )

    if llm is None:
        llm = build_local_llm()

    prompt = CLAIM_JSON_SCHEMA_PROMPT.replace("{raw_text}", raw_text)

    last_err = None
    for _ in range(max_retries + 1):
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):  # some providers return content blocks
            content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        cleaned = _strip_code_fence(content)
        try:
            claim_json = json.loads(cleaned)
            claim_json["_source_file"] = os.path.basename(file_path)  # traceability, not guessed data
            return claim_json
        except json.JSONDecodeError as e:
            last_err = e
            prompt = (
                f"Your previous output was not valid JSON (error: {e}). "
                f"Return ONLY the JSON object, no markdown, no extra text.\n\n{prompt}"
            )

    raise ValueError(f"Could not get valid JSON from the LLM after retries: {last_err}")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python extractor.py <file_path>")
        sys.exit(1)

    if "--json-claim" in sys.argv:
        path = [a for a in sys.argv[1:] if a != "--json-claim"][0]
        claim = extract_claim_json(path)
        print(json.dumps(claim, indent=2, ensure_ascii=False))
    else:
        result = extract(sys.argv[1])
        print(json.dumps(result, indent=2, default=str)[:2000])