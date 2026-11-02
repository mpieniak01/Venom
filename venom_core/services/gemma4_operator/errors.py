"""Typed preparation errors shared by CLI and diagnostic evidence services."""


class EvidenceMismatch(ValueError):
    """Well-formed evidence identifies incompatible configurations or cases."""
