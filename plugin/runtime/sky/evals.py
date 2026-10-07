"""Offline retrieval evaluation. Characters are measured; tokens are estimates.

No model or network is called. Baselines are reviewed fixtures, not fabricated
measurements. Reports count unique record ids but all returned response characters.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from . import decisions
from .kbserve import Server
from .kbstore import StoreError

TOKEN_METHOD = "estimate: Unicode response characters / 4"
COUNTING_METHOD = "Unicode code points of canonical JSON response"


def atomic(path, value):
    path = Path(path)
    if path.is_symlink():
        raise StoreError("evaluation refuses symbolic links")
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def validate(items):
    if not isinstance(items, list) or not items:
        raise StoreError("golden set must be a nonempty list")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {"id", "question", "expect_ids", "must_contain", "capability", "k"}:
            raise StoreError("golden item has unknown fields or is not an object")
        for key in ("id", "question"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise StoreError("golden item requires " + key)
        if item["id"] in seen:
            raise StoreError("duplicate golden id: " + item["id"])
        seen.add(item["id"])
        expected = item.get("expect_ids")
        if not isinstance(expected, list) or not expected or any(not isinstance(x, str) or not x for x in expected) or len(set(expected)) != len(expected):
            raise StoreError(item["id"] + ": expected ids must be nonempty and unique")
        if item.get("capability") not in {"search", "decisions"} or type(item.get("k")) is not int or not 1 <= item["k"] <= 100:
            raise StoreError(item["id"] + ": invalid capability or k")
        if "must_contain" in item and (not isinstance(item["must_contain"], str) or not item["must_contain"].strip()):
            raise StoreError(item["id"] + ": invalid must_contain")
    return items


def load_golden(directory):
    items = []
    for path in sorted(Path(directory).glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        items.extend(value if isinstance(value, list) else [value])
    return validate(items)


def score(item, response):
    if not isinstance(response, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in response):
        raise StoreError(item["id"] + ": invalid retrieval response")
    returned = {row["id"] for row in response}
    expected = set(item["expect_ids"])
    text = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    relevant = len(returned & expected)
    return {"id": item["id"], "expected": len(expected), "retrieved": len(returned),
            "relevant": relevant, "recall": relevant / len(expected),
            "precision": relevant / len(returned) if returned else None,
            "characters": len(text), "estimated_tokens": len(text) / 4,
            "missing_ids": sorted(expected - returned),
            "phrase_ok": item.get("must_contain", "").casefold() in text.casefold()}


def evaluate(store, items, *, retrieve=None):
    validate(items)
    server = Server(store)
    def local(item):
        if item["capability"] == "decisions":
            return decisions.find(store, item["question"], k=item["k"])
        return server.search(item["question"], k=item["k"])
    rows = [score(item, (retrieve or local)(item)) for item in items]
    relevant = sum(row["relevant"] for row in rows)
    retrieved = sum(row["retrieved"] for row in rows)
    chars = sum(row["characters"] for row in rows)
    return {"schema_version": 1, "items": rows, "overall": {
        "recall": relevant / sum(row["expected"] for row in rows),
        "precision": relevant / retrieved if retrieved else None,
        "characters": chars, "estimated_tokens": chars / 4},
        "counting_method": COUNTING_METHOD, "token_method": TOKEN_METHOD}


def compare(report, baseline, *, recall_tolerance=0, precision_tolerance=0, characters_tolerance=0):
    for value in (recall_tolerance, precision_tolerance, characters_tolerance):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise StoreError("baseline tolerance must be finite and nonnegative")
    if not isinstance(baseline, dict) or baseline.get("schema_version") != 1 or not isinstance(baseline.get("items"), list):
        raise StoreError("invalid evaluation baseline")
    indexed = {row["id"]: row for row in baseline["items"]}
    if len(indexed) != len(baseline["items"]):
        raise StoreError("duplicate baseline item")
    failures = []
    for row in [*report["items"], {"id": "overall", **report["overall"]}]:
        previous = baseline.get("overall") if row["id"] == "overall" else indexed.get(row["id"])
        if previous is None:
            failures.append(row["id"] + ": absent from baseline")
            continue
        for key, tolerance in (("recall", recall_tolerance), ("precision", precision_tolerance), ("characters", characters_tolerance)):
            actual, target = row[key], previous.get(key)
            if target is None or not isinstance(target, (int, float)) or isinstance(target, bool) or not math.isfinite(target):
                raise StoreError(row["id"] + ": invalid baseline " + key)
            if actual is None or (actual > target + tolerance if key == "characters" else actual < target - tolerance):
                failures.append(row["id"] + ": regression in " + key)
        if row.get("phrase_ok") is False:
            failures.append(row["id"] + ": required phrase missing")
        if row.get("retrieved") == 0:
            failures.append(row["id"] + ": no hits")
    for missing in sorted(set(indexed) - {row["id"] for row in report["items"]}):
        failures.append(missing + ": missing golden item")
    return failures


def update_baseline(path, report, *, env=None):
    if "SKY_LAUNCHED" in (os.environ if env is None else env):
        raise StoreError("baseline updates require a person; refused under SKY_LAUNCHED")
    if any(not row["phrase_ok"] or row["precision"] is None or row["recall"] < 1 for row in report["items"]):
        raise StoreError("baseline update refused: expected ids or required phrases missing")
    atomic(path, report)


def run(store, *, golden, baseline, run, update=False, **tolerances):
    report = evaluate(store, load_golden(golden))
    if update:
        update_baseline(baseline, report)
    failures = compare(report, json.loads(Path(baseline).read_text(encoding="utf-8")), **tolerances)
    report["failures"] = failures
    report["passed"] = not failures
    atomic(run.directory / "eval-report.json", report)
    table = "item | recall | precision | characters | estimated tokens\n"
    for row in report["items"]:
        precision = "undefined" if row["precision"] is None else f"{row['precision']:.3f}"
        table += f"{row['id']} | {row['recall']:.3f} | {precision} | {row['characters']} | {row['estimated_tokens']:.2f}\n"
    table += TOKEN_METHOD + "\n" + ("PASS" if not failures else "FAIL: " + "; ".join(failures)) + "\n"
    # Use atomic JSON report as the machine record; text is a readable companion.
    (run.directory / "eval-report.txt").write_text(table, encoding="utf-8", newline="\n")
    return report
