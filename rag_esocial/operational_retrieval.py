"""Evidence-first retrieval over persisted identities and parent relations."""

from sqlalchemy import select, text

from .models.build import CorpusBuild
from .models.layout import LayoutDocument, LayoutEvent, LayoutField, LayoutGroup
from .models.search import SearchUnit
from .models.xsd import XsdElement, XsdEnumeration, XsdEventSchema, XsdPackageDocument
from .operational_query import _fold, analyze_query


def _names(path):
    return {_fold(part) for part in path.split("/") if part}


def _schema_scope(session, build, event_code):
    """Resolve code through the Layout XML-root name, never a guessed XSD code."""
    roots = (
        session.execute(
            select(LayoutGroup.technical_name)
            .join(LayoutEvent)
            .join(LayoutDocument)
            .where(
                LayoutDocument.corpus_build_id == build.id,
                LayoutEvent.event_code == event_code,
                LayoutGroup.parent_group_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    schemas = session.scalars(
        select(XsdEventSchema)
        .join(XsdPackageDocument)
        .where(
            XsdPackageDocument.corpus_build_id == build.id,
            XsdEventSchema.schema_key.in_(roots),
        )
    ).all()
    return schemas[0] if len(schemas) == 1 else None


def _fts_scores(session, projection, query):
    if not query:
        return {}
    rows = session.execute(
        text(
            "SELECT id, ts_rank_cd(search_vector, "
            "websearch_to_tsquery('simple', :query)) AS score "
            "FROM search_units WHERE search_projection_id=:projection "
            "AND search_vector @@ websearch_to_tsquery('simple', :query)"
        ),
        {"query": query, "projection": projection.id},
    ).all()
    return dict(rows)


def _layout_relations(session, build, intent, units_by_path):
    names = {_fold(name) for name in intent.technical_tokens}
    if intent.requested_attributes and intent.object_kind == "FIELD":
        fields = session.execute(
            select(LayoutField, LayoutEvent)
            .select_from(LayoutField)
            .join(LayoutGroup, LayoutField.layout_group_id == LayoutGroup.id)
            .join(LayoutEvent, LayoutGroup.layout_event_id == LayoutEvent.id)
            .join(LayoutDocument)
            .where(LayoutDocument.corpus_build_id == build.id)
        ).all()
        attr = intent.requested_attributes[0]
        column = {"type": "field_type"}.get(attr, attr)
        candidates = [
            field
            for field, event in fields
            if _fold(field.technical_name) in names
            and (not intent.event_codes or event.event_code in intent.event_codes)
            and all(name in _names(field.source_local_stable_path) for name in names)
        ]
        if candidates:
            return [
                (units_by_path[field.source_local_stable_path], 100.0)
                for field in candidates
                if getattr(field, column, None) not in (None, "")
                and field.source_local_stable_path in units_by_path
            ]
    groups = session.execute(
        select(LayoutGroup, LayoutEvent)
        .select_from(LayoutGroup)
        .join(LayoutEvent, LayoutGroup.layout_event_id == LayoutEvent.id)
        .join(LayoutDocument)
        .where(LayoutDocument.corpus_build_id == build.id)
    ).all()
    candidates = [
        (group, event)
        for group, event in groups
        if _fold(group.technical_name) in names
        and (not intent.event_codes or event.event_code in intent.event_codes)
        and all(name in _names(group.source_local_stable_path) for name in names)
    ]
    if not candidates:
        return None
    # Branch-qualified names choose the deepest matching group; ambiguous
    # unqualified names remain multiple source-qualified results.
    depth = max(group.source_local_stable_path.count("/") for group, _ in candidates)
    candidates = [
        (group, event)
        for group, event in candidates
        if group.source_local_stable_path.count("/") == depth
    ]
    if intent.relationship == "CHILDREN":
        parent_ids = {group.id for group, _ in candidates}
        child_paths = [
            field.source_local_stable_path
            for field in session.scalars(
                select(LayoutField).where(LayoutField.layout_group_id.in_(parent_ids))
            ).all()
        ]
        if intent.object_kind != "FIELD":
            child_paths += [
                group.source_local_stable_path
                for group in session.scalars(
                    select(LayoutGroup).where(
                        LayoutGroup.parent_group_id.in_(parent_ids)
                    )
                ).all()
            ]
        return [
            (units_by_path[path], 100.0)
            for path in child_paths
            if path in units_by_path
        ]
    if intent.relationship == "PARENT":
        parent_ids = {
            group.parent_group_id for group, _ in candidates if group.parent_group_id
        }
        paths = session.scalars(
            select(LayoutGroup.source_local_stable_path).where(
                LayoutGroup.id.in_(parent_ids)
            )
        ).all()
        return [(units_by_path[path], 100.0) for path in paths if path in units_by_path]
    if intent.requested_attributes:
        attribute = next(
            (a for a in intent.requested_attributes if a not in {"children", "parent"}),
            None,
        )
        candidates_with_value = [
            group
            for group, _ in candidates
            if attribute and getattr(group, attribute, None) not in (None, "")
        ]
        return [
            (units_by_path[group.source_local_stable_path], 100.0)
            for group in candidates_with_value
            if group.source_local_stable_path in units_by_path
        ]
    return None


def _xsd_relations(session, build, schema, intent, units_by_path):
    names = {_fold(name) for name in intent.technical_tokens}
    if not names:
        return None
    statement = (
        select(XsdElement)
        .join(XsdPackageDocument)
        .where(XsdPackageDocument.corpus_build_id == build.id)
    )
    if schema is not None:
        statement = statement.where(XsdElement.owner_schema_id == schema.id)
    elements = session.scalars(statement).all()
    candidates = [
        item
        for item in elements
        if _fold(item.name) in names
        and all(name in _names(item.source_local_stable_path) for name in names)
    ]
    if not candidates:
        return None
    depth = max(item.source_local_stable_path.count("/") for item in candidates)
    candidates = [
        item for item in candidates if item.source_local_stable_path.count("/") == depth
    ]
    if intent.relationship == "CHILDREN":
        parents = {item.id for item in candidates}
        children = [item for item in elements if item.parent_element_id in parents]
        return [
            (units_by_path[item.source_local_stable_path], 100.0)
            for item in children
            if item.source_local_stable_path in units_by_path
        ]
    if intent.relationship == "PARENT":
        parents = {item.parent_element_id for item in candidates}
        return [
            (units_by_path[item.source_local_stable_path], 100.0)
            for item in elements
            if item.id in parents and item.source_local_stable_path in units_by_path
        ]
    if intent.requested_attributes:
        attribute = intent.requested_attributes[0]
        mapping = {"type": "type_qname", "description": "documentation"}

        def has(item):
            if attribute == "occurrence":
                return item.min_occurs is not None or item.max_occurs is not None
            if attribute == "pattern":
                return bool((item.facets or {}).get("pattern"))
            if attribute == "enum":
                return (
                    session.scalar(
                        select(XsdEnumeration.id)
                        .where(XsdEnumeration.owner_element_id == item.id)
                        .limit(1)
                    )
                    is not None
                )
            return getattr(item, mapping.get(attribute, attribute), None) not in (
                None,
                "",
            )

        return [
            (units_by_path[item.source_local_stable_path], 100.0)
            for item in candidates
            if has(item) and item.source_local_stable_path in units_by_path
        ]
    return None


def operational_search(session, projection, question, limit=20):
    if limit < 1 or not question.strip():
        return []
    units = session.scalars(
        select(SearchUnit).where(SearchUnit.search_projection_id == projection.id)
    ).all()
    known_names = {
        part
        for unit in units
        for part in unit.source_local_stable_path.split("/")
        if part and not part.startswith("http")
    }
    intent = analyze_query(question, known_names)
    by_path = {unit.source_local_stable_path: unit for unit in units}
    family = projection.profile.removesuffix("_ALL")
    build = session.get(CorpusBuild, projection.corpus_build_id)
    schema = None
    if intent.event_codes:
        if family == "XSD":
            if len(intent.event_codes) != 1:
                return []
            schema = _schema_scope(session, build, intent.event_codes[0])
            if schema is None:
                return []
            units = [
                unit
                for unit in units
                if unit.source_local_stable_path == schema.source_local_stable_path
                or unit.source_local_stable_path.startswith(
                    schema.source_local_stable_path + "/"
                )
            ]
        else:
            units = [
                unit
                for unit in units
                if any(
                    f"/{code}/" in unit.source_local_stable_path
                    or unit.source_local_stable_path.endswith(f"/{code}")
                    for code in intent.event_codes
                )
            ]
        by_path = {unit.source_local_stable_path: unit for unit in units}
    if (
        family == "LAYOUT"
        and intent.technical_tokens
        and (intent.relationship or intent.requested_attributes)
    ):
        special = _layout_relations(session, build, intent, by_path)
        if special is not None:
            return _output(special, limit)
    if (
        family == "XSD"
        and intent.technical_tokens
        and (intent.relationship or intent.requested_attributes)
    ):
        special = _xsd_relations(session, build, schema, intent, by_path)
        if special is not None:
            return _output(special, limit)
    scores = _fts_scores(session, projection, intent.normalized_text)
    names = {_fold(name) for name in intent.technical_tokens}
    path_matches = [
        unit
        for unit in units
        if names
        and all(name in _names(unit.source_local_stable_path) for name in names)
    ]
    pool = (
        path_matches if path_matches else [unit for unit in units if unit.id in scores]
    )
    ranked = []
    for unit in pool:
        own_name = _fold(unit.source_local_stable_path.rsplit("/", 1)[-1])
        category = 80 if names and own_name in names else 70 if path_matches else 40
        ranked.append((unit, category + float(scores.get(unit.id, 0))))
    return _output(ranked, limit)


def _output(rows, limit):
    rows = sorted(rows, key=lambda item: (-item[1], item[0].source_local_stable_path))[
        :limit
    ]
    return [
        {
            "id": unit.id,
            "source_local_stable_path": unit.source_local_stable_path,
            "title": unit.title,
            "document_family": unit.document_family,
            "unit_kind": unit.unit_kind,
            "search_text": unit.search_text,
            "root_citation_target_id": unit.root_citation_target_id,
            "score": score,
        }
        for unit, score in rows
    ]
