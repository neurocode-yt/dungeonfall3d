from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
PBR_DIR = ROOT / "assets3d" / "pbr"


def pack_selector(roughness_path: Path, output_path: Path) -> None:
    """Pack AO/roughness/metalness into SimplePBR's selector RGB texture.

    SimplePBR samples selector.r as ambient occlusion, selector.g as
    roughness, and selector.b as metallic. Dungeon stone uses full AO,
    authored roughness, and zero metallic.
    """
    rough = Image.open(roughness_path).convert("L")
    ao = Image.new("L", rough.size, 255)
    metallic = Image.new("L", rough.size, 0)
    Image.merge("RGB", (ao, rough, metallic)).save(output_path, quality=94)


def main() -> None:
    PBR_DIR.mkdir(parents=True, exist_ok=True)
    flat_normal = Image.new("RGB", (8, 8), (128, 128, 255))
    flat_normal.save(PBR_DIR / "flat_normal.png")

    pack_selector(
        PBR_DIR / "stone_wall_rough_2k.jpg",
        PBR_DIR / "stone_wall_selector_2k.jpg",
    )
    pack_selector(
        PBR_DIR / "stone_floor_rough_2k.jpg",
        PBR_DIR / "stone_floor_selector_2k.jpg",
    )

    print("Prepared SimplePBR normal/selector maps in", PBR_DIR)


if __name__ == "__main__":
    main()
