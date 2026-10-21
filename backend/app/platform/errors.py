"""Errors shared by the platform clients."""


class SourceUnavailable(Exception):
    """A data source could not answer. Callers answer 503; nothing is inferred."""
