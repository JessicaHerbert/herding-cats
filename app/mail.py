"""Threads where the ball is in your court.

The reading itself moved to app/providers/gmail.py so a different mail backend
can answer instead. This module stays as the name the rest of the app already
calls, and hands the question to whichever provider is configured.
"""


def waiting(limit: int = 40) -> list[dict]:
    from . import providers

    provider = providers.mail()
    if provider is None:
        return []
    return provider.waiting(limit)
