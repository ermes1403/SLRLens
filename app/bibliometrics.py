from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering


COUNTRY_ALIASES = {
    "united states": "United States", "usa": "United States", "u.s.a.": "United States",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "italy": "Italy", "italia": "Italy", "germany": "Germany", "france": "France",
    "spain": "Spain", "canada": "Canada", "china": "China", "india": "India",
    "australia": "Australia", "brazil": "Brazil", "netherlands": "Netherlands",
    "sweden": "Sweden", "norway": "Norway", "finland": "Finland", "denmark": "Denmark",
    "switzerland": "Switzerland", "austria": "Austria", "belgium": "Belgium",
    "portugal": "Portugal", "greece": "Greece", "ireland": "Ireland",
    "japan": "Japan", "south korea": "South Korea", "korea": "South Korea",
    "singapore": "Singapore", "malaysia": "Malaysia", "indonesia": "Indonesia",
    "saudi arabia": "Saudi Arabia", "united arab emirates": "United Arab Emirates",
    "turkey": "Turkey", "türkiye": "Turkey", "israel": "Israel", "poland": "Poland",
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "romania": "Romania", "hungary": "Hungary", "mexico": "Mexico",
    "chile": "Chile", "argentina": "Argentina", "colombia": "Colombia",
    "new zealand": "New Zealand", "south africa": "South Africa",
    "russian federation": "Russia", "russia": "Russia", "taiwan": "Taiwan",
}


def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _split(value: Any, separators: str = r";|\|") -> list[str]:
    return [
        item.strip(" ,.")
        for item in re.split(separators, _clean(value))
        if item.strip(" ,.")
    ]


def _authors(value: Any) -> list[str]:
    # Scopus exports authors with semicolons; comma is part of "Surname, Name".
    return _split(value)


def _keywords(row: pd.Series) -> list[str]:
    values: list[str] = []
    for column in ("keywords", "index_keywords"):
        for term in _split(row.get(column, "")):
            normalized = re.sub(r"\s+", " ", term.lower()).strip()
            if 2 < len(normalized) <= 80:
                values.append(normalized)
    return list(dict.fromkeys(values))


def _countries(value: Any) -> list[str]:
    text = _clean(value).lower()
    found: list[str] = []
    for alias, canonical in COUNTRY_ALIASES.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text):
            found.append(canonical)
    return list(dict.fromkeys(found))


def _affiliations(value: Any) -> list[str]:
    affiliations = []
    for item in _split(value):
        parts = [part.strip() for part in item.split(",") if part.strip()]
        if parts:
            affiliations.append(parts[0])
    return list(dict.fromkeys(affiliations))


def _references(value: Any) -> list[str]:
    references = []
    for item in _split(value):
        key = re.sub(r"\s+", " ", item.lower()).strip(" .;,")
        if len(key) >= 12:
            references.append(key)
    return list(dict.fromkeys(references))


def _ranked(counter: Counter, limit: int = 20, key: str = "papers") -> list[dict[str, Any]]:
    return [{"name": name, key: int(count)} for name, count in counter.most_common(limit)]


def _impact_index(citations: Iterable[int], first_year: int, current_year: int) -> dict[str, float]:
    ordered = sorted((max(0, int(value)) for value in citations), reverse=True)
    h = sum(value >= rank for rank, value in enumerate(ordered, 1))
    cumulative = 0
    g = 0
    for rank, value in enumerate(ordered, 1):
        cumulative += value
        if cumulative >= rank * rank:
            g = rank
    career = max(1, current_year - first_year + 1)
    return {"h_index": h, "g_index": g, "m_index": h / career}


def _network(edges: Counter, node_counts: Counter, limit: int = 45) -> dict[str, Any]:
    allowed = {name for name, _ in node_counts.most_common(limit)}
    filtered = [
        (left, right, weight)
        for (left, right), weight in edges.most_common(limit * 4)
        if left in allowed and right in allowed
    ]
    degree = Counter()
    for left, right, weight in filtered:
        degree[left] += weight
        degree[right] += weight
    nodes = [
        {"id": name, "label": name, "papers": int(node_counts[name]), "degree": int(degree[name])}
        for name in allowed if degree[name] or len(allowed) == 1
    ]
    return {
        "nodes": sorted(nodes, key=lambda item: (-item["degree"], item["label"])),
        "edges": [
            {"source": left, "target": right, "weight": int(weight)}
            for left, right, weight in filtered
        ],
    }


