"""
config.py
=========

Every value you might want to change lives in this one file.
Nothing here is code you have to understand - they are just settings.

The most important settings are SKILL_GROUP_EDGE_WEIGHT and SIMILARITY_DECAY_K
below. Those are what make the graph "semantic" instead of "count the hops".
"""

import os

from dotenv import load_dotenv

# Reads the .env file in this folder (if any) into the process environment,
# so OPENAI_API_KEY below does not have to be set by hand every time.
load_dotenv()

# ---------------------------------------------------------------------------
# Where the ESCO files are
# ---------------------------------------------------------------------------

DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# The version of ESCO these settings were checked against. Concept URIs change
# between ESCO releases, so write the version down.
ESCO_VERSION = "1.2.1"

SKILLS_FILE = os.path.join(DATA_FOLDER, "skills_en.csv")
BROADER_RELATIONS_FILE = os.path.join(DATA_FOLDER, "broaderRelationsSkillPillar_en.csv")
DIGITAL_SKILLS_FILE = os.path.join(DATA_FOLDER, "digitalSkillsCollection_en.csv")
SKILL_SKILL_RELATIONS_FILE = os.path.join(DATA_FOLDER, "skillSkillRelations_en.csv")


# ---------------------------------------------------------------------------
# Which part of ESCO counts as "technology"
# ---------------------------------------------------------------------------
#
# We use two rules together, because neither one is clean on its own.
#
# Rule 1: the skill must sit under one of these two branches of the ESCO tree.
#         The first branch holds technology KNOWLEDGE (Python, PostgreSQL, ...).
#         The second holds computer COMPETENCES (software testing, networking...).
#
# Rule 2: the skill must also appear in digitalSkillsCollection_en.csv, which
#         is a list ESCO curated by hand.
#
# Why both? Rule 1 alone drags in misfiled ESCO entries such as "operate nail
# gun" and "maintain pharmacy records". Rule 2 alone drags in things that are
# digital but not software engineering, such as "assemble robots" and
# "aircraft flight control systems". Requiring both gives a clean subset.

TECHNOLOGY_BRANCH_ROOT_URIS = [
    # "information and communication technologies (icts)"  - the knowledge side
    "http://data.europa.eu/esco/isced-f/06",
    # "working with computers"                             - the competence side
    "http://data.europa.eu/esco/skill/243eb885-07c7-4b77-ab9c-827551d83dc4",
]

# A few genuinely technical skills are inside the branches above but were left
# out of digitalSkillsCollection_en.csv. We add them back by name.
EXTRA_SKILL_LABELS_TO_KEEP = [
    "deep learning",
    "quantum computing",
    "usability engineering",
    "scientific modelling",
    "blockchain openness",
]


# ---------------------------------------------------------------------------
# THE TWO KINDS OF ESCO RELATIONSHIP
# ---------------------------------------------------------------------------
#
# broaderRelationsSkillPillar_en.csv does not contain one kind of relationship.
# Its "broaderType" column tells us there are two, and they mean very
# different things:
#
#   KnowledgeSkillCompetence  the parent is another SKILL
#                             "Python is a kind of computer programming"
#                             This is a real statement about the skills.
#
#   SkillGroup                the parent is an ISCED-F education category
#                             "Python is filed under software and applications
#                              development and analysis"
#                             This is a filing decision, not a statement that
#                             two skills are alike. That bucket holds 161
#                             concepts, from quantum computing to WordPress.
#
# We name them like this everywhere in the project.
RELATION_TYPE_SKILL = "skill"              # skill -> skill      (real hierarchy)
RELATION_TYPE_SKILL_GROUP = "skill_group"  # skill -> ISCED group (classification)

# What ESCO calls them in the CSV, so we can translate the column.
ESCO_BROADER_TYPE_SKILL = "KnowledgeSkillCompetence"
ESCO_BROADER_TYPE_GROUP = "SkillGroup"


# ---------------------------------------------------------------------------
# A THIRD KIND OF RELATIONSHIP: ESCO's own skill-to-skill links
# ---------------------------------------------------------------------------
#
# skillSkillRelations_en.csv is not about parent and child at all. Each row is
# ESCO directly saying two skills belong together - one is "essential" or
# "optional" for the other - even when they sit in completely different
# branches of the classification tree. broaderRelationsSkillPillar_en.csv can
# only ever connect two skills that share an ancestor; this file connects
# skills ESCO itself has curated as related, regardless of where either one
# is filed.
RELATION_TYPE_SKILL_RELATION = "skill_relation"  # skill <-> skill (ESCO curated link, not hierarchy)


