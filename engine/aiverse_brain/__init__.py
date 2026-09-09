"""AI-Verse Brain deterministic intelligence core."""

from .action_boundary import ActionExecutor, ActionRequest, ApprovalGrant
from .authority import AuthorityTier
from .cognition import CognitionProposal, CognitionPurpose, CognitionRequest, validate_proposal
from .controller import BrainController
from .doctor import run_doctor
from .integration import HostMode, inspect_host, native_path_contract, plan_integration
from .models import BrainObject, EvidenceRef, Scope
from .orchestrator import TickPlanner
from .policy import ProactivityLevel
from .proposal_apply import AppliedProposal, ProposalApplier
from .reasoner import ContextAssembler, ContextBundle, ReasonerAdapter, parse_reasoner_output
from .runtime import BrainRuntime, SurfaceItem, TickRunResult

__all__ = [
    "ActionExecutor", "ActionRequest", "ApprovalGrant",
    "AuthorityTier",
    "BrainController", "BrainObject", "EvidenceRef", "Scope",
    "CognitionProposal", "CognitionPurpose", "CognitionRequest", "validate_proposal",
    "HostMode", "inspect_host", "native_path_contract", "plan_integration", "run_doctor",
    "TickPlanner", "ProactivityLevel",
    "AppliedProposal", "ProposalApplier",
    "ContextAssembler", "ContextBundle", "ReasonerAdapter", "parse_reasoner_output",
    "BrainRuntime", "SurfaceItem", "TickRunResult",
]

__version__ = "0.1.0a5"
