from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "third_party" / "quaternius_selected"
PARTS = ROOT / "assets3d" / "quaternius_parts"
BAM_DIR = ROOT / "assets3d" / "quaternius_bam"
MANIFEST = ROOT / "assets3d" / "quaternius_manifest.json"

MODELS = (
    "Character_Animated",
    "Wall",
    "Floor_Standard",
    "Wall_ArchGothic",
    "Column_Round",
    "Doors_GothicArch",
    "Torch",
    "Barrel",
    "Bookcase_Full",
    "Bricks",
    "Candles_1",
)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def read_materials(path: Path) -> dict[str, dict[str, object]]:
    materials: dict[str, dict[str, object]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            current = line.split(maxsplit=1)[1]
            materials[current] = {"color": [1.0, 1.0, 1.0, 1.0]}
        elif current and line.startswith("Kd "):
            values = [float(v) for v in line.split()[1:4]]
            materials[current]["color"] = [*values, materials[current]["color"][3]]
        elif current and line.startswith("d "):
            alpha = float(line.split()[1])
            materials[current]["color"][3] = alpha
    return materials


def split_obj(path: Path) -> dict[str, list[str]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    # Keep all vertex/normal/UV data so original face indices remain valid.
    common = [
        line
        for line in lines
        if not line.startswith(("f ", "usemtl ", "mtllib "))
    ]
    faces: dict[str, list[str]] = {}
    current = "default"
    for line in lines:
        if line.startswith("usemtl "):
            current = line.split(maxsplit=1)[1].strip()
            faces.setdefault(current, [])
        elif line.startswith("f "):
            faces.setdefault(current, []).append(line)
    return {name: common + group for name, group in faces.items() if group}


def convert_obj(obj_path: Path, bam_path: Path) -> None:
    egg_path = bam_path.with_suffix(".egg")
    subprocess.run(
        ["obj2egg", "-o", str(egg_path), str(obj_path)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["egg2bam", "-o", str(bam_path), str(egg_path)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    egg_path.unlink(missing_ok=True)


def main() -> None:
    PARTS.mkdir(parents=True, exist_ok=True)
    BAM_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, list[dict[str, object]]] = {}

    for model in MODELS:
        obj_path = SOURCE / f"{model}.obj"
        mtl_path = SOURCE / f"{model}.mtl"
        if not obj_path.exists() or not mtl_path.exists():
            print(f"Skipping {model}: source file missing")
            continue

        materials = read_materials(mtl_path)
        parts = split_obj(obj_path)
        manifest[model] = []
        for material_name, content in parts.items():
            part_name = f"{model}__{safe_name(material_name)}"
            part_obj = PARTS / f"{part_name}.obj"
            part_bam = BAM_DIR / f"{part_name}.bam"
            part_obj.write_text("\n".join(content) + "\n", encoding="utf-8")
            convert_obj(part_obj, part_bam)
            info = materials.get(material_name, {"color": [1.0, 1.0, 1.0, 1.0]})
            manifest[model].append(
                {
                    "material": material_name,
                    "bam": part_bam.relative_to(ROOT).as_posix(),
                    "color": info["color"],
                }
            )
        print(f"Prepared {model}: {len(manifest[model])} material parts")

    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
