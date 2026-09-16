from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


@dataclass
class PdfTextExtractionResult:
    pages: list[PdfPageText] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class PdfTextExtractionError(ValueError):
    pass


class PdfTextExtractor:
    def extract(self, path: Path) -> PdfTextExtractionResult:
        try:
            reader = PdfReader(str(path), strict=False)
        except Exception as exc:
            raise PdfTextExtractionError(f"invalid PDF: {path}") from exc
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PdfPageText(index, text))
        if not any(page.text.strip() for page in pages):
            raise PdfTextExtractionError("PDF has no usable text layer")
        return PdfTextExtractionResult(pages)
