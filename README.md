# skill-radar

*[Leia em português](README.pt-BR.md)*

A Claude Code hook that notices, before each of your messages, when a request matches an installed skill that **can't be invoked automatically** (`disable-model-invocation: true`) — and injects a one-line hint so Claude can point you to the right command instead of re-explaining the mechanism from scratch every time.

No per-skill list to maintain: it actually scans `~/.claude/skills`, `~/.agents/skills` and `~/.claude/plugins/cache`, reads every `SKILL.md`'s frontmatter, and any new skill you install — yours, a plugin's, or anyone else's package — is picked up automatically, no edits needed.

## How it works

![Architecture](assets/architecture.svg)

1. You type a message.
2. The `UserPromptSubmit` hook runs `hint.py` **before** Claude processes the message.
3. `discover.py` scans the skill directories (cached — only rescans when a `SKILL.md` actually changed) and keeps the ones with `disable-model-invocation: true`.
4. `hint.py` merges that with `index.json` (hand-curated entries for skills we already know well, including Portuguese phrasing) and tries to match your message against 4 tiers, most to least specific:
   - **Strong phrase** — a snippet specific enough to fire alone ("grill me", "to-spec").
   - **Name parts** — every part of a compound name shows up in the message, even non-adjacent ("untangle" ... "codebase").
   - **Weak fallback** — words pulled from the skill's own description, pruned to drop ones shared by many skills; needs 2+ hits.
   - **Ambiguous + context** — an everyday word that also happens to be a skill name ("retro", "triage", "wayfinder") only fires when paired with a project/dev-context word (`issue`, `ticket`, `pr`, `bug`, `session`, `spec`...). This rule is generic — any future skill with a single-word name is protected automatically, with no manual tuning.
5. On a match, it injects a one- or two-line `additionalContext` naming the applicable skill and reminding Claude that, being `disable-model-invocation: true`, only the user typing the command actually fires it — never Claude on its own, even on a verbal "yes".

## Example

![Usage example](assets/example.svg)

## Installation

Requires `python3` on PATH (`pyyaml` is optional — there's a fallback parser without it).

```bash
git clone <this-repo-url> skill-radar
cd skill-radar
./install.sh
```

`install.sh`:
- copies `hint.py`, `discover.py` and `index.json` to `~/.claude/skill-radar/`;
- merges (never overwrites the rest of) a `UserPromptSubmit` hook into `~/.claude/settings.json`;
- is idempotent — running it again doesn't duplicate the entry, just refreshes the path.

After installing, **start a new Claude Code session** — the hook is only read at session startup.

### Manual installation (without the script)

If you'd rather not run `install.sh`, copy the three files anywhere and add this to `~/.claude/settings.json` (merging with whatever is already in `hooks`, never replacing it):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"/absolute/path/to/hint.py\"",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Uninstalling

Remove the `hooks.UserPromptSubmit` entry from `~/.claude/settings.json` and delete `~/.claude/skill-radar/`.

## Extending / fixing a false positive

- **A brand-new skill, with no manual curation:** already works on its own (quoted phrases in the skill's own description + its name + the weak fallback). Nothing to do.
- **Want to sharpen the matching for one specific skill:** edit `index.json`. Fields accepted per skill:
  - `keywords`: phrases that fire alone (checked by substring, not exact-match — no need for the whole sentence).
  - `risk`: `"alto"` switches the message to stress that it can't fire even on the user's verbal "yes" (reserved for skills already audited by hand for ungated destructive/external actions).
  - `ambiguous_keywords` + `context_words`: extra skill-specific context words, added on top of the generic ones (`GENERIC_CONTEXT_WORDS` in `hint.py`).
- Nothing else needs touching after editing `index.json` — `hint.py` reads it fresh on every call.

## Known limitations

- Doesn't cover *model-invoked* skills (no `disable-model-invocation: true`) — Claude can already call those on its own, so they don't need a nudge.
- The weak-fallback tier pulls words from an English description (most installed `SKILL.md` files are in English); for an all-Portuguese request that doesn't mention the skill's name, the tiers doing the real work are "name parts" and "ambiguous + context", not the fallback.
- Runs fully locally, no LLM call and no network — faster and more predictable, but it doesn't understand synonyms or intent beyond what's written here.
- Claude Code's settings watcher only watches folders that already had a `settings.json` when the session started, so a new session is needed after installing or updating.

## Test results

A battery of 28 cases (one positive per in-scope skill, project-start chatter, mid-project chatter, and deliberate ambiguous-word traps) + 8 extra edge cases + 1 synthetic case with a never-before-seen skill name (`polish`, to prove the protection is generic rather than hand-tuned per skill): **all passing**. Also validated live, in a real Claude Code session, not just via script.

## Why this exists

No published skill or plugin does exactly this — a deterministic, local filesystem scan specifically for `disable-model-invocation: true`, with no LLM call and no fixed keyword list. The closest in mechanism sends your prompt to an external server; the rest are `SKILL.md` files the model itself reads (costing context every time) or ship a fixed catalog instead of scanning the disk.

## License

MIT — see [LICENSE](LICENSE).
