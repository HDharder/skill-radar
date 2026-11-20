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

Requires `python3` on PATH (`pyyaml` is optional, there's a fallback parser without it).

```bash
git clone https://github.com/hdharder/skill-radar
cd skill-radar
./install.sh
```

`install.sh`:
- copies `hint.py`, `discover.py` and `index.json` to `~/.claude/skill-radar/`;
- merges a `UserPromptSubmit` hook into `~/.claude/settings.json` without touching the rest of the file;
- is idempotent, running it again doesn't duplicate the entry, it just refreshes the path.

After installing, start a new Claude Code session. The hook is only read at session startup.

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

A battery of 36 cases: one positive per in-scope skill, project-start chatter, mid-project chatter, deliberate ambiguous-word traps, and boundary checks on the new matching tiers. All 36 behave as expected. There's also a 37th, synthetic case run separately (not shown below since it needed temporarily injecting a fake skill): a never-before-seen single-word skill name ("polish") gets the same ambiguous-word protection automatically, with zero manual curation, proving the fix is generic rather than hand-tuned per skill.

Every case below shows the exact prompt sent to the hook and its exact output, for full transparency.

<details>
<summary><strong>36 test cases, all behaving as expected (click to expand)</strong></summary>

<details>
<summary>1. triage - short (fired)</summary>

Prompt sent:
```
me ajuda a dar uma triagem nas issues que abriram essa semana?
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
isso aqui é grande demais pra uma sessão só, queria mapear esse trabalho todo antes de começar
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
a spec e os tickets já tão prontos, bora pro implement-spec
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
os tickets tão prontos, pode implementar esse ticket aqui
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
não sei qual skill eu uso pra isso, pode me ajudar a escolher?
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
quero que você me entreviste bem a fundo sobre essa ideia antes de eu decidir
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
faz uma entrevista com docs sobre essa decisão de arquitetura
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
bora fazer uma retrospectiva da sessão de hoje?
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
quero transformar isso em spec e publicar no tracker
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
vamos quebrar em tickets esse plano aqui
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
queria melhorar a arquitetura desse código, tá com muita dependência circular
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
preciso configurar o repo para as skills antes de usar as outras
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
olha, esse projeto tá uma bagunça total, os arquivos estão emaranhados, mal organizados, cheio de dependência cruzada confusa. queria que você fizesse um untangle bem completo nesse codebase inteiro antes de eu continuar trabalhando nele, porque tá osso de debugar qualquer coisa
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
quero fazer um untangle nesse codebase inteiro, tá uma bagunça
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
Oi! Vamos começar um projeto novo de um app de finanças pessoais em React Native. Pensei em usar Expo e Supabase como backend.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>16. project start 2 (stayed silent)</summary>

Prompt sent:
```
Pode criar a estrutura inicial de pastas pro projeto, com src, components, hooks e utils?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>17. project start 3 (stayed silent)</summary>

Prompt sent:
```
Qual stack você recomendaria pra um SaaS B2B pequeno, Next.js ou Remix?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>18. mid-project 1 (stayed silent)</summary>

Prompt sent:
```
Esse código de autenticação tá meio confuso mas funciona, vamos seguir com o resto das telas.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>19. mid-project 2 (conjugated verb, no exact phrase) (stayed silent)</summary>

Prompt sent:
```
Implementei a tela de login, falta só testar.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>20. mid-project 3 (casual PR mention) (stayed silent)</summary>

Prompt sent:
```
Vamos revisar o PR antes de abrir, só confere se os testes passam.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>21. mid-project 4 (code review, out-of-scope skill) (stayed silent)</summary>

Prompt sent:
```
Depois de implementar, preciso que você faça o code review padrão.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>22. mid-project 5 (casual debug, no explicit ask) (stayed silent)</summary>

Prompt sent:
```
Ih, deu erro ali na função de pagamento, dá uma olhada rápida?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>23. trap: medical triage (stayed silent)</summary>

Prompt sent:
```
A triagem de malária já foi feita no laboratório, os resultados saem hoje.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>24. trap: aesthetic retro (stayed silent)</summary>

Prompt sent:
```
Quero um visual retro pra esse app, tipo anos 80, com cores saturadas.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>25. trap: retro game (stayed silent)</summary>

Prompt sent:
```
Esse jogo tem uma pegada bem retro, lembra os clássicos de 16-bit.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>26. trap: literal wayfinder/map (stayed silent)</summary>

Prompt sent:
```
Esse mapa de carnaval é incrível, vamos mapear o trajeto do bloco pra galera não se perder.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>27. trap: generic implement (stayed silent)</summary>

Prompt sent:
```
Vou implementar uma função de debounce aqui no hook.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>28. trap: codebase without untangle (stayed silent)</summary>

Prompt sent:
```
Esse codebase tá ok, só precisa de uns testes a mais.
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>29. boundary: context word alone (issue, no 'triagem') (stayed silent)</summary>

Prompt sent:
```
abri uma issue nova no repo pra acompanhar esse bug
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>30. boundary: context word alone (sessão, no 'retro') (stayed silent)</summary>

Prompt sent:
```
vamos fazer um resumo dessa sessão de trabalho?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>31. ask-matt - 'skill' out of context (stayed silent)</summary>

Prompt sent:
```
o Messi tem muita skill no drible
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>32. grill - 'grill' out of context (barbecue) (stayed silent)</summary>

Prompt sent:
```
bora fazer um grill no fim de semana?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>33. implement - 'ticket' out of context (stayed silent)</summary>

Prompt sent:
```
comprei o ticket pro show de sábado
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>34. wayfinder - bare name matches even without a 2nd part (stayed silent)</summary>

Prompt sent:
```
contratei um wayfinder pra me guiar na trilha
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>35. to-spec - 'spec' alone (laptop specs) (stayed silent)</summary>

Prompt sent:
```
vou comprar um notebook, quais specs você recomenda?
```

Hook output: none (no `additionalContext` injected).

</details>

<details>
<summary>36. setup - generic 'setup' word (stayed silent)</summary>

Prompt sent:
```
qual o setup de teclado e mouse que você usa?
```

Hook output: none (no `additionalContext` injected).

</details>

</details>

## Why this exists

No published skill or plugin does exactly this: a deterministic, local filesystem scan specifically for `disable-model-invocation: true`, with no LLM call and no fixed keyword list. The closest in mechanism sends your prompt to an external server; the rest are `SKILL.md` files the model itself reads (costing context every time) or ship a fixed catalog instead of scanning the disk.

## License

MIT, see [LICENSE](LICENSE).
