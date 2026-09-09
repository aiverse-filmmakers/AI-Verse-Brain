"""AI-Verse Brain deterministic intelligence core."""

from ._version import __version__
from .action_boundary import ActionExecutor, ActionRequest, ApprovalGrant
from .authority import AuthorityTier
from .bridge import (
    BridgeConfig,
    BridgeDescription,
    BridgeHostAdapter,
    BridgeReasonerAdapter,
    JSONSubprocessBridge,
    adapter_doctor,
)
from .cadence_hooks import render_cadence_hooks
from .cognition import CognitionProposal, CognitionPurpose, CognitionRequest, validate_proposal
from .controller import BrainController
from .doctor import run_doctor
from .installation import InitPlan, InitResult, initialize, plan_init, read_installation_marker
from .integration import HostMode, inspect_host, native_path_contract, plan_integration
from .local_host import ReadOnlyContextHost
from .migration import MigrationPlan, apply_migration, plan_migration
from .models import BrainObject, EvidenceRef, Scope
from .onboarding import OnboardingPlan, OnboardingResult, OnboardingService
from .orchestrator import TickPlanner
from .policy import ProactivityLevel
from .proposal_apply import AppliedProposal, ProposalApplier
from .reasoner import ContextAssembler, ContextBundle, ReasonerAdapter, parse_reasoner_output
from .runtime import BrainRuntime, SurfaceItem, TickRunResult
from .vendor import vendor_bridge_config, vendor_reasoner
from .vendor_bridge import VendorOptions

__all__ = [
    "ActionExecutor", "ActionRequest", "ApprovalGrant",
    "AuthorityTier",
    "BridgeConfig", "BridgeDescription", "BridgeHostAdapter", "BridgeReasonerAdapter",
    "JSONSubprocessBridge", "adapter_doctor",
    "BrainController", "BrainObject", "EvidenceRef", "Scope",
    "CognitionProposal", "CognitionPurpose", "CognitionRequest", "validate_proposal",
    "InitPlan", "InitResult", "initialize", "plan_init", "read_installation_marker",
    "HostMode", "inspect_host", "native_path_contract", "plan_integration", "run_doctor",
    "OnboardingPlan", "OnboardingResult", "OnboardingService",
    "TickPlanner", "ProactivityLevel",
    "AppliedProposal", "ProposalApplier",
    "ContextAssembler", "ContextBundle", "ReasonerAdapter", "parse_reasoner_output",
    "BrainRuntime", "SurfaceItem", "TickRunResult",
    "ReadOnlyContextHost",
    "MigrationPlan", "plan_migration", "apply_migration",
    "VendorOptions", "vendor_bridge_config", "vendor_reasoner",
    "render_cadence_hooks",
    "__version__",
]
