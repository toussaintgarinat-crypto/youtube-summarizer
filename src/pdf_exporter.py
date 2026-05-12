"""PDF Export — converts markdown analysis output to a clean PDF."""

import re
from datetime import datetime

# A4 content width with 20mm left/right margins
_CONTENT_W = 170


def _strip_emojis(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def _clean(text: str) -> str:
    """Strip markdown syntax and emojis for plain PDF rendering."""
    text = _strip_emojis(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # Drop characters outside latin-1 (fpdf core fonts limitation)
    text = text.encode("latin-1", errors="ignore").decode("latin-1")
    return text.strip()


def export_to_pdf(markdown_text: str, title: str = "Analyse") -> bytes:
    """
    Convert a markdown string to a PDF document.
    Returns raw PDF bytes.
    Requires: pip install fpdf2
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise ValueError("fpdf2 non installe. Executez: pip install fpdf2")

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(160, 160, 160)
            self.cell(_CONTENT_W, 7, "YouTube Summarizer", align="R")
            self.ln(1)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(160, 160, 160)
            date_str = datetime.now().strftime("%d/%m/%Y")
            self.cell(_CONTENT_W, 8, f"Page {self.page_no()} | {date_str}", align="C")

    pdf = PDF()
    pdf.set_margins(20, 18, 20)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    for line in markdown_text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 15)
            pdf.set_text_color(20, 20, 20)
            text = _clean(stripped[2:])
            if text:
                pdf.multi_cell(_CONTENT_W, 9, text)
                pdf.ln(2)

        elif stripped.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(35, 80, 165)
            text = _clean(stripped[3:])
            if text:
                pdf.multi_cell(_CONTENT_W, 8, text)
                pdf.ln(1)

        elif stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(60, 60, 60)
            text = _clean(stripped[4:])
            if text:
                pdf.multi_cell(_CONTENT_W, 7, text)

        elif stripped.startswith(("- ", "* ")):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            text = _clean(stripped[2:])
            if text:
                pdf.multi_cell(_CONTENT_W, 6, f"  - {text}")

        elif stripped.startswith("|") and "|" in stripped[1:]:
            # Table — flatten cells to a single line
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells = [_clean(c) for c in cells if c and not re.match(r"^[-:]+$", c)]
            if cells:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(_CONTENT_W, 6, " | ".join(cells))

        elif stripped.startswith(("---", "===")):
            pdf.ln(3)
            pdf.set_draw_color(200, 200, 200)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.line(x, y, x + _CONTENT_W, y)
            pdf.ln(3)

        elif stripped:
            is_bold_line = stripped.startswith("**") and stripped.endswith("**")
            pdf.set_font("Helvetica", "B" if is_bold_line else "", 10)
            pdf.set_text_color(40, 40, 40)
            text = _clean(stripped)
            if text:
                pdf.multi_cell(_CONTENT_W, 6, text)

        else:
            pdf.ln(2)

    return bytes(pdf.output())
