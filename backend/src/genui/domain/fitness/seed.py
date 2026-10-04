"""Seed ~8 weeks of realistic training and body-weight history for the demo user.

Uses a fixed-seed `random.Random` purely for reproducible demo data (not security-sensitive).
"""

import logging
import random
from collections.abc import Iterator
from datetime import date, timedelta

from sqlalchemy import func, select

from genui.db.session import SessionFactory
from genui.domain.fitness.models import BodyMetric, WorkoutSession, WorkoutSet

logger = logging.getLogger(__name__)

# (exercise, sets, reps, starting kg, weekly progression kg)
_TEMPLATES: dict[str, list[tuple[str, int, int, float, float]]] = {
    "Push day": [
        ("Barbell Bench Press", 4, 6, 72.5, 1.25),
        ("Overhead Press", 3, 8, 40.0, 0.625),
        ("Incline Dumbbell Press", 3, 10, 24.0, 0.5),
        ("Lateral Raise", 3, 15, 8.0, 0.25),
        ("Triceps Pushdown", 3, 12, 25.0, 0.5),
    ],
    "Pull day": [
        ("Deadlift", 3, 5, 130.0, 2.5),
        ("Pull-Up", 3, 8, 0.0, 0.0),
        ("Barbell Row", 3, 8, 62.5, 1.25),
        ("Face Pull", 3, 15, 20.0, 0.25),
        ("Dumbbell Curl", 3, 10, 12.0, 0.25),
    ],
    "Leg day": [
        ("Back Squat", 4, 6, 100.0, 2.5),
        ("Romanian Deadlift", 3, 8, 85.0, 1.25),
        ("Leg Press", 3, 10, 160.0, 5.0),
        ("Leg Curl", 3, 12, 40.0, 0.5),
        ("Standing Calf Raise", 4, 12, 60.0, 1.25),
    ],
}
_ROTATION = ["Push day", "Pull day", "Leg day"]
_TRAINING_WEEKDAYS = (0, 2, 4, 5)  # Mon, Wed, Fri, Sat


def _round_to(x: float, step: float) -> float:
    return round(x / step) * step if x > 0 else 0.0


def _build_workout(
    rng: random.Random, user_id: str, name: str, day: date, week: int
) -> WorkoutSession:
    workout = WorkoutSession(
        user_id=user_id, name=name, performed_on=day, duration_min=rng.randint(55, 80)
    )
    for exercise, n_sets, reps, base, step in _TEMPLATES[name]:
        weight = _round_to(base + step * week, 2.5 if base >= 20 else 1.0)
        # Bodyweight moves progress by reps instead of load
        target_reps = reps + week // 3 if base == 0 else reps
        for set_number in range(1, n_sets + 1):
            # Fatigue: occasionally drop a rep or two on the last set
            drop = rng.choice((0, 0, 1, 2)) if set_number == n_sets else 0
            workout.sets.append(
                WorkoutSet(
                    exercise=exercise,
                    set_number=set_number,
                    reps=max(target_reps - drop, 1),
                    weight_kg=weight,
                )
            )
    return workout


def _workouts(rng: random.Random, user_id: str, start: date, end: date) -> Iterator[WorkoutSession]:
    rotation_idx = 0
    day = start
    while day < end:
        if day.weekday() in _TRAINING_WEEKDAYS and rng.random() > 0.1:  # ~10% missed sessions
            name = _ROTATION[rotation_idx % len(_ROTATION)]
            rotation_idx += 1
            yield _build_workout(rng, user_id, name, day, week=(day - start).days // 7)
        day += timedelta(days=1)


def _body_metrics(rng: random.Random, user_id: str, start: date, end: date) -> Iterator[BodyMetric]:
    """A slow cut from ~84 kg with daily noise, logged every 2-3 days."""
    weight, body_fat = 84.0, 20.5
    day = start
    while day <= end:
        yield BodyMetric(
            user_id=user_id,
            recorded_on=day,
            weight_kg=round(weight + rng.uniform(-0.35, 0.35), 1),
            body_fat_pct=round(body_fat + rng.uniform(-0.2, 0.2), 1),
        )
        step_days = rng.choice((2, 3))
        weight -= 0.045 * step_days
        body_fat -= 0.03 * step_days
        day += timedelta(days=step_days)


async def seed_demo_data(session_factory: SessionFactory, user_id: str, *, weeks: int = 8) -> bool:
    """Insert demo history if the user has none. Returns True when data was inserted."""
    async with session_factory() as session:
        existing = await session.scalar(
            select(func.count())
            .select_from(WorkoutSession)
            .where(WorkoutSession.user_id == user_id)
        )
        if existing:
            return False

        rng = random.Random(42)  # noqa: S311 - deterministic demo data
        today = date.today()
        start = today - timedelta(weeks=weeks)
        workouts = list(_workouts(rng, user_id, start, today))
        session.add_all(workouts)
        session.add_all(_body_metrics(rng, user_id, start, today))
        await session.commit()
        logger.info("Seeded %d demo workouts for user %s", len(workouts), user_id)
        return True
