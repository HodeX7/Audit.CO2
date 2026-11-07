import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        # Footer
        self.drawString(54, 30, "Audit.CO2 — WeMakeDevs 'Flip the Switch' Hackathon · Track 01: Best Business Workflow")
        page_str = f"Slide {self._pageNumber} of {page_count}"
        self.drawRightString(self._pagesize[0] - 54, 30, page_str)
        self.restoreState()

def create_pdf():
    pdf_path = "Audit_CO2_Presentation.pdf"
    # Landscape 16:9 ratio approximately or landscape letter (11 x 8.5 in)
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=landscape(letter),
        leftMargin=40,
        rightMargin=40,
        topMargin=35,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    C_BG = colors.HexColor("#0d1527")
    C_CARD = colors.HexColor("#14203a")
    C_CYAN = colors.HexColor("#06b6d4")
    C_EMERALD = colors.HexColor("#10b981")
    C_AMBER = colors.HexColor("#f59e0b")
    C_PURPLE = colors.HexColor("#a855f7")
    C_RED = colors.HexColor("#ef4444")
    C_WHITE = colors.HexColor("#ffffff")
    C_MUTED = colors.HexColor("#94a3b8")
    C_BORDER = colors.HexColor("#283858")

    # Typography Styles
    title_style = ParagraphStyle(
        "SlideTitle", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=C_WHITE
    )
    tag_style = ParagraphStyle(
        "SlideTag", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=C_CYAN
    )
    subtitle_style = ParagraphStyle(
        "SlideSubtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, leading=14, textColor=C_MUTED
    )
    card_title_style = ParagraphStyle(
        "CardTitle", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=C_WHITE
    )
    card_sub_style = ParagraphStyle(
        "CardSub", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=C_CYAN
    )
    body_style = ParagraphStyle(
        "CardBody", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=12, textColor=C_MUTED
    )

    story = []

    def add_slide_header(tag, title, subtitle):
        header_data = [
            [Paragraph(tag.upper(), tag_style)],
            [Paragraph(title, title_style)],
            [Paragraph(subtitle, subtitle_style)]
        ]
        t = Table(header_data, colWidths=[712])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.transparent),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(t)
        story.append(Spacer(1, 15))

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    s1_header = [
        [Paragraph("WE-MAKE-DEVS · 'FLIP THE SWITCH' HACKATHON · TRACK 01: BEST BUSINESS WORKFLOW", tag_style)],
        [Spacer(1, 5)],
        [Paragraph("Audit.CO2", ParagraphStyle("TitleMain", parent=title_style, fontSize=36, leading=40))],
        [Paragraph("Autonomous Multi-Agent Enterprise Carbon Accounting with Cryptographic Proof Boundary", ParagraphStyle("SubMain", parent=subtitle_style, fontSize=14, leading=18, textColor=C_CYAN))],
        [Spacer(1, 10)],
        [Paragraph("Powered by Switch AI  ·  4 Specialized Agents  ·  Human-in-the-Loop Collaboration", ParagraphStyle("AuthMain", parent=subtitle_style, fontSize=10, leading=14, textColor=C_MUTED))],
    ]
    t1 = Table(s1_header, colWidths=[712])
    t1.setStyle(TableStyle([('LEFTPADDING', (0,0), (-1,-1), 0)]))
    story.append(t1)
    story.append(Spacer(1, 40))

    # 3 Pillars on Title Slide
    cards_s1 = [
        [
            Paragraph("4 Specialized Agents", ParagraphStyle("P1", parent=card_title_style, textColor=C_CYAN)),
            Paragraph("Zero Hallucinations", ParagraphStyle("P2", parent=card_title_style, textColor=C_EMERALD)),
            Paragraph("91-Event Audit Chain", ParagraphStyle("P3", parent=card_title_style, textColor=C_PURPLE))
        ],
        [
            Paragraph("Orchestrator (@carbon-room), Collector, Watchdog, and Reporter running 4 concurrent duplex WebSockets inside a shared enterprise room.", body_style),
            Paragraph("Models are strictly quarantined to extraction; a deterministic proof validator guarantees verbatim raw source text matching and high-precision math.", body_style),
            Paragraph("Tamper-evident append-only SQLite ledger. Every human resolution, approval, and event is cryptographically hashed with SHA-256.", body_style)
        ]
    ]
    t1_cards = Table(cards_s1, colWidths=[230, 230, 230])
    t1_cards.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_CYAN),
        ('BOX', (1,0), (1,-1), 1, C_EMERALD),
        ('BOX', (2,0), (2,-1), 1, C_PURPLE),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
        ('LEFTPADDING', (0,0), (-1,-1), 14),
        ('RIGHTPADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t1_cards)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 2: Act I — The Problem
    # ==========================================
    add_slide_header("Act I: Problem & Motivation", "Enterprise Carbon Accounting Is Broken",
                     "CSRD, SEC, and GHG Protocol mandates require audit-ready disclosures, but current workflows fail.")

    sq_text = """
    <b>• 3+ Weeks per Monthly Close:</b> Sustainability teams manually chase utility bills, PDF receipts, and cloud invoices across disparate teams.<br/><br/>
    <b>• Spreadsheet Fragility:</b> Broken Excel formulas, manual copy-pasting, and missing emission factor version tracking.<br/><br/>
    <b>• Zero Chain of Custody:</b> Auditors cannot verify who approved an estimate, when, or against what source evidence.<br/><br/>
    <b>• Severe Regulatory Risk:</b> CSRD and SEC penalties for inaccurate ESG disclosures reach millions of dollars in fines.
    """
    ai_text = """
    <b>• LLM Number Hallucinations:</b> Generative AI invents numbers and dates when reading complex utility bills.<br/><br/>
    <b>• Floating Point Arithmetic Drift:</b> LLMs fail to perform exact 10-decimal GHG Protocol factor multiplications.<br/><br/>
    <b>• Solo Chatbot Isolation:</b> A solo bot in a web tab cannot coordinate facility managers, accountants, and auditors.<br/><br/>
    <b>• Black-Box Liability:</b> External assurance partners reject unverified AI answers as legal compliance evidence.
    """
    s2_data = [
        [Paragraph("⚠️ The Status Quo: Spreadsheet Chaos", ParagraphStyle("W1", parent=card_title_style, textColor=C_RED)),
         Paragraph("❌ Why Solo AI Chatbots Fail", ParagraphStyle("W2", parent=card_title_style, textColor=C_AMBER))],
        [Paragraph(sq_text, body_style),
         Paragraph(ai_text, body_style)]
    ]
    t2 = Table(s2_data, colWidths=[348, 348])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_RED),
        ('BOX', (1,0), (1,-1), 1, C_AMBER),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
        ('LEFTPADDING', (0,0), (-1,-1), 14),
        ('RIGHTPADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t2)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 3: Act II — The Solution & Multi-Agent Architecture
    # ==========================================
    add_slide_header("Act II: The Solution & Why Switch", "Audit.CO2: Collaborative Multi-Agent Enterprise Room",
                     "Instead of a solo chatbot, 4 specialized agents collaborate with human stakeholders in Switch.")

    s3_data = [
        [
            Paragraph("⚡ @carbon-room", ParagraphStyle("A1", parent=card_title_style, textColor=C_CYAN)),
            Paragraph("📥 @collector", ParagraphStyle("A2", parent=card_title_style, textColor=colors.HexColor("#3b82f6"))),
            Paragraph("🛡️ @watchdog", ParagraphStyle("A3", parent=card_title_style, textColor=C_AMBER)),
            Paragraph("📊 @reporter", ParagraphStyle("A4", parent=card_title_style, textColor=C_EMERALD))
        ],
        [
            Paragraph("ORCHESTRATOR", card_sub_style),
            Paragraph("INGESTION ENGINE", ParagraphStyle("S2", parent=card_sub_style, textColor=colors.HexColor("#3b82f6"))),
            Paragraph("AUDIT & RULES", ParagraphStyle("S3", parent=card_sub_style, textColor=C_AMBER)),
            Paragraph("DISCLOSURE & TRACE", ParagraphStyle("S4", parent=card_sub_style, textColor=C_EMERALD))
        ],
        [
            Paragraph("• Manages close phases (COLLECTING → PUBLISHED)<br/>• Locks factor set editions<br/>• Live Close Board maintainer<br/>• Enforces 12-post noise limit", body_style),
            Paragraph("• Proof Boundary verification<br/>• SHA-256 content deduplication<br/>• Enforces verbatim raw text match<br/>• Parses PDFs, EMLs, CSVs, cloud JSON", body_style),
            Paragraph("• 7 Deterministic GHG rules<br/>• Flags period mismatches & variances<br/>• Opens targeted gap threads<br/>• Recalculates ledger in real time", body_style),
            Paragraph("• Mandatory compliance disclosures<br/>• Unverified AI datacenter flags<br/>• Cryptographic 91-event audit check<br/>• Publishes PDF, JSON, HTML, Markdown", body_style)
        ]
    ]
    t3 = Table(s3_data, colWidths=[172, 172, 172, 172])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_CYAN),
        ('BOX', (1,0), (1,-1), 1, colors.HexColor("#3b82f6")),
        ('BOX', (2,0), (2,-1), 1, C_AMBER),
        ('BOX', (3,0), (3,-1), 1, C_EMERALD),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t3)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 4: Act III — The Live Workflow & HITL
    # ==========================================
    add_slide_header("Act III: Live Demo & HITL Magic", "The October 2026 Close: Human-in-the-Loop Collaboration",
                     "How agents and humans resolve compliance gaps live in Mattermost / Switch.")

    s4_data = [
        [
            Paragraph("Step 1: Start Close", ParagraphStyle("F1", parent=card_title_style, textColor=C_CYAN)),
            Paragraph("Step 2: 4 Gaps Flagged", ParagraphStyle("F2", parent=card_title_style, textColor=C_AMBER)),
            Paragraph("Step 3: Human Resolutions", ParagraphStyle("F3", parent=card_title_style, textColor=C_PURPLE)),
            Paragraph("Step 4: Draft & Publish", ParagraphStyle("F4", parent=card_title_style, textColor=C_EMERALD))
        ],
        [
            Paragraph("@carbon-room close October", card_sub_style),
            Paragraph("@watchdog opens threads", ParagraphStyle("FS2", parent=card_sub_style, textColor=C_AMBER)),
            Paragraph("upload & pick & approve", ParagraphStyle("FS3", parent=card_sub_style, textColor=C_PURPLE)),
            Paragraph("@reporter draft → publish", ParagraphStyle("FS4", parent=card_sub_style, textColor=C_EMERALD))
        ],
        [
            Paragraph("Orchestrator locks factor set (FS-2026-10), transitions state to COLLECTING, and signals Collector.", body_style),
            Paragraph("Collector harvests invoices. Watchdog catches 4 traps (G-1..G-4) and refuses clean total: 0.0 tCO2e verified.", body_style),
            Paragraph("Priya uploads real bill; Lead picks Rev A, approves factor & variance. Total moves live to 21.9 tCO2e (100% Coverage).", body_style),
            Paragraph("Mandatory regulatory disclosures attached. Lead publishes immutable reports (PDF, JSON, HTML, MD).", body_style)
        ]
    ]
    t4 = Table(s4_data, colWidths=[172, 172, 172, 172])
    t4.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_CYAN),
        ('BOX', (1,0), (1,-1), 1, C_AMBER),
        ('BOX', (2,0), (2,-1), 1, C_PURPLE),
        ('BOX', (3,0), (3,-1), 1, C_EMERALD),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t4)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 5: Act IV — Deep Engineering Architecture
    # ==========================================
    add_slide_header("Act IV: Deep Technical Architecture", "Zero-Hallucination Proof Boundary & Deterministic Core",
                     "Why Audit.CO2 is production-grade and legally verifiable.")

    s5_data = [
        [
            Paragraph("Proof Boundary", ParagraphStyle("T1", parent=card_title_style, textColor=C_CYAN)),
            Paragraph("Deterministic Math", ParagraphStyle("T2", parent=card_title_style, textColor=C_EMERALD)),
            Paragraph("Cryptographic Ledger", ParagraphStyle("T3", parent=card_title_style, textColor=C_PURPLE)),
            Paragraph("Switch Bus Engine", ParagraphStyle("T4", parent=card_title_style, textColor=C_AMBER))
        ],
        [
            Paragraph("ZERO HALLUCINATIONS", card_sub_style),
            Paragraph("DECIMAL PRECISION", ParagraphStyle("TS2", parent=card_sub_style, textColor=C_EMERALD)),
            Paragraph("SHA-256 EVENT CHAIN", ParagraphStyle("TS3", parent=card_sub_style, textColor=C_PURPLE)),
            Paragraph("4 DUPLEX WEBSOCKETS", ParagraphStyle("TS4", parent=card_sub_style, textColor=C_AMBER))
        ],
        [
            Paragraph("AI models strictly extract candidates. A deterministic validator checks that every number matches verbatim in raw file bytes:<br/><br/><code>excerpt in norm(page)</code><br/><br/>If model hallucinates, validate() rejects.", body_style),
            Paragraph("Zero floating-point rounding drift.<br/><br/>All multiplications executed using Python Decimal:<br/><code>Activity × PUE × Factor</code><br/><br/>Verified down to 10 decimal places (21.9418970878 tCO2e).", body_style),
            Paragraph("Every human resolution, upload, and approval is chained in SQLite:<br/><br/><code>H_n = SHA256(H_n-1 || ev)</code><br/><br/>Any manual DB tampering breaks the cryptographic chain (91 events verified).", body_style),
            Paragraph("Maintains 4 concurrent duplex Switch sockets.<br/><br/>Implements SPEC-09B cross-agent addressing delegation.<br/><br/>Pure intent grammar parser backed by 642 passing unit & integration tests.", body_style)
        ]
    ]
    t5 = Table(s5_data, colWidths=[172, 172, 172, 172])
    t5.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_CYAN),
        ('BOX', (1,0), (1,-1), 1, C_EMERALD),
        ('BOX', (2,0), (2,-1), 1, C_PURPLE),
        ('BOX', (3,0), (3,-1), 1, C_AMBER),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t5)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 6: Act V — Impact & Conclusion
    # ==========================================
    add_slide_header("Act V: Impact & Conclusion", "Turning 3 Weeks of Spreadsheet Chaos into 3 Minutes",
                     "The future of enterprise sustainability reporting powered by Switch.")

    s6_data = [
        [
            Paragraph("95% Time Reduction", ParagraphStyle("I1", parent=card_title_style, textColor=C_CYAN)),
            Paragraph("100% Audit Verifiable", ParagraphStyle("I2", parent=card_title_style, textColor=C_EMERALD)),
            Paragraph("Complete Output Suite", ParagraphStyle("I3", parent=card_title_style, textColor=C_PURPLE)),
            Paragraph("Built on Switch", ParagraphStyle("I4", parent=card_title_style, textColor=C_AMBER))
        ],
        [
            Paragraph("3 WEEKS → 3 MINUTES", card_sub_style),
            Paragraph("MATHEMATICALLY REPRODUCIBLE", ParagraphStyle("IS2", parent=card_sub_style, textColor=C_EMERALD)),
            Paragraph("4 REGULATORY FORMATS", ParagraphStyle("IS3", parent=card_sub_style, textColor=C_PURPLE)),
            Paragraph("HUMAN-AGENT SYNERGY", ParagraphStyle("IS4", parent=card_sub_style, textColor=C_AMBER))
        ],
        [
            Paragraph("Automates ingestion, rule checking, and variance analysis while keeping humans in the loop for binding sign-offs and legal authority.", body_style),
            Paragraph("Every published gram of CO2 can be traced back to raw source bytes via @reporter trace S-001. No black-box estimations.", body_style),
            Paragraph("Outputs out/2026-10/v1/ with report.pdf, report.json, report.md, and interactive coverage.html with compliance disclosures.", body_style),
            Paragraph("Proves how autonomous agents and human experts can collaborate inside enterprise chat platforms safely and effectively.", body_style)
        ]
    ]
    t6 = Table(s6_data, colWidths=[172, 172, 172, 172])
    t6.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CARD),
        ('BOX', (0,0), (0,-1), 1, C_CYAN),
        ('BOX', (1,0), (1,-1), 1, C_EMERALD),
        ('BOX', (2,0), (2,-1), 1, C_PURPLE),
        ('BOX', (3,0), (3,-1), 1, C_AMBER),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t6)

    def draw_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_bg, onLaterPages=draw_bg, canvasmaker=NumberedCanvas)
    print("Saved Audit_CO2_Presentation.pdf successfully!")

if __name__ == "__main__":
    create_pdf()
