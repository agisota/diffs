# Input materials

All inputs for DocDiffOps planning and first comparison batch.
Open-source unless noted.

## Reference documents (downloaded from open sources)

| File | Source URL | Description | Source rank |
| --- | --- | --- | --- |
| `concept_2026_2030_kremlin.html` | http://www.kremlin.ru/acts/bank/52490 | New migration policy concept 2026–2030, Presidential Decree | 1 (official NPA) |
| `ukaz_622_concept_2019_2025_kremlin.html` | http://www.kremlin.ru/acts/bank/43577 | Old migration policy concept 2019–2025, Presidential Decree №622 of 31.10.2018 | 1 (official NPA) |
| `ukaz_580_grazhdanstvo_2025.html` | http://www.kremlin.ru/acts/bank/52489 | Presidential Decree on simplifying citizenship procedures (2025) | 1 (official NPA) |
| `fz_109_migration_registration.html` | https://normativ.kontur.ru/document?moduleId=1&documentId=504542 | Federal Law on migration registration of foreign citizens (2006, ed. 31.07.2025) | 2 (legal system) |
| `rasporjazenie_30r_2024.pdf` | https://www.profiz.ru/upl/pictures/SR/_01_2024/Распоряжение Правительства Российской Федерации от 16.01.2024 № 30-р.pdf | Government Order 30-r of 16.01.2024 on Concept implementation | 1 (official NPA) |
| `post_pravitelstva_794_deportacia.html` | http://government.ru/docs/all/52186/ | Government Order on deportation/expulsion procedures | 1 (official NPA) |
| ⚠️ `klerk_normative_summary.html` | https://www.klerk.ru/blogs/astral/658232/ | Klerk.ru summary of regulations for foreign workers | 3 (analytics/blog) |
| `fom_migration_2024.html` | https://fom.ru/Mir/14856 | FOM analytics: Russian attitudes toward migrants (2024) | 3 (analytics) |
| `levada_migrants.html` | https://www.levada.ru/2024/06/11/migranty-v-rossii/ | Levada-Centre analytics: migrants in Russia (June 2024) | 3 (analytics) |
| `vciom_migration_2026.pdf` ¹ | provided by user | VCIOM analytics presentation on migration indicators | 3 (analytics presentation) |

¹ Compressed via `gs -dPDFSETTINGS=/ebook` from 7.5 MB → 2.75 MB to fit GitHub HTTP push window (server enforces ~30 s on receive-pack at this network's upload rate). Visual content preserved; if pixel-exact sourcing is needed, re-download from the analytics team and replace.

## Internal materials (provided by user)

| File | Description |
| --- | --- |
| `internal_neuron_manual_v2.pdf` | Internal manual for the existing "Сравнение документов" / "Нейрон" service — reference for what NOT to repeat |
| `sample_neuron_comparison_brief.xlsx` | Sample output of existing internal service for one presentation pack — reference for evidence matrix shape |

## Download status

⚠️ marks files that could not be retrieved automatically from this network on 2026-05-09:

- `klerk_normative_summary.html` — **partial** (16 KB, truncated mid-page), re-download recommended

Sites that were geo-blocked / unreachable from the download host (use a different network or VPN
to retrieve manually):
- consultant.ru (returned bot-block stubs ~16 KB for FZ 115 / 114 / 62 / 99)
- pravo.gov.ru, docs.cntd.ru (connection timeout)
- mvd.ru, economy.gov.ru, tinao.mos.ru (connection timeout)
- vciom.ru analytical-reviews endpoints (returned 2.3 KB stubs)

The remaining files are present and intact. Total: **12 distinct documents** suitable for a
C(12, 2) = 66-pair batch.

## Source ranking rule

- **rank 1**: official NPA (federal laws, presidential decrees, government orders)
- **rank 2**: departmental/ministerial info, legal databases
- **rank 3**: analytics, presentations, blog posts, expert summaries

`rank 3` cannot refute `rank 1`. It can be: not-confirmed, partially-confirmed, contradicting-as-thesis, or manual-review.

## Comparison pairs (planning batch 1)

All-to-all over the 9 files above → `9 * 8 / 2 = 36 pairs`.
First-pass: deterministic fuzzy/block diff. Second-pass: legal + claim_validation. Anchor for report rendering: TBD by user.
