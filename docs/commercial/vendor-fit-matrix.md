# Vendor fit matrix

Research checked against vendor-controlled pages on August 20, 2026. A public
product claim establishes relevance, not willingness to buy.

## First wave: systems that directly answer government or property questions

| # | Vendor | Public reason it fits | Best first test | Contact route |
|---:|---|---|---|---|
| 1 | Polimorphic | Its platform says it uses municipal codes and GIS layers for address-specific regulatory answers. | 20 address-level answers across jurisdictions; property identity, official record and abstention. | Product/QA owner through [platform page](https://www.polimorphic.com/platform). |
| 2 | CivicPlus | CivicPlus Agent says it answers from Municipal Websites and Municode, while staff monitor submitted questions and answers. | Questions that require a property-specific official record outside a general website page. | Phil Claiborne or the Agent product team via [CivicPlus Intelligence](https://www.civicplus.com/civicplus-intelligence/). |
| 3 | Citibot | Citibot says it supports resident answers for 200+ governments in 35+ states. | Repeated address and jurisdiction questions from three participating communities. | Product or partnerships; public email `chat@citibot.io` on [communities page](https://www.citibot.io/our-communities). |
| 4 | Granicus | GXA says it returns answers from agency-approved sources and provides source citations. | Whether citations open the exact supporting record, not only an agency page. | GXA product/AI team via [GXA](https://granicus.com/gxa/). |
| 5 | Tyler Technologies | Resident AI Assistant says it connects several agencies and surfaces government-site answers in seconds. | Cross-department property questions where website text and official GIS differ. | Resident Experience product team via [Resident AI Assistant](https://www.tylertech.com/products/resident-assistant). |
| 6 | CityFront | AskEcho says it verifies a government's digital presence and returns verified answers. | Address questions requiring evidence beyond page retrieval and a correct jurisdiction. | Product team; public email `sales@cityfront.ai` on [CityFront](https://www.cityfront.ai/). |
| 7 | Munibit | Its resident assistant reads municipal pages and documents and claims accurate, current answers. | Small-town questions where a document answer is insufficient without a property lookup. | Product owner; public email `contact@munibit.com` on [AI chatbot page](https://www.munibit.com/ai-chatbot). |
| 8 | GovToKnow | It markets cited answers from official documents, including address-specific public-safety examples. | Citation usability, correct address and source-date tests. | Founder/product contact through [GovToKnow](https://govtoknow.com/). |
| 9 | Forerunner | Its public portal provides address and parcel search, flood zone, SFHA, BFE and official property files. | Flood-zone and wrong-parcel tests; Lasting Ground should complement, not pretend to replace, its workflow. | Data/product team via [public-site documentation](https://withforerunner.com/docs/public-website/overview). |
| 10 | Esri | ArcGIS Hub assistant answers natural-language questions over public datasets; ArcGIS is adding agentic mapping. | Whether an agent chooses the correct layer, feature, property and reproducible spatial operation. | Hub assistant or agentic GIS product team via [Hub assistant](https://www.esri.com/arcgis-blog/products/arcgis-hub/constituent-engagement/chat-with-the-arcgis-hub-assistant). |

## Second wave: property, risk and spatial platforms

These companies may value external data and answer QA, but several sell data
rather than resident-facing answers. They are lower-probability until the first
wave confirms that the audit is useful.

| # | Vendor | Public reason it fits | Best first test | Contact route |
|---:|---|---|---|---|
| 11 | OpenGov | OG Assist says it can analyze properties, parcels, assets and other government datasets in context. | Parcel identity, evidence lineage and unsupported “no” answers in property analysis. | OG Assist product team via [OG Assist](https://opengov.com/products/og-assist/). |
| 12 | CARTO | CARTO for Agents exposes governed spatial analysis through MCP tools with traceability. | Reproducible natural-language spatial queries and source/operation traces. | Agentic GIS product team via [CARTO for Agents](https://carto.com/blog/introducing-carto-for-agents-gis-for-the-agentic-enterprise/). |
| 13 | Regrid | Regrid offers nationwide parcel, address and zoning data through REST and MCP. | Address-to-parcel match quality and abstention where a requested fact is absent. | API/MCP product team via [Regrid API](https://regrid.com/api). |
| 14 | LightBox | LightBox Live unifies regulatory environmental records with parcels and municipal boundaries. | Official-record identity, distance rule, date and citation tests for environmental answers. | Environmental data/product team via [environmental data documentation](https://lightbox.document360.io/lightbox/docs/environmental-data). |
| 15 | ATTOM | ATTOM's API exposes address match codes, parcel IDs, coordinates and source publication dates. | Wrong-property and stale-record tests across address normalization edge cases. | Property API product/data QA via [API documentation](https://api.developer.attomdata.com/docs). |
| 16 | First Street | Its APIs return climate risk by point and portfolio with explicit data vintages. | Property identity, vintage disclosure and citation tests alongside—not against—modeled risk. | Enterprise API/data QA via [First Street API](https://docs.firststreet.org/api). |
| 17 | Precisely | Its Data Graph and Risks APIs join address, property and hazard records. | Address match and risk-source lineage across multiple datasets. | Data Graph/Risks product team via [Data Graph](https://developer.cloud.precisely.com/apis/data-graph). |
| 18 | Nearmap | Nearmap sells current property intelligence, AI layers and government workflows. | Official-record corroboration for AI-derived property attributes and change dates. | Property Intelligence QA/product via [government offering](https://www.nearmap.com/solutions/government). |
| 19 | UrbanFootprint | It joins thousands of datasets across 160 million parcels for resilience analysis. | Source-date, parcel identity and reproducibility for resilience insights. | Insight Engine/data team via [UrbanFootprint](https://urbanfootprint.com/). |
| 20 | Accela | Accela says its AI is explainable, auditable and accountable across civic workflows. | Evidence lineage for property-facing answers, excluding permit questions from the GroundTruth test. | AI/platform product team via [Accela](https://www.accela.com/). |

## Brutal prioritization

- **Best fit now:** Polimorphic. It publicly names the exact address-level GIS
  behavior the evaluation tests.
- **Best distribution:** CivicPlus, Citibot, Granicus and Tyler. They have many
  government deployments, but their internal QA may be sophisticated and sales
  cycles may be slow.
- **Best property-specific wedge:** Forerunner, LightBox and Regrid. They may see
  Lasting Ground as a competitor or redundant data layer, so the message must be
  external evaluation, not “we have better data.”
- **Largest eventual contract, lowest first-sale probability:** Esri, CARTO,
  ATTOM, Precisely and Nearmap.
- **Do not count 20 emails as pipeline:** a target becomes qualified only after
  it names cases, an owner and a plausible payment path.
