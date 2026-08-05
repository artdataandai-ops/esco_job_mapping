"""
app.py
======

A small Streamlit demo that explains how candidate scoring works with the
ESCO Knowledge Graph.

The screen has exactly four sections:

  1. Enter Job Description Skills
  2. Add Candidates
  3. Map Skills
  4. Score Candidate

Run the demo with:

    streamlit run app.py
"""

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from graph import build_technology_graph
from mapping import build_mapping_index, map_skill_list_to_esco, shorten_uri
from scoring import (build_path_steps, build_path_text, count_skipped_skills,
                     describe_relationship, explain_route, score_candidate)
from visualization import build_explanation_graph_html

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="ESCO Technology Skill Scoring Demo",
                  layout="wide")

st.title("ESCO Technology Skill Scoring Demo")
st.write(
    "This demo shows how two skills that are spelled differently can still "
    "be a good match, because ESCO knows how technology skills are related "
    "to each other."
)


# ---------------------------------------------------------------------------
# Load the ESCO technology graph exactly once
# ---------------------------------------------------------------------------

@st.cache_resource
def load_graph_and_index():
    """
    Build the ESCO technology graph and the mapping index one single time.

    Streamlit re-runs this whole file on every click. The @st.cache_resource
    decorator tells Streamlit: "run this function only the first time and
    keep the result in memory afterwards".

    What it does : builds the one graph the whole application uses.
    Inputs       : nothing
    Outputs      : a tuple (technology_graph, mapping_index)
    """
    technology_graph = build_technology_graph()
    mapping_index = build_mapping_index(technology_graph)

    return technology_graph, mapping_index


with st.spinner("Loading the ESCO technology graph ..."):
    technology_graph, mapping_index = load_graph_and_index()

st.caption(
    "Technology graph loaded: "
    + str(technology_graph.number_of_nodes()) + " ESCO concepts and "
    + str(technology_graph.number_of_edges()) + " relations."
)


# ---------------------------------------------------------------------------
# Remember what the user typed, even after a button click
# ---------------------------------------------------------------------------
#
# st.session_state is a dictionary that survives between clicks.
# We store two things in it:
#   job_description_skills -> a list of strings
#   candidates             -> a list of dictionaries {name, skills}

if "job_description_skills" not in st.session_state:
    st.session_state.job_description_skills = []

if "candidates" not in st.session_state:
    st.session_state.candidates = []


# ===========================================================================
# SECTION 1 - Enter Job Description Skills
# ===========================================================================

st.header("1. Enter Job Description Skills")

with st.form("job_description_skill_form", clear_on_submit=True):
    typed_job_skill = st.text_input("Job description skill",
                                   placeholder="for example: Python")
    job_skill_was_added = st.form_submit_button("Add skill")

if job_skill_was_added and typed_job_skill.strip() != "":
    st.session_state.job_description_skills.append(typed_job_skill.strip())

if len(st.session_state.job_description_skills) == 0:
    st.info("No job description skills yet. Add them one by one.")
else:
    st.write("**Job description skills**")
    for one_job_skill in st.session_state.job_description_skills:
        st.write("- " + one_job_skill)

    if st.button("Clear job description skills"):
        st.session_state.job_description_skills = []
        st.rerun()


# ===========================================================================
# SECTION 2 - Add Candidates
# ===========================================================================

st.header("2. Add Candidates")

with st.form("candidate_form", clear_on_submit=True):
    typed_candidate_name = st.text_input("Candidate name",
                                       placeholder="for example: John")
    typed_candidate_skills = st.text_area(
        "Candidate skills (one skill per line)",
        placeholder="Python\nFlask\nDocker\nAzure",
        height=140,
    )
    candidate_was_added = st.form_submit_button("Add candidate")

if candidate_was_added and typed_candidate_name.strip() != "":
    # Turn the text area into a clean list of skills, one per line.
    candidate_skill_list = []
    for one_line in typed_candidate_skills.split("\n"):
        if one_line.strip() != "":
            candidate_skill_list.append(one_line.strip())

    st.session_state.candidates.append({
        "name": typed_candidate_name.strip(),
        "skills": candidate_skill_list,
    })

if len(st.session_state.candidates) == 0:
    st.info("No candidates yet. Add a name and a list of skills.")