def _label_communities(network: dict[str, Any]) -> dict[str, int]:
    names = [node["id"] for node in network["nodes"]]
    if len(names) < 4:
        return {name: index + 1 for index, name in enumerate(names)}
    index = {name: position for position, name in enumerate(names)}
    adjacency = np.zeros((len(names), len(names)), dtype=float)
    for edge in network["edges"]:
        left = index.get(edge["source"])
        right = index.get(edge["target"])
        if left is not None and right is not None:
            adjacency[left, right] = edge["weight"]
            adjacency[right, left] = edge["weight"]
    degree = adjacency.sum(axis=1)
    denominator = np.sqrt(np.outer(np.maximum(degree, 1), np.maximum(degree, 1)))
    similarity = np.divide(adjacency, denominator, out=np.zeros_like(adjacency), where=denominator > 0)
    distance = 1 - similarity
    np.fill_diagonal(distance, 0)
    cluster_count = min(7, max(3, round(math.sqrt(len(names)) / 1.7)))
    labels = AgglomerativeClustering(
        n_clusters=cluster_count,
        metric="precomputed",
        linkage="average",
    ).fit_predict(distance)
    return {name: int(labels[position]) + 1 for position, name in enumerate(names)}


def _thematic_map(network: dict[str, Any]) -> list[dict[str, Any]]:
    communities = _label_communities(network)
    internal = Counter()
    external = Counter()
    keywords: dict[int, Counter] = defaultdict(Counter)
    papers = {node["id"]: node["papers"] for node in network["nodes"]}
    for node, community in communities.items():
        keywords[community][node] = papers.get(node, 0)
    for edge in network["edges"]:
        left = communities.get(edge["source"])
        right = communities.get(edge["target"])
        if left is None or right is None:
            continue
        if left == right:
            internal[left] += edge["weight"]
        else:
            external[left] += edge["weight"]
            external[right] += edge["weight"]
    output = []
    for community, terms in keywords.items():
        size = max(1, len(terms))
        output.append({
            "cluster": community,
            "label": " · ".join(term for term, _ in terms.most_common(3)),
            "keywords": [term for term, _ in terms.most_common(8)],
            "centrality": float(external[community]),
            "density": float(internal[community] / size),
            "documents": int(sum(terms.values())),
        })
    if output:
        centrality_median = float(np.median([item["centrality"] for item in output]))
        density_median = float(np.median([item["density"] for item in output]))
        for item in output:
            item["centrality_relative"] = item["centrality"] - centrality_median
            item["density_relative"] = item["density"] - density_median
    return sorted(output, key=lambda item: (-item["centrality"], -item["density"]))


def _bradford(sources: Counter) -> dict[str, Any]:
    ranked = sources.most_common()
    total = sum(sources.values())
    if not ranked:
        return {"zones": [], "nucleus_sources": [], "target_papers_per_zone": 0}
    target = total / 3
    zones: list[dict[str, Any]] = []
    zone = 1
    zone_sources = 0
    zone_papers = 0
    nucleus = []
    cumulative = 0
    for name, papers in ranked:
        if zone < 3 and zone_papers >= target:
            zones.append({"zone": zone, "sources": zone_sources, "papers": zone_papers})
            zone += 1
            zone_sources = 0
            zone_papers = 0
        zone_sources += 1
        zone_papers += papers
        cumulative += papers
        if zone == 1:
            nucleus.append({"name": name, "papers": int(papers), "cumulative": int(cumulative)})
    zones.append({"zone": zone, "sources": zone_sources, "papers": zone_papers})
    return {"zones": zones, "nucleus_sources": nucleus, "target_papers_per_zone": target}


