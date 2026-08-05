"""
config.py
=========

Every value you might want to change lives in this one file.
Nothing here is code you have to understand - they are just settings.

The most important setting is EDGE_WEIGHT_BY_PARENT_DEPTH at the bottom.
That table is what makes the graph "semantic" instead of "count the hops".
"""

import os

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
# deliberately expensive. The deeper the group, the narrower it is, so the
# cheaper the step.
SKILL_GROUP_EDGE_WEIGHT_BY_DEPTH = {
    0: 12,  # the very top of the classification tree - almost meaningless
    1: 8,   # a huge ESCO group
    2: 5,   # a mid sized ESCO group, e.g. software and applications development
}

# Used for any group deeper than the table above.
DEFAULT_SKILL_GROUP_EDGE_WEIGHT = 5

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
# group edge costs 5 or more, the cost tells you what KIND of route was taken.
# So we group the costs into bands, and each band has a real meaning:
#
#   cost 1 or 2   the route used only genuine skill relationships
#   cost 5+       the route had to go through an education category, which
#                 means ESCO knows of no real relationship between the two
#
# Read the list from the top down and use the first band that fits:
#   (highest cost still inside this band, similarity percentage)

SIMILARITY_BANDS = [
    (0, 100),   # the very same ESCO concept
    (1, 90),    # direct skill parent and child, e.g. git and Ansible
    (2, 75),    # siblings under a real skill, e.g. Python and Java
    (4, 60),    # a short chain of real skill relationships
    (6, 50),    # one education category step, plus real skill steps
    (10, 35),   # joined ONLY through an education category
    (20, 15),   # joined only near the top of the classification tree
]

# Anything more expensive than the last band above.
SIMILARITY_WHEN_TOO_FAR = 0


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
