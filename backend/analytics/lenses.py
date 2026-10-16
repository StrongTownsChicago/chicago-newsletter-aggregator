"""Keyword lenses: reviewed phrase lists that say what a newsletter mentions.

A lens is a named list of words and phrases, such as "street sweeping" for city
services or "tax" for budget and taxes. A newsletter mentions a lens when its
subject and text contain the lens's phrases often enough (see
`analytics.lens_matching`, which holds the matching). Unlike LLM topic labels,
lenses are transparent (the phrase list is the definition), cheap to re-run
over the whole archive, and do not drift when a prompt or model changes.

Lists may overlap: the two Strong Towns Chicago focus lenses are deliberately
narrower slices of the broad housing and transportation lenses. Which text is
matched (boilerplate-cleaned or raw) and how many mentions a newsletter needs
are set, and explained, in `utils/compute_analytics.py`.
"""

from dataclasses import dataclass

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
            # "ins" is too short to fold, so the plural is listed too.
            "break-ins",
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
