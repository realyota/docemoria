from __future__ import annotations

import hashlib


def stable_content_checksum(content: str) -> str:
    """Return a deterministic checksum for textual content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
