"""
scoring.py
==========

This file does the actual candidate scoring.

The idea is very simple:

  For every job description skill
      compare it with every candidate skill
      keep the candidate skill with the SHORTEST path in the ESCO graph
      turn that path length into a similarity percentage

  The overall score is the average of all those percentages.

We use Dijkstra's shortest path algorithm from NetworkX to measure the
distance between two ESCO skills.
"""

import difflib

import config
from graph import find_shortest_path, get_label


# ---------------------------------------------------------------------------
# Path cost -> similarity
# ---------------------------------------------------------------------------
#
# The graph is weighted, so what Dijkstra gives us back is a COST, not a
# number of hops. A cost of 4 might be one expensive climb into a generic
# ESCO group, or four cheap steps between very specific skills.
#
# Because of that we group the costs into bands instead of giving every
# single number its own percentage. The bands live in config.SIMILARITY_BANDS.

def similarity_from_distance(path_cost):
    """
    Turn a Dijkstra path cost into a similarity percentage.

    What it does : finds the first band in config.SIMILARITY_BANDS that the
                   cost fits into, and returns that band's percentage.
    Inputs       : path_cost - a whole number, or None when there is no path
    Outputs      : a whole number between 0 and 100
    """
    # No path at all in the graph means the two skills are unrelated.
    if path_cost is None:
        return config.SIMILARITY_WHEN_TOO_FAR

    # Walk the bands from cheapest to most expensive and take the first fit.
    for highest_cost_in_band, similarity in config.SIMILARITY_BANDS:
        if path_cost <= highest_cost_in_band:
            return similarity

    # More expensive than every band, so the skills are too far apart.
    return config.SIMILARITY_WHEN_TOO_FAR


def compare_names(first_name, second_name):
    """
    Say how much two skill names look alike, as a number between 0 and 1.

    We only use this to break a tie. Two candidate skills are often exactly
    the same number of hops away from a job description skill. In that case
    we prefer the one whose name looks more like the job description skill,
    because that is the answer a human would expect.

    What it does : compares two pieces of text letter by letter.
    Inputs       : first_name  - a skill name as typed
                   second_name - another skill name as typed
    Outputs      : a number between 0.0 (nothing alike) and 1.0 (identical)
    """
    return difflib.SequenceMatcher(None, first_name.lower(),
                                  second_name.lower()).ratio()


# ---------------------------------------------------------------------------
# Compare one job description skill against all candidate skills
# ---------------------------------------------------------------------------

def find_best_candidate_skill(technology_graph, job_skill_mapping,
                             candidate_skill_mappings):
    """
    Find the candidate skill that is closest to one job description skill.

    We walk through every candidate skill, measure the ESCO distance with
    Dijkstra, and remember the smallest distance we have seen.

    What it does : picks the best matching candidate skill for one JD skill.
    Inputs       : technology_graph         - the ESCO technology graph
                   job_skill_mapping        - one mapping dictionary (from mapping.py)
                                              for a job description skill
                   candidate_skill_mappings - a list of mapping dictionaries
                                              for the candidate skills
    Outputs      : one dictionary describing the match:
                     job_skill        -> what the job description asked for
                     job_esco_label   -> the ESCO name of the JD skill
                     candidate_skill  -> the closest candidate skill (or None)
                     candidate_esco_label -> the ESCO name of that skill (or None)
                     distance         -> the path cost (or None)
                     similarity       -> a percentage between 0 and 100
                     path_uris        -> the shortest path as a list of URIs
                     path_labels      -> the same path as readable ESCO names
                     skipped          -> True when ESCO has no concept for this
                                         JD skill, so it cannot be judged
    """
    # We start with "nothing found yet".
    best_match = {
        "job_skill": job_skill_mapping["typed_skill"],
        "job_esco_label": job_skill_mapping["esco_label"],
        "candidate_skill": None,
        "candidate_esco_label": None,
        "distance": None,
        "similarity": 0,
        "path_uris": [],
        "path_labels": [],
        "skipped": False,
    }

    # If the job description skill is not in ESCO at all, there is nothing to
    # measure. We mark the row as skipped so it stays visible in the table but
    # is left out of the average. Otherwise ESCO's own gaps would punish the
    # candidate: a job asking for Docker would cost every candidate points,
    # even one who has used Docker for ten years.
    if job_skill_mapping["esco_uri"] is None:
        best_match["skipped"] = True
        return best_match

    # Used only to break a tie between two equally close candidate skills.
    best_name_similarity = 0.0

    for candidate_skill_mapping in candidate_skill_mappings:
        # Skip candidate skills that could not be mapped to ESCO.
        if candidate_skill_mapping["esco_uri"] is None:
            continue

        path_uris, distance = find_shortest_path(
            technology_graph,
            job_skill_mapping["esco_uri"],
            candidate_skill_mapping["esco_uri"],
        )

        # No path in the graph means these two skills are not related at all.
        if distance is None:
            continue

        # How much does the candidate skill name look like the JD skill name?
        name_similarity = compare_names(job_skill_mapping["typed_skill"],
                                       candidate_skill_mapping["typed_skill"])

        # Is this candidate skill better than the best one so far?
        # It is better when it is closer in the graph, or when it is
        # exactly as close but has a more similar name.
        is_first_result = best_match["distance"] is None
        is_closer = (not is_first_result) and distance < best_match["distance"]
        is_a_better_tie = (
            (not is_first_result)
            and distance == best_match["distance"]
            and name_similarity > best_name_similarity
        )

        if is_first_result or is_closer or is_a_better_tie:
            best_name_similarity = name_similarity
            best_match["candidate_skill"] = candidate_skill_mapping["typed_skill"]
            best_match["candidate_esco_label"] = candidate_skill_mapping["esco_label"]
            best_match["distance"] = distance
            best_match["similarity"] = similarity_from_distance(distance)
            best_match["path_uris"] = path_uris
            best_match["path_labels"] = [get_label(technology_graph, one_uri)
                                        for one_uri in path_uris]

    return best_match


