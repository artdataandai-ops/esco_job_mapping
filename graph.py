"""
graph.py
========

This file builds ONE weighted technology ESCO graph and keeps it in memory.

The important idea
------------------
The graph is weighted, but the weights are NOT distances.
A weight is the COST of walking along one edge, and the cost says how much
MEANING you lose by taking that step.

  * Stepping between two very specific concepts is cheap.
        Docker  ->  Jenkins                        cost 1
  * Climbing up to a very generic concept is expensive.
        software development  ->  ICT              cost 8

Dijkstra always picks the cheapest route, so it naturally prefers to stay
among specific technical concepts instead of taking a shortcut through a huge
generic group. That is exactly the behaviour we want for skill matching.

All the numbers live in config.py, so nothing is hardcoded here.

Run this file on its own to check the graph was built correctly:

    python graph.py
"""

import networkx as nx
import pandas as pd

import config

# ---------------------------------------------------------------------------
# Step 1: read the three ESCO files
# ---------------------------------------------------------------------------

def load_skills_table():
    """
    Read skills_en.csv into a pandas DataFrame.

    What it does : loads every ESCO skill from disk.
    Inputs       : nothing (the file path comes from config.py)
    Outputs      : a DataFrame with the columns
                   conceptUri, preferredLabel, altLabels, description
    """
    skills_table = pd.read_csv(config.SKILLS_FILE)

    # Keep only the few columns this project needs. Fewer columns is easier to
    # read. Note there are TWO columns of extra names:
    #   altLabels    - synonyms ESCO shows to people
    #   hiddenLabels - synonyms ESCO keeps for searching only, such as "aws",
    #                  "react", "ubuntu". Both are official ESCO data.
    return skills_table[["conceptUri", "preferredLabel", "altLabels",
                        "hiddenLabels", "description"]]


def load_broader_relations_table():
    """
    Read broaderRelationsSkillPillar_en.csv into a pandas DataFrame.

    Each row says "concept X sits inside the broader concept Y".
    These rows become the edges of our graph.

    What it does : loads every parent/child relation from disk.
    Inputs       : nothing (the file path comes from config.py)
    Outputs      : a DataFrame with the columns
                   conceptUri, conceptLabel, broaderUri, broaderLabel
    """
    relations_table = pd.read_csv(config.BROADER_RELATIONS_FILE)

    # "broaderType" is the important one. It says whether the parent is another
    # real skill, or just an ISCED-F education category. Those two mean very
    # different things and must not be treated the same.
    return relations_table[["conceptUri", "conceptLabel", "broaderUri",
                           "broaderLabel", "broaderType"]]


def load_digital_skill_uris():
    """
    Read digitalSkillsCollection_en.csv and return just the URIs.

    This file is a list ESCO curated by hand of skills that are "digital".
    We only use it as a filter - never to create edges, because it contains
    no skill groups at all.

    What it does : loads the set of digital skill URIs.
    Inputs       : nothing (the file path comes from config.py)
    Outputs      : a Python set of URI strings
    """
    digital_table = pd.read_csv(config.DIGITAL_SKILLS_FILE)

    return set(digital_table["conceptUri"])


# ---------------------------------------------------------------------------
# Step 2: work out which concepts belong in the technology graph
# ---------------------------------------------------------------------------

def build_children_lookup(relations_table):
    """
    Build a dictionary: parent URI -> list of its child URIs.

    What it does : lets us walk DOWN the ESCO tree quickly.
    Inputs       : relations_table - from load_broader_relations_table()
    Outputs      : a dictionary {parent_uri: [child_uri, child_uri, ...]}
    """
    children_of = {}

    for child_uri, parent_uri in zip(relations_table["conceptUri"],
                                     relations_table["broaderUri"]):
        if parent_uri not in children_of:
            children_of[parent_uri] = []
        children_of[parent_uri].append(child_uri)

    return children_of


def build_parents_lookup(relations_table):
    """
    Build a dictionary: child URI -> list of its parent URIs.

    A concept can have SEVERAL parents in ESCO. For example PostgreSQL sits
    under both "database management systems" and under the bigger group
    "database and network design and administration". So this really is a
    list, not a single value.

    What it does : lets us walk UP the ESCO tree quickly.
    Inputs       : relations_table - from load_broader_relations_table()
    Outputs      : a dictionary {child_uri: [parent_uri, parent_uri, ...]}
    """
    parents_of = {}

    for child_uri, parent_uri in zip(relations_table["conceptUri"],
                                     relations_table["broaderUri"]):
        if child_uri not in parents_of:
            parents_of[child_uri] = []
        parents_of[child_uri].append(parent_uri)

    return parents_of


