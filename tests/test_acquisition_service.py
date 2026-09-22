import zipfile

import pytest

from rag_esocial.acquisition_service import (
    AcquisitionError,
    UrlDownloader,
    discover_layout_annexes,
    validate_download,
)


def test_discover_layout_annexes_resolves_relative_and_absolute_links():
    html = """
    <a href="docs/tabelas.html"> Anexo I — Tabelas </a>
    <a href="https://example.test/regras.html">ANEXO II - Regras de Validação</a>
    """
    assert discover_layout_annexes(html, "https://example.test/layout/index.html") == {
        "LAYOUT_ANNEX_I_DOMAIN_TABLES": "https://example.test/layout/docs/tabelas.html",
        "LAYOUT_ANNEX_II_VALIDATION_RULES": "https://example.test/regras.html",
    }


@pytest.mark.parametrize(
    "html",
    [
        '<a href="i.html">Anexo I</a>',
        (
            '<a href="i1.html">Anexo I</a><a href="i2.html">Anexo I</a>'
            '<a href="ii.html">Anexo II</a>'
        ),
    ],
)
def test_discover_layout_annexes_fails_closed(html):
    with pytest.raises(AcquisitionError):
        discover_layout_annexes(html, "https://example.test/layout.html")


def test_discover_layout_annexes_does_not_infer_from_unrelated_content():
    with pytest.raises(AcquisitionError):
        discover_layout_annexes(
            "<p>Anexo I aparece no texto, sem link</p>", "https://example.test"
        )


def test_discovery_normalizes_fragments_and_deduplicates_realistic_annex_links():
    html = """
    <a href="tabelas.html#01">Tabela 01</a>
    <a href="tabelas.html#05">Tabela 05</a>
    <a href="./tabelas.html#10">Tabela 10</a>
    <a href="regras.html#REGRA_EXEMPLO">REGRA_EXEMPLO</a>
    <a href="regras.html#REGRA_OUTRA">REGRA_OUTRA</a>
    """
    assert discover_layout_annexes(html, "https://example.test/v1/index.html") == {
        "LAYOUT_ANNEX_I_DOMAIN_TABLES": "https://example.test/v1/tabelas.html",
        "LAYOUT_ANNEX_II_VALIDATION_RULES": "https://example.test/v1/regras.html",
    }


def test_discovery_resolves_parent_link_and_preserves_legitimate_query_string():
    html = """
    <a href="../tabelas.html?edition=1#05">Tabela 05</a>
    <a href="https://example.test/regras.html?edition=1#REGRA_X">REGRA_X</a>
    """
    assert discover_layout_annexes(html, "https://example.test/v1/page/index.html") == {
        "LAYOUT_ANNEX_I_DOMAIN_TABLES": "https://example.test/v1/tabelas.html?edition=1",
        "LAYOUT_ANNEX_II_VALIDATION_RULES": "https://example.test/regras.html?edition=1",
    }


@pytest.mark.parametrize(
    "html",
    [
        (
            '<a href="a/tabelas.html#01">Tabela</a>'
            '<a href="b/tabelas.html#02">Tabela</a>'
            '<a href="regras.html#A">REGRA_A</a>'
        ),
        (
            '<a href="tabelas.html#01">Tabela</a>'
            '<a href="a/regras.html#A">REGRA_A</a>'
            '<a href="b/regras.html#B">REGRA_B</a>'
        ),
    ],
)
def test_discovery_rejects_distinct_base_urls_for_one_annex(html):
    with pytest.raises(AcquisitionError, match="ambíguos"):
        discover_layout_annexes(html, "https://example.test/layout/index.html")


def test_discovery_does_not_accept_unrelated_table_or_rule_links():
    html = """
    <a href="glossario.html#tabela">tabela de conteúdo</a>
    <a href="manual.html#regra">regra editorial</a>
    """
    with pytest.raises(AcquisitionError, match="Anexo I"):
        discover_layout_annexes(html, "https://example.test/layout/index.html")


def test_validate_download_rejects_wrong_physical_types(tmp_path):
    pdf = tmp_path / "mos.pdf"
    pdf.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(AcquisitionError, match="PDF válido"):
        validate_download(pdf, "MOS_MAIN")

    archive = tmp_path / "xsd.zip"
    archive.write_bytes(b"PK-not-a-zip")
    with pytest.raises(AcquisitionError, match="corrompido"):
        validate_download(archive, "XSD_PACKAGE")

    layout = tmp_path / "layout.html"
    layout.write_text("plain text")
    with pytest.raises(AcquisitionError, match="HTML válido"):
        validate_download(layout, "LAYOUT_MAIN")


@pytest.mark.parametrize(
    "member", ["../escape.xsd", "..\\escape.xsd", "C:\\escape.xsd"]
)
def test_validate_download_rejects_zip_slip_for_posix_and_windows_paths(
    tmp_path, member
):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(member, "<xs:schema/>")

    with pytest.raises(AcquisitionError, match="caminho inseguro"):
        validate_download(archive, "XSD_PACKAGE")


class _Response:
    headers = {"Content-Type": "application/pdf"}

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


def test_downloader_validates_before_persisting_and_hashes(tmp_path):
    downloader = UrlDownloader(
        tmp_path, opener=lambda *_args, **_kwargs: _Response(b"%PDF-1.7\n")
    )
    item = downloader.download("MOS_MAIN", "https://example.test/mos.pdf")
    assert item.path.is_file()
    assert item.sha256
    assert item.path.parent == tmp_path
    assert not list(tmp_path.glob(".download-*"))


@pytest.mark.parametrize(
    ("role", "payload", "message"),
    [
        (
            "LAYOUT_ANNEX_I_DOMAIN_TABLES",
            (
                b"<html><h1>Anexo II dos Leiautes do eSocial</h1>"
                b"Regras de Validacao</html>"
            ),
            "Anexo I",
        ),
        (
            "LAYOUT_ANNEX_II_VALIDATION_RULES",
            b"<html><h1>Anexo I dos Leiautes do eSocial</h1>Tabelas</html>",
            "Anexo II",
        ),
    ],
)
def test_downloader_rejects_semantically_wrong_annex_before_persisting(
    tmp_path, role, payload, message
):
    downloader = UrlDownloader(
        tmp_path, opener=lambda *_args, **_kwargs: _Response(payload)
    )
    with pytest.raises(AcquisitionError, match=message):
        downloader.download(role, "https://example.test/annex.html")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("role", "payload"),
    [
        (
            "LAYOUT_ANNEX_I_DOMAIN_TABLES",
            b"<html><h1>ANEXO I DOS LEIAUTES DO eSOCIAL</h1><p>TABELAS</p></html>",
        ),
        (
            "LAYOUT_ANNEX_II_VALIDATION_RULES",
            (
                b"<html><h1>ANEXO II DOS LEIAUTES DO eSOCIAL</h1>"
                b"<p>REGRAS DE VALIDA\xc3\x87\xc3\x83O</p></html>"
            ),
        ),
    ],
)
def test_downloader_accepts_semantically_valid_annex(tmp_path, role, payload):
    downloader = UrlDownloader(
        tmp_path, opener=lambda *_args, **_kwargs: _Response(payload)
    )
    item = downloader.download(role, "https://example.test/annex.html")
    assert item.path.is_file()
