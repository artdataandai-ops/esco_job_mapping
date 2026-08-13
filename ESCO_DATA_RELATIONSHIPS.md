# How the ESCO CSVs relate to each other (and how graph.py turns them into one graph)

Reference note — read this before explaining the mapping approach on a call.

## The one-sentence version

We have 4 ESCO CSV files. One is the master list of skills, one filters that
list down to "technology" skills, one gives the skill hierarchy (parent/child
edges), and one gives extra curated skill-to-skill shortcuts. `graph.py` reads
all four and builds **one weighted graph**, where cheap edges mean "these two
concepts are genuinely related" and expensive edges mean "these two concepts
just happen to be filed in the same bucket." Dijkstra's shortest path then
acts as a similarity score.

## The 4 files, one line each

| File | Role |
|---|---|
| `skills_en.csv` | Master list of every ESCO skill (13,960 rows): URI, label, alt labels, description. |
| `digitalSkillsCollection_en.csv` | A hand-curated filter: which skills count as "technology." Never creates edges. |
| `broaderRelationsSkillPillar_en.csv` | The hierarchy: parent/child edges (~20,800 rows). This is the tree structure. |
| `skillSkillRelations_en.csv` | Curated lateral shortcuts: "these two skills go together," independent of the tree (5,819 rows). |

---

## Deep dive: `broaderRelationsSkillPillar_en.csv` — the part that's easy to get wrong on a call

Each row means **"conceptUri sits inside broaderUri"**:

- `conceptUri` = the child (the more specific concept)
- `broaderUri` = the parent (the more general concept)

One row = one edge, direction is child → parent.

### The column that actually matters: `broaderType`

It only ever has two values, and they mean very different things:

| `broaderType` value | What the parent (`broaderUri`) actually is | Internal name | Edge weight |
|---|---|---|---|
| `KnowledgeSkillCompetence` | Another **real ESCO skill**. A genuine "is-a-kind-of" statement. | `skill` | **1** (cheap) |
| `SkillGroup` | An **ISCED-F education/classification category** — just a filing label, not a skill. | `skill_group` | **8** (expensive) |

Say it like this on a call: *"Some rows say a skill is a kind of another skill — that's a real relationship. Other rows just say a skill is filed under an education category — that's bookkeeping, not a relationship. We keep both, but we make the bookkeeping ones much more expensive to travel through."*

**Quick tell from the URL shape alone**, without even checking the column:
- `.../esco/isced-f/...` → always a `SkillGroup` (classification bucket)
- `.../esco/skill/<uuid>` → always `KnowledgeSkillCompetence` (a real skill)

### Worked example: Python and Java

Both skills have exactly two parent rows each in this file:

| skill | broaderUri (parent) | broaderType |
|---|---|---|
| Python (computer programming) | `.../skill/21d2f96d-...` → **computer programming** | `KnowledgeSkillCompetence` |
| Java (computer programming) | `.../skill/21d2f96d-...` → **computer programming** | `KnowledgeSkillCompetence` |
| Python (computer programming) | `.../isced-f/0613` → **software and applications development and analysis** | `SkillGroup` |
| Java (computer programming) | `.../isced-f/0613` → **software and applications development and analysis** | `SkillGroup` |

Note the parent URI is **identical** on both skills' rows in each case — that shared value is literally what connects them. This gives two possible routes between Python and Java:

- **Via "computer programming"** (real skill parent): 1 + 1 = **cost 2**
- **Via the SkillGroup** (classification bucket): 8 + 8 = **cost 16**

Dijkstra computes both totals and returns the cheaper one — **not** "whichever appears first in the file." It's picked purely because 2 < 16. If the weights were reversed, the answer would flip, with no other code change.

---

## Deep dive: `skillSkillRelations_en.csv`

Plain definition: a list of skill pairs ESCO's curators directly vouch for as
related, regardless of where either sits in the hierarchy. Each row is tagged
`essential` (weight **1**) or `optional` (weight **2**).

### Example 1 — where it adds nothing (Python & Java)

