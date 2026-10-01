"""Application exception hierarchy."""


class AnalyzerError(Exception):
    """Base class for all expected application errors."""


class InputRejectedError(AnalyzerError):
    """An input file or archive violated a safety limit or could not be read."""


class ParseError(AnalyzerError):
    """A file could not be parsed with the selected parser."""


class AnalysisCancelled(AnalyzerError):
    """The user cancelled a running analysis."""


class ProviderUnavailableError(AnalyzerError):
    """An external provider (AI or threat intelligence) could not be reached."""


class ProviderResponseError(AnalyzerError):
    """An external provider returned a response that failed validation."""


class SecretStoreError(AnalyzerError):
    """The secure secret storage backend is not available."""
