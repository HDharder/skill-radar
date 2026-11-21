#!/usr/bin/env python3
"""Executable version of the 36 cases documented in README.md, plus the
synthetic "polish" case proving the ambiguous-word protection is generic.

Runs hint.py from a temporary copy of the repo with a fixture
discovered.json (tests/fixtures/discovered.json) instead of a live scan of
whatever happens to be installed on the machine running the tests, so the
results are the same on any machine or CI runner.

Run with:
    python3 -m unittest discover -s tests -v
or just:
    python3 tests/test_hint.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# (description, prompt, expected_skill_or_None): same 36 cases as README.md's
# "Test results" section, kept in sync by hand; if you change one, change
# both.
CASES = [
    ("triage - short", "can you triage the issues that came in this week?", "triage"),
    ("wayfinder - medium", "This is way too big for one session, I want to map this out before we start.", "wayfinder"),
    ("implement-spec - short", "The spec and tickets are ready, let's go with implement-spec.", "implement-spec"),
    ("implement - short", "The tickets are ready, can you implement this ticket here?", "implement"),
    ("ask-matt - short", "I don't know which skill to use for this, can you help me pick?", "ask-matt"),
    ("grill-me - short", "I want you to grill me thoroughly on this idea before I decide.", "grill-me"),
    ("grill-with-docs - short", "Do a grill with docs session on this architecture decision.", "grill-with-docs"),
    ("retro (legitimate) - short", "Let's do a session retro for today?", "retro"),
    ("to-spec - short", "I want to turn this into a spec and publish it to the tracker.", "to-spec"),
    ("to-tickets - short", "Let's run to-tickets on this plan.", "to-tickets"),
    ("improve-arch - short", "I want to improve the architecture of this code, there's too much circular dependency.", "improve-codebase-architecture"),
    ("setup-matt - short", "I need to run setup-matt-pocock-skills before using the others.", "setup-matt-pocock-skills"),
    ("untangle - long/narrative", (
        "Look, this project is a complete mess, files are tangled, poorly organized, "
        "full of confusing cross dependencies. I want you to do a thorough untangle "
        "on this whole codebase before I keep working on it, because it's a nightmare "
        "to debug anything."
    ), "untangle-codebase"),
    ("untangle - short", "I want to untangle this codebase, it's a mess.", "untangle-codebase"),

    ("project start 1", "Hey! Let's start a new personal finance app project in React Native. I was thinking Expo and Supabase as backend.", None),
    ("project start 2", "Can you set up the initial folder structure for the project, with src, components, hooks and utils?", None),
    ("project start 3", "Which stack would you recommend for a small B2B SaaS, Next.js or Remix?", None),

    ("mid-project 1", "This auth code is a bit messy but it works, let's move on to the rest of the screens.", None),
    ("mid-project 2 (conjugated verb, no exact phrase)", "I implemented the login screen, just need to test it.", None),
    ("mid-project 3 (casual PR mention)", "Let's review the PR before opening it, just check the tests pass.", None),
    ("mid-project 4 (code review, out-of-scope skill)", "After implementing, I need you to do the standard code review.", None),
    ("mid-project 5 (casual debug, no explicit ask)", "Ugh, there's an error in the payment function, can you take a quick look?", None),

    ("trap: medical triage", "The malaria triage at the ER was already completed, results come out today.", None),
    ("trap: aesthetic retro", "I want a retro look for this app, like the 80s, with saturated colors.", None),
    ("trap: retro game", "This game has a real retro vibe, reminds me of classic 16-bit games.", None),
    ("trap: literal wayfinder/map", "This carnival map is amazing, let's map out the parade route so people don't get lost.", None),
    ("trap: generic implement", "I'm going to implement a debounce function here in the hook.", None),
    ("trap: codebase without untangle", "This codebase is fine, it just needs a few more tests.", None),

    ("boundary: context word alone (issue, no 'triage')", "I opened a new issue in the repo to track this bug.", None),
    ("boundary: context word alone (session, no 'retro')", "Let's do a summary of this work session?", None),
    ("ask-matt - 'skill' out of context", "Messi has so much skill in dribbling.", None),
    ("grill - 'grill' out of context (barbecue)", "Let's have a grill this weekend?", None),
    ("implement - 'ticket' out of context", "I bought the ticket for Saturday's show.", None),
    ("wayfinder - bare name, out of context (trail guide)", "I hired a wayfinder to guide me on the trail.", None),
    ("to-spec - 'specs' alone (laptop specs)", "I'm buying a laptop, what specs would you recommend?", None),
    ("setup - generic 'setup' word", "What keyboard and mouse setup do you use?", None),

    # Not in README.md's 36: the synthetic case proving the ambiguous-word
    # guard is generic, not hand-tuned per skill. "polish" is a never-curated
    # single-word skill name that only exists in tests/fixtures/discovered.json.
    ("synthetic: never-curated single-word skill, out of context", "I'm going to polish this wooden table this weekend.", None),
    ("synthetic: never-curated single-word skill, with dev context", "This UI needs a polish pass before deploy, there are some rough edges.", "polish"),
]


class SkillRadarMatchingTests(unittest.TestCase):
    hint_path = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmpdir = cls._tmp.name
        for name in ("hint.py", "discover.py", "index.json"):
            shutil.copy(os.path.join(REPO_ROOT, name), os.path.join(cls.tmpdir, name))
        shutil.copy(
            os.path.join(FIXTURES_DIR, "discovered.json"),
            os.path.join(cls.tmpdir, "discovered.json"),
        )
        cls.hint_path = os.path.join(cls.tmpdir, "hint.py")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_case(self, prompt):
        env = dict(os.environ)
        env["SKILL_RADAR_SKIP_DISCOVER"] = "1"
        result = subprocess.run(
            [sys.executable, self.hint_path],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        out = result.stdout.strip()
        if not out:
            return None
        data = json.loads(out)
        ctx = data["hookSpecificOutput"]["additionalContext"]
        for line in ctx.splitlines():
            if line.startswith("Possibly applicable skill: /"):
                return line.split("/", 1)[1].split(" ", 1)[0]
        return None


def _make_test(desc, prompt, expected):
    def test(self):
        fired = self.run_case(prompt)
        self.assertEqual(fired, expected, msg=f"prompt: {prompt!r}")
    test.__name__ = f"test_{desc}"
    return test


for i, (desc, prompt, expected) in enumerate(CASES):
    safe_desc = "".join(c if c.isalnum() else "_" for c in f"{i:02d}_{desc}")
    setattr(SkillRadarMatchingTests, f"test_{safe_desc}", _make_test(desc, prompt, expected))


if __name__ == "__main__":
    unittest.main(verbosity=2)
