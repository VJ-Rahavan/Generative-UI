"""Built-in exercise library (static reference data)."""

import difflib
from dataclasses import asdict, dataclass
from typing import Any, Literal

Difficulty = Literal["beginner", "intermediate", "advanced"]

MUSCLE_GROUPS = (
    "chest", "back", "shoulders", "biceps", "triceps", "quads",
    "hamstrings", "glutes", "calves", "core", "forearms", "full body",
)  # fmt: skip
EQUIPMENT = ("barbell", "dumbbell", "cable", "machine", "bodyweight", "kettlebell", "band")


@dataclass(frozen=True, slots=True)
class Exercise:
    name: str
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]
    equipment: str
    difficulty: Difficulty
    category: Literal["compound", "isolation"]
    instructions: tuple[str, ...]
    tips: tuple[str, ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "primary_muscles": list(self.primary_muscles),
            "equipment": self.equipment,
            "difficulty": self.difficulty,
            "category": self.category,
        }

    def details(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in data.items()}


def _ex(
    name: str,
    primary: tuple[str, ...],
    secondary: tuple[str, ...],
    equipment: str,
    difficulty: Difficulty,
    category: Literal["compound", "isolation"],
    instructions: tuple[str, ...],
    tips: tuple[str, ...] = (),
) -> Exercise:
    return Exercise(name, primary, secondary, equipment, difficulty, category, instructions, tips)


