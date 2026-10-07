"""The `sky` command.

Standard library only, on purpose: Ethan depends on this and carries no
dependencies of its own, so adding one here would add one there.

`doctor`, `kb`, `policy` and `build` work. `build` is the launcher — the one
place the rule *a brain with no Safety may answer and review, but may not
build* is applied, because it runs before the model exists.

`build` refuses without a policy or a matching Claude agent definition: that
definition carries tier A, so a role name alone is a label rather than a
boundary. A brain that is not ready stops after the probes, naming the part
to fix.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
import os
import sys
from pathlib import Path

from . import broker, guard, hand, hosts, launcher, probes, recorder, selftest, setup, usage
from .kbmap import CONFIG_DIR, KBMap, KBMapError, NoKBForPath
from .policy import Policy, PolicyError
from .readiness import Kind
from .agent_definitions import DefinitionError, check_definition
from . import context_sources

EXIT_OK, EXIT_PROBLEM, EXIT_MISUSE = 0, 1, 2


def _load_map(args) -> KBMap:
    return KBMap.load(Path(args.kb_map) if args.kb_map else None)


def _resolve_kb(args):
    """A configured local source needs no remote KB map or credential."""
    context = context_sources.load(Path.cwd())
    if context and context.local and not args.kb:
        return context_sources.LocalMap(), context_sources.local_kb(context), context
    kbmap = _load_map(args)
    return kbmap, kbmap.resolve(Path.cwd(), override=args.kb), None


def _load_policy(args) -> Policy | None:
    """The policy, or None with the reason printed.

    None is not fatal for `doctor` — reporting that Safety is missing is the
    whole job. It IS fatal for `build`, because the tool allowlist lives here.
    """
    try:
        policy = Policy.load(getattr(args, "policy", None))
        if getattr(policy, "notice", ""):
            print(policy.notice)
        return policy
    except PolicyError as exc:
        print(f"policy: {exc}", file=sys.stderr)
        return None


def cmd_doctor(args) -> int:
    """What is alive, and what that permits."""
    try:
        kbmap, kb, context = _resolve_kb(args)
    except (KBMapError, NoKBForPath, context_sources.ContextError) as exc:
        # Not a crash — an unconfigured machine is a normal state. Say what to
        # do about it, then still probe and show everything else.
        print(f"sky doctor: {exc}", file=sys.stderr)
        print("no knowledge base — the rows below that need one read MISSING\n")
        brain = probes.run_all(None, policy=_load_policy(args), cwd=Path.cwd(),
                               no_kb=f"{exc}")
        enforced = os.environ.get("SKY_LAUNCHED") == "1"
        print(brain.table(enforced=enforced))
        return EXIT_PROBLEM

    print(f"KB {kb.name}  ({kb.privacy})  tenant {kb.tenant}  ontology {kb.ontology}")
    cat = kbmap.catalogue()
    if cat:
        print(f"catalogue {cat.name}  tenant {cat.tenant}  — skills, read-only, "
              f"alongside the task KB")
    print(f"   {kb.url}")
    if kb.code_url:
        print(f"   {kb.code_url}   (code index)")
    print()

    brain = probes.run_all(kb, policy=_load_policy(args), cwd=Path.cwd(),
                           deep=getattr(args, 'deep', False))
    # A session we did not start ourselves has no scrubbed environment, so the
    # tiers below A are not enforced in it. Say so rather than imply otherwise.
    enforced = os.environ.get("SKY_LAUNCHED") == "1"
    print(brain.table(enforced=enforced))

    return EXIT_OK if brain.ready_for(Kind.QUESTION) else EXIT_PROBLEM


def cmd_kb(args) -> int:
    """Inspect mapped KBs, or operate the project's validated local store."""
    if args.kb_action in ("serve", "put", "show", "search", "init", "decide", "analyze", "plan", "knowledge", "refresh"):
        from .kbcommands import execute
        return execute(args)
    try:
        kbmap = _load_map(args)
    except KBMapError as exc:
        print(f"sky kb: {exc}", file=sys.stderr)
        return EXIT_PROBLEM

    if args.kb_action == "list":
        try:
            here = kbmap.resolve(Path.cwd())
        except (KBMapError, NoKBForPath):
            here = None
        for kb in sorted(kbmap, key=lambda k: k.name):
            marks = []
            if kb.default:
                marks.append("default")
            if here and kb.name == here.name:
                marks.append("← this directory")
            if not kb.write:
                marks.append("read-only")
            tail = f"   [{', '.join(marks)}]" if marks else ""
            print(f"  {kb.name:<16} {kb.privacy:<8} {kb.purpose[:60]}{tail}")
        return EXIT_OK

    # `sky kb which`
    try:
        kb = kbmap.resolve(Path.cwd(), override=args.kb)
    except (KBMapError, NoKBForPath) as exc:
        print(f"sky kb: {exc}", file=sys.stderr)
        return EXIT_PROBLEM
    if args.kb:
        reason = "chosen with --kb"
    elif kbmap.owner_of(Path.cwd()):
        reason = "this directory belongs to it"
    else:
        reason = "it is the default"
    print(f"{kb.name}   ({reason})")
    return EXIT_OK


