from pathlib import Path

from pypdf import PdfReader
from docx import Document


def extract_text(path: Path) -> str:
    """
    Extract readable text from supported documents.
    """

    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path)

    if extension == ".docx":
        return extract_docx(path)

    if extension == ".txt":
        return extract_txt(path)

    raise ValueError(
        f"Text extraction is not supported for {extension} files."
    )


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text.strip())

    return "\n\n".join(pages).strip()


def extract_docx(path: Path) -> str:
    document = Document(str(path))

    paragraphs = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs).strip()


def extract_txt(path: Path) -> str:
    return path.read_text(
        encoding="utf-8",
        errors="ignore",
    ).strip()