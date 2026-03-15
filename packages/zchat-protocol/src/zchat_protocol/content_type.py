"""ContentType — short ↔ MIME deterministic mapping."""

from __future__ import annotations

_ZCHAT_VND = "application/vnd.zchat."
_ZCHAT_EXT_VND = "application/vnd.zchat-ext."


def short_to_mime(short: str) -> str:
    """Convert a short content-type name to its MIME equivalent.

    Rules:
      1. Contains ``/`` → standard MIME, passthrough.
      2. Starts with ``ext.`` → ``application/vnd.zchat-ext.<rest>``.
      3. ACP namespace with 3+ dot-segments → last dot becomes hyphen.
      4. Otherwise → ``application/vnd.zchat.<short>``.
    """
    if "/" in short:
        return short

    if short.startswith("ext."):
        return f"{_ZCHAT_EXT_VND}{short[4:]}"

    parts = short.split(".")
    if len(parts) >= 3:
        # ACP special case: last dot → hyphen in MIME
        prefix = ".".join(parts[:-1])
        return f"{_ZCHAT_VND}{prefix}-{parts[-1]}"

    return f"{_ZCHAT_VND}{short}"


def mime_to_short(mime: str) -> str:
    """Convert a MIME type back to its short content-type name.

    Inverse of :func:`short_to_mime`.
    """
    if mime.startswith(_ZCHAT_EXT_VND):
        return f"ext.{mime[len(_ZCHAT_EXT_VND):]}"

    if mime.startswith(_ZCHAT_VND):
        rest = mime[len(_ZCHAT_VND):]
        # Check for ACP-style: contains a dot AND a hyphen in the last segment
        # e.g. "acp.session-prompt" → "acp.session.prompt"
        dot_parts = rest.split(".")
        if len(dot_parts) >= 2:
            last = dot_parts[-1]
            if "-" in last:
                # Last hyphen → dot to recover the original short name
                prefix = ".".join(dot_parts[:-1])
                idx = last.rfind("-")
                restored_last = last[:idx] + "." + last[idx + 1:]
                return f"{prefix}.{restored_last}"
        return rest

    # Standard MIME passthrough
    return mime
