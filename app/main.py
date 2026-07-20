from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.analysis import analyze, normalize_dataset, public_papers


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

app = FastAPI(title="SLR Lens", version="3.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

datasets: dict[str, pd.DataFrame] = {}
results: dict[str, dict] = {}
store_lock = Lock()


class AnalysisRequest(BaseModel):
    dataset_id: str
    topic_counts: list[int] = Field(default_factory=lambda: [2, 4, 6, 8])
    mode: str = "fast"
    include_lsi: bool = True
    excluded_ids: list[str] = Field(default_factory=list)


def _read_upload(filename: str, content: bytes) -> pd.DataFrame:
    extension = Path(filename).suffix.lower()
    if extension in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(content))
    if extension == ".csv":
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(content), encoding=encoding, sep=None, engine="python")
            except Exception as exc:  # pragma: no cover - only reached by malformed exports
                last_error = exc
        raise ValueError(f"CSV non leggibile: {last_error}")
    raise ValueError("Formato non supportato. Usa CSV o XLSX esportato da Scopus.")


def _comparison_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _doi_key(value: object) -> str:
    return re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        str(value or "").strip().lower(),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": "3.0.0",
        "algorithms": ["LDA", "LSI", "Bibliometric Intelligence"],
        "validation": "multi-metric, multi-seed, explorable LDA candidates and real LDA-vs-LSI comparison",
        "lsi": True,
    }


@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...)) -> JSONResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Il file supera il limite di 30 MB.")
    try:
        raw = _read_upload(file.filename or "dataset.csv", content)
        normalized, summary = normalize_dataset(raw)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    dataset_id = uuid.uuid4().hex
    with store_lock:
        datasets[dataset_id] = normalized
    years = sorted(int(y) for y in normalized["year_num"].unique() if y)
    return JSONResponse({
        "dataset_id": dataset_id,
        "filename": file.filename,
        "summary": summary,
        "years": years,
        "papers": public_papers(normalized),
    })


@app.post("/api/analyze")
def run_analysis(request: AnalysisRequest) -> JSONResponse:
    if request.mode not in {"fast", "accurate"}:
        raise HTTPException(400, "Modalità non valida.")
    with store_lock:
        dataset = datasets.get(request.dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset non trovato: ricarica il file.")
    try:
        payload = analyze(
            dataset,
            request.topic_counts,
            request.mode,
            set(request.excluded_ids),
            request.include_lsi,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    analysis_id = uuid.uuid4().hex
    payload["analysis_id"] = analysis_id
    with store_lock:
        results[analysis_id] = payload
    return JSONResponse(payload)


@app.get("/api/results/{analysis_id}/export")
def export_results(analysis_id: str) -> Response:
    with store_lock:
        result = results.get(analysis_id)
    if result is None:
        raise HTTPException(404, "Analisi non trovata.")
    topic_labels = {topic["id"]: topic["label"] for topic in result["topics"]}
    lsi_by_id = {
        document["id"]: document for document in (
            result["lsi"]["document_assignments"] if result.get("lsi") else []
        )
    }
    rows = [{
        "Topic": document["topic"],
        "Topic label": topic_labels[document["topic"]],
        "Topic confidence": document["confidence"],
        "Second topic": document["second_topic"],
        "Second topic weight": document["second_weight"],
        "Normalized entropy": document["entropy"],
        "Uncertain assignment": document["uncertain"],
        "Semantic outlier": document["semantic_outlier"],
        "Nearest document similarity": document["nearest_similarity"],
        "Topic distribution": json.dumps(document["topic_distribution"]),
        "Document title": document["title"],
        "Authors": document["authors"],
        "Year": document["year"],
        "Source": document["source"],
        "Document type": document["document_type"],
        "Citations": document["citations"],
        "DOI": document["doi"],
        "Link": document["link"],
        "Open access": document["open_access"],
        "LSI topic": lsi_by_id.get(document["id"], {}).get("topic"),
        "LSI relative salience": lsi_by_id.get(document["id"], {}).get("salience"),
        "LSI component scores": json.dumps(
            lsi_by_id.get(document["id"], {}).get("component_scores", [])
        ),
    } for document in result["documents"]]
    output = io.StringIO()
    pd.DataFrame(rows).to_csv(output, index=False)
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="slr-lens-topics-{analysis_id[:8]}.csv"'},
    )


@app.get("/api/results/{analysis_id}/methodology")
def export_methodology(analysis_id: str) -> Response:
    with store_lock:
        result = results.get(analysis_id)
    if result is None:
        raise HTTPException(404, "Analisi non trovata.")
    content = json.dumps({
        "algorithm": result["algorithm"],
        "metrics": {
            "perplexity": result["perplexity"],
            "log_likelihood_per_word": result["log_likelihood_per_word"],
            "coherence_umass": result["coherence_umass"],
            "coherence_npmi": result["coherence_npmi"],
            "topic_diversity": result["topic_diversity"],
            "topic_exclusivity": result["topic_exclusivity"],
            "stability": result["stability"],
        },
        "selection_mode": result["selection_mode"],
        "corpus_sha256": result["corpus_sha256"],
        "methodology": result["methodology"],
        "candidates": result["candidates"],
        "lda_models": result["lda_models"],
        "lsi": result.get("lsi"),
        "algorithm_comparison": result.get("algorithm_comparison"),
        "external_validation": result.get("external_validation"),
    }, indent=2, ensure_ascii=False)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="slr-lens-methodology-{analysis_id[:8]}.json"'},
    )


