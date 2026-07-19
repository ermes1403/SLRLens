from __future__ import annotations

import math
import re
import time
import hashlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy import sparse
from scipy.optimize import linear_sum_assignment
from scipy.stats import rankdata
from sklearn.decomposition import LatentDirichletAllocation, TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.manifold import TSNE


COLUMN_ALIASES = {
    "title": ("title", "document title", "titolo"),
    "abstract": ("abstract", "description", "riassunto"),
    "year": ("year", "publication year", "anno"),
    "authors": ("author full names", "authors", "author(s)", "autori"),
    "keywords": ("author keywords", "index keywords", "keywords", "parole chiave"),
    "doi": ("doi",),
    "eid": ("eid", "scopus id", "document id", "id"),
    "source": ("source title", "publication name", "journal", "source"),
    "document_type": ("document type", "type"),
    "citations": ("cited by", "citations", "citation count", "scopus citations"),
    "avg_citations_year": ("avg citations year", "avg_citations_year", "citations per year"),
    "open_access": ("open access", "openaccess"),
    "language": ("language of original document", "language"),
    "link": ("link", "url"),
    "issn": ("issn",),
    "source_database": ("paper source db", "paper_source_db", "source database"),
}

GENERIC_STOP_WORDS = {
    "study", "studies", "paper", "papers", "research", "result", "results",
    "method", "methods", "analysis", "approach", "approaches", "using", "use",
    "used", "based", "proposed", "provide", "provides", "show", "shows", "also",
    "however", "including", "new", "different", "data", "system", "systems",
    "model", "models", "work", "works", "article", "authors", "author",
    "future", "current", "various", "several", "aim", "aims", "present",
}

PHRASE_NORMALIZATION = (
    (r"\blarge[\s-]+language[\s-]+models?\b|\bllms?\b", "large_language_model"),
    (r"\bgenerative[\s-]+artificial[\s-]+intelligence\b|\bgenerative[\s-]+ai\b|\bgenai\b", "generative_ai"),
    (r"\bartificial[\s-]+intelligence\b", "artificial_intelligence"),
    (r"\bsoftware[\s-]+development[\s-]+life[\s-]+cycle\b|\bsdle\b|\bsdlc\b", "software_development_lifecycle"),
    (r"\brequirements?[\s-]+engineering\b", "requirements_engineering"),
    (r"\bsoftware[\s-]+engineering\b", "software_engineering"),
    (r"\bsoftware[\s-]+development\b", "software_development"),
    (r"\bsoftware[\s-]+testing\b", "software_testing"),
    (r"\btest[\s-]+cases?[\s-]+generation\b|\bautomated[\s-]+test[\s-]+generation\b", "test_case_generation"),
    (r"\bcode[\s-]+generation\b", "code_generation"),
    (r"\bprogram[\s-]+repair\b|\bautomatic[\s-]+program[\s-]+repair\b", "program_repair"),
    (r"\bmulti[\s-]+agents?\b|\bmultiagent\b", "multi_agent"),
    (r"\bhuman[\s-]+in[\s-]+the[\s-]+loop\b|\bhitl\b", "human_in_the_loop"),
    (r"\bretrieval[\s-]+augmented[\s-]+generation\b|\brag\b", "retrieval_augmented_generation"),
    (r"\bnatural[\s-]+language[\s-]+processing\b|\bnlp\b", "natural_language_processing"),
)

BOILERPLATE_PATTERNS = (
    r"©.*$",
    r"\bcopyright\s+(?:held|owned|reserved).*?$",
    r"\ball rights reserved.*?$",
    r"\bthe author\(s\), under exclusive licence.*?$",
    r"\bpublished by .*?$",
)


