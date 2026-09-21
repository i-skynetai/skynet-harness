"""Pre-flight validation against the knowledge platform's OWN ontology schema.

A rejected upload is a terse 422 from the server, hours after the file was
written. This catches the same errors locally, using the platform's real schema
rather than a copy — a copy is a second source of truth and goes stale.

**This is a development tool and is not shipped.** It needs the platform's
source tree to import the schema from, which nobody installing the plugin has.
It used to live in `plugin/ontology/` with an absolute path into one
developer's home directory, so it reached every installer and worked for
exactly one of them.

    export SKY_PLATFORM_SRC=/path/to/the/platform/checkout
    <that checkout's python> scripts/validate-ontology.py \
        plugin/ontology/sky_skill.yaml [<previous.yaml>]

Use that checkout's own interpreter, so the schema's dependencies import.
"""
import sys, yaml, importlib.util, os, pathlib

_src = os.environ.get("SKY_PLATFORM_SRC")
if not _src:
    sys.exit("set SKY_PLATFORM_SRC to the platform checkout first "
             "(see the docstring at the top of this file)")
PLATFORM = pathlib.Path(_src).expanduser()
_schema = PLATFORM / "app/services/ontology/schema.py"
if not _schema.is_file():
    sys.exit(f"no ontology schema at {_schema} — is SKY_PLATFORM_SRC right?")

spec = importlib.util.spec_from_file_location("ont_schema", _schema)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Ontology = mod.Ontology
# schema.py uses forward references; resolve them against the module namespace
# or pydantic refuses to instantiate ("is not fully defined").
try:
    Ontology.model_rebuild(_types_namespace=vars(mod))
except Exception as _e:
    print("WARN: could not rebuild Ontology model:", _e)

new = pathlib.Path(sys.argv[1])
raw = new.read_text()
print(f"file: {new.name}  ({len(raw)} bytes)")

if len(raw.encode()) > 256 * 1024:
    print("FAIL: exceeds the 256 KiB upload cap"); sys.exit(1)

parsed = yaml.safe_load(raw)
try:
    ont = Ontology(**parsed)
except Exception as e:
    print("FAIL: rejected by the platform's own Ontology schema:\n", e)
    sys.exit(1)

print(f"PASS schema: name={ont.name!r}  {len(ont.entity_types)} entities  "
      f"{len(ont.relation_types)} relations")

ents = [e.name for e in ont.entity_types]
rels = [r.name for r in ont.relation_types]
for label, seq in (("entity", ents), ("relation", rels)):
    dupes = {n for n in seq if seq.count(n) > 1}
    if dupes:
        print(f"FAIL: duplicate {label} names: {sorted(dupes)}"); sys.exit(1)

# every relation endpoint resolves (the server checks this too, belt and braces)
missing = [(r.name, r.source, r.target) for r in ont.relation_types
           if r.source not in set(ents) or r.target not in set(ents)]
if missing:
    print("FAIL: relation endpoints not defined as entity types:", missing); sys.exit(1)
print("PASS endpoints: every relation source/target resolves")

# leak scan — this file is going into a client-facing environment
# The words to look for are read from the same local, uncommitted list that
# `sky selftest` uses. Carrying one organisation's vocabulary in a committed
# file, inside the tool whose job is to keep that vocabulary out, is
# self-defeating — and it is the exact mistake this script used to make.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "core"))
try:
    from sky.selftest import load_words, WORDS_FILE
    BANNED = load_words()
except ImportError:
    BANNED, WORDS_FILE = [], "the word list"

if not BANNED:
    print(f"SKIP leak scan: no word list at {WORDS_FILE}")
else:
    import re
    hits = []
    for i, line in enumerate(raw.splitlines(), 1):
        for b in BANNED:
            # Word boundaries, not substrings: "usual" contains a three-letter
            # organisation name, and a check that cries wolf gets switched off.
            if re.search(rf"\b{re.escape(b)}\b", line, re.I):
                hits.append((i, b, line.strip()[:100]))
    if hits:
        print(f"FAIL leak scan: {len(hits)} local reference(s)")
        for i, b, t in hits[:15]:
            print(f"  line {i}: [{b}] {t}")
        sys.exit(1)
    print(f"PASS leak scan: none of {len(BANNED)} listed words appear")

# coverage vs the source ontology, if given
if len(sys.argv) > 2:
    src = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())
    s_ents = [e["name"] for e in src.get("entity_types", [])]
    s_rels = [r["name"] for r in src.get("relation_types", [])]
    lost_e, lost_r = set(s_ents) - set(ents), set(s_rels) - set(rels)
    extra_e, extra_r = set(ents) - set(s_ents), set(rels) - set(s_rels)
    print(f"\nsource: {len(s_ents)} entities / {len(s_rels)} relations")
    print(f"  dropped entities : {sorted(lost_e) or 'none'}")
    print(f"  dropped relations: {sorted(lost_r) or 'none'}")
    print(f"  added entities   : {sorted(extra_e) or 'none'}")
    print(f"  added relations  : {sorted(extra_r) or 'none'}")
    if lost_e or lost_r or extra_e or extra_r:
        print("FAIL: type coverage differs from source"); sys.exit(1)
    print("PASS coverage: identical type sets")

# descriptions must stay rich — they drive extraction quality in this format
thin = [e.name for e in ont.entity_types if len(e.description) < 40]
if thin:
    print(f"\nWARN: {len(thin)} entity description(s) under 40 chars: {thin}")
print("\nALL CHECKS PASSED — safe to upload")
