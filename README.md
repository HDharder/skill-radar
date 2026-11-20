# skill-radar

*[Leia em português](README.pt-BR.md)*

A Claude Code hook that notices, before each of your messages, when a request matches an installed skill that can't be invoked automatically (`disable-model-invocation: true`). It injects a one-line hint so Claude can point you to the right command instead of re-explaining the mechanism from scratch every time.

No per-skill list to maintain: it actually scans `~/.claude/skills`, `~/.agents/skills` and `~/.claude/plugins/cache`, reads every `SKILL.md`'s frontmatter, and any new skill you install (yours, a plugin's, or anyone else's package) is picked up automatically, no edits needed.

## How it works

![Architecture](assets/architecture.svg)

1. You type a message.
2. The `UserPromptSubmit` hook runs `hint.py` before Claude processes the message.
3. `discover.py` scans the skill directories (cached, only rescans when a `SKILL.md` actually changed) and keeps the ones with `disable-model-invocation: true`.
4. `hint.py` merges that with `index.json` (hand-curated entries for skills we already know well, including Portuguese phrasing) and tries to match your message against 4 tiers, from most to least specific:
   - **Strong phrase**, a snippet specific enough to fire alone ("grill me", "to-spec").
   - **Name parts**, every part of a compound name shows up in the message, even non-adjacent ("untangle" ... "codebase").
   - **Weak fallback**, words pulled from the skill's own description, pruned to drop ones shared by many skills, needs 2+ hits.
   - **Ambiguous + context**, an everyday word that also happens to be a skill name ("retro", "triage", "wayfinder") only fires when paired with a project/dev-context word (`issue`, `ticket`, `pr`, `bug`, `session`, `spec`...). This rule is generic: any future skill with a single-word name is protected automatically, with no manual tuning.
5. On a match, it injects a one- or two-line `additionalContext` naming the applicable skill and reminding Claude that, being `disable-model-invocation: true`, only the user typing the command actually fires it, never Claude on its own, even on a verbal "yes".

## Example

![Usage example](assets/example.svg)

## Installation

Pick ONE of the three methods below. They all end up doing the same thing (registering the same hook), so combining them just means the hint gets injected twice.

### Option A: as a Claude Code plugin (recommended)

```
/plugin marketplace add HDharder/skill-radar
/plugin install skill-radar@skill-radar
```

This uses Claude Code's own plugin system: no Python setup step, no `~/.claude/settings.json` editing. Start a new session afterward for it to take effect. (Authored against the published plugin manifest reference; if your Claude Code version handles plugin hooks differently, fall back to option B.)

### Option B: npx or git clone, with install.sh