# ---------------------------------------------------------------------------
# Score one candidate
# ---------------------------------------------------------------------------

def score_candidate(technology_graph, job_skill_mappings,
                   candidate_skill_mappings):
    """
    Score one candidate against the whole job description.

    Every job description skill gets its own row. The overall score is the
    average similarity over all those rows.

    What it does : builds the score table and the average score.
    Inputs       : technology_graph         - the ESCO technology graph
                   job_skill_mappings       - list of mapping dictionaries (JD)
                   candidate_skill_mappings - list of mapping dictionaries (candidate)
    Outputs      : a tuple (match_rows, average_similarity)
                   match_rows is a list of match dictionaries, one per JD skill.
                   average_similarity is a number with one decimal place.
    """
    match_rows = []

    for job_skill_mapping in job_skill_mappings:
        one_match = find_best_candidate_skill(technology_graph,
                                            job_skill_mapping,
                                            candidate_skill_mappings)
        match_rows.append(one_match)

    average_similarity = calculate_average_similarity(match_rows)

    return match_rows, average_similarity


def calculate_average_similarity(match_rows):
    """
    Calculate the average similarity of the matches we were able to judge.

    Rows marked "skipped" are left out completely - they are not counted as a
    zero, and they do not count towards the number we divide by. A JD skill
    that ESCO has never heard of simply cannot be assessed.

    What it does : averages the similarity of the rows that ESCO could judge.
    Inputs       : match_rows - the list of match dictionaries
    Outputs      : the average as a number with one decimal place
                   (0.0 when there is nothing we could judge at all)
    """
    rows_we_could_judge = []
    for one_match in match_rows:
        if not one_match["skipped"]:
            rows_we_could_judge.append(one_match)

    if len(rows_we_could_judge) == 0:
        return 0.0

    total_similarity = 0
    for one_match in rows_we_could_judge:
        total_similarity = total_similarity + one_match["similarity"]

    average_similarity = total_similarity / len(rows_we_could_judge)

    return round(average_similarity, 1)


def count_skipped_skills(match_rows):
    """
    Count how many job description skills could not be judged.

    What it does : counts the rows that were skipped because ESCO has no
                   concept for that JD skill.
    Inputs       : match_rows - the list of match dictionaries
    Outputs      : a whole number
    """
    number_skipped = 0
    for one_match in match_rows:
        if one_match["skipped"]:
            number_skipped = number_skipped + 1

    return number_skipped


def build_path_steps(technology_graph, one_match):
    """
    Break the chosen route into one entry per edge, so it can be inspected.

    This is what makes the score checkable. Instead of only seeing "cost 10",
    you see each step, what kind of ESCO relationship it used, and what that
    step cost.

    What it does : lists every edge of the shortest path with its details.
    Inputs       : technology_graph - the ESCO technology graph
                   one_match        - a match dictionary
    Outputs      : a list of dictionaries, one per edge, each holding
                     from_label      -> the concept we step from
                     to_label        -> the concept we step to
                     relation_type   -> "skill" or "skill_group"
                     esco_type       -> what ESCO calls it in the CSV
                     direction       -> "up to parent" or "down to child"
                     weight          -> what this single step cost
    """
    path_of_uris = one_match["path_uris"]
    path_steps = []

    # A path with one node or none has no edges to describe.
    if len(path_of_uris) < 2:
        return path_steps

    for position in range(len(path_of_uris) - 1):
        this_uri = path_of_uris[position]
        next_uri = path_of_uris[position + 1]
        edge = technology_graph[this_uri][next_uri]

        # Which end of this edge is the parent? That tells us the direction.
        if edge["parent_uri"] == next_uri:
            direction = "up to parent"
        else:
            direction = "down to child"

        path_steps.append({
            "from_label": get_label(technology_graph, this_uri),
            "to_label": get_label(technology_graph, next_uri),
            "relation_type": edge["relation_type"],
            "esco_type": edge["esco_broader_type"],
            "direction": direction,
            "weight": edge["weight"],
        })

    return path_steps


