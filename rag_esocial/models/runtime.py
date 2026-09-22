from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ActiveRuntime(Base):
    __tablename__ = "active_runtimes"

    runtime_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    corpus_build_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_builds.id"), nullable=False
    )
    search_projection_id: Mapped[str] = mapped_column(
        ForeignKey("search_projections.id"), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generation: Mapped[int] = mapped_column(nullable=False, default=1)
    build = relationship("CorpusBuild")
    projection = relationship("SearchProjection")
