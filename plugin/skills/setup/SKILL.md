---
name: setup
description: Walk someone through turning an installed plugin into a working one, or fix a broken configuration. Use for "set up sky", "configure the knowledge base", "I have a profile file", "rotate my token", "sky is not connected", "where does the token go". Runs the `sky setup` commands and explains what each one writes.
---

# /sky:setup — make an installed plugin into a working one

Installing the plugin gives you the skills. It does not give you a knowledge
base — that needs an address, a tenant and a token, none of which ship with the
plugin, because they are yours and not everybody's.

Everything here is `sky setup`, a plain command. This skill's job is to explain
what each step writes, and to read the results back in plain words.

## First, find out what is actually wrong

Run `sky setup doctor` and read it out. It answers the configuration questions —
is there a map, does it name a token variable, is that variable set, is a server
registered, is the token file readable only by you. **`sky doctor` is a
different command** and answers a different question: is the running system
alive. A typo and an outage should not look the same, which is why they are two
tables.

## A first-time setup

1. **You need a profile** — a small JSON file with the address, the tenant and
   the ontology, produced by whoever administers the knowledge base. Ask for it
   if the user does not have one; do not invent its contents.
2. **You need a token of your own.** Every person uses their own, so the record
   of who ingested what is true. It is minted in the knowledge-base
   application, shown once.
3. Run:

       sky setup init --profile <the file you were sent>

   It prints exactly what it will write and waits. Read the plan out. Then it
   asks for the token at a hidden prompt.

   **It has to be typed at a terminal.** The command refuses to read a token
   when standard input is not a terminal, because that usually means something
   is recording — and a recorded token is a spent one. Never offer to paste the
   token into the conversation, and never put it on a command line.

4. It writes four things:
   - `~/.config/sky/env` — the token, mode 600, and nothing else
   - `~/.config/sky/kb-map.json` — which knowledge bases exist, holding the
     *name* of the token variable, never its value
   - `~/.config/sky/sky-headers` — the small program the host runs to fetch the
     token, copied here so a plugin update cannot break the path
   - `~/.claude.json` — one MCP server per knowledge base, pointing at that
     helper
5. **Restart the host**, then `sky setup doctor` again.

## Rotating a token

    sky setup rotate <instance>

Replaces one instance's token and leaves every other line alone. It refuses a
value identical to the stored one, because that is almost always a paste of the
old token and would otherwise report success. Afterwards: close every terminal
and restart — a running process still holds the old token, and it will keep
working until it does not.

## Adding another knowledge base

Run `init` again with the second profile. The map holds several entries; which
one a task uses is decided by the directory it runs in, then by `--kb`, then by
the default. A repository belonging to one privacy class never falls back to a
default of another — it gets no knowledge base and says so.

## What this never does

- **Never asks for a token in the conversation, and never echoes one.**
- Never writes a token into a settings file, a map, or a ticket.
- Never edits the user's MCP configuration except through `sky setup`, which
  shows the change first and records what it added so `uninstall` removes only
  that.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **`sky setup doctor`, not the absence of an error** —
reading your own output and concluding it is fine is not verification.

- **Run `sky setup doctor` afterwards and read it back.** A command that exited zero
  is not the same as a working configuration.
- **Check the launcher's directory is on PATH** and say so plainly if it is not —
  "installed somewhere PATH does not look" is the failure this step exists to end.
- Never echo a token to confirm it was written. Confirm the variable's NAME is there.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.
