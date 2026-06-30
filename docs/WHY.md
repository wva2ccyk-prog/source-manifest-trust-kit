# Why Source Manifest Trust Kit Exists

Most analysis workflows collapse source collection, summarization, judgment, and reporting into one step. That is convenient, but it makes it hard to see where an assertion came from and whether a report is repeating weak evidence as if it were verified fact.

This kit exists for a narrower job: take a local package of already collected sources, preserve the manifest, label claims and risks deterministically, and produce review artifacts that make the next human or model review safer.

## Repeated Pain

- Source packages mix official records, news articles, forum claims, commentary, and copied excerpts.
- A summary can sound confident even when the underlying evidence is rumor-like or inaccessible.
- Finance-related language can accidentally turn source analysis into advice, target-price language, allocation guidance, or action prompts.
- Reviewers need compact verification packets, not raw folders of unrelated text.
- Operators need a reproducible local pass before they spend tokens on deeper analysis.

## Why Existing Tools Are Not Enough

Search engines and feed readers help find material, but they usually do not preserve a controlled local source manifest. General note tools preserve text, but they do not enforce claim ledgers, source-type labels, finance-safety masking, or verification packet boundaries. LLM summarizers can be useful after packaging, but they can overstate weak evidence if the source package has not been structured first.

Source Manifest Trust Kit intentionally stays boring: local files in, deterministic artifacts out. Its purpose is to prepare a cleaner evidence surface for later review, not to be the reviewer of last resort.

## Design Principles

- Source metadata should travel with the text.
- Reports should separate observation, interpretation, risk, and verification need.
- Finance-sensitive wording should be masked in report surfaces.
- Helper/model review should be advisory and unable to upgrade deterministic classifications.
- Public demos should use synthetic sources only.
