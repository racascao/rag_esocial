from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from rag_esocial.pdf_text import PdfTextExtractionError, PdfTextExtractor


def make_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = StreamObject()
    stream._data = (
        b"BT /F1 12 Tf 40 740 Td (S-9999 Evento de Teste) Tj "
        b"0 -20 Td (Conceito {ideDmDev} [infoPerAnt]) Tj "
        b"0 -20 Td (REGRA_EXEMPLO Tabela 05) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def test_valid_pdf_extracts_page_and_references(tmp_path: Path) -> None:
    path = tmp_path / "fixture.pdf"
    make_pdf(path)
    result = PdfTextExtractor().extract(path)
    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "S-9999" in result.pages[0].text
    assert "{ideDmDev}" in result.pages[0].text
    assert "[infoPerAnt]" in result.pages[0].text
    assert "REGRA_EXEMPLO" in result.pages[0].text
    assert "Tabela 05" in result.pages[0].text


def test_invalid_pdf_is_controlled(tmp_path: Path) -> None:
    path = tmp_path / "invalid.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(PdfTextExtractionError):
        PdfTextExtractor().extract(path)