else:
    # Show every candidate in its own card, side by side.
    candidate_columns = st.columns(len(st.session_state.candidates))

    for column, one_candidate in zip(candidate_columns,
                                    st.session_state.candidates):
        with column:
            with st.container(border=True):
                st.subheader(one_candidate["name"])
                for one_candidate_skill in one_candidate["skills"]:
                    st.write("- " + one_candidate_skill)

    if st.button("Clear candidates"):
        st.session_state.candidates = []
        st.rerun()


# ===========================================================================
# SECTION 3 - Map Skills
# ===========================================================================

st.header("3. Map Skills")
st.write(
    "Every skill that was typed is mapped to a real ESCO technology skill. "
    "This is the step that makes the graph search possible."
)


def show_mapping_results(title, mapping_results):
    """
    Show one mapping block on the screen.

    What it does : prints "typed skill -> ESCO label -> ESCO URI" as a table.
    Inputs       : title           - the heading to show above the table
                   mapping_results - the list of mapping dictionaries
    Outputs      : nothing, it only draws on the screen
    """
    st.write("**" + title + "**")

    if len(mapping_results) == 0:
        st.write("Nothing to map.")
        return

    # Build a small table so the three steps are easy to read.
    table_rows = []
    for one_mapping in mapping_results:
        table_rows.append({
            "Original Skill": one_mapping["typed_skill"],
            "ESCO Label": one_mapping["esco_label"] or "not found in ESCO",
            "ESCO URI": shorten_uri(one_mapping["esco_uri"]),
            "How it matched": one_mapping["match_type"],
        })

    st.dataframe(pd.DataFrame(table_rows), hide_index=True,
                use_container_width=True)


if st.button("Map Skills"):
    st.session_state.mapping_was_requested = True

if st.session_state.get("mapping_was_requested", False):
    # --- the job description ---------------------------------------------
    job_skill_mappings = map_skill_list_to_esco(
        st.session_state.job_description_skills, mapping_index)
    show_mapping_results("Job Description", job_skill_mappings)

    # --- every candidate --------------------------------------------------
    for candidate_number, one_candidate in enumerate(st.session_state.candidates,
                                                    start=1):
        candidate_skill_mappings = map_skill_list_to_esco(
            one_candidate["skills"], mapping_index)
        show_mapping_results(
            "Candidate " + str(candidate_number) + ": " + one_candidate["name"],
            candidate_skill_mappings,
        )
else:
    st.info("Click 'Map Skills' to see how every typed skill becomes an ESCO skill.")


# ===========================================================================
# SECTION 4 - Score Candidates
# ===========================================================================

st.header("4. Score Candidates")
st.write(
    "For every job description skill we look for the closest candidate skill "
    "using Dijkstra's algorithm. The graph is weighted, so what we compare is "
    "the COST of the route, not the number of steps. Staying among specific "
    "skills is cheap. Climbing up into a generic ESCO group is expensive."
)


def score_one_candidate(one_candidate):
    """
    Score one candidate against the job description.

    What it does : maps both sides onto ESCO and runs the scoring.
    Inputs       : one_candidate - a dictionary {name, skills}
    Outputs      : a tuple (match_rows, average_similarity)
    """
    job_skill_mappings = map_skill_list_to_esco(
        st.session_state.job_description_skills, mapping_index)
    candidate_skill_mappings = map_skill_list_to_esco(
        one_candidate["skills"], mapping_index)

    return score_candidate(technology_graph, job_skill_mappings,
                          candidate_skill_mappings)


def build_score_table(match_rows):
    """
    Turn the match rows into a table we can show on screen.

    What it does : formats one row per job description skill, including a
                   plain words explanation of why the score is what it is.
    Inputs       : match_rows - from scoring.score_candidate()
    Outputs      : a pandas DataFrame
    """
    table_rows = []

    for one_match in match_rows:
        # A skipped row is a JD skill that ESCO has no concept for. We still
        # show it, so nothing disappears silently, but it did not take part
        # in the average.
        if one_match["skipped"]:
            table_rows.append({
                "JD Skill": one_match["job_skill"],
                "Candidate Skill": "-",
                "Why this score": "not in ESCO, so it could not be judged",
                "Shared ESCO concept": "-",
                "Shortest Path": "-",
                "Path Cost": "-",
                "Similarity": "not counted",
            })
            continue

        relationship, shared_concept = describe_relationship(technology_graph,
                                                            one_match)

        table_rows.append({
            "JD Skill": one_match["job_skill"],
            "Candidate Skill": one_match["candidate_skill"] or "no match",
            "Why this score": relationship,
            "Shared ESCO concept": shared_concept or "-",
            "Shortest Path": build_path_text(one_match),
            # Kept as text so the whole column has one type, because the
            # skipped rows above put a "-" in it.
            "Path Cost": str(one_match["distance"]) if one_match["distance"] is not None else "-",
            "Similarity": str(one_match["similarity"]) + "%",
        })

    return pd.DataFrame(table_rows)


