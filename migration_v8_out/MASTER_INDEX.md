# MASTER INDEX — Forensic v8 пакет

Provenance-grade список всех артефактов с SHA-256 fingerprint.
Сгенерировано: 2026-05-09 04:44:49Z

| Размер | SHA-256 (16) | Путь |
|---:|:---|:---|
|     8,912 | `63f6bf409b6373d6…` | `NAVIGATION.md` |
|     3,156 | `bdd0756fb3a8b450…` | `SUMMARY.md` |
|    16,095 | `103f7a0a449ab95c…` | `data/01_источники_v8.csv` |
|   113,950 | `e3ad7547f806542c…` | `data/02_pairs_v8.csv` |
|     4,117 | `6b800c3c1628dbd2…` | `data/03_doc_x_doc_matrix.csv` |
|     1,830 | `cbeb689814103754…` | `data/04_topic_x_doc.csv` |
|    76,844 | `78baac312f37ce43…` | `data/05_thesis_x_npa.csv` |
|     2,666 | `c295c31a3b98806e…` | `data/06_old_vs_new_redactions.csv` |
|     1,416 | `a64e8d26acde0095…` | `data/07_regime_x_regime.csv` |
|     6,822 | `93d883e0ade5b323…` | `data/08_provenance_risk.csv` |
|    57,166 | `184b83c7d38383b8…` | `data/09_manual_review_queue.csv` |
|    11,837 | `ebbdfe5d62bba190…` | `data/10_actions_catalogue.csv` |
|     3,604 | `4687b98c799d51f0…` | `data/11_brochure_redgreen_diff.csv` |
|     2,999 | `9b6b8531e5813eb3…` | `data/12_klerk_npa_links.csv` |
|     2,980 | `850a06436415c320…` | `data/13_eaeu_split.csv` |
|     1,915 | `b252a71b068aa47a…` | `data/14_amendment_chain.csv` |
|     1,893 | `9a25569f4db4fe60…` | `data/15_provenance_actions.csv` |
|     3,012 | `ebdd8befba43f0c5…` | `data/16_top_priority_review.csv` |
|     4,000 | `507ae98a16bb04e9…` | `data/17_raci_matrix.csv` |
|    12,028 | `98ed84ad33a83d2a…` | `data/18_doc_xref.csv` |
|    38,068 | `d3f586528a9b7697…` | `data/integral_cross_comparison.json` |
|     8,238 | `c5afd745128d2dc9…` | `data/v8_bundle.schema.json` |
|   483,902 | `63d0a64fe8576ced…` | `docs/Forensic_v8_cover.pdf` |
|   192,451 | `9067e504a617ea28…` | `docs/Forensic_v8_report.html` |
|   151,750 | `edfb80adc3c66f31…` | `docs/visuals/cover_summary.png` |
|   147,988 | `526d4e1f7e639608…` | `docs/visuals/heatmap_doc_x_doc.png` |
|    31,949 | `c6cb5506d927e796…` | `docs/visuals/rank_pair_bar.png` |
|    57,813 | `33bae506da40400a…` | `docs/visuals/status_pie.png` |
|   110,800 | `6bbac0031d94ac36…` | `docs/visuals/topic_bar.png` |
|    47,484 | `a1038a0ae98efdba…` | `docs/Интегральное_перекрестное_сравнение.pdf` |
|    88,683 | `1a0f709faf7d3b88…` | `docs/Интегральное_перекрестное_сравнение.xlsx` |
|    38,509 | `c1202756ee2837b5…` | `docs/Лист_согласования.docx` |
|    39,225 | `c2a343dc27f9186f…` | `docs/Лист_согласования.pdf` |
|   152,256 | `c1ad7a90d43732eb…` | `docs/Несоответствия_и_действия.xlsx` |
|    41,237 | `164db062f13e83e2…` | `docs/Пояснительная_записка.docx` |
|    43,491 | `fb74c8936088083d…` | `docs/Пояснительная_записка.pdf` |
|    41,937 | `fb447b8fb9cb1399…` | `docs/Редакционный_diff.docx` |
|    52,226 | `7277e6b193f631f0…` | `docs/Редакционный_diff.pdf` |
|    45,607 | `6c569eb9afed3cbf…` | `docs/Что_делать.docx` |
|    51,899 | `2fa57ef3ff653f4c…` | `docs/Что_делать.pdf` |
|     1,436 | `0a02a36cf0b7cee9…` | `logs/build.log` |
|     2,120 | `b26520ad82b39f4c…` | `logs/qa.json` |
|       654 | `a253f51be44eae88…` | `logs/qa_v8_1.json` |
|       550 | `6d3a2c269db9c5d6…` | `logs/qa_v8_2.json` |
|       364 | `ff3e11e76ff37051…` | `logs/qa_v8_3.json` |
|   102,551 | `817f4d6e298f5c61…` | `scripts/__pycache__/build_integral.cpython-314.pyc` |
|    85,556 | `66c609ff7492e8f8…` | `scripts/build_integral.py` |
|    14,135 | `2126d698c5d87424…` | `scripts/build_v8_2.py` |
|    24,216 | `da43a6a507eb0993…` | `scripts/build_v8_3.py` |
|    27,335 | `ce08b3fce95d3e8a…` | `scripts/build_v8_4.py` |
|    12,434 | `713d075b370832e1…` | `scripts/build_visuals.py` |
|    68,336 | `fc8e6260e58ad7c8…` | `scripts/enhance_v8.py` |


## Total

- **Файлов**: 52
- **Совокупный размер**: 2,542,442b (2.42 MB)

## Re-verify

```bash
cd /home/dev/diff/migration_v8_out
python3 -c "import hashlib, sys; [print(hashlib.sha256(open(f, 'rb').read()).hexdigest()[:16], f) for f in sys.argv[1:]]" \
  data/v8_bundle.schema.json data/integral_cross_comparison.json
```