Requires `python3` on PATH (`pyyaml` is optional, there's a fallback parser without it).

With Node installed, no npm registry publish needed:

```bash
npx github:HDharder/skill-radar
```

Or clone and run the installer directly:

```bash
git clone https://github.com/HDharder/skill-radar
cd skill-radar
./install.sh
```

Either way, `install.sh` (the npx path just runs it for you):
- copies `hint.py`, `discover.py` and `index.json` to `~/.claude/skill-radar/`;
- merges a `UserPromptSubmit` hook into `~/.claude/settings.json` without touching the rest of the file;
- is idempotent, running it again doesn't duplicate the entry, it just refreshes the path.

After installing, start a new Claude Code session. The hook is only read at session startup.

### Option C: fully manual (without the script)

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

- **A brand-new skill, with no manual curation**: already works on its own (quoted phrases in the skill's own description, plus its name, plus the weak fallback). Nothing to do.
- **Want to sharpen the matching for one specific skill**: edit `index.json`. Fields accepted per skill:
  - `keywords`: phrases that fire alone (checked by substring, not exact-match, no need for the whole sentence).
  - `risk`: `"alto"` switches the message to stress that it can't fire even on the user's verbal "yes" (reserved for skills already audited by hand for ungated destructive/external actions).
  - `ambiguous_keywords` + `context_words`: extra skill-specific context words, added on top of the generic ones (`GENERIC_CONTEXT_WORDS` in `hint.py`).
- Nothing else needs touching after editing `index.json`. `hint.py` reads it fresh on every call.

## Known limitations

- Doesn't cover *model-invoked* skills (no `disable-model-invocation: true`). Claude can already call those on its own, so they don't need a nudge.
- The weak-fallback tier pulls words from a skill's English description. For a request written entirely in a language other than English, without mentioning the skill's name, that tier won't help; the tiers doing the real work there are "name parts" and "ambiguous + context", not the fallback.
- Runs fully locally, no LLM call and no network. Faster and more predictable, but it doesn't understand synonyms or intent beyond what's written here.
- Claude Code's settings watcher only watches folders that already had a `settings.json` when the session started, so a new session is needed after installing or updating.

## Test results

A battery of 36 cases: one positive per in-scope skill, project-start chatter, mid-project chatter, deliberate ambiguous-word traps, and boundary checks on the matching tiers. All 36 behave as expected. There's also a synthetic case proving the ambiguous-word protection is generic, not hand-tuned per skill: a never-before-seen single-word skill name ("polish") gets the same protection automatically, with zero manual curation.

These 38 cases are also an executable test suite in [`tests/`](tests/test_hint.py), run against a fixture instead of whatever happens to be installed on your machine, so they're portable:

```bash
python3 tests/test_hint.py
```

Every case below shows the exact prompt sent to the hook and its exact output, for full transparency.

<details>
<summary><strong>36 test cases, all behaving as expected (click to expand)</strong></summary>

<details>
<summary>1. triage - short (fired)</summary>

Prompt sent:
```
can you triage the issues that came in this week?
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /triage (high risk, disable-model-invocation: true). Do NOT invoke it yourself, not even on the user's verbal \"yes\": that's blocked by the harness. Tell the user and ask them to type /triage themselves if they want to run it."}}
```

</details>

<details>
<summary>2. wayfinder - medium (fired)</summary>

Prompt sent:
```
This is way too big for one session, I want to map this out before we start.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /wayfinder (high risk, disable-model-invocation: true). Do NOT invoke it yourself, not even on the user's verbal \"yes\": that's blocked by the harness. Tell the user and ask them to type /wayfinder themselves if they want to run it."}}
```

</details>

<details>
<summary>3. implement-spec - short (fired)</summary>

Prompt sent:
```
The spec and tickets are ready, let's go with implement-spec.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /implement-spec (high risk, disable-model-invocation: true). Do NOT invoke it yourself, not even on the user's verbal \"yes\": that's blocked by the harness. Tell the user and ask them to type /implement-spec themselves if they want to run it."}}
```

</details>

<details>
<summary>4. implement - short (fired)</summary>

Prompt sent:
```
The tickets are ready, can you implement this ticket here?
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /implement (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /implement."}}
```

</details>

<details>
<summary>5. ask-matt - short (fired)</summary>

Prompt sent:
```
I don't know which skill to use for this, can you help me pick?
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /ask-matt (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /ask-matt."}}
```

</details>

<details>
<summary>6. grill-me - short (fired)</summary>

Prompt sent:
```
I want you to grill me thoroughly on this idea before I decide.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /grill-me (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /grill-me."}}
```

</details>

<details>
<summary>7. grill-with-docs - short (fired)</summary>

Prompt sent:
```
Do a grill with docs session on this architecture decision.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /grill-with-docs (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /grill-with-docs."}}
```

</details>

<details>
<summary>8. retro (legitimate) - short (fired)</summary>

Prompt sent:
```
Let's do a session retro for today?
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /retro (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /retro."}}
```

</details>

<details>
<summary>9. to-spec - short (fired)</summary>

Prompt sent:
```
I want to turn this into a spec and publish it to the tracker.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /to-spec (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /to-spec."}}
```

</details>

<details>
<summary>10. to-tickets - short (fired)</summary>

Prompt sent:
```
Let's run to-tickets on this plan.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /to-tickets (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /to-tickets."}}
```

</details>

<details>
<summary>11. improve-arch - short (fired)</summary>

Prompt sent:
```
I want to improve the architecture of this code, there's too much circular dependency.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /improve-codebase-architecture (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /improve-codebase-architecture."}}
```

</details>

<details>
<summary>12. setup-matt - short (fired)</summary>

Prompt sent:
```
I need to run setup-matt-pocock-skills before using the others.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /setup-matt-pocock-skills (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /setup-matt-pocock-skills."}}
```

</details>

<details>
<summary>13. untangle - long/narrative (fired)</summary>

Prompt sent:
```
Look, this project is a complete mess, files are tangled, poorly organized, full of confusing cross dependencies. I want you to do a thorough untangle on this whole codebase before I keep working on it, because it's a nightmare to debug anything.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /untangle-codebase (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /untangle-codebase."}}
```

</details>

<details>
<summary>14. untangle - short (fired)</summary>

Prompt sent:
```
I want to untangle this codebase, it's a mess.
```

Hook output:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "Possibly applicable skill: /untangle-codebase (disable-model-invocation: true). Cannot be invoked by you; suggest the user type /untangle-codebase."}}
```

</details>

<details>
<summary>15. project start 1 (stayed silent)</summary>

Prompt sent:
```
Hey! Let's start a new personal finance app project in React Native. I was thinking Expo and Supabase as backend.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>16. project start 2 (stayed silent)</summary>

