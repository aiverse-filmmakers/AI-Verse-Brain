"""AI-Verse Brain deterministic intelligence core."""

from .authority import AuthorityTier
from .controller import BrainController
from .doctor import run_doctor
from .integration import HostMode, inspect_host, native_path_contract, plan_integration
from .models import BrainObject, EvidenceRef, Scope
from .policy import ProactivityLevel

__all__ = [
    "AuthorityTier",
    "BrainController",
    "BrainObject",
    "EvidenceRef",
    "Scope",
    "ProactivityLevel",
    "HostMode",
    "inspect_host",
    "native_path_contract",
    "plan_integration",
    "run_doctor",
]

__version__ = "0.1.0a3"