def build_path_inspector_text(one_match):
    """
    Write out one comparison step by step, so the score can be checked by hand.

    It shows what was typed, what ESCO concept it became, then every single
    edge of the route with the kind of ESCO relationship it used and what that
    step cost.

    What it does : builds the text for one row of the path inspector.
    Inputs       : one_match - a match dictionary from scoring
    Outputs      : the explanation as one string
    """
    lines = []
    lines.append("Job description skill : " + one_match["job_skill"])
    lines.append("Mapped ESCO concept   : " + str(one_match["job_esco_label"]))
    lines.append("")
    lines.append("Candidate skill       : " + str(one_match["candidate_skill"]))
    lines.append("Mapped ESCO concept   : "
                + str(one_match["candidate_esco_label"]))
    lines.append("")
    lines.append("-" * 62)
    lines.append("")

    path_steps = build_path_steps(technology_graph, one_match)

    if len(path_steps) == 0:
        lines.append(str(one_match["job_esco_label"]))
        lines.append("   (both skills are the same ESCO concept, no travel needed)")
    else:
        # Draw the chain, one edge at a time.
        lines.append(path_steps[0]["from_label"])
        for one_step in path_steps:
            lines.append("  |")
            lines.append("  +-- " + one_step["relation_type"]
                        + "  (" + one_step["esco_type"] + ")"
                        + "   cost = " + str(one_step["weight"]))
            lines.append("  |")
            lines.append(one_step["to_label"])

    lines.append("")
    lines.append("-" * 62)
    lines.append("")
    lines.append("Total cost  : " + str(one_match["distance"]))
    lines.append("Similarity  : " + str(one_match["similarity"]) + "%")
    lines.append("")
    lines.append("Reason      : " + explain_route(technology_graph, one_match))

    return "\n".join(lines)


def show_path_inspector(match_rows):
    """
    Show the path inspector for every job description skill.

    What it does : draws one foldable block per JD skill, containing the full
                   edge by edge explanation of that row's score.
    Inputs       : match_rows - from scoring.score_candidate()
    Outputs      : nothing, it only draws
    """
    st.write("**Path inspector**")
    st.caption("Pick a job description skill to see every step of the route, "
              "what kind of ESCO relationship each step used, and what it cost. "
              "A 'skill' step is a real ESCO skill relationship and is cheap. "
              "A 'skill_group' step is only an education category and is dear.")

    # Only the rows we could actually judge have a route to inspect.
    rows_to_inspect = []
    skipped_skill_names = []

    for one_match in match_rows:
        if one_match["skipped"]:
            skipped_skill_names.append(one_match["job_skill"])
        else:
            rows_to_inspect.append(one_match)

    if len(skipped_skill_names) > 0:
        st.caption("Not in ESCO, so nothing to inspect: "
                  + ", ".join(skipped_skill_names))

    if len(rows_to_inspect) == 0:
        return

    # One tab per job description skill. Tabs are used rather than foldable
    # panels because this whole block can already sit inside a foldable panel
    # when we are comparing everybody, and Streamlit does not allow those to
    # be nested.
    tab_labels = [one_match["job_skill"] for one_match in rows_to_inspect]
    inspector_tabs = st.tabs(tab_labels)

    for one_tab, one_match in zip(inspector_tabs, rows_to_inspect):
        with one_tab:
            st.code(build_path_inspector_text(one_match), language="text")


