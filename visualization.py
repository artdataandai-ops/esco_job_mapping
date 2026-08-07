"""
visualization.py
================

This file draws the small explanation graph with PyVis.

We do NOT draw the whole ESCO technology graph. That would be a hairball
of hundreds of nodes and nobody could read it.

Instead we draw only what was used while scoring one candidate:

  * the job description skills          -> GREEN
  * the candidate skills                -> BLUE
  * the ESCO nodes in between them      -> YELLOW

Every path found during scoring becomes a chain of nodes. The typed words are
shown on the boxes, and the real ESCO concepts they resolved to are shown
underneath, for example:

    FastAPI                 software and applications      Flask
    (web services)     ->   development and analysis  ->   (web programming)

Note that "FastAPI" and "Flask" are not ESCO concepts - ESCO has no entry for
either of them. They are typed words that mapping.py resolved onto the two
real ESCO concepts shown in brackets.
"""

from pyvis.network import Network

import config

# The three colours of the demo. Keeping them here makes them easy to change.
COLOUR_JOB_DESCRIPTION_SKILL = "#4CAF50"   # green
COLOUR_CANDIDATE_SKILL = "#2196F3"         # blue
COLOUR_INTERMEDIATE_NODE = "#FFC107"       # yellow

# The three kinds of edge are drawn differently, because they mean very
# different things. A real hierarchy skill relationship is a solid dark
# green line. ESCO's own curated skill-to-skill link is a solid blue line -
# just as cheap, but it did not come from the hierarchy at all. An education
# category is a faint dashed line, because it is a weak connection.
COLOUR_SKILL_EDGE = "#2E7D32"           # dark green, solid
COLOUR_SKILL_GROUP_EDGE = "#B0A9A0"     # faint grey, dashed
COLOUR_SKILL_RELATION_EDGE = "#1565C0"  # blue, solid


def describe_edge_for_drawing(technology_graph, first_uri, second_uri):
    """
    Work out how one edge should look and what text to write on it.

    What it does : reads the relationship type and cost off the graph edge and
                   turns them into drawing instructions.
    Inputs       : technology_graph - the ESCO technology graph
                   first_uri        - one end of the edge
                   second_uri       - the other end
    Outputs      : a dictionary of PyVis edge settings
                   (label, title, color, dashes, width)
    """
    edge = technology_graph[first_uri][second_uri]
    relation_type = edge["relation_type"]
    weight = edge["weight"]

    is_education_category = (relation_type == config.RELATION_TYPE_SKILL_GROUP)
    is_skill_relation = (relation_type == config.RELATION_TYPE_SKILL_RELATION)

    # The short text drawn next to the line.
    if is_education_category:
        label = "group  " + str(weight)
        colour = COLOUR_SKILL_GROUP_EDGE
    elif is_skill_relation:
        label = "related  " + str(weight)
        colour = COLOUR_SKILL_RELATION_EDGE
    else:
        label = "skill  " + str(weight)
        colour = COLOUR_SKILL_EDGE

    # The longer text shown when you hover over the line.
    title = ("relationship: " + relation_type
             + "\nESCO type: " + edge["esco_broader_type"]
             + "\ncost of this step: " + str(weight))

    if is_education_category:
        title = title + "\n\nThis is only an ESCO education category, not a"
        title = title + "\nreal relationship between the two skills, so it"
        title = title + "\nis expensive to travel through."
    elif is_skill_relation:
        title = title + "\n\nThis comes from ESCO's own curated skill-to-skill"
        title = title + "\ndata, not the hierarchy, so it is cheap to travel"
        title = title + "\nthrough even though the two skills sit in"
        title = title + "\ndifferent branches of the tree."
    else:
        title = title + "\n\nThis is a real ESCO skill relationship, so it"
        title = title + "\nis cheap to travel through."

    return {
        "label": label,
        "title": title,
        "color": colour,
        "dashes": is_education_category,
        "width": 1 if is_education_category else 3,
    }


