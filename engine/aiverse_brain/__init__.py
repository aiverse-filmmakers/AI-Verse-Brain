"""AI-Verse Brain deterministic intelligence core."""

from .authority import AuthorityTier
from .controller import BrainController
from .direction import GapProposal, InitiativeProposal, OpportunityProposal
from .evaluator import CriterionVerdict, EvaluationResult, Independence
from .models import BrainObject, EvidenceRef, Scope
from .policy import ProactivityLevel
from .progress import AttemptObservation

__all__ = [
    "AuthorityTier",
    "AttemptObservation",
    "BrainController",
    "BrainObject",
    "CriterionVerdict",
    "EvaluationResult",
    "EvidenceRef",
    "GapProposal",
    "Independence",
    "InitiativeProposal",
    "OpportunityProposal",
    "Scope",
    "ProactivityLevel",
]

__version__ = "0.1.0a2"
