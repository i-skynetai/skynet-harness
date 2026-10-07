# How a skill works here

A skill is not a prompt. It is the procedure for one job, plus the code and
examples that job needs, kept where a future run can find them. Four rules, and
each exists because the alternative costs something measurable.

---

## 1. Save the code. Do not re-derive it.

When a run writes a script that works, **save it in the skill** and call it next
time. Re-deriving it costs tokens on every run, and — worse — gives a slightly
different script each time, so the output drifts for reasons nobody can see.

```
skills/<name>/
    SKILL.md          the procedure
    scripts/          code the procedure runs
    reference/        examples, templates, voice — things to imitate
```

A step that says *"render the diagram"* is a step that gets reinvented. A step
that says *"run `scripts/render-diagram.py`"* is one that behaves the same on
Tuesday as it did on Monday.

**When a run produces a script worth keeping**, say so and stop: a script in a
skill is code that later runs unread, so it arrives by a reviewed change like
any other code — `/sky:sync` shows it in full before it lands.

## 2. A skill nobody can find is a skill nobody has.

The host reads only each skill's `name` and `description` until one matches;
the body and the scripts stay on disk. That is what keeps twenty-one skills from
filling the context — and it means the description is the whole of how a skill
gets chosen.

A description must say **what it does** and **when to use it, in the words a
person would actually type**:

> Retrieve cited context from the knowledge base for a ticket or topic. Use when
> the user asks to "get context for `<TICKET>`", "what do we know about X", "how
> does Y work" …

Two skills must not claim the same trigger. "Helps with content" and "creates
marketing assets" overlap, name no trigger, and leave the host guessing —
`sky selftest` fails on both.

## 3. A correction that dies with the session is a correction you will make again.

When a run goes wrong, fixing the output is half the job. Ask what kind of
wrong it was, and put the fix in **the smallest durable place**:

| what was wrong | where the fix belongs |
|---|---|
| the procedure was wrong or incomplete | the steps in `SKILL.md` |
| it lacked your voice, format or an example | a file in `reference/` |
| the same mistake keeps coming back | an explicit rule in `SKILL.md`, saying *not* to |
| the code was unreliable | the script in `scripts/` |

Then **run the same task again** and check the fix held. A skill becomes a
record of how this job is actually done here, and that only happens if each
correction is written down once.

This is what `/sky:learn` is for. It is deliberately not a transcript: a skill
stores the *procedure*, not the conversation.

## 4. Your first look should not be the agent's first look.

A skill that hands over its first attempt has done perhaps 70% of the job and
left the rest to you. Before returning anything:

1. **State the acceptance criteria** — what "done" means for this task.
2. **Produce a first version.** Treat it as a draft, not an answer.
3. **Check it against evidence outside the draft.** Reading your own work and
   concluding it is fine is not verification. Real evidence looks like: a test
   that ran, a rendered image somebody looked at, the primary source a claim
   came from, a command's actual output.
4. **Fix everything found, and check again.**
5. **Return it with what you checked** — and say plainly what you could not
   verify, rather than leaving it to be discovered.

**Where the evidence comes from, per kind of work:** code → the tests run and
their output. A document with a diagram → the image rendered and read back. A
claim about the repository or a system → the file, the command, the source. A
judgement call about tone or audience → a second opinion, not your own second
read.

What this does *not* mean is running until it looks impressive. If a thing
cannot be verified, say so — "I could not check X" is a finding, and a useful
one.
