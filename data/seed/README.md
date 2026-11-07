# Carbon Room contract seed

`scripts/make_seed.py` deterministically creates the synthetic September and October evidence sets used by the
contract ingestion tests. Every PDF is labelled as synthetic and fictional. The held-back Warehouse-2 upload lives
in `data/demo_uploads/` so it is never ingested by the normal close collection path.

`EXPECTED.md` is the P2 calculation/check/resolution baseline. Regenerate it read-only with
`python -m scripts.generate_expected` and verify the checked-in file with
`python -m scripts.generate_expected --check`. The generator uses a temporary database and source-store directory.
