from __future__ import annotations

import json
from pathlib import Path

from prepare_quaternius_assets import convert_obj, read_materials, safe_name, split_obj


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "third_party" / "quaternius_knight_selected"
PARTS = ROOT / "assets3d" / "knight_parts"
BAM_DIR = ROOT / "assets3d" / "knight_bam"
MANIFEST = ROOT / "assets3d" / "knight_manifest.json"

MODELS = ("KnightCharacter", "Helmet1", "Helmet2", "ShoulderPads", "Sword")


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
