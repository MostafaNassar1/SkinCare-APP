"""The onboarding skin quiz: its questions and how the answers become a skin type.

The quiz is the ONLY source of oiliness and dryness (and of redness from quiz v2): no reliable
licensed photo data exists for them (Phase 3 decision, migration 0010). Questions are original
(not copied from a copyrighted questionnaire) and are defined only here, so the app shows
whatever this file contains.

Scoring:
- Each answer may add points to an oil score and/or a dry score, and may be a T-zone sign
  (forehead, nose, chin).
- Frequent reactions to new products -> "sensitive" (decides over the rest: safety first).
- Otherwise: oil >= 4 and oil > dry -> "oily"; two or more T-zone signs -> "combination";
  dry >= 3 and dry > oil -> "dry"; anything else -> "normal".
- The sun question gives the Fitzpatrick skin tone type (1-6), used to check the AI model's
  accuracy per skin tone.
- Quiz v2 (2026-10-29): the redness question gives the redness concern of the routine (rarely ->
  none, sometimes -> mild, often -> moderate, most of the time with small visible blood vessels
  -> severe, which refers the user to a dermatologist instead of treating it). It asks about
  redness the face has on its own; reactions to products are the "reactions" question
  (sensitive skin). Answers of v1 have no redness answer: no redness until the quiz is retaken.
"""

from dataclasses import dataclass

QUIZ_VERSION = 2  # stored with the answers, so the quiz can change without breaking old results


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    oil: int = 0
    dry: int = 0
    t_zone: bool = False
    redness: str | None = None  # the redness concern's severity (quiz v2)


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    options: tuple[Option, ...]

    def option(self, option_id: str) -> Option | None:
        return next((option for option in self.options if option.id == option_id), None)


QUESTIONS: tuple[Question, ...] = (
    Question(
        "after_washing",
        "2-3 hours after washing your face (without applying any product), how does it feel?",
        (
            Option("tight", "Tight or dry", dry=2),
            Option("comfortable", "Comfortable"),
            Option("t_zone_shiny", "Shiny on the forehead and nose only", oil=1, t_zone=True),
            Option("all_shiny", "Shiny all over", oil=2),
        ),
    ),
    Question(
        "midday_shine",
        "By midday, how shiny is your face?",
        (
            Option("none", "Not shiny at all", dry=1),
            Option("t_zone", "Shiny on the forehead, nose and chin (T-zone)", oil=1, t_zone=True),
            Option("everywhere", "Shiny everywhere", oil=2),
        ),
    ),
    Question(
        "flaking",
        "How often do you notice flaky or rough patches?",
        (
            Option("often", "Often", dry=2),
            Option("sometimes", "Sometimes", dry=1),
            Option("rarely", "Rarely or never"),
        ),
    ),
    Question(
        "pores",
        "How visible are your pores?",
        (
            Option("barely", "Barely visible"),
            Option("nose", "Visible on the nose", t_zone=True),
            Option("nose_and_cheeks", "Visible on the nose and cheeks", oil=2),
        ),
    ),
    Question(
        "reactions",
        "How often do new skincare products cause redness, stinging or itching?",
        (
            Option("often", "Often"),
            Option("sometimes", "Sometimes"),
            Option("never", "Never"),
        ),
    ),
    Question(
        "redness",
        "How often does your face look red or flushed (cheeks, nose, chin), even when you have "
        "not tried a new product?",
        (
            Option("rarely", "Rarely or never"),
            Option("sometimes", "Sometimes, and it fades quickly", redness="mild"),
            Option(
                "often", "Often (with heat, sun or spicy food), and it lasts a while",
                redness="moderate",
            ),
            Option(
                "most_of_the_time", "Most of the time, with small visible blood vessels",
                redness="severe",
            ),
        ),
    ),
    Question(
        "sun",
        "What happens when you spend time in the sun without sunscreen?",
        (
            Option("type_1", "I always burn and never tan"),
            Option("type_2", "I burn easily and tan very little"),
            Option("type_3", "I sometimes burn, then tan gradually"),
            Option("type_4", "I rarely burn and tan easily"),
            Option("type_5", "I very rarely burn and tan very easily"),
            Option("type_6", "I never burn"),
        ),
    ),
    Question(
        "pregnancy",
        "Are you pregnant or breastfeeding?",
        (
            Option("yes", "Yes"),
            Option("no", "No"),
            Option("prefer_not", "Prefer not to say"),
        ),
    ),
)

QUESTIONS_BY_ID = {question.id: question for question in QUESTIONS}


@dataclass(frozen=True)
class QuizResult:
    skin_type: str
    fitzpatrick_scale: int
    is_pregnant_or_breastfeeding: bool | None  # None = "prefer not to say": leave the flag as is
    redness: str | None  # severity of the redness concern, None = no redness
    oil_score: int
    dry_score: int


def answer_errors(answers: dict[str, str]) -> list[dict[str, str]]:
    """Problems with a set of answers: every question once, with one of its own options."""
    errors = []
    for question in QUESTIONS:
        if question.id not in answers:
            errors.append({"field": f"answers.{question.id}", "message": "Answer required"})
        elif question.option(answers[question.id]) is None:
            allowed = ", ".join(option.id for option in question.options)
            errors.append(
                {"field": f"answers.{question.id}", "message": f"Must be one of: {allowed}"}
            )
    for question_id in answers.keys() - QUESTIONS_BY_ID.keys():
        errors.append({"field": f"answers.{question_id}", "message": "Unknown question"})
    return errors


def score(answers: dict[str, str]) -> QuizResult:
    """Turn complete, valid answers into a result (see the rules at the top of this file)."""
    chosen = [
        QUESTIONS_BY_ID[question_id].option(option_id) for question_id, option_id in answers.items()
    ]
    oil = sum(option.oil for option in chosen)
    dry = sum(option.dry for option in chosen)
    t_zone_signs = sum(option.t_zone for option in chosen)

    if answers["reactions"] == "often":
        skin_type = "sensitive"
    elif oil >= 4 and oil > dry:
        skin_type = "oily"
    elif t_zone_signs >= 2:
        skin_type = "combination"
    elif dry >= 3 and dry > oil:
        skin_type = "dry"
    else:
        skin_type = "normal"

    pregnancy = {"yes": True, "no": False, "prefer_not": None}[answers["pregnancy"]]
    return QuizResult(
        skin_type=skin_type,
        fitzpatrick_scale=int(answers["sun"].removeprefix("type_")),
        is_pregnant_or_breastfeeding=pregnancy,
        redness=QUESTIONS_BY_ID["redness"].option(answers["redness"]).redness,
        oil_score=oil,
        dry_score=dry,
    )


def redness_from_saved(saved: dict | None) -> str | None:
    """The redness severity of the saved quiz answers ({"version", "answers"}); None for no
    redness, no quiz yet, or a v1 quiz (taken before the redness question existed)."""
    answer = ((saved or {}).get("answers") or {}).get("redness")
    option = QUESTIONS_BY_ID["redness"].option(answer) if answer else None
    return option.redness if option else None
