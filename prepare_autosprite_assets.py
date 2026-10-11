"""Prepare the detailed CC0 AutoSprite characters for Panda3D/Ursina.

AutoSprite's free GLB files use ``EXT_texture_webp``.  panda3d-gltf 1.3.0
does not currently resolve that extension, so converting the GLB directly to
BAM drops the textures.  This helper rewrites each GLB as an equivalent glTF
with ordinary external PNG textures, then asks ``gltf2bam`` to emit the model
and each animation as separate BAM files.

The raw downloads stay untouched under ``third_party/autosprite_free``.
"""

from __future__ import annotations

import io
import json
import struct
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "third_party" / "autosprite_free"
PROCESSED_DIR = RAW_DIR / "processed"
OUTPUT_DIR = ROOT / "assets3d" / "autosprite"

CHARACTERS = (
    "azure-champion",
    "hooded-blade",
    "paladin",
    "silver-knight",
    "skeleton-gunslinger",
)


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(data):
        raise ValueError(f"Unsupported or corrupt GLB: {path}")

    offset = 12
    json_chunk: bytes | None = None
    bin_chunk = b""
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == 0x4E4F534A:  # JSON
            json_chunk = chunk
        elif chunk_type == 0x004E4942:  # BIN\0
            bin_chunk = chunk

    if json_chunk is None:
        raise ValueError(f"GLB has no JSON chunk: {path}")
    document = json.loads(json_chunk.decode("utf-8").rstrip("\x00 \t\r\n"))
    return document, bin_chunk


def _remove_webp_extension(document: dict) -> None:
    for key in ("extensionsUsed", "extensionsRequired"):
        values = document.get(key)
        if not values:
            continue
        document[key] = [value for value in values if value != "EXT_texture_webp"]
        if not document[key]:
            document.pop(key, None)


def rewrite_textured_gltf(name: str) -> Path:
    raw_path = RAW_DIR / f"{name}.glb"
    if not raw_path.exists():
        raise FileNotFoundError(raw_path)

    document, binary = _read_glb(raw_path)
    target_dir = PROCESSED_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    # Keep the original binary buffer intact.  Mesh/skin/animation accessors
    # still point at it; the old embedded image bytes can harmlessly remain.
    bin_name = f"{name}.bin"
    (target_dir / bin_name).write_bytes(binary)
    if document.get("buffers"):
        document["buffers"][0]["uri"] = bin_name

    images = document.get("images", [])
    buffer_views = document.get("bufferViews", [])
    for index, image in enumerate(images):
        if "bufferView" not in image:
            continue
        view = buffer_views[image["bufferView"]]
        start = int(view.get("byteOffset", 0))
        length = int(view["byteLength"])
        source = binary[start : start + length]
        png_name = f"{name}_texture_{index}.png"
        with Image.open(io.BytesIO(source)) as decoded:
            decoded.convert("RGBA").save(target_dir / png_name, "PNG")
        image.clear()
        image.update({"name": f"{name}_texture_{index}", "uri": png_name})

    for texture in document.get("textures", []):
        extension = texture.get("extensions", {}).get("EXT_texture_webp")
        if extension and "source" in extension:
            texture["source"] = extension["source"]
        texture.pop("extensions", None)

    _remove_webp_extension(document)
    gltf_path = target_dir / f"{name}.gltf"
    gltf_path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return gltf_path


def convert_character(name: str) -> None:
    gltf_path = rewrite_textured_gltf(name)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{name}.bam"
    subprocess.run(
        ["gltf2bam", "--animations", "separate", str(gltf_path), str(output_path)],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    for name in CHARACTERS:
        print(f"Preparing {name}...")
        convert_character(name)
    print(f"Prepared {len(CHARACTERS)} detailed characters in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
