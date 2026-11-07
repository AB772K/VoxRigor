"""Errors raised by the offline benchmark subsystem."""


class BenchmarkError(Exception):
    """Base exception for expected benchmark validation and execution errors."""


class DatasetManifestError(BenchmarkError):
    """Dataset manifest is missing, invalid or inconsistent."""


class ScoreFileError(BenchmarkError):
    """Score-trial file is missing, malformed or does not match its manifest."""


class MetricError(BenchmarkError):
    """A metric cannot be computed from the supplied evaluation sample."""