EXERCISES: tuple[Exercise, ...] = (
    # ---- chest
    _ex("Barbell Bench Press", ("chest",), ("triceps", "shoulders"), "barbell", "intermediate", "compound",
        ("Lie on the bench with eyes under the bar, feet planted.",
         "Grip slightly wider than shoulders, retract shoulder blades.",
         "Lower the bar to mid-chest with elbows ~45° from the torso.",
         "Press up and slightly back to lockout."),
        ("Keep a slight arch and glutes on the bench.", "Use a spotter or safety pins for heavy sets.")),
    _ex("Incline Dumbbell Press", ("chest",), ("shoulders", "triceps"), "dumbbell", "beginner", "compound",
        ("Set the bench to 30–45°.", "Press dumbbells from shoulder level until arms are extended.",
         "Lower under control to a deep stretch."),
        ("Don't let the dumbbells drift too far apart at the bottom.",)),
    _ex("Push-Up", ("chest",), ("triceps", "shoulders", "core"), "bodyweight", "beginner", "compound",
        ("Hands slightly wider than shoulders, body in a straight line.",
         "Lower until the chest nearly touches the floor.", "Push back up to full extension."),
        ("Squeeze glutes to avoid sagging hips.", "Elevate hands to make it easier.")),
    _ex("Cable Fly", ("chest",), ("shoulders",), "cable", "beginner", "isolation",
        ("Set pulleys at chest height and step forward into a split stance.",
         "With a soft bend in the elbows, bring handles together in an arc.",
         "Return slowly until you feel a stretch across the chest.")),
    _ex("Dip", ("triceps", "chest"), ("shoulders",), "bodyweight", "intermediate", "compound",
        ("Support yourself on parallel bars with arms locked.",
         "Lean slightly forward and lower until shoulders are just below elbows.",
         "Press back up to lockout."),
        ("Stop short of depth if you feel shoulder pain.",)),
    # ---- back
    _ex("Deadlift", ("back", "hamstrings", "glutes"), ("forearms", "core", "quads"), "barbell", "advanced", "compound",
        ("Stand with mid-foot under the bar, hip-width stance.",
         "Hinge and grip the bar just outside the knees.",
         "Brace, flatten the back, and pull the slack out of the bar.",
         "Drive through the floor and extend hips and knees together.",
         "Lower by pushing hips back, keeping the bar close."),
        ("Never round the lower back under load.", "Keep the bar in contact with your legs.")),
    _ex("Pull-Up", ("back",), ("biceps", "forearms"), "bodyweight", "intermediate", "compound",
        ("Hang from the bar with an overhand grip, slightly wider than shoulders.",
         "Pull your chest toward the bar by driving elbows down.",
         "Lower to a full hang under control."),
        ("Use a band or negatives to build up to full reps.",)),
    _ex("Barbell Row", ("back",), ("biceps", "forearms", "core"), "barbell", "intermediate", "compound",
        ("Hinge to ~45° with a neutral spine, bar hanging at arm's length.",
         "Row the bar to the lower ribs, squeezing shoulder blades.",
         "Lower under control."),
        ("Avoid using momentum from the hips.",)),
    _ex("Lat Pulldown", ("back",), ("biceps",), "cable", "beginner", "compound",
        ("Grip the bar slightly wider than shoulders and sit with thighs secured.",
         "Pull the bar to the upper chest, leading with elbows.",
         "Return slowly to full stretch.")),
    _ex("Seated Cable Row", ("back",), ("biceps", "forearms"), "cable", "beginner", "compound",
        ("Sit tall with a slight knee bend.", "Row the handle to your stomach, chest up.",
         "Let shoulders stretch forward on the return.")),
    _ex("One-Arm Dumbbell Row", ("back",), ("biceps",), "dumbbell", "beginner", "compound",
        ("Brace one hand and knee on a bench, back flat.",
         "Row the dumbbell toward the hip.", "Lower to a full stretch.")),
    _ex("Face Pull", ("shoulders",), ("back",), "cable", "beginner", "isolation",
        ("Set a rope at upper-chest height.",
         "Pull toward your face, separating the rope and rotating hands back.",
         "Pause, then return slowly."),
        ("Great for shoulder health — keep the weight light.",)),
    # ---- shoulders
    _ex("Overhead Press", ("shoulders",), ("triceps", "core"), "barbell", "intermediate", "compound",
        ("Start with the bar on the front of the shoulders, grip just outside shoulders.",
         "Brace glutes and core, press the bar straight overhead.",
         "Move your head through once the bar passes your forehead; lock out."),
        ("Don't lean back excessively.",)),
    _ex("Seated Dumbbell Shoulder Press", ("shoulders",), ("triceps",), "dumbbell", "beginner", "compound",
        ("Sit upright with dumbbells at shoulder height.", "Press overhead without clashing the weights.",
         "Lower to ear level.")),
    _ex("Lateral Raise", ("shoulders",), (), "dumbbell", "beginner", "isolation",
        ("Stand with dumbbells at your sides.", "Raise arms out to shoulder height with a slight elbow bend.",
         "Lower slowly."),
        ("Lead with the elbows; avoid shrugging.",)),
    # ---- arms
    _ex("Dumbbell Curl", ("biceps",), ("forearms",), "dumbbell", "beginner", "isolation",
        ("Stand with palms forward.", "Curl the weights without swinging the elbows forward.",
         "Lower fully.")),
    _ex("Hammer Curl", ("biceps", "forearms"), (), "dumbbell", "beginner", "isolation",
        ("Hold dumbbells with a neutral grip.", "Curl up keeping palms facing each other.", "Lower slowly.")),
    _ex("Barbell Curl", ("biceps",), ("forearms",), "barbell", "beginner", "isolation",
        ("Grip the bar shoulder-width, palms up.", "Curl to shoulder height, elbows pinned.",
         "Lower under control.")),
    _ex("Triceps Pushdown", ("triceps",), (), "cable", "beginner", "isolation",
        ("Grip the bar or rope at chest height, elbows at your sides.",
         "Extend elbows fully.", "Return until forearms are just above parallel.")),
    _ex("Skull Crusher", ("triceps",), (), "barbell", "intermediate", "isolation",
        ("Lie on a bench holding an EZ-bar over your chest.",
         "Bend at the elbows to lower the bar toward your forehead.", "Extend back up."),
        ("Keep upper arms still; go lighter than you think.",)),
    # ---- legs
    _ex("Back Squat", ("quads", "glutes"), ("hamstrings", "core"), "barbell", "intermediate", "compound",
        ("Bar on upper back, feet shoulder-width, toes slightly out.",
         "Brace and sit down between your hips, knees tracking toes.",
         "Reach at least parallel depth.", "Drive up through the whole foot."),
        ("Keep chest up and core braced.", "Use safety bars in the rack.")),
    _ex("Front Squat", ("quads",), ("glutes", "core"), "barbell", "advanced", "compound",
        ("Rack the bar on the front delts, elbows high.", "Squat down keeping torso upright.",
         "Drive up, keeping elbows up.")),
    _ex("Goblet Squat", ("quads", "glutes"), ("core",), "dumbbell", "beginner", "compound",
        ("Hold a dumbbell at your chest.", "Squat down between your knees, chest tall.", "Stand back up.")),
    _ex("Romanian Deadlift", ("hamstrings", "glutes"), ("back", "forearms"), "barbell", "intermediate", "compound",
        ("Stand tall holding the bar, soft knees.",
         "Push hips back, sliding the bar down the thighs until you feel a hamstring stretch.",
         "Drive hips forward to stand."),
        ("Keep the back neutral; depth comes from the hips, not the spine.",)),
    _ex("Leg Press", ("quads", "glutes"), ("hamstrings",), "machine", "beginner", "compound",
        ("Feet shoulder-width on the platform.", "Lower until knees reach ~90°.",
         "Press without locking the knees hard.")),
    _ex("Walking Lunge", ("quads", "glutes"), ("hamstrings", "core"), "dumbbell", "beginner", "compound",
        ("Step forward and lower until both knees are ~90°.", "Push through the front heel into the next step.")),
    _ex("Bulgarian Split Squat", ("quads", "glutes"), ("hamstrings",), "dumbbell", "intermediate", "compound",
        ("Rear foot on a bench, front foot a stride ahead.", "Lower straight down until the back knee nearly touches.",
         "Drive up through the front foot.")),
    _ex("Hip Thrust", ("glutes",), ("hamstrings",), "barbell", "beginner", "compound",
        ("Upper back on a bench, bar over hips.", "Drive hips up until the torso is parallel to the floor.",
         "Pause and squeeze, then lower.")),
    _ex("Leg Curl", ("hamstrings",), (), "machine", "beginner", "isolation",
        ("Adjust the pad above the heels.", "Curl the heels toward the glutes.", "Lower slowly.")),
    _ex("Leg Extension", ("quads",), (), "machine", "beginner", "isolation",
        ("Pad on the lower shins.", "Extend knees fully and squeeze.", "Lower under control.")),
    _ex("Standing Calf Raise", ("calves",), (), "machine", "beginner", "isolation",
        ("Balls of the feet on the platform.", "Rise as high as possible.", "Lower to a deep stretch.")),
    # ---- core / full body
    _ex("Plank", ("core",), ("shoulders",), "bodyweight", "beginner", "isolation",
        ("Forearms under shoulders, body straight from head to heels.", "Brace and hold."),
        ("Don't let hips sag or pike.",)),
    _ex("Hanging Leg Raise", ("core",), ("forearms",), "bodyweight", "intermediate", "isolation",
        ("Hang from a bar.", "Raise legs to hip height or higher without swinging.", "Lower slowly.")),
    _ex("Cable Crunch", ("core",), (), "cable", "beginner", "isolation",
        ("Kneel facing a high pulley holding a rope by your head.",
         "Crunch down by flexing the spine.", "Return slowly.")),
    _ex("Kettlebell Swing", ("glutes", "hamstrings"), ("core", "back"), "kettlebell", "intermediate", "compound",
        ("Hike the bell back between your legs.", "Snap the hips forward to float the bell to chest height.",
         "Let it fall back and repeat."),
        ("It's a hip hinge, not a squat or a front raise.",)),
    _ex("Farmer's Carry", ("forearms", "full body"), ("core",), "dumbbell", "beginner", "compound",
        ("Pick up heavy dumbbells and stand tall.", "Walk with short, quick steps for distance or time.")),
)  # fmt: skip

