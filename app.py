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

import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from graph import build_technology_graph
from mapping import build_mapping_index, map_skill_list_to_esco, shorten_uri
from pdf_extraction import extract_text_from_pdf_bytes
from scoring import (build_path_steps, build_path_text, count_skipped_skills,
                     describe_relationship, explain_route, score_candidate)
from skill_extraction import extract_skills_from_text
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


# ---------------------------------------------------------------------------
# Shared helper: one uploaded PDF -> a list of skill names
# ---------------------------------------------------------------------------
#
# Used by both Section 1 (the job description) and Section 2 (candidates).
# Turns the PDF into text with pdf_extraction, then asks the LLM in
# skill_extraction which words in that text are skills. Any failure (a bad
# PDF, a missing OPENAI_API_KEY, the LLM call itself) is shown right there as
# an error for that one file, instead of crashing the whole page.

def extract_skills_from_uploaded_pdf(uploaded_file):
    """
    Turn one uploaded PDF into a list of skill names.

    What it does : reads the PDF, extracts its text, then asks the LLM which
                   words in that text are skills.
    Inputs       : uploaded_file - a Streamlit UploadedFile from a PDF
                   file_uploader widget
    Outputs      : a list of skill name strings, or None if something failed
                   (the failure is already shown on screen as an st.error)
    """
    try:
        document_text = extract_text_from_pdf_bytes(uploaded_file.getvalue())
    except Exception as error:
        st.error("Could not read " + uploaded_file.name + ": " + str(error))
        return None

    if document_text == "":
        st.warning(uploaded_file.name + " has no readable text (maybe a "
                  "scanned image?). Nothing was extracted.")
        return None

    try:
        return extract_skills_from_text(document_text)
    except Exception as error:
        st.error("Skill extraction failed for " + uploaded_file.name
                + ": " + str(error))
        return None


# ===========================================================================
# SECTION 1 - Enter Job Description Skills
# ===========================================================================

st.header("1. Enter Job Description Skills")

upload_jd_tab, type_jd_tab = st.tabs(["Upload PDF", "Type manually"])

with upload_jd_tab:
    uploaded_jd_pdf = st.file_uploader("Job description (PDF)", type=["pdf"],
                                      key="jd_pdf_uploader")

    if uploaded_jd_pdf is not None and st.button("Extract skills from PDF"):
        with st.spinner("Reading the PDF and asking the LLM for skills ..."):
            extracted_job_skills = extract_skills_from_uploaded_pdf(uploaded_jd_pdf)

        if extracted_job_skills is not None:
            if len(extracted_job_skills) == 0:
                st.warning("No technical skills were found in that PDF.")
            else:
                st.session_state.job_description_skills.extend(extracted_job_skills)
                st.success("Added " + str(len(extracted_job_skills))
                          + " skill(s) from " + uploaded_jd_pdf.name + ".")
                st.rerun()

with type_jd_tab:
    with st.form("job_description_skill_form", clear_on_submit=True):
        typed_job_skills = st.text_area(
            "Job description skills (one skill per line)",
            placeholder="Python\nPostgreSQL\nJenkins\nDocker",
            height=140,
        )
        job_skills_were_added = st.form_submit_button("Add skills")

    if job_skills_were_added:
        # Turn the text area into a clean list of skills, one per line.
        for one_line in typed_job_skills.split("\n"):
            if one_line.strip() != "":
                st.session_state.job_description_skills.append(one_line.strip())

if len(st.session_state.job_description_skills) == 0:
    st.info("No job description skills yet. Upload a PDF or add them all at once.")
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

upload_resume_tab, type_candidate_tab = st.tabs(["Upload resumes (PDF)", "Type manually"])

with upload_resume_tab:
    uploaded_resume_pdfs = st.file_uploader(
        "Resume PDFs (one candidate per file)", type=["pdf"],
        accept_multiple_files=True, key="resume_pdf_uploader")

    if uploaded_resume_pdfs and st.button("Extract candidates from PDFs"):
        existing_candidate_names = {one_candidate["name"]
                                   for one_candidate in st.session_state.candidates}
        added_candidate_names = []

        for one_resume_pdf in uploaded_resume_pdfs:
            # The file name (without ".pdf") becomes the candidate's name.
            candidate_name = os.path.splitext(one_resume_pdf.name)[0]

            if candidate_name in existing_candidate_names:
                st.warning(candidate_name + " is already in the candidate "
                          "list, skipping " + one_resume_pdf.name + ".")
                continue

            with st.spinner("Reading " + one_resume_pdf.name
                           + " and asking the LLM for skills ..."):
                extracted_candidate_skills = extract_skills_from_uploaded_pdf(
                    one_resume_pdf)

            if extracted_candidate_skills is None:
                continue

            if len(extracted_candidate_skills) == 0:
                st.warning("No technical skills were found in "
                          + one_resume_pdf.name + ".")
                continue

            st.session_state.candidates.append({
                "name": candidate_name,
                "skills": extracted_candidate_skills,
            })
            existing_candidate_names.add(candidate_name)
            added_candidate_names.append(candidate_name)

        if len(added_candidate_names) > 0:
            st.success("Added candidate(s): " + ", ".join(added_candidate_names))
            st.rerun()

with type_candidate_tab:
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
    "using Dijkstra's algorithm. The graph only contains real ESCO "
    "relationships - skill hierarchy links and ESCO's own curated "
    "skill-to-skill links - never a shared classification category. If ESCO "
    "never actually related two skills, we say so honestly instead of "
    "guessing."
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
              "A 'skill' step is a real ESCO hierarchy relationship. A "
              "'skill_relation' step is ESCO's own curated skill-to-skill "
              "link. Both are real ESCO relationships, so both are cheap - "
              "we only ever score real relationships, never a shared "
              "classification category.")

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
        "`skill` is a real ESCO hierarchy relationship. A thick blue line "
        "marked `related` is ESCO's own curated skill-to-skill link. Both "
        "are real, cheap ESCO relationships - we never score a route that "
        "only shares a generic classification category. Hover over a line "
        "for the full explanation."
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