def _emit(args, **summary) -> None:
    """The one line a program reads. Printed last, on stdout, only with --json.

    Ethan calls `sky build` and needs to know what happened without parsing
    prose. Every exit from `cmd_build` — refusal included — goes through here,
    so a caller always gets a structured answer and never has to guess from an
    exit code why nothing started.
    """
    if getattr(args, "json", False):
        import json
        print(json.dumps({"sky": "build", **summary}, default=str), flush=True)


def cmd_build(args) -> int:
    """Start a hand — or refuse, and say which part is the problem.

    The order is the design: resolve, check, build the environment, prove it.
    Nothing starts until the proof passes.
    """
    kind = Kind.BUILD if args.role == "developer" else Kind.REVIEW
    try:
        kbmap, kb, context = _resolve_kb(args)
    except (KBMapError, NoKBForPath, context_sources.ContextError) as exc:
        print(f"sky build: {exc}", file=sys.stderr)
        _emit(args, outcome="refused", ok=False, reason=str(exc), stage="kb")
        return EXIT_PROBLEM

    policy = _load_policy(args)
    if policy is None:
        print("\nsky build refused — there is no policy, so there is no tool "
              "allowlist,\n    and a role without one is a label rather than a "
              "boundary.", file=sys.stderr)
        _emit(args, outcome="refused", ok=False, stage="policy",
              reason="no policy — no tool allowlist, so a role is a label, not a boundary")
        return EXIT_PROBLEM

    agent_id = os.environ.get("SKY_AGENT_ID", f"{os.environ.get('USER', 'someone')}-{args.role}-1")
    run = recorder.Run.start(role=args.role, task=args.task, kb=kb.name, agent_id=agent_id)
    print(f"run {run.run_id}   {agent_id}   KB {kb.name}", flush=True)

    if args.hand == "claude":
        try:
            if hasattr(policy, "requires_identity_selection") and policy.requires_identity_selection(args.role):
                raise DefinitionError("effective identity selection lands with SH-062")
            definition = check_definition(policy, args.role)
        except DefinitionError as exc:
            print(f"  agent definitions  MISSING  {exc}")
            run.event("launch_refused", hand=args.hand, role=args.role, reason=str(exc))
            run.refused("agent definition failed", detail=str(exc))
            run.finish("refused")
            print(f"\nsky build refused — {exc}", file=sys.stderr)
            _emit(args, outcome="refused", ok=False, stage="agent-definition",
                  reason=str(exc), run_id=run.run_id, directory=run.directory,
                  agent_id=agent_id, kb=kb.name)
            return EXIT_PROBLEM
        print(f"  agent definitions  ok       {args.role}: {definition}")
        run.event("agent.definition.checked", role=args.role, file=str(definition))

    # 2. readiness — before anything is built, and before anything is started
    brain = probes.run_all(kb, hand=args.hand, policy=policy, cwd=Path.cwd())
    try:
        launcher.check_readiness(brain, kind)
    except launcher.Refused as exc:
        run.refused("not ready", kind=kind.value)
        run.finish("refused")
        print(f"\nsky build refused — {exc}", file=sys.stderr)
        print(f"\n    run record: {run.directory}", file=sys.stderr)
        _emit(args, outcome="refused", ok=False, stage="readiness", reason=str(exc),
              run_id=run.run_id, directory=run.directory, agent_id=agent_id, kb=kb.name)
        return EXIT_PROBLEM

    # 3. the environment the hand will get
    env = launcher.build_env(kb, run_id=run.run_id, agent_id=agent_id,
                             role=args.role, task=args.task,
                             directory=run.directory)
    try:
        # 4. prove it, rather than assume it
        blocked, why = launcher.prove_git_blocked(env, Path.cwd())
        run.event("git.block.checked", blocked=blocked, detail=why)
        if not blocked:
            run.refused("git block failed", detail=why)
            run.finish("refused")
            print(f"\nsky build refused — {why}", file=sys.stderr)
            print(f"\n    run record: {run.directory}", file=sys.stderr)
            _emit(args, outcome="refused", ok=False, stage="git-block", reason=why,
                  run_id=run.run_id, directory=run.directory, agent_id=agent_id, kb=kb.name)
            return EXIT_PROBLEM
        print(f"git block proven: {why}")

        mcp = (context_sources.mcp_config(context, run.directory) if context else
               launcher.write_mcp_config(env, kb, run.directory, catalogue=kbmap.catalogue()))
        try:
            cmd = launcher.hand_command(args.hand, args.role, mcp, args.task or "",
                                        policy)
        except launcher.Refused as exc:
            run.event("launch_refused", hand=args.hand, role=args.role, reason=str(exc))
            run.refused("hand cannot enforce the role", hand=args.hand, role=args.role)
            run.finish("refused")
            print(f"\nsky build refused — {exc}", file=sys.stderr)
            _emit(args, outcome="refused", ok=False, stage="hand", reason=str(exc),
                  run_id=run.run_id, directory=run.directory, agent_id=agent_id, kb=kb.name)
            return EXIT_PROBLEM
        run.event("hand.command", hand=args.hand, role=args.role,
                  tools=policy.tools_for(args.role),
                  policy=str(policy.path or "built-in"))

        if context:
            # Protocol availability cannot grant roles different MCP names.
            # Readiness and authority must both hold, including for dry-runs.
            source = context.sources["local"]
            needed = [f"mcp__{source['server']}__{source[op]['tool']}"
                      for op in ("search.keyword", "graph.neighbours", "decisions.find") if op in source]
            missing = next((tool for tool in needed if tool not in policy.tools_for(args.role)), None)
            if missing:
                why = f"local context tool {missing} is not granted to {args.role}; render matching policy and agent grants"
                run.event("launch_refused", hand=args.hand, role=args.role, reason=why)
                run.refused(why)
                run.finish("refused")
                print(f"sky build refused — {why}", file=sys.stderr)
                _emit(args, outcome="refused", ok=False, stage="local-grants", reason=why,
                      run_id=run.run_id, directory=run.directory)
                return EXIT_PROBLEM

        if args.dry_run:
            print("\n--dry-run: everything above passed; the hand was not started.")
            print("  command      "
                  + " ".join(launcher.without_prompt(cmd, args.task or "")))
            secret = [k for k in env.variables if launcher.is_secret(k)]
            print(f"  environment  {len(env.variables)} variables, "
                  f"{len(secret)} secret ({', '.join(secret)})")
            cat = kbmap.catalogue()
            if context:
                print("  mcp servers  " + ", ".join(sorted(context.servers)))
            else:
                print(f"  mcp servers  {kb.name}" + (" + code" if kb.code_url else "")
                      + (f" + catalogue ({cat.name})" if cat and cat.name != kb.name else ""))
            print(f"  run record   {run.directory}")
            if context:
                print(f"  local MCP grants verified for {args.role}; local context readiness checked")
            run.finish("dry-run")
            _emit(args, outcome="dry-run", ok=True, run_id=run.run_id,
                  directory=run.directory, agent_id=agent_id, kb=kb.name,
                  role=args.role, hand=args.hand)
            return EXIT_OK

        print(f"\nstarting {args.hand} as {args.role}…  (log: {run.directory}/hand.log)")
        run.event("hand.start", command=launcher.without_prompt(cmd, args.task or ""))
        result = hand.run(cmd, env=env.variables, cwd=Path.cwd(),
                          log_path=run.directory / "hand.log")
        run.event("hand.end", reason=result.reason, exit_code=result.exit_code,
                  seconds=round(result.seconds, 1))

        # What the hand asked to have done outside the machine. It never ran
        # `sky`; it left files in the outbox, and the runtime seals each with
        # this run's identity now (SH-004). Nothing is executed.
        filed, refused = broker.collect_outbox(
            Path.cwd() / broker.OUTBOX, run_id=run.run_id, agent_id=agent_id,
            pending=Path.cwd() / PENDING)
        for path in filed:
            run.event("intent.filed", intent=path.name)
        for path, why in refused:
            run.event("intent.refused", file=path.name, reason=why)
        if filed:
            print(f"\n{len(filed)} outward action(s) waiting for you — run `sky ship`.")
        for path, why in refused:
            print(f"  not passed on: {path.name} — {why}", file=sys.stderr)

        # The bill, per run: from the hand's own structured report, read back
        # from the durable log. Recorded whether or not it was available, with
        # the reason when it was not — a blank on a dashboard must say why.
        report = usage.from_log(args.hand, run.directory / "hand.log")
        run.event("run.usage", **report.as_event())

        print(f"\n{result}   ·   {report}")
        # What a person sees is the hand's final text. With stream-json the raw
        # tail is JSON events, which is the record and not the message.
        shown = report.result_text or result.tail
        if shown:
            print("\n".join("  " + line for line in shown.splitlines()[-8:]))
        run.finish(result.reason)
        print(f"\nrun record: {run.directory}")
        _emit(args, outcome=result.reason, ok=result.ok, exit_code=result.exit_code,
              seconds=round(result.seconds, 1), run_id=run.run_id,
              directory=run.directory, agent_id=agent_id, kb=kb.name,
              role=args.role, hand=args.hand, usage=report.as_event(),
              result_text=report.result_text)
        return EXIT_OK if result.ok else EXIT_PROBLEM
    finally:
        env.close()


