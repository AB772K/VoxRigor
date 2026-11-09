"""Typed errors for the protocol and API security subsystem."""

from voxrigor.errors import VoxRigorError


class ProtocolError(VoxRigorError):
    """An authorized local protocol assessment could not be completed."""


class ScopeManifestError(ProtocolError):
    """A protocol scope manifest is missing, invalid or unsafe."""
