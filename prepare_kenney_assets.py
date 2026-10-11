from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "third_party" / "kenney_mini_dungeon" / "Models" / "OBJ format"
OUT = ROOT / "assets3d" / "kenney"
OUT.mkdir(parents=True, exist_ok=True)


def relaxed_character(source_name: str, target_name: str, shoulder_y: float) -> None:
    src = SRC / source_name
    lines = src.read_text(encoding="utf-8").splitlines()

    vertices: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    for line in lines:
        if line.startswith("v "):
            _, x, y, z, *_ = line.split()
            vertices.append((float(x), float(y), float(z)))
        elif line.startswith("f "):
            faces.append([int(token.split("/")[0]) - 1 for token in line.split()[1:]])

    parent = list(range(len(vertices)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for face in faces:
        for i in face[1:]:
            union(face[0], i)

    components: dict[int, list[int]] = defaultdict(list)
    for i in range(len(vertices)):
        components[find(i)].append(i)

    right: set[int] = set()
    left: set[int] = set()
    for ids in components.values():
        xs = [vertices[i][0] for i in ids]
        ys = [vertices[i][1] for i in ids]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)

        # Arms, hands and shoulder pieces sit outside the torso and above the
        # hips. Legs/head/torso remain untouched.
        if mean_y > 0.20 and mean_y < 0.55:
            if mean_x > 0.145:
                right.update(ids)
            elif mean_x < -0.145:
                left.update(ids)

    # Rotate horizontal arms down about 62 degrees. Shoulder X positions are
    # close to +/-0.11 in both Kenney human/orc meshes.
    angle = math.radians(62)
    transformed = list(vertices)
    for ids, pivot_x, theta in ((right, 0.11, -angle), (left, -0.11, angle)):
        c, s = math.cos(theta), math.sin(theta)
        for i in ids:
            x, y, z = vertices[i]
            dx = x - pivot_x
            dy = y - shoulder_y
            nx = pivot_x + dx * c - dy * s
            ny = shoulder_y + dx * s + dy * c
            transformed[i] = (nx, ny, z)

    out_lines: list[str] = []
    vertex_index = 0
    for line in lines:
        if line.startswith("mtllib "):
            # Texture is explicitly assigned by Ursina, so the copied OBJ
            # does not need a relative .mtl file.
            continue
        if line.startswith("v "):
            x, y, z = transformed[vertex_index]
            out_lines.append(f"v {x:.7f} {y:.7f} {z:.7f}")
            vertex_index += 1
        else:
            out_lines.append(line)

    (OUT / target_name).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Generated {target_name}: {len(right)} right-arm verts, {len(left)} left-arm verts")


if __name__ == "__main__":
    relaxed_character("character-human.obj", "character-human-relaxed.obj", shoulder_y=0.34)
    relaxed_character("character-orc.obj", "character-orc-relaxed.obj", shoulder_y=0.35)