def cmd_policy(args) -> int:
    """Show the policy, or check that it holds together."""
    policy = _load_policy(args)
    if policy is None:
        return EXIT_PROBLEM

    if hasattr(policy, "layers_notice") and (args.policy_action == "lint" or
            args.policy_action == "show" and getattr(args, "layers", False)):
        print(policy.layers_notice())

    directory = Path(args.what) if args.what else \
        (policy.path.parent / "agents" if policy.path else Path("agents"))
    if args.policy_action == "lint":
        problems = policy.artifact_problems(directory)
        if problems:
            for problem in problems:
                print(problem)
            return EXIT_PROBLEM
        # Loading already ran the lint and refused a broken file, so reaching
        # here means it is clean. Saying so plainly is the point of the command.
        shown = policy.path
        try:
            shown = policy.path.resolve().relative_to(Path.cwd().resolve())
        except (AttributeError, ValueError):
            pass                       # outside this directory: the full path
        print(f"{shown}: clean")
        print(f"    {len(policy.roles)} roles, {len(policy.actions)} actions, "
              f"{len(policy.guard.get('deny_commands') or ())} guard rules")
        return EXIT_OK

    if args.policy_action in ("render", "sync-agents", "check-agents"):
        # The agent files live beside the policy, in the plugin.
        directory = Path(args.what) if args.what else \
            (policy.path.parent / "agents" if policy.path else Path("agents"))
        write = args.policy_action != "check-agents"
        try:
            if hasattr(policy, "layer_lines"):
                if args.what:
                    raise PolicyError("managed render uses the project .claude directory")
                directory = policy.root / ".claude" / "agents"
                changed = policy.render() if write else policy.artifact_problems()
            else:
                changed = policy.render(directory) if write else policy.sync_agents(directory, write=False)
        except (PolicyError, OSError, UnicodeError) as exc:
            print(f"policy render refused: {exc}", file=sys.stderr)
            return EXIT_PROBLEM
        if not changed:
            print(f"{directory}: all {len(policy.roles)} role agents match the policy")
            return EXIT_OK
        for item in changed:
            print(("updated " if write else "DRIFTED ") + item)
        if not write:
            print("\n    Run `sky policy render` to bring them back in line.")
        return EXIT_OK if write else EXIT_PROBLEM

    if args.policy_action == "show":
        print(f"policy {policy.path}   version {policy.version}\n")
        if getattr(args, "layers", False):
            print("  layers:")
            if hasattr(policy, "layer_lines"):
                for line in policy.layer_lines():
                    print("      " + line)
            else:
                print("      single explicit or discovered policy")
        for role in policy.roles_named():
            spec = policy.roles[role]
            print(f"  {role}")
            print(f"      {spec.get('purpose', '')}")
            print(f"      tools        {', '.join(policy.tools_for(role))}")
            print(f"      may          {', '.join(spec.get('may') or ()) or '—'}")
            print(f"      needs a human {', '.join(spec.get('needs_human') or ()) or '—'}")
        never = [a for a in policy.actions.values() if a.never]
        print(f"\n  never, for anyone ({len(never)}):")
        for action in sorted(never, key=lambda a: a.name):
            print(f"      {action.name:<20} {action.never}")
        granted = {skill for role in policy.roles_named() for skill in policy.skills_for(role)}
        ungranted = sorted(set(policy.skills) - granted)
        if ungranted:
            print("\n  declared, granted to no role (procedure alignment: SH-082):")
            print("      " + ", ".join(ungranted))
        return EXIT_OK

    # `sky policy check <role> <action>` — the same call the guard makes.
    decision = policy.decide(args.policy_action, args.what or "")
    print(decision)
    return EXIT_OK if decision.allowed else EXIT_PROBLEM


