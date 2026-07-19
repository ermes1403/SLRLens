import pandas as pd

from app.analysis import analyze, clean_scientific_text, normalize_dataset


def sample_frame() -> pd.DataFrame:
    themes = [
        ("Software testing with generated unit tests and mutation coverage", "Automated unit test generation improves mutation testing coverage and fault detection.", "unit tests; mutation testing"),
        ("Large language models for test case generation", "Language models generate executable test cases and improve software quality assurance.", "test generation; quality"),
        ("Requirements engineering with language models", "Requirements extraction detects ambiguity and improves specification completeness.", "requirements; ambiguity"),
        ("Automated requirement classification in software projects", "Natural language requirements are classified and validated for consistency.", "requirements engineering; classification"),
        ("Multi agent systems for software delivery", "Autonomous agents collaborate on planning coding review and delivery workflows.", "multi-agent; software agents"),
        ("Agentic workflows for repository maintenance", "Agents plan tool use and validate changes in complex software repositories.", "agentic AI; maintenance"),
    ]
    rows = []
    for cycle in range(3):
        for index, (title, abstract, keywords) in enumerate(themes):
            rows.append({
                "Title": f"{title} {cycle + 1}",
                "Abstract": abstract + f" Empirical evaluation {cycle + 1}.",
                "Author Keywords": keywords,
                "Year": 2022 + cycle,
                "Authors": f"Author {index}; Researcher {cycle}",
                "DOI": f"10.1000/{cycle}-{index}",
                "Cited by": cycle + index,
            })
    rows.append(rows[0].copy())
    return pd.DataFrame(rows)


def test_normalization_and_deduplication():
    normalized, summary = normalize_dataset(sample_frame())
    assert summary["imported"] == 19
    assert summary["unique"] == 18
    assert summary["duplicates_removed"] == 1
    assert normalized["id"].is_unique


def test_lda_analysis_has_traceable_outputs():
    normalized, _ = normalize_dataset(sample_frame())
    result = analyze(normalized, [2, 3, 4], mode="fast")
    assert "Latent Dirichlet Allocation (LDA)" in result["algorithm"]
    assert result["methodology"]["lsi_used"] is True
    assert result["lsi"]["algorithm"].startswith("Latent Semantic Indexing")
    assert len(result["lsi"]["candidates"]) == 3
    assert result["lsi"]["perplexity"] is None
    assert result["best_topic_number"] in {2, 3, 4}
    assert len(result["documents"]) == 18
    assert sum(topic["document_count"] for topic in result["topics"]) == 18
    assert len(result["candidates"]) == 3
    assert len(result["lda_models"]) == 3
    assert [model["topics_count"] for model in result["lda_models"]] == [2, 3, 4]
    assert sum(model["recommended"] for model in result["lda_models"]) == 1
    for model in result["lda_models"]:
        assert len(model["topics"]) == model["topics_count"]
        assert len(model["topic_coordinates"]) == model["topics_count"]
        assert len(model["document_assignments"]) == 18
        assert sum(topic["document_count"] for topic in model["topics"]) == 18
        assert all("topic_frequency" in word for topic in model["topics"] for word in topic["words"])
        assert all("prevalence" in point for point in model["topic_coordinates"])
        assert all(
            "zzfieldboundaryzz" not in word["token"]
            for topic in model["topics"]
            for word in topic["words"]
        )
    assert result["duration_seconds"] > 0
    assert result["selection_mode"] == "screening"
    assert "coherence_npmi" in result
    assert "stability" in result
    assert result["methodology"]["lsi_used"] is True
    assert all("uncertain" in document for document in result["documents"])


def test_scientific_cleaning_removes_publishers_and_normalizes_concepts():
    text = clean_scientific_text(
        "LLMs and large language models for software development. "
        "© The Author(s), under exclusive licence to Springer 2026."
    )
    assert text.count("large_language_model") == 2
    assert "software_development" in text
    assert "copyright" not in text
    assert "springer" not in text
    assert clean_scientific_text(
        "software development lifecycle (SDLC)"
    ) == "software_development_lifecycle"


def test_single_k_is_not_reported_as_optimized():
    normalized, _ = normalize_dataset(sample_frame())
    result = analyze(normalized, [3], mode="fast")
    assert result["selection_mode"] == "configured"
    assert result["candidates"][0]["runs"] == 1


def test_lsi_can_be_disabled_explicitly():
    normalized, _ = normalize_dataset(sample_frame())
    result = analyze(normalized, [2, 3], mode="fast", include_lsi=False)
    assert result["lsi"] is None
    assert result["methodology"]["lsi_used"] is False