# ---------------------------------------------------------------------------
# THE EDGE WEIGHTS - the heart of this graph
# ---------------------------------------------------------------------------
#
# A weight is the COST of walking along one edge. Dijkstra always looks for
# the cheapest total route, so cheap edges are the ones it prefers.
#
# The cost is decided by two things together:
#
#   1. the RELATIONSHIP TYPE - is this a real skill relationship, or just an
#      education category?
#   2. how GENERIC the parent is - measured by depth, where 0 is the very top
#      of the tree and deeper means more specific.
#
# Real skill relationships are cheap, because they say something true about
# the two skills. Education categories are expensive, because "both of these
# are filed under software" says almost nothing.
#
# The effect is that Dijkstra prefers to travel along genuine skill hierarchy
# whenever such a route exists, and only falls back on the education
# categories when there is no other way through. No special logic is needed
# inside Dijkstra - the weights alone produce that behaviour.

# A skill -> skill edge, for example "Python -> computer programming" or
# "Ansible -> tools for software configuration management".
SKILL_EDGE_WEIGHT = 1

# A skill -> ISCED group edge. Still needed to keep the graph connected, but
# deliberately expensive - a filing decision should always cost more than a
# real relationship.
#
# Kept deliberately simple for now: every SKILL_GROUP edge costs this same
# flat number, no matter how big or small the classification bucket is.
# graph.calculate_subtree_sizes() already measures each bucket's size (it
# still gets stored on every node and shown in the report), so a size-aware
# cost can be wired back into get_edge_weight() later without recomputing
# anything - this is just not doing that yet.
SKILL_GROUP_EDGE_WEIGHT = 8

# A skill <-> skill edge from skillSkillRelations_en.csv. This is real,
# curated evidence that two skills go together, so both weights stay far
# cheaper than any skill_group edge. "essential" is stronger evidence than
# "optional", so it costs less.
ESSENTIAL_SKILL_RELATION_WEIGHT = 1
OPTIONAL_SKILL_RELATION_WEIGHT = 2

# ---------------------------------------------------------------------------
# Spelling repair when a typed skill does not match an ESCO name exactly
# ---------------------------------------------------------------------------
#
# 1.0 means "the text must be identical" and 0.0 means "anything goes".
#
# 0.85 was chosen by testing. It still repairs real typing mistakes such as
# "pyton" and "my sql", but it refuses to invent a meaning: at 0.75 the word
# "linux" was matched to "database management systems", because that concept
# happens to carry a stray alternative label "db.linux". Lower this value at
# your own risk.
FUZZY_MATCH_CUTOFF = 0.85


# ---------------------------------------------------------------------------
# Turning a path cost into a similarity percentage
# ---------------------------------------------------------------------------
#
# A path cost is not a count of steps. Because a skill edge costs 1 and a
# group edge costs several times that, the cost tells you what KIND of route
# was taken. Instead of sorting costs into hand-picked bands, similarity
# decays smoothly as cost grows:
#
#   similarity = 100 * exp(-path_cost / SIMILARITY_DECAY_K)
#
# K=10 means every 10 points of accumulated cost divides similarity by e
# (about 2.72). It is anchored on one plain-English judgement: a direct
# skill parent/child (cost 1) should score about 90% - solving
# 90 = 100*exp(-1/K) for K gives about 9.5, rounded to the cleaner 10. Every
# other point on the curve follows from that one anchor, not a separate guess.
SIMILARITY_DECAY_K = 10.0

# Anything with no path at all in the graph - the two skills are unrelated.
SIMILARITY_WHEN_TOO_FAR = 0


# ---------------------------------------------------------------------------
# LLM-based skill extraction from uploaded JD / resume PDFs
# ---------------------------------------------------------------------------
#
# This is the one part of the project that is NOT purely ESCO-driven: an LLM
# decides which words in a PDF are worth treating as skills at all. Whatever
# it returns is then still mapped onto ESCO exactly like a manually typed
# skill, so a skill the LLM invents but ESCO does not recognise still ends up
# "not found in ESCO", same as today.

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_MODEL = "gpt-4o-mini"

# Roughly a page and a half. Keeps requests cheap and fast; a JD or one
# candidate's resume does not need more than this to list its skills.
LLM_MAX_INPUT_CHARS = 4000


# ---------------------------------------------------------------------------
# Only used by the report that "python graph.py" prints
# ---------------------------------------------------------------------------
#
# A few well known skills, so the printed check shows something recognisable
# instead of whichever concept happens to come first alphabetically.

SAMPLE_SKILL_LABELS_FOR_REPORT = [
    "Python (computer programming)",
    "PostgreSQL",
    "tools for software configuration management",
    "cloud technologies",
    "machine learning",
]

# Pairs of skills to compare in the report, to show that a cheap path really
# does mean "closely related" and an expensive path means "barely related".
SAMPLE_PAIRS_FOR_REPORT = [
    ("Python (computer programming)", "Java (computer programming)"),
    ("PostgreSQL", "MySQL"),
    ("tools for software configuration management",
     "Jenkins (tools for software configuration management)"),
    ("machine learning", "deep learning"),
    ("web services", "web programming"),
    ("Python (computer programming)", "JavaScript Framework"),
    ("cloud technologies", "CSS"),
    ("Python (computer programming)", "machine learning"),
]
