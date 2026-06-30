# Public Differentiation

## Compared With Generic LLM Prompt Templates

Prompt templates are quick, but they often mix source text, instructions, and conclusions in one paste. Source Manifest Trust Kit creates a deterministic package first: source manifest, safe claim index, verification packet, and explicit review boundaries.

## Compared With Browser Research Assistants

Browser assistants focus on finding and summarizing web content. This kit assumes the operator already collected excerpts and wants a controlled local package. It does not scrape, monitor, follow links, or decide which live source is authoritative.

## Compared With RAG Or Citation Tools

RAG tools optimize retrieval over a corpus. This kit is smaller: package a bounded source set, preserve evidence boundaries, and prepare an LLM-consumable review packet. It is useful before building a larger retrieval layer.

## Compared With Finance Or News Summarizers

Finance/news summarizers can blur analysis into recommendations or confident narratives. This kit treats finance wording as a safety risk and masks recommendation-like language in report surfaces.

## Actual Differentiator

The strongest differentiator is not generic summarization. It is the enforced sequence:

```text
operator-collected excerpts -> deterministic evidence boundary -> LLM-safe review packet -> advisory review
```

That makes the package useful for teams that already have source excerpts and want a safer pre-model packaging step.

## Honest Verdict

Readiness class: `public_alpha_candidate` (pending the release gate).

The package is differentiated because it is source-manifest first, preserves evidence boundaries before model review, and prevents unsafe investing/trading recommendation leakage. It is deliberately narrow: the default LLM path is the no-key deterministic mock, the real-provider adapter is a dry-run template only, and the frontend is a static artifact viewer. It is not a fact checker, truth-verification engine, RAG evaluator, or finance/investment tool.
