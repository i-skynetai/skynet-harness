"""SH-068 ledger-derived measurements used by the published manifest.

These are observed response characters, not tokens or proof that every character
entered a model prompt. The CLI places these in runtime-owned retrievals.
"""
from .ledger import COUNTING_METHOD, read


def build(path):
    items, findings = [], []
    indexed = False
    last = 0
    for row in read(path):
        if not str(row.get("tool", "")).startswith("mcp__"):
            continue
        sequence, characters = row.get("sequence"), row.get("response_chars")
        if (type(sequence) is not int or sequence <= last or
                type(characters) is not int or characters < 0 or
                row.get("counting_method") != COUNTING_METHOD or
                not isinstance(row.get("server"), str) or
                not isinstance(row.get("input_identity"), str) or
                type(row.get("failed")) is not bool):
            raise ValueError("malformed or out-of-order MCP measurement")
        last = sequence
        operation = row.get("operation")
        if operation in ("code.find", "code.outline", "code.related"):
            indexed = True
        if operation == "code.source" and not indexed:
            findings.append(f"sequence {sequence}: verification before any index call")
        if row["failed"]:
            findings.append(f"sequence {sequence}: {row['tool']} failed")
        items.append({"source": row["server"], "id": row["input_identity"],
                      "sequence": sequence, "characters": characters,
                      "failed": row["failed"]})
    return {"items": items, "measured_characters": sum(i["characters"] for i in items),
            "counting_method": COUNTING_METHOD, "findings": findings}