def collect_branch_uris(children_of, root_uri):
    """
    Collect every concept that sits somewhere below one root concept.

    We start at the root and keep walking down to children of children of
    children, until there is nothing left to visit.

    What it does : finds one whole branch of the ESCO tree.
    Inputs       : children_of - the dictionary from build_children_lookup()
                   root_uri    - the URI to start walking from
    Outputs      : a set of URIs, including the root itself
    """
    branch_uris = {root_uri}
    uris_still_to_visit = [root_uri]

    while uris_still_to_visit:
        current_uri = uris_still_to_visit.pop()

        for child_uri in children_of.get(current_uri, []):
            if child_uri not in branch_uris:
                branch_uris.add(child_uri)
                uris_still_to_visit.append(child_uri)

    return branch_uris


def find_technology_skill_uris(skills_table, children_of):
    """
    Decide which ESCO skills are technology skills.

    A skill is kept when BOTH rules are true:
      rule 1 - it sits under one of the technology branches in config.py
      rule 2 - it also appears in digitalSkillsCollection_en.csv

    Neither rule is clean on its own. Rule 1 alone lets in misfiled ESCO
    entries like "operate nail gun". Rule 2 alone lets in digital-but-not-IT
    skills like "assemble robots". Together they give a clean subset.

    A short list of exceptions from config.py is added back at the end.

    What it does : chooses the technology skills for the graph.
    Inputs       : skills_table - from load_skills_table()
                   children_of  - from build_children_lookup()
    Outputs      : a set of technology skill URIs
    """
    # Rule 1: everything below the technology roots.
    uris_inside_branches = set()
    for root_uri in config.TECHNOLOGY_BRANCH_ROOT_URIS:
        uris_inside_branches.update(collect_branch_uris(children_of, root_uri))

    # Rule 2: everything ESCO marked as a digital skill.
    digital_skill_uris = load_digital_skill_uris()

    # Keep only what satisfies both rules.
    technology_skill_uris = uris_inside_branches & digital_skill_uris

    # Add the handful of exceptions back in, looked up by their label.
    uri_of_label = dict(zip(skills_table["preferredLabel"],
                           skills_table["conceptUri"]))

    for label_to_keep in config.EXTRA_SKILL_LABELS_TO_KEEP:
        if label_to_keep in uri_of_label:
            technology_skill_uris.add(uri_of_label[label_to_keep])

    return technology_skill_uris


def add_connecting_group_uris(technology_skill_uris, parents_of, children_of):
    """
    Add back the ESCO groups that hold the technology skills together.

    This step is easy to forget and the graph does not work without it.
    digitalSkillsCollection_en.csv contains skills only - not one single
    group. But in ESCO a skill's parent is almost always a group. If we drop
    the groups, the skills end up as hundreds of disconnected islands and
    there is no ladder for Dijkstra to climb.

    So for every technology skill we walk upwards and keep its groups too,
    as long as they are still inside the technology branches.

    What it does : adds the structural group nodes to the node set.
    Inputs       : technology_skill_uris - from find_technology_skill_uris()
                   parents_of            - from build_parents_lookup()
                   children_of           - from build_children_lookup()
    Outputs      : a set with the skills AND their groups
    """
    # Work out the branches once more so we never wander outside technology.
    uris_inside_branches = set()
    for root_uri in config.TECHNOLOGY_BRANCH_ROOT_URIS:
        uris_inside_branches.update(collect_branch_uris(children_of, root_uri))

    all_graph_uris = set(technology_skill_uris)
    uris_still_to_visit = list(technology_skill_uris)

    while uris_still_to_visit:
        current_uri = uris_still_to_visit.pop()

        for parent_uri in parents_of.get(current_uri, []):
            is_inside_technology = parent_uri in uris_inside_branches
            is_new = parent_uri not in all_graph_uris

            if is_inside_technology and is_new:
                all_graph_uris.add(parent_uri)
                uris_still_to_visit.append(parent_uri)

    return all_graph_uris


# ---------------------------------------------------------------------------
# Step 3: depth, which is how we measure "how generic is this concept"
# ---------------------------------------------------------------------------

