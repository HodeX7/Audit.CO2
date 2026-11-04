"""Generate the fictional seed documents (text-based PDFs) for the demo, traps included.

Everything here is invented: Brightwell Manufacturing, the utilities, the fuel supplier,
Nimbus Cloud, the registry, addresses and account numbers. Each page carries a
"FICTIONAL DOCUMENT" footer.

Run:  carbonroom seed --regenerate-docs     (or: python -m carbonroom.ingest.seedgen)

Output is deterministic (reportlab `invariant` mode), so the file hashes - and therefore
the extraction cache keys in data/seed/extractions/ - stay the same across runs with the
pinned reportlab version.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path

FOOTER = (
    "FICTIONAL DOCUMENT - created for the Carbon Room hackathon demo. "
    "Brightwell Manufacturing and every name, address and number here are invented. Not a real bill."
)

CUSTOMER = "Brightwell Manufacturing"
AUSTIN_ADDR = "Austin Plant, 4100 Foundry Row, Austin, TX (fictional address)"
RENO_ADDR = "Reno Office, 77 Ledger Lane, Suite 300, Reno, NV (fictional address)"


@dataclass
class SeedDoc:
    file: str
    folder: str  # 'docs' = loaded by `carbonroom seed`; 'later' = held back for the live demo
    kind: str
    site: str
    period: str
    received_from: str
    room: str
    traps: list[str]
    description: str
    pages: list[list[tuple[str, str]]] = field(default_factory=list)


def _bill(issuer, issuer_addr, title, ref, account, location, period_line, usage_line, extra, charges):
    lines = [
        ("issuer", issuer),
        ("small", issuer_addr),
        ("title", title),
        ("kv", f"Bill number: {ref}"),
        ("kv", f"Account: {account}"),
        ("kv", f"Customer: {CUSTOMER}"),
        ("kv", f"Service location: {location}"),
        ("kv", period_line),
        ("rule", ""),
        ("h2", "Usage"),
        ("kv", usage_line),
        *[("kv", e) for e in extra],
        ("rule", ""),
        ("h2", "Charges"),
        *[("kv", c) for c in charges],
    ]
    return lines


def seed_documents() -> list[SeedDoc]:
    docs: list[SeedDoc] = []

    # --- Austin Plant electricity -------------------------------------------------------
    docs.append(SeedDoc(
        file="2026-09_austin_electricity_ELB-AUS-2609.pdf", folder="docs", kind="utility_bill",
        site="austin", period="2026-09", received_from="omar", room="cr-site-austin",
        traps=["baseline"],
        description="Austin Plant electricity, September 2026: 182,400 kWh.",
        pages=[_bill(
            "Cedar Mesa Power & Light", "PO Box 4410, Cedar Mesa, TX (fictional utility)",
            "ELECTRICITY BILL", "ELB-AUS-2609", "4471-0920-AUS", AUSTIN_ADDR,
            "Service period: September 1, 2026 - September 30, 2026",
            "Total energy used this period: 182,400 kWh",
            ["Meter: CMPL-M-77120", "Peak demand: 398 kW"],
            ["Bill date: October 3, 2026", "Energy charge: $14,592.00", "Delivery charge: $2,188.80",
             "Amount due: $16,780.80"],
        )],
    ))
    docs.append(SeedDoc(
        file="2026-10_austin_electricity_ELB-AUS-2610.pdf", folder="docs", kind="utility_bill",
        site="austin", period="2026-10", received_from="omar", room="cr-site-austin",
        traps=["false_done (original; later replaced by ELB-AUS-2610-C)"],
        description="Austin Plant electricity, October 2026: 191,300 kWh. The utility later re-issues it.",
        pages=[_bill(
            "Cedar Mesa Power & Light", "PO Box 4410, Cedar Mesa, TX (fictional utility)",
            "ELECTRICITY BILL", "ELB-AUS-2610", "4471-0920-AUS", AUSTIN_ADDR,
            "Service period: October 1, 2026 - October 31, 2026",
            "Total energy used this period: 191,300 kWh",
            ["Meter: CMPL-M-77120", "Peak demand: 412 kW", "Meter read type: estimated"],
            ["Bill date: November 2, 2026", "Energy charge: $15,304.00", "Delivery charge: $2,295.60",
             "Amount due: $17,599.60"],
        )],
    ))
    docs.append(SeedDoc(
        file="2026-10_austin_electricity_ELB-AUS-2610-C.pdf", folder="later", kind="utility_bill",
        site="austin", period="2026-10", received_from="omar", room="cr-site-austin",
        traps=["false_done (corrected bill; supersedes ELB-AUS-2610)"],
        description="Corrected Austin October bill: 196,800 kWh. Replaces ELB-AUS-2610 after an actual meter read.",
        pages=[[
            ("issuer", "Cedar Mesa Power & Light"),
            ("small", "PO Box 4410, Cedar Mesa, TX (fictional utility)"),
            ("title", "CORRECTED ELECTRICITY BILL"),
            ("kv", "Bill number: ELB-AUS-2610-C"),
            ("kv", "Replaces bill: ELB-AUS-2610 (meter read correction)"),
            ("kv", "Account: 4471-0920-AUS"),
            ("kv", f"Customer: {CUSTOMER}"),
            ("kv", f"Service location: {AUSTIN_ADDR}"),
            ("kv", "Service period: October 1, 2026 - October 31, 2026"),
            ("rule", ""),
            ("h2", "Usage"),
            ("kv", "Total energy used this period: 196,800 kWh"),
            ("kv", "Meter: CMPL-M-77120"),
            ("kv", "Meter read type: actual (replaces an estimated read)"),
            ("rule", ""),
            ("h2", "Charges"),
            ("kv", "Bill date: November 9, 2026"),
            ("kv", "Energy charge: $15,744.00"),
            ("kv", "Delivery charge: $2,361.60"),
            ("kv", "Amount due: $18,105.60"),
        ]],
    ))

    # --- Reno Office electricity (reported in MWh) -----------------------------------
    docs.append(SeedDoc(
        file="2026-09_reno_electricity_ELB-RNO-2609.pdf", folder="docs", kind="utility_bill",
        site="reno", period="2026-09", received_from="lena", room="cr-site-reno",
        traps=["unit_normalization (MWh -> kWh)"],
        description="Reno Office electricity, September 2026: 14.62 MWh (stored as 14,620 kWh).",
        pages=[_bill(
            "Sagebrush Valley Electric", "1 Basin Road, Sagebrush Valley, NV (fictional utility)",
            "ELECTRIC SERVICE STATEMENT", "ELB-RNO-2609", "SVE-88213-RNO", RENO_ADDR,
            "Service period: September 1, 2026 - September 30, 2026",
            "Total energy used this period: 14.62 MWh",
            ["Meter: SVE-0042-118"],
            ["Bill date: October 5, 2026", "Energy and delivery: $1,754.40", "Amount due: $1,754.40"],
        )],
    ))
    docs.append(SeedDoc(
        file="2026-10_reno_electricity_ELB-RNO-2610.pdf", folder="later", kind="utility_bill",
        site="reno", period="2026-10", received_from="lena", room="cr-site-reno",
        traps=["missing_bill (held back; Lena uploads it in the gap thread during the demo)"],
        description="Reno Office electricity, October 2026: 15.08 MWh. Not loaded by `carbonroom seed`.",
        pages=[_bill(
            "Sagebrush Valley Electric", "1 Basin Road, Sagebrush Valley, NV (fictional utility)",
            "ELECTRIC SERVICE STATEMENT", "ELB-RNO-2610", "SVE-88213-RNO", RENO_ADDR,
            "Service period: October 1, 2026 - October 31, 2026",
            "Total energy used this period: 15.08 MWh",
            ["Meter: SVE-0042-118"],
            ["Bill date: November 4, 2026", "Energy and delivery: $1,809.60", "Amount due: $1,809.60"],
        )],
    ))

    # --- Austin Plant natural gas (October is the outlier) ---------------------------
    docs.append(SeedDoc(
        file="2026-09_austin_gas_GAS-AUS-2609.pdf", folder="docs", kind="utility_bill",
        site="austin", period="2026-09", received_from="omar", room="cr-site-austin",
        traps=["baseline for the outlier"],
        description="Austin Plant natural gas, September 2026: 4,800 therms.",
        pages=[_bill(
            "Pecan Hollow Gas Company", "220 Mill Street, Pecan Hollow, TX (fictional utility)",
            "NATURAL GAS BILL", "GAS-AUS-2609", "PHG-55190-AUS", AUSTIN_ADDR,
            "Service period: September 1, 2026 - September 30, 2026",
            "Total gas used this period: 4,800 therms",
            ["Meter: PHG-M-3307"],
            ["Bill date: October 4, 2026", "Gas supply charge: $4,320.00", "Amount due: $4,320.00"],
        )],
    ))
    docs.append(SeedDoc(
        file="2026-10_austin_gas_GAS-AUS-2610.pdf", folder="docs", kind="utility_bill",
        site="austin", period="2026-10", received_from="omar", room="cr-site-austin",
        traps=["outlier (+60.4% vs September; owner is asked to confirm)"],
        description="Austin Plant natural gas, October 2026: 7,700 therms (about 60% above September).",
        pages=[_bill(
            "Pecan Hollow Gas Company", "220 Mill Street, Pecan Hollow, TX (fictional utility)",
            "NATURAL GAS BILL", "GAS-AUS-2610", "PHG-55190-AUS", AUSTIN_ADDR,
            "Service period: October 1, 2026 - October 31, 2026",
            "Total gas used this period: 7,700 therms",
            ["Meter: PHG-M-3307"],
            ["Bill date: November 3, 2026", "Gas supply charge: $6,930.00", "Amount due: $6,930.00"],
        )],
    ))

    # --- Austin Plant diesel (backup generators) -------------------------------------
    def fuel(issuer, issuer_addr, ref, inv_date, ticket, delivery_date, qty_line, price, total):
        return [[
            ("issuer", issuer),
            ("small", issuer_addr),
            ("title", "FUEL INVOICE"),
            ("kv", f"Invoice number: {ref}"),
            ("kv", f"Invoice date: {inv_date}"),
            ("kv", f"Bill to: {CUSTOMER}"),
            ("kv", f"Deliver to: {AUSTIN_ADDR} - backup generator tank"),
            ("rule", ""),
            ("h2", "Delivery"),
            ("kv", f"Delivery ticket: {ticket}"),
            ("kv", f"Delivery date: {delivery_date}"),
            ("kv", "Product: Ultra-low sulfur diesel No. 2 (off-road)"),
            ("kv", qty_line),
            ("rule", ""),
            ("h2", "Charges"),
            ("kv", price),
            ("kv", total),
        ]]

    docs.append(SeedDoc(
        file="2026-09_austin_diesel_INV-188.pdf", folder="docs", kind="fuel_invoice",
        site="austin", period="2026-09", received_from="omar", room="cr-site-austin",
        traps=["unit_normalization (litres -> US gallons)"],
        description="Austin Plant diesel, September 2026: 1,892.7 L (stored as 499.998 gal).",
        pages=fuel("Northbank Energy Logistics", "9 Wharf Road, Northbank, TX (fictional supplier)",
                   "INV-188", "September 18, 2026", "DLV-7590", "September 17, 2026",
                   "Quantity delivered: 1,892.7 L", "Price per litre: $0.91", "Total due: $1,722.36"),
    ))
    docs.append(SeedDoc(
        file="2026-10_austin_diesel_INV-204.pdf", folder="docs", kind="fuel_invoice",
        site="austin", period="2026-10", received_from="omar", room="cr-site-austin",
        traps=["conflict (same delivery DLV-7731 as INV-204B, different quantity)"],
        description="Austin Plant diesel, October 2026: invoice INV-204 says 500.0 gal for delivery DLV-7731.",
        pages=fuel("Redtail Fuel Supply - Austin Depot", "3300 Depot Road, Austin, TX (fictional supplier)",
                   "INV-204", "October 15, 2026", "DLV-7731", "October 14, 2026",
                   "Quantity delivered: 500.0 gal", "Price per gallon: $3.42", "Total due: $1,710.00"),
    ))
    docs.append(SeedDoc(
        file="2026-10_austin_diesel_INV-204B.pdf", folder="docs", kind="fuel_invoice",
        site="austin", period="2026-10", received_from="omar", room="cr-site-austin",
        traps=["conflict (same delivery DLV-7731 as INV-204, says 550.0 gal)"],
        description="Austin Plant diesel, October 2026: invoice INV-204B says 550.0 gal for the same delivery.",
        pages=fuel("Redtail Fuel Supply - Billing Center", "PO Box 7731, Round Mesa, TX (fictional supplier)",
                   "INV-204B", "October 22, 2026", "DLV-7731", "October 14, 2026",
                   "Quantity delivered: 550.0 gal", "Price per gallon: $3.42", "Total due: $1,881.00"),
    ))

    # --- Nimbus Cloud invoices (2 pages: charges, then energy & water disclosure) ------
    def cloud(ref, period_text, inv_date, it_kwh, pue, wue, charges):
        return [
            [
                ("issuer", "Nimbus Cloud, Inc."),
                ("small", "500 Stratus Avenue, Ashgrove, VA (fictional provider)"),
                ("title", "CLOUD SERVICES INVOICE"),
                ("kv", f"Invoice number: {ref}"),
                ("kv", f"Invoice date: {inv_date}"),
                ("kv", f"Billing period: {period_text}"),
                ("kv", f"Customer: {CUSTOMER}"),
                ("kv", "Account: BW-NC-30114"),
                ("kv", "Region: us-east-va (Virginia)"),
                ("rule", ""),
                ("h2", "Charges"),
                *[("kv", c) for c in charges],
                ("rule", ""),
                ("p", "See page 2 for the energy and water disclosure for this billing period."),
            ],
            [
                ("issuer", "Nimbus Cloud, Inc."),
                ("title", "ENERGY AND WATER DISCLOSURE"),
                ("kv", f"Invoice number: {ref}"),
                ("kv", f"Billing period: {period_text}"),
                ("kv", "Region: us-east-va (Virginia)"),
                ("rule", ""),
                ("kv", f"IT equipment energy attributed to this account: {it_kwh} kWh"),
                ("kv", f"Power usage effectiveness (PUE), facility average: {pue}"),
                ("kv", f"Water usage effectiveness (WUE): {wue} L/kWh"),
                ("p", "Method: metered rack power for dedicated hosts; shared hosts allocated by vCPU-hours."),
                ("p", "Facility energy = IT energy x PUE. Water = IT energy x WUE."),
            ],
        ]

    docs.append(SeedDoc(
        file="2026-09_nimbus_cloud_NC-2609.pdf", folder="docs", kind="cloud_invoice",
        site="nimbus-cloud", period="2026-09", received_from="dev", room="cr-cloud",
        traps=["data_centre_line (baseline)"],
        description="Nimbus Cloud, September 2026: IT energy 36,900 kWh, PUE 1.36, WUE 0.43 L/kWh (page 2).",
        pages=cloud("NC-2609", "September 2026", "October 2, 2026", "36,900", "1.36", "0.43",
                    ["Compute instances (reserved, 64 vCPU x 12): $18,240.00",
                     "GPU inference hours (1,310 h): $4,585.00",
                     "Object storage (80 TB-month): $1,680.00",
                     "Total due: $24,505.00"]),
    ))
    docs.append(SeedDoc(
        file="2026-10_nimbus_cloud_NC-2610.pdf", folder="docs", kind="cloud_invoice",
        site="nimbus-cloud", period="2026-10", received_from="dev", room="cr-cloud",
        traps=["data_centre_line (IT kWh, PUE, WUE on page 2; Scope 3 Cat 1)"],
        description="Nimbus Cloud, October 2026: IT energy 38,200 kWh, PUE 1.35, WUE 0.42 L/kWh (page 2).",
        pages=cloud("NC-2610", "October 2026", "November 2, 2026", "38,200", "1.35", "0.42",
                    ["Compute instances (reserved, 64 vCPU x 12): $18,240.00",
                     "GPU inference hours (1,450 h): $5,075.00",
                     "Object storage (82 TB-month): $1,722.00",
                     "Total due: $25,037.00"]),
    ))

    # --- REC certificate: wrong region AND old vintage --------------------------------
    docs.append(SeedDoc(
        file="2026-10_rec_REC-WECC-2023-55120.pdf", folder="docs", kind="rec_certificate",
        site="nimbus-cloud", period="2026-10", received_from="dev", room="cr-cloud",
        traps=["rec_quality (WECC Northwest generation vs a Virginia load; 2023 vintage for 2026 use)"],
        description="REC retirement: 120 MWh, WECC Northwest (Oregon), vintage 2023, claimed against Nimbus "
                    "Cloud us-east-va for October 2026. Low quality: wrong region and stale vintage.",
        pages=[[
            ("issuer", "Cascadia Renewable Certificate Registry"),
            ("small", "12 Turbine Way, Ridgeline, OR (fictional registry)"),
            ("title", "RENEWABLE ENERGY CERTIFICATE - RETIREMENT STATEMENT"),
            ("kv", "Certificate ID: REC-WECC-2023-55120"),
            ("kv", "Quantity retired: 120 MWh"),
            ("kv", "Generation region: WECC Northwest (Oregon)"),
            ("kv", "Generation facility: Ridgeline Wind 3 (fictional)"),
            ("kv", "Vintage (generation year): 2023"),
            ("rule", ""),
            ("kv", f"Retired on behalf of: {CUSTOMER}"),
            ("kv", "Claimed against: Nimbus Cloud (us-east-va) consumption"),
            ("kv", "Consumption period claimed: October 2026"),
            ("kv", "Retirement date: October 28, 2026"),
        ]],
    ))
    return docs


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render(doc: SeedDoc, out_path: Path) -> None:
    from reportlab import rl_config
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    rl_config.invariant = 1  # fixed creation date + document id -> byte-identical output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = letter
    c = canvas.Canvas(str(out_path), pagesize=letter, pageCompression=0)
    c.setTitle(out_path.stem)
    c.setAuthor("Carbon Room seed generator (fictional)")
    c.setSubject("FICTIONAL DOCUMENT")
    accent = HexColor("#1F5C4A")
    n_pages = len(doc.pages)
    for page_no, lines in enumerate(doc.pages, start=1):
        c.setFillColor(accent)
        c.rect(0, height - 18, width, 18, stroke=0, fill=1)
        y = height - 64
        for style, text in lines:
            if style == "issuer":
                c.setFillColor(accent)
                c.setFont("Helvetica-Bold", 17)
                c.drawString(54, y, text)
                y -= 18
            elif style == "small":
                c.setFillColor(HexColor("#555555"))
                c.setFont("Helvetica", 9)
                c.drawString(54, y, text)
                y -= 26
            elif style == "title":
                c.setFillColor(HexColor("#111111"))
                c.setFont("Helvetica-Bold", 13)
                c.drawString(54, y, text)
                y -= 24
            elif style == "h2":
                c.setFillColor(accent)
                c.setFont("Helvetica-Bold", 11)
                c.drawString(54, y, text)
                y -= 18
            elif style == "rule":
                c.setStrokeColor(HexColor("#BBBBBB"))
                c.setLineWidth(0.6)
                c.line(54, y + 6, width - 54, y + 6)
                y -= 12
            else:  # kv / p
                c.setFillColor(HexColor("#111111"))
                c.setFont("Helvetica", 10.5)
                c.drawString(54, y, text)
                y -= 16
        c.setFillColor(HexColor("#9A3412"))
        c.setFont("Helvetica-Oblique", 7.5)
        for i, footer_line in enumerate(textwrap.wrap(FOOTER, 115)):
            c.drawString(54, 46 - 10 * i, footer_line)
        c.setFillColor(HexColor("#555555"))
        c.setFont("Helvetica", 8)
        c.drawRightString(width - 54, 24, f"Page {page_no} of {n_pages}")
        c.showPage()
    c.save()


def generate(seed_dir: Path) -> list[Path]:
    """Write every seed PDF plus manifest.json. Returns the written paths."""
    written = []
    manifest = []
    for doc in seed_documents():
        path = seed_dir / doc.folder / doc.file
        _render(doc, path)
        written.append(path)
        entry = asdict(doc)
        entry.pop("pages")
        entry["path"] = f"{doc.folder}/{doc.file}"
        manifest.append(entry)
    (seed_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return written


def main() -> None:  # pragma: no cover - thin wrapper
    from carbonroom import config

    for path in generate(config.seed_dir()):
        print(path)


if __name__ == "__main__":  # pragma: no cover
    main()
