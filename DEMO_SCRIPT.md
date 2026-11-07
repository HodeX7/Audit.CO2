# Audit.CO2 — Hackathon Video Script & Submission Guide
**Event:** WeMakeDevs "Flip the Switch" Hackathon (Powered by Switch AI)  
**Track:** Best Business Workflow / Human-Agent Collaboration  
**Target Video Duration:** 2:15 – 2:45 (Strictly under 3 minutes)  
**Format:** YouTube (Unlisted or Public), 1080p / 60fps  

---

## 📋 Hackathon Submission Requirements Checklist

Before submitting on the portal, verify every item below:
- [x] **Public GitHub Repository:** Repository is public with full commit history (`HodeX7/Audit.CO2`).
- [x] **Comprehensive README:** Problem statement, architecture, Switch integration guide, setup instructions, and reproduction steps.
- [x] **Switch Deep Integration:** 4 specialized agents connected via Switch WebSockets, using Switch ops, threads, room documents, and cross-agent delegation (SPEC-09B).
- [x] **Working Demo Video (≤ 3 minutes):** Hosted on YouTube (Unlisted or Public) with audio narration and clear screen recording.
- [x] **Zero Hallucination & Verifiability:** Tested with 642 unit/integration tests (`make test`), proof boundary, and 91-event cryptographic SHA-256 audit chain.

---

## 🏆 The Hackathon Winning Strategy Breakdown

Judges review dozens of projects in under an hour. To win, the presentation follows the proven 5-stage formula:

| Time | Stage | Core Message to Judges | Evaluation Rubric Hit |
|---|---|---|---|
| **0:00 – 0:25** | **The Real Problem** | Enterprise carbon accounting is manual, spreadsheet-heavy, and broken. Generic LLMs hallucinate numbers, causing audit fraud and greenwashing penalties. | *Real-World Impact & Novelty* |
| **0:25 – 0:50** | **The Solution & Why Switch** | Introducing Audit.CO2: an autonomous multi-agent accounting room powered by Switch, pairing 4 specialized agents with human stakeholders. | *Effective Use of Switch* |
| **0:50 – 1:45** | **The Live Demo (HITL Magic)** | Close initiation $\to$ 4 gaps detected $\to$ Human-in-the-loop thread resolution $\to$ Live recalculation to 21.9 tCO2e $\to$ One-click immutable publication. | *Technical Execution & UX* |
| **1:45 – 2:15** | **Deep Backend Architecture** | Show `docs/architecture-demo.html`: zero-hallucination proof boundary, deterministic decimal math, factor sets, and 91-event cryptographic SHA-256 chain. | *Engineering Depth & Rigor* |
| **2:15 – 2:35** | **Impact & Conclusion** | Turns 3 weeks of spreadsheet chaos into 3 minutes of verifiable, audit-proof reporting. | *Business Value & Scalability* |

---

## 🎙️ Word-for-Word Video Script & On-Screen Choreography

### [0:00 – 0:25] ACT I: The Real Problem
**On Screen:** Show a chaotic corporate emissions spreadsheet or PDF invoice pile, then transition to the title slide: **Audit.CO2 — Verifiable Enterprise Carbon Accounting on Switch**.

> **Voiceover:**  
> *"Every enterprise today faces stringent CSRD and SEC emissions reporting mandates. Yet, corporate carbon accounting is trapped in weeks of spreadsheet chaos and fragmented email chains.*  
>  
> *When companies try throwing solo AI chatbots at this problem, disaster strikes: black-box LLMs hallucinate emissions numbers, perform incorrect unit conversions, and leave no legal audit trail—exposing companies to millions in greenwashing fines.*  
>  
> *Verifiable carbon accounting cannot be solved by a solo chatbot. It requires a coordinated team of specialized agents collaborating directly with human facility managers and auditors. That’s why we built **Audit.CO2**, powered by **Switch**."*

---

### [0:25 – 0:50] ACT II: The Solution & The Multi-Agent Room
**On Screen:** Open Switch / Mattermost `#emissions-reporting` channel (`http://127.0.0.1:51547/switch/channels/emissions-reporting`). Point out the channel members and 4 distinct specialized agents.

> **Voiceover:**  
> *"Audit.CO2 transforms emissions reporting into a shared, collaborative workspace where human decision-makers work alongside four specialized Switch agents:*  
>  
> *1. **`@carbon-room`** — The Orchestrator managing monthly close phases and the live close board.*  
> *2. **`@collector`** — The Ingestion Engine that extracts raw utility bills with a zero-hallucination proof boundary.*  
> *3. **`@watchdog`** — The Compliance Auditor checking every claim against 7 deterministic GHG rules and opening gap threads.*  
> *4. **`@reporter`** — The Disclosure Specialist that verifies cryptographic audit chains and publishes immutable reports.*  
>  
> *Let's watch them run the October 2026 month-end close live."*

---

### [0:50 – 1:45] ACT III: Live Working Demo (The HITL Magic)
**On Screen:** Switch to the live `#emissions-reporting` channel and demonstrate the workflow in real-time.

#### 1. Close Initiation
**Type in channel:**
```text
@carbon-room close October
```
> **Voiceover:**  
> *"The Sustainability Lead kicks off the close with `@carbon-room close October`. Instantly, the orchestrator locks our emissions factor set and tasks `@collector`.*  
>  
> *Notice what happens: Collector ingests all invoices, but Watchdog refuses to issue a clean total. It identifies 4 compliance gaps and opens dedicated threads assigned to specific team members."*

