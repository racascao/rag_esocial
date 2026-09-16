import zipfile

from rag_esocial.xsd_parser import parse_xsd_package


def test_xsd_parser_preserves_named_structure_facets_and_auxiliary(tmp_path):
    package = tmp_path / "package.zip"
    event = """<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema' targetNamespace='urn:fixture:1.0'><xs:element name='evtFixture'><xs:complexType><xs:sequence><xs:element name='id' type='ts:TS_Id' minOccurs='1' maxOccurs='unbounded'/><xs:element name='code'><xs:simpleType><xs:restriction base='xs:string'><xs:pattern value='[A-Z]+'/><xs:enumeration value='A'><xs:annotation><xs:documentation>Primeiro</xs:documentation></xs:annotation></xs:enumeration></xs:restriction></xs:simpleType></xs:element></xs:sequence></xs:complexType></xs:element><xs:include schemaLocation='tipos.xsd'/></xs:schema>"""  # noqa: E501
    types = """<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema' targetNamespace='urn:fixture:1.0'><xs:simpleType name='TS_Id'><xs:restriction base='xs:string'><xs:minLength value='2'/></xs:restriction></xs:simpleType><xs:complexType name='T_Group'><xs:sequence><xs:element name='child'/></xs:sequence></xs:complexType></xs:schema>"""  # noqa: E501
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("evento_fixture.xsd", event)
        archive.writestr("tipos.xsd", types)
        archive.writestr(
            "xmldsig-core-schema.xsd",
            "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>",
        )
    results = parse_xsd_package(package)
    event_result = next(item for item in results if item.kind == "EVENT_SCHEMA")
    root = event_result.elements[0]
    assert root.children[0].max_occurs == "unbounded"
    assert root.children[0].type_qname == "ts:TS_Id"
    assert root.children[1].facets["pattern"] == ["[A-Z]+"]
    assert root.children[1].enumerations[0][0] == "A"
    assert event_result.references == [
        ("SCHEMA_INCLUDE", "tipos.xsd", "evento_fixture.xsd")
    ]
    assert any(item.kind == "AUXILIARY_SCHEMA" for item in results)
    assert any(item.kind == "SHARED_TYPES_SCHEMA" for item in results)
