# Written outreach drafts

**Status: drafts only. Do not send until the send gate in `README.md` passes and Tim approves each message. Replace every bracketed release field.**

## Rules for every message

- Ask whether the problem and method fit; do not lead with price.
- Do not call the benchmark independent, certified, representative or national.
- Do not claim that a vendor has errors before testing its outputs.
- Do not promise to test private resident data or permit workflows.
- Link to the stable 20-case audit and evidence contract after they are public.
- Keep the entire exchange in writing.

## 1. Polimorphic

**Subject:** Testing address-level government answers against official records

Hi Polimorphic product team,

Your platform page says Polimorphic uses municipal codes and GIS layers to
answer address-specific questions. I built Lasting Ground, a property-evidence
system, and GroundTruth-Geo, a small evaluation that checks the failure points
that matter in those answers: the wrong property, the wrong official source, an
unsupported answer, a citation that does not open the record, stale evidence,
or failing to stop when the record is not enough.

Here is a 20-case example audit: **https://lasting-ground-citygraph.pages.dev/groundtruth-audit**. It is a real
closed-book run in which the model stopped on every question; the audit does not
present that as accuracy, because none of the questions was answered.

Would the product or QA owner for Polimorphic's address-level answers be willing
to tell me whether this six-check method fits your release process? If useful,
you could send five representative questions and outputs. I would respond in
writing with whether they are evaluable and what a bounded paid test would need.

Tim Sullivan
Lasting Ground
**https://github.com/sulmusic2-star/groundtruth-geo/blob/main/docs/evidence-contract.md**

## 2. CivicPlus

**Subject:** An external check for CivicPlus Agent's official-source answers

Hi Phil,

CivicPlus says its Agent answers from Municipal Websites and Municode, and that
municipal leaders can review submitted questions and answers. I built a narrow
property-answer audit that could add a different check: whether an
address-specific answer chose the right property, opened the exact official
record, supported the answer, used dated evidence, and stopped when the source
could not answer.

The 20-case example is here: **https://lasting-ground-citygraph.pages.dev/groundtruth-audit**. It shows the model
answer beside the official record and keeps safe abstention separate from a
usable answer.

Does that test match any CivicPlus Agent or Athena QA need? If so, send five
representative address-level questions and outputs. I will reply in writing with
whether the method fits and, only then, a bounded paid-evaluation scope.

Tim Sullivan
Lasting Ground
**https://github.com/sulmusic2-star/groundtruth-geo/blob/main/docs/evidence-contract.md**

## 3. Citibot

**Subject:** A property-answer audit for resident AI systems

Hi Citibot product team,

Citibot says it helps more than 200 governments answer resident questions. I
built Lasting Ground and GroundTruth-Geo to test a narrow class of those
questions: answers tied to a specific address and official flood,
environmental, historic or land record.

For every answer, the audit checks the property, source, support, citation,
evidence date and whether the system stopped when it could not know. The
20-case example is here: **https://lasting-ground-citygraph.pages.dev/groundtruth-audit**.

Would you be willing to send five representative address-level questions and
outputs from a test environment or public deployment? I will respond in writing
with whether the method fits. If it does, the next step would be a separately
scoped paid evaluation—not an open-ended free audit.

Tim Sullivan
Lasting Ground
**https://github.com/sulmusic2-star/groundtruth-geo/blob/main/docs/evidence-contract.md**

## Shared body for vendors 4–20

Use one tailored opening below, then this body:

> I built Lasting Ground and GroundTruth-Geo to test six things in an
> address-specific answer: the property, the official source, support for the
> answer, whether the citation opens the record, the evidence date, and whether
> the system stops when it cannot know. A 20-case example audit is here:
> **https://lasting-ground-citygraph.pages.dev/groundtruth-audit**.
>
> Does that method fit any current product, QA, release or customer-assurance
> need? If so, send five representative questions and outputs. I will reply in
> writing with whether they are evaluable and what a bounded paid test would
> require. I would discuss price only after the scope and accepted evidence are
> clear.
>
> Tim Sullivan
> Lasting Ground
> **https://github.com/sulmusic2-star/groundtruth-geo/blob/main/docs/evidence-contract.md**

## Tailored openings 4–20

4. **Granicus — subject: Checking whether a GXA citation supports the exact answer.**
   Your GXA materials say answers come from agency-approved sources and include
   source citations. I am testing the narrower question a reviewer faces after
   seeing that citation: does it open the exact record that supports this
   address-specific answer?

