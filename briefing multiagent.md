# Briefing Document

## 1. Goal Proof-Of-Concept Phase

The objective is to automate the complex and labor-intensive reporting process required by
government institutions for youth integration programs. These reports are triggered across
multiple program phases and rely on fragmented data (e.g., PDFs, DocX, case notes). We aim
to build a **multi-agent system enhanced by LLMs** that automates report generation, ensures
compliance, and reduces manual workload.
In the **first phase** we are looking to create an easy accessible fast solution to deliver a **PoC** and
validate the use case within the next three months together with the agency.

## 2. Approach

```
● Develop an automated reporting pipeline using self-hosted n8n as the orchestration
layer.
● Integrate LLM (Large Language Model) agents to handle:
○ Document ingestion (PDFs, emails, forms)
○ Phase-specific context extraction
○ Validation against reporting templates
○ Draft generation and formatting (Word, PDF)
● The system should support human-in-the-loop validation after each step / chapter of
the creation of the end-report, and especially for final report checks.
```
## 3. Architecture (High-Level Overview)

**Components:**
● **Input Layer** :
○ Document Reader (PDF / Word), Data Analytic Tool (Excel)


○ LLM parsing of case notes
● **Agent Layer** :
○ Context Agent (track case progression)
○ Compliance Agent (verify against required templates)
○ Report Generation Agent
○ Validation Agent - after every chapter a human-in-the-loop validation shall be
included
● **Orchestration Layer** :
○ **n8n** workflows to trigger agents, manage data flow, and ensure process
traceability, human-
● **Output Layer** :
○ Reports exported in required formats (e.g., docx, PDF)
○ Storage and submission-ready packages
○ Visualizations:


## 4. Guidelines

1. **Platform** :
    ○ Base orchestration must use **n8n**
    ○ Self-hosted on a Swiss infrastructure (i.e. via Hostinger, not cloud.n8n.io usage)
2. **LLM**
    ○ Use open-source LLM in order to manage the content and deliver the results
    ○ Either use an existing Swiss-hosted LLM solution offered via API (i.e. SwissGPT,
       Infomaniak, Kvant,...) or deploy an LLM solution in a Swiss-hosted cloud and
       access via API
3. **Hosting**
    ○ All components must be **hosted in Switzerland**
    ○ If LLMs are used via API, the **provider must guarantee data remains in CH**
    ○ Optionally, propose a **fully self-hosted LLM stack** (e.g., LLaMA, Mistral) in a
       CH-based cloud
4. **Security & Compliance** :
    ○ GDPR and Swiss data protection laws must be followed
    ○ Role-based access, audit trails, and data retention policies must be considered
5. **Scalability** : (optional not for PoC)
    ○ The system should be modular and expandable to support new templates or data
       sources
    ○ Agents should be decoupled for maintenance and future AI model swaps


## 5. Questions to Supplier

Please include clear responses or proposals for the following points:

1. **Technical Feasibility** :
    ○ How would you design the LLM agent layer within n8n?
    ○ What models or tools do you recommend for document understanding?
2. **LLM Deployment** :
    ○ Can you support deploying a performant LLM model fully in CH infrastructure?
    ○ Do you have experience with open-source models suitable for this (e.g., Mistral,
       GPT-J)?
3. **Integration with n8n** :
    ○ What’s your experience in extending/customizing n8n for multi-agent logic?
    ○ How would you structure agent triggering and workflow fallback (e.g., on failure)?
4. **Human-in-the-Loop Editing** :
    ○ What UI or integration layer would you propose for manual review/editing?
5. **Security & Hosting** :
    ○ What infrastructure partners do you suggest for CH-only hosting (e.g., Exoscale,
       Infomaniak)?
    ○ What measures would you implement to secure data at rest and in transit?
6. **Estimated Timeline & Budget** :
    ○ Provide a rough time and cost estimation for a PoC