def _norm(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in {"nan", "none", "n/a", "0"} else text


def _find_column(df: pd.DataFrame, logical: str) -> str | None:
    normalized = {
        re.sub(r"[_\s]+", " ", str(column).strip().lower()): column
        for column in df.columns
    }
    for alias in COLUMN_ALIASES[logical]:
        key = re.sub(r"[_\s]+", " ", alias.strip().lower())
        if key in normalized:
            return normalized[key]
    return None


def clean_scientific_text(value: str) -> str:
    text = _norm(value).lower()
    for pattern in BOILERPLATE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    for pattern, replacement in PHRASE_NORMALIZATION:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:https?://|www\.)\S+\b", " ", text)
    text = re.sub(r"\b(?:doi|issn|isbn)\s*:\s*\S+", " ", text)
    text = re.sub(r"[^a-z0-9_\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _weighted_text(row: pd.Series) -> str:
    # Title and author keywords contain much less boilerplate and carry more semantic signal.
    title = clean_scientific_text(row["title"])
    abstract = clean_scientific_text(row["abstract"])
    keywords = clean_scientific_text(row["keywords"].replace(";", " "))
    return " ".join([title, title, abstract, keywords, keywords, keywords]).strip()


def normalize_dataset(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    columns = {name: _find_column(raw, name) for name in COLUMN_ALIASES}
    if not columns["title"]:
        raise ValueError("Colonna titolo non trovata. Esporta almeno Title e Abstract.")

    data = pd.DataFrame()
    for name, source in columns.items():
        data[name] = raw[source].map(_norm) if source else ""

    data["title"] = data["title"].replace("", pd.NA)
    before_empty = len(data)
    data = data.dropna(subset=["title"]).copy()
    empty_removed = before_empty - len(data)
    for column in ("title", "abstract", "keywords"):
        data[column] = data[column].fillna("").astype(str)

    data["text"] = data.apply(_weighted_text, axis=1)
    data["_doi_key"] = (
        data["doi"].str.lower().str.replace(r"https?://(dx\.)?doi\.org/", "", regex=True)
    )
    data["_title_key"] = (
        data["title"].str.lower().str.replace(r"[^a-z0-9]+", "", regex=True)
    )
    valid_doi = data["_doi_key"].str.match(r"^10\.\d{4,9}/\S+$", na=False)
    valid_eid = data["eid"].str.len().gt(3)
    data["_dedupe_key"] = np.where(
        valid_doi,
        "doi:" + data["_doi_key"],
        np.where(valid_eid, "eid:" + data["eid"].str.lower(), "title:" + data["_title_key"]),
    )
    before_dedupe = len(data)
    data = data.drop_duplicates("_dedupe_key", keep="first").reset_index(drop=True)
    duplicates_removed = before_dedupe - len(data)
    data["id"] = [f"paper-{index + 1}" for index in range(len(data))]
    data["year_num"] = pd.to_numeric(data["year"], errors="coerce").fillna(0).astype(int)
    data["citations_num"] = pd.to_numeric(data["citations"], errors="coerce").fillna(0).astype(int)
    data["avg_citations_num"] = pd.to_numeric(
        data["avg_citations_year"], errors="coerce"
    ).fillna(0.0)
    meaningful_abstracts = int(data["abstract"].str.len().gt(20).sum())
    meaningful_keywords = int(data["keywords"].str.len().gt(2).sum())
    valid_dois = int(data["_doi_key"].str.match(r"^10\.\d{4,9}/\S+$", na=False).sum())
    return data, {
        "imported": int(len(raw)),
        "empty_titles_removed": int(empty_removed),
        "duplicates_removed": int(duplicates_removed),
        "unique": int(len(data)),
        "abstracts_available": meaningful_abstracts,
        "keywords_available": meaningful_keywords,
        "valid_dois": valid_dois,
    }


def public_papers(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "id": row.id,
            "title": row.title,
            "authors": row.authors,
            "year": int(row.year_num) if row.year_num else None,
            "source": row.source,
            "document_type": row.document_type,
            "citations": int(row.citations_num),
            "has_abstract": bool(row.abstract),
            "doi": row.doi,
            "open_access": bool(row.open_access),
        }
        for row in data.itertuples()
    ]


def _binary_matrix(matrix: sparse.csr_matrix) -> sparse.csr_matrix:
    binary = matrix.copy()
    binary.data = np.ones_like(binary.data)
    return binary


def _coherence_umass(
    binary: sparse.csr_matrix,
    document_frequency: np.ndarray,
    topic_words: np.ndarray,
) -> float:
    scores = []
    for later in range(1, len(topic_words)):
        for earlier in range(later):
            wi, wj = int(topic_words[later]), int(topic_words[earlier])
            cooccur = float(binary[:, wi].multiply(binary[:, wj]).sum())
            scores.append(math.log((cooccur + 1.0) / max(float(document_frequency[wj]), 1.0)))
    return float(np.mean(scores)) if scores else 0.0


def _coherence_npmi(
    binary: sparse.csr_matrix,
    document_frequency: np.ndarray,
    topic_words: np.ndarray,
) -> float:
    documents = binary.shape[0]
    scores = []
    for first, second in combinations(topic_words, 2):
        cooccur = float(binary[:, int(first)].multiply(binary[:, int(second)]).sum())
        if cooccur <= 0:
            scores.append(-1.0)
            continue
        pxy = cooccur / documents
        px = max(float(document_frequency[int(first)]) / documents, 1e-12)
        py = max(float(document_frequency[int(second)]) / documents, 1e-12)
        scores.append(math.log(pxy / (px * py)) / -math.log(pxy))
    return float(np.mean(scores)) if scores else -1.0


def _topic_diversity(top_words: np.ndarray) -> float:
    return float(len(set(top_words.ravel())) / max(top_words.size, 1))


def _topic_exclusivity(model: LatentDirichletAllocation, top_words: np.ndarray) -> float:
    normalized = model.components_ / np.maximum(model.components_.sum(axis=1, keepdims=True), 1e-12)
    across_topics = normalized.sum(axis=0)
    scores = []
    for topic_index, word_indices in enumerate(top_words):
        scores.extend(
            float(normalized[topic_index, word] / max(across_topics[word], 1e-12))
            for word in word_indices
        )
    return float(np.mean(scores)) if scores else 0.0


def _component_set_stability(component_matrices: list[np.ndarray], top_n: int = 15) -> float:
    if len(component_matrices) < 2:
        return 1.0
    model_sets = [
        [set(np.argsort(component)[-top_n:]) for component in components]
        for components in component_matrices
    ]
    pair_scores = []
    for first, second in combinations(model_sets, 2):
        similarities = np.array([
            [len(a & b) / max(len(a | b), 1) for b in second]
            for a in first
        ])
        rows, cols = linear_sum_assignment(-similarities)
        pair_scores.append(float(similarities[rows, cols].mean()))
    return float(np.mean(pair_scores)) if pair_scores else 1.0


def _topic_set_stability(models: list[LatentDirichletAllocation], top_n: int = 15) -> float:
    return _component_set_stability([model.components_ for model in models], top_n)


@dataclass
class FitResult:
    model: LatentDirichletAllocation
    seed: int
    perplexity: float
    log_likelihood_per_word: float
    coherence_umass: float
    coherence_npmi: float
    diversity: float
    exclusivity: float
    seconds: float


@dataclass
class Candidate:
    topics: int
    model: LatentDirichletAllocation
    perplexity: float
    log_likelihood_per_word: float
    coherence_umass: float
    coherence_npmi: float
    diversity: float
    exclusivity: float
    stability: float
    seconds: float
    runs: int
    selection_score: float = field(default=0.0)


@dataclass
class LsiFitResult:
    model: TruncatedSVD
    seed: int
    coherence_umass: float
    coherence_npmi: float
    diversity: float
    explained_variance: float
    seconds: float


@dataclass
class LsiCandidate:
    topics: int
    model: TruncatedSVD
    coherence_umass: float
    coherence_npmi: float
    diversity: float
    stability: float
    explained_variance: float
    seconds: float
    runs: int
    selection_score: float = field(default=0.0)


def _fit_once(
    matrix: sparse.csr_matrix,
    binary: sparse.csr_matrix,
    document_frequency: np.ndarray,
    topics: int,
    iterations: int,
    seed: int,
    learning_method: str,
) -> FitResult:
    started = time.perf_counter()
    model = LatentDirichletAllocation(
        n_components=topics,
        max_iter=iterations,
        learning_method=learning_method,
        batch_size=128,
        evaluate_every=-1,
        random_state=seed,
        n_jobs=1,
        doc_topic_prior=1.0 / topics,
        topic_word_prior=0.01,
    )
    model.fit(matrix)
    perplexity = float(model.perplexity(matrix))
    top_words = np.argsort(model.components_, axis=1)[:, -10:][:, ::-1]
    umass = float(np.mean([
        _coherence_umass(binary, document_frequency, words) for words in top_words
    ]))
    npmi = float(np.mean([
        _coherence_npmi(binary, document_frequency, words) for words in top_words
    ]))
    return FitResult(
        model=model,
        seed=seed,
        perplexity=perplexity,
        log_likelihood_per_word=-math.log(max(perplexity, 1e-12)),
        coherence_umass=umass,
        coherence_npmi=npmi,
        diversity=_topic_diversity(top_words),
        exclusivity=_topic_exclusivity(model, top_words),
        seconds=time.perf_counter() - started,
    )


def _aggregate_candidate(topics: int, fits: list[FitResult]) -> Candidate:
    stability = _topic_set_stability([fit.model for fit in fits])
    # The representative run is the medoid-like best balance of both coherence metrics.
    umass_values = np.array([fit.coherence_umass for fit in fits])
    npmi_values = np.array([fit.coherence_npmi for fit in fits])
    representative_index = int(np.argmax(
        (umass_values - umass_values.mean()) / max(umass_values.std(), 1e-9)
        + (npmi_values - npmi_values.mean()) / max(npmi_values.std(), 1e-9)
    )) if len(fits) > 1 else 0
    representative = fits[representative_index]
    return Candidate(
        topics=topics,
        model=representative.model,
        perplexity=float(np.mean([fit.perplexity for fit in fits])),
        log_likelihood_per_word=float(np.mean([fit.log_likelihood_per_word for fit in fits])),
        coherence_umass=float(np.mean(umass_values)),
        coherence_npmi=float(np.mean(npmi_values)),
        diversity=float(np.mean([fit.diversity for fit in fits])),
        exclusivity=float(np.mean([fit.exclusivity for fit in fits])),
        stability=stability,
        seconds=float(sum(fit.seconds for fit in fits)),
        runs=len(fits),
    )


def _rank_candidates(candidates: list[Candidate]) -> None:
    if len(candidates) == 1:
        candidates[0].selection_score = 1.0
        return

    metrics = {
        "coherence_umass": (0.28, True),
        "coherence_npmi": (0.28, True),
        "stability": (0.22, True),
        "diversity": (0.10, True),
        "exclusivity": (0.07, True),
        "perplexity": (0.05, False),
    }
    totals = np.zeros(len(candidates))
    for attribute, (weight, higher_is_better) in metrics.items():
        values = np.array([getattr(candidate, attribute) for candidate in candidates], dtype=float)
        order = rankdata(values, method="average") - 1.0
        if not higher_is_better:
            order = len(values) - 1 - order
        percentile = order / max(len(values) - 1, 1)
        totals += weight * percentile
    for candidate, score in zip(candidates, totals):
        candidate.selection_score = float(score)


def _oriented_lsi_components(model: TruncatedSVD) -> np.ndarray:
    components = model.components_.copy()
    for index, component in enumerate(components):
        pivot = int(np.argmax(np.abs(component)))
        if component[pivot] < 0:
            components[index] *= -1
    return components


def _fit_lsi_once(
    tfidf: sparse.csr_matrix,
    binary: sparse.csr_matrix,
    document_frequency: np.ndarray,
    topics: int,
    iterations: int,
    seed: int,
) -> LsiFitResult:
    started = time.perf_counter()
    model = TruncatedSVD(
        n_components=topics,
        algorithm="randomized",
        n_iter=iterations,
        random_state=seed,
    )
    model.fit(tfidf)
    components = _oriented_lsi_components(model)
    top_words = np.argsort(components, axis=1)[:, -10:][:, ::-1]
    return LsiFitResult(
        model=model,
        seed=seed,
        coherence_umass=float(np.mean([
            _coherence_umass(binary, document_frequency, words) for words in top_words
        ])),
        coherence_npmi=float(np.mean([
            _coherence_npmi(binary, document_frequency, words) for words in top_words
        ])),
        diversity=_topic_diversity(top_words),
        explained_variance=float(model.explained_variance_ratio_.sum()),
        seconds=time.perf_counter() - started,
    )


def _aggregate_lsi_candidate(topics: int, fits: list[LsiFitResult]) -> LsiCandidate:
    stability = _component_set_stability([
        _oriented_lsi_components(fit.model) for fit in fits
    ])
    umass = np.array([fit.coherence_umass for fit in fits])
    npmi = np.array([fit.coherence_npmi for fit in fits])
    if len(fits) > 1:
        balanced = (
            (umass - umass.mean()) / max(umass.std(), 1e-9)
            + (npmi - npmi.mean()) / max(npmi.std(), 1e-9)
        )
        representative = fits[int(np.argmax(balanced))]
    else:
        representative = fits[0]
    return LsiCandidate(
        topics=topics,
        model=representative.model,
        coherence_umass=float(umass.mean()),
        coherence_npmi=float(npmi.mean()),
        diversity=float(np.mean([fit.diversity for fit in fits])),
        stability=stability,
        explained_variance=float(np.mean([fit.explained_variance for fit in fits])),
        seconds=float(sum(fit.seconds for fit in fits)),
        runs=len(fits),
    )


def _rank_lsi_candidates(candidates: list[LsiCandidate]) -> None:
    if len(candidates) == 1:
        candidates[0].selection_score = 1.0
        return
    metrics = {
        "coherence_umass": 0.30,
        "coherence_npmi": 0.30,
        "stability": 0.25,
        "diversity": 0.10,
        "explained_variance": 0.05,
    }
    totals = np.zeros(len(candidates))
    for attribute, weight in metrics.items():
        values = np.array([getattr(candidate, attribute) for candidate in candidates])
        ranks = (rankdata(values, method="average") - 1.0) / max(len(values) - 1, 1)
        totals += weight * ranks
    for candidate, score in zip(candidates, totals):
        candidate.selection_score = float(score)


def _lsi_topic_payload(
    candidate: LsiCandidate,
    tfidf: sparse.csr_matrix,
    features: np.ndarray,
    selected: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components = _oriented_lsi_components(candidate.model)
    raw_document_scores = candidate.model.transform(tfidf)
    # Component signs are arbitrary in SVD. Magnitudes are used only as relative
    # salience scores and are never presented as probabilities.
    salience = np.abs(raw_document_scores)
    normalized_salience = salience / np.maximum(salience.sum(axis=1, keepdims=True), 1e-12)
    assignments = normalized_salience.argmax(axis=1)
    component_magnitude = np.abs(components)
    across_components = component_magnitude.sum(axis=0)
    topics = []
    for topic_index, component in enumerate(components):
        positive_indices = np.argsort(component)[-35:][::-1]
        words = [{
            "term": str(features[word_index]).replace("_", " "),
            "loading": float(component[word_index]),
            "exclusivity": float(
                abs(component[word_index]) / max(across_components[word_index], 1e-12)
            ),
        } for word_index in positive_indices]
        label_words: list[str] = []
        for word in words:
            parts = set(word["term"].split())
            if any(parts <= set(existing.split()) or set(existing.split()) <= parts for existing in label_words):
                continue
            label_words.append(word["term"])
            if len(label_words) == 3:
                break
        rows = np.where(assignments == topic_index)[0]
        documents = sorted(({
            "id": selected.iloc[row]["id"],
            "title": selected.iloc[row]["title"],
            "authors": selected.iloc[row]["authors"],
            "year": int(selected.iloc[row]["year_num"]) or None,
            "salience": float(normalized_salience[row, topic_index]),
        } for row in rows), key=lambda item: item["salience"], reverse=True)
        topics.append({
            "id": topic_index + 1,
            "label": " · ".join(label_words),
            "document_count": int(len(rows)),
            "words": words,
            "documents": documents,
        })
    document_assignments = [{
        "id": selected.iloc[index]["id"],
        "topic": int(assignments[index]) + 1,
        "salience": float(normalized_salience[index, assignments[index]]),
        "component_scores": [float(value) for value in raw_document_scores[index]],
    } for index in range(len(selected))]
    return topics, document_assignments


def _authors(value: str) -> list[str]:
    if not value:
        return []
    parts = value.split(";") if ";" in value else re.split(r"\s+and\s+|\|", value)
    if len(parts) == 1 and value.count(",") <= 5:
        parts = value.split(",")
    return [re.sub(r"\s*\([^)]*\)\s*", "", part).strip() for part in parts if part.strip()]


def _scale_coordinates(coords: np.ndarray) -> np.ndarray:
    coords = np.asarray(coords, dtype=float)
    for axis in range(2):
        low, high = coords[:, axis].min(), coords[:, axis].max()
        coords[:, axis] = (coords[:, axis] - low) / (high - low) if high > low else 0.5
    return coords


def _project_documents(
    matrix: sparse.csr_matrix,
    mode: str,
    seed: int = 42,
) -> tuple[np.ndarray, str]:
    tfidf = TfidfTransformer(sublinear_tf=True).fit_transform(matrix)
    components = min(30, tfidf.shape[0] - 1, tfidf.shape[1] - 1)
    if components < 2:
        return _scale_coordinates(np.column_stack((np.arange(tfidf.shape[0]), np.zeros(tfidf.shape[0])))), "linear fallback"
    reduced = TruncatedSVD(n_components=components, random_state=seed).fit_transform(tfidf)
    if mode == "accurate" and len(reduced) >= 10:
        perplexity = min(30.0, max(5.0, (len(reduced) - 1) / 4))
        coords = TSNE(
            n_components=2,
            perplexity=perplexity,
            learning_rate="auto",
            init="pca",
            max_iter=750,
            random_state=seed,
        ).fit_transform(reduced)
        return _scale_coordinates(coords), "t-SNE on TF-IDF + TruncatedSVD"
    return _scale_coordinates(reduced[:, :2]), "TruncatedSVD on TF-IDF"


def _topic_coordinates(model: LatentDirichletAllocation) -> list[dict[str, float | int]]:
    matrix = model.components_ / np.maximum(model.components_.sum(axis=1, keepdims=True), 1e-12)
    if len(matrix) == 2:
        coords = np.array([[0.15, 0.5], [0.85, 0.5]])
    else:
        coords = _scale_coordinates(TruncatedSVD(n_components=2, random_state=42).fit_transform(matrix))
    return [
        {"topic": index + 1, "x": float(point[0]), "y": float(point[1])}
        for index, point in enumerate(coords)
    ]


def _bibliometrics(selected: pd.DataFrame, assignments: np.ndarray) -> dict[str, Any]:
    sources = Counter(source for source in selected["source"] if source)
    types = Counter(value for value in selected["document_type"] if value)
    languages = Counter(value for value in selected["language"] if value)
    open_access_count = int(selected["open_access"].str.len().gt(0).sum())
    citations = selected["citations_num"].to_numpy()
    annualized = selected["avg_citations_num"].to_numpy(dtype=float)
    topic_impact = []
    for topic in sorted(set(assignments)):
        values = citations[assignments == topic]
        topic_impact.append({
            "topic": int(topic) + 1,
            "papers": int(len(values)),
            "citations": int(values.sum()),
            "mean_citations": float(values.mean()) if len(values) else 0.0,
            "mean_annualized_citations": float(
                annualized[assignments == topic].mean()
            ) if len(values) else 0.0,
        })
    return {
        "total_citations": int(citations.sum()),
        "mean_citations": float(citations.mean()) if len(citations) else 0.0,
        "median_citations": float(np.median(citations)) if len(citations) else 0.0,
        "mean_annualized_citations": float(annualized.mean()) if len(annualized) else 0.0,
        "open_access_count": open_access_count,
        "open_access_rate": open_access_count / max(len(selected), 1),
        "sources_count": len(sources),
        "top_sources": [{"name": name, "papers": count} for name, count in sources.most_common(20)],
        "document_types": [{"name": name, "papers": count} for name, count in types.most_common()],
        "languages": [{"name": name, "papers": count} for name, count in languages.most_common()],
        "topic_impact": topic_impact,
    }


def analyze(
    data: pd.DataFrame,
    topic_counts: list[int],
    mode: str = "fast",
    excluded_ids: set[str] | None = None,
    include_lsi: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    selected = data[~data["id"].isin(excluded_ids or set())].copy().reset_index(drop=True)
    if len(selected) < 4:
        raise ValueError("Servono almeno 4 documenti selezionati per eseguire LDA.")
    fingerprint_payload = pd.util.hash_pandas_object(
        selected[["title", "abstract", "keywords", "doi"]].fillna(""),
        index=False,
    ).values.tobytes()
    corpus_fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()

    min_df = 2 if len(selected) >= 20 else 1
    max_df = 0.88 if len(selected) >= 12 else 1.0
    vectorizer = CountVectorizer(
        lowercase=False,
        strip_accents="unicode",
        stop_words="english",
        max_df=max_df,
        min_df=min_df,
        max_features=7000 if mode == "accurate" else 3000,
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-z][a-z0-9_\-]{2,}\b",
    )
    matrix = vectorizer.fit_transform(selected["text"].tolist()).tocsr()
    if matrix.shape[1] < 5:
        raise ValueError("Il corpus non contiene abbastanza termini informativi dopo la pulizia.")

    features = vectorizer.get_feature_names_out()
    keep = np.array([
        term not in GENERIC_STOP_WORDS
        and not any(part in GENERIC_STOP_WORDS for part in term.split())
        for term in features
    ])
    matrix = matrix[:, keep].tocsr()
    features = features[keep]
    binary = _binary_matrix(matrix)
    document_frequency = np.asarray(binary.sum(axis=0)).ravel()

    max_topics = max(2, min(20, len(selected) - 1, matrix.shape[1] - 1))
    counts = sorted({int(value) for value in topic_counts if 2 <= int(value) <= max_topics})
    if not counts:
        counts = list(range(2, min(10, max_topics) + 1))

    if mode == "accurate":
        iterations, learning_method, seeds = 25, "batch", (42, 7, 101)
    else:
        iterations, learning_method, seeds = 6, "online", (42,)

    fits_by_topics: dict[int, list[FitResult]] = defaultdict(list)
    tasks = [(topics, seed) for topics in counts for seed in seeds]
    workers = min(len(tasks), 4)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lda") as pool:
        futures = {
            pool.submit(
                _fit_once,
                matrix,
                binary,
                document_frequency,
                topics,
                iterations,
                seed,
                learning_method,
            ): (topics, seed)
            for topics, seed in tasks
        }
        for future in as_completed(futures):
            topics, _ = futures[future]
            fits_by_topics[topics].append(future.result())

    candidates = [
        _aggregate_candidate(topics, fits_by_topics[topics]) for topics in counts
    ]
    candidates.sort(key=lambda item: item.topics)
    _rank_candidates(candidates)
    best = max(candidates, key=lambda item: (item.selection_score, item.coherence_npmi))
    selection_mode = (
        "configured" if len(candidates) == 1
        else "optimized" if len(seeds) > 1
        else "screening"
    )

    lsi_payload: dict[str, Any] | None = None
    if include_lsi:
        lsi_started = time.perf_counter()
        tfidf_for_lsi = TfidfTransformer(sublinear_tf=True).fit_transform(matrix).tocsr()
        lsi_fits_by_topics: dict[int, list[LsiFitResult]] = defaultdict(list)
        lsi_iterations = 12 if mode == "accurate" else 7
        lsi_tasks = [(topics, seed) for topics in counts for seed in seeds]
        with ThreadPoolExecutor(
            max_workers=min(len(lsi_tasks), 4),
            thread_name_prefix="lsi",
        ) as pool:
            futures = {
                pool.submit(
                    _fit_lsi_once,
                    tfidf_for_lsi,
                    binary,
                    document_frequency,
                    topics,
                    lsi_iterations,
                    seed,
                ): topics
                for topics, seed in lsi_tasks
            }
            for future in as_completed(futures):
                lsi_fits_by_topics[futures[future]].append(future.result())
        lsi_candidates = [
            _aggregate_lsi_candidate(topics, lsi_fits_by_topics[topics])
            for topics in counts
        ]
        lsi_candidates.sort(key=lambda item: item.topics)
        _rank_lsi_candidates(lsi_candidates)
        best_lsi = max(
            lsi_candidates,
            key=lambda item: (item.selection_score, item.coherence_npmi),
        )
        lsi_topics, lsi_assignments = _lsi_topic_payload(
            best_lsi,
            tfidf_for_lsi,
            features,
            selected,
        )
        lsi_payload = {
            "algorithm": "Latent Semantic Indexing (TruncatedSVD)",
            "best_topic_number": best_lsi.topics,
            "selection_mode": selection_mode,
            "coherence_umass": best_lsi.coherence_umass,
            "coherence_npmi": best_lsi.coherence_npmi,
            "stability": best_lsi.stability,
            "diversity": best_lsi.diversity,
            "explained_variance": best_lsi.explained_variance,
            "perplexity": None,
            "duration_seconds": time.perf_counter() - lsi_started,
            "candidates": [{
                "topics": item.topics,
                "coherence_umass": item.coherence_umass,
                "coherence_npmi": item.coherence_npmi,
                "stability": item.stability,
                "diversity": item.diversity,
                "explained_variance": item.explained_variance,
                "selection_score": item.selection_score,
                "seconds": item.seconds,
                "runs": item.runs,
                "perplexity": None,
            } for item in lsi_candidates],
            "topics": lsi_topics,
            "document_assignments": lsi_assignments,
            "interpretation_note": (
                "LSI is a signed linear decomposition, not a probabilistic model. "
                "Document salience values are relative component magnitudes, not probabilities."
            ),
        }

    distribution = best.model.transform(matrix)
    assignments = distribution.argmax(axis=1)
    confidence = distribution.max(axis=1)
    entropy = -np.sum(distribution * np.log(np.maximum(distribution, 1e-12)), axis=1)
    normalized_entropy = entropy / max(math.log(best.topics), 1e-12)
    coordinates, projection_method = _project_documents(matrix, mode)
    term_totals = np.asarray(matrix.sum(axis=0)).ravel()
    global_prob = (term_totals + 1) / (term_totals.sum() + len(term_totals))
    topic_probabilities = best.model.components_ / np.maximum(
        best.model.components_.sum(axis=1, keepdims=True), 1e-12
    )
    across_topics = topic_probabilities.sum(axis=0)

    topics = []
    for index, component_prob in enumerate(topic_probabilities):
        relevance = 0.55 * np.log(np.maximum(component_prob, 1e-12)) + 0.45 * np.log(
            np.maximum(component_prob / global_prob, 1e-12)
        )
        top_indices = np.argsort(relevance)[-40:][::-1]
        words = []
        for word_index in top_indices:
            probability = float(component_prob[word_index])
            words.append({
                "term": str(features[word_index]).replace("_", " "),
                "token": str(features[word_index]),
                "weight": probability,
                "frequency": int(term_totals[word_index]),
                "log_lift": float(math.log(max(probability / global_prob[word_index], 1e-12))),
                "log_prob": float(math.log(max(probability, 1e-12))),
                "exclusivity": float(probability / max(across_topics[word_index], 1e-12)),
            })
        label_words = []
        for word in words:
            normalized_parts = set(word["term"].split())
            if any(normalized_parts <= set(existing.split()) or set(existing.split()) <= normalized_parts for existing in label_words):
                continue
            label_words.append(word["term"])
            if len(label_words) == 3:
                break
        topic_rows = np.where(assignments == index)[0]
        representative = sorted(
            ({
                "id": selected.iloc[row]["id"],
                "title": selected.iloc[row]["title"],
                "year": int(selected.iloc[row]["year_num"]) or None,
                "authors": selected.iloc[row]["authors"],
                "weight": float(distribution[row, index]),
                "entropy": float(normalized_entropy[row]),
            } for row in topic_rows),
            key=lambda item: item["weight"],
            reverse=True,
        )
        topics.append({
            "id": index + 1,
            "label": " · ".join(label_words),
            "document_count": int(len(topic_rows)),
            "weight_sum": float(distribution[:, index].sum()),
            "words": words,
            "documents": representative,
        })

    year_topic: dict[int, list[int]] = defaultdict(lambda: [0] * best.topics)
    year_topic_soft: dict[int, list[float]] = defaultdict(lambda: [0.0] * best.topics)
    for row_index, row in selected.iterrows():
        if row["year_num"]:
            year = int(row["year_num"])
            year_topic[year][int(assignments[row_index])] += 1
            year_topic_soft[year] = (
                np.asarray(year_topic_soft[year]) + distribution[row_index]
            ).tolist()

    author_counts: Counter[str] = Counter()
    coauthor_counts: Counter[tuple[str, str]] = Counter()
    for value in selected["authors"]:
        names = _authors(value)[:20]
        author_counts.update(names)
        for first_index, first in enumerate(names):
            for second in names[first_index + 1:]:
                coauthor_counts[tuple(sorted((first, second)))] += 1
    top_authors = author_counts.most_common(30)
    author_names = {name for name, _ in top_authors}

    documents = []
    for index, row in selected.iterrows():
        ranked_topics = np.argsort(distribution[index])[::-1]
        documents.append({
            "id": row["id"],
            "title": row["title"],
            "abstract": row["abstract"],
            "authors": row["authors"],
            "year": int(row["year_num"]) or None,
            "source": row["source"],
            "document_type": row["document_type"],
            "citations": int(row["citations_num"]),
            "doi": row["doi"],
            "link": row["link"],
            "open_access": row["open_access"],
            "topic": int(assignments[index]) + 1,
            "confidence": float(confidence[index]),
            "second_topic": int(ranked_topics[1]) + 1 if best.topics > 1 else None,
            "second_weight": float(distribution[index, ranked_topics[1]]) if best.topics > 1 else 0.0,
            "entropy": float(normalized_entropy[index]),
            "uncertain": bool(confidence[index] < 0.60 or normalized_entropy[index] > 0.72),
            "topic_distribution": [float(value) for value in distribution[index]],
            "x": float(coordinates[index, 0]),
            "y": float(coordinates[index, 1]),
        })

    tfidf = TfidfTransformer(sublinear_tf=True).fit_transform(matrix)
    normalized = tfidf / np.maximum(np.sqrt(tfidf.multiply(tfidf).sum(axis=1)), 1e-12)
    similarities = (normalized @ normalized.T).toarray()
    np.fill_diagonal(similarities, 0.0)
    nearest_similarity = similarities.max(axis=1)
    outlier_threshold = float(min(0.20, max(0.08, np.quantile(nearest_similarity, 0.10))))
    for index, document in enumerate(documents):
        document["nearest_similarity"] = float(nearest_similarity[index])
        document["semantic_outlier"] = bool(nearest_similarity[index] <= outlier_threshold)
    upper = np.triu_indices(len(selected), k=1)
    ranked_edges = np.argsort(similarities[upper])[::-1]
    connections = []
    for rank in ranked_edges[: min(500, len(ranked_edges))]:
        score = float(similarities[upper[0][rank], upper[1][rank]])
        if score < 0.24:
            break
        connections.append({
            "source": selected.iloc[upper[0][rank]]["id"],
            "target": selected.iloc[upper[1][rank]]["id"],
            "similarity": score,
        })

    quality = {
        "strong_assignments": int((confidence >= 0.70).sum()),
        "strong_assignment_rate": float((confidence >= 0.70).mean()),
        "uncertain_documents": int(sum(document["uncertain"] for document in documents)),
        "uncertain_rate": float(np.mean([document["uncertain"] for document in documents])),
        "mean_confidence": float(confidence.mean()),
        "median_confidence": float(np.median(confidence)),
        "mean_entropy": float(normalized_entropy.mean()),
        "semantic_outliers": int(sum(document["semantic_outlier"] for document in documents)),
        "outlier_threshold": outlier_threshold,
        "abstract_coverage": float(selected["abstract"].str.len().gt(20).mean()),
        "keyword_coverage": float(selected["keywords"].str.len().gt(2).mean()),
        "doi_coverage": float(selected["_doi_key"].str.match(r"^10\.\d{4,9}/\S+$", na=False).mean()),
        "uncertain": sorted(
            (document for document in documents if document["uncertain"]),
            key=lambda item: (-item["entropy"], item["confidence"]),
        ),
        "outliers": sorted(
            (document for document in documents if document["semantic_outlier"]),
            key=lambda item: item["nearest_similarity"],
        ),
    }

    elapsed = time.perf_counter() - started
    return {
        "algorithm": (
            "Latent Dirichlet Allocation (LDA) with real LSI comparison"
            if include_lsi else "Latent Dirichlet Allocation (LDA)"
        ),
        "mode": mode,
        "selection_mode": selection_mode,
        "document_count": int(len(selected)),
        "vocabulary_size": int(len(features)),
        "best_topic_number": int(best.topics),
        "perplexity": best.perplexity,
        "log_likelihood_per_word": best.log_likelihood_per_word,
        "coherence_umass": best.coherence_umass,
        "coherence_npmi": best.coherence_npmi,
        "topic_diversity": best.diversity,
        "topic_exclusivity": best.exclusivity,
        "stability": best.stability,
        "duration_seconds": elapsed,
        "corpus_sha256": corpus_fingerprint,
        "candidates": [{
            "topics": item.topics,
            "perplexity": item.perplexity,
            "log_likelihood_per_word": item.log_likelihood_per_word,
            "coherence": item.coherence_umass,
            "coherence_umass": item.coherence_umass,
            "coherence_npmi": item.coherence_npmi,
            "diversity": item.diversity,
            "exclusivity": item.exclusivity,
            "stability": item.stability,
            "selection_score": item.selection_score,
            "seconds": item.seconds,
            "runs": item.runs,
        } for item in candidates],
        "lsi": lsi_payload,
        "algorithm_comparison": [{
            "topics": candidate.topics,
            "lda_umass": candidate.coherence_umass,
            "lda_npmi": candidate.coherence_npmi,
            "lsi_umass": (
                lsi_payload["candidates"][index]["coherence_umass"]
                if lsi_payload else None
            ),
            "lsi_npmi": (
                lsi_payload["candidates"][index]["coherence_npmi"]
                if lsi_payload else None
            ),
        } for index, candidate in enumerate(candidates)],
        "topics": topics,
        "topic_coordinates": _topic_coordinates(best.model),
        "years": [{
            "year": year,
            "counts": counts_by_topic,
            "soft_counts": year_topic_soft[year],
        } for year, counts_by_topic in sorted(year_topic.items())],
        "authors": [{"name": name, "papers": count} for name, count in top_authors],
        "coauthors": [{
            "source": pair[0], "target": pair[1], "papers": count
        } for pair, count in coauthor_counts.most_common(100)
            if pair[0] in author_names and pair[1] in author_names],
        "documents": documents,
        "connections": connections,
        "quality": quality,
        "bibliometrics": _bibliometrics(selected, assignments),
        "methodology": {
            "text_fields": "2× Title + Abstract + 3× Author Keywords",
            "preprocessing": "Unicode normalization, publisher boilerplate removal, controlled phrase normalization, English and scientific stopwords",
            "vectorizer": "CountVectorizer, unigrams + bigrams, adaptive document frequency",
            "optimization": "Parallel candidate runs; rank aggregation across UMass, NPMI, stability, diversity, exclusivity and perplexity",
            "selection_weights": {
                "coherence_umass": 0.28,
                "coherence_npmi": 0.28,
                "stability": 0.22,
                "diversity": 0.10,
                "exclusivity": 0.07,
                "perplexity": 0.05,
            },
            "random_seeds": list(seeds),
            "iterations_per_run": iterations,
            "learning_method": learning_method,
            "projection": projection_method,
            "similarity": "Cosine similarity on TF-IDF",
            "uncertainty_rule": "max topic probability < 0.60 OR normalized entropy > 0.72",
            "strong_assignment_rule": "max topic probability >= 0.70",
            "semantic_outlier_rule": f"nearest-neighbour cosine similarity <= {outlier_threshold:.6f}",
            "runtime_versions": {
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "scipy": scipy.__version__,
                "scikit_learn": sklearn.__version__,
            },
            "lsi_used": include_lsi,
            "lsi_implementation": (
                "TF-IDF + randomized TruncatedSVD; top positive component loadings"
                if include_lsi else None
            ),
            "lsi_alias_note": "LSI is commonly also called latent semantic analysis (LSA).",
        },
    }
