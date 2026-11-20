"""Export the pinned OpenCV SFace graph for the small secure CPU runtime.

Weights remain public. Every streamed block has a SHA-256 digest compiled into
the TA; feature tensors never need to be placed in normal-world shared memory.
Run this on the build workstation, not in the trusted application.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper, shape_inference

MODEL_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
BLOCK_LIMIT = 512 * 1024
KINDS = {"Sub": 0, "Mul": 1, "BatchNormalization": 2, "PRelu": 3, "Conv": 4, "Gemm": 5}


def export(model_path, destination):
    raw = Path(model_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError("Unsupported checkpoint: expected the pinned OpenCV SFace 2021dec FP32 model")
    model = shape_inference.infer_shapes(onnx.load_model_from_string(raw))
    constants = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    shapes = {v.name: [d.dim_value for d in v.type.tensor_type.shape.dim]
              for v in list(model.graph.input) + list(model.graph.value_info) + list(model.graph.output)}
    previous = model.graph.input[0].name
    steps, blocks = [], []
    largest = max(int(np.prod(shape)) for name, shape in shapes.items() if name not in constants)

    def append(kind, dims, begin, count, kernel, stride, pad, groups, last, arrays, node):
        payload = b"".join(np.asarray(a, dtype="<f4").tobytes() for a in arrays)
        if not payload or len(payload) > BLOCK_LIMIT:
            raise ValueError(f"Invalid block size for {node}")
        index = len(steps)
        steps.append(dict(index=index, node=node, kind=KINDS[kind], dims=dims,
                          begin=begin, count=count, kernel=kernel, stride=stride,
                          pad=pad, groups=groups, last=last, offset=sum(map(len, blocks)),
                          size=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
        blocks.append(payload)

    for node in model.graph.node:
        if node.input[0] != previous:
            raise ValueError("Runtime supports only the pinned sequential graph")
        previous = node.output[0]
        attr = {a.name: helper.get_attribute_value(a) for a in node.attribute}
        shape = shapes[node.input[0]]
        cin, h, w = (shape[1], 1, 1) if len(shape) == 2 else shape[1:]
        outshape = shapes[node.output[0]]
        cout, oh, ow = (outshape[1], 1, 1) if len(outshape) == 2 else outshape[1:]
        dims = [cin, h, w, cout, oh, ow]
        if node.op_type in ("Dropout", "Flatten"):
            continue  # inference identity / contiguous NCHW reshape, pinned graph only
        if node.op_type in ("Sub", "Mul", "PRelu"):
            arrays = [constants[node.input[1]]]
        elif node.op_type == "BatchNormalization":
            gamma, beta, mean, var = [constants[name] for name in node.input[1:]]
            invstd = np.float32(1) / np.sqrt(var + np.float32(attr.get("epsilon", 1e-5)))
            arrays = [gamma, beta, mean, invstd]
        elif node.op_type in ("Conv", "Gemm"):
            weight = constants[node.input[1]]
            bias = constants[node.input[2]] if len(node.input) > 2 else np.zeros(cout, dtype=np.float32)
            if node.op_type == "Conv":
                kh, kw = attr["kernel_shape"]
                sh, sw = attr["strides"]
                pads = attr["pads"]
                if kh != kw or sh != sw or len(set(pads)) != 1 or attr["dilations"] != [1, 1]:
                    raise ValueError("Unsupported convolution")
                kernel, stride, pad, groups = kh, sh, pads[0], attr["group"]
            else:
                if attr.get("transA", 0) or attr.get("transB", 0) != 1 or attr.get("alpha", 1) != 1 or attr.get("beta", 1) != 1:
                    raise ValueError("Unsupported Gemm")
                kernel, stride, pad, groups = 1, 1, 0, 1
            row_floats = int(np.prod(weight.shape[1:]))
            tile = max(1, BLOCK_LIMIT // ((row_floats + 1) * 4))
            for begin in range(0, cout, tile):
                count = min(tile, cout - begin)
                append(node.op_type, dims, begin, count, kernel, stride, pad, groups,
                       int(begin + count == cout), [weight[begin:begin + count], bias[begin:begin + count]], node.name)
            continue
        else:
            raise ValueError(f"Unsupported operator {node.op_type}")
        append(node.op_type, dims, 0, cout, 1, 1, 0, 1, 1, arrays, node.name)

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    blob = b"".join(blocks)
    manifest = {"model_sha256": digest, "blob_sha256": hashlib.sha256(blob).hexdigest(),
                "blob_bytes": len(blob), "activation_buffer_floats": largest,
                "activation_buffers": 2, "max_block_bytes": max(map(len, blocks)),
                "secure_working_bytes": largest * 8 + max(map(len, blocks)),
                "input": "112x112 BGR uint8, packed HWC", "output": "128 masked uint64",
                "steps": steps}
    (destination / "weights.bin").write_bytes(blob)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    header = ["/* Generated from pinned ONNX. Do not edit. */", "#ifndef SF_MODEL_H", "#define SF_MODEL_H",
              '#include "runtime.h"', f"#define SF_BUFFER_FLOATS {largest}u",
              f"#define SF_BLOCK_BYTES {max(map(len, blocks))}u", f"#define SF_BLOB_BYTES {len(blob)}u",
              f"#define SF_STEP_COUNT {len(steps)}u", f'#define SF_MODEL_SHA256 "{digest}"',
              "static const unsigned char sf_model_digest[32] = {" + ",".join(str(x) for x in bytes.fromhex(digest)) + "};",
              "static const struct sf_step sf_steps[SF_STEP_COUNT] = {"]
    for step in steps:
        numbers = [step["kind"], *step["dims"], step["begin"], step["count"], step["kernel"],
                   step["stride"], step["pad"], step["groups"], step["last"], step["offset"], step["size"]]
        sha = ",".join(str(x) for x in bytes.fromhex(step["sha256"]))
        header.append("  {" + ",".join(map(str, numbers)) + ",{" + sha + "}},")
    header += ["};", "#endif"]
    (destination / "model.h").write_text("\n".join(header) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "steps"}, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args()
    export(args.model, args.output)