_BY_NAME = {e.name.lower(): e for e in EXERCISES}


def find_exercise(name: str) -> Exercise | None:
    """Case-insensitive lookup with substring and fuzzy fallback."""
    key = name.strip().lower()
    if key in _BY_NAME:
        return _BY_NAME[key]
    contains = [e for n, e in _BY_NAME.items() if key in n or n in key]
    if len(contains) == 1:
        return contains[0]
    close = difflib.get_close_matches(key, _BY_NAME, n=1, cutoff=0.75)
    return _BY_NAME[close[0]] if close else None


def suggest_exercises(name: str, n: int = 5) -> list[str]:
    return [_BY_NAME[m].name for m in difflib.get_close_matches(name.lower(), _BY_NAME, n, 0.4)]


def canonical_name(name: str) -> str:
    match = find_exercise(name)
    return match.name if match else name.strip()


def muscle_group(name: str) -> str:
    match = find_exercise(name)
    return match.primary_muscles[0] if match else "other"


def search_exercises(
    *,
    query: str | None = None,
    muscle: str | None = None,
    equipment: str | None = None,
    difficulty: str | None = None,
) -> list[Exercise]:
    results = []
    for ex in EXERCISES:
        if query and query.lower() not in ex.name.lower():
            continue
        if muscle and muscle.lower() not in (*ex.primary_muscles, *ex.secondary_muscles):
            continue
        if equipment and ex.equipment != equipment.lower():
            continue
        if difficulty and ex.difficulty != difficulty.lower():
            continue
        results.append(ex)
    # Primary-muscle matches first
    if muscle:
        results.sort(key=lambda e: muscle.lower() not in e.primary_muscles)
    return results
