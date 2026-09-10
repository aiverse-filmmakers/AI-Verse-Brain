from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .cognition import CognitionRequest
from .errors import ValidationError

MAX_RETRIEVAL_QUERY_CHARS = 2048
DEFAULT_MAX_CAPABILITY_CANDIDATES = 1000

_PURPOSE_INTENT = {
    "orient": "the user's confirmed goals, active initiatives, current objectives, blockers, and immediate context",
    "gap_analysis": "gaps between current state and confirmed goals, including blockers, constraints, prior attempts, decisions, and outcomes",
    "opportunity_discovery": "useful opportunities that can advance confirmed goals or active initiatives from the current situation",
    "objective_planning": "the next concrete objective, required steps, dependencies, blockers, and tools needed to advance active initiatives",
    "reflection": "recent objective progress, actions, decisions, outcomes, failures, successes, evidence, and lessons",
    "strategy_review": "repeated outcomes, validated learnings, strategic decisions, regressions, and patterns relevant to confirmed goals",
    "evaluation": "evidence and prior results needed to evaluate current objective success criteria",
}

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "capabilities",
    "capability", "current", "do", "for", "from", "find", "goal", "goals", "host", "in", "including", "into",
    "is", "it", "needed", "of", "on", "or", "our", "prior", "relevant", "scope", "that", "the", "their",
    "this", "to", "tool", "tools", "user", "using", "with", "work", "needed", "active", "confirmed",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _clean_text(value: str, *, max_chars: int = 320) -> str:
    text = _WS_RE.sub(" ", value).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _collect_strings(value: Any, out: List[str], *, depth: int = 0, max_items: int = 80) -> None:
    if len(out) >= max_items or depth > 5:
        return
    if isinstance(value, str):
        text = _clean_text(value)
        if text:
            out.append(text)
        return
    if isinstance(value, Mapping):
        # Payload-bearing fields are semantically stronger than envelope metadata.
        preferred = ("payload", "desired_state", "success_criteria", "objective", "goal", "summary", "title", "name", "description", "current_context")
        seen = set()
        for key in preferred:
            if key in value:
                seen.add(key)
                _collect_strings(value[key], out, depth=depth + 1, max_items=max_items)
        for key, child in value.items():
            if key in seen or str(key) in {"id", "revision", "created_at", "updated_at", "created_by", "updated_by"}:
                continue
            _collect_strings(child, out, depth=depth + 1, max_items=max_items)
        return
    if isinstance(value, (list, tuple, set)):
        for child in value:
            _collect_strings(child, out, depth=depth + 1, max_items=max_items)
            if len(out) >= max_items:
                break


def _semantic_signals(request: CognitionRequest, current_context: Dict[str, Any], brain_state: Sequence[Dict[str, Any]]) -> List[str]:
    raw: List[str] = []
    _collect_strings(current_context, raw)
    _collect_strings(brain_state, raw)
    _collect_strings(request.context_refs, raw)
    _collect_strings(request.evidence_refs, raw)

    result: List[str] = []
    seen = set()
    for text in raw:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= 36:
            break
    return result


def build_retrieval_query(
    request: CognitionRequest,
    current_context: Dict[str, Any],
    brain_state: Sequence[Dict[str, Any]],
    *,
    target: str,
    max_chars: int = MAX_RETRIEVAL_QUERY_CHARS,
) -> str:
    """Build a bounded semantic query from the actual cognition task and canonical context.

    The query is deliberately human/semantic text. Internal purpose labels such as
    ``gap_analysis`` are never used as the retrieval query itself.
    """

    if target not in {"history", "capabilities"}:
        raise ValidationError("retrieval target must be 'history' or 'capabilities'")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 256 <= max_chars <= 8192:
        raise ValidationError("retrieval query max_chars must be an integer between 256 and 8192")

    purpose = request.purpose.value
    intent = _PURPOSE_INTENT.get(purpose, "the current cognition task and confirmed user direction")
    if target == "history":
        prefix = f"Recall prior facts, decisions, outcomes, attempts, constraints, and lessons relevant to {intent}."
    else:
        prefix = f"Rank executable capabilities that are useful for {intent}."

    signals = _semantic_signals(request, current_context, brain_state)
    query = prefix
    if signals:
        query += " Signals: "
        for signal in signals:
            addition = (" | " if not query.endswith(": ") else "") + signal
            if len(query) + len(addition) > max_chars:
                remaining = max_chars - len(query)
                if remaining > 1:
                    query += addition[:remaining]
                break
            query += addition
    return query[:max_chars].strip()


def _tokens(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value
    elif isinstance(value, Mapping):
        text = " ".join(f"{k} {v}" for k, v in value.items())
    elif isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value)
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _query_terms(query: str) -> Tuple[str, ...]:
    ordered: List[str] = []
    seen = set()
    for token in _tokens(query):
        if token in _STOPWORDS or len(token) < 3 or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= 96:
            break
    return tuple(ordered)


def capability_relevance_score(capability: Mapping[str, Any], query: str) -> float:
    """Deterministically score provider-style capability metadata against a task query."""

    terms = set(_query_terms(query))
    if not terms:
        return 0.0

    weighted_fields = (
        ("id", 10.0),
        ("name", 10.0),
        ("description", 5.0),
        ("operators", 3.0),
        ("tags", 3.0),
        ("keywords", 3.0),
        ("dependencies", 1.5),
        ("kind", 1.0),
    )
    score = 0.0
    matched = set()
    for field, weight in weighted_fields:
        field_terms = set(_tokens(capability.get(field)))
        overlap = terms & field_terms
        if overlap:
            score += weight * len(overlap)
            matched.update(overlap)

    # Reward breadth so a capability matching several distinct task concepts beats
    # one that repeats a single generic word across metadata fields.
    score += 2.0 * max(0, len(matched) - 1)
    return score


def rank_capabilities(
    capabilities: Iterable[Dict[str, Any]],
    query: str,
    *,
    limit: int,
    max_candidates: int = DEFAULT_MAX_CAPABILITY_CANDIDATES,
) -> List[Dict[str, Any]]:
    """Validate the full bounded candidate set, rank it, then apply the reasoning limit.

    This intentionally avoids the old failure mode where provider order was truncated
    first and task relevance was considered only afterward. If a host returns more
    than the explicit candidate budget Brain fails closed instead of silently hiding
    candidates beyond the cutoff.
    """

    for name, value in (("limit", limit), ("max_candidates", max_candidates)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValidationError(f"{name} must be a positive integer")
    if max_candidates < limit:
        raise ValidationError("max_candidates must be greater than or equal to limit")
    if max_candidates > 10000:
        raise ValidationError("max_candidates may not exceed 10000")
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("capability ranking query must be non-empty")

    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for index, item in enumerate(capabilities):
        if index >= max_candidates:
            raise ValidationError(
                f"host returned more than {max_candidates} capability candidates; "
                "scope/filter the provider result instead of relying on silent truncation"
            )
        if not isinstance(item, dict):
            raise ValidationError("capability entries must be objects")
        candidates.append((index, dict(item)))

    ranked = sorted(
        candidates,
        key=lambda pair: (-capability_relevance_score(pair[1], query), pair[0]),
    )
    return [item for _, item in ranked[:limit]]