def build_explanation_graph_html(technology_graph, match_rows, candidate_name):
    """
    Build the interactive PyVis graph for one scored candidate.

    What it does : creates a small graph from the shortest paths and returns
                   it as a ready to display HTML page. Every line is labelled
                   with the kind of ESCO relationship it is and what it cost.
    Inputs       : technology_graph - the ESCO technology graph
                   match_rows       - the list of match dictionaries produced by
                                      scoring.score_candidate()
                   candidate_name   - the name of the candidate, for tooltips
    Outputs      : the graph as one HTML string
    """
    # cdn_resources="in_line" writes the drawing library straight into the
    # HTML, so the graph also works without an internet connection.
    pyvis_graph = Network(height="520px", width="100%", bgcolor="#ffffff",
                         font_color="#222222", cdn_resources="in_line")

    # A gentle physics layout so the nodes spread out and stay readable.
    pyvis_graph.barnes_hut(gravity=-8000, spring_length=180)

    # ---------------------------------------------------------------------
    # Pass 1: add the two ends of every path (the skills people typed)
    # ---------------------------------------------------------------------
    #
    # A job description skill and a candidate skill can be the very same
    # ESCO concept (for example both sides typed "Python"). We still want to
    # SEE two nodes, one green and one blue, so we give them different ids
    # by putting "JD::" or "CAND::" in front of the ESCO URI.

    for one_match in match_rows:
        # Skip rows where scoring found nothing to draw.
        if len(one_match["path_uris"]) == 0:
            continue

        job_skill_uri = one_match["path_uris"][0]
        candidate_skill_uri = one_match["path_uris"][-1]

        pyvis_graph.add_node(
            "JD::" + job_skill_uri,
            label=build_node_label(one_match["job_skill"],
                                  one_match["job_esco_label"]),
            color=COLOUR_JOB_DESCRIPTION_SKILL,
            shape="box",
            title="Job description skill: " + one_match["job_skill"]
                  + "\nESCO skill: " + one_match["job_esco_label"],
        )

        pyvis_graph.add_node(
            "CAND::" + candidate_skill_uri,
            label=build_node_label(one_match["candidate_skill"],
                                  one_match["candidate_esco_label"]),
            color=COLOUR_CANDIDATE_SKILL,
            shape="box",
            title=candidate_name + " skill: " + one_match["candidate_skill"]
                  + "\nESCO skill: " + one_match["candidate_esco_label"],
        )

    # ---------------------------------------------------------------------
    # Pass 2: add the nodes in between, and all the edges
    # ---------------------------------------------------------------------

    for one_match in match_rows:
        if len(one_match["path_uris"]) == 0:
            continue

        # When the distance is 0 both sides are the very same ESCO concept,
        # so the path has only one URI in it. We then simply draw the green
        # node next to the blue node and connect the two.
        if len(one_match["path_uris"]) == 1:
            only_uri = one_match["path_uris"][0]
            # There is no ESCO edge here at all, so we label it for what it is.
            pyvis_graph.add_edge(
                "JD::" + only_uri, "CAND::" + only_uri,
                label="same concept  0",
                title="Both skills are names for the very same ESCO concept,"
                      "\nso nothing had to be travelled. Cost 0.",
                color=COLOUR_SKILL_EDGE,
                width=3,
            )
            continue

        # Translate every URI of the path into the id we want to draw.
        node_ids_of_this_path = []

        for position, one_uri in enumerate(one_match["path_uris"]):
            is_first_node = (position == 0)
            is_last_node = (position == len(one_match["path_uris"]) - 1)

            if is_first_node:
                node_ids_of_this_path.append("JD::" + one_uri)
            elif is_last_node:
                node_ids_of_this_path.append("CAND::" + one_uri)
            else:
                # A node in the middle of the path.
                # If this ESCO concept is already drawn as a green or blue
                # node we reuse that node instead of drawing a duplicate.
                node_id = pick_existing_node_id(pyvis_graph, one_uri)
                node_ids_of_this_path.append(node_id)

                if node_id == one_uri:
                    pyvis_graph.add_node(
                        one_uri,
                        label=one_match["path_labels"][position],
                        color=COLOUR_INTERMEDIATE_NODE,
                        shape="ellipse",
                        title="ESCO concept used to connect the two skills",
                    )

        # Now connect the chain: node 0 to node 1, node 1 to node 2, and so on.
        # Each line is labelled with the real ESCO relationship it came from,
        # which we look up using the ORIGINAL uris, not the drawing ids.
        for position in range(len(node_ids_of_this_path) - 1):
            edge_settings = describe_edge_for_drawing(
                technology_graph,
                one_match["path_uris"][position],
                one_match["path_uris"][position + 1],
            )

            pyvis_graph.add_edge(node_ids_of_this_path[position],
                                node_ids_of_this_path[position + 1],
                                **edge_settings)

    return pyvis_graph.generate_html(notebook=False)


def build_node_label(typed_skill, esco_label):
    """
    Build the text shown inside a green or blue box.

    We show the word the person actually typed on the first line, because
    that is what they recognise. When ESCO calls the skill something else we
    add the ESCO name on a second line, so it is clear which concept the
    graph is really using.

    Example: "Docker" and "tools for software configuration management"
             become two lines:
                 Docker
                 (tools for software configuration management)

    What it does : joins the typed skill and the ESCO name into a label.
    Inputs       : typed_skill - the skill as the user typed it
                   esco_label  - the ESCO name it was mapped to
    Outputs      : the label as a string (it may contain a line break)
    """
    # When the two names are the same there is no point repeating them.
    if typed_skill.strip().lower() == esco_label.lower():
        return esco_label

    return typed_skill + "\n(" + esco_label + ")"


def pick_existing_node_id(pyvis_graph, esco_uri):
    """
    Decide which node id to use for an ESCO concept in the middle of a path.

    What it does : reuses an already drawn green or blue node when possible,
                   so the same ESCO concept is never drawn twice.
    Inputs       : pyvis_graph - the PyVis network we are building
                   esco_uri    - the ESCO URI of the concept
    Outputs      : the node id to use, as a string
    """
    already_drawn_node_ids = pyvis_graph.get_nodes()

    if "JD::" + esco_uri in already_drawn_node_ids:
        return "JD::" + esco_uri

    if "CAND::" + esco_uri in already_drawn_node_ids:
        return "CAND::" + esco_uri

    # Nothing drawn yet, so use the plain URI (this becomes a yellow node).
    return esco_uri
