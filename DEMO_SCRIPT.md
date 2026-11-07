# Audit.CO2 — Hackathon Video Script & Presentation Guide
**Event:** WeMakeDevs "Flip the Switch" Hackathon  
**Track:** Best Business Workflow / Human-Agent Collaboration  
**Presentation Strategy:** Interactive HTML Architecture Walkthrough (Steps 1–6) + Existing Mattermost Message Tour  
**Target Video Duration:** 2:30 – 2:45 (Strictly under 3:00 hard limit)  
**Deliverables:** Hosted on YouTube (Unlisted or Public) at 1080p / 60fps  

---

## 🏆 Key Winning Points for Judges (Evaluation Checklist)

| Winning Point | Hackathon Criterion | Where It Appears in Script |
|---|---|---|
| **Why Switch is Central & Indispensable** | Effective Use of Switch | **Intro (0:15) & Step 4/6**: Switch is NOT a passive chat UI; it is the **authoritative cryptographic and operational boundary**. The CLI intentionally has *no* publish or approve commands. Every action requires a verified Switch `chat_message_id` and role (`lead`, `site_manager`, `finance`). **Removing Switch kills the app** because without Switch, no report can be drafted, approved, or published. |
| **4 Connected Specialized Agents** | Technical Complexity & Architecture | **Intro (0:25) & Steps 1–6**: 4 autonomous agents running over 4 concurrent duplex WebSockets: `@carbon-room` (Orchestrator), `@collector` (Ingestion), `@watchdog` (Audit & Rules), and `@reporter` (Disclosure & Trace). |
| **Human-in-the-Loop (HITL) Workflow** | Best Business Workflow | **Step 4 (1:18) & Mattermost Tour**: Multi-threaded gap resolution where humans (`@akshar`, `@richa` / Priya) upload evidence and approve variances in dedicated threads, updating live emissions from 0.0 to 21.9 tCO2e. |
| **Zero-Hallucination Proof Boundary** | AI Safety & Verifiability | **Step 2 (0:48)**: AI extractors are sandboxed; every extracted number must match verbatim bytes in raw source files or it is rejected. |
| **Cryptographic Tamper-Evident Chain** | Engineering Depth | **Step 6 (1:45) & Mattermost Tour**: Deterministic decimal arithmetic, factor locking (`FS-2026-10`), and a 91-event SHA-256 hash-chained ledger in SQLite. |
| **Real Impact** | Business Value | **Conclusion (2:35)**: Condenses 3 weeks of painful manual corporate carbon auditing into 3 minutes of mathematically verifiable multi-agent execution. |

---

## ⏱️ Video Timeline & Screen Breakdown (Total: 2m 45s)

```
0:00 ──────────────── 0:35 ──────────────── 1:55 ──────────────── 2:35 ────── 2:45
  [1. Intro & Why Switch]  [2. HTML Walkthrough: 1 to 6]   [3. Mattermost Tour]  [4. Impact]
```

- **0:00 – 0:35 (35s):** Architecture Overview on HTML page — Problem & Why Switch is Essential.
- **0:35 – 1:55 (80s):** Step-by-Step Voiceover on HTML Page (Clicking Steps 1 to 6).
- **1:55 – 2:35 (40s):** Tour of Existing Mattermost Messages (No typing required; scroll & expand threads).
- **2:35 – 2:48 (13s):** Closing Pitch & Business Impact.

---

## 🎬 Screen Setup Checklist (Before Hitting Record)

1. **Browser Tab 1:** Live Visualizer at `https://hodex7.github.io/Audit.CO2/` (or local [`docs/architecture-demo.html`](docs/architecture-demo.html)) (Full screen, zoomed to 100% or 110% for crisp display). Ensure Step 1 is selected.
2. **Browser Tab 2:** Mattermost Channel (`http://127.0.0.1:51547/switch/channels/emissions-reporting`). Make sure the completed October close run is visible and threads are readily expandable.
3. **Screen Resolution:** 1920x1080 (1080p).
4. **Audio:** Test microphone levels. Speak with energy, clarity, and authority.

---

## 🎙️ Word-for-Word Video Script

---

### [0:00 – 0:35] Act I: Introduction & Why Switch is Indispensable
**Screen:** Show `docs/architecture-demo.html` in browser. Mouse hovers over the 3 architecture layers (Chat Interface $\to$ 4 Specialized Agents $\to$ Core Ledger).