def calculate_node_depths(graph):
    """
    Work out how deep every node sits in the technology tree.

    Depth 0 is a root concept (the most generic). The bigger the number, the
    more specific the concept. When a concept can be reached by more than one
    route we keep the SHORTEST one, because that is its highest position in
    the tree.

    What it does : measures how generic or specific every node is.
    Inputs       : graph - a NetworkX graph that already has all its edges
    Outputs      : a dictionary {uri: depth as a whole number}
    """
    depth_of_node = {}

    for root_uri in config.TECHNOLOGY_BRANCH_ROOT_URIS:
        # A root that ended up outside the graph has nothing to measure.
        if root_uri not in graph:
            continue

        # This counts plain steps from the root, ignoring weights on purpose.
        # Depth is about POSITION in the tree, not about cost.
        steps_from_root = nx.single_source_shortest_path_length(graph, root_uri)

        for node_uri, number_of_steps in steps_from_root.items():
            if node_uri not in depth_of_node:
                depth_of_node[node_uri] = number_of_steps
            else:
                depth_of_node[node_uri] = min(depth_of_node[node_uri],
                                             number_of_steps)

    return depth_of_node


def translate_relation_type(esco_broader_type):
    """
    Translate ESCO's "broaderType" column into our own two names.

    What it does : turns "KnowledgeSkillCompetence" into "skill" and
                   "SkillGroup" into "skill_group".
    Inputs       : esco_broader_type - the value from the CSV column
    Outputs      : one of config.RELATION_TYPE_SKILL or
                   config.RELATION_TYPE_SKILL_GROUP
    """
    if esco_broader_type == config.ESCO_BROADER_TYPE_GROUP:
        return config.RELATION_TYPE_SKILL_GROUP

    return config.RELATION_TYPE_SKILL


def get_edge_weight(relation_type, parent_uri, depth_of_node):
    """
    Decide what one edge should cost.

    Two things decide it, and the relationship type matters most:

      a SKILL edge          ->  cost 1
          "Python is a kind of computer programming"
          A real statement about the two skills, so it is cheap to walk.

      a SKILL_GROUP edge    ->  cost 5, 8 or 12 depending on the group's depth
          "Python is filed under software and applications development"
          Only a filing decision. That group holds 161 unrelated concepts, so
          walking through it should be expensive.

    Because group edges are dear, Dijkstra will automatically prefer a route
    made of real skill relationships whenever one exists, and only climb into
    the education categories when there is no alternative.

    All the numbers live in config.py.

    What it does : looks up the cost of one edge.
    Inputs       : relation_type - "skill" or "skill_group"
                   parent_uri    - the more generic end of the edge
                   depth_of_node - from calculate_node_depths()
    Outputs      : the weight as a whole number
    """
    # A genuine skill relationship always costs the same small amount.
    if relation_type == config.RELATION_TYPE_SKILL:
        return config.SKILL_EDGE_WEIGHT

    # An education category costs more, and more still near the top of the tree.
    depth_of_parent = depth_of_node.get(parent_uri)

    if depth_of_parent is None:
        return config.DEFAULT_SKILL_GROUP_EDGE_WEIGHT

    return config.SKILL_GROUP_EDGE_WEIGHT_BY_DEPTH.get(
        depth_of_parent, config.DEFAULT_SKILL_GROUP_EDGE_WEIGHT)


# ---------------------------------------------------------------------------
# Step 4: build the graph
# ---------------------------------------------------------------------------

