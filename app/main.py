from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from threading import Lock

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.analysis import analyze, normalize_dataset, public_papers


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

app = FastAPI(title="SLR Lens", version="2.1.0")
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": "2.1.0",
        "algorithms": ["LDA", "LSI"],
        "validation": "multi-metric, multi-seed, real LDA-vs-LSI comparison",
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
        "lsi": result.get("lsi"),
        "algorithm_comparison": result.get("algorithm_comparison"),
    }, indent=2, ensure_ascii=False)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="slr-lens-methodology-{analysis_id[:8]}.json"'},
    )


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
            "duration_seconds", "candidates", "quality", "bibliometrics",
            "methodology", "lsi", "algorithm_comparison",
        )
    }
    diagnostics["quality"] = {
        key: value for key, value in diagnostics["quality"].items()
        if key not in {"uncertain", "outliers"}
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document_assignments.csv", pd.DataFrame(document_rows).to_csv(index=False))
        archive.writestr("topic_terms.csv", pd.DataFrame(term_rows).to_csv(index=False))
        archive.writestr(
            "methodology_and_diagnostics.json",
            json.dumps(diagnostics, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            "README.txt",
            "SLR Lens reproducibility bundle\n"
            "Contains LDA and LSI assignments, topic terms, all candidate metrics and the exact methodology.\n"
            "Higher UMass/NPMI/stability/diversity/exclusivity is better; lower perplexity is better.\n"
            "LSI is a real TruncatedSVD implementation. Perplexity does not apply to LSI.\n",
        )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="slr-lens-reproducibility-{analysis_id[:8]}.zip"'
        },
    )
