import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

def create_deck():
    prs = Presentation()
    # 16:9 widescreen
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    # Color Palette
    BG_DARK = RGBColor(13, 21, 39)       # #0d1527
    CARD_BG = RGBColor(20, 32, 58)       # #14203a
    CYAN = RGBColor(6, 182, 212)         # #06b6d4
    EMERALD = RGBColor(16, 185, 129)     # #10b981
    AMBER = RGBColor(245, 158, 11)       # #f59e0b
    PURPLE = RGBColor(168, 85, 247)      # #a855f7
    WHITE = RGBColor(255, 255, 255)
    TEXT_MUTED = RGBColor(148, 163, 184) # #94a3b8
    BORDER_COLOR = RGBColor(40, 56, 88)

    blank_layout = prs.slide_layouts[6]

    def set_slide_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_DARK
        bg.line.fill.background() # no line

    def add_header(slide, tag_text, title_text, subtitle_text):
        # Tag
        tag_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.35))
        tf = tag_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = tag_text.upper()
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = CYAN

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.85), Inches(11.7), Inches(0.7))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = WHITE

        # Subtitle
        if subtitle_text:
            sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(0.4))
            tf = sub_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = subtitle_text
            p.font.size = Pt(13)
            p.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1)

    # Glowing box background for logo
    logo_bg = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.4), Inches(1.2), Inches(1.2))
    logo_bg.fill.solid()
    logo_bg.fill.fore_color.rgb = CYAN
    logo_bg.line.fill.background()
    p = logo_bg.text_frame.paragraphs[0]
    p.text = "CO₂"
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = BG_DARK

    tbox = s1.shapes.add_textbox(Inches(2.3), Inches(1.3), Inches(10), Inches(2.5))
    tf = tbox.text_frame
    tf.word_wrap = True
    p0 = tf.paragraphs[0]
    p0.text = "Audit.CO2"
    p0.font.size = Pt(48)
    p0.font.bold = True
    p0.font.color.rgb = WHITE

    p1 = tf.add_paragraph()
    p1.text = "Autonomous Multi-Agent Enterprise Carbon Accounting with Cryptographic Proof Boundary"
    p1.font.size = Pt(18)
    p1.font.color.rgb = CYAN
    p1.space_before = Pt(8)

    p2 = tf.add_paragraph()
    p2.text = "Powered by Switch AI  ·  Track 01: Best Business Workflow  ·  WeMakeDevs Hackathon"
    p2.font.size = Pt(13)
    p2.font.color.rgb = TEXT_MUTED
    p2.space_before = Pt(12)

    # 3 Stat Cards on Title Slide
    stats = [
        ("4 Specialized Agents", "Orchestrator, Collector, Watchdog, Reporter", CYAN),
        ("Zero Hallucinations", "Verbatim raw-document proof boundary & Decimal math", EMERALD),
        ("91-Event Audit Chain", "Tamper-evident SHA-256 cryptographic SQLite ledger", PURPLE),
    ]
    for i, (headline, desc, col) in enumerate(stats):
        card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 3.9), Inches(4.5), Inches(3.7), Inches(2.2))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.3)
        tf.margin_left = Inches(0.3)
        p = tf.paragraphs[0]
        p.text = headline
        p.font.size = Pt(18)
        p.font.bold = True
        p.font.color.rgb = col
        p_desc = tf.add_paragraph()
        p_desc.text = desc
        p_desc.font.size = Pt(12)
        p_desc.font.color.rgb = TEXT_MUTED
        p_desc.space_before = Pt(10)

    # ==========================================
    # SLIDE 2: ACT I — The Real Problem
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "Act I: Problem & Motivation", "Enterprise Carbon Accounting Is Broken", 
               "CSRD, SEC, and GHG Protocol mandates require audit-ready disclosures, but current workflows fail.")

    # Two Comparative Panels
    # Left: Status Quo
    sq = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.1), Inches(5.6), Inches(4.7))
    sq.fill.solid()
    sq.fill.fore_color.rgb = CARD_BG
    sq.line.color.rgb = RGBColor(239, 68, 68) # red
    sq.line.width = Pt(1.5)
    tf = sq.text_frame
    tf.word_wrap = True
    tf.margin_top = Inches(0.3)
    tf.margin_left = Inches(0.4)
    p = tf.paragraphs[0]
    p.text = "⚠️ The Status Quo: Spreadsheet Chaos"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = RGBColor(239, 68, 68)
    
    bullets_sq = [
        ("3+ Weeks per Close", "Sustainability teams manually chase emails, PDFs, utility bills, and cloud logs."),
        ("Spreadsheet Fragility", "Broken formulas, missing factor version tracking, and unit conversion mistakes."),
        ("No Chain of Custody", "Auditors cannot verify who approved an estimate, when, or against what source."),
        ("Massive Compliance Risk", "CSRD and SEC fines for inaccurate reports reach up to millions of dollars.")
    ]
    for b_title, b_desc in bullets_sq:
        p_t = tf.add_paragraph()
        p_t.text = f"• {b_title}: "
        p_t.font.size = Pt(13)
        p_t.font.bold = True
        p_t.font.color.rgb = WHITE
        p_t.space_before = Pt(12)
        p_d = tf.add_paragraph()
        p_d.text = f"  {b_desc}"
        p_d.font.size = Pt(11)
        p_d.font.color.rgb = TEXT_MUTED

    # Right: Why Solo AI Chatbots Fail
    ai = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.9), Inches(2.1), Inches(5.6), Inches(4.7))
    ai.fill.solid()
    ai.fill.fore_color.rgb = CARD_BG
    ai.line.color.rgb = AMBER
    ai.line.width = Pt(1.5)
    tf = ai.text_frame
    tf.word_wrap = True
    tf.margin_top = Inches(0.3)
    tf.margin_left = Inches(0.4)
    p = tf.paragraphs[0]
    p.text = "❌ Why Solo AI Chatbots Fail"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = AMBER
    
    bullets_ai = [
        ("LLM Number Hallucinations", "Generative models invent numbers when reading unparsed PDF invoices."),
        ("Floating Point Drift", "LLMs cannot perform strict 10-decimal GHG Protocol factor multiplication."),
        ("Solo Chatbot Isolation", "A bot in a silo cannot coordinate facility managers, accountants, and auditors."),
        ("Black-Box Liability", "External assurance partners immediately reject 'ChatGPT said so' as proof.")
    ]
    for b_title, b_desc in bullets_ai:
        p_t = tf.add_paragraph()
        p_t.text = f"• {b_title}: "
        p_t.font.size = Pt(13)
        p_t.font.bold = True
        p_t.font.color.rgb = WHITE
        p_t.space_before = Pt(12)
        p_d = tf.add_paragraph()
        p_d.text = f"  {b_desc}"
        p_d.font.size = Pt(11)
        p_d.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 3: ACT II — The Solution & Multi-Agent Architecture
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3)
    add_header(s3, "Act II: The Solution & Why Switch", "Audit.CO2: Collaborative Multi-Agent Enterprise Room",
               "Instead of a solo chatbot, 4 specialized agents collaborate with human stakeholders in Switch.")

    agents_data = [
        ("⚡ @carbon-room", "Orchestrator", CYAN, 
         "• State Machine: COLLECTING → CHECKING → PUBLISHED\n• Generates close plan & factor lock\n• Live Close Board document maintainer\n• Manages noise ceiling (max 12 posts)"),
        ("📥 @collector", "Ingestion Engine", RGBColor(59, 130, 246),
         "• Zero-Hallucination Proof Boundary\n• SHA-256 Content-addressable storage\n• Enforces exact verbatim text match\n• Handles utility PDFs, EMLs, CSVs, cloud JSON"),
        ("🛡️ @watchdog", "Audit & Rules", AMBER,
         "• 7 Deterministic GHG Compliance Rules\n• Identifies period mismatches & variances\n• Opens targeted gap threads to owners\n• Verifies HITL resolutions & recalculates live"),
        ("📊 @reporter", "Disclosure & Trace", EMBER if 'EMBER' in locals() else EMERALD,
         "• Mandatory regulatory disclosure compiler\n• Unverified AI datacenter line warnings\n• Cryptographic 91-event audit chain check\n• Publishes PDF, JSON, HTML, and Markdown")
    ]
    for i, (name, role, col, bullets) in enumerate(agents_data):
        card = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 2.95), Inches(2.1), Inches(2.8), Inches(4.7))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.25)
        tf.margin_left = Inches(0.25)
        p = tf.paragraphs[0]
        p.text = name
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p_role = tf.add_paragraph()
        p_role.text = role.upper()
        p_role.font.size = Pt(11)
        p_role.font.bold = True
        p_role.font.color.rgb = col
        p_role.space_before = Pt(4)
        
        for line in bullets.split("\n"):
            p_b = tf.add_paragraph()
            p_b.text = line
            p_b.font.size = Pt(10)
            p_b.font.color.rgb = TEXT_MUTED
            p_b.space_before = Pt(8)

    # ==========================================
    # SLIDE 4: ACT III — The Live E2E Workflow & HITL
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "Act III: Live Demo & HITL Magic", "The October 2026 Close: Human-in-the-Loop Collaboration",
               "How agents and humans resolve compliance gaps live in Mattermost / Switch.")

    workflow_steps = [
        ("Step 1: Start Close", "@carbon-room close October", "Orchestrator generates close plan, locks factor set (FS-2026-10), triggers Collector.", CYAN),
        ("Step 2: 4 Gaps Flagged", "@watchdog opens threads", "Collector gathers bills. Watchdog catches 4 traps (G-1..G-4) and refuses clean total.", AMBER),
        ("Step 3: Human Resolutions", "upload & pick & approve", "Priya uploads real bill; Lead picks Rev A, approves factor & variance. Total moves to 21.9 tCO2e.", PURPLE),
        ("Step 4: Draft & Publish", "@reporter draft → publish", "Mandatory compliance disclosures drafted; Lead publishes immutable audit suite.", EMERALD)
    ]
    for i, (title, action, details, col) in enumerate(workflow_steps):
        card = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 2.95), Inches(2.1), Inches(2.8), Inches(4.7))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.25)
        tf.margin_left = Inches(0.25)
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(15)
        p.font.bold = True
        p.font.color.rgb = col
        
        p_act = tf.add_paragraph()
        p_act.text = action
        p_act.font.size = Pt(11)
        p_act.font.bold = True
        p_act.font.color.rgb = WHITE
        p_act.space_before = Pt(6)
        
        p_det = tf.add_paragraph()
        p_det.text = details
        p_det.font.size = Pt(11)
        p_det.font.color.rgb = TEXT_MUTED
        p_det.space_before = Pt(12)

    # ==========================================
    # SLIDE 5: ACT IV — Deep Engineering Architecture
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "Act IV: Deep Technical Architecture", "Zero-Hallucination Proof Boundary & Deterministic Core",
               "Why Audit.CO2 is production-grade and legally verifiable.")

    tech_pillars = [
        ("Proof Boundary", "No Model Inventions", CYAN, 
         "AI models are strictly quarantined to extraction.\nA deterministic validator checks that every number matches verbatim in the source file bytes:\nexcerpt in normalized(page)\nIf a model hallucinates, validate() rejects it."),
        ("Deterministic Arithmetic", "Decimal High-Precision", EMERALD,
         "Zero floating point rounding drift.\nAll multiplication executed using Python Decimal:\nActivity × PUE × Emission Factor\nVerified down to 10 decimal places (e.g. 21.9418970878 tCO2e)."),
        ("Cryptographic Ledger", "91-Event SHA-256 Chain", PURPLE,
         "Every human resolution, upload, and agent event is chained:\nH_n = SHA256(H_n-1 || event)\nAny manual modification to the SQLite database breaks the cryptographic hash chain."),
        ("Enterprise Switch Bus", "4 Duplex WebSockets", AMBER,
         "One runtime maintaining 4 concurrent duplex Switch sockets.\nImplements SPEC-09B cross-agent delegation.\nPure intent grammar parser.\nFull suite of 642 passing tests.")
    ]
    for i, (title, sub, col, body) in enumerate(tech_pillars):
        card = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 2.95), Inches(2.1), Inches(2.8), Inches(4.7))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.25)
        tf.margin_left = Inches(0.25)
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = col
        
        p_s = tf.add_paragraph()
        p_s.text = sub.upper()
        p_s.font.size = Pt(10)
        p_s.font.bold = True
        p_s.font.color.rgb = WHITE
        p_s.space_before = Pt(4)

        for line in body.split("\n"):
            p_b = tf.add_paragraph()
            p_b.text = line
            p_b.font.size = Pt(10)
            p_b.font.color.rgb = TEXT_MUTED
            p_b.space_before = Pt(6)

    # ==========================================
    # SLIDE 6: ACT V — Business Impact & Conclusion
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "Act V: Impact & Conclusion", "Turning 3 Weeks of Spreadsheet Chaos into 3 Minutes",
               "The future of enterprise sustainability reporting powered by Switch.")

    impact_cards = [
        ("95% Time Reduction", "From 3 Weeks → 3 Minutes", CYAN,
         "Automates data ingestion, rule checking, and variance analysis while keeping humans in the loop for critical sign-offs."),
        ("100% Audit Verifiable", "Mathematically Reproducible", EMERALD,
         "Every published number can be traced back to raw source bytes via @reporter trace S-001. No black-box approximations."),
        ("Complete Regulatory Suite", "4 Formats Generated", PURPLE,
         "Outputs out/2026-10/v1/ with report.pdf, report.json, report.md, and interactive coverage.html with compliance flags."),
        ("Built on Switch", "True Human-Agent Synergy", AMBER,
         "Proves that autonomous agents and human experts can collaborate inside modern enterprise chat platforms safely.")
    ]
    for i, (metric, sub, col, desc) in enumerate(impact_cards):
        card = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 2.95), Inches(2.1), Inches(2.8), Inches(4.7))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.25)
        tf.margin_left = Inches(0.25)
        p = tf.paragraphs[0]
        p.text = metric
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = col
        
        p_s = tf.add_paragraph()
        p_s.text = sub
        p_s.font.size = Pt(11)
        p_s.font.bold = True
        p_s.font.color.rgb = WHITE
        p_s.space_before = Pt(6)
        
        p_d = tf.add_paragraph()
        p_d.text = desc
        p_d.font.size = Pt(11)
        p_d.font.color.rgb = TEXT_MUTED
        p_d.space_before = Pt(12)

    prs.save("Audit_CO2_Presentation.pptx")
    print("Saved Audit_CO2_Presentation.pptx successfully!")

if __name__ == "__main__":
    create_deck()
