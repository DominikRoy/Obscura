"""Native regression for one-use grouped setup and authenticated reconstruction."""

import contextlib
import hmac
import os
import struct

from material import make_row, seal_group, VEC
from run import Session, PROVISION, DECIDE
from compare import GROUP_SETUP, GROUP_NEXT, MASK_STORED, server


def rejected(call, *args):
    try:
        call(*args)
    except RuntimeError:
        return
    raise AssertionError("Unexpected success")


def main():
    key = os.urandom(32)
    with contextlib.closing(Session(True)) as session:
        session.call(PROVISION, key)
    x, y = [1] * 128, [2] * 128
    for mode in ("P", "R"):
        for fault in (
            "none",
            "corrupt setup",
            "advance early",
            "duplicate mask",
            "corrupt reply",
        ):
            if mode == "P" and fault == "corrupt reply":
                continue
            pairs = [make_row(x, mode) for _ in range(2)]
            box = seal_group(key, mode, "lfw", [secret for _, secret in pairs])
            with contextlib.closing(Session(True)) as ta:
                if fault == "corrupt setup":
                    rejected(ta.call, GROUP_SETUP, box[:-1] + bytes([box[-1] ^ 1]))
                    continue
                ta.call(GROUP_SETUP, box)
                for (slot, mx, s0, s1, corr, _, auth), _ in pairs:
                    ta.call(GROUP_NEXT)
                    if fault == "advance early":
                        rejected(ta.call, GROUP_NEXT)
                        break
                    packet = ta.call(MASK_STORED, struct.pack("<128q", *y), 1072)
                    assert packet[:16] == slot
                    assert hmac.compare_digest(
                        hmac.digest(auth[:32], packet[:1040], "sha256"), packet[1040:]
                    )
                    if fault == "duplicate mask":
                        rejected(ta.call, MASK_STORED, struct.pack("<128q", *y), 1072)
                        break
                    if mode == "R":
                        masked = VEC.unpack_from(packet, 16)
                        local, other = [
                            s.getFirstRoundMessage(masked)
                            for s in (server(0, s0, mx), server(1, s1, mx, corr))
                        ]
                        ct = bytes(
                            a ^ b
                            for a, b in zip(struct.pack("<2Q", *other), auth[32:48])
                        )
                        reply = (
                            struct.pack("<2Q", *local)
                            + ct
                            + hmac.digest(
                                auth[56:], slot + packet[1040:] + ct, "sha256"
                            )
                        )
                        if fault == "corrupt reply":
                            rejected(
                                ta.call, DECIDE, reply[:-1] + bytes([reply[-1] ^ 1]), 1
                            )
                            break
                        assert ta.call(DECIDE, reply, 1) == bytes([1])
                else:
                    rejected(ta.call, GROUP_NEXT)
            with contextlib.closing(Session(True)) as new:
                rejected(new.call, GROUP_SETUP, box)
    print(
        "Grouped setup, ordered consumption, corrupt inputs, decision and replay checks passed."
    )


if __name__ == "__main__":
    main()
