# Modelos das fontes

As famílias têm árvores próprias:

| Família | Unidades persistidas principais |
| --- | --- |
| MOS | `MosDocument`, `MosEventSection`, `EventMetadataBlock`, `MosTopic`, `MosEventTopic`, `MosEventSubitem`, `ContentBlock` |
| Leiaute | `LayoutDocument`, `LayoutEvent`, `LayoutGroup`, `LayoutField` |
| XSD | `XsdPackageDocument`, `XsdEventSchema`, `XsdElement`, `XsdSharedType`, `XsdEnumeration` |

Cada nó estrutural recebe path local estável e pode originar um `CitationTarget`.
As árvores não são achatadas em chunks universais. Consulte as referências
[MOS](../mos_structure.md), [Leiaute](../layout_structure.md) e [XSD](../xsd_structure.md).
