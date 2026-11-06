"""Build the deterministic synthetic contract seed data; no real customer data is used."""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "SAMPLE — synthetic demo data — FICTIONAL DOCUMENT"


def pdf(path: Path, site: str, period: str, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=letter, invariant=1)
    canvas.setTitle("Carbon Room synthetic bill")
    for y, text in enumerate((SAMPLE, f"Site: {site}", f"Billing period: {period}", line), start=1):
        canvas.drawString(72, 750 - y * 36, text)
    canvas.save()


def email_invoice(path: Path, site: str, period: str, litres: str, invoice: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    message = EmailMessage()
    message["Subject"] = f"Diesel invoice {invoice}"
    message["From"] = "synthetic@example.test"
    message["Date"] = "Wed, 04 Nov 2026 10:00:00 +0000"
    message.set_content(f"{SAMPLE}\nSite: {site}\nPeriod: {period}\nInvoice: {invoice}\nDiesel delivered: {litres} L")
    path.write_bytes(bytes(message))


def cloud(path: Path, period_start: str, period_end: str, factor: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sample": SAMPLE, "period_start": period_start, "period_end": period_end,
                                "it_energy_kwh": "12000", "pue": "1.2", "region": "eu-west-1",
                                "market_based_kgco2e": "0", "vendor_factor_ref": factor}, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def main() -> None:
    seed = ROOT / "data/seed"
    pdf(seed / "2026-09/hq_electricity_2026-09.pdf", "hq", "1 Sep 2026 – 30 Sep 2026", "Usage: 35,000 kWh")
    email_invoice(seed / "2026-09/hq_diesel_2026-09_inv-4402.eml", "hq", "2026-09-01 to 2026-09-30", "2,200", "4402")
    pdf(seed / "2026-09/warehouse2_electricity_2026-09.pdf", "warehouse-2", "1 Sep 2026 – 30 Sep 2026", "Usage: 18,000 kWh")
    cloud(seed / "2026-09/dc_euwest_cloud_2026-09.json", "2026-09-01", "2026-09-30", "Ember 2025 IE")
    pdf(seed / "2026-10/hq_electricity_2026-10.pdf", "hq", "1 Oct 2026 – 31 Oct 2026", "Usage: 48,300 kWh")
    email_invoice(seed / "2026-10/hq_diesel_2026-10_inv-4471.eml", "hq", "2026-10-01 to 2026-10-31", "2,000", "4471")
    email_invoice(seed / "2026-10/hq_diesel_2026-10_inv-4471-rev.eml", "hq", "2026-10-01 to 2026-10-31", "2,400", "4471-R")
    pdf(seed / "2026-10/warehouse2_electricity_2026-10.pdf", "warehouse-2", "1 Sep 2026 – 30 Sep 2026", "Usage: 17,500 kWh")
    cloud(seed / "2026-10/dc_euwest_cloud_2026-10.json", "2026-10-01", "2026-10-31", "Ember 2024 IE")
    pdf(ROOT / "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf", "warehouse-2", "1 Oct 2026 – 31 Oct 2026", "Usage: 18,500 kWh")


if __name__ == "__main__":
    main()
