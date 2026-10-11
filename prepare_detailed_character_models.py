"""Build static high-detail character rigs for procedural animation.

The AutoSprite meshes are much more detailed than the previous live Pirate
characters.  Their authored keyframe tracks do not survive Panda's animation
import reliably, but the skin/joint hierarchy itself does.  The game therefore
loads static Assimp-converted rigs and drives the joints directly at runtime.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from panda3d.core import LoaderFileTypeRegistry, ModelPool, loadPrcFileData


ROOT = Path(__file__).resolve().parent
PROCESSED_ROOT = ROOT / "third_party" / "autosprite_free" / "processed"
STATIC_ROOT = ROOT / "third_party" / "autosprite_free" / "static"
OPTIMIZED_ROOT = ROOT / "third_party" / "autosprite_free" / "optimized"
OUTPUT_ROOT = ROOT / "assets3d" / "detailed_characters"

CHARACTERS = ("azure-champion", "hooded-blade")


def make_static_gltf(name: str) -> Path:
    source_dir = PROCESSED_ROOT / name
    source_path = source_dir / f"{name}.gltf"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document.pop("animations", None)

    output_dir = STATIC_ROOT / name
    output_dir.mkdir(parents=True, exist_ok=True)

    buffer_uri = document["buffers"][0]["uri"]
    shutil.copy2(source_dir / buffer_uri, output_dir / Path(buffer_uri).name)
    document["buffers"][0]["uri"] = Path(buffer_uri).name

    for image in document.get("images", []):
        uri = image.get("uri")
        if uri:
            shutil.copy2(source_dir / uri, output_dir / Path(uri).name)
            image["uri"] = Path(uri).name

    output_path = output_dir / f"{name}.gltf"
    output_path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return output_path


def main() -> None:
    # Force glTF through Panda's native Assimp plug-in.  panda3d-gltf remains
    # installed for the rest of the project, but its conversion path is the one
    # that left these particular rigs visually frozen under SimplePBR.
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "load-file-type gltf p3assimp")
    loadPrcFileData("", "load-file-type glb p3assimp")
    loadPrcFileData("", "notify-level-assimp error")
    loadPrcFileData("", "notify-level-loader error")
    from direct.showbase.ShowBase import ShowBase

    base = ShowBase(windowType="offscreen")
    registry = LoaderFileTypeRegistry.getGlobalPtr()
    for extension in ("gltf", "glb"):
        current = registry.getTypeFromExtension(extension)
        if current and current.getName() == "Python loader":
            registry.unregisterType(current)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        for name in CHARACTERS:
            optimized = OPTIMIZED_ROOT / f"{name}.glb"
            source = optimized if optimized.exists() else make_static_gltf(name)
            ModelPool.releaseAllModels()
            source_rel = source.relative_to(ROOT).as_posix()
            model = base.loader.loadModel(source_rel, noCache=True)
            if model.isEmpty():
                raise RuntimeError(f"Assimp returned an empty model for {name}")
            output = OUTPUT_ROOT / f"{name}.bam"
            output_rel = output.relative_to(ROOT).as_posix()
            if not model.writeBamFile(output_rel):
                raise RuntimeError(f"Could not write {output}")
            print(f"Prepared {name}: {output}")
    finally:
        base.destroy()


if __name__ == "__main__":
    main()