> **Voiceover (0:00 – 0:15):**  
> *"Every enterprise today faces strict CSRD and SEC emissions reporting mandates. Yet, corporate carbon accounting takes weeks of manual spreadsheet wrangling. And when companies try generic LLMs, disaster strikes: black-box models hallucinate emissions numbers, leading to massive greenwashing penalties.*  
>  
> *This is **Audit.CO2**—an autonomous multi-agent carbon accounting platform powered by **Switch**.*  

**Screen:** Point cursor to **Layer 1 (Switch Protocol)** and **Layer 2 (4 Room Agents)**.

> **Voiceover (0:15 – 0:35):**  
> *Now, why is Switch central here? Switch is **not** just a passive chat UI or notification bot. In Audit.CO2, Switch is the **authoritative execution and governance boundary**.*  
>  
> *Our CLI intentionally has **zero** publish or approve commands. By architectural design, every document upload, factor approval, and report publication requires an authoritative Switch `chat_message_id` and verified role-based identity.*  
>  
> ***Removing Switch kills the application*** *— because without Switch, the chain of custody breaks and the system mathematically refuses to publish.  
>  
> Let's see how our four specialized agents collaborate with human experts across the 6-step monthly close."*

---

### [0:35 – 1:55] Act II: Interactive Architecture Walkthrough (Steps 1 to 6)

#### Step 1: Close Initiation [0:35 – 0:48]
**Screen Action:** Click **Step 1: Initiation** tab (or **Next Step →**). The Orchestrator card glows cyan. Point to the Ledger Tracker on the right showing `Verified: 0.0 tCO2e (0% Coverage)`.

> **Voiceover:**  
> *"In **Step 1**, Sustainability Lead `@akshar` calls `@carbon-room close October`.*  
>  
> *The orchestrator immediately locks emission factor set `FS-2026-10`, transitions the room state to `COLLECTING`, and dispatches `@collector`.*  
>  
> *Notice our ledger tracker on the right: corporate verified emissions start strictly at **0.0 tCO2e**."*

---

#### Step 2: Proof Boundary & Ingestion [0:48 – 1:02]
**Screen Action:** Click **Step 2: Collection** tab. The Ingestion Engine and Proof Boundary cards glow blue.

> **Voiceover:**  
> *"In **Step 2**, `@collector` ingests raw PDF invoices, emails, and cloud bills into content-addressable storage.*  
>  
> *Here is our first AI safety breakthrough: the **Zero-Hallucination Proof Boundary**. LLMs extract candidate numbers, but a deterministic byte-validator verifies that every extracted figure matches verbatim in the raw document text. If an AI hallucinates a number, it is instantly rejected before touching the database."*

---

#### Step 3: Audit Engine & 7 Deterministic Rules [1:02 – 1:18]
**Screen Action:** Click **Step 3: Audit Engine** tab. The Watchdog and 7 Rules cards glow amber.

> **Voiceover:**  
> *"In **Step 3**, `@watchdog` runs all 7 deterministic GHG compliance rules.*  
>  
> *It identifies four critical blockers: a period mismatch on Warehouse-2, conflicting diesel invoices, a stale grid factor, and a 38% electricity surge.  
>  
> Instead of quietly guessing or averaging, Watchdog quarantines **24.7 tCO2e** of unverified data, keeps verified emissions at zero, and automatically opens four dedicated resolution threads in Switch."*

---

#### Step 4: Human-in-the-Loop (HITL) Thread Resolution [1:18 – 1:35]
**Screen Action:** Click **Step 4: HITL** tab. Human nodes (`@akshar`, `@richa`) and Watchdog glow purple. Point to the Ledger Tracker jumping to `21.9 tCO2e` (100% Coverage).

> **Voiceover:**  
> *"In **Step 4**, the power of Switch shines. Humans and agents collaborate inside dedicated threads.*  
>  
> *Priya, our site manager, uploads the actual Warehouse-2 invoice in thread G-3. The Lead picks Revision A for diesel in G-1, approves the locked factor in G-2, and approves the variance in G-4.*  
>  
> *As each thread resolves, Watchdog recalculates the ledger in real-time. Verified emissions move dynamically from 0 to 8.6, to 12.5, reaching exactly **21.9 tCO2e** with 100% verified coverage."*

---

#### Step 5: Regulatory Compliance & Disclosure Draft [1:35 – 1:45]
**Screen Action:** Click **Step 5: Disclosure** tab. The Reporter card glows emerald.

> **Voiceover:**  
> *"In **Step 5**, the Lead requests `@reporter draft`.*  
>  
> *Reporter compiles Draft v1 with mandatory CSRD disclosures: separating certificate-based clean energy and explicitly flagging unverified AI datacenter workloads—preventing corporate greenwashing penalties."*

---

#### Step 6: Immutable Publication & 91-Event Audit Chain [1:45 – 1:55]
**Screen Action:** Click **Step 6: Publication** tab. The entire bottom layer and Auditor node glow emerald. Point to `91 Events Intact`.

> **Voiceover:**  
> *"Finally, in **Step 6**, the Lead publishes. Immutable PDF, JSON, and HTML reports are generated.*  
>  
> *External Auditor `@p3admin` asks `@reporter verify audit`—and the system cryptographically verifies all **91 SHA-256 chained events** in SQLite. If anyone tampers with a single byte in the database, the cryptographic hash tree fails instantly."*

---

### [1:55 – 2:35] Act III: Live Mattermost Tour (Existing Execution Messages)

**Screen Action:** Switch browser tab to Mattermost channel `http://127.0.0.1:51547/switch/channels/emissions-reporting`.  
Smoothly scroll through the existing message history.

> **Voiceover (1:55 – 2:10):**  
> *"Now let's see these exact messages live in our Switch Mattermost channel.*  
>  
> *Here is `@akshar` starting the close, and `@carbon-room` locking factor set `FS-2026-10`.*  
> *Below that, `@collector` posts the harvested batch of 5 source documents.*  
> *And right here is `@watchdog` declaring the four compliance gaps, holding corporate emissions at 0.0 tCO2e."*

**Screen Action:** Click on the thread icon for **G-3** or scroll to show the threaded interactions:

> **Voiceover (2:10 – 2:25):**  
> *"Looking into the threads: here is Priya uploading the actual Warehouse-2 electricity bill, resolving Gap 3.*  
> *In Gap 1, the Lead replied `pick A`. In G-2 and G-4, the Lead replied `approve`.*  
>  
> *And look at Watchdog's live update post: verified emissions cleanly updated to **21.9 tCO2e** with 100% coverage."*

**Screen Action:** Scroll down to the final messages at the bottom:

> **Voiceover (2:25 – 2:35):**  
> *"At the bottom, we see `@reporter draft`, `@carbon-room publish` outputting the final signed report artifacts, and when we ask `@reporter trace S-001`, it outputs the exact mathematical lineage and raw document excerpt.  
> And `@reporter verify audit` confirms all **91 events** in the cryptographic chain are intact."*

---

### [2:35 – 2:48] Act IV: Impact & Winning Conclusion

**Screen Action:** Switch back to `docs/architecture-demo.html` or display the final summary view.

> **Voiceover:**  
> *"Audit.CO2 reduces corporate emissions auditing from **three weeks of spreadsheet chaos to three minutes of verifiable multi-agent execution**.*  
>  
> *Switch makes this possible by providing the trusted human-agent communication bus and cryptographic governance boundary that enterprise compliance demands.*  
>  
> *Flip the Switch on carbon accounting. Thank you!"*

---

## 💡 Quick Tips for the Live Recording

1. **Pacing:** Keep a steady, confident pace. Don't rush, but don't pause unnecessarily. The script is timed at ~140 words per minute, easily fitting within 2 minutes 45 seconds.
2. **Cursor Guidance:** When you talk about an agent or card (e.g. `@watchdog`, Proof Boundary, 91 Events), hover your mouse over it briefly to draw the judge's eyes.
3. **No Live Typing Risk:** Because you are presenting the interactive architecture diagram and touring the already completed live Mattermost thread run, there is **zero risk of network delay, typo, or CLI failure** during the recording.
4. **YouTube Settings:** Upload as **Unlisted** (or Public), title it *"Audit.CO2 — Autonomous Multi-Agent Emissions Accounting on Switch (WeMakeDevs Hackathon)"*, and include the repository link (`https://github.com/HodeX7/Audit.CO2`) in the description.
