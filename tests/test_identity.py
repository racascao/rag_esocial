from rag_esocial.identity import (
    build_digest,
    citation_stable_key,
    entity_stable_key,
    parser_config_digest,
)


def test_parser_config_and_build_digests_are_deterministic() -> None:
    assert parser_config_digest({"b": 2, "a": 1}) == parser_config_digest(
        {"a": 1, "b": 2}
    )
    digest = build_digest("m" * 64, "parser-v1", parser_config_digest({}))
    assert digest == build_digest("m" * 64, "parser-v1", parser_config_digest({}))
    assert digest != build_digest("m" * 64, "parser-v2", parser_config_digest({}))


def test_citation_and_entity_identities_are_separate() -> None:
    mos = citation_stable_key("version-a", "MOS", "MOS/AnnexII/rule")
    layout = citation_stable_key("version-a", "LAYOUT", "LAYOUT/AnnexII/rule")
    assert mos != layout
    assert entity_stable_key("RULE", "REGRA_X") != entity_stable_key(
        "DOMAIN_TABLE", "REGRA_X"
    )
