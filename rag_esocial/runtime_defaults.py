"""Defaults controlled by the application, not by the normal user flow."""

DEFAULT_PARSER_REVISION = "parser-suite-v1"
DEFAULT_PARSER_CONFIG = {"suite": "mos-layout-xsd", "revision": DEFAULT_PARSER_REVISION}
DEFAULT_SEARCH_PROFILE = "LAYOUT_FIELD"
DEFAULT_SEARCH_REVISION = "fts-baseline-v1"
DEFAULT_SEARCH_CONFIG = {}
DEFAULT_TOP_K = 5
RUNTIME_KEY = "default"

ROLE_METADATA = {
    "MOS_MAIN": ("MOS", "Manual de Orientação do eSocial"),
    "LAYOUT_MAIN": ("LAYOUT", "Leiautes do eSocial"),
    "LAYOUT_ANNEX_I_DOMAIN_TABLES": ("LAYOUT", "Anexo I — Tabelas de Domínio"),
    "LAYOUT_ANNEX_II_VALIDATION_RULES": ("LAYOUT", "Anexo II — Regras de Validação"),
    "XSD_PACKAGE": ("XSD", "Pacote de esquemas XSD do eSocial"),
}