@app.post("/api/results/{analysis_id}/compare-myslr")
async def compare_myslr_export(
    analysis_id: str,
    file: UploadFile = File(...),
) -> JSONResponse:
    with store_lock:
        result = results.get(analysis_id)
    if result is None:
        raise HTTPException(404, "Analisi non trovata.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Il file supera il limite di 30 MB.")
    try:
        reference = _read_upload(file.filename or "myslr-export.xlsx", content)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    columns = {
        _comparison_key(column): column for column in reference.columns
    }
    topic_column = columns.get("topic")
    doi_column = columns.get("doi")
    title_column = columns.get("title")
    if topic_column is None or (doi_column is None and title_column is None):
        raise HTTPException(
            400,
            "L'export deve contenere topic e almeno una colonna DOI o title.",
        )
    reference = reference[reference[topic_column].notna()].copy()
    labels = sorted(
        {str(value) for value in reference[topic_column]},
        key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value),
    )
    label_index = {label: index for index, label in enumerate(labels)}
    by_doi = {}
    by_title = {}
    for row in reference.to_dict("records"):
        topic = label_index[str(row[topic_column])]
        if doi_column and _doi_key(row.get(doi_column)):
            by_doi[_doi_key(row.get(doi_column))] = topic
        if title_column and _comparison_key(row.get(title_column)):
            by_title[_comparison_key(row.get(title_column))] = topic

    documents = {document["id"]: document for document in result["documents"]}
    comparisons = []
    for model in result["lda_models"]:
        reference_topics = []
        slr_topics = []
        doi_matches = 0
        title_matches = 0
        for assignment in model["document_assignments"]:
            document = documents[assignment["id"]]
            topic = by_doi.get(_doi_key(document.get("doi")))
            if topic is not None:
                doi_matches += 1
            else:
                topic = by_title.get(_comparison_key(document.get("title")))
                if topic is not None:
                    title_matches += 1
            if topic is not None:
                reference_topics.append(topic)
                slr_topics.append(int(assignment["topic"]) - 1)
        rows_count = len(labels)
        columns_count = model["topics_count"]
        contingency = np.zeros((rows_count, columns_count), dtype=int)
        for reference_topic, slr_topic in zip(reference_topics, slr_topics):
            contingency[reference_topic, slr_topic] += 1
        row_indices, column_indices = linear_sum_assignment(-contingency)
        aligned = int(contingency[row_indices, column_indices].sum())
        matched = len(reference_topics)
        comparisons.append({
            "topics": model["topics_count"],
            "same_topic_count": model["topics_count"] == len(labels),
            "matched_documents": matched,
            "coverage": matched / max(len(result["documents"]), 1),
            "doi_matches": doi_matches,
            "title_matches": title_matches,
            "adjusted_rand_index": float(
                adjusted_rand_score(reference_topics, slr_topics)
            ) if matched else None,
            "normalized_mutual_information": float(
                normalized_mutual_info_score(reference_topics, slr_topics)
            ) if matched else None,
            "aligned_accuracy": aligned / max(matched, 1),
            "contingency_matrix": contingency.tolist(),
            "best_mapping": [{
                "myslr_topic": labels[int(row)] ,
                "slr_lens_topic": int(column) + 1,
                "documents": int(contingency[row, column]),
            } for row, column in zip(row_indices, column_indices)],
        })
    payload = {
        "source_file": file.filename,
        "reference_topics": labels,
        "reference_documents": int(len(reference)),
        "comparisons": comparisons,
        "interpretation": (
            "ARI and NMI are label-invariant. Values near 1 indicate strong agreement; "
            "values near 0 indicate little agreement. Agreement is not ground-truth accuracy."
        ),
    }
    with store_lock:
        result["external_validation"] = payload
    return JSONResponse(payload)


