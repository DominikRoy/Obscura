"""Dealer-generated masked comparisons using the repository DCF tree algorithm."""

import hashlib
import importlib.util
import secrets
from pathlib import Path

# Load a private module instance. The historical scripts in the same process
# must keep their original sampling behavior. DCF.keyGen calls sampleBits once
# to choose its two root seeds; replace that hook in this instance only.
source = Path(__file__).resolve().parents[3] / "libfss/fss.py"
spec = importlib.util.spec_from_file_location("experiment_dcf", source)
tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tree)
tree.sampleBits = lambda unused_seed, bits: secrets.randbits(bits)


class ComparisonTree(tree.DCF):
    def prg(self, seed):
        bits = 4 * self.sec_para + 2
        stream = hashlib.shake_256(
            b"obscura-dcf-tree-v1" + seed.to_bytes(16, "big")
        ).digest((bits + 7) // 8)
        return int.from_bytes(stream, "big") % (1 << bits)

    def convertG(self, seed):
        stream = hashlib.shake_256(
            b"obscura-dcf-value-v1" + seed.to_bytes(16, "big")
        ).digest((self.ring_len + 7) // 8)
        return tree.GroupElement(int.from_bytes(stream, "big"), self.ring_len)


def keys(threshold, bits, output_bits):
    dcf = ComparisonTree(ring_len=output_bits)
    pair = dcf.keyGen(
        None, tree.GroupElement(threshold, bits), tree.GroupElement(1, output_bits)
    )
    return [bytes(k.packData()).hex() for k in pair]


def evaluate(role, public, bits, output_bits, key):
    key = tree.DCFKey.unpack(bytes.fromhex(key), output_bits)
    return (
        ComparisonTree(ring_len=output_bits)
        .eval(role, tree.GroupElement(public, bits), key)
        .getValue()
    )
