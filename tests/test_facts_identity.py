from rag_esocial.identity import citation_stable_key, entity_stable_key


def test_phase4_identity_keeps_canonical_and_citation_layers_distinct():
    assert entity_stable_key("EVENT", "S-9999") == "EVENT:S-9999"
    assert citation_stable_key(
        "version-a", "MOS", "MOS/CapIII/S-9999"
    ) != entity_stable_key("EVENT", "S-9999")
