"""Keyword lenses: reviewed phrase lists that say what a newsletter mentions.

A lens is a named list of words and phrases, such as "street sweeping" for
city services or "tax" for budget and taxes. A newsletter mentions a lens when
its subject and text contain the lens's phrases often enough (see
`LensMatcher.lenses_mentioned`). Unlike LLM topic
labels, lenses are transparent (the phrase list is the definition), cheap to
re-run over the whole archive, and do not drift when a prompt or model
changes.

Matching is explainable by design:

- Text is lowercased, URLs and email addresses are dropped, and each word is
  plural-folded (`analytics.plurals`), so "speed hump" also finds "Speed
  Humps". Phrases are folded the same way.
- A phrase matches whole words only, in order, within one sentence or list
  item: "park" never matches "parking", and no phrase spans a period,
  bullet or paragraph break. Line breaks inside a paragraph do not split a
  phrase, because some sources hard-wrap their text.
- Words with a common second meaning are only listed inside a qualifying
  phrase ("ice agents", not "ice"; "park district", not "park"). See
  AMBIGUOUS_WORDS, which `validate_lenses` enforces.

Lists may overlap: the two Strong Towns Chicago focus lenses are deliberately
narrower slices of the broad housing and transportation lenses. Which text is
matched (boilerplate-cleaned or raw) and how many phrase occurrences make a
mention are set in `utils/compute_analytics.py`, where the choices are
explained.
"""

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from analytics.plurals import fold_plural
from analytics.records import NewsletterRecord
from analytics.text import WORD_PATTERN, normalize_text

POSSESSIVE_SUFFIX = "'s"
# Sentence and list punctuation ends a phrase. Line breaks do not (see the
# module docstring); blank lines, which separate paragraphs, do.
SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.,;:!?()\[\]{}<>\"|/\\*#=+•·–—…]+")
PARAGRAPH_BREAK_PATTERN = re.compile(r"\n\s*\n")
# Joins a subject to its body as a separate paragraph.
SUBJECT_SEPARATOR = "\n\n"

# Words that must never be a phrase on their own, because in newsletter text
# their everyday meaning often differs from the lens meaning. Each may still
# appear inside a longer phrase that fixes the meaning ("ice agents", "park
# district"). Chosen from sampled matches in the archive.
AMBIGUOUS_WORDS: frozenset[str] = frozenset(
    {
        "ice",  # weather and skating vs. Immigration and Customs Enforcement
        "park",  # the verb, and neighborhood names (Wicker Park, Hyde Park)
        "parking",  # mostly "free parking available" in event listings
        "polish",  # the nationality vs. the verb
        "bears",  # the football team vs. the verb
        "caps",  # CAPS community policing vs. caps and gowns, rate caps
        "pace",  # Pace suburban buses vs. "at a fast pace"
        "station",  # train stations vs. police, gas, and Divvy stations
        "train",  # CTA trains vs. "kiddie train rides" and training
        "line",  # CTA lines vs. any line
        "development",  # real estate vs. workforce, child, and economic development
        "construction",  # buildings vs. road work
        "event",  # nearly every newsletter has an events section
        "vote",  # elections vs. City Council votes
        "voting",  # elections vs. council and participatory budgeting votes
        "health",  # "health and safety" headers, "financial health"
        "safety",  # appears in nearly every subject area
        "nature",  # "nature museum", and "of this nature"
        "principal",  # school principals vs. "principal place of residence"
        "exemption",  # property tax exemptions vs. SNAP work-requirement exemptions
        "officer",  # police officers vs. any officer
        "wellness",  # wellness programs vs. restaurant menus and staff wellness
        "911",  # "call 911" advice and the 9/11 memorial
        "resolution",  # council resolutions vs. other uses
        "ssa",  # Special Service Areas vs. the Social Security Administration
    }
)


@dataclass(frozen=True)
class Lens:
    """A named, reviewed list of phrases that defines one subject."""

    id: str
    label: str
    description: str
    phrases: tuple[str, ...]
    # A Strong Towns Chicago focus area rather than a broad civic subject.
    strong_towns_focus: bool = False


