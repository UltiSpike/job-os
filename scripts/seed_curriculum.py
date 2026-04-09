"""Seed curriculum from data/curriculum/*.json into the DB.

Idempotent: re-running upserts everything in place.

Usage:
    python -m scripts.seed_curriculum
    python -m scripts.seed_curriculum data/curriculum/k8s.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python -m scripts.seed_curriculum` from project root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.storage import curriculum_repo  # noqa: E402
from server.storage.db import init_db  # noqa: E402


def seed_file(path: Path) -> tuple[int, int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    track = data["track"]
    curriculum_repo.upsert_track(
        slug=track["slug"], name=track["name"], description=track.get("description", "")
    )
    n_modules = 0
    n_lessons = 0
    for m in data.get("modules", []):
        curriculum_repo.upsert_module(
            slug=m["slug"],
            track_slug=track["slug"],
            order_index=m.get("order_index", 0),
            name=m["name"],
            description=m.get("description", ""),
        )
        n_modules += 1
        for l in m.get("lessons", []):
            cap = l.get("capstone") or {}
            curriculum_repo.upsert_lesson(
                slug=l["slug"],
                module_slug=m["slug"],
                order_index=l.get("order_index", 0),
                name=l["name"],
                concept_md=l.get("concept_md", ""),
                prereq_slugs=l.get("prereq") or [],
                est_minutes=l.get("est_minutes", 20),
                capstone_prompt=cap.get("prompt", ""),
                capstone_depth=cap.get("depth", 2),
            )
            n_lessons += 1
    return 1, n_modules, n_lessons


def main():
    init_db()
    paths: list[Path]
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = sorted((ROOT / "data" / "curriculum").glob("*.json"))
    if not paths:
        print("no curriculum files found under data/curriculum/")
        sys.exit(1)
    total_t = total_m = total_l = 0
    for p in paths:
        t, m, l = seed_file(p)
        print(f"  ✓ {p.name}: {t} track, {m} modules, {l} lessons")
        total_t += t
        total_m += m
        total_l += l
    print(f"done. tracks={total_t} modules={total_m} lessons={total_l}")


if __name__ == "__main__":
    main()
