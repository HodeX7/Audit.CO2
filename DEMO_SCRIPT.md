# Audit.CO2 — Hackathon Video Script & Presentation Guide
**Event:** WeMakeDevs "Flip the Switch" Hackathon  
**Track:** Best Business Workflow / Human-Agent Collaboration  
**Presentation Strategy:** Interactive Architecture Walkthrough (Layers & Agent Roles) + Live Mattermost Collaboration Tour  
**Target Video Duration:** 2:20 – 2:40 (Strictly under 3:00 hard limit)  
**Deliverables:** Hosted on YouTube (Unlisted or Public) at 1080p / 60fps  

---

## 🏆 Key Winning Points for Judges (Evaluation Checklist)

| Winning Point | Hackathon Criterion | Where It Appears in Script |
|---|---|---|
| **Why Switch is Central & Indispensable** | Effective Use of Switch | **Intro (0:15) & Throughout**: Switch is NOT just a chat UI; it is the **authoritative cryptographic and operational boundary**. The CLI intentionally has *no* publish or approve commands. Every action requires a verified Switch `chat_message_id` and role (`lead`, `site_manager`, `finance`). **Removing Switch kills the app** because without Switch, no report can be drafted, approved, or published. |
| **4 Connected Specialized Agents** | Technical Complexity & Architecture | **Intro (0:25) & Step-by-Step**: 4 autonomous agents running over 4 concurrent duplex WebSockets: `@carbon-room` (Orchestrator), `@collector` (Ingestion), `@watchdog` (Audit & Rules), and `@reporter` (Disclosure & Trace). |
| **Human-in-the-Loop Collaboration** | Best Business Workflow | **Step 4 & Mattermost Tour**: Multi-threaded gap resolution where human facility managers and leads collaborate with agents in dedicated threads to resolve evidence blockers. |
| **Zero-Hallucination Proof Boundary** | AI Safety & Verifiability | **Step 2**: AI extractors are sandboxed; every extracted claim must match verbatim text bytes in raw source files or it is rejected. |
| **Cryptographic Tamper-Evident Chain** | Engineering Depth | **Step 6 & Mattermost Tour**: Deterministic decimal arithmetic, factor set immutability, and a SHA-256 hash-chained ledger in SQLite. |
| **Real-World Business Impact** | Business Value | **Conclusion**: Transforms weeks of fragmented enterprise spreadsheets into minutes of transparent, verifiable human-agent teamwork. |

---

## ⏱️ Video Timeline & Screen Breakdown (Total: ~2m 30s)

```
0:00 ──────────────── 0:35 ──────────────── 1:45 ──────────────── 2:20 ────── 2:30
  [1. Intro & Why Switch]  [2. Architecture & Agent Walkthrough]   [3. Mattermost Tour]  [4. Impact]
```

- **0:00 – 0:35 (35s):** Architecture Overview — The Problem & Why Switch is the Core Backbone.
- **0:35 – 1:45 (70s):** Architecture & Agent Roles Walkthrough (Stepping through 1 to 6 on the HTML Visualizer).
- **1:45 – 2:20 (35s):** Mattermost Live Tour (Showcasing Real Human-Agent Collaboration in Threads).
- **2:20 – 2:35 (15s):** Closing Pitch & Business Impact.

---

## 🎬 Screen Setup Checklist (Before Hitting Record)

1. **Browser Tab 1:** Live Architecture Visualizer at `https://hodex7.github.io/Audit.CO2/` (Full screen, zoomed to 100% or 110%). Start on **Step 1**.
2. **Browser Tab 2:** Mattermost Channel (`http://127.0.0.1:51547/switch/channels/emissions-reporting`). Keep the completed run ready so you can scroll and expand threads smoothly.
3. **Screen Resolution:** 1920x1080 (1080p).
4. **Audio:** Speak with clear energy, confidence, and authority.

---

## 🎙️ Word-for-Word Video Script

---

### [0:00 – 0:35] Act I: Introduction & Why Switch is Indispensable

