# How ingestion and the ledger work (plain language)

Owner: Ujjwal. Written so any teammate can answer a judge's question without notes.

## The one promise

Every number in the ledger points to a real document, the exact line it came from, and a hash.
If we can't prove a number from the document, it doesn't go in as a fact: it becomes a gap for a named
person to fix in chat.

## The path of one bill

Take Lena's October electricity bill for the Reno Office.

1. **It arrives.** An agent downloads it from the `cr-site-reno` room and runs
   `carbonroom ingest file.pdf --from lena --room cr-site-reno --json`, or drops it in `data/inbox/cr-site-reno/`.
2. **Collector: who is this file?** We compute the SHA-256 of its bytes. If that hash is already in the ledger,
   we skip it: uploading the same bill twice, even under another name, changes nothing. New files are copied to
   `data/store/<hash>.pdf`, so the evidence can't change or vanish later.
3. **Read the text.** `pdfplumber` gives the text of each page.
4. **Propose.** Something suggests what the bill says: the site, the month, and "electricity, 15.08 MWh",
   each with the exact line it read and the page number. The proposer is one of:
   - the **cache** (`data/seed/extractions/<hash>.json`), so the demo runs with no API key
   - the **LLM** (NVIDIA's free API by default, through `carbonroom/llm.py`)
   - the **rules** proposer, label patterns that need no network
5. **Verify: the important part.** Code, not the model, checks each proposal:
   - Is the quoted line really in the document? We ignore spacing and capitals, nothing else.
   - Is the number really in that line? Is the unit?
   - Does the "site" line name exactly one of our sites, and does it agree with the proposal?
   - Does the "period" line name exactly one month, and is it the proposed month?

   If any check fails, the value is rejected and an `unverified_claim` gap goes to the site owner. We store
   the full source line ourselves (not the model's version), and code works out the page and line number.
6. **Normalize units.** 15.08 MWh becomes 15,080 kWh. Litres become US gallons (exactly 3.785411784 L per
   gallon). The original number and unit stay in `extra_json`. Units that would need a guess, like gas in
   cubic feet (that needs the utility's heat content), are refused and become a gap.
7. **Consolidate.** One `activities` row per proven claim, always `UNVERIFIED`. Only Richa's checker can
   verify. Every write is logged in `events`.

## The traps, and why ingestion handles them this way

- **Two invoices for one delivery** (500 vs 550 gal): we store **both**, each linked to its own invoice and
  the shared delivery ticket `DLV-7731`. Picking one would be guessing; the checker asks Omar.
- **Corrected bill:** a document that says "Replaces bill: ELB-AUS-2610" (and proves it in an excerpt) marks
  the old document as superseded and records which old row the new one replaces. We **don't** change the
  old row ourselves. If the checker had already said VERIFIED, it now has to notice and reopen it: that's
  the "false done" moment in the demo.
- **Missing bill:** each site lists the documents it must send every month (`expected_documents`). Reno's
  October bill isn't there, so `expected_but_missing` reports it with Lena as the owner. Diesel is "as
  delivered", so a month with no delivery isn't a false alarm.
- **REC certificate:** stored with its own proof (MWh, region, vintage, which load it's claimed against). The
  checker decides it's low quality (generated in the Northwest, claimed against a Virginia load, 2023 vintage).

## Why the database can't be talked into lying

The rules are in the database, not just in our Python, so they hold even if an agent writes raw SQL:

- every table refuses `DELETE` (corrections supersede, they never erase)
- quantity, excerpt and source of an activity can't be edited after it's written
- the audit log, approvals and calculations are append-only
- a gap can't be closed without the name of the person who resolved it and what they said
- a month can't be marked `CLOSED` unless that approver's `APPROVE` is recorded

Quantities are stored as exact decimal text (`"499.998"`), never floating point, so the same inputs always give
the same totals.

## Questions judges might ask

**"Isn't the LLM making numbers up?"** It can try, but it can't get one into the ledger. A number is accepted only
if the quoted line exists in the PDF and contains that number and unit. Our tests feed in a made-up "16.08 MWh":
it's rejected and becomes a gap for Lena.

**"What if the cache file is edited by hand?"** The cache is only a proposal. It goes through the same checks
every run; an edited value fails and becomes a gap (there's a test for this).

**"Can you prove a number later?"** `carbonroom ledger verify` re-hashes every stored document and finds every
excerpt again on its recorded page. It fails loudly if anything changed.

**"Why a rules proposer if you have an LLM?"** So anyone can clone the repo and reproduce the demo without a key,
and so a rate limit (the free tier allows about 40 requests per minute) never stops a live demo. Both go through
the same verifier.

**"Why is the cloud a 'site'?"** So its gaps go to Dev in `cr-cloud`, like any site's go to its owner. It is marked
`kind = cloud`; purchased cloud is Scope 3 Category 1 and is kept out of the Scope 1+2 total.

**"What happens if two agents write at once?"** SQLite in WAL mode with a 30-second busy timeout. Writes take the
lock (`BEGIN IMMEDIATE`), and a document is added together with its rows in one transaction, all or nothing.

## Where the code is

| File | Job |
| --- | --- |
| `contracts/schema.sql` | tables plus guard triggers |
| `carbonroom/ledger/db.py` | the only way into the ledger |
| `carbonroom/ingest/collector.py` | hashing, duplicate skipping, the inbox, the evidence store |
| `carbonroom/ingest/extract.py` | page text, proposers, cache, **verification** |
| `carbonroom/ingest/rules.py` | keyless rules proposer and document-kind rules |
| `carbonroom/llm.py` | NVIDIA/Anthropic client, throttling, retries |
| `carbonroom/ingest/units.py` | unit normalization |
| `carbonroom/ingest/consolidator.py` | rows, supersede links, gaps |
| `carbonroom/ingest/pipeline.py` | ties it together; watch mode |
| `carbonroom/ingest/evidence.py` | evidence re-check for the checker |
| `carbonroom/ingest/seedgen.py`, `seed.py` | fictional documents; `carbonroom seed` |
| `carbonroom/cli.py` | the `carbonroom` command |

## Extraction proposal format (`cr.extraction.v1`)

```json
{
  "doc_kind": "utility_bill",
  "doc_ref":  {"value": "ELB-RNO-2610", "excerpt": "Bill number: ELB-RNO-2610", "page": 1},
  "replaces_ref": null,
  "site":     {"value": "Reno Office", "excerpt": "Service location: Reno Office, 77 Ledger Lane, ...", "page": 1},
  "period":   {"value": "2026-10", "excerpt": "Service period: October 1, 2026 - October 31, 2026", "page": 1},
  "claims": [{"category": "electricity", "quantity": "15.08", "unit": "MWh",
              "excerpt": "Total energy used this period: 15.08 MWh", "page": 1, "fields": {}}],
  "instruments": []
}
```
