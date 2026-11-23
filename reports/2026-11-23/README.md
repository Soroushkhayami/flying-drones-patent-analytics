# Flying drones patent analytics · 23 November 2026

The production run selected 168,664 DOCDB families using the SBERT filter. After family expansion, the year window and the patent-of-invention filter, the final extract contained 106,998 families. Of these, 106,877 had applicant records (99.89%). The separate estimate of **filter precision was 94%**.

## Production filter validation

Run `phase2a-prod-001` · Notebook `Step0/2c-ProdValidation.ipynb` · Output column `Filtro SBERT PROD v2`. This table transcribes the TIP output shared by the project team.

| Notebook metric | Value |
| --- | ---: |
| selected_families | 168,664 |
| rejected_families | 13,059 |
| sample_selected | 100 |
| sample_rejected | 100 |
| precision | 0.9400 |
| precision_CI95_low | 0.8752 |
| precision_CI95_high | 0.9722 |
| recall_within_pool | 0.9477 |
| recall_range_low | 0.9374 |
| recall_range_high | 0.9564 |
| F1 | 0.9438 |
| relevant_share_in_rejected | 0.6700 |
| rejected_share_CI95_low | 0.5731 |
| rejected_share_CI95_high | 0.7544 |
| to_check_by_hand | 0 |
| estimated_drone_families_kept | 158,544.16 |
| estimated_drone_families_lost | 8,749.53 |
| tau_filter | 0.45 |
| prompt_id | `22e63c620e` |

Of the 100 sampled families selected by the filter, 94 were labelled relevant and six were labelled irrelevant. Of the 100 sampled rejected families, 67 were labelled relevant. Recall is estimated within the scored candidate pool.

## TEST and PROD results

| Measure | TEST · phase2a-test-001 | PROD · phase2a-prod-001 |
| --- | ---: | ---: |
| Applications scored | 3,016 | 216,775 |
| Applications passing the filter | 2,610 | 199,121 |
| Selected DOCDB families | 2,048 | 168,664 |
| Final extracted families | 1,854 | 106,998 |
| Extracted families with applicant records | 1,843 | 106,877 |
| Applicant relationship records | 3,181 | 169,122 |
| Distinct applicant person IDs | 2,018 | 53,000 |
| Harmonized applicant entities | 1,640 | 42,769 |
| Applicant records flagged for review | 268 | 37,063 |

## Production extraction

| Notebook 3 output | Count |
| --- | ---: |
| Final DOCDB families | 106,998 |
| Application member rows | 149,045 |
| CPC classification rows | 1,099,152 |
| Person rows | 708,230 |
| Families with an English abstract | 106,994 |
| EP publications | 11,775 |
| Backward citations | 42,324 |
| Forward citations (EP) | 1,881 |

The report includes the extraction rules, all eight adjudicated family decisions, applicant coverage and the inventory of Step 1 tables. [Read the daily report](Flying-Drones-Patent-Analytics-Report-2026-11-23.pdf)