Python and Java are each linked to a *different, unrelated* skill in this
file — not to each other:

```
use scripting programming        --optional-->   Python (computer programming)
use object-oriented programming  --optional-->   Java (computer programming)
```

No row pairs Python with Java directly, so this file contributes nothing
extra for that pair — the hierarchy already connects them at cost 2 anyway.

### Example 2 — where it's the whole story (the best one to use on a call)

```
operate relational database management system  --optional-->  MySQL
```

These two skills share **no hierarchy parent at all**:

| skill | broaderUri (parent) | broaderType |
|---|---|---|
| operate relational database management system | managing, gathering and storing digital data | `SkillGroup` |
| MySQL | database management systems | `KnowledgeSkillCompetence` |
| MySQL | database and network design and administration | `SkillGroup` |

Verified directly against the built graph: **remove** the
`skillSkillRelations` edges and ask for the hierarchy-only route between
them:

```
operate relational database management system
  -> managing, gathering and storing digital data
  -> use databases
  -> museum databases
  -> database
  -> database and network design and administration
  -> MySQL                                                    cost 34
```

Six hops, wandering through an unrelated "museum databases" detour, cost 34.
**With** the curated edge in place, it's just:

```
operate relational database management system  <->  MySQL     cost 2
```

This is the clearest illustration of the file's value: without it, two
skills that obviously belong together (you use MySQL *to* operate a
relational database) would look almost unrelated by hierarchy alone.

---

## Where `digitalSkillsCollection_en.csv` fits in

Pure filter, nothing else. A skill only becomes a graph node if it's **both**:
1. somewhere under one of the two technology root branches in `config.py`, **and**
2. present in `digitalSkillsCollection_en.csv`.

It never creates an edge — it only decides which skills are even eligible to
be "technology" nodes (`find_technology_skill_uris` in `graph.py`). Rule 1
alone lets in misfiled junk ("operate nail gun"); rule 2 alone lets in
non-IT digital skills ("assemble robots"). Both together give a clean set.

---

## Putting it together: the full weight table

From `config.py`:

| Edge source | Meaning | Weight |
|---|---|---|
| `broaderRelationsSkillPillar`, `broaderType = KnowledgeSkillCompetence` | real skill → skill parent | **1** |
| `broaderRelationsSkillPillar`, `broaderType = SkillGroup` | skill → classification bucket | **8** |
| `skillSkillRelations`, `relationType = essential` | curated, strong evidence | **1** |
| `skillSkillRelations`, `relationType = optional` | curated, weaker evidence | **2** |

Because real relationships are always far cheaper than classification
bucket hops, Dijkstra naturally prefers to travel through genuine skill
relationships and only climbs into an education category when there's no
other way through. That's what turns a plain shortest-path search into a
usable similarity score (`similarity = 100 * exp(-cost / 10)`).

---

## Cheat-sheet: if asked on the spot

- **"Is the graph cyclic?"** Yes — verified directly on the built graph:
  777 nodes, 1234 edges, 458 independent cycles. It's cyclic because ESCO
  skills can have more than one parent (e.g. Python has two), so shared
  parents naturally create loops. This doesn't break Dijkstra — it only
  requires non-negative weights, which we have.
- **"Do we need to fetch the actual ESCO URI/webpage?"** No. The URI is only
  used as a join key across the 4 CSVs and as the node ID in the graph.
  Every label, alt-label, description, and relationship the app uses is
  already flattened into the CSV columns — no network call needed. (ESCO's
  URIs do resolve to a live page because they're Linked-Data identifiers,
  but that page just renders the same underlying data we already have
  locally.)
- **"Why not just count hops?"** Because a hop through a classification
  bucket ("both filed under software") says almost nothing, while a hop
  through a real skill parent says something true. Weighting lets the
  algorithm tell those two apart instead of treating every step as equal.
- **"What's the difference between the hierarchy file and the relations
  file, in one line?"** The hierarchy file can only connect two skills that
  share an ancestor somewhere in the tree; the relations file connects
  skills ESCO curators picked by hand, even when they sit in completely
  different branches.
