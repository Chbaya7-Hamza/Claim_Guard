"""Tolerant JSONL reading shared by ingestion and the rule runner.

A judge's file may come from Windows (UTF-8 BOM, CRLF), hold a stray invalid byte, a claim whose text
contains U+2028, or an integer with thousands of digits. None of these may abort the run or silently
lose a neighbouring claim: each bad line is reported and the next one is read.
"""
import json


def read_lines(path):
    """Yield (line_number, text_or_None, error_or_None) for every non-blank line.

    Splits on b"\n" only (str.splitlines would also split on U+2028 inside a JSON string), tolerates a
    leading BOM and CRLF, and decodes each line on its own so one invalid byte costs one line.
    """
    with open(path, 'rb') as f:
        for n, raw in enumerate(f, start=1):
            if n == 1 and raw.startswith(b'\xef\xbb\xbf'):
                raw = raw[3:]
            raw = raw.rstrip(b'\r\n')
            if not raw.strip():
                continue
            try:
                yield n, raw.decode('utf-8'), None
            except UnicodeDecodeError as e:
                yield n, None, f'Invalid UTF-8: {e}'


def parse_json(text):
    """(value, None) or (None, error). ValueError also covers an over-long integer, RecursionError deep nesting."""
    try:
        return json.loads(text), None
    except (ValueError, RecursionError) as e:
        return None, f'Invalid JSON: {str(e)[:200]}'
