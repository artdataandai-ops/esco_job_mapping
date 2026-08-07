"""
skill_extraction.py
====================

Turns the raw text of a job description or a resume into a plain list of
skill names, using an LLM (OpenAI's gpt-4o-mini by default).

This is the one part of the project that is NOT purely ESCO-driven: the LLM
decides which words in the text are worth treating as a skill at all. What
happens after that is unchanged - mapping.py still decides, using nothing but
ESCO's own vocabulary, whether any of those words are a skill ESCO recognises.
So a skill the LLM invents but ESCO does not know about still ends up
"not found in ESCO", exactly like a manually typed one would.

The prompt below is carried over from an earlier version of this project
(job_map/services/ingestion/llm_extractor.py), which already tuned it against
real job descriptions and resumes.
"""

import json

from openai import OpenAI

import config

_SYSTEM_PROMPT = """\
You are an expert technical recruiter and skill extractor.
Extract ONLY professional, technical skills from the provided text.

Include:
- Programming languages (Python, Java, TypeScript, Go, Rust, etc.)
- Frameworks and libraries (FastAPI, React, Spring Boot, Django, etc.)
- Databases (PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, etc.)
- Cloud platforms and services (AWS, GCP, Azure, S3, EC2, EKS, Lambda, etc.)
- DevOps and infrastructure tools (Docker, Kubernetes, Terraform, Ansible, CI/CD, Git, Jenkins, etc.)
- Software methodologies (Agile, Scrum, Kanban, TDD, Microservices, REST API, GraphQL, etc.)
- Data and ML tools (TensorFlow, PyTorch, Spark, Kafka, Airflow, etc.)
- Operating systems (Linux, Ubuntu, Windows Server, etc.)
- Security tools (OAuth, JWT, SSL/TLS, Kali Linux, OWASP, etc.)
- Certifications relevant to IT roles (AWS Certified, CKA, etc.)
- Named technical disciplines, practices and knowledge areas - these count as
  skills even though they are not products. Extract them whenever the text names
  one, in the wording the text uses:
    software architecture, software design, systems development life-cycle,
    data models, data modelling, information architecture, database design,
    requirements analysis, software testing, unit testing, integration testing,
    code review, version control, technical documentation, algorithms,
    data structures, computer networks, network security, information security,
    encryption, penetration testing, web programming, data mining,
    data warehouse, data analytics, business intelligence, machine learning,
    computer vision, deep learning, neural networks, virtualisation,
    cloud technologies, system integration, software metrics

Do NOT include:
- Soft skills (communication, teamwork, leadership, problem solving)
- Sports or hobbies (football, swimming, photography, etc.)
- Medical or health skills (first aid, clinical skills, etc.)
- Non-IT industry skills (accounting, construction, legal, etc.)
- Bare generic verbs with no technical object (develop, collaborate, participate).
  NOTE: this excludes bare verbs only. A named discipline such as "software
  architecture" or "systems development life-cycle" IS a skill - extract it.
- Job titles, company names, or locations
- Experience levels or years (e.g. "5 years of Python" -> just "Python")

Extract every distinct skill the text names, including ones listed in a comma-
separated "Skills" line and ones that only appear inside experience bullets.
"""

_USER_TEMPLATE = """\
Extract all technical skills from this text. Return a JSON array only, no other text.
Each element must be: {{"skill": "<exact skill name>", "confidence": <0.0-1.0>}}

Text:
{text}

JSON array of skills:"""


_client = None


def get_client():
    """
    Build (once) and return the OpenAI client used for skill extraction.

    What it does : creates the client on first use and reuses it afterwards.
    Inputs       : nothing (the API key comes from config.OPENAI_API_KEY)
    Outputs      : an openai.OpenAI client
    """
    global _client

    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to the .env file in this "
                "project folder, or set it as an environment variable.")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)

    return _client


def extract_skills_from_text(document_text):
    """
    Ask the LLM which technical skills appear in one piece of text.

    What it does : sends the text to the LLM and parses its JSON answer into
                   a plain list of skill names.
    Inputs       : document_text - the plain text of one JD or one resume,
                   for example from pdf_extraction.extract_text_from_pdf_bytes()
    Outputs      : a list of skill name strings, in the order the LLM returned
                   them (empty list if the text is empty or nothing qualifies)
    """
    if not document_text.strip():
        return []

    client = get_client()
    truncated_text = document_text[:config.LLM_MAX_INPUT_CHARS]

    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(text=truncated_text)},
        ],
        temperature=0.0,
        max_tokens=1200,
        response_format={"type": "json_object"} if "gpt-4" in config.LLM_MODEL else None,
    )

    return _parse_skill_response(response.choices[0].message.content)


def _parse_skill_response(raw_content):
    """
    Turn the LLM's raw text answer into a list of skill name strings.

    The LLM is asked for a JSON array, but when response_format forces JSON
    object mode it may instead wrap that array inside an object such as
    {"skills": [...]}. Both shapes are accepted. If the answer is not valid
    JSON at all, each non-empty line is treated as one skill, so a reasonable
    answer still is not thrown away over a formatting slip.

    What it does : parses and normalises one LLM response.
    Inputs       : raw_content - the message content returned by the LLM
    Outputs      : a list of skill name strings
    """
    content = raw_content.strip()

    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json\n"):
            content = content[5:]

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return [line.strip() for line in content.splitlines() if line.strip()]

    if isinstance(parsed, list):
        skill_items = parsed
    elif isinstance(parsed, dict):
        skill_items = next(
            (parsed[key] for key in ("skills", "data", "result", "results")
             if isinstance(parsed.get(key), list)),
            [])
    else:
        skill_items = []

    skill_names = []
    for one_item in skill_items:
        if isinstance(one_item, dict) and "skill" in one_item:
            skill_names.append(str(one_item["skill"]))
        elif isinstance(one_item, str):
            skill_names.append(one_item)

    return skill_names
