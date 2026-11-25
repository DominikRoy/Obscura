"""Trusted workstation only: emulate a sensor delivering full BGR frames."""

import hashlib
import hmac
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from setup_slot import MODEL_DIGEST

FRAME_DOMAIN = b"obscura-camera-bgr-v1".ljust(
    len(b"obscura-v1/SFace128/trunc256/tau2=11368578e-8/"), b"\0"
)


def sensor_pixels(path, max_side=None):
    import cv2

    if max_side is not None and max_side < 1:
        raise ValueError("Sensor maximum side must be positive")
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode {path}")
    h, w = image.shape[:2]
    if max_side and max(h, w) > max_side:
        scale = max_side / max(h, w)
        image = cv2.resize(
            image,
            (max(1, round(w * scale)), max(1, round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    h, w = image.shape[:2]
    if max(w, h) > 1024 or w * h > 640 * 480:
        raise ValueError(
            "Frame exceeds sensor envelope. Choose --sensor-max-side 640 or a smaller resolution."
        )
    return struct.pack("<HH", w, h) + image.tobytes()


def seal_frame(pixels, slot, key):
    header = b"F" + slot
    nonce = os.urandom(12)
    return (
        header
        + nonce
        + AESGCM(key).encrypt(nonce, pixels, FRAME_DOMAIN + MODEL_DIGEST + header)
    )


def frame_id(pixels, key):
    return hmac.digest(
        key, b"obscura-replay-frame-id/" + hashlib.sha256(pixels).digest(), "sha256"
    ).hex()