# The reviewed lens list. Phrases are written as readers would search for them;
# plurals need not be listed ("speed hump" also matches "speed humps"). A
# phrase that another phrase in the same lens contains adds nothing ("property
# tax" when "tax" is listed), so it is left out. Lens order is display order.
LENSES: tuple[Lens, ...] = (
    Lens(
        id="public_safety",
        label="Public safety",
        description="Police, crime, CAPS and police district council meetings, and violence prevention.",
        phrases=(
            "police",
            "CPD",
            "public safety",
            "community safety",
            "beat meeting",
            "CAPS meeting",
            "CAPS office",
            "district council",
            "district commander",
            "crime",
            "shooting",
            "gun violence",
            "homicide",
            "carjacking",
            "robbery",
            "burglary",
            "theft",
            "break-in",
            "arrest",
            "violence prevention",
            "safe passage",
            "safety alert",
            "fire department",
        ),
    ),
    Lens(
        id="city_services",
        label="City services",
        description="311, garbage and recycling, street sweeping, rodents, trees, snow, sewers, alleys, and cooling and warming centers.",
        phrases=(
            "311",
            "CHI311",
            "service request",
            "city services",
            "street sweeping",
            "street sweeper",
            "garbage",
            "recycling",
            "blue cart",
            "trash",
            "bulk pickup",
            "yard waste",
            "sanitation",
            "rodent",
            "rat",
            "graffiti",
            "tree trimming",
            "tree removal",
            "tree planting",
            "pothole",
            "snow",
            "water main",
            "sewer",
            "street light",
            "streetlight",
            "alley",
            "cooling center",
            "warming center",
        ),
    ),
    Lens(
        id="schools",
        label="Schools",
        description="Chicago Public Schools, students and teachers, local school councils, and the school board.",
        phrases=(
            "school",
            "CPS",
            "student",
            "teacher",
            "classroom",
            "kindergarten",
            "pre-K",
            "preschool",
            "elementary",
            "tutoring",
            "LSC",
            "board of education",
        ),
    ),
    Lens(
        id="parks_libraries",
        label="Parks, libraries & recreation",
        description="Park District facilities and programs, libraries, beaches, pools, and camps.",
        phrases=(
            "park district",
            "park advisory council",
            "park cleanup",
            "dog park",
            "playground",
            "fieldhouse",
            "field house",
            "pool",
            "splash pad",
            "beach",
            "ice rink",
            "recreation",
            "summer camp",
            "day camp",
            "library",
        ),
    ),
    Lens(
        id="immigration",
        label="Immigration",
        description="Immigration, immigration enforcement (ICE, Border Patrol, Operation Midway Blitz), and know-your-rights resources.",
        phrases=(
            "immigration",
            "immigrant",
            "migrant",
            "new arrivals",
            "asylum",
            "undocumented",
            "deportation",
            "know your rights",
            "welcoming city",
            "sanctuary",
            "ICE agent",
            "ICE activity",
            "ICE sighting",
            "ICE presence",
            "ICE operation",
            "ICE raid",
            "ICE enforcement",
            "ICE detention",
            "ICE custody",
            "ICE-free zone",
            "abolish ICE",
            "CBP",
            "border patrol",
            "federal agents",
            "Midway Blitz",
        ),
    ),
    Lens(
        id="housing_development",
        label="Housing & development",
        description="Housing, renters and landlords, homelessness, zoning, and proposed developments.",
        phrases=(
            "housing",
            "apartment",
            "condo",
            "rent",
            "renter",
            "tenant",
            "landlord",
            "eviction",
            "homeless",
            "homelessness",
            "unhoused",
            "zoning",
            "rezoning",
            "planned development",
            "proposed development",
            "new development",
            "development proposal",
            "developer",
            "mixed-use",
            "vacant lot",
            "demolition",
            "building permit",
        ),
    ),
    Lens(
        id="transportation",
        label="Transportation",
        description="CTA and Metra, biking and walking, traffic, parking rules, and street and sidewalk work.",
        phrases=(
            "CTA",
            "bus",
            "transit",
            "Metra",
            "Red Line",
            "Blue Line",
            "Brown Line",
            "Green Line",
            "Orange Line",
            "Pink Line",
            "Purple Line",
            "Divvy",
            "bike",
            "bicycle",
            "scooter",
            "pedestrian",
            "crosswalk",
            "sidewalk",
            "intersection",
            "traffic",
            "speed hump",
            "speed bump",
            "speed camera",
            "residential parking",
            "permit parking",
            "parking permit",
            "parking restriction",
            "parking ban",
            "parking meter",
            "parking enforcement",
            "street parking",
            "CDOT",
            "department of transportation",
            "IDOT",
            "Lake Shore Drive",
            "DLSD",
            "resurfacing",
            "repaving",
            "street closure",
            "lane closure",
        ),
    ),
    Lens(
        id="budget_taxes",
        label="Budget & taxes",
        description="The city budget, property and other taxes, TIF, pensions, aldermanic menu money, and participatory budgeting.",
        phrases=(
            "budget",
            "participatory budgeting",
            "tax",
            "TIF",
            "homeowner exemption",
            "senior exemption",
            "senior freeze",
            "assessor",
            "revenue",
            "deficit",
            "fiscal",
            "pension",
            "aldermanic menu",
            "menu money",
        ),
    ),
    Lens(
        id="events",
        label="Community events",
        description="Festivals, parades, block parties, farmers markets, concerts, and holiday events.",
        phrases=(
            "festival",
            "fest",
            "parade",
            "block party",
            "farmers market",
            "concert",
            "movie night",
            "picnic",
            "celebration",
            "art fair",
            "car show",
            "halloween",
            "trick or treat",
            "egg hunt",
            "tree lighting",
            "toy drive",
            "coat drive",
        ),
    ),
    Lens(
        id="elections_civic",
        label="Elections & civic participation",
        description="Elections and voting logistics, plus town halls, community meetings, and public hearings.",
        phrases=(
            "election",
            "voter",
            "early voting",
            "vote by mail",
            "register to vote",
            "ballot",
            "polling place",
            "census",
            "town hall",
            "ward night",
            "community meeting",
            "community input",
            "public hearing",
            "public comment",
        ),
    ),
    Lens(
        id="city_council",
        label="City Council & legislation",
        description="City Council meetings, ordinances, and legislation.",
        phrases=(
            "city council",
            "council meeting",
            "ordinance",
            "legislation",
        ),
    ),
    Lens(
        id="seniors_health",
        label="Seniors & health",
        description="Seniors, public and mental health, clinics, vaccines, and health coverage.",
        phrases=(
            "senior",
            "older adult",
            "public health",
            "CDPH",
            "mental health",
            "healthcare",
            "health care",
            "health insurance",
            "health fair",
            "clinic",
            "hospital",
            "vaccine",
            "vaccination",
            "flu shot",
            "COVID",
            "Medicare",
            "Medicaid",
            "Narcan",
            "overdose",
        ),
    ),
    Lens(
        id="food_assistance",
        label="Food & assistance programs",
        description="SNAP, food pantries, and utility, rental, and cash assistance.",
        phrases=(
            "SNAP",
            "food pantry",
            "food bank",
            "food drive",
            "food assistance",
            "WIC",
            "LIHEAP",
            "utility assistance",
            "rental assistance",
            "cash assistance",
        ),
    ),
    Lens(
        id="local_business",
        label="Local business",
        description="Small and local businesses, chambers of commerce, openings, business licensing, and business grants.",
        phrases=(
            "small business",
            "local business",
            "business owner",
            "business license",
            "chamber of commerce",
            "grand opening",
            "ribbon cutting",
            "shop local",
            "SBIF",
            "BACP",
            "special service area",
        ),
    ),
    Lens(
        id="zoning_land_use",
        label="Zoning & land use",
        description="Strong Towns Chicago focus: zoning changes and appeals, density, ADUs, and small multi-unit housing.",
        phrases=(
            "zoning",
            "rezoning",
            "map amendment",
            "planned development",
            "ZBA",
            "variance",
            "land use",
            "density",
            "upzoning",
            "downzoning",
            "transit-oriented development",
            "parking minimum",
            "ADU",
            "accessory dwelling unit",
            "coach house",
            "missing middle",
            "single stair",
            "two-flat",
            "three-flat",
            "four-flat",
            "2-flat",
            "3-flat",
            "4-flat",
        ),
        strong_towns_focus=True,
    ),
    Lens(
        id="street_safety",
        label="Street safety & traffic calming",
        description="Strong Towns Chicago focus: traffic calming, safer crossings, bike and bus lanes, and speed enforcement.",
        phrases=(
            "traffic calming",
            "traffic safety",
            "pedestrian safety",
            "vision zero",
            "speed hump",
            "speed bump",
            "speed limit",
            "speed camera",
            "red light camera",
            "Smart Streets",
            "crosswalk",
            "curb extension",
            "bump out",
            "pedestrian island",
            "refuge island",
            "road diet",
            "stop sign",
            "traffic signal",
            "bike lane",
            "bus lane",
        ),
        strong_towns_focus=True,
    ),
)


