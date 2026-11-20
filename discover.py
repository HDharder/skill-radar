#!/usr/bin/env python3
"""Scan every known skill root for SKILL.md files, parse frontmatter, and
cache the ones with disable-model-invocation: true, plus the phrases to
match them against a user prompt.

Re-run automatically by hint.py whenever the set of SKILL.md files (or their
mtimes) changes, so newly installed skills are picked up with no manual edit.
"""
import glob
import json
import os
import re
import sys

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "discovered.json")

# Known-risk overrides for skills we've specifically audited by hand and
# tested for missing confirmation gates. Everything else discovered gets the
# generic disable-model-invocation warning.
HIGH_RISK = {"triage", "wayfinder", "implement-spec"}

# Bump whenever the matching algorithm changes, so the fingerprint check
# (which otherwise only looks at SKILL.md mtimes) forces a rebuild.
SCRIPT_VERSION = "2"

ROOTS = [
    os.path.join(HOME, ".claude", "skills"),
    os.path.join(HOME, ".agents", "skills"),
    os.path.join(HOME, ".claude", "plugins", "cache"),
]

STOPWORDS = set(
    """
    the a an of to in on for with and or that this these those it is are be as by
    use used using uses when where what which who how why your you your's about
    after being based every their there these those where which while without
    doing other across through before should would could might needs need want
    wants where whose whom under over most some such each only also into onto
    first second third fresh whole entire single multiple several proper making
    o a os as um uma de do da dos das em no na para com que isso esse essa este esta
    ou e por quando onde qual quais quem como porque seu sua use usar usando usa
    sobre apos sendo baseado cada todos todas antes deveria poderia precisam
    precisa quer quere onde cujo apenas tambem dentro primeiro segundo terceiro
    unico unica inteiro inteira varios varias proprio propria fazendo
    """.split()
)


def find_skill_files():
    files = []
    # project-local skills too, if a project dir is the cwd
    cwd_skills = os.path.join(os.getcwd(), ".claude", "skills")
    for root in ROOTS + [cwd_skills]:
        if not os.path.isdir(root):
            continue
        files.extend(glob.glob(os.path.join(root, "**", "SKILL.md"), recursive=True))
    # dedupe by realpath (symlinks under ~/.claude/skills point into ~/.agents/skills)
    seen = {}
    for f in files:
        try:
            real = os.path.realpath(f)
            st = os.stat(real)
        except OSError:
            continue
        seen[real] = st.st_mtime
    return seen  # {realpath: mtime}


def fingerprint(file_mtimes: dict) -> str:
    parts = sorted(f"{p}:{m}" for p, m in file_mtimes.items())
    return str(hash(SCRIPT_VERSION + "|" + "|".join(parts)))


def parse_frontmatter(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    raw = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(raw) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # fallback: naive key: value line parser (handles the simple cases we've seen)
    data = {}
    for line in raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val:
            data[key] = val
    return data


def extract_phrases(description: str):
    if not description:
        return []
    phrases = re.findall(r'"([^"]{4,80})"', description)
    phrases += re.findall(r"'([^']{4,80})'", description)
    return [p.strip() for p in phrases if p.strip()]


def candidate_words(text: str, limit: int = 12):
    """Raw pool of distinctive-looking words from a description, before the
    cross-skill rarity filter runs. Longer minimum length than before (6, not
    5) to drop generic adjectives like "whole" that show up in any text."""
    words = re.findall(r"[a-zA-ZÀ-ÿ]{6,}", text.lower())
    out = []
    for w in words:
        if w in STOPWORDS or w in out:
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


def prune_to_distinctive(pools: dict, max_doc_freq: int = 2, final_limit: int = 5):
    """Keep, per skill, only the words from its candidate pool that are rare
    across every OTHER skill's pool too. A word like "codebase" that shows up
    in five different skill descriptions is too generic to mean "this one
    specific skill" when it appears in a long, unrelated chunk of text (e.g.
    a research report quoting several skill descriptions) — exactly the
    false-positive mode observed in production, not a short-vs-long-prompt
    problem. This fixes that without penalizing long genuine requests, which
    still match fine on whichever words stay distinctive."""
    doc_freq = {}
    for words in pools.values():
        for w in set(words):
            doc_freq[w] = doc_freq.get(w, 0) + 1
    pruned = {}
    for name, words in pools.items():
        kept = [w for w in words if doc_freq.get(w, 0) <= max_doc_freq]
        kept.sort(key=lambda w: (doc_freq.get(w, 0), -len(w)))
        pruned[name] = kept[:final_limit]
    return pruned


def build_index():
    raw = {}
    for real, _mtime in find_skill_files().items():
        fm = parse_frontmatter(real)
        if not fm:
            continue
        disabled = fm.get("disable-model-invocation")
        is_disabled = disabled is True or str(disabled).strip().lower() == "true"
        if not is_disabled:
            continue
        name = str(fm.get("name") or os.path.basename(os.path.dirname(real))).strip()
        if not name:
            continue
        description = str(fm.get("description") or "")
        raw[name] = {
            "dir": os.path.dirname(real),
            "phrases": extract_phrases(description),
            "name_tokens": [name, name.replace("-", " ")],
            "candidate_words": candidate_words(description),
        }

    pools = {name: info["candidate_words"] for name, info in raw.items()}
    pruned = prune_to_distinctive(pools)

    discovered = {}
    for name, info in raw.items():
        discovered[name] = {
            "dir": info["dir"],
            "phrases": info["phrases"],
            "name_tokens": info["name_tokens"],
            # only used as a fallback when there's no quoted example phrase
            "fallback_words": [] if info["phrases"] else pruned.get(name, []),
            "risk": "alto" if name in HIGH_RISK else "normal",
        }
    return discovered


def main():
    file_mtimes = find_skill_files()
    fp = fingerprint(file_mtimes)

    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("fingerprint") == fp:
                return 0  # up to date, nothing to do
        except (OSError, json.JSONDecodeError):
            pass

    index = build_index()
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fp, "skills": index}, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
