"""Negative controls for the skeptic: comments known to be wrong, mixed into its batch.

A skeptic that confirms everything looks the same as one facing only true
comments. Controls tell them apart. For cross-reference comments, a control
claims that two mentions of a fact contradict each other when the paper
states the same value both times, which is exactly the false alarm the
skeptic exists to catch. The skeptic is not told which comments are
controls; its refutation rate on them is its measured accuracy.
"""

import json
import random
from pathlib import Path

from jaanch.check import read_jsonl
from jaanch.xref import FACTS, FOLDER, GROUP_TAG, GROUPS, _value_key

VERIFY = "verify"


def _agreeing_pairs(facts: list[dict]) -> list[tuple[dict, dict]]:
    """Two mentions of one key with the same value, in different places."""
    by_key: dict[str, list[dict]] = {}
    for fact in facts:
        by_key.setdefault(fact["key"], []).append(fact)
    pairs = []
    for members in by_key.values():
        for i, a in enumerate(members):
            same = [
                b
                for b in members[i + 1 :]
                if _value_key(b["value"]) == _value_key(a["value"]) and b["quote"] != a["quote"]
            ]
            if same:
                pairs.append((a, same[0]))
                break
    return pairs


def _cross_subject_pairs(facts: list[dict]) -> list[tuple[dict, dict]]:
    """The same aspect of two different subjects with different values: study 1's N and study 2's N.

    Presenting them as one fact stated two ways is the commonest false alarm.
    """
    by_aspect: dict[tuple, list[dict]] = {}
    for fact in facts:
        parts = fact["key"].split(":")
        if len(parts) >= 3:
            by_aspect.setdefault((parts[0], *parts[2:]), []).append(fact)
    pairs = []
    for members in by_aspect.values():
        for i, a in enumerate(members):
            other = [
                b
                for b in members[i + 1 :]
                if b["key"] != a["key"] and _value_key(b["value"]) != _value_key(a["value"])
            ]
            if other:
                pairs.append((a, other[0]))
                break
    return pairs


def _dismissed_pairs(run_dir: Path, facts: list[dict], name: str) -> list[tuple[dict, dict]]:
    """Two mentions from a group the finder judged compatible (paraphrase, rounding) and left uncommented."""
    groups_path = run_dir / FOLDER / GROUPS
    if not groups_path.exists():
        return []
    commented = set()
    for comment in read_jsonl(run_dir / "candidates" / f"{name}.jsonl"):
        match = GROUP_TAG.match(comment.get("message", ""))
        if match:
            commented.add(match.group(1))
    by_id = {fact["id"]: fact for fact in facts}
    pairs = []
    for group in read_jsonl(groups_path):
        if group["key"] in commented or len(group["values"]) < 2:
            continue
        a, b = by_id.get(group["values"][0]["facts"][0]), by_id.get(group["values"][1]["facts"][0])
        if a and b:
            pairs.append((a, b))
    return pairs


def _decoy(number: int, prefix: str, a: dict, b: dict) -> dict:
    subject = a["key"].split(":", 1)[1].replace(":", " ").replace("_", " ")
    return {
        "id": f"{prefix}_{number:03d}",
        "goal": "consistency",
        "title": f"Inconsistent description of {subject}",
        "quote": b["quote"],
        "location": b["location"],
        "message": (
            f"[group: {a['key']}] {b['location']} describes the {subject} differently from {a['location']}, "
            f'which says "{a["quote"]}". Both cannot hold, and the claims that rest on the {subject} '
            "are affected."
        ),
        "suggestion": "Reconcile the two descriptions.",
        "severity": "major",
        "kind": "substance/contradiction",
        "fix_effort": "edit_in_place",
    }


KINDS = ("same_value", "other_subject", "judged_compatible")


def make_controls(run_dir: Path, name: str, share: float = 0.5, seed: int = 0) -> dict:
    """Write verify/batch_<name>.jsonl: candidates plus decoys of each kind, shuffled; record decoys apart.

    same_value: two mentions that state the same value. other_subject: the
    same aspect of two different subjects. judged_compatible: two mentions
    from a group the finder itself dismissed. The last two are harder and
    their labels noisier: a skeptic's refusal to refute one needs reading.
    """
    candidates = read_jsonl(run_dir / "candidates" / f"{name}.jsonl")
    facts = read_jsonl(run_dir / FOLDER / FACTS) if (run_dir / FOLDER / FACTS).exists() else []
    rng = random.Random(seed)
    pools = {
        "same_value": _agreeing_pairs(facts),
        "other_subject": _cross_subject_pairs(facts),
        "judged_compatible": _dismissed_pairs(run_dir, facts, name),
    }
    for pool in pools.values():
        rng.shuffle(pool)
    per_kind = max(1, round(len(candidates) * share / len(KINDS))) if candidates else 0
    prefix = candidates[0]["id"].rsplit("_", 1)[0] if candidates else name
    used = {int(c["id"].rsplit("_", 1)[1]) for c in candidates if c["id"].rsplit("_", 1)[1].isdigit()}
    free = iter(n for n in range(1, 1000) if n not in used)
    decoys, kinds = [], {}
    for kind in KINDS:
        for a, b in pools[kind][:per_kind]:
            decoy = _decoy(next(free), prefix, a, b)
            decoys.append(decoy)
            kinds[decoy["id"]] = kind
    batch = candidates + decoys
    rng.shuffle(batch)
    folder = run_dir / VERIFY
    folder.mkdir(exist_ok=True)
    (folder / f"batch_{name}.jsonl").write_text("".join(json.dumps(c) + "\n" for c in batch))
    # Kept outside the batch, where the skeptic is not pointed.
    (folder / f"controls_{name}.json").write_text(json.dumps(kinds))
    return {
        "candidates": len(candidates),
        "controls": {kind: sum(v == kind for v in kinds.values()) for kind in KINDS},
        "available": {kind: len(pool) for kind, pool in pools.items()},
    }


def score_controls(run_dir: Path, name: str) -> dict:
    """The skeptic's verdicts on each kind of control and on real candidates, kept apart."""
    folder = run_dir / VERIFY
    kinds = json.loads((folder / f"controls_{name}.json").read_text())
    if isinstance(kinds, list):
        kinds = {control: "same_value" for control in kinds}
    verdicts = {v["id"]: v["verdict"] for v in read_jsonl(folder / f"verdicts_{name}.jsonl")}
    by_kind = {}
    for kind in KINDS:
        ids = [i for i, k in kinds.items() if k == kind]
        if ids:
            by_kind[kind] = {
                "controls": len(ids),
                "refuted": sum(verdicts.get(i) == "refuted" for i in ids),
                "unjudged": sum(i not in verdicts for i in ids),
            }
    real = [v for i, v in verdicts.items() if i not in kinds]
    return {
        "controls": by_kind,
        "real": {verdict: real.count(verdict) for verdict in ("confirmed", "plausible", "refuted")},
    }