def tokenize_phrase(phrase: str) -> list[str]:
    """Split a phrase into lowercase, plural-folded words, dropping possessives."""
    words = WORD_PATTERN.findall(phrase.lower().replace("’", "'"))
    return [fold_plural(word.removesuffix(POSSESSIVE_SUFFIX)) for word in words]


def phrase_key(phrase: str) -> str:
    """The folded form a phrase is matched by: "Speed Humps" -> "speed hump"."""
    return " ".join(tokenize_phrase(phrase))


def split_into_sentences(text: str) -> Iterator[list[str]]:
    """Yield the folded words of each sentence or list item of text."""
    for paragraph in PARAGRAPH_BREAK_PATTERN.split(normalize_text(text)):
        for sentence in SENTENCE_BOUNDARY_PATTERN.split(paragraph):
            words = tokenize_phrase(sentence)
            if words:
                yield words


def contains_words(words: list[str], part: list[str]) -> bool:
    """True if part occurs in words as a contiguous run."""
    return any(
        words[start : start + len(part)] == part
        for start in range(len(words) - len(part) + 1)
    )


def validate_lenses(lenses: Iterable[Lens]) -> list[str]:
    """Return every problem with a lens list; an empty list means it is sound.

    Checks that ids are unique, that no phrase is a lone AMBIGUOUS_WORDS word,
    and that no phrase repeats or contains another phrase of the same lens
    (the longer one could never add a match, so it only misleads readers).
    """
    problems: list[str] = []
    seen_ids: set[str] = set()
    for lens in lenses:
        if lens.id in seen_ids:
            problems.append(f"duplicate lens id {lens.id!r}")
        seen_ids.add(lens.id)
        tokenized = [(phrase, tokenize_phrase(phrase)) for phrase in lens.phrases]
        for phrase, words in tokenized:
            if not words:
                problems.append(f"{lens.id}: phrase {phrase!r} has no words")
            elif len(words) == 1 and words[0] in AMBIGUOUS_WORDS:
                problems.append(f"{lens.id}: {phrase!r} is ambiguous on its own")
        for index, (phrase, words) in enumerate(tokenized):
            for other_phrase, other_words in tokenized[index + 1 :]:
                if (
                    words
                    and other_words
                    and (
                        contains_words(words, other_words)
                        or contains_words(other_words, words)
                    )
                ):
                    problems.append(
                        f"{lens.id}: {phrase!r} and {other_phrase!r} overlap"
                    )
    return problems


