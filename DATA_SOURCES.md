# Data sources

All datasets are downloaded locally by `scripts/download_data.py` into the git-ignored
`data/` folder. Nothing here is committed or redistributed. Sources and licences were
confirmed by the owner on 2026-10-26.

## Chinook (sample database)

- **What:** a sample SQLite database of a digital music store (artists, albums, tracks,
  customers, invoices). Used for the safety suite and the live demo.
- **Official source:** <https://github.com/lerocha/chinook-database> — the
  `Chinook_Sqlite.sqlite` asset on the [releases page](https://github.com/lerocha/chinook-database/releases).
- **Licence:** MIT (per the repository's `LICENSE.md`).
- **Checksum:** recorded against the downloaded asset by the download script.

## Spider (text-to-SQL benchmark)

- **What:** ~10,181 questions over ~200 SQLite databases, each question paired with a gold SQL
  query and result. Used to measure execution accuracy in the eval harness (P5).
- **Official source:** Yale LILY — <https://yale-lily.github.io/spider> (repo
  <https://github.com/taoyds/spider>).
- **Download used:** questions + gold SQL from the Hugging Face mirror
  [`xlangai/spider`](https://huggingface.co/datasets/xlangai/spider) (dev = `validation` split,
  1,034 questions over 20 databases); the SQLite **databases** come per-file from
  [`premai-io/spider`](https://huggingface.co/datasets/premai-io/spider)
  (`database/<db_id>/<db_id>.sqlite`), fetched on demand by `eval/build_slice.py`. The
  `xlangai/spider` parquet ships questions only, so the databases needed to compute gold
  results come from the second repo (see `DECISIONS.md`).
- **Licence:** CC-BY-SA-4.0. We only *use* the data (never redistribute it, since `data/` is
  git-ignored) and attribute it here and in the README.
