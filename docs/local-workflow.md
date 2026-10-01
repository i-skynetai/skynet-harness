# The local loop

What a managed run looks like from your side, and the one habit that matters.

## The loop

1. `./sky doctor` — confirm the knowledge base and the coding agent are ready.
2. `./sky build --task <ID> --role developer --hand claude` — the harness
   resolves the KB, applies the role, blocks the credential paths and launches.
3. The agent works. It can read, edit, run tests and commit locally.
4. You review. Then you decide what leaves the machine.

## Reviewing before you commit

Stage deliberately and read what you staged:

```bash
git add path/to/the/file.py
git add path/to/the/test.py
git diff --staged
```

Not `git add -A`. A blanket add stages whatever else the run touched — a scratch file, a
rewritten lockfile, a config the agent edited to make something pass. You then commit it
without having read it, which is the failure this whole project exists to prevent.

## Outward actions

The harness renders the command. You run it.

```
The broker would run:

    git push origin feat/PROJ-123

Nothing has been pushed. Copy the command if you want it.
```

This is why a run record cannot contain "I opened a pull request" unless one was opened.
Opening one was never something the agent could do.

## Reading the evidence

Each managed run leaves a local record: its identity, the events, the result, and the
usage the coding agent reported. The model does not write it.

When a run claims something surprising, the record is the thing to check — not the
transcript.