def cmd_selftest(args) -> int:
    """Is this repository still the thing it claims to be?"""
    root = Path(args.root).expanduser() if args.root else _repo_root()
    if root is None:
        print("sky selftest: run this inside the harness repository, or pass "
              "--root", file=sys.stderr)
        return EXIT_MISUSE

    print(f"selftest  {root}\n")
    results = selftest.run_all(root)
    for result in results:
        print(result)

    failed = [r for r in results if not r.passed]
    skipped = [r for r in results if r.skipped]
    print()
    if skipped:
        # A skipped check is not a passed one. Saying so is the difference
        # between "nothing was wrong" and "nothing was looked at".
        print(f"{len(skipped)} check(s) did not run — see SKIP above.")
    if failed:
        print(f"FAIL — {len(failed)} of {len(results)} checks.")
        return EXIT_PROBLEM
    print(f"PASS — {len(results) - len(skipped)} checks.")
    return EXIT_OK


def _repo_root() -> Path | None:
    """The harness repository, found from where core actually is."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "plugin").is_dir() and (candidate / "core").is_dir():
            return candidate
    return None



def _read_token(prompt: str, token_env: str | None) -> str:
    """A token, from a named variable or a hidden prompt — never from argv.

    Not from argv because argv is in the process table, the shell history and
    every transcript. Not from a pipe either: the usual reason standard input
    is not a terminal is that something is recording, and a recorded token is
    a spent one. `--token-env` is the deliberate exception, for a script whose
    author has thought about where the value came from.
    """
    if token_env:
        value = os.environ.get(token_env, "")
        if not value:
            print(f"${token_env} is not set", file=sys.stderr)
            raise SystemExit(EXIT_MISUSE)
        return value
    if not sys.stdin.isatty():
        print("a token has to be typed at a terminal. Run this in one, or pass "
              "--token-env with the name of a variable holding it.", file=sys.stderr)
        raise SystemExit(EXIT_MISUSE)
    import getpass
    return getpass.getpass(prompt)


def cmd_setup(args) -> int:
    action = args.setup_action
    try:
        if getattr(args, "local", False):
            if action != "init":
                raise setup.SetupError("--local is only supported by setup init")
            print(setup.init_local(Path.cwd(), force=getattr(args, "force", False)))
            return EXIT_OK
        if getattr(args, "force", False):
            raise setup.SetupError("--force is only supported by setup init --local")
        if action == "init":
            if not args.profile:
                print("`sky setup init` needs --profile <file>, the JSON your "
                      "administrator sent you.", file=sys.stderr)
                return EXIT_MISUSE
            profile = setup.Profile.load(Path(args.profile))
            if args.name:
                profile = replace(profile, name=args.name)
            print(f"\n{profile.name}: tenant {profile.tenant}, ontology "
                  f"{profile.ontology}, class {profile.privacy}\n")
            print("This will:")
            for change in setup.plan(profile, claude_json=_claude_json(args)):
                print(change)
            if not args.yes:
                print()
                if input("Go ahead? [y/N] ").strip().lower() not in ("y", "yes"):
                    print("nothing was written.")
                    return EXIT_OK
            token = _read_token(f"{profile.instance} token (hidden): ",
                                args.token_env)
            written = setup.init(profile, token, claude_json=_claude_json(args),
                                 register=not args.no_register,
                                 replace_servers=args.replace_servers)
            print()
            for path in written:
                print(f"  wrote {path}")
            launcher = Path(setup.LAUNCHER_DIR) / "sky"
            on_path = str(launcher.parent) in os.environ.get(
                "PATH", "").split(os.pathsep)
            print()
            if on_path:
                print("`sky` is now on your PATH.")
            else:
                # Saying this plainly matters: "installed, somewhere PATH does
                # not look" is the failure this launcher exists to end.
                print(f"`sky` was installed at {launcher}, which is NOT on your "
                      f"PATH.\nAdd it before using the skills:\n"
                      f'    export PATH="{launcher.parent}:$PATH"')
            print("\nThen restart Claude and run `sky setup doctor`.")
            return EXIT_OK

        if action == "use":
            if not args.instance:
                print("`sky setup use` needs a knowledge-base name, e.g. "
                      "`sky setup use team_kb`.", file=sys.stderr)
                return EXIT_MISUSE
            print(setup.use(args.instance, claude_json=_claude_json(args)))
            return EXIT_OK

        if action == "rotate":
            if not args.instance:
                print("`sky setup rotate` needs the instance name, e.g. "
                      "`sky setup rotate example-kb`.", file=sys.stderr)
                return EXIT_MISUSE
            token = _read_token(f"new {args.instance} token (hidden): ",
                                args.token_env)
            path = setup.rotate(args.instance, token)
            print(f"{setup.token_variable(args.instance)} replaced in {path}.")
            print("Close every terminal and restart Claude — a running process "
                  "still holds the old one.")
            return EXIT_OK

        if action == "doctor":
            findings = setup.doctor(claude_json=_claude_json(args))
            print()
            for finding in findings:
                print(finding)
            bad = [f for f in findings if not f.ok]
            print(f"\n{'FAIL' if bad else 'PASS'} — {len(findings) - len(bad)}"
                  f"/{len(findings)} checks.")
            return EXIT_PROBLEM if bad else EXIT_OK

        if action == "uninstall":
            for line in setup.uninstall(claude_json=_claude_json(args),
                                        remove_tokens=args.remove_tokens):
                print(f"  {line}")
            return EXIT_OK
    except setup.SetupError as exc:
        print(f"sky setup: {exc}", file=sys.stderr)
        return EXIT_PROBLEM

    print(f"unknown action {action!r}", file=sys.stderr)
    return EXIT_MISUSE


def _claude_json(args) -> Path | None:
    return Path(args.claude_json) if getattr(args, "claude_json", None) else None



def cmd_guard(args) -> int:
    """PreToolUse. Reads the host's JSON on stdin, answers on stdout.

    **With no policy, fails closed inside a managed run, loudly.** The run was
    promised these rules, so every command is denied and the reason goes to
    stderr and to the host. Outside a managed run the guard stands aside, as
    it does for every command there. Tier A, the tool allowlist, is the
    boundary; this is the layer under it.
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError as exc:
        print(f"sky guard: unreadable hook input ({exc})", file=sys.stderr)
        print(json.dumps(guard.Verdict("allow").as_hook_output()))
        return EXIT_OK
    try:
        where = Path(args.policy) if args.policy else Policy.find()
        policy = Policy.load(where) if where else None
        if policy is None:
            raise PolicyError("none is installed and none was given")
    except (PolicyError, OSError) as exc:
        where_said = ("denying every command in this managed run"
                      if guard.in_managed_run() else "standing aside")
        print(f"sky guard: no policy ({exc}); {where_said}", file=sys.stderr)
        policy = None
    verdict = guard.decide(payload, policy)
    guard.record(payload, verdict)
    print(json.dumps(verdict.as_hook_output()))
    return EXIT_OK


