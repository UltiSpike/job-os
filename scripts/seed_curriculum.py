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

from server.storage import concepts_repo, curriculum_repo  # noqa: E402
from server.storage.base import now_iso, transaction  # noqa: E402
from server.storage.db import get_conn, init_db  # noqa: E402


def seed_drills(path: Path) -> int:
    """Upsert drill questions per lesson into the questions table.

    Stable id format: q_drill_<lesson_slug>_<n>. Idempotent — re-seeding rewrites
    text/best_practice_answer in place.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    drills_map = data.get("drills") or {}
    if not drills_map:
        return 0
    now = now_iso()
    n = 0
    with transaction() as conn:
        for lesson_slug, drills in drills_map.items():
            for i, d in enumerate(drills, start=1):
                qid = f"q_drill_{lesson_slug}_{i}"
                text = d.get("text", "").strip()
                answer = d.get("answer", "").strip()
                existing = conn.execute(
                    "SELECT id FROM questions WHERE id = ?", (qid,)
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE questions
                           SET text = ?, best_practice_answer = ?, lesson_slug = ?,
                               is_capstone = 0, source = 'curriculum', updated_at = ?
                           WHERE id = ?""",
                        (text, answer, lesson_slug, now, qid),
                    )
                else:
                    conn.execute(
                        """INSERT INTO questions (
                            id, text, source, lesson_slug, is_capstone,
                            best_practice_answer, speaking_logs, action_items,
                            created_at, updated_at
                        ) VALUES (?, ?, 'curriculum', ?, 0, ?, '[]', '[]', ?, ?)""",
                        (qid, text, lesson_slug, answer, now, now),
                    )
                n += 1
    return n


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
            # 1 lesson = 1 concept (slug 一致), 自动 upsert
            concepts_repo.upsert_concept(
                slug=l["slug"],
                name=l["name"],
                description=(l.get("concept_md") or "")[:200],
                track_slug=track["slug"],
                module_slug=m["slug"],
            )
            n_lessons += 1
    return 1, n_modules, n_lessons


def link_lesson_questions_to_concepts() -> int:
    """walk all questions with lesson_slug, ensure concept_questions row exists.
    1 lesson = 1 concept => question.lesson_slug == concept.slug.
    Idempotent."""
    n = 0
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, lesson_slug FROM questions WHERE lesson_slug IS NOT NULL AND lesson_slug != ''"
        ).fetchall()
        for r in rows:
            qid, lslug = r["id"], r["lesson_slug"]
            # 确认 concept 存在
            cexist = conn.execute("SELECT 1 FROM concepts WHERE slug = ?", (lslug,)).fetchone()
            if not cexist:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO concept_questions (concept_slug, question_id) VALUES (?, ?)",
                (lslug, qid),
            )
            n += 1
    return n


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
    total_t = total_m = total_l = total_d = 0
    for p in paths:
        if "drill" in p.name:
            d = seed_drills(p)
            print(f"  ✓ {p.name}: {d} drill questions")
            total_d += d
        else:
            t, m, l = seed_file(p)
            print(f"  ✓ {p.name}: {t} track, {m} modules, {l} lessons")
            total_t += t
            total_m += m
            total_l += l
    n_links = link_lesson_questions_to_concepts()
    print(f"  ✓ linked {n_links} questions to concepts")
    print(f"done. tracks={total_t} modules={total_m} lessons={total_l} drills={total_d}")


if __name__ == "__main__":
    main()
