import re
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import HTTPException

import chat_memory
import main_legacy_api as legacy_api


SMILES_REGEX = re.compile(r"([A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]{3,})")
COUNT_REGEX = re.compile(r"\b(\d{1,3})\b")

GENERATE_PATTERNS = (
    r"\bgenerate\b",
    r"\bfind\b",
    r"\bdiscover\b",
    r"\bdesign\b",
    r"\bcandidates?\b",
    r"\bdrug-like\b",
)
SCORE_PATTERNS = (
    r"\bscore\b",
    r"\bevaluate\b",
    r"\banaly[sz]e\b",
    r"\bprofile\b",
)
BEST_PATTERNS = (
    r"\bbest\b",
    r"\btop\b",
    r"\branked\b",
    r"\bleaderboard\b",
)
REPORT_PATTERNS = (
    r"\breport\b",
    r"\bhtml\b",
    r"\bsummary\b",
    r"\bdashboard\b",
)
COMPARISON_PATTERNS = (
    r"\bcompare\b",
    r"\bversus\b",
    r"\bvs\b",
    r"\bbetter than\b",
    r"\bhigher than\b",
    r"\blower than\b",
)


@dataclass
class ParsedPrompt:
    raw_message: str
    intent: str
    count: int | None
    disease: str | None
    molecule: str | None
    comparison_keywords: list[str]


def _matched_patterns(message: str, patterns: tuple[str, ...]) -> list[str]:
    return [
        pattern.replace(r"\b", "").replace("\\", "")
        for pattern in patterns
        if re.search(pattern, message)
    ]


def _extract_count(message: str) -> int | None:
    match = COUNT_REGEX.search(message)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _extract_disease(message: str) -> str | None:
    lowered = message.lower()
    disease_aliases = {
        "diabetes": ("diabetes", "diabetic", "glucose", "insulin"),
        "infection": ("infection", "infectious", "antibacterial", "antiviral", "pathogen"),
    }
    for canonical, aliases in disease_aliases.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    return None


def _extract_smiles(message: str) -> str | None:
    quoted = re.findall(r'["\']([^"\']+)["\']', message)
    if quoted:
        return quoted[0].strip()

    lowered = message.lower()
    if not any(term in lowered for term in ("score", "smiles", "evaluate", "analyze", "analyse", "profile")):
        return None

    candidates = SMILES_REGEX.findall(message)
    if not candidates:
        return None

    blocked_words = {
        "score",
        "report",
        "find",
        "show",
        "best",
        "top",
        "drug-like",
        "molecules",
        "molecule",
        "diabetes",
        "infection",
    }
    filtered = [candidate for candidate in candidates if candidate.lower() not in blocked_words]
    if not filtered:
        return None
    return max(filtered, key=len).strip()


def _detect_intent(message: str, molecule: str | None) -> str:
    lowered = message.lower()
    scores = {
        "generate": len(_matched_patterns(lowered, GENERATE_PATTERNS)),
        "score": len(_matched_patterns(lowered, SCORE_PATTERNS)),
        "best_molecules": len(_matched_patterns(lowered, BEST_PATTERNS)),
        "report": len(_matched_patterns(lowered, REPORT_PATTERNS)),
    }

    if molecule and scores["score"] == 0 and ("smiles" in lowered or "molecule" in lowered):
        scores["score"] += 1

    if "show" in lowered and ("best" in lowered or "top" in lowered):
        scores["best_molecules"] += 1

    if any(term in lowered for term in ("find", "generate", "discover")) and any(
        term in lowered for term in ("molecule", "molecules", "candidate", "candidates")
    ):
        scores["generate"] += 2

    best_intent = max(scores, key=scores.get)
    if scores[best_intent] == 0:
        return "help"
    return best_intent


def parse_prompt(message: str) -> ParsedPrompt:
    lowered = message.lower()
    molecule = _extract_smiles(message)
    comparison_keywords = _matched_patterns(lowered, COMPARISON_PATTERNS)
    intent = _detect_intent(message, molecule)

    return ParsedPrompt(
        raw_message=message,
        intent=intent,
        count=_extract_count(message),
        disease=_extract_disease(message),
        molecule=molecule,
        comparison_keywords=comparison_keywords,
    )


def _suggested_title(message: str) -> str:
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return chat_memory.DEFAULT_CONVERSATION_TITLE
    if len(cleaned) <= 48:
        return cleaned
    return f"{cleaned[:45].rstrip()}..."


def _build_response(
    conversation_id: str,
    message: dict[str, Any],
    tool_used: str | None,
    data: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "message": {
            "role": message["role"],
            "content": message["content"],
            "type": message["type"],
        },
        "tool_used": tool_used,
        "data": data,
        "created_at": message["created_at"],
    }


def _build_error_response(
    conversation_id: str,
    detail: str,
    status_code: int = 400,
) -> dict[str, Any]:
    assistant_message = chat_memory.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=detail,
        message_type="error",
        data={"status_code": status_code, "detail": detail},
        metadata={"safe_error": True},
    )
    return _build_response(
        conversation_id=conversation_id,
        message=assistant_message,
        tool_used=None,
        data=assistant_message["data"],
    )