5. **Tyler — subject: External evidence checks for Resident AI Assistant.**
   Tyler says Resident AI Assistant can connect information across agencies and
   reduce support work. I am testing address questions where the correct answer
   depends on choosing the right property and official dataset, not merely the
   most relevant website page.

6. **CityFront — subject: A six-part check for AskEcho's verified answers.**
   CityFront says AskEcho returns verified answers from a government's own
   digital presence. I built a case-level audit that shows exactly what
   “verified” means for a property answer and what remains unknown.

7. **Munibit — subject: Testing small-town resident answers that need a property record.**
   Munibit says its assistant answers from municipal pages and documents. I am
   testing the boundary where a page is relevant but an address-specific answer
   still requires the correct official property record.

8. **GovToKnow — subject: Can the cited source support the address-level claim?**
   GovToKnow leads with cited answers from public records, including
   address-specific examples. My audit tests whether the citation, property,
   evidence date and answer all agree.

9. **Forerunner — subject: External replay of address-to-flood answers.**
   Forerunner already provides property search, SFHA status, flood zones and
   official property files. I am not proposing another floodplain workflow; I am
   proposing an external, reproducible replay of the property match and evidence
   behind selected answers.

10. **Esri — subject: Reproducible checks for natural-language spatial answers.**
    ArcGIS Hub assistant and agentic mapping make public spatial data accessible
    through natural language. My audit asks whether the resulting answer chose
    the right layer, feature and property and preserved the operation a reviewer
    can reproduce.

11. **OpenGov — subject: Evidence checks for OG Assist property and parcel answers.**
    OG Assist says users can ask questions about properties, parcels and assets.
    I built a narrow test for whether those answers preserve property identity,
    source lineage and honest unknowns.

12. **CARTO — subject: Case-level assurance for agentic spatial analysis.**
    CARTO for Agents emphasizes governed, traceable spatial workflows. I built a
    case-level evaluation that compares the agent's answer and trace with the
    dated official record a human reviewer needs.

13. **Regrid — subject: Testing address-to-parcel answers through REST and MCP.**
    Regrid exposes standardized parcel and address data through both REST and
    MCP. My evaluation focuses on address-match quality, correct parcel identity
    and abstention when the requested official fact is absent.

14. **LightBox — subject: Record-level checks for environmental property answers.**
    LightBox Live joins environmental records with parcels and municipal
    boundaries. I built a reproducible check for the exact regulatory record,
    property identity, distance rule, date and citation behind a selected answer.

15. **ATTOM — subject: External property-match and evidence-date evaluation.**
    ATTOM exposes address match codes, parcel IDs, coordinates and source dates.
    My test uses those same kinds of fields to catch wrong-property and stale
    evidence errors before evaluating the final answer.

16. **First Street — subject: A separate official-record check beside modeled risk.**
    First Street publishes explicit API vintages for point and portfolio climate
    risk. My evaluation would not judge the climate model; it would test property
    identity, vintage disclosure and official-record citations in any downstream
    address answer.

17. **Precisely — subject: Testing source lineage across address, property and risk data.**
    Precisely's Data Graph joins address, property and natural-hazard records. I
    built an evaluation for whether an answer preserves the right location and
    source lineage across those joins.

18. **Nearmap — subject: Official-record corroboration for property AI outputs.**
    Nearmap emphasizes current, defensible property intelligence. My audit could
    test a complementary question: when a downstream answer cites an official
    government condition, does that record support the AI-derived property
    result on the stated date?

19. **UrbanFootprint — subject: Reproducibility checks for parcel-level resilience answers.**
    UrbanFootprint joins thousands of datasets across a nationwide parcel core.
    I built a compact way to test the property identity, source date and
    reproducibility behind selected resilience answers.

20. **Accela — subject: Evidence lineage for property-facing AI answers.**
    Accela says its AI is intended to be explainable, auditable and accountable.
    I built a permit-free property-answer test that checks the evidence chain a
    reviewer would need for those claims.

## Follow-up after seven business days

**Subject:** Re: [original subject]

Hi [name],

One concise follow-up: is address-specific answer evaluation relevant to your
product or QA work, and if not, should I close this out?

The example audit is **https://lasting-ground-citygraph.pages.dev/groundtruth-audit**. I am looking for five
representative questions to determine fit before proposing any paid scope.

Tim

Send at most one follow-up. Silence is not demand.
