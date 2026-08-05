"""
mapping.py
==========

This file turns the words a human types ("postgres", "pyton", "ML") into a
real ESCO technology skill ("PostgreSQL", "Python (computer programming)",
"machine learning").

EVERYTHING HERE COMES FROM ESCO
-------------------------------
There is no hand written dictionary of tool names in this project. The only
vocabulary we recognise is the vocabulary ESCO itself publishes:

  1. the preferred label of every skill in the graph
  2. every alternative label ESCO lists for those skills

ESCO's alternative labels are richer than people expect. They already give us
"python", "postgres", "git", "ml", "jenkins", "cloud computing" and about
4,200 other names for free.

The consequence is important and intentional: if ESCO does not contain a
technology, this project reports "not found in ESCO" instead of guessing.
Docker, Kubernetes, FastAPI, Flask, AWS, Azure, React and Node.js are all
absent from ESCO 1.2.1, so they will not be matched. That is the honest
answer, and it keeps the whole demo faithful to the ESCO taxonomy.

The one thing we do on top of ESCO is repair spelling. "pyton" is matched to
"python" because they are the same word typed badly - not because we decided
what "pyton" means. The strictness of that repair lives in
config.FUZZY_MATCH_CUTOFF.

Everything is compared in lower case, so "PYTHON", "Python" and "python" all
behave the same way.
"""

import difflib

import config
from graph import load_skills_table


# ---------------------------------------------------------------------------
# Step 1: build the search index
# ---------------------------------------------------------------------------

def build_mapping_index(technology_graph):
    """
    Build one dictionary we can search when mapping a typed skill.

    The dictionary key is a searchable name in lower case.
    The dictionary value is a tuple (esco_label, esco_uri).

    We fill it from three sources, and all three of them are ESCO:
      1. the preferred label of every technology node in the graph
      2. the "altLabels" column   - synonyms ESCO shows to people
      3. the "hiddenLabels" column - synonyms ESCO keeps for searching only

    The order matters. Earlier sources win, so a name is never overwritten by
    a lower quality one. That protects us from mistakes inside ESCO itself:
    ESCO lists "mysql" as a hidden label of SQL Server, which is wrong, but
    because "mysql" is already the preferred label of MySQL from source 1, the
    correct answer stays.

    What it does : prepares the lookup table used by map_skill_to_esco().
    Inputs       : technology_graph - the graph from graph.build_technology_graph()
    Outputs      : a dictionary {searchable_lower_case_name: (esco_label, esco_uri)}
    """
    mapping_index = {}

    # --- source 1: the preferred labels of the technology graph -----------
    for concept_uri in technology_graph.nodes:
        esco_label = technology_graph.nodes[concept_uri]["label"]
        mapping_index[esco_label.lower()] = (esco_label, concept_uri)

    # --- sources 2 and 3: the two ESCO synonym columns -------------------
    # ESCO stores all the names of a skill inside ONE cell, separated by line
    # breaks. Both columns are read the same way, so we loop over them.
    skills_table = load_skills_table()

    for column_name in ["altLabels", "hiddenLabels"]:
        add_names_from_column(mapping_index, technology_graph,
                             skills_table, column_name)

    return mapping_index


def add_names_from_column(mapping_index, technology_graph, skills_table,
                         column_name):
    """
    Add every name found in one ESCO name column to the lookup table.

    What it does : reads one column of synonyms and puts each name into the
                   index, without ever overwriting a name that is already there.
    Inputs       : mapping_index    - the dictionary being filled in
                   technology_graph - used to skip skills outside our subset
                   skills_table     - from graph.load_skills_table()
                   column_name      - "altLabels" or "hiddenLabels"
    Outputs      : nothing, it changes mapping_index in place
    """
    for concept_uri, names_in_one_cell in zip(skills_table["conceptUri"],
                                              skills_table[column_name]):
        # Skip skills that are not part of our technology graph.
        if concept_uri not in technology_graph:
            continue

        # Skip empty cells (pandas reads them as NaN, which is not a string).
        if not isinstance(names_in_one_cell, str):
            continue

        esco_label = technology_graph.nodes[concept_uri]["label"]

        for one_name in names_in_one_cell.split("\n"):
            one_name = one_name.strip().lower()
            if one_name == "":
                continue

            # First source to claim a name keeps it.
            if one_name not in mapping_index:
                mapping_index[one_name] = (esco_label, concept_uri)