@app.get("/api/results/{analysis_id}/bundle")
def export_reproducibility_bundle(analysis_id: str) -> Response:
    with store_lock:
        result = results.get(analysis_id)
    if result is None:
        raise HTTPException(404, "Analisi non trovata.")

    topic_labels = {topic["id"]: topic["label"] for topic in result["topics"]}
    lsi_by_id = {
        document["id"]: document for document in (
            result["lsi"]["document_assignments"] if result.get("lsi") else []
        )
    }
    document_rows = [{
        "topic": document["topic"],
        "topic_label": topic_labels[document["topic"]],
        "confidence": document["confidence"],
        "second_topic": document["second_topic"],
        "second_weight": document["second_weight"],
        "normalized_entropy": document["entropy"],
        "uncertain": document["uncertain"],
        "semantic_outlier": document["semantic_outlier"],
        "nearest_similarity": document["nearest_similarity"],
        "topic_distribution": json.dumps(document["topic_distribution"]),
        "title": document["title"],
        "authors": document["authors"],
        "year": document["year"],
        "source": document["source"],
        "document_type": document["document_type"],
        "citations": document["citations"],
        "doi": document["doi"],
        "link": document["link"],
        "lsi_topic": lsi_by_id.get(document["id"], {}).get("topic"),
        "lsi_relative_salience": lsi_by_id.get(document["id"], {}).get("salience"),
        "lsi_component_scores": json.dumps(
            lsi_by_id.get(document["id"], {}).get("component_scores", [])
        ),
    } for document in result["documents"]]
    term_rows = [{
        "topic": topic["id"],
        "topic_label": topic["label"],
        "term": word["term"],
        "probability": word["weight"],
        "frequency": word["frequency"],
        "log_lift": word["log_lift"],
        "log_probability": word["log_prob"],
        "exclusivity": word["exclusivity"],
    } for topic in result["topics"] for word in topic["words"]]
    diagnostics = {
        key: result[key] for key in (
            "algorithm", "mode", "selection_mode", "document_count",
            "vocabulary_size", "best_topic_number", "perplexity",
            "corpus_sha256",
            "log_likelihood_per_word", "coherence_umass", "coherence_npmi",
            "topic_diversity", "topic_exclusivity", "stability",
            "duration_seconds", "candidates", "lda_models", "quality", "bibliometrics",
            "methodology", "lsi", "algorithm_comparison",
        )
    }
    diagnostics["quality"] = {
        key: value for key, value in diagnostics["quality"].items()
        if key not in {"uncertain", "outliers"}
    }
    diagnostics["external_validation"] = result.get("external_validation")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        bibliometrics = result["bibliometrics"]
        archive.writestr("document_assignments.csv", pd.DataFrame(document_rows).to_csv(index=False))
        archive.writestr("topic_terms.csv", pd.DataFrame(term_rows).to_csv(index=False))
        archive.writestr(
            "bibliometrics/authors_impact.csv",
            pd.DataFrame(bibliometrics["authors"]).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/sources_bradford.csv",
            pd.DataFrame(bibliometrics["top_sources"]).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/countries_collaboration.csv",
            pd.DataFrame(bibliometrics["countries"]).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/most_cited_documents.csv",
            pd.DataFrame(bibliometrics["most_cited_documents"]).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/keyword_network_edges.csv",
            pd.DataFrame(
                bibliometrics["conceptual"]["keyword_network"]["edges"]
            ).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/thematic_map.csv",
            pd.DataFrame(bibliometrics["conceptual"]["thematic_map"]).to_csv(index=False),
        )
        archive.writestr(
            "bibliometrics/intellectual_structure.json",
            json.dumps(bibliometrics["intellectual"], indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "methodology_and_diagnostics.json",
            json.dumps(diagnostics, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.txt",
            "SLR Lens reproducibility bundle\n"
            "Contains LDA and LSI assignments, topic terms, all candidate metrics and the exact methodology.\n"
            "Higher UMass/NPMI/stability/diversity/exclusivity is better; lower perplexity is better.\n"
            "LSI is a real TruncatedSVD implementation. Perplexity does not apply to LSI.\n"
            "Bibliometric tables contain Bradford, Lotka, author impact, collaboration, "
            "co-word and reference-gated intellectual structure outputs.\n",
        )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="slr-lens-reproducibility-{analysis_id[:8]}.zip"'
        },
    )
