"""Fitness tools exposed to the LLM. Each returns plain JSON-able data for the model to render."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from genui.domain.fitness import exercises as lib
from genui.domain.fitness.models import BodyMetric, WorkoutPlan, WorkoutSession, WorkoutSet
from genui.tools import ToolContext, ToolError, ToolRegistry

registry = ToolRegistry()


# --------------------------------------------------------------------------- helpers


def estimated_1rm(weight_kg: float, reps: int) -> float:
    """Epley estimate of one-rep max."""
    if weight_kg <= 0:
        return 0.0
    return round(weight_kg if reps <= 1 else weight_kg * (1 + reps / 30), 1)


def _fmt_set(weight_kg: float, reps: int) -> str:
    return f"{reps} reps (bodyweight)" if weight_kg <= 0 else f"{weight_kg:g} kg × {reps}"


def _pct_change(old: float, new: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _sessions_since(ctx: ToolContext, since: date) -> list[WorkoutSession]:
    async with ctx.session_factory() as session:
        result = await session.scalars(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == ctx.user_id, WorkoutSession.performed_on >= since)
            .options(selectinload(WorkoutSession.sets))
            .order_by(WorkoutSession.performed_on.desc(), WorkoutSession.id.desc())
        )
        return list(result)


def _session_summary(s: WorkoutSession) -> dict[str, Any]:
    by_exercise: dict[str, list[WorkoutSet]] = defaultdict(list)
    for st in s.sets:
        by_exercise[st.exercise].append(st)
    exercises = []
    for name, sets in by_exercise.items():
        top = max(sets, key=lambda x: (x.weight_kg, x.reps))
        exercises.append(
            {
                "exercise": name,
                "sets": len(sets),
                "top_set": _fmt_set(top.weight_kg, top.reps),
                "volume_kg": round(sum(x.weight_kg * x.reps for x in sets)),
            }
        )
    return {
        "id": s.id,
        "date": s.performed_on.isoformat(),
        "name": s.name,
        "duration_min": s.duration_min,
        "notes": s.notes,
        "total_sets": len(s.sets),
        "total_volume_kg": round(sum(x.weight_kg * x.reps for x in s.sets)),
        "exercises": exercises,
    }


# --------------------------------------------------------------------------- exercise library


class SearchExercisesArgs(BaseModel):
    query: str | None = Field(None, description="Text to match in the exercise name")
    muscle: str | None = Field(None, description=f"One of: {', '.join(lib.MUSCLE_GROUPS)}")
    equipment: str | None = Field(None, description=f"One of: {', '.join(lib.EQUIPMENT)}")
    difficulty: Literal["beginner", "intermediate", "advanced"] | None = None
    limit: int = Field(12, ge=1, le=40)


@registry.tool(label="Searching the exercise library")
async def search_exercises(args: SearchExercisesArgs, ctx: ToolContext) -> dict[str, Any]:
    """Search the built-in exercise library by name, muscle group, equipment or difficulty."""
    found = lib.search_exercises(
        query=args.query, muscle=args.muscle, equipment=args.equipment, difficulty=args.difficulty
    )
    return {"count": len(found), "exercises": [e.summary() for e in found[: args.limit]]}


class ExerciseDetailsArgs(BaseModel):
    name: str = Field(description="Exercise name, e.g. 'Romanian Deadlift'")


@registry.tool(label="Looking up exercise technique")
async def get_exercise_details(args: ExerciseDetailsArgs, ctx: ToolContext) -> dict[str, Any]:
    """Get muscles worked, equipment, step-by-step instructions and tips for an exercise."""
    ex = lib.find_exercise(args.name)
    if ex is None:
        suggestions = lib.suggest_exercises(args.name)
        raise ToolError(
            f"Exercise '{args.name}' is not in the library."
            + (f" Did you mean: {', '.join(suggestions)}?" if suggestions else "")
            + " You may still describe it from general knowledge."
        )
    return ex.details()


# --------------------------------------------------------------------------- workouts


class LoggedSet(BaseModel):
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(0, ge=0, le=1000, description="0 for bodyweight")


class LoggedExercise(BaseModel):
    exercise: str
    sets: list[LoggedSet] = Field(min_length=1, max_length=20)


class LogWorkoutArgs(BaseModel):
    name: str = Field(description="Session name, e.g. 'Push day'")
    exercises: list[LoggedExercise] = Field(min_length=1, max_length=20)
    performed_on: date | None = Field(None, description="YYYY-MM-DD; defaults to today")
    duration_min: int | None = Field(None, ge=1, le=600)
    notes: str | None = None


@registry.tool(label="Logging your workout")
async def log_workout(args: LogWorkoutArgs, ctx: ToolContext) -> dict[str, Any]:
    """Save a completed workout session. Detects new personal records (estimated 1RM)."""
    performed_on = args.performed_on or date.today()
    async with ctx.session_factory() as session:
        workout = WorkoutSession(
            user_id=ctx.user_id,
            name=args.name,
            performed_on=performed_on,
            duration_min=args.duration_min,
            notes=args.notes,
        )
        prs = []
        for item in args.exercises:
            name = lib.canonical_name(item.exercise)
            previous_best = await session.scalar(
                select(func.max(WorkoutSet.weight_kg * (1 + WorkoutSet.reps / 30.0)))
                .join(WorkoutSession)
                .where(WorkoutSession.user_id == ctx.user_id, WorkoutSet.exercise == name)
            )
            best_now = max(estimated_1rm(s.weight_kg, s.reps) for s in item.sets)
            if best_now > 0 and previous_best is not None and best_now > previous_best:
                prs.append(
                    {
                        "exercise": name,
                        "est_1rm_kg": best_now,
                        "previous_kg": round(previous_best, 1),
                    }
                )
            for i, s in enumerate(item.sets, start=1):
                workout.sets.append(
                    WorkoutSet(exercise=name, set_number=i, reps=s.reps, weight_kg=s.weight_kg)
                )
        session.add(workout)
        await session.commit()
        await session.refresh(workout, ["sets"])
        summary = _session_summary(workout)
    return {"saved": True, "session": summary, "personal_records": prs}


class HistoryArgs(BaseModel):
    days: int = Field(30, ge=1, le=365, description="Look-back window in days")
    limit: int = Field(15, ge=1, le=50)


@registry.tool(label="Fetching workout history")
async def get_workout_history(args: HistoryArgs, ctx: ToolContext) -> dict[str, Any]:
    """List recent workout sessions with per-exercise top sets and volume."""
    sessions = await _sessions_since(ctx, date.today() - timedelta(days=args.days))
    return {
        "period_days": args.days,
        "total_sessions": len(sessions),
        "sessions": [_session_summary(s) for s in sessions[: args.limit]],
    }


class ProgressArgs(BaseModel):
    exercise: str
    days: int = Field(90, ge=7, le=730)


@registry.tool(label="Analyzing exercise progress")
async def get_exercise_progress(args: ProgressArgs, ctx: ToolContext) -> dict[str, Any]:
    """Per-session progression for one exercise: top weight, estimated 1RM and volume over time."""
    name = lib.canonical_name(args.exercise)
    since = date.today() - timedelta(days=args.days)
    async with ctx.session_factory() as session:
        rows = (
            await session.execute(
                select(WorkoutSession.performed_on, WorkoutSet.weight_kg, WorkoutSet.reps)
                .join(WorkoutSession)
                .where(
                    WorkoutSession.user_id == ctx.user_id,
                    WorkoutSet.exercise == name,
                    WorkoutSession.performed_on >= since,
                )
                .order_by(WorkoutSession.performed_on)
            )
        ).all()
        if not rows:
            logged = await session.scalars(
                select(WorkoutSet.exercise)
                .join(WorkoutSession)
                .where(WorkoutSession.user_id == ctx.user_id)
                .distinct()
            )
            raise ToolError(
                f"No sets of '{name}' logged in the last {args.days} days. "
                f"Exercises with history: {', '.join(sorted(logged)) or 'none'}."
            )

    by_day: dict[date, list[tuple[float, int]]] = defaultdict(list)
    for performed_on, weight, reps in rows:
        by_day[performed_on].append((weight, reps))
    points: list[dict[str, Any]] = []
    e1rms: list[float] = []
    for day, sets in by_day.items():
        e1rms.append(max(estimated_1rm(w, r) for w, r in sets))
        top_w, top_r = max(sets)
        points.append(
            {
                "date": day.isoformat(),
                "top_weight_kg": top_w,
                "est_1rm_kg": e1rms[-1],
                "volume_kg": round(sum(w * r for w, r in sets)),
                "best_set": _fmt_set(top_w, top_r),
            }
        )
    first, last = e1rms[0], e1rms[-1]
    return {
        "exercise": name,
        "sessions": len(points),
        "first_est_1rm_kg": first,
        "latest_est_1rm_kg": last,
        "best_est_1rm_kg": max(e1rms),
        "change_pct": _pct_change(first, last),
        "history": points,
    }


class SummaryArgs(BaseModel):
    days: int = Field(7, ge=1, le=90, description="Period length, e.g. 7 for this week")


@registry.tool(label="Building your training summary")
async def get_training_summary(args: SummaryArgs, ctx: ToolContext) -> dict[str, Any]:
    """Dashboard stats: sessions, sets, volume, sets per muscle group, comparison with the
    previous period and weekly volume for the last 8 weeks."""
    today = date.today()
    period_start = today - timedelta(days=args.days - 1)
    lookback = min(period_start - timedelta(days=args.days), today - timedelta(weeks=8))
    sessions = await _sessions_since(ctx, lookback)

    current = [s for s in sessions if s.performed_on >= period_start]
    previous = [
        s
        for s in sessions
        if period_start - timedelta(days=args.days) <= s.performed_on < period_start
    ]

    def totals(group: list[WorkoutSession]) -> dict[str, Any]:
        sets = [st for s in group for st in s.sets]
        durations = [s.duration_min for s in group if s.duration_min]
        return {
            "sessions": len(group),
            "sets": len(sets),
            "reps": sum(st.reps for st in sets),
            "volume_kg": round(sum(st.weight_kg * st.reps for st in sets)),
            "avg_duration_min": round(sum(durations) / len(durations)) if durations else None,
        }

    cur, prev = totals(current), totals(previous)
    muscle_sets: dict[str, int] = defaultdict(int)
    for s in current:
        for st in s.sets:
            muscle_sets[lib.muscle_group(st.exercise)] += 1

    weekly: dict[date, dict[str, Any]] = {}
    for i in range(7, -1, -1):
        wk = _week_start(today) - timedelta(weeks=i)
        weekly[wk] = {"week": wk.isoformat(), "sessions": 0, "volume_kg": 0}
    for s in sessions:
        wk = _week_start(s.performed_on)
        if wk in weekly:
            weekly[wk]["sessions"] += 1
            weekly[wk]["volume_kg"] += round(sum(st.weight_kg * st.reps for st in s.sets))

    return {
        "period": {"days": args.days, "start": period_start.isoformat(), "end": today.isoformat()},
        "current": cur,
        "previous": prev,
        "change_pct": {
            "sessions": _pct_change(prev["sessions"], cur["sessions"]),
            "volume": _pct_change(prev["volume_kg"], cur["volume_kg"]),
        },
        "sets_by_muscle": sorted(
            ({"muscle": m, "sets": n} for m, n in muscle_sets.items()), key=lambda x: -x["sets"]
        ),
        "weekly": list(weekly.values()),
        "recent_sessions": [
            {"date": s.performed_on.isoformat(), "name": s.name} for s in current[:5]
        ],
    }


# --------------------------------------------------------------------------- body metrics


class LogBodyMetricArgs(BaseModel):
    weight_kg: float = Field(ge=25, le=400)
    body_fat_pct: float | None = Field(None, ge=2, le=70)
    recorded_on: date | None = Field(None, description="YYYY-MM-DD; defaults to today")


@registry.tool(label="Saving body metrics")
async def log_body_metric(args: LogBodyMetricArgs, ctx: ToolContext) -> dict[str, Any]:
    """Record body weight (and optionally body-fat %) for a day. Overwrites that day's entry."""
    day = args.recorded_on or date.today()
    async with ctx.session_factory() as session:
        entry = await session.scalar(
            select(BodyMetric).where(
                BodyMetric.user_id == ctx.user_id, BodyMetric.recorded_on == day
            )
        )
        if entry is None:
            entry = BodyMetric(user_id=ctx.user_id, recorded_on=day, weight_kg=args.weight_kg)
            session.add(entry)
        entry.weight_kg = args.weight_kg
        if args.body_fat_pct is not None:
            entry.body_fat_pct = args.body_fat_pct
        await session.commit()
    return {
        "saved": True,
        "date": day.isoformat(),
        "weight_kg": args.weight_kg,
        "body_fat_pct": args.body_fat_pct,
    }


