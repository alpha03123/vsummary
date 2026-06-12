from __future__ import annotations

from llama_index.core.vector_stores import FilterCondition, FilterOperator, MetadataFilter, MetadataFilters


def build_filters(
    *,
    scope_type: str,
    series_id: str,
    video_id: str,
    target_source: str,
    source_tags: list[str],
) -> MetadataFilters:
    filters: list[MetadataFilter | MetadataFilters] = [
        MetadataFilter(key="series_id", value=series_id),
    ]
    if scope_type == "video":
        filters.append(MetadataFilter(key="video_id", value=video_id))
    family_filters = build_source_family_filters(source_tags, target_source=target_source)
    if family_filters:
        if len(family_filters) == 1:
            filters.append(family_filters[0])
        else:
            filters.append(MetadataFilters(filters=family_filters, condition=FilterCondition.OR))
    return MetadataFilters(filters=filters, condition=FilterCondition.AND)


def build_source_family_filters(
    source_tags: list[str],
    *,
    target_source: str,
) -> list[MetadataFilter]:
    if source_tags:
        families = []
        for tag in source_tags:
            if tag == "summary":
                families.append("summary")
            elif tag == "transcript":
                families.append("transcript")
            elif tag == "notes":
                families.append("notes")
            elif tag == "cards":
                families.append("cards")
        if families:
            unique_families = list(dict.fromkeys(families))
            if len(unique_families) == 1:
                return [MetadataFilter(key="source_family", value=unique_families[0])]
            return [
                MetadataFilter(
                    key="source_family",
                    value=unique_families,
                    operator=FilterOperator.IN,
                )
            ]
    if target_source == "summary":
        return [MetadataFilter(key="source_family", value="summary")]
    if target_source == "transcript":
        return [MetadataFilter(key="source_family", value="transcript")]
    return []
