class BrainError(Exception):
    """Base error for AI-Verse Brain."""


class ValidationError(BrainError):
    pass


class ScopeError(BrainError):
    pass


class AuthorityError(BrainError):
    pass


class TransitionError(BrainError):
    pass


class RevisionConflict(BrainError):
    pass


class DuplicateTrigger(BrainError):
    pass


class PermissionDenied(BrainError):
    pass