class BodyMetricsArgs(BaseModel):
    days: int = Field(90, ge=7, le=730)


@registry.tool(label="Fetching body metrics")
async def get_body_metrics(args: BodyMetricsArgs, ctx: ToolContext) -> dict[str, Any]:
    """Body weight / body-fat history with overall change and average weekly rate."""
    since = date.today() - timedelta(days=args.days)
    async with ctx.session_factory() as session:
        entries = list(
            await session.scalars(
                select(BodyMetric)
                .where(BodyMetric.user_id == ctx.user_id, BodyMetric.recorded_on >= since)
                .order_by(BodyMetric.recorded_on)
            )
        )
    if not entries:
        return {"entries": [], "message": "No body metrics logged in this period."}
    first, last = entries[0], entries[-1]
    weeks = max((last.recorded_on - first.recorded_on).days / 7, 1)
    return {
        "entries": [
            {
                "date": e.recorded_on.isoformat(),
                "weight_kg": e.weight_kg,
                "body_fat_pct": e.body_fat_pct,
            }
            for e in entries
        ],
        "latest": {"date": last.recorded_on.isoformat(), "weight_kg": last.weight_kg,
                   "body_fat_pct": last.body_fat_pct},
        "change_kg": round(last.weight_kg - first.weight_kg, 1),
        "avg_weekly_change_kg": round((last.weight_kg - first.weight_kg) / weeks, 2),
        "body_fat_change_pct_points": (
            round(last.body_fat_pct - first.body_fat_pct, 1)
            if last.body_fat_pct is not None and first.body_fat_pct is not None
            else None
        ),
    }  # fmt: skip


