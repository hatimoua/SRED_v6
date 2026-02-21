class SREDError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(SREDError):
    """Requested resource does not exist."""


class ConflictError(SREDError):
    """Operation conflicts with existing state (e.g. wrong run ownership)."""
