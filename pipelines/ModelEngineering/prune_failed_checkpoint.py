"""
Prune failed rows from a batch_evaluator checkpoint so a rerun retries them.

A row is "failed" if any of:
  - scores is None  (generation died -- empty body, parse error, etc.)
  - generator_error is set  (defensive belt+suspenders)
  - all three rubric scores are 0  (judge call itself errored)

Keeps the successful rows so they don't get re-scored (which would burn budget
and could shift the number by 1-2pp due to judge non-determinism).

CLI:
  python prune_failed_checkpoint.py runs/_checkpoint_<label>.jsonl
"""
import json
import sys
from pathlib import Path


def is_bad(row: dict) -> bool:
    if row.get("scores") is None:
        return True
    if row.get("generator_error"):
        return True
    s = row["scores"]
    if s.get("accuracy_score") == 0 and s.get("pedagogy_score") == 0 and s.get("formatting_score") == 0:
        return True
    return False


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: checkpoint not found: {path}", file=sys.stderr)
        return 2

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    keep = [r for r in rows if not is_bad(r)]
    drop = [r for r in rows if is_bad(r)]

    if not drop:
        print(f"Nothing to prune; all {len(rows)} rows look good.")
        return 0

    backup = path.with_suffix(path.suffix + ".pre-prune.bak")
    path.replace(backup)
    with path.open("w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, default=str) + "\n")

    print(f"Backed up original to: {backup.name}")
    print(f"Kept {len(keep)} successful rows; dropped {len(drop)} failures (will retry on rerun).")
    print(f"Dropped (source/id) preview: {[(r['source'], r['id']) for r in drop[:10]]}{' ...' if len(drop) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