#### 2. Human-in-the-Loop Thread Resolutions
**On Screen:** Open the gap threads and resolve them one by one:

- **Warehouse-2 Gap Thread (G-3):**
  > **Voiceover:** *"Warehouse-2's bill had a period mismatch. Priya, our site manager, uploads the correct bill directly in the thread:"*  
  **Type in G-3 thread:** `upload warehouse2_electricity_2026-10_actual.pdf`  
  *(Watchdog replies: "Checking… Resolved. G-3 is closed.")*

- **Diesel Conflict Thread (G-1):**
  > **Voiceover:** *"For HQ diesel, two conflicting invoices were found. The Lead reviews the difference and selects Revision A:"*  
  **Type in G-1 thread:** `pick A`  
  *(Watchdog replies: "Resolved. G-1 is closed.")*

- **Stale Factor Thread (G-2):**
  > **Voiceover:** *"Data Centre EU-West was using a stale factor. The Lead approves the locked 2025 factor:"*  
  **Type in G-2 thread:** `approve`  

- **Variance Thread (G-4):**
  > **Voiceover:** *"HQ electricity surged by 38%, exceeding our 10% variance guardrail. The Lead investigates and approves the variance:"*  
  **Type in G-4 thread:** `approve`  

#### 3. Real-Time Recalculation & Publishing
**On Screen:** Return to the main channel.

> **Voiceover:**  
> *"Watchdog recalculates the ledger in real-time. Our verified total updates from 0 to 8.6, to 12.5, to exactly **21.9 tCO2e** with 100% coverage.*  
>  
> *With all gaps cleared, the Lead drafts and publishes:"*  
**Type in channel:**  
```text
@reporter draft
@carbon-room publish
```
*(Show the published confirmation with `report.pdf`, `report.json`, and `coverage.html`).*

#### 4. Specialized Agent Interaction & Audit Verification
**On Screen:** Show direct Q&A with the specialized agents:

**Type in channel:**
```text
@reporter trace S-001
@reporter verify audit
```
> **Voiceover:**  
> *"Anyone in the room can talk to specialized agents. We ask `@reporter trace S-001`—and it outputs the exact mathematical formula, raw document excerpt, and factor version.  
> We ask `@reporter verify audit`—and it cryptographically verifies all 91 ledger events in SQLite."*

---

### [1:45 – 2:15] ACT IV: Under the Hood Architecture
**On Screen:** Switch browser tabs to [`docs/architecture-demo.html`](file:///Users/aksharmehta/Projects/Audit.CO2/docs/architecture-demo.html). Click **Auto Tour** or click through the 3 layers.

> **Voiceover:**  
> *"Behind this chat interface lies an enterprise-grade engineering architecture:*  
>  
> *1. **The Switch Duplex Bus:** Four concurrent WebSocket sessions maintaining real-time event streaming and cross-agent delegation.*  
> *2. **The Zero-Hallucination Proof Boundary:** AI models are strictly quarantined to extraction. A deterministic validator verifies that every claimed number matches verbatim in the source file bytes.*  
> *3. **Cryptographic SHA-256 Event Chain:** Calculations are executed with high-precision Decimal arithmetic—no floating-point rounding errors. Every human approval and agent action is immutably hashed into an append-only SQLite ledger.*  
> *4. **Production Reliability:** Backed by 642 passing unit and integration tests."*

---

### [2:15 – 2:35] ACT V: Impact & Conclusion
**On Screen:** Show the generated `out/2026-10/v1/coverage.html` or final slide with GitHub repository link.

> **Voiceover:**  
> *"Audit.CO2 reduces corporate month-end carbon closes from 3 weeks of spreadsheet chaos to 3 minutes of transparent, verifiable collaboration.*  
>  
> *By combining Switch's multi-agent infrastructure with deterministic accounting and cryptographic proof boundaries, we've made enterprise emissions reporting fast, transparent, and completely audit-proof.*  
>  
> *Flip the Switch on carbon accounting. Thank you!"*

---

## 🛠️ Step-by-Step Live Rehearsal Guide (Pre-Recording Checklist)

Before hitting record on OBS / Loom:

1. **Verify Backend is Running:**
   ```bash
   make doctor
   ```
   *Ensure all 9 checks show green checkmarks.*

2. **Ensure Room Daemon is Running:**
   ```bash
   make run
   ```
   *(Keep it running in the background).*

3. **Reset Demo State for a Clean Recording:**
   ```bash
   make reset-demo
   ```
   *Type `reset` when prompted. Then copy the demo file into inbox:*
   ```bash
   cp data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf data/inbox/
   ```

4. **Have Browser Windows Ready:**
   - **Window 1:** Mattermost `#emissions-reporting` channel (`http://127.0.0.1:51547/switch/channels/emissions-reporting`). Log in as `akshar`.
   - **Window 2:** Architecture visualizer: `open docs/architecture-demo.html`.
   - **Window 3:** Published folder ready: `out/2026-10/v1/coverage.html`.

5. **Quick-Copy Cheat Sheet for Video Recording:**
   - Command 1: `@carbon-room close October`
   - Command 2 (Thread G-3): `upload warehouse2_electricity_2026-10_actual.pdf`
   - Command 3 (Thread G-1): `pick A`
   - Command 4 (Thread G-2): `approve`
   - Command 5 (Thread G-4): `approve`
   - Command 6: `@reporter draft`
   - Command 7: `@carbon-room publish`
   - Command 8: `@reporter trace S-001`
   - Command 9: `@reporter verify audit`
