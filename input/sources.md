# Input materials

All inputs for DocDiffOps planning and first comparison batch.
Open-source unless noted.

## Reference documents (downloaded from open sources)

| File | Source URL | Description | Source rank |
| --- | --- | --- | --- |
| `concept_2026_2030_kremlin.html` | http://www.kremlin.ru/acts/bank/52490 | New migration policy concept 2026–2030, Presidential Decree | 1 (official NPA) |
| ⚠️ `concept_2019_2025_ukaz_622.pdf` | https://tinao.mos.ru/Ukaz_Prezidenta_RF_ot_31.10.2018_622_O_Kontseptsii_gosudarstvennoy_migratsionnoy_politiki_Rossiyskoy_Federatsii_na_2019_2025_gody_.pdf | Old migration policy concept 2019–2025, Presidential Decree №622 of 31.10.2018 | 1 (official NPA) |
| `fz_109_migration_registration.html` | https://normativ.kontur.ru/document?moduleId=1&documentId=504542 | Federal Law on migration registration of foreign citizens (2006, ed. 31.07.2025) | 2 (legal system) |
| `rasporjazenie_30r_2024.pdf` | https://www.profiz.ru/upl/pictures/SR/_01_2024/Распоряжение Правительства Российской Федерации от 16.01.2024 № 30-р.pdf | Government Order 30-r of 16.01.2024 on Concept implementation | 1 (official NPA) |
| ⚠️ `klerk_normative_summary.html` | https://www.klerk.ru/blogs/astral/658232/ | Klerk.ru summary of regulations for foreign workers | 3 (analytics/blog) |
| ⚠️ `mineconomy_migration_index.html` | https://www.economy.gov.ru/material/departments/d04/migracionnaya_politika/ | Ministry of Economy migration policy materials index | 2 (departmental) |
| `vciom_migration_2026.pdf` | provided by user | VCIOM analytics presentation on migration indicators | 3 (analytics presentation) |

## Internal materials (provided by user)

| File | Description |
| --- | --- |
| `internal_neuron_manual_v2.pdf` | Internal manual for the existing "Сравнение документов" / "Нейрон" service — reference for what NOT to repeat |
| `sample_neuron_comparison_brief.xlsx` | Sample output of existing internal service for one presentation pack — reference for evidence matrix shape |

## Download status

⚠️ marks files that could not be retrieved automatically from this network on 2026-05-08
(connection timeout to tinao.mos.ru and economy.gov.ru, partial response from klerk.ru):

- `concept_2019_2025_ukaz_622.pdf` — **missing**, retrieve manually before running batch
- `mineconomy_migration_index.html` — **missing**, retrieve manually before running batch
- `klerk_normative_summary.html` — **partial** (16 KB, truncated mid-page), re-download recommended

The remaining 6 input files are present and intact (sha256 will be computed at upload time).

## Source ranking rule

- **rank 1**: official NPA (federal laws, presidential decrees, government orders)
- **rank 2**: departmental/ministerial info, legal databases
- **rank 3**: analytics, presentations, blog posts, expert summaries

`rank 3` cannot refute `rank 1`. It can be: not-confirmed, partially-confirmed, contradicting-as-thesis, or manual-review.

## Comparison pairs (planning batch 1)

All-to-all over the 9 files above → `9 * 8 / 2 = 36 pairs`.
First-pass: deterministic fuzzy/block diff. Second-pass: legal + claim_validation. Anchor for report rendering: TBD by user.
