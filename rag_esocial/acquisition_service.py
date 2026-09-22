"""Deterministic, closed-world acquisition for the normal onboarding flow."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit


class AcquisitionError(ValueError):
    """An expected source/download/discovery error shown without a traceback."""


@dataclass(frozen=True)
class SourceInput:
    mos_url: str
    xsd_url: str
    layout_url: str


@dataclass(frozen=True)
class DownloadedSource:
    role: str
    url: str
    filename: str
    path: Path
    sha256: str
    size_bytes: int
    media_type: str | None = None


def _validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AcquisitionError("Informe uma URL HTTP/HTTPS válida.")
    return url.strip()


def _filename(url: str, role: str) -> str:
    name = Path(urlparse(url).path).name
    if not name or name in {".", ".."}:
        suffix = {"MOS_MAIN": ".pdf", "XSD_PACKAGE": ".zip"}.get(role, ".html")
        return f"{role.lower()}{suffix}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:240]


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_download(path: Path, role: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise AcquisitionError(f"O artefato {role} está vazio.")
    head = path.read_bytes()[:512]
    if role == "MOS_MAIN" and not head.startswith(b"%PDF"):
        raise AcquisitionError(
            "O endereço informado para o MOS não retornou um PDF válido."
        )
    if role == "XSD_PACKAGE":
        if not head.startswith(b"PK"):
            raise AcquisitionError("O pacote XSD não é um ZIP válido.")
        try:
            with zipfile.ZipFile(path) as archive:
                names = [
                    name for name in archive.namelist() if name.lower().endswith(".xsd")
                ]
                if not names:
                    raise AcquisitionError("O pacote XSD não contém esquemas XSD.")
                for name in names:
                    safe = Path(name)
                    if safe.is_absolute() or ".." in safe.parts:
                        raise AcquisitionError("O pacote XSD contém caminho inseguro.")
                    archive.open(name).close()
        except zipfile.BadZipFile as error:
            raise AcquisitionError("O pacote XSD está corrompido.") from error
    if role.startswith("LAYOUT"):
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeError as error:
            raise AcquisitionError(
                "O documento do Leiaute não é HTML válido."
            ) from error
        if "<html" not in text.lower() and "<!doctype" not in text.lower():
            raise AcquisitionError("O documento do Leiaute não é HTML válido.")
        if role == "LAYOUT_ANNEX_I_DOMAIN_TABLES":
            validate_layout_annex(path, "I")
        if role == "LAYOUT_ANNEX_II_VALIDATION_RULES":
            validate_layout_annex(path, "II")


def _normalized_document_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_accents).casefold()


def validate_layout_annex(path: Path, roman: str) -> None:
    """Confirm that a physically valid HTML document has the requested role."""
    text = _normalized_document_text(path.read_text(encoding="utf-8", errors="strict"))
    if roman == "I":
        valid = bool(re.search(r"\banexo\s+i\b", text)) and "tabela" in text
        label = "Anexo I — Tabelas"
    elif roman == "II":
        valid = bool(re.search(r"\banexo\s+ii\b", text)) and (
            "regras de validacao" in text
        )
        label = "Anexo II — Regras de Validação"
    else:
        raise ValueError(f"annex role is invalid: {roman}")
    if not valid:
        raise AcquisitionError(f"O documento não corresponde a {label}.")


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def discover_layout_annexes(html: str, page_url: str) -> dict[str, str]:
    """Resolve annexes from source links, collapsing anchors before ambiguity checks."""
    parser = _LinkParser()
    parser.feed(html)
    candidates: dict[str, set[str]] = {"I": set(), "II": set()}
    for href, label in parser.links:
        resolved = urljoin(page_url, href)
        parsed = urlsplit(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        normalized_url = urlunsplit(parsed._replace(fragment=""))
        link_text = _normalized_document_text(f"{label} {href}")
        basename = Path(parsed.path).name.casefold()
        explicit_i = bool(re.search(r"\banexo\s+i\b|\bannex\s+i\b", link_text))
        explicit_ii = bool(re.search(r"\banexo\s+ii\b|\bannex\s+ii\b", link_text))
        if explicit_i or basename == "tabelas.html":
            candidates["I"].add(normalized_url)
        if explicit_ii or basename == "regras.html":
            candidates["II"].add(normalized_url)
    resolved = {}
    for roman, values in candidates.items():
        unique = sorted(values)
        if len(unique) != 1:
            label = f"Anexo {roman}"
            if not unique:
                raise AcquisitionError(
                    f"Não foi possível localizar {label} na página de Leiautes."
                )
            raise AcquisitionError(
                f"A página de Leiautes possui links ambíguos para {label}."
            )
        resolved[
            "LAYOUT_ANNEX_I_DOMAIN_TABLES"
            if roman == "I"
            else "LAYOUT_ANNEX_II_VALIDATION_RULES"
        ] = unique[0]
    return resolved


class UrlDownloader:
    def __init__(self, destination: Path, opener=None):
        self.destination = Path(destination)
        self.destination.mkdir(parents=True, exist_ok=True)
        self.opener = opener or urllib.request.urlopen

    def download(self, role: str, url: str) -> DownloadedSource:
        url = _validate_url(url)
        filename = _filename(url, role)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".download-", dir=self.destination
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with (
                self.opener(url, timeout=60) as response,
                temporary.open("wb") as target,
            ):
                target.write(response.read())
                media_type = response.headers.get("Content-Type")
            validate_download(temporary, role)
            final = self.destination / f"{uuid.uuid4()}-{filename}"
            temporary.replace(final)
            return DownloadedSource(
                role,
                url,
                filename,
                final,
                _digest(final),
                final.stat().st_size,
                media_type,
            )
        except AcquisitionError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise AcquisitionError(
                f"Não foi possível baixar o artefato {role}."
            ) from error
