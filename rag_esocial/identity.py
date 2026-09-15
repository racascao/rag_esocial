import hashlib
import json


def canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parser_config_digest(config: dict) -> str:
    return hashlib.sha256(canonical_json(config).encode()).hexdigest()


def build_digest(manifest_sha256: str, parser_revision: str, config_digest: str) -> str:
    value = f"{manifest_sha256}\n{parser_revision}\n{config_digest}".encode()
    return hashlib.sha256(value).hexdigest()


def citation_stable_key(
    document_version_key: str, document_family: str, path: str
) -> str:
    return f"{document_version_key}|{document_family}|{path}"


def entity_stable_key(entity_kind: str, canonical_key: str) -> str:
    return f"{entity_kind}:{canonical_key}"
