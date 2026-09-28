"""
document_loader.py

Bridges extractor.py (one dict per file: {text, tables, metadata})
to the flat list[str] of chunks that agent.py needs for embedding + FAISS.
"""

from pathlib import Path
from typing import List

from extractor import extract
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".csv",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".txt",
}


# Tune these based on your documents. Sentences/short notes -> smaller chunk_size.
# Dense course PDFs -> 500-1000 is usually a reasonable start.
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 50     # overlap so we don't cut a sentence in half between chunks


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Simple sliding-window chunker (no extra dependency needed)."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap  # slide forward, keeping overlap
    return chunks


def get_documents(source: str) -> List[str]:
    """
    source: path to a single file OR a folder containing files.
    Returns a flat list of text chunks ready for embedding.
    """
    source_path = Path(source)

    if source_path.is_file():
        file_paths = [source_path]
    elif source_path.is_dir():
        file_paths = sorted(
            p for p in source_path.rglob("*")
            if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    else:
        raise FileNotFoundError(f"Path not found: {source}")

    if not file_paths:
        raise ValueError(f"No supported files found in: {source}")

    all_chunks: List[str] = []
    for file_path in file_paths:
        try:
            result = extract(str(file_path))
        except Exception as e:
            print(f"[document_loader] Skipping {file_path.name}: {e}")
            continue

        text = result.get("text", "")
        chunks = _chunk_text(text)
        all_chunks.extend(chunks)
        print(f"[document_loader] {file_path.name}: {len(chunks)} chunk(s)")

    if not all_chunks:
        raise ValueError("No text could be extracted from any of the provided files.")

    return all_chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python document_loader.py <file_or_folder>")
        sys.exit(1)

    docs = get_documents(sys.argv[1])
    print(f"\nTotal chunks: {len(docs)}")
    if docs:
        print("First chunk preview:\n", docs[0][:200])