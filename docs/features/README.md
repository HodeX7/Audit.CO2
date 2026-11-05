# Feature docs: Ingestion & Ledger (Ujjwal)

One file per shipped feature. Each one says **why** the feature exists, **how it is designed**, the
**architecture** (diagram), the **decisions** behind it, a **code map**, and how it is **tested**.

| Feature | Doc | Main code |
| --- | --- | --- |
| Contract-compatible shared types | [contract-compatibility.md](contract-compatibility.md) | `carbon_room/models.py` |

Decision log: [../DECISIONS.md](../DECISIONS.md). Current implementation status: [../STATUS.md](../STATUS.md).

## Rules for keeping docs true

1. **One pull request per feature.** The PR that changes code also changes its feature documentation.
2. **Docs describe the code as it is, not as planned.** Plans go in `docs/STATUS.md` under "Next".