def build_technology_graph():
    """
    Build the one and only weighted technology graph.

    The graph is undirected on purpose. To see that Python and Java are
    related you have to walk UP from Python to "computer programming" and then
    back DOWN to Java. A one-way parent-to-child graph makes that second step
    impossible, so every comparison would fail.
    The original direction is not lost - each edge records which end was the
    parent, in the "parent_uri" attribute.

    What it does : reads the ESCO files and produces the finished graph.
    Inputs       : nothing
    Outputs      : a NetworkX Graph where
                     every node has  label, alternative_labels, description, depth
                     every edge has  weight, relation_type, parent_uri
    """
    skills_table = load_skills_table()
    relations_table = load_broader_relations_table()

    children_of = build_children_lookup(relations_table)
    parents_of = build_parents_lookup(relations_table)

    # --- decide which concepts are allowed in -----------------------------
    technology_skill_uris = find_technology_skill_uris(skills_table, children_of)
    all_graph_uris = add_connecting_group_uris(technology_skill_uris,
                                              parents_of, children_of)

    # --- add the edges ----------------------------------------------------
    technology_graph = nx.Graph()

    for child_uri, child_label, parent_uri, parent_label, esco_broader_type in zip(
        relations_table["conceptUri"],
        relations_table["conceptLabel"],
        relations_table["broaderUri"],
        relations_table["broaderLabel"],
        relations_table["broaderType"],
    ):
        # An edge is only created when BOTH ends are in our technology subset.
        if child_uri in all_graph_uris and parent_uri in all_graph_uris:
            technology_graph.add_node(child_uri, label=child_label)
            technology_graph.add_node(parent_uri, label=parent_label)

            # Remember WHICH KIND of relationship this is. The weight below
            # depends on it, and so does the explanation shown to the user.
            technology_graph.add_edge(
                child_uri, parent_uri,
                relation_type=translate_relation_type(esco_broader_type),
                esco_broader_type=esco_broader_type,
                parent_uri=parent_uri)

    # --- now that the shape is known, measure depth and set the weights ---
    # This has to happen after the edges exist, because depth is worked out by
    # walking the finished tree.
    depth_of_node = calculate_node_depths(technology_graph)

    for node_uri in technology_graph.nodes:
        technology_graph.nodes[node_uri]["depth"] = depth_of_node.get(node_uri, -1)

    for first_uri, second_uri in technology_graph.edges:
        edge = technology_graph[first_uri][second_uri]
        edge["weight"] = get_edge_weight(edge["relation_type"],
                                        edge["parent_uri"], depth_of_node)

    # --- finally copy the labels and descriptions onto the nodes ----------
    add_skill_details_to_nodes(technology_graph, skills_table)

    return technology_graph


def add_skill_details_to_nodes(technology_graph, skills_table):
    """
    Copy the alternative labels and the description onto every node.

    ESCO stores all the alternative names of a skill inside ONE cell,
    separated by line breaks, so we split them into a proper list.

    What it does : fills in the extra node information.
    Inputs       : technology_graph - the graph being built
                   skills_table     - from load_skills_table()
    Outputs      : nothing, it changes the graph in place
    """
    # Give every node a sensible empty value first, so no node is missing a key.
    for node_uri in technology_graph.nodes:
        technology_graph.nodes[node_uri].setdefault("alternative_labels", [])
        technology_graph.nodes[node_uri].setdefault("description", "")

    for concept_uri, alternative_labels, description in zip(
        skills_table["conceptUri"],
        skills_table["altLabels"],
        skills_table["description"],
    ):
        if concept_uri not in technology_graph:
            continue

        # Empty cells arrive from pandas as NaN, which is not a string.
        if isinstance(alternative_labels, str):
            split_labels = []
            for one_label in alternative_labels.split("\n"):
                if one_label.strip() != "":
                    split_labels.append(one_label.strip())
            technology_graph.nodes[concept_uri]["alternative_labels"] = split_labels

        if isinstance(description, str):
            technology_graph.nodes[concept_uri]["description"] = description


# ---------------------------------------------------------------------------
# Step 5: helpers the rest of the application uses
# ---------------------------------------------------------------------------

def build_label_lookup(technology_graph):
    """
    Build a dictionary that maps an ESCO label to its ESCO URI.

    What it does : creates a label -> uri translation table.
    Inputs       : technology_graph - from build_technology_graph()
    Outputs      : a dictionary {esco_label: esco_uri}
    """
    label_to_uri = {}

    for concept_uri in technology_graph.nodes:
        label_to_uri[technology_graph.nodes[concept_uri]["label"]] = concept_uri

    return label_to_uri


def find_shortest_path(technology_graph, start_uri, end_uri):
    """
    Find the cheapest path between two ESCO concepts using Dijkstra.

    Note the word CHEAPEST, not shortest. Dijkstra adds up the edge weights,
    so a route made of three cheap specific steps can beat a route made of
    one expensive climb through a generic group. That is the whole point of
    the weights.

    What it does : runs Dijkstra's algorithm on the weighted graph.
    Inputs       : technology_graph - from build_technology_graph()
                   start_uri        - ESCO URI to start from
                   end_uri          - ESCO URI to end at
    Outputs      : a tuple (path_of_uris, total_cost)
                   or (None, None) when the two concepts are not connected
    """
    if start_uri not in technology_graph or end_uri not in technology_graph:
        return None, None

    try:
        path_of_uris = nx.dijkstra_path(technology_graph, start_uri, end_uri,
                                       weight="weight")
        total_cost = nx.dijkstra_path_length(technology_graph, start_uri,
                                            end_uri, weight="weight")
    except nx.NetworkXNoPath:
        return None, None

    # Dijkstra returns a float such as 4.0, so make it a whole number.
    return path_of_uris, int(total_cost)


