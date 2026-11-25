"""Check the sealed input boundary with a synthetic public frame on the native TA."""
import os
import struct

from camera.input import seal_frame
from run import BENCH, BEGIN, CAMERA_BEGIN, FINISH, PROVISION, SETUP, STEP, Model, Session, camera_clock
from setup_slot import prepare


def main():
    key = os.urandom(32)
    session = Session(True)
    try:
        session.call(PROVISION, key)
    finally:
        session.close()
    box, _ = prepare("A", [0] * 128, key, "lfw", camera=True)
    slot = box[1:17]
    pixels = struct.pack("<HH", 112, 112) + bytes(112 * 112 * 3)
    frame = seal_frame(pixels, slot, key)
    for cmd, data, valid in [
        (BEGIN, pixels[4:], False),
        (CAMERA_BEGIN, frame[:-1], False),
        (CAMERA_BEGIN, frame[:-1] + bytes([frame[-1] ^ 1]), False),
        (CAMERA_BEGIN, seal_frame(pixels, os.urandom(16), key), False),
        (CAMERA_BEGIN, seal_frame(pixels[4:], slot, key), False),
        (CAMERA_BEGIN, frame, True),
    ]:
        session = Session(True)
        try:
            session.call(SETUP, box)
            try:
                session.call(cmd, data)
            except RuntimeError:
                if valid:
                    raise
            else:
                if not valid:
                    raise AssertionError("Unexpected success on invalid camera input")
                _, start, end = camera_clock(session)
                assert start > 0 and end == 0
                model = Model(BENCH / "secure_sface/generated")
                for block in model.blocks:
                    session.call(STEP, block)
                _, stamped_start, stamped_end = camera_clock(session)
                assert stamped_start == start and stamped_end > start
                session.call(FINISH, out_len=1)
                assert camera_clock(session)[1:] == (stamped_start, stamped_end)
        finally:
            session.close()
    print("Camera-only slot accepted its authenticated frame and rejected five invalid inputs.")


if __name__ == "__main__":
    main()
