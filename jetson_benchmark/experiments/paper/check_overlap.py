"""Compare each placement with the original Obscura transcript on public fixtures."""

import contextlib
import hashlib
import os
import pickle
import struct

from material import ROOT, VEC, seal_group
from compare import (
    DECIDE,
    GROUP_NEXT,
    GROUP_SETUP,
    MASK_STORED,
    PROVISION,
    Server,
    Session,
    seal_reply,
    verify_masked_probe,
)
from common.constants import THRESHOLD_TAU_SQUARE

# From the original driver and its 1,000 public data/64 pickle pairs at 60ae87d6.
# In row order: masked Y, drone's xy and xx shares, WD's xy and xx shares, bit.
ORIGINAL_DIGEST = "541d918cdb6f88dc39c2bed2b6d25fb078ada5bcb0c1ffcb1260641f1effe076"


def load_party(role, number):
    party = Server(role)
    with (ROOT / "data/64" / f"offline.pkl{role}-{number}").open("rb") as f:
        party.receiveCircuit(pickle.load(f))
    return party


def main():
    key = os.urandom(32)
    transcript = hashlib.sha256()
    with contextlib.closing(Session(True)) as ta:
        ta.call(PROVISION, key)
    for first in range(0, 1000, 100):
        cases = []
        for number in range(first, first + 100):
            drone, wd = load_party(0, number), load_party(1, number)
            xy, xx, masked = drone.getFirstRoundMessageDrone()
            local = [xy, xx]
            peer = wd.getFirstRoundMessage(masked)
            probe = drone.circuit["non_vec_v"]
            bit = drone.reconstructDecision(local, peer, probe, THRESHOLD_TAU_SQUARE)
            transcript.update(struct.pack("<128Q4QB", *masked, *local, *peer, bit))
            cases.append((drone, wd, masked, local, peer, bit))
        # Use identical, public fixture masks across placements only for this
        # deterministic equivalence test. Every test slot and its MAC keys are fresh.
        for mode in ("P", "R"):
            slots, records = [], []
            for drone, *_ in cases:
                slot = os.urandom(16)
                auth = os.urandom(32 if mode == "P" else 88)
                slots.append((slot, auth))
                records.append(slot + VEC.pack(*drone.circuit["in_v_drone"]) + auth)
            with contextlib.closing(Session(True)) as ta:
                ta.call(GROUP_SETUP, seal_group(key, mode, "lfw", records))
                for case, (slot, auth) in zip(cases, slots):
                    (
                        drone,
                        wd,
                        expected_y,
                        expected_local,
                        expected_peer,
                        expected_bit,
                    ) = case
                    probe = drone.circuit["non_vec_v"]
                    ta.call(GROUP_NEXT)
                    packet = ta.call(MASK_STORED, struct.pack("<128q", *probe), 1072)
                    masked = verify_masked_probe(packet, slot, auth[:32], "lfw")
                    local = drone.getFirstRoundMessage(masked)
                    peer = wd.getFirstRoundMessage(masked)
                    assert list(masked) == expected_y
                    assert local == expected_local and peer == expected_peer
                    if mode == "R":
                        reply = seal_reply(peer, slot, packet[1040:], auth)
                        bit = ta.call(DECIDE, struct.pack("<2Q", *local) + reply, 1)[0]
                    else:
                        bit = drone.reconstructDecision(
                            local, peer, probe, THRESHOLD_TAU_SQUARE
                        )
                    assert bit == expected_bit
    assert transcript.hexdigest() == ORIGINAL_DIGEST, (
        "Original fixture transcript changed"
    )
    print("1,000 original transcripts matched both TEE placements (native TA test).")


if __name__ == "__main__":
    main()
