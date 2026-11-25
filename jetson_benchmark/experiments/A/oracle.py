"""Independent plaintext CondEval decision with Obscura's configured threshold."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thresholds import DEN, NUMERATORS


def encode(values):
    if len(values) != 128:
        raise ValueError("Expected a 128-coordinate SFace vector")
    q = [int(v * 256) for v in values]
    if any(abs(v) > 32767 for v in q):
        raise ValueError("Input exceeds the experiment circuit bound")
    return q


def terms(x, y):
    return (
        sum(a * b for a, b in zip(x, y)),
        sum(a * a for a in x),
        sum(b * b for b in y),
    )


def decision(x, y, profile="lfw"):
    d, xx, yy = terms(x, y)
    return int(d >= 0 and DEN * d * d >= NUMERATORS[profile] * xx * yy)


if __name__ == "__main__":
    data = ROOT / "data"
    bank = json.loads((data / "new_emb1.txt").read_text())
    correct = disagreements = total = 0
    for line in (data / "veri_test1.txt").read_text().splitlines()[:1000]:
        label, a, b, *_ = line.split()
        x, y = encode(bank[a]), encode(bank[b])
        d, xx, yy = terms(x, y)
        upstream = d >= 0 and d * d * (1 / 0.11368578) - xx * yy >= 0
        answer = decision(x, y)
        disagreements += upstream != answer
        correct += answer == int(label)
        total += 1
    print(
        json.dumps(
            {
                "stored_pairs": total,
                "correct": correct,
                "upstream_disagreements": disagreements,
            }
        )
    )
