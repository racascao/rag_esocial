from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class XsdPackageDocument(Base):
    __tablename__ = "xsd_package_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("document_artifacts.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class XsdEventSchema(Base):
    __tablename__ = "xsd_event_schemas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_document_id: Mapped[str] = mapped_column(
        ForeignKey("xsd_package_documents.id"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    schema_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_namespace: Mapped[str | None] = mapped_column(Text)
    schema_key: Mapped[str] = mapped_column(String(300), nullable=False)
    event_code: Mapped[str | None] = mapped_column(String(20))
    root_name: Mapped[str | None] = mapped_column(String(300))
    documentation: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("package_document_id", "source_local_stable_path"),
    )


class XsdSharedType(Base):
    __tablename__ = "xsd_shared_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_document_id: Mapped[str] = mapped_column(
        ForeignKey("xsd_package_documents.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_namespace: Mapped[str | None] = mapped_column(Text)
    base_qname: Mapped[str | None] = mapped_column(String(300))
    facets: Mapped[dict | None] = mapped_column(JSON)
    documentation: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("package_document_id", "source_local_stable_path"),
    )


class XsdElement(Base):
    __tablename__ = "xsd_elements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_document_id: Mapped[str] = mapped_column(
        ForeignKey("xsd_package_documents.id"), nullable=False
    )
    owner_schema_id: Mapped[str | None] = mapped_column(
        ForeignKey("xsd_event_schemas.id")
    )
    owner_shared_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("xsd_shared_types.id")
    )
    parent_element_id: Mapped[str | None] = mapped_column(ForeignKey("xsd_elements.id"))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    type_qname: Mapped[str | None] = mapped_column(String(300))
    ref_qname: Mapped[str | None] = mapped_column(String(300))
    min_occurs: Mapped[str | None] = mapped_column(String(30))
    max_occurs: Mapped[str | None] = mapped_column(String(30))
    nillable: Mapped[bool | None] = mapped_column()
    default_value: Mapped[str | None] = mapped_column(Text)
    fixed_value: Mapped[str | None] = mapped_column(Text)
    facets: Mapped[dict | None] = mapped_column(JSON)
    documentation: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("package_document_id", "source_local_stable_path"),
    )


class XsdEnumeration(Base):
    __tablename__ = "xsd_enumerations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_document_id: Mapped[str] = mapped_column(
        ForeignKey("xsd_package_documents.id"), nullable=False
    )
    owner_element_id: Mapped[str | None] = mapped_column(ForeignKey("xsd_elements.id"))
    owner_shared_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("xsd_shared_types.id")
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    documentation: Mapped[str | None] = mapped_column(Text)
    source_local_stable_path: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("package_document_id", "source_local_stable_path"),
    )
