"""Obscura fixed-point encoding and replaceable masking backends."""
import ctypes
import math
import secrets
import struct

DIMENSION = 128
SCALE = 1 << 8
MODULUS = 1 << 64


def encode(embedding):
    values = [float(x) for x in embedding]
    if len(values) != DIMENSION or not all(math.isfinite(x) for x in values):
        raise ValueError("Expected exactly 128 finite embedding values")
    scaled = [x * SCALE for x in values]
    if not all(math.isfinite(x) for x in scaled):
        raise ValueError("Embedding exceeds fixed-point range")
    signed = [int(x) for x in scaled]  # truncate toward zero, as in common/helper.py
    if any(x < -(1 << 63) or x >= (1 << 63) for x in signed):
        raise ValueError("Embedding exceeds signed 64-bit fixed-point range")
    return [x % MODULUS for x in signed]


class SoftwareMasker:
    """Normal-world baseline. No hardware isolation or guaranteed memory erasure."""
    name = "software_no_tee"

    def mask(self, encoded):
        if len(encoded) != DIMENSION:
            raise ValueError("Expected 128 encoded values")
        # Fresh independent 64-bit pad for every coordinate and every invocation.
        pads = struct.unpack("<128Q", secrets.token_bytes(DIMENSION * 8))
        return [(x + r) % MODULUS for x, r in zip(encoded, pads)]

    def close(self):
        pass


class OpteeMasker:
    """Mask inside a TA; the input embedding still originates in normal-world Python."""
    name = "optee_mask_only"

    def __init__(self, library):
        try:
            self.lib = ctypes.CDLL(str(library))
        except OSError as error:
            raise RuntimeError(
                f"Cannot load OP-TEE bridge {library}. Build/install the TA and libteec "
                "using README.md, then run on the Jetson. No software fallback."
            ) from error
        self.lib.obscura_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.lib.obscura_open.restype = ctypes.c_uint32
        self.lib.obscura_mask.argtypes = [ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_uint64),
                                        ctypes.POINTER(ctypes.c_uint64)]
        self.lib.obscura_mask.restype = ctypes.c_uint32
        self.lib.obscura_close.argtypes = [ctypes.c_void_p]
        self.lib.obscura_close.restype = None
        self.handle = ctypes.c_void_p()
        result = self.lib.obscura_open(ctypes.byref(self.handle))
        if result:
            raise RuntimeError(f"OP-TEE open failed: 0x{result:08x}; no software fallback")

    def mask(self, encoded):
        if not self.handle:
            raise RuntimeError("OP-TEE session is closed")
        if len(encoded) != DIMENSION:
            raise ValueError("Expected 128 encoded values")
        array = ctypes.c_uint64 * DIMENSION
        source, output = array(*encoded), array()
        try:
            result = self.lib.obscura_mask(self.handle, source, output)
            if result:
                raise RuntimeError(f"OP-TEE masking failed: 0x{result:08x}")
            return list(output)
        finally:
            ctypes.memset(source, 0, ctypes.sizeof(source))

    def close(self):
        if self.handle:
            self.lib.obscura_close(self.handle)
            self.handle = ctypes.c_void_p()