def _lotka(author_counts: Counter) -> dict[str, Any]:
    distribution = Counter(author_counts.values())
    points = sorted((papers, authors) for papers, authors in distribution.items() if papers > 0)
    usable = [(math.log(papers), math.log(authors)) for papers, authors in points if authors > 0]
    beta = float(-np.polyfit(*zip(*usable), 1)[0]) if len(usable) >= 2 else 0.0
    single = distribution.get(1, 0)
    return {
        "distribution": [{"papers": papers, "authors": authors} for papers, authors in points],
        "estimated_beta": beta,
        "single_publication_rate": single / max(sum(distribution.values()), 1),
    }


def calculate_bibliometrics(
    selected: pd.DataFrame,
    assignments: np.ndarray,
    current_year: int,
) -> dict[str, Any]:
    sources = Counter(value for value in selected["source"] if value)
    types = Counter(value for value in selected["document_type"] if value)
    languages = Counter(value for value in selected["language"] if value)
    citations = selected["citations_num"].to_numpy()
    annualized = selected["avg_citations_num"].to_numpy(dtype=float)
    open_access_count = int(selected["open_access"].str.len().gt(0).sum())

    years = Counter(int(year) for year in selected["year_num"] if int(year) > 0)
    annual_production = [{"year": year, "papers": count} for year, count in sorted(years.items())]
    valid_years = sorted(years)
    growth_rate = 0.0
    if len(valid_years) > 1 and years[valid_years[0]] > 0:
        span = valid_years[-1] - valid_years[0]
        growth_rate = (
            (years[valid_years[-1]] / years[valid_years[0]]) ** (1 / span) - 1
            if span > 0 else 0.0
        )

    author_counts: Counter = Counter()
    author_fractional: Counter = Counter()
    author_citations: dict[str, list[int]] = defaultdict(list)
    author_years: dict[str, list[int]] = defaultdict(list)
    coauthor_edges: Counter = Counter()
    affiliations: Counter = Counter()
    countries: Counter = Counter()
    country_edges: Counter = Counter()
    country_scp: Counter = Counter()
    country_mcp: Counter = Counter()
    keyword_counts: Counter = Counter()
    keyword_edges: Counter = Counter()
    source_by_year: dict[str, Counter] = defaultdict(Counter)
    keyword_by_year: dict[str, Counter] = defaultdict(Counter)
    reference_counts: Counter = Counter()
    reference_edges: Counter = Counter()
    coupling_edges: Counter = Counter()
    author_keyword_flows: Counter = Counter()
    keyword_source_flows: Counter = Counter()
    keyword_edges_by_year: dict[int, Counter] = defaultdict(Counter)
    keyword_counts_by_year: dict[int, Counter] = defaultdict(Counter)
    references_by_doc: list[set[str]] = []

    for index, row in selected.iterrows():
        row_authors = _authors(row["authors"])
        for author in row_authors:
            author_counts[author] += 1
            author_fractional[author] += 1 / max(len(row_authors), 1)
            author_citations[author].append(int(row["citations_num"]))
            if int(row["year_num"]) > 0:
                author_years[author].append(int(row["year_num"]))
        for pair in combinations(sorted(set(row_authors)), 2):
            coauthor_edges[pair] += 1

        row_affiliations = _affiliations(row.get("affiliations", ""))
        affiliations.update(row_affiliations)
        row_countries = _countries(
            f"{row.get('affiliations', '')}; {row.get('correspondence_address', '')}"
        )
        countries.update(row_countries)
        if len(row_countries) <= 1:
            country_scp.update(row_countries)
        else:
            country_mcp.update(row_countries)
        for pair in combinations(sorted(set(row_countries)), 2):
            country_edges[pair] += 1

        row_keywords = _keywords(row)
        keyword_counts.update(row_keywords)
        for pair in combinations(sorted(row_keywords), 2):
            keyword_edges[pair] += 1
        year = int(row["year_num"])
        if year > 0:
            keyword_by_year[str(year)].update(row_keywords)
            keyword_counts_by_year[year].update(row_keywords)
            for pair in combinations(sorted(row_keywords), 2):
                keyword_edges_by_year[year][pair] += 1
            if row["source"]:
                source_by_year[row["source"]][year] += 1
        for author in row_authors[:8]:
            for keyword in row_keywords[:12]:
                author_keyword_flows[(author, keyword)] += 1
        if row["source"]:
            for keyword in row_keywords[:12]:
                keyword_source_flows[(keyword, row["source"])] += 1

        refs = set(_references(row.get("references", "")))
        references_by_doc.append(refs)
        reference_counts.update(refs)
        for pair in combinations(sorted(refs), 2):
            reference_edges[pair] += 1

    for left, right in combinations(range(len(references_by_doc)), 2):
        shared = len(references_by_doc[left] & references_by_doc[right])
        if shared:
            coupling_edges[(selected.iloc[left]["title"], selected.iloc[right]["title"])] = shared

    collaboration_documents = sum(1 for value in selected["authors"] if len(_authors(value)) > 1)
    all_authors = sum(len(_authors(value)) for value in selected["authors"])
    author_rows = []
    for author, papers in author_counts.most_common(30):
        indices = _impact_index(
            author_citations[author],
            min(author_years[author], default=current_year),
            current_year,
        )
        author_rows.append({
            "name": author,
            "papers": int(papers),
            "fractional_papers": float(author_fractional[author]),
            "citations": int(sum(author_citations[author])),
            **indices,
        })

    topic_impact = []
    for topic in sorted(set(assignments)):
        values = citations[assignments == topic]
        topic_impact.append({
            "topic": int(topic) + 1,
            "papers": int(len(values)),
            "citations": int(values.sum()),
            "mean_citations": float(values.mean()) if len(values) else 0.0,
            "mean_annualized_citations": float(annualized[assignments == topic].mean()) if len(values) else 0.0,
        })

    keyword_network = _network(keyword_edges, keyword_counts, 45)
    reference_available = any(references_by_doc)
    top_keyword_trends = []
    for keyword, total in keyword_counts.most_common(20):
        series = [
            {"year": int(year), "papers": counts.get(keyword, 0)}
            for year, counts in sorted(keyword_by_year.items(), key=lambda item: int(item[0]))
        ]
        top_keyword_trends.append({"keyword": keyword, "total": int(total), "series": series})

    thematic_evolution = {"slices": [], "flows": []}
    if len(valid_years) >= 2:
        midpoint = valid_years[len(valid_years) // 2]
        ranges = [
            (valid_years[0], midpoint - 1),
            (midpoint, valid_years[-1]),
        ]
        slice_clusters: list[list[dict[str, Any]]] = []
        for start, end in ranges:
            counts = Counter()
            edges = Counter()
            for year in range(start, end + 1):
                counts.update(keyword_counts_by_year[year])
                edges.update(keyword_edges_by_year[year])
            themes = _thematic_map(_network(edges, counts, 35))
            normalized = [
                {
                    "id": f"{start}-{end}:{theme['cluster']}",
                    "label": theme["label"],
                    "keywords": theme["keywords"],
                    "start_year": start,
                    "end_year": end,
                    "documents": theme["documents"],
                }
                for theme in themes[:10]
            ]
            slice_clusters.append(normalized)
            thematic_evolution["slices"].append({
                "start_year": start, "end_year": end, "themes": normalized
            })
        if len(slice_clusters) == 2:
            for left in slice_clusters[0]:
                left_terms = set(left["keywords"])
                for right in slice_clusters[1]:
                    right_terms = set(right["keywords"])
                    union = left_terms | right_terms
                    overlap = len(left_terms & right_terms) / max(len(union), 1)
                    if overlap > 0:
                        thematic_evolution["flows"].append({
                            "source": left["id"], "target": right["id"],
                            "jaccard": overlap,
                            "shared_keywords": sorted(left_terms & right_terms),
                        })
            thematic_evolution["flows"].sort(key=lambda item: -item["jaccard"])

    most_cited = selected.sort_values("citations_num", ascending=False).head(20)
    return {
        "total_citations": int(citations.sum()),
        "mean_citations": float(citations.mean()) if len(citations) else 0.0,
        "median_citations": float(np.median(citations)) if len(citations) else 0.0,
        "mean_annualized_citations": float(annualized.mean()) if len(annualized) else 0.0,
        "open_access_count": open_access_count,
        "open_access_rate": open_access_count / max(len(selected), 1),
        "sources_count": len(sources),
        "authors_count": len(author_counts),
        "countries_count": len(countries),
        "annual_growth_rate": growth_rate,
        "annual_production": annual_production,
        "collaboration": {
            "multi_authored_documents": collaboration_documents,
            "multi_authored_rate": collaboration_documents / max(len(selected), 1),
            "authors_per_document": all_authors / max(len(selected), 1),
            "collaboration_index": all_authors / max(collaboration_documents, 1),
        },
        "top_sources": _ranked(sources),
        "source_dynamics": [
            {"name": name, "series": [{"year": year, "papers": count} for year, count in sorted(source_by_year[name].items())]}
            for name, _ in sources.most_common(10)
        ],
        "bradford": _bradford(sources),
        "authors": author_rows,
        "lotka": _lotka(author_counts),
        "coauthor_network": _network(coauthor_edges, author_counts, 45),
        "top_affiliations": _ranked(affiliations),
        "countries": [
            {
                "name": name, "papers": int(count),
                "scp": int(country_scp[name]), "mcp": int(country_mcp[name]),
                "mcp_rate": country_mcp[name] / max(count, 1),
            }
            for name, count in countries.most_common(30)
        ],
        "country_network": _network(country_edges, countries, 40),
        "document_types": _ranked(types),
        "languages": _ranked(languages),
        "most_cited_documents": [
            {
                "title": row["title"], "year": int(row["year_num"]),
                "citations": int(row["citations_num"]), "doi": row["doi"],
                "source": row["source"],
            }
            for _, row in most_cited.iterrows()
        ],
        "topic_impact": topic_impact,
        "conceptual": {
            "keyword_network": keyword_network,
            "thematic_map": _thematic_map(keyword_network),
            "trend_topics": top_keyword_trends,
            "thematic_evolution": thematic_evolution,
            "three_fields": {
                "author_keyword": [
                    {"source": left, "target": right, "weight": int(weight)}
                    for (left, right), weight in author_keyword_flows.most_common(40)
                ],
                "keyword_source": [
                    {"source": left, "target": right, "weight": int(weight)}
                    for (left, right), weight in keyword_source_flows.most_common(40)
                ],
            },
        },
        "intellectual": {
            "available": reference_available,
            "reason": None if reference_available else (
                "L'export non contiene le cited references. Co-citazione e bibliographic "
                "coupling richiedono il campo References/Cited references."
            ),
            "references_coverage": sum(bool(value) for value in references_by_doc) / max(len(selected), 1),
            "top_references": _ranked(reference_counts, 25, "citations"),
            "cocitation_network": _network(reference_edges, reference_counts, 35) if reference_available else {"nodes": [], "edges": []},
            "bibliographic_coupling": [
                {"source": left, "target": right, "shared_references": int(weight)}
                for (left, right), weight in coupling_edges.most_common(80)
            ] if reference_available else [],
        },
        "methodology": {
            "bradford": "Fonti ordinate per produttività e suddivise in tre zone con circa un terzo degli articoli ciascuna.",
            "lotka": "Distribuzione osservata della produttività autoriale; beta stimato con regressione log-log.",
            "author_impact": "h, g e m-index calcolati sulle citazioni presenti nel corpus importato.",
            "networks": "Archi pesati per co-occorrenza nello stesso documento; comunità con label propagation deterministica.",
            "thematic_map": "Centralità = legami esterni pesati; densità = legami interni pesati per keyword.",
            "thematic_evolution": "Cluster di keyword in due finestre temporali collegati tramite similarità di Jaccard.",
            "three_fields": "Flussi pesati Autori → Keyword → Fonti osservati nei record importati.",
            "reference_gate": "Le analisi intellettuali sono eseguite solo se le cited references sono presenti.",
        },
    }