def _format_generate_reply(payload: dict[str, Any], parsed: ParsedPrompt) -> tuple[str, dict[str, Any]]:
    molecules = payload.get("molecules", [])
    disease = payload["disease"]
    if not molecules:
        return (
            f"I couldn't find any {disease} candidates yet.",
            {"type": "table", **payload, "query": asdict(parsed)},
        )

    top = molecules[0]
    comparison_note = ""
    if parsed.comparison_keywords:
        comparison_note = f" I also noticed comparison wording: {', '.join(parsed.comparison_keywords)}."

    content = "\n".join(
        [
            f"I found {len(molecules)} {disease} candidates ranked by Genorova clinical score.{comparison_note}",
            "",
            f"Top candidate: `{top.get('smiles', '')}`",
            f"Clinical score: `{top.get('clinical_score', 0)}`",
            f"Recommendation: `{top.get('recommendation', 'N/A')}`",
        ]
    )
    return content, {"type": "table", **payload, "query": asdict(parsed)}


def _format_score_reply(payload: dict[str, Any], parsed: ParsedPrompt) -> tuple[str, dict[str, Any]]:
    content = "\n".join(
        [
            f"I scored the molecule `{payload['smiles']}`.",
            "",
            f"Clinical score: `{payload.get('clinical_score', 0)}`",
            f"QED score: `{payload.get('qed_score', 0)}`",
            f"SA score: `{payload.get('sa_score', 0)}`",
            f"Lipinski pass: `{payload.get('passes_lipinski', False)}`",
            f"Recommendation: `{payload.get('recommendation', 'N/A')}`",
        ]
    )
    return content, {"type": "score", **payload, "query": asdict(parsed)}


def _format_best_reply(payload: dict[str, Any], parsed: ParsedPrompt) -> tuple[str, dict[str, Any]]:
    molecules = payload.get("molecules", [])
    if not molecules:
        return (
            "I couldn't find any ranked molecules yet.",
            {"type": "table", **payload, "query": asdict(parsed)},
        )

    top = molecules[0]
    content = "\n".join(
        [
            f"Here are the current top {len(molecules)} molecules from Genorova.",
            "",
            f"Best molecule: `{top.get('smiles', '')}`",
            f"Target disease: `{top.get('target_disease', 'unknown')}`",
            f"Clinical score: `{top.get('clinical_score', 0)}`",
            f"Recommendation: `{top.get('recommendation', 'N/A')}`",
        ]
    )
    return content, {"type": "table", **payload, "query": asdict(parsed)}


def _format_report_reply(parsed: ParsedPrompt) -> tuple[str, dict[str, Any]]:
    content = (
        "The latest Genorova report is ready.\n\n"
        "Open the report in a new tab to review the generated HTML output."
    )
    return content, {"type": "report", "url": "/report", "query": asdict(parsed)}


def _format_help_reply(parsed: ParsedPrompt) -> tuple[str, dict[str, Any]]:
    content = (
        "I can help with candidate generation, SMILES scoring, best-molecule lookup, and the latest report.\n\n"
        "Try one of these:\n"
        '- `Find 10 drug-like molecules for diabetes`\n'
        '- `Score "CCO"`\n'
        "- `Show the best molecules`\n"
        "- `Open the latest report`"
    )
    return content, {"type": "text", "query": asdict(parsed)}


def handle_chat_message(message: str, conversation_id: str | None = None) -> dict[str, Any]:
    conversation = chat_memory.ensure_conversation(conversation_id)
    convo_id = conversation["id"]
    parsed = parse_prompt(message)

    if conversation["title"] == chat_memory.DEFAULT_CONVERSATION_TITLE:
        chat_memory.update_conversation_title(convo_id, _suggested_title(message))

    chat_memory.add_message(
        conversation_id=convo_id,
        role="user",
        content=message,
        message_type="text",
        metadata={"parsed_prompt": asdict(parsed)},
    )

    try:
        tool_used: str | None = None
        content: str
        data: dict[str, Any]
        message_type: str

        if parsed.intent == "best_molecules":
            tool_used = "best_molecules"
            payload = legacy_api.best_molecules(n=parsed.count or 10)
            content, data = _format_best_reply(payload, parsed)
            message_type = "table"

        elif parsed.intent == "score":
            if not parsed.molecule:
                raise HTTPException(
                    status_code=422,
                    detail='Please include a SMILES string, for example: score "CCO".',
                )
            tool_used = "score"
            payload = legacy_api.score(legacy_api.ScoreRequest(smiles=parsed.molecule))
            content, data = _format_score_reply(payload, parsed)
            message_type = "score"

        elif parsed.intent == "generate":
            tool_used = "generate"
            payload = legacy_api.generate(
                legacy_api.GenerateRequest(
                    disease=parsed.disease or "diabetes",
                    count=parsed.count or 10,
                )
            )
            content, data = _format_generate_reply(payload, parsed)
            message_type = "table"

        elif parsed.intent == "report":
            tool_used = "report"
            content, data = _format_report_reply(parsed)
            message_type = "report"

        else:
            content, data = _format_help_reply(parsed)
            message_type = "text"

        assistant_message = chat_memory.add_message(
            conversation_id=convo_id,
            role="assistant",
            content=content,
            message_type=message_type,
            tool_used=tool_used,
            data=data,
            metadata={"parsed_prompt": asdict(parsed)},
        )
        return _build_response(convo_id, assistant_message, tool_used, data)

    except HTTPException as exc:
        return _build_error_response(
            conversation_id=convo_id,
            detail=f"Request failed: {exc.detail}",
            status_code=exc.status_code,
        )
    except Exception:
        return _build_error_response(
            conversation_id=convo_id,
            detail="Something went wrong while processing that request. Please try again.",
            status_code=500,
        )
