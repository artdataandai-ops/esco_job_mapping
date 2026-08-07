"""
pdf_extraction.py
==================

Turns an uploaded PDF (a job description or a resume) into plain text, so it
can be handed to skill_extraction.py.

Uses PyMuPDF (imported as "fitz") rather than a pure-Python PDF library.
Resumes in particular are often laid out in two columns or use small tables
for contact details and skill lists; PyMuPDF's text extraction keeps reading
order sane on layouts like that, and it is fast enough that a page never
takes more than a few milliseconds.
"""

import fitz


def extract_text_from_pdf_bytes(pdf_bytes):
    """
    Read all the text out of one PDF file.

    What it does : opens a PDF held in memory and joins the text of every page.
    Inputs       : pdf_bytes - the raw bytes of one PDF file, for example from
                   a Streamlit st.file_uploader widget
    Outputs      : the PDF's text as one string (empty string when the PDF has
                   no text layer at all, such as a pure scan)
    """
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        page_texts = [page.get_text() for page in document]
    finally:
        document.close()

    return "\n".join(page_texts).strip()
