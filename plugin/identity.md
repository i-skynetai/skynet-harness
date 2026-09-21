# Who is doing this, and who is answerable

Two different questions, and conflating them is how an audit trail becomes
fiction.

## The agent is *declared*, not proven

A run carries an agent id and a run id. The **runtime** writes both; a model
never does. They say *which configured agent this session is*, and that is all
they say. They are not a credential and they authenticate nothing.

Every outward system — the git host, the ticket tracker, the knowledge base —
records the **person whose token was used**. There is no per-agent credential
to be had: a token identifies the whole person, every tenant, no scope. So:

> The agent id says which agent ran. The token says who is answerable. They are
> never the same claim, and a document that blurs them is worse than one that
> omits the agent entirely.

## The stamp

Every artifact a run produces carries the same five fields:

    sky_agent · sky_run · sky_role · sky_task · sky_kb

Get them from `sky stamp --json`. **Do not compose them yourself** — a stamp a
model assembled is a stamp a model can get wrong, and the whole value of the
field is that it was not.

An ingest without the stamp is refused. Not because the fields are magic, but
because an unstamped document cannot later be traced to the run that produced
it, and a knowledge base full of those is a knowledge base nobody can audit.

## The commit trailer

A commit made inside a run carries one line, exactly:

    SKY-Agent: <agent id> <run id>

The runtime supplies it. The broker refuses to push a commit that does not
carry it — which is what turns "the model will remember" into a check, since
the hand runs `git commit` itself.

## What you must never claim

- **Never write an approval.** `approved_by`, `approved_at`, `channel` and
  `executed` belong to the runtime on the intent contract. A hand that could
  write one could approve its own push.
- **Never assert an outcome the runtime observes** — the commit that exists,
  the pull request that was opened, what CI said, how long you ran, what it
  cost. Report what you did; the runtime reports what happened.
- **Never claim to be a person.** Not in a commit message, not in a ticket
  comment, not in a pull request body. The person's name is on it already,
  because their token carried it.
