"""Errors raised by MusicGenerationProvider implementations.

Kept provider-agnostic so callers never need to know which backend raised them.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all provider errors."""


class ProviderUnavailableError(ProviderError):
    """The provider's API could not be reached (connection refused, DNS, etc.)."""


class ProviderTimeoutError(ProviderError):
    """A request to the provider, or a job's generation, exceeded its time budget."""


class ProviderResponseError(ProviderError):
    """The provider returned a response Tunora could not parse or did not expect."""
