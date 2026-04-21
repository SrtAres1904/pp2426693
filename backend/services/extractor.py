import io
import PyPDF2
import docx


def extract_text(content: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        return _extract_from_pdf(content)
    elif filename.lower().endswith(".txt"):
        return content.decode("utf-8", errors="replace")
    elif filename.lower().endswith(".docx"):
        return _extract_from_docx(content)
    else:
        raise ValueError(f"Unsupported file type: {filename}")


def _extract_from_pdf(content: bytes) -> str:
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)


def _extract_from_docx(content: bytes) -> str:
    document = docx.Document(io.BytesIO(content))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)