# --------------------------------------------------------------------------- nutrition

_ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725,
             "very_active": 1.9}  # fmt: skip
_GOAL_ADJUST = {"lose_fat": -0.20, "maintain": 0.0, "build_muscle": 0.10}
_PROTEIN_G_PER_KG = {"lose_fat": 2.2, "maintain": 1.8, "build_muscle": 2.0}


class NutritionArgs(BaseModel):
    sex: Literal["male", "female"]
    age: int = Field(ge=14, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float | None = Field(
        None, ge=30, le=300, description="Omit to use the latest logged body weight"
    )
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal: Literal["lose_fat", "maintain", "build_muscle"]
    meals_per_day: int = Field(4, ge=1, le=8)


@registry.tool(label="Calculating nutrition targets")
async def calculate_nutrition_targets(args: NutritionArgs, ctx: ToolContext) -> dict[str, Any]:
    """Daily calories and macros (Mifflin-St Jeor BMR × activity, adjusted for the goal)."""
    weight = args.weight_kg
    if weight is None:
        async with ctx.session_factory() as session:
            weight = await session.scalar(
                select(BodyMetric.weight_kg)
                .where(BodyMetric.user_id == ctx.user_id)
                .order_by(BodyMetric.recorded_on.desc())
                .limit(1)
            )
        if weight is None:
            raise ToolError("No body weight logged; ask the user for weight_kg.")

    bmr = 10 * weight + 6.25 * args.height_cm - 5 * args.age + (5 if args.sex == "male" else -161)
    tdee = bmr * _ACTIVITY[args.activity_level]
    calories = round(tdee * (1 + _GOAL_ADJUST[args.goal]) / 10) * 10
    protein_g = round(weight * _PROTEIN_G_PER_KG[args.goal])
    fat_g = round(calories * 0.25 / 9)
    carbs_g = max(round((calories - protein_g * 4 - fat_g * 9) / 4), 0)
    macro_kcal = {"protein": protein_g * 4, "carbs": carbs_g * 4, "fat": fat_g * 9}
    total = sum(macro_kcal.values()) or 1
    return {
        "inputs": {**args.model_dump(), "weight_kg": weight},
        "bmr_kcal": round(bmr),
        "tdee_kcal": round(tdee),
        "target_kcal": calories,
        "macros_g": {"protein": protein_g, "carbs": carbs_g, "fat": fat_g},
        "macro_split_pct": {k: round(v / total * 100) for k, v in macro_kcal.items()},
        "per_meal": {
            "kcal": round(calories / args.meals_per_day),
            "protein_g": round(protein_g / args.meals_per_day),
            "carbs_g": round(carbs_g / args.meals_per_day),
            "fat_g": round(fat_g / args.meals_per_day),
        },
        "water_l": round(weight * 0.035, 1),
        "note": "Estimates — adjust by ~100–200 kcal based on 2–3 weeks of weight trend.",
    }


# --------------------------------------------------------------------------- plans


class PlanExerciseArgs(BaseModel):
    name: str
    sets: int = Field(ge=1, le=20)
    reps: str = Field(description="e.g. '8-12'")
    rest_seconds: int | None = Field(None, ge=0, le=600)
    notes: str | None = None


class PlanDayArgs(BaseModel):
    day: str
    focus: str
    exercises: list[PlanExerciseArgs] = Field(min_length=1)


class SavePlanArgs(BaseModel):
    name: str
    goal: str | None = None
    days: list[PlanDayArgs] = Field(min_length=1, max_length=7)


@registry.tool(label="Saving your workout plan")
async def save_workout_plan(args: SavePlanArgs, ctx: ToolContext) -> dict[str, Any]:
    """Save a training program so the user can come back to it later."""
    async with ctx.session_factory() as session:
        plan = WorkoutPlan(
            user_id=ctx.user_id,
            name=args.name,
            goal=args.goal,
            days=[d.model_dump(exclude_none=True) for d in args.days],
        )
        session.add(plan)
        await session.commit()
        return {"saved": True, "plan_id": plan.id, "name": plan.name}


class ListPlansArgs(BaseModel):
    limit: int = Field(5, ge=1, le=20)


@registry.tool(label="Loading saved plans")
async def list_workout_plans(args: ListPlansArgs, ctx: ToolContext) -> dict[str, Any]:
    """List the user's saved training programs (most recent first) with full day details."""
    async with ctx.session_factory() as session:
        plans = await session.scalars(
            select(WorkoutPlan)
            .where(WorkoutPlan.user_id == ctx.user_id)
            .order_by(WorkoutPlan.id.desc())
            .limit(args.limit)
        )
        return {
            "plans": [
                {"id": p.id, "name": p.name, "goal": p.goal, "created_at": p.created_at.isoformat(),
                 "days": p.days}
                for p in plans
            ]
        }  # fmt: skip