**Screen:** Display the Architecture Visualizer at `https://hodex7.github.io/Audit.CO2/`. Mouse hovers across the 3 architecture layers (Chat Interface $\to$ 4 Specialized Agents $\to$ Core Ledger).

> **Voiceover (0:00 – 0:15):**  
> *"Every enterprise today faces stringent emissions reporting mandates. Yet corporate carbon accounting remains trapped in weeks of fragmented spreadsheets and disconnected facility teams. When companies try generic generative AI, black-box models hallucinate emissions data, exposing organizations to severe greenwashing penalties.*  
>  
> *This is **Audit.CO2**—an autonomous multi-agent carbon accounting platform powered by **Switch**.*  

**Screen:** Point cursor to **Layer 1 (Switch Protocol)** and **Layer 2 (4 Room Agents)**.

> **Voiceover (0:15 – 0:35):**  
> *Now, why is Switch central to this architecture? Switch is **not** an optional chat wrapper or notification bot. In Audit.CO2, Switch is the **authoritative governance and execution boundary**.*  
>  
> *Our system intentionally has **no** standalone CLI commands to publish reports or approve data. By architectural design, every document upload, factor resolution, and publication requires an authoritative Switch message ID and verified role identity.*  
>  
> ***Removing Switch kills the application*** *— because without Switch, the chain of custody breaks and the system mathematically refuses to publish.*  
>  
> *Let's see how our four specialized agents collaborate with human stakeholders to complete a full enterprise close."*

---

### [0:35 – 1:45] Act II: Architecture & Agent Roles Walkthrough (Steps 1 to 6)

#### Step 1: Close Initiation & Orchestration [0:35 – 0:45]
**Screen Action:** Click **Step 1: Initiation** tab (or **Next Step →**). The Orchestrator card glows cyan.

> **Voiceover:**  
> *"In **Step 1**, the Sustainability Lead triggers the close in the room.*  
>  
> *Our Orchestrator agent, `@carbon-room`, takes charge. It locks the regulatory emissions factor set to prevent retroactive tampering, advances the close state machine, and orchestrates task hand-offs to our downstream agents.*  
>  
> *Notice our ledger architecture: unverified claims are strictly quarantined, ensuring unvetted numbers never enter corporate totals."*

---

#### Step 2: Ingestion & Zero-Hallucination Proof Boundary [0:45 – 0:58]
**Screen Action:** Click **Step 2: Collection** tab. The Ingestion Engine and Proof Boundary cards glow blue.

> **Voiceover:**  
> *"In **Step 2**, our Ingestion agent, `@collector`, harvests raw evidence across utility PDFs, emails, and cloud billing records into content-addressable storage.*  
>  
> *Here is our core AI safety innovation: the **Zero-Hallucination Proof Boundary**. While AI models assist with extraction, an automated byte-validator enforces that every extracted claim must match verbatim text in the source document. If an AI hallucinates, the proof boundary catches and rejects it before it can ever touch the ledger."*

---

#### Step 3: Audit Engine & Deterministic Rules [0:58 – 1:10]
**Screen Action:** Click **Step 3: Audit Engine** tab. The Watchdog and 7 Rules cards glow amber.

> **Voiceover:**  
> *"In **Step 3**, our Compliance agent, `@watchdog`, evaluates all data against deterministic greenhouse gas accounting rules.*  
>  
> *Instead of silently guessing or averaging discrepancies, Watchdog flags real-world compliance traps: billing period mismatches, conflicting vendor invoices, stale grid factors, and consumption spikes.*  
>  
> *It isolates these issues, excludes unverified figures from the close, and automatically spins out dedicated resolution threads in Switch."*

---

#### Step 4: Human-in-the-Loop Thread Resolution [1:10 – 1:24]
**Screen Action:** Click **Step 4: HITL** tab. Human nodes (`@akshar`, `@richa`) and Watchdog glow purple.

> **Voiceover:**  
> *"In **Step 4**, the true power of human-agent collaboration through Switch comes alive.*  
>  
> *Rather than overwhelming the main channel, stakeholders collaborate directly inside dedicated threads: our Site Manager uploads the corrected facility bill, while the Lead and Finance review vendor conflicts and approve factor overrides.*  
>  
> *As humans resolve each issue, Watchdog dynamically recalculates corporate totals in real-time—anchoring every human action to their authenticated Switch identity."*

