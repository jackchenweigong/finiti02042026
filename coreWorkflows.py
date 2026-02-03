# • Drafting: User requests a 10-K section draft 
# • Reviewing: System checks a paragraph against sources, returns discrepancies 
# • Benchmarking: Returns peer excerpts with confidence scores and audit trail 

# ---------------------------
# 1) Drafting: draft a 10-K section
# ---------------------------
def draft_10k_section(tenant_id, user_id, filing_version_id, section_key, peer_set_id=None):
    authorize(user_id, tenant_id, "DRAFT")

    run_id = audit.start_run("DRAFT", {
        "filing_version_id": filing_version_id,
        "section_key": section_key,
        "peer_set_id": peer_set_id
    })

    # Retrieve evidence (hybrid: section match + BM25 + vector)
    chunks = search.hybrid_retrieve(
        query=section_key,
        filters={"filing_version_id": filing_version_id, "section_key": section_key},
        peer_set_id=peer_set_id,
        top_k=20
    )

    # Generate draft with required citations (returns JSON: paragraphs + citations)
    draft = llm.generate_json(
        prompt_version="draft_10k_v2",
        context=chunks,
        schema="DraftSchemaRequiresCitations"
    )

    # Validate that every claim/paragraph has citations
    if not validate.citation_coverage(draft):
        draft = llm.repair_add_citations(draft, chunks)

    db.save_draft(draft, run_id)
    audit.end_run(run_id, {"draft_id": draft.id})
    return draft


# ---------------------------
# 2) Reviewing: check paragraph vs sources, return discrepancies
# ---------------------------
def review_paragraph(tenant_id, user_id, filing_version_id, paragraph_text):
    authorize(user_id, tenant_id, "REVIEW")

    run_id = audit.start_run("REVIEW", {
        "filing_version_id": filing_version_id,
        "paragraph_hash": hash(paragraph_text)
    })

    # Retrieve likely supporting/contradicting sources
    evidence = search.hybrid_retrieve(
        query=paragraph_text,
        filters={"filing_version_id": filing_version_id},
        top_k=25
    )

    # Deterministic checks (numbers/dates/units)
    numeric_issues = checks.verify_numbers_dates_units(paragraph_text, evidence)

    # LLM verification (returns structured issues with cited chunk_ids)
    semantic_issues = llm.verify_json(
        prompt_version="verify_v1",
        paragraph=paragraph_text,
        evidence=evidence,
        schema="ReviewIssuesSchema"
    )

    issues = numeric_issues + semantic_issues
    audit.end_run(run_id, {"issue_count": len(issues), "evidence_used": [c.id for c in evidence]})
    return {"status": "reviewed", "issues": issues, "audit_run_id": run_id}


# ---------------------------
# 3) Benchmarking: peer excerpts + confidence + audit trail
# ---------------------------
def benchmark_paragraph(tenant_id, user_id, peer_set_id, paragraph_text, section_key=None):
    authorize(user_id, tenant_id, "BENCHMARK")

    run_id = audit.start_run("BENCHMARK", {
        "peer_set_id": peer_set_id,
        "section_key": section_key,
        "paragraph_hash": hash(paragraph_text)
    })

    # Search across peer corpus for similar excerpts
    peers = search.peer_similarity_search(
        query=paragraph_text,
        peer_set_id=peer_set_id,
        filters={"section_key": section_key} if section_key else {},
        top_k=10
    )

    # Compute confidence from retrieval/rerank signals (simple placeholder formula)
    results = []
    for p in peers:
        conf = confidence.score(retrieval=p.retrieval_score, rerank=p.rerank_score, freshness=p.filing_date)
        results.append({
            "peer_company": p.company_name,
            "excerpt": p.text,
            "chunk_id": p.chunk_id,
            "confidence": conf
        })

    audit.end_run(run_id, {"result_count": len(results), "peer_chunks": [r["chunk_id"] for r in results]})
    return {"results": results, "audit_run_id": run_id}
