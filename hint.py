#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge Claude toward a disable-model-invocation:true
skill that fits the user's message, instead of making Claude work it out
(or explain the mechanism) from scratch every time.

Two sources, merged:
  - index.json: hand-curated PT/EN keywords for skills we already know well
    (and the 3 we specifically audited and tagged high-risk).
  - discovered.json (built by discover.py, re-run here if stale): every
    OTHER skill on disk with disable-model-invocation: true, matched by
    its name and by quoted example phrases / fallback words pulled straight
    out of its own description. Covers skills installed after this hook was
    written with no manual edit needed.
"""
import json
import os
import re
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL_PATH = os.path.join(HERE, "index.json")
DISCOVERED_PATH = os.path.join(HERE, "discovered.json")
DISCOVER_SCRIPT = os.path.join(HERE, "discover.py")

HIGH_RISK_MESSAGE = (
    'Possibly applicable skill: /{name} — high risk, disable-model-invocation: true. '
    'Do NOT invoke it yourself, not even on the user\'s verbal "yes" — that\'s blocked by '
    'the harness. Tell the user and ask them to type /{name} themselves if they want to run it.'
)
NORMAL_MESSAGE = (
    'Possibly applicable skill: /{name} — disable-model-invocation: true. '
    'Cannot be invoked by you; suggest the user type /{name}.'
)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    return strip_accents(s.lower())


def ensure_discovered_fresh():
    try:
        subprocess.run(
            [sys.executable, DISCOVER_SCRIPT],
            timeout=4,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # stale or missing cache is fine, just degrades gracefully


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def name_parts(name: str):
    """Meaningful pieces of a hyphenated skill name, e.g. "untangle-codebase"
    -> ["untangle", "codebase"]. Short connector-ish pieces ("to", "pr") are
    dropped so a 2-letter match can't fire this tier on its own."""
    return [p for p in name.split("-") if len(p) >= 4]


# Generic project/dev-context words. Applied to EVERY skill automatically —
# curated or auto-discovered — as the companion a bare ambiguous word needs
# before it's allowed to fire. No per-skill tuning required.
# Deliberately bilingual (EN + PT): this is matching data, not code — it has
# to recognize whatever language the user actually types in, so Portuguese
# entries stay even though the rest of this file is English.
GENERIC_CONTEXT_WORDS = [
    "issue", "issues", "ticket", "tickets", "pr", "bug", "bugs", "repo",
    "repositorio", "repositório", "codigo", "código", "projeto", "project",
    "spec", "specs", "skill", "skills", "sessao", "sessão", "codebase",
    "branch", "commit", "deploy", "sprint", "tracker", "github", "gitlab",
    "tarefa", "tarefas",
]

_BARE_TOKEN_RE = re.compile(r"^[a-zà-ÿ]+$")


def is_bare_token(phrase: str) -> bool:
    """True for a single alphabetic word with no space or hyphen — the
    shape that keeps colliding with everyday meanings ("retro", "triagem",
    "wayfinder"). A phrase with a space or a hyphen is specific enough on
    its own ("grill me", "to-spec", "untangle codebase")."""
    return bool(_BARE_TOKEN_RE.match(normalize(phrase)))


def split_strong(phrases):
    """Partition a phrase list into (specific_enough_to_fire_alone, bare_single_words)."""
    strong, bare = [], []
    for p in phrases:
        (bare if is_bare_token(p) else strong).append(p)
    return strong, bare


def build_candidates():
    """name -> {"risk": "normal"|"alto", "strong": [phrases requiring 1 hit],
    "name_parts": [all must appear, unordered, as whole words],
    "weak": [words requiring 2 hits],
    "ambiguous": [bare words needing a context word alongside],
    "context_words": [the context words that unlock "ambiguous"]}.

    Every bare single-word trigger — whether it came from a hand-written
    keyword list or from an auto-discovered skill's own name — is demoted
    from "fires alone" to "needs a dev-context word too". This is what
    makes the protection generic: a brand-new skill named e.g. "polish" or
    "sprint" gets the same guard with zero manual curation, because the
    rule is about the SHAPE of the trigger (one common word), not about
    which specific skill it belongs to.
    """
    manual = load_json(MANUAL_PATH, {})
    discovered = load_json(DISCOVERED_PATH, {"skills": {}}).get("skills", {})

    candidates = {}
    for name, info in manual.items():
        strong, bare = split_strong(info.get("keywords", []))
        candidates[name] = {
            "risk": info.get("risk", "normal"),
            "strong": strong,
            "name_parts": name_parts(name),
            "weak": [],
            "ambiguous": list(info.get("ambiguous_keywords", [])) + bare,
            "context_words": list(info.get("context_words", [])) + GENERIC_CONTEXT_WORDS,
        }
    for name, info in discovered.items():
        if name in candidates:
            continue  # manual entry already covers it with better phrasing
        raw_strong = list(info.get("phrases", [])) + [name, name.replace("-", " ")]
        strong, bare = split_strong(raw_strong)
        candidates[name] = {
            "risk": info.get("risk", "normal"),
            "strong": strong,
            "name_parts": name_parts(name),
            "weak": list(info.get("fallback_words", [])),
            "ambiguous": bare,
            "context_words": GENERIC_CONTEXT_WORDS,
        }
    return candidates


def matches(norm_prompt: str, cand: dict) -> bool:
    for phrase in cand["strong"]:
        if normalize(phrase) in norm_prompt:
            return True

    prompt_words = set(re.findall(r"[a-zà-ÿ]{4,}", norm_prompt))

    # All parts of the skill's own name showing up anywhere in the prompt
    # (not necessarily adjacent) is a strong, language-independent signal —
    # e.g. "untangle" and "codebase" both present, even with other words
    # between them. Requires 2+ parts so a single generic word can't fire it.
    parts = cand["name_parts"]
    if len(parts) >= 2 and all(normalize(p) in prompt_words for p in parts):
        return True

    # Weakest tier: generic words pulled from the skill's own description,
    # already pruned (in discover.py) to drop ones shared by many skills.
    # Needs 2 independent hits since any single word here can still be
    # fairly common on its own.
    if cand["weak"]:
        hits = sum(1 for w in cand["weak"] if normalize(w) in prompt_words)
        if hits >= 2:
            return True

    # Ambiguous word + dev-context word tier: a bare word like "retro" or
    # "triagem" means something unrelated most of the time ("retro style",
    # medical "triagem"), so only fire when a project/issue-tracker word is
    # also present in the same message.
    if cand["ambiguous"] and cand["context_words"]:
        has_ambiguous = any(normalize(w) in prompt_words for w in cand["ambiguous"])
        has_context = any(normalize(w) in prompt_words for w in cand["context_words"])
        if has_ambiguous and has_context:
            return True
    return False


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    prompt = data.get("prompt") or data.get("message") or ""
    if not prompt or not isinstance(prompt, str):
        return 0

    ensure_discovered_fresh()
    candidates = build_candidates()
    norm_prompt = normalize(prompt)

    hits = [name for name, cand in candidates.items() if matches(norm_prompt, cand)]
    if not hits:
        return 0

    hits = hits[:2]  # keep the injected context short
    lines = []
    for name in hits:
        risk = candidates[name]["risk"]
        template = HIGH_RISK_MESSAGE if risk == "alto" else NORMAL_MESSAGE
        lines.append(template.format(name=name))

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