---

#### Step 5: Regulatory Compliance & Disclosure Draft [1:24 – 1:35]
**Screen Action:** Click **Step 5: Disclosure** tab. The Reporter card glows emerald.

> **Voiceover:**  
> *"In **Step 5**, our Disclosure agent, `@reporter`, compiles the audit-ready disclosure draft.*  
>  
> *It applies strict regulatory guardrails: separating market-based clean energy certificates from physical grid emissions and explicitly flagging unverified cloud AI workloads—safeguarding the company against greenwashing liability."*

---

#### Step 6: Immutable Publication & Cryptographic Audit Chain [1:35 – 1:45]
**Screen Action:** Click **Step 6: Publication** tab. The bottom ledger layer and Auditor node glow emerald.

> **Voiceover:**  
> *"Finally, in **Step 6**, the Lead authorizes publication, generating immutable PDF, JSON, and web reports.*  
>  
> *Our External Auditor can invoke `@reporter` at any time to inspect full mathematical lineage and verify the cryptographic SHA-256 event chain in our SQLite ledger. If anyone tampers with a single record, the cryptographic hash tree fails immediately."*

---

### [1:45 – 2:20] Act III: Live Mattermost Tour (Human-Agent Teamwork in Action)

**Screen Action:** Switch browser tab to Mattermost channel `http://127.0.0.1:51547/switch/channels/emissions-reporting`.  
Smoothly scroll through the channel to show the real workspace collaboration.

> **Voiceover (1:45 – 2:00):**  
> *"Now let's see how this collaboration actually feels inside our Switch Mattermost channel.*  
>  
> *Here, the Sustainability Lead kicks off the close with `@carbon-room`, and the orchestrator acknowledges by locking factor versions.*  
> *`@collector` confirms the ingestion of multi-facility evidence.*  
> *And right below, `@watchdog` posts the actionable compliance gaps, keeping our channel transparent and focused."*

**Screen Action:** Click open the thread drawer (e.g. Gap 3 or Gap 1) to show the threaded conversation:

> **Voiceover (2:00 – 2:12):**  
> *"Inside the threads, you can see human-agent teamwork at work: Priya, our facility manager, uploads the correct bill right inside the thread, and Watchdog verifies it on the spot.*  
> *In neighboring threads, the Lead resolves supplier invoice conflicts and confirms variance approvals.*  
> *Notice how cleanly threads keep the main channel uncluttered while maintaining full context."*

**Screen Action:** Scroll down to the final messages at the bottom:

> **Voiceover (2:12 – 2:20):**  
> *"At the bottom, `@reporter` drafts the disclosure and `@carbon-room` publishes the signed reporting suite.*  
> *Anyone on the team can ask `@reporter trace` for instant mathematical lineage, or `@reporter verify audit` to validate the tamper-evident cryptographic chain."*

---

### [2:20 – 2:35] Act IV: Business Impact & Conclusion

**Screen Action:** Switch back to `https://hodex7.github.io/Audit.CO2/` or show the final summary view.

> **Voiceover:**  
> *"Audit.CO2 transforms corporate carbon accounting from **weeks of spreadsheet chaos into minutes of transparent, verifiable human-agent collaboration**.*  
>  
> *Switch makes this possible by providing the trusted communication bus, role-based identity, and cryptographic governance boundary that enterprise compliance demands.*  
>  
> *Flip the Switch on carbon accounting. Thank you!"*

---

## 💡 Key Reminders for the Recording
1. **Focus on Roles & Architecture:** Keep the emphasis on *what the agents are doing* (orchestrating, ingesting with proof boundaries, auditing against rules, disclosing with guardrails) and *how humans collaborate via Switch*.
2. **Smooth Transitions:** Move smoothly from the architecture diagram tabs (1 to 6) to the Mattermost channel.
3. **Pacing:** At ~135 words per minute, this script clocks in at **2 minutes 25 seconds**—leaving plenty of breathing room well under the 3-minute limit.
