"""Normalize AutoSprite glTF animation channels for Panda3D's Assimp bridge.

The source clips legitimately store animated bones at (for example) 33 keys
while constant translation/scale channels only store two keys.  Panda 1.10's
Assimp converter asserts when a single animation contains channels with
different frame counts.  This script expands the shorter channels onto the
longest timeline in each clip without changing the authored motion.
"""

from __future__ import annotations

import json
import math
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "third_party" / "autosprite_free" / "processed"
OUTPUT_ROOT = ROOT / "third_party" / "autosprite_free" / "resampled"

COMPONENT_FORMAT = {5126: "f"}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _decode_accessor(document: dict, binary: bytes, accessor_index: int) -> list[tuple[float, ...]]:
    accessor = document["accessors"][accessor_index]
    component_type = accessor["componentType"]
    if component_type not in COMPONENT_FORMAT:
        raise ValueError(f"Animation accessor uses unsupported component type {component_type}")
    width = TYPE_SIZE[accessor["type"]]
    view = document["bufferViews"][accessor["bufferView"]]
    item_size = 4 * width
    stride = int(view.get("byteStride", item_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    fmt = "<" + COMPONENT_FORMAT[component_type] * width
    return [struct.unpack_from(fmt, binary, start + row * stride) for row in range(accessor["count"])]


def _lerp(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, ...]:
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _normalize_quat(q: tuple[float, ...]) -> tuple[float, ...]:
    length = math.sqrt(sum(component * component for component in q))
    if length <= 1e-10:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(component / length for component in q)


def _slerp(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, ...]:
    qa = _normalize_quat(a)
    qb = _normalize_quat(b)
    dot = sum(x * y for x, y in zip(qa, qb))
    if dot < 0.0:
        qb = tuple(-component for component in qb)
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return _normalize_quat(_lerp(qa, qb, t))
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    a_weight = math.sin(theta_0 - theta) / sin_theta_0
    b_weight = math.sin(theta) / sin_theta_0
    return tuple(a_weight * x + b_weight * y for x, y in zip(qa, qb))


def _sample(
    key_times: list[float],
    values: list[tuple[float, ...]],
    time_value: float,
    interpolation: str,
    rotation: bool,
) -> tuple[float, ...]:
    if time_value <= key_times[0]:
        return values[0]
    if time_value >= key_times[-1]:
        return values[-1]
    right = 1
    while right < len(key_times) and key_times[right] < time_value:
        right += 1
    left = right - 1
    if interpolation == "STEP":
        return values[left]
    start = key_times[left]
    end = key_times[right]
    alpha = 0.0 if end <= start else (time_value - start) / (end - start)
    if rotation:
        return _slerp(values[left], values[right], alpha)
    return _lerp(values[left], values[right], alpha)


def _append_accessor(
    document: dict,
    binary: bytearray,
    values: list[tuple[float, ...]],
    accessor_type: str,
) -> int:
    while len(binary) % 4:
        binary.append(0)
    byte_offset = len(binary)
    width = TYPE_SIZE[accessor_type]
    fmt = "<" + "f" * width
    for value in values:
        binary.extend(struct.pack(fmt, *value))
    byte_length = len(binary) - byte_offset
    document["bufferViews"].append(
        {"buffer": 0, "byteOffset": byte_offset, "byteLength": byte_length}
    )
    view_index = len(document["bufferViews"]) - 1
    document["accessors"].append(
        {
            "bufferView": view_index,
            "componentType": 5126,
            "count": len(values),
            "type": accessor_type,
        }
    )
    return len(document["accessors"]) - 1


def resample_character(name: str) -> Path:
    source_dir = SOURCE_ROOT / name
    source_gltf = source_dir / f"{name}.gltf"
    document = json.loads(source_gltf.read_text(encoding="utf-8"))
    source_bin = source_dir / document["buffers"][0]["uri"]
    original_binary = source_bin.read_bytes()
    binary = bytearray(original_binary)

    for animation in document.get("animations", []):
        samplers = animation["samplers"]
        input_counts = [document["accessors"][sampler["input"]]["count"] for sampler in samplers]
        target_count = max(input_counts)
        if min(input_counts) == target_count:
            continue

        master_sampler = samplers[input_counts.index(target_count)]
        master_input = master_sampler["input"]
        master_times = [row[0] for row in _decode_accessor(document, original_binary, master_input)]

        sampler_paths: dict[int, str] = {}
        for channel in animation["channels"]:
            sampler_paths[channel["sampler"]] = channel["target"]["path"]

        for sampler_index, sampler in enumerate(samplers):
            input_accessor = document["accessors"][sampler["input"]]
            if input_accessor["count"] == target_count:
                continue
            interpolation = sampler.get("interpolation", "LINEAR")
            if interpolation not in {"LINEAR", "STEP"}:
                raise ValueError(
                    f"{name}/{animation.get('name')}: unsupported interpolation {interpolation}"
                )
            key_times = [row[0] for row in _decode_accessor(document, original_binary, sampler["input"])]
            output_accessor = document["accessors"][sampler["output"]]
            values = _decode_accessor(document, original_binary, sampler["output"])
            path = sampler_paths.get(sampler_index, "")
            expanded = [
                _sample(key_times, values, t, interpolation, path == "rotation")
                for t in master_times
            ]
            sampler["input"] = master_input
            sampler["output"] = _append_accessor(document, binary, expanded, output_accessor["type"])

    document["buffers"][0]["byteLength"] = len(binary)
    output_dir = OUTPUT_ROOT / name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_bin = output_dir / f"{name}.bin"
    output_bin.write_bytes(binary)
    document["buffers"][0]["uri"] = output_bin.name

    for image in document.get("images", []):
        uri = image.get("uri")
        if uri:
            shutil.copy2(source_dir / uri, output_dir / Path(uri).name)
            image["uri"] = Path(uri).name

    output_gltf = output_dir / f"{name}.gltf"
    output_gltf.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return output_gltf


def main() -> None:
    for name in ("azure-champion", "hooded-blade", "skeleton-gunslinger"):
        result = resample_character(name)
        print(f"Resampled {name}: {result}")


if __name__ == "__main__":
    main()
