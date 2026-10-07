# Benchmark status

No source-derived gold labels have been approved (approved records: 0). The private
manual-review-candidates.json is a 12-case source-coverage shortlist, NOT an evaluation dataset
and NOT training data. Experts approve edited cases first; an admin then selects holdouts on the
«التقييم» page (or `scripts/build_benchmark.py`) and freezes a dataset manifest. Until then the
evaluation and export pages stay empty by design; never machine-approve cases to fill them.
Synthetic fruit comparisons in tests/ test mechanics only and never enter the book dataset.
