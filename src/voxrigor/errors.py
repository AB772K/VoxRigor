"""Typed exceptions used by the VoxRigor core."""


class VoxRigorError(Exception):
    """Base class for expected, user-facing VoxRigor errors."""


class ManifestError(VoxRigorError):
    """A project manifest is missing, malformed, or unsupported."""


class TestNotFoundError(VoxRigorError):
    """A requested test identifier is not registered."""


class ReportError(VoxRigorError):
    """A report or run artifact could not be safely written or read."""


class ProjectExistsError(VoxRigorError):
    """Refuse to overwrite an existing project manifest."""
