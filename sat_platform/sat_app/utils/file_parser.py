"""Utilities for parsing uploaded files into question blocks."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, List


def _clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse_plain_text(stream: BinaryIO, filename: str) -> List[dict]:
    content = stream.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="ignore")
    blocks: List[dict] = []
    current: List[str] = []
    for line in content.splitlines():
        if not line.strip():
            if current:
                blocks.append(
                    {
                        "type": "text",
                        "content": _clean_text("\n".join(current)),
                        "metadata": {"source": filename},
                    }
                )
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(
            {
                "type": "text",
                "content": _clean_text("\n".join(current)),
                "metadata": {"source": filename},
            }
        )
    return blocks


def parse_file(stream: BinaryIO, filename: str) -> List[dict]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        stream.seek(0)
        return parse_plain_text(stream, filename)
    stream.seek(0)
    data = stream.read()
    if isinstance(data, bytes):
        data_b64 = data.hex()
    else:
        data_b64 = data.encode("utf-8").hex()
    return [
        {
            "type": "image" if suffix in {".png", ".jpg", ".jpeg"} else "binary",
            "content": "",
            "metadata": {"source": filename, "payload_hex": data_b64[:1024]},
        }
    ]

