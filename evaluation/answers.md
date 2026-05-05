# Private evaluation notes (outside the readable sample_repo root)

- Pagination: catalog.py uses page * size; it should use (page - 1) * size.
- Missing product: main.py indexes item before checking None; move the check first.
- Filtering: catalog.py uses OR where both category and active must hold; use AND.
- Vague: request endpoint, inputs, expected/actual results, and reproduction steps.
- Unavailable: payment code, logs, and provider request/idempotency information are absent.

The assistant must never import this directory. Mock mode contains explicit demo
heuristics and is not an independent diagnosis evaluation. Live evaluation uses
these expectations only after reports are produced.