def show_one_candidate_result(one_candidate, match_rows, average_similarity):
    """
    Show the score, the graph and the table for one candidate.

    This is used both when scoring a single candidate and when comparing
    everybody, so the two views always look the same.

    What it does : draws one candidate's full result on the screen.
    Inputs       : one_candidate      - a dictionary {name, skills}
                   match_rows         - from scoring.score_candidate()
                   average_similarity - the candidate's score
    Outputs      : nothing, it only draws
    """
    number_skipped = count_skipped_skills(match_rows)
    number_judged = len(match_rows) - number_skipped

    st.metric("Average Similarity for " + one_candidate["name"],
             str(average_similarity) + "%")
    st.caption("Averaged over the " + str(number_judged)
               + " job description skills ESCO could judge."
               + (" " + str(number_skipped) + " skill(s) were skipped "
                  "because ESCO has no concept for them."
                  if number_skipped > 0 else ""))

    st.write(
        "**Nodes** - green = job description skill, "
        "blue = candidate skill, "
        "yellow = ESCO concept in between."
    )
    st.write(
        "**Lines** - each one is labelled with the kind of ESCO relationship "
        "it uses and what that step costs. A thick green line marked "
        "`skill` is a real ESCO skill relationship and is cheap. A thin "
        "dashed grey line marked `group` is only an ESCO education category "
        "and is expensive. Hover over a line for the full explanation."
    )
    components.html(build_explanation_graph_html(technology_graph, match_rows,
                                                one_candidate["name"]),
                   height=520)

    st.dataframe(build_score_table(match_rows), hide_index=True,
                use_container_width=True)

    show_path_inspector(match_rows)


def build_comparison_table(all_results):
    """
    Build the table that puts every candidate side by side.

    What it does : sorts the candidates by score, best first, and adds a rank.
    Inputs       : all_results - a list of tuples
                                 (candidate, match_rows, average_similarity)
    Outputs      : a pandas DataFrame
    """
    # Sort by the score, highest first.
    sorted_results = sorted(all_results, key=lambda result: result[2],
                           reverse=True)

    table_rows = []
    rank_number = 1

    for one_candidate, match_rows, average_similarity in sorted_results:
        # Count how many job description skills this candidate matched well.
        strong_matches = 0
        for one_match in match_rows:
            if not one_match["skipped"] and one_match["similarity"] >= 90:
                strong_matches = strong_matches + 1

        table_rows.append({
            "Rank": rank_number,
            "Candidate": one_candidate["name"],
            "Overall Score": str(average_similarity) + "%",
            "Strong matches (90% or more)": strong_matches,
            "Skills listed": len(one_candidate["skills"]),
        })
        rank_number = rank_number + 1

    return pd.DataFrame(table_rows)


if len(st.session_state.job_description_skills) == 0 or len(st.session_state.candidates) == 0:
    st.info("Add job description skills and at least one candidate first.")
else:
    candidate_names = [one_candidate["name"]
                      for one_candidate in st.session_state.candidates]

    # Two ways to look at the results: one candidate on their own, or
    # everybody together so they can be compared.
    single_tab, compare_tab = st.tabs(["One candidate", "Compare everybody"])

    # --- one candidate at a time -----------------------------------------
    with single_tab:
        selected_candidate_name = st.selectbox("Select Candidate",
                                              candidate_names)

        if st.button("Score"):
            for one_candidate in st.session_state.candidates:
                if one_candidate["name"] == selected_candidate_name:
                    match_rows, average_similarity = score_one_candidate(
                        one_candidate)
                    show_one_candidate_result(one_candidate, match_rows,
                                             average_similarity)

    # --- everybody together ----------------------------------------------
    with compare_tab:
        st.write(
            "Every candidate is scored against the same job description, so "
            "the scores can be compared directly. The same job description "
            "skills are skipped for everybody, which keeps the comparison fair."
        )

        if st.button("Score All Candidates"):
            # Score everybody first, then show the comparison, then the
            # detail for each person underneath it.
            all_results = []
            for one_candidate in st.session_state.candidates:
                match_rows, average_similarity = score_one_candidate(
                    one_candidate)
                all_results.append((one_candidate, match_rows,
                                   average_similarity))

            st.subheader("Comparison")
            st.dataframe(build_comparison_table(all_results), hide_index=True,
                        use_container_width=True)

            # A simple bar chart, the easiest way to see the gaps.
            chart_data = pd.DataFrame(
                {"Overall Score": [result[2] for result in all_results]},
                index=[result[0]["name"] for result in all_results],
            )
            st.bar_chart(chart_data)

            st.subheader("Every candidate in detail")
            st.caption("Best score first. Open a candidate to see their graph "
                      "and their score table.")

            # Show the details best first, matching the comparison table.
            sorted_results = sorted(all_results, key=lambda result: result[2],
                                   reverse=True)

            for position in range(len(sorted_results)):
                one_candidate, match_rows, average_similarity = sorted_results[position]

                heading = (one_candidate["name"] + "  -  "
                          + str(average_similarity) + "%")

                # Open the best candidate, keep the rest folded away.
                is_best_candidate = (position == 0)
                with st.expander(heading, expanded=is_best_candidate):
                    show_one_candidate_result(one_candidate, match_rows,
                                             average_similarity)