def cmd_ledger(args) -> int:
    """PostToolUse. Records what ran; never changes what happens."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return EXIT_OK
    if getattr(args, "mcp", False):
        from . import ledger
        try:
            if not isinstance(payload, dict) or not str(payload.get("tool_name", "")).startswith("mcp__"):
                return EXIT_OK
            root = context_sources.repository(payload.get("cwd"))
            ledger.record(payload, context=context_sources.load(root=root))
        except context_sources.NotManaged:
            pass
        except (ValueError, OSError, PolicyError) as exc:
            print(f"sky ledger: observation failed: {exc}", file=sys.stderr)
            return EXIT_PROBLEM
    else:
        guard.record(payload)
    return EXIT_OK


def cmd_context(args):
    from . import contextcommands
    return contextcommands.execute(args)



def cmd_stamp(args) -> int:
    """The five fields every artifact a run produces must carry.

    A command rather than a documented convention, because a stamp a model
    assembled is a stamp a model can get wrong — and the entire value of the
    field is that it was not written by the thing being audited.

    Outside a run the fields are empty and it says so on stderr, exit 1: an
    interactive session has no run to attribute anything to, and inventing one
    would put a fictional id into a knowledge base.
    """
    stamp = {
        "sky_agent": os.environ.get("SKY_AGENT_ID", ""),
        "sky_run": os.environ.get("SKY_RUN_ID", ""),
        "sky_role": os.environ.get("SKY_ROLE", ""),
        "sky_task": os.environ.get("SKY_TASK", ""),
        "sky_kb": os.environ.get("SKY_KB_NAME", ""),
    }
    missing = [k for k in ("sky_agent", "sky_run") if not stamp[k]]
    if missing:
        print("sky stamp: this session is not a run — "
              + ", ".join(missing) + " are not set. An ingest from here cannot "
              "be attributed, so it should not claim to be.", file=sys.stderr)
        if not args.json:
            return EXIT_PROBLEM
    print(json.dumps(stamp) if args.json
          else "\n".join(f"{k}={v}" for k, v in stamp.items()))
    return EXIT_OK if not missing else EXIT_PROBLEM



def cmd_host(args) -> int:
    """Write the package for a coding agent that is not Claude.

    It prints what each file is for, because a generated configuration nobody
    understands is one nobody maintains — and the first line of every package
    says what that host can and cannot actually enforce.
    """
    try:
        where = Path(args.policy) if args.policy else Policy.find()
        policy = Policy.load(where) if where else None
        profile = (setup.Profile.load(Path(args.profile))
                   if args.profile else None)
        package = hosts.build(args.host_name, policy, profile=profile)
    except hosts.HostError as exc:
        print(f"sky host: {exc}", file=sys.stderr)
        return EXIT_MISUSE
    except PolicyError as exc:
        print(f"sky host: the policy did not load ({exc}). A package without "
              f"the rules would say nothing worth reading.", file=sys.stderr)
        return EXIT_PROBLEM
    if not args.into:
        # The skills make this hundreds of pages; list them and print the
        # configuration, which is the part a person actually reads.
        for name in sorted(package.files):
            if name.startswith("skills/"):
                print(f"   {name}")
                continue
            print(f"── {name} " + "─" * max(0, 60 - len(name)))
            print(package.files[name])
        return EXIT_OK
    for path in package.write(Path(args.into)):
        print(f"  wrote {path}")
    enforces, roles = hosts.CAN_ENFORCE[args.host_name]
    print(f"\n{args.host_name} enforces {enforces}.")
    print(f"Roles it may be asked to run: {hosts.roles_line(roles)}.")
    return EXIT_OK



PENDING = ".sky/pending"


def cmd_intent(args) -> int:
    """See `--from-file`: model-written text must never cross a shell."""
    """A hand asks for an outward action. It does not perform one.

    The runtime stamps the run and agent onto it here, which is why this is a
    command and not a file the hand writes itself: a request that carried its
    own `run_id` would be a request that could claim to come from a different
    run — or, with `approved_by`, to have been approved already.
    """
    if args.from_file:
        # The safe path, and the one the skill uses. A model that writes
        # `--body "$(…)"` or a backtick into a shell argument has already run
        # it: the shell expands before `sky` is even started, so every check in
        # the broker happens too late. Writing a JSON file with an editor tool
        # and naming it here means model text never touches a command line.
        try:
            body = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"sky intent: cannot read {args.from_file}: {exc}",
                  file=sys.stderr)
            return EXIT_PROBLEM
        if not isinstance(body, dict):
            print(f"sky intent: {args.from_file} should hold one JSON object",
                  file=sys.stderr)
            return EXIT_PROBLEM
        body = {k: v for k, v in body.items() if v not in ("", None)}
    else:
        body = {k: v for k, v in (
            ("kind", args.kind), ("summary", args.summary), ("branch", args.branch),
            ("remote", args.remote), ("base", args.base), ("title", args.title),
            ("body", args.body), ("issue_key", args.issue),
            ("to_state", args.to_state),
        ) if v}
    if not body.get("kind"):
        print("sky intent: no kind — pass --kind, or put one in the file",
              file=sys.stderr)
        return EXIT_MISUSE
    run_id = os.environ.get("SKY_RUN_ID", "")
    agent_id = os.environ.get("SKY_AGENT_ID", "")
    if not run_id or not agent_id:
        print("sky intent: this session is not a run, so an intent from it "
              "cannot be attributed. Run the action yourself.", file=sys.stderr)
        return EXIT_PROBLEM
    try:
        path = broker.file_intent(body, run_id=run_id, agent_id=agent_id,
                                  directory=Path(args.directory or PENDING))
    except broker.Refused as exc:
        print(f"sky intent: {exc}", file=sys.stderr)
        return EXIT_PROBLEM
    print(f"recorded {path} — run `sky ship` to see what a person "
          f"then does")
    return EXIT_OK


def cmd_ship(args) -> int:
    """Render every pending intent. Runs none of them.

    This is the command `/sky:ship` calls. It matters that it is a command:
    a skill that asked the model to compose the push line would be a skill in
    which the model chooses what goes on a command line, and every validation
    in the broker would be decoration.
    """
    intents = broker.read_pending(Path(args.directory or PENDING))
    if not intents:
        print("nothing pending.")
        return EXIT_OK
    problems = 0
    for intent, result in broker.render_all(intents):
        print()
        if isinstance(result, broker.Refused):
            problems += 1
            print(f"REFUSED  {intent.get('kind', '?')} — {result}")
            continue
        print(result)
    print("\nNone of the above has been run. Run them yourself, in this order.")
    if problems:
        print(f"{problems} intent(s) were refused and are not shown as commands.")
    return EXIT_PROBLEM if problems else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sky",
        description="The SKY runtime: resolve a KB, check what is alive, launch a hand.",
    )
    p.add_argument("--kb-map", metavar="PATH",
                   help=f"the KB map to read (default: {CONFIG_DIR}/kb-map.json)")
    p.add_argument("--kb", metavar="NAME",
                   help="use this KB instead of the one this directory resolves to")
    p.add_argument("--policy", metavar="PATH",
                   help="the policy to read (default: $SKY_POLICY, then the "
                        "installed plugin)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="what is alive, and what that permits")
    d.add_argument("--deep", action="store_true",
                   help="also run the probes that write: ingests one small probe "
                        "document and reads its entity count, which is the only "
                        "way to catch an ingest that COMPLETES having learned "
                        "nothing")
    d.set_defaults(func=cmd_doctor)

    k = sub.add_parser("kb", help="which knowledge bases exist, and which one applies here")
    k.add_argument("kb_action", nargs="?", default="list", choices=["list", "which", "serve", "put", "show", "search", "init", "decide", "analyze", "plan", "knowledge", "refresh"])
    k.add_argument("kb_value", nargs="?", help="file, document id or quoted search query")
    k.add_argument("decision_id", nargs="?", help="decision id for decide transitions/show")
    k.add_argument("--from", dest="proposal_from", help="proposal file or - for stdin")
    k.add_argument("--by", help="replacement decision id for supersede")
    k.add_argument("--yes", action="store_true", help="confirm exact revision without prompting")
    k.add_argument("--status", help="decision status filter")
    k.add_argument("--scope", help="repository-relative decision scope filter")
    k.add_argument("--goal", help="requested goal for analyze put")
    k.add_argument("--analysis", dest="analysis_id", help="pinned input analysis for plan put")
    k.add_argument("--module", help="knowledge module filter")
    k.add_argument("--category", help="knowledge category filter")
    k.add_argument("--stale", action="store_true", help="only stale knowledge")
    k.add_argument("--paths", nargs="+", help="repository-relative changed paths for refresh")
    k.add_argument("--root", help="explicit repository root for local KB commands")
    k.add_argument("--type", dest="document_type", help="validated document type for put")
    k.add_argument("-k", type=int, default=10, help="maximum search hits (1–100)")
    k.add_argument("--write-adapter", action="store_true", help="write the local adapter and exit")
    k.add_argument("--add", action="append", default=[], help="additional repository-relative source for init")
    k.add_argument("--discover", action="store_true", help="codebase discovery (SH-088)")
    k.set_defaults(func=cmd_kb)

    pol = sub.add_parser("policy", help="what each role may do, and why")
    pol.add_argument("policy_action", nargs="?", default="show",
                     help="show · lint · render · sync-agents · check-agents · "
                          "a role name, with an action")
    pol.add_argument("what", nargs="?",
                     help="the action when checking a role, or the agents "
                          "directory when syncing")
    pol.set_defaults(func=cmd_policy)
    pol.add_argument("--layers", action="store_true", help="show each grant's source layer")

    st = sub.add_parser("selftest", help="is this repository still sound")
    st.add_argument("--root", metavar="PATH",
                    help="the harness repository (default: the one core is in)")
    st.set_defaults(func=cmd_selftest)

    s = sub.add_parser("setup", help="make an installed plugin into a working one")
    s.add_argument("--local", action="store_true", help="init a managed local project without services")
    s.add_argument("--force", action="store_true", help="replace local project configuration")
    s.add_argument("setup_action",
                   choices=["init", "use", "rotate", "doctor", "uninstall"])
    s.add_argument("instance", nargs="?",
                   help="for rotate: which instance. for use: which KB")
    s.add_argument("--profile", metavar="PATH",
                   help="for init: the JSON your administrator sent you")
    s.add_argument("--name", metavar="NAME",
                   help="for init: call this KB something other than the "
                        "profile's own name")
    s.add_argument("--token-env", metavar="VAR",
                   help="read the token from this variable instead of prompting")
    s.add_argument("--claude-json", metavar="PATH",
                   help=f"the host's server file (default: {setup.CLAUDE_JSON})")
    s.add_argument("--replace-servers", action="store_true",
                   help="for init: take over an MCP server name that already "
                        "exists. The old entry is recorded, and `uninstall` "
                        "puts it back")
    s.add_argument("--no-register", action="store_true",
                   help="for init: write the configuration but register no MCP "
                        "server with the host")
    s.add_argument("--remove-tokens", action="store_true",
                   help="for uninstall: delete the token file as well")
    s.add_argument("--yes", action="store_true", help="skip the confirmation")
    s.set_defaults(func=cmd_setup)

    it = sub.add_parser("intent", help="ask for an outward action (a hand does this)")
    it.add_argument("--from-file", metavar="PATH",
                    help="read the whole intent from a JSON file — the safe "
                         "way, because text written by a model never reaches a "
                         "shell argument")
    it.add_argument("--kind",
                    choices=["push", "pr.open", "ticket.comment", "ticket.transition"])
    it.add_argument("--summary", default="")
    for opt in ("branch", "remote", "base", "title", "body", "issue", "to-state"):
        it.add_argument(f"--{opt}", default="", dest=opt.replace("-", "_"))
    it.add_argument("--directory", metavar="DIR")
    it.set_defaults(func=cmd_intent)

    sh = sub.add_parser("ship", help="render every pending intent, and run none")
    sh.add_argument("--directory", metavar="DIR")
    sh.set_defaults(func=cmd_ship)

    h = sub.add_parser("host", help="package the rules for another coding agent")
    h.add_argument("host_name", choices=sorted(hosts.BUILDERS))
    h.add_argument("--into", metavar="DIR",
                   help="write the files there (default: list them)")
    h.add_argument("--profile", metavar="PATH",
                   help="fill the address and token variable in from this "
                        "profile instead of leaving placeholders")
    h.set_defaults(func=cmd_host)

    sp = sub.add_parser("stamp", help="the five fields every artifact must carry")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stamp)

    g = sub.add_parser("guard", help="PreToolUse hook: judge one command")
    g.set_defaults(func=cmd_guard)

    rh = sub.add_parser("refresh-hook", help="best-effort freshness observation")
    rh.add_argument("refresh_action", choices=["enqueue", "stop"])
    from .refresh_hooks import command as refresh_hook_command
    rh.set_defaults(func=refresh_hook_command)

    lg = sub.add_parser("ledger", help="PostToolUse hook: record one tool call")
    lg.add_argument("--mcp", action="store_true", help="managed-project MCP observation")
    lg.set_defaults(func=cmd_ledger)

    cx = sub.add_parser("context", help="context adapters and measured retrieval manifests")
    cx.add_argument("context_action", choices=["adapter", "manifest"])
    cx.add_argument("context_value", help="code adapter or run id")
    cx.add_argument("--from-mcp-json")
    cx.add_argument("--server")
    cx.add_argument("--repo")
    cx.add_argument("--branch", default="main")
    cx.add_argument("--json", action="store_true")
    cx.set_defaults(func=cmd_context)

    b = sub.add_parser("build", help="launch a hand for a task")
    b.add_argument("--role", default="developer")
    b.add_argument("--task", default="")
    b.add_argument("--hand", default="claude", choices=sorted(launcher.HAND_COMMANDS))
    b.add_argument("--dry-run", action="store_true",
                   help="run every check and build the environment, but start nothing")
    b.add_argument("--json", action="store_true",
                   help="print one JSON line last, whatever happened — for a caller "
                        "that is a program (Ethan) rather than a person")
    b.set_defaults(func=cmd_build)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
