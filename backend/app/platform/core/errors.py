class PlatformError(Exception):
    """Base exception for platform errors."""


class ModelInvocationError(PlatformError):
    """Raised when the model call fails."""


class ToolExecutionError(PlatformError):
    """Raised when a tool execution fails."""


class AppConfigurationError(PlatformError):
    """Raised when an app configuration is invalid."""


class PermissionDeniedError(PlatformError):
    """Raised when a capability is not allowed."""
