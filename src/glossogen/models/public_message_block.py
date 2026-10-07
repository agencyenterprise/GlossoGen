"""The block that carries public message bodies inside an agent-facing tool result.

Scenarios that deliver channel messages inside tool results render them after
the rest of the result, under ``PUBLIC_MESSAGES_HEADER``. Each body is delivered
once, so the self-hosted context trimmer keeps this block when it drops an older
result. The two empty bodies below say that nothing was delivered and are not
kept.
"""

PUBLIC_MESSAGES_HEADER = "NEW PUBLIC MESSAGES"
NO_PUBLIC_MESSAGES = "none"
PUBLIC_MESSAGES_DISABLED = "Broadcast is disabled."


def public_message_block(text: str) -> str | None:
    """Return the block from the header to the end of ``text``, or None when it delivers nothing."""
    start = text.find(PUBLIC_MESSAGES_HEADER)
    if start < 0:
        return None
    block = text[start:].rstrip()
    body = block[len(PUBLIC_MESSAGES_HEADER) :].strip()
    if body in ("", NO_PUBLIC_MESSAGES, PUBLIC_MESSAGES_DISABLED):
        return None
    return block
