# Flying Drones Patent Analytics

## Run the Step 0 → Step 1 baseline

Use Python 3.11 or later and an EPO TIP notebook kernel with PATSTAT access for retrieval, extraction, and Step 1. The scoring notebook uses Colab and the patent SBERT model. Use the repository's Python requirements in the relevant runtime. The applicant notebook also imports Cleanco. Fresh LLM classifications require the course-authorized API credential. Cached calibration and the saved blind-label comparison can use existing labels.

1. In `config/sector.yaml`, select `TEST` or `PROD`, set `patstat_edition` if TIP identifies it, and select a persistent `paths.run_root` with space for the extracts. The default is the ignored `outputs/runs` directory in the checkout. The configuration keeps the original application query window (2000–2024) distinct from the family/analysis window (2000–2025). The committed default is **PROD**. Set **TEST** for a development extraction.
2. Set one explicit run ID for every TIP kernel participating in the run. For example, execute `%env PATENT_RUN_ID=baseline-001` in each kernel, or export the variable before launching Jupyter. Start notebooks from their checkout. Keep the same checkout, YAML contents, and run ID when restarting a stage. Different inputs, settings, or revised outputs belong to a fresh run ID.
3. **Query diagnostics, optional.** `Step0/1a-QueryDiagnostics.ipynb` documents how the team selected terms and codes. Its diagnostic groups and cached labels support calibration. The production search uses the explicit final lists in `1b`.
4. **TIP → Colab.** Run `Step0/1b-DataPreparation.ipynb` through section 2.1. This publishes `preparation/df_sbert_input.parquet` and its adjacent `.receipt.json` in the run directory. Transfer this pair to the approved scoring runtime. Run `Step0/1c-SbertScoring_Colab.ipynb`. Place the returned `df_sbert_scored.parquet` **and** `df_sbert_scored.parquet.handoff.json` in that same run's `colab_return/` directory on TIP.
5. **TIP selection.** Continue `1b` from section 2.2. After a kernel restart, run its imports and settings first. The import checks the run, model/description, file digests, and original application rows. The notebook publishes the scored and selected application files and the immutable selection `manifest.json`.
6. **PROD validation.** Run `Step0/2c-ProdValidation.ipynb` on the same PROD run. It uses `2-DataValidation.ipynb`, samples kept/rejected families and stores any pending human reviews in the run's `validation/` directory. Fill the hand labels there, re-run the evaluation, then publish the v2 summary. The optional historical blind-label study in `2b-LLMHandCheck.ipynb` belongs to TEST. Selection and validation are separate stages.
7. **Family expansion and extraction.** Run `Step0/3-DataExtractionAndCleaning.ipynb`. It verifies the selection release, expands DOCDB families, applies the existing year and PI rules, then publishes `extract/*.parquet`. The family year and summary fields are still computed before PI-member exclusion.
8. **Downstream branches.** `Step0/3b-NameHarmonization.ipynb` uses the run's extracted persons and families to publish `harmonization/*.csv`. Use a separate working copy of the alias-review template for human decisions. Independently, `Step1/1-GeneralDescription.ipynb` reads four verified extract tables and live TIP benchmarks/WIPO fields, then publishes twelve CSVs under `step1/`. Step 1 does not require the applicant harmonization notebook.

### Identify and verify a run

Files live under `<run_root>/<TEST|PROD>/<PATENT_RUN_ID>/`. `run.json` records the configuration snapshot. After selection, `manifest.json` identifies the cohort, model, full method settings, file digests and counts. Each published artifact has an adjacent SHA-256 receipt with its dependencies. Identical publications can be reused. An altered file, changed configuration, foreign receipt, or conflicting publication fails verification. Missing edition or Git metadata is recorded as unknown. The storage volume used by TIP must support Linux file locking and same-filesystem hard links.

To check the complete selection lineage from the checkout root with the run ID set:

```python
from pathlib import Path
import json
from run_baseline import Run

run = Run.open(Path.cwd())
release = json.loads(run.verify("manifest.json").read_text())
print(run.env, run.run_id, release["selected_rows"], release["selected_families"])
```

Use `python -m unittest discover -s tests -v` for the local baseline checks. They use temporary run directories. A fresh TIP run is required to establish new scientific results. Embedded notebook outputs and files already tracked in `Step0/validation/` document earlier runs; copying a legacy Parquet into a new run does not give it provenance. Keep patent extracts and full-text working reviews in approved storage.

## Historical TEST workflow

The following notes describe the earlier TEST prototype in `Step0/startingDraft.ipynb`. Its search and completion notes predate the baseline above.

**PWStep0 — Patent Dataset Construction for the Flying Drones Sector**

The notebook builds a patent dataset for the flying drones sector using PATSTAT through the EPO Technology Intelligence Platform (TIP). Development currently uses the **TEST environment**, so the focus is on implementing and checking the procedure rather than reporting sector statistics.

**1. Search definition and application extraction**

Applications are identified through three complementary strategies: keywords in titles and abstracts, IPC prefix `B64U`, and CPC prefixes `B64U` and `B64C39/024`. Keyword matching is case-insensitive, while classification symbols are matched by prefix after removing padding spaces.

The three sets of application IDs are combined using OR logic through SQL `UNION`. Bibliographic information, family IDs, earliest filing years, grant indicators, titles and abstracts are retrieved.

**2. Data checks and retrieval diagnostics**

Initial checks identify repeated application IDs, invalid family IDs and unavailable years. Each application is assigned flags showing which search strategies retrieved it.

Diagnostic functions display full texts, matching keywords and matching classification codes. This helps investigate potentially irrelevant results and refine the search criteria.

**3. Family grouping and manual validation**

Retrieved applications are grouped into one row per DOCDB family, preserving links to the matched applications and their retrieval strategies.

A reproducible random sample of approximately 100 families is selected for manual validation. Families are assessed as `relevant`, `not relevant` or `uncertain`, with a short explanation. Assessments are saved to a CSV file and can be reloaded. Validation is still in progress.

**4. Family-member retrieval and dating**

Additional available applications belonging to the selected families are retrieved, including members that did not directly match the search. These are stored separately from the original results.

Each family receives a `priority_year`, calculated as the minimum valid `earliest_filing_year` across its available members. Missing years and PATSTAT’s unavailable-year code are excluded.

**5. Applicant extraction and name normalization**

Applicants and their countries are retrieved for the applications belonging to the selected families. The results are stored in a separate table linked to the family dataset through docdb_family_id, preserving multiple applicants and applications within each family.
Applicant names are normalized for whitespace, capitalization and equivalent Unicode characters. PATSTAT standardized names (psn_name) are preferred, with original names used as a fallback. Original values are preserved for traceability. Further organizational disambiguation and subsidiary consolidation remain to be evaluated.

**Remaining work**

- **Complete query validation:** finish manual family labelling, summarize relevance assessments and refine the search criteria where necessary. Verify the final selection in PROD.

- **Complete applicant cleaning:** investigate families without applicant records and unresolved name variants. Document any organizational mappings or subsidiary consolidation.

- **Define the analysis period:** choose the starting year, apply the filter using family-level priority years and flag incomplete recent years.

- **Complete supporting data extraction:** retrieve family classification codes beyond those matching the search and prepare citation data for subsequent analyses.

- **Finalize reproducibility and PROD execution:** export the resulting tables, document configuration and cleaning rules, record the PATSTAT edition and run the pipeline with final checks in PROD.