def explain_route(technology_graph, one_match):
    """
    Say in one sentence why the route cost what it did.

    The sentence depends on whether the route managed to stay inside the real
    skill hierarchy, or had to climb into an ESCO education category.

    What it does : writes a short reason for the score.
    Inputs       : technology_graph - the ESCO technology graph
                   one_match        - a match dictionary
    Outputs      : the reason as a string
    """
    if one_match["skipped"]:
        return "ESCO has no concept for this job description skill."

    path_steps = build_path_steps(technology_graph, one_match)

    if len(path_steps) == 0:
        if one_match["distance"] == 0:
            return ("Both skills are names for the very same ESCO concept, so "
                    "there is nothing to travel.")
        return "ESCO has no route between these two concepts at all."

    # Count how many steps used each kind of relationship.
    group_steps = 0
    for one_step in path_steps:
        if one_step["relation_type"] == config.RELATION_TYPE_SKILL_GROUP:
            group_steps = group_steps + 1

    if group_steps == 0:
        return ("The whole route uses real ESCO skill relationships, which is "
                "why it is cheap. ESCO genuinely relates these two skills.")

    if group_steps == len(path_steps):
        return ("The only connection is through an ESCO education category. "
                "ESCO does not relate these two skills directly - it just "
                "files them in the same part of the classification, which is "
                "why the cost is high.")

    return ("Part of the route uses real skill relationships, but it still had "
            "to pass through an ESCO education category, which is expensive.")


def describe_relationship(technology_graph, one_match):
    """
    Say in plain words HOW the two skills are related in ESCO.

    These are the standard names used for taxonomies and thesauri. ESCO is
    published as SKOS, and SKOS calls the two directions "broader" and
    "narrower", which is where the wording comes from:

      same concept          both typed words are names for ONE ESCO concept
      narrower term (child) the candidate skill sits directly under the JD skill
      broader term (parent) the candidate skill sits directly above it
      sibling terms         both hang under the SAME parent
      cousin terms          related only through a higher up shared concept
      unrelated             no route between them at all
      not in ESCO           the JD skill is not in ESCO, so it was skipped

    The shared concept we return is what the research literature calls the
    "least common subsumer" - the lowest concept that covers both skills. It
    is the single most useful thing for explaining a score, because it says
    what the two skills actually have in common.

    What it does : classifies one match and finds the shared concept.
    Inputs       : technology_graph - the ESCO technology graph
                   one_match        - a match dictionary
    Outputs      : a tuple (relationship_name, shared_concept_label)
                   shared_concept_label is "" when there is nothing to name
    """
    if one_match["skipped"]:
        return "not in ESCO", ""

    path_of_uris = one_match["path_uris"]

    if len(path_of_uris) == 0:
        return "unrelated", ""

    if len(path_of_uris) == 1:
        return "same concept", ""

    # Walk the route and note whether each step climbs UP to a parent or
    # goes DOWN to a child. Every edge remembers which end was the parent,
    # so we do not have to guess.
    steps_going_up = 0
    steps_going_down = 0
    highest_point_uri = path_of_uris[0]

    for position in range(len(path_of_uris) - 1):
        this_uri = path_of_uris[position]
        next_uri = path_of_uris[position + 1]
        parent_uri = technology_graph[this_uri][next_uri]["parent_uri"]

        if parent_uri == next_uri:
            steps_going_up = steps_going_up + 1
            # We are still climbing, so this is the highest point so far.
            highest_point_uri = next_uri
        else:
            steps_going_down = steps_going_down + 1

    # Never went down: the candidate skill is above the JD skill.
    if steps_going_down == 0:
        if steps_going_up == 1:
            return "broader term (parent)", ""
        return "broader, " + str(steps_going_up) + " levels up", ""

    # Never went up: the candidate skill is below the JD skill.
    if steps_going_up == 0:
        if steps_going_down == 1:
            return "narrower term (child)", ""
        return "narrower, " + str(steps_going_down) + " levels down", ""

    # Went up and then down, so the turning point is the shared concept.
    shared_concept_label = get_label(technology_graph, highest_point_uri)

    if steps_going_up == 1 and steps_going_down == 1:
        return "sibling terms", shared_concept_label

    return "cousin terms", shared_concept_label


def build_path_text(one_match):
    """
    Write the shortest path as one readable line of text.

    Example: "FastAPI -> software frameworks -> Flask"

    What it does : joins the ESCO labels of the path with arrows.
    Inputs       : one_match - a match dictionary from find_best_candidate_skill()
    Outputs      : the path as a string ("no path found" when there is none)
    """
    if len(one_match["path_labels"]) == 0:
        return "no path found"

    return "  ->  ".join(one_match["path_labels"])
