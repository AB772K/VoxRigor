"""Errors raised by biometric model integrations."""


class ModelIntegrationError(Exception):
    """Base class for expected model integration failures."""


class OptionalDependencyError(ModelIntegrationError):
    """An optional backend dependency is not installed."""


class ModelLoadError(ModelIntegrationError):
    """A model or runtime could not be loaded safely."""


class AudioInputError(ModelIntegrationError):
    """An audio file or in-memory audio signal is invalid."""


class InferenceError(ModelIntegrationError):
    """A model returned an invalid result or inference failed."""