def get_label(technology_graph, concept_uri):
    """
    Look up the readable ESCO label of one node.

    What it does : translates an ESCO URI into its human readable name.
    Inputs       : technology_graph - from build_technology_graph()
                   concept_uri      - one ESCO URI
    Outputs      : the label as a string (or the URI when it is unknown)
    """
    if concept_uri in technology_graph:
        return technology_graph.nodes[concept_uri]["label"]

    return concept_uri


# ---------------------------------------------------------------------------
# Verification - run "python graph.py" to check the graph looks right
# ---------------------------------------------------------------------------

def print_graph_report(technology_graph):
    """
    Print a short report so we can see the graph was built correctly.

    What it does : prints totals, then a few sample nodes and edges.
    Inputs       : technology_graph - from build_technology_graph()
    Outputs      : nothing, it only prints
    """
    skills_table = load_skills_table()
    all_skill_uris = set(skills_table["conceptUri"])

    # A node is a "skill" when it appears in skills_en.csv. Everything else is
    # one of the ESCO groups we added to hold the skills together.
    skill_nodes = [n for n in technology_graph.nodes if n in all_skill_uris]
    group_nodes = [n for n in technology_graph.nodes if n not in all_skill_uris]

    print("ESCO version               :", config.ESCO_VERSION)
    print("Total ESCO skills in file  :", len(all_skill_uris))
    print("Technology skills kept     :", len(skill_nodes))
    print("Connecting group nodes     :", len(group_nodes))
    print("Total graph nodes          :", technology_graph.number_of_nodes())
    print("Total graph edges          :", technology_graph.number_of_edges())
    print("Separate pieces (should be 1):",
          nx.number_connected_components(technology_graph))

    print()
    print("Edges by relationship type and cost")
    counts = {}
    for _, _, edge_data in technology_graph.edges(data=True):
        key = (edge_data["relation_type"], edge_data["weight"])
        counts[key] = counts.get(key, 0) + 1
    for relation_type, one_weight in sorted(counts):
        print("   " + relation_type.ljust(12) + " cost " + str(one_weight).rjust(2)
              + "  ->  " + str(counts[(relation_type, one_weight)]) + " edges")

    uri_of_label = build_label_lookup(technology_graph)

    print()
    print("Sample nodes")
    for label in config.SAMPLE_SKILL_LABELS_FOR_REPORT:
        if label not in uri_of_label:
            print("   " + label + "  -- NOT IN THE GRAPH")
            continue
        node = technology_graph.nodes[uri_of_label[label]]
        print("   " + node["label"])
        print("      uri   :", uri_of_label[label])
        print("      depth :", node["depth"], " (bigger means more specific)")
        print("      alt   :", node["alternative_labels"][:3])

    print()
    print("Sample edges (child -> parent, and what that one step costs)")
    # Show one real example of every weight the graph uses, cheapest first.
    already_shown_weights = set()
    for first_uri, second_uri, edge_data in technology_graph.edges(data=True):
        one_weight = edge_data["weight"]
        if one_weight in already_shown_weights:
            continue
        already_shown_weights.add(one_weight)

        parent_uri = edge_data["parent_uri"]
        child_uri = second_uri if parent_uri == first_uri else first_uri
        print("   weight " + str(one_weight) + "  "
              + get_label(technology_graph, child_uri)
              + "  ->  " + get_label(technology_graph, parent_uri))

    print()
    print("Sample comparisons (the cheapest route Dijkstra found)")
    for first_label, second_label in config.SAMPLE_PAIRS_FOR_REPORT:
        if first_label not in uri_of_label or second_label not in uri_of_label:
            print("   " + first_label + " / " + second_label + "  -- NOT IN THE GRAPH")
            continue

        path_of_uris, total_cost = find_shortest_path(technology_graph,
                                                     uri_of_label[first_label],
                                                     uri_of_label[second_label])
        if path_of_uris is None:
            print("   cost   -  " + first_label + "  /  " + second_label
                  + "   (not connected)")
            continue

        route = "  ->  ".join(get_label(technology_graph, one_uri)
                             for one_uri in path_of_uris)
        print("   cost " + str(total_cost).rjust(2) + "   " + route)


if __name__ == "__main__":
    print("Building the weighted technology ESCO graph ...")
    print()
    print_graph_report(build_technology_graph())
