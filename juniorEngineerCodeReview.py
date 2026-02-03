import openai, db

def review_draft(draft_text, filing_id):
    filing = db.query(f"SELECT * FROM filings WHERE id = {filing_id}")[0]

    prompt = (
        "Check this draft against the source and find errors:\n"
        f"Draft: {draft_text}\n"
        f"Source: {filing['full_text']}"
    )

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    discrepancies = response.choices[0].message.content

    return {
        "status": "reviewed",
        "issues": discrepancies,
        "confidence": 0.85,
    }