# ---------------------------------------------------------------------------
# Step 2: map one skill
# ---------------------------------------------------------------------------

def map_skill_to_esco(typed_skill, mapping_index):
    """
    Map one typed skill to one ESCO technology skill.

    What it does : looks the typed text up in ESCO's own vocabulary, and falls
                   back to a spelling repair when there is no direct hit.
    Inputs       : typed_skill   - what the user typed, for example "postgres"
                   mapping_index - the dictionary from build_mapping_index()
    Outputs      : a dictionary that always has the same four keys:
                     typed_skill -> the original text
                     esco_label  -> the ESCO name, or None when nothing matched
                     esco_uri    -> the ESCO URI, or None when nothing matched
                     match_type  -> "exact name", "similar name" or "not found"

                   "not found" is a normal, correct answer. It means ESCO has
                   no concept for that word, which is true for Docker, AWS,
                   FastAPI and many other modern tools.
    """
    search_text = typed_skill.strip().lower()

    # --- try an exact ESCO name first ------------------------------------
    # This covers both preferred labels ("PostgreSQL") and ESCO's own
    # alternative labels ("postgres", "git", "ml", "cloud computing").
    if search_text in mapping_index:
        esco_label, esco_uri = mapping_index[search_text]
        return {
            "typed_skill": typed_skill,
            "esco_label": esco_label,
            "esco_uri": esco_uri,
            "match_type": "exact name",
        }

    # --- otherwise repair the spelling -----------------------------------
    # difflib compares the typed text against every ESCO name we know and
    # returns the single closest one, but only when it is very close indeed
    # (see config.FUZZY_MATCH_CUTOFF). This fixes typing mistakes such as
    # "pyton"; it is not allowed to guess what an unknown tool means.
    all_known_esco_names = list(mapping_index.keys())
    closest_names = difflib.get_close_matches(search_text, all_known_esco_names,
                                              n=1, cutoff=config.FUZZY_MATCH_CUTOFF)

    if closest_names:
        esco_label, esco_uri = mapping_index[closest_names[0]]
        return {
            "typed_skill": typed_skill,
            "esco_label": esco_label,
            "esco_uri": esco_uri,
            "match_type": "similar name",
        }

    # --- nothing worked --------------------------------------------------
    return {
        "typed_skill": typed_skill,
        "esco_label": None,
        "esco_uri": None,
        "match_type": "not found",
    }


def map_skill_list_to_esco(typed_skills, mapping_index):
    """
    Map a whole list of typed skills, one after the other.

    What it does : calls map_skill_to_esco() for every skill in the list.
    Inputs       : typed_skills  - a list of strings the user typed
                   mapping_index - the dictionary from build_mapping_index()
    Outputs      : a list of mapping dictionaries, in the same order
    """
    mapping_results = []

    for typed_skill in typed_skills:
        mapping_results.append(map_skill_to_esco(typed_skill, mapping_index))

    return mapping_results


def shorten_uri(esco_uri):
    """
    Shorten a long ESCO URI so it fits nicely on the screen.

    "http://data.europa.eu/esco/skill/1234abcd..." becomes "skill/1234abcd...".

    What it does : cuts the common web address prefix off an ESCO URI.
    Inputs       : esco_uri - the full ESCO URI, or None
    Outputs      : the shortened URI as a string (empty string when None)
    """
    if esco_uri is None:
        return ""

    prefix_to_remove = "http://data.europa.eu/esco/"
    if esco_uri.startswith(prefix_to_remove):
        return esco_uri[len(prefix_to_remove):]

    return esco_uri
