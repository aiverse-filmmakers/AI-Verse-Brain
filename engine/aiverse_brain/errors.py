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


class LockConflict(BrainError):
    pass


class DuplicateTrigger(BrainError):
    pass


class PermissionDenied(BrainError):
    pass


class PolicyViolation(BrainError):
    pass


class DuplicateOpportunity(BrainError):
    pass


class CooldownActive(BrainError):
    pass


class EvaluationError(BrainError):
    pass


class CognitionContractError(BrainError):
    pass


class DuplicateAction(BrainError):
    pass


class UncertainActionOutcome(BrainError):
    pass