class LensMatcher:
    """Finds which lens phrases a text contains; built once, used for many texts."""

    def __init__(self, lenses: Iterable[Lens]) -> None:
        self.lenses = tuple(lenses)
        self.keys_by_lens = {
            lens.id: frozenset(phrase_key(phrase) for phrase in lens.phrases)
            for lens in self.lenses
        }
        self.phrase_keys: frozenset[str] = frozenset().union(
            *self.keys_by_lens.values()
        )
        self.first_words = {key.split(" ")[0] for key in self.phrase_keys}
        self.max_phrase_words = max(
            (len(key.split(" ")) for key in self.phrase_keys), default=0
        )

    def count_phrases(self, text: str) -> Counter[str]:
        """Count each lens phrase's occurrences in text, keyed by `phrase_key`."""
        found: Counter[str] = Counter()
        for words in split_into_sentences(text):
            for start, word in enumerate(words):
                if word not in self.first_words:
                    continue
                for end in range(
                    start + 1, min(start + self.max_phrase_words, len(words)) + 1
                ):
                    candidate = " ".join(words[start:end])
                    if candidate in self.phrase_keys:
                        found[candidate] += 1
        return found

    def lenses_mentioned(
        self, phrase_counts: Mapping[str, int], min_occurrences: int
    ) -> list[str]:
        """Return the ids of the lenses whose phrases occur at least min_occurrences
        times in total, in lens order.
        """
        return [
            lens.id
            for lens in self.lenses
            if sum(phrase_counts.get(key, 0) for key in self.keys_by_lens[lens.id])
            >= min_occurrences
        ]


def count_newsletter_phrases(
    newsletters: Iterable[NewsletterRecord], matcher: LensMatcher
) -> dict[str, Counter[str]]:
    """Count the lens phrases in each newsletter's subject and text, by newsletter id.

    The subject is its own paragraph, so no phrase spans subject and body.
    """
    return {
        newsletter.id: matcher.count_phrases(
            f"{newsletter.subject}{SUBJECT_SEPARATOR}{newsletter.plain_text}"
        )
        for newsletter in newsletters
    }


def summarize_lens_hits(
    matcher: LensMatcher,
    phrase_counts_by_newsletter: Mapping[str, Mapping[str, int]],
    lenses_by_newsletter: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    """Describe each lens with how many newsletters mention it and contain each phrase.

    This is the evidence a reader needs to audit a lens: its full definition
    plus which phrases do the work. Phrases are listed most-found first.
    """
    phrase_newsletters: Counter[str] = Counter(
        key for counts in phrase_counts_by_newsletter.values() for key in counts
    )
    lens_newsletters: Counter[str] = Counter(
        lens_id for lens_ids in lenses_by_newsletter.values() for lens_id in lens_ids
    )
    return [
        {
            "id": lens.id,
            "label": lens.label,
            "description": lens.description,
            "strong_towns_focus": lens.strong_towns_focus,
            "newsletters": lens_newsletters[lens.id],
            "phrases": sorted(
                (
                    {
                        "phrase": phrase,
                        "newsletters": phrase_newsletters[phrase_key(phrase)],
                    }
                    for phrase in lens.phrases
                ),
                key=lambda item: (-item["newsletters"], item["phrase"].lower()),
            ),
        }
        for lens in matcher.lenses
    ]