Prompt sent:
```
Can you set up the initial folder structure for the project, with src, components, hooks and utils?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>17. project start 3 (stayed silent)</summary>

Prompt sent:
```
Which stack would you recommend for a small B2B SaaS, Next.js or Remix?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>18. mid-project 1 (stayed silent)</summary>

Prompt sent:
```
This auth code is a bit messy but it works, let's move on to the rest of the screens.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>19. mid-project 2 (conjugated verb, no exact phrase) (stayed silent)</summary>

Prompt sent:
```
I implemented the login screen, just need to test it.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>20. mid-project 3 (casual PR mention) (stayed silent)</summary>

Prompt sent:
```
Let's review the PR before opening it, just check the tests pass.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>21. mid-project 4 (code review, out-of-scope skill) (stayed silent)</summary>

Prompt sent:
```
After implementing, I need you to do the standard code review.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>22. mid-project 5 (casual debug, no explicit ask) (stayed silent)</summary>

Prompt sent:
```
Ugh, there's an error in the payment function, can you take a quick look?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>23. trap: medical triage (stayed silent)</summary>

Prompt sent:
```
The malaria triage at the ER was already completed, results come out today.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>24. trap: aesthetic retro (stayed silent)</summary>

Prompt sent:
```
I want a retro look for this app, like the 80s, with saturated colors.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>25. trap: retro game (stayed silent)</summary>

Prompt sent:
```
This game has a real retro vibe, reminds me of classic 16-bit games.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>26. trap: literal wayfinder/map (stayed silent)</summary>

Prompt sent:
```
This carnival map is amazing, let's map out the parade route so people don't get lost.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>27. trap: generic implement (stayed silent)</summary>

Prompt sent:
```
I'm going to implement a debounce function here in the hook.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>28. trap: codebase without untangle (stayed silent)</summary>

Prompt sent:
```
This codebase is fine, it just needs a few more tests.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>29. boundary: context word alone (issue, no 'triage') (stayed silent)</summary>

Prompt sent:
```
I opened a new issue in the repo to track this bug.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>30. boundary: context word alone (session, no 'retro') (stayed silent)</summary>

Prompt sent:
```
Let's do a summary of this work session?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>31. ask-matt - 'skill' out of context (stayed silent)</summary>

Prompt sent:
```
Messi has so much skill in dribbling.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>32. grill - 'grill' out of context (barbecue) (stayed silent)</summary>

Prompt sent:
```
Let's have a grill this weekend?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>33. implement - 'ticket' out of context (stayed silent)</summary>

Prompt sent:
```
I bought the ticket for Saturday's show.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>34. wayfinder - bare name, out of context (trail guide) (stayed silent)</summary>

Prompt sent:
```
I hired a wayfinder to guide me on the trail.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>35. to-spec - 'specs' alone (laptop specs) (stayed silent)</summary>

Prompt sent:
```
I'm buying a laptop, what specs would you recommend?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>36. setup - generic 'setup' word (stayed silent)</summary>

Prompt sent:
```
What keyboard and mouse setup do you use?
```

Hook output: none (no `additionalContext` injected).

</details>

</details>

## Related projects

A few other projects also try to nudge Claude toward the right skill. None found cover the exact gap this hook targets:

- **[jev-skill-suggestion](https://www.aitmpl.com/component/mod/productivity/jev-skill-suggestion)** (a community mod in `davila7/claude-code-templates`): suggests skills via a hook, but its own docs say it explicitly skips skills with `disable-model-invocation: true`, leaving them out of its suggestions entirely. That's exactly the case this project exists for.
- **[skill-compass](https://by-sonic.github.io/skill-compass/)**: a hook that reads your repo to work out what it's made of and tells Claude which skills to load, aimed at ordinary, model-invocable skills, not the manual-only ones.
- **[Dispatch](https://skills.cat/skills/visionairyse/dispatch)** (VisionAIrySE): a runtime router across the whole marketplace (plugins, MCP servers, skills) using an LLM classifier, hosted or with your own API key. Broader scope, but it sends your prompt to an external service in hosted mode, or costs an LLM call either way, unlike this project's local, deterministic scan.

None of these were found to specifically target `disable-model-invocation: true` skills with a local, LLM-free, frontmatter-based scan.

## Why this exists

No published skill or plugin does exactly this: a deterministic, local filesystem scan specifically for `disable-model-invocation: true`, with no LLM call and no fixed keyword list. The closest in mechanism sends your prompt to an external server; the rest are `SKILL.md` files the model itself reads (costing context every time) or ship a fixed catalog instead of scanning the disk.

## License

MIT, see [LICENSE](LICENSE).
