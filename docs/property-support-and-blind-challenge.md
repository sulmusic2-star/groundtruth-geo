# Property support and external challenge status

## What changed

The original benchmark asks questions about a Census-geocoded point. That remains a reproducible public task, but it is not always a reliable stand-in for the actual property. The stronger review keeps the point result and adds a separate official property support: an exact local address point linked to one official building footprint or parcel.

The support review uses three outcomes:

- `certain_yes`: every location in the selected property geometry produces yes;
- `certain_no`: every location produces no; and
- `mixed`: the decision boundary crosses the property, so one point hides a material ambiguity.

It blocks the case when the local address cannot be confirmed, more than one building remains plausible, the address point does not fall inside the selected building or parcel, or federal source coverage is incomplete. Source authority, currency, and redistribution rights are separate fields.

## Current sensitive-case result

| Property | Census-to-local offset | Support | Result | Current status |
|---|---:|---|---|---|
| 1300 Ocean Dr, Miami Beach | 33.238 m | Exact addressed county building | FEMA certain yes | Reviewed automated screen |
| 10 E Liberty St, Savannah | — | No publishable exact local address or parcel confirmation | Blocked | Property identity unresolved |
| 600 Congress Ave, Austin | 47.709 m | Unique building containing exact city address point | Historic districts certain yes | Provisional: 2017 building imagery |
| 1600 Pennsylvania Ave NW, Washington | 163.787 m | Unique building containing an active center-of-building address point | Historic district certain yes | Provisional: older footprint capture |
| 233 S Wacker Dr, Chicago | 66.570 m | Unique county building linked to exact address and current parcel | FEMA certain no; historic result mixed | Provisional: 2022 building footprint |
| 100 N Tampa St, Tampa | 54.930 m | Exact addressed city building | FEMA certain yes | Reviewed automated screen |

The Chicago historic result is the clearest gain: the official building footprint overlaps the West Loop–LaSalle Street Historic District across approximately 24.13% of its area. The original point says no; the property-level screen says mixed and requires review.

The Washington address also shows why a fixed distance tolerance is unsafe. The active DC address point is marked `CENTER OF BUILDING`, yet it is about 164 meters from the Census point used by the public benchmark.

## Source controls

The collector uses official public local services from Miami-Dade County, City of Austin, DC GIS, Cook County, and City of Tampa. Savannah's public parcel layer was queried, but its separate Master Address Database was not copied because the service description says not to distribute it without a data-sharing agreement. A technically accessible endpoint is not automatically publishable evidence. The other receipts are marked as public-endpoint captures whose current terms still require review before redistribution or commercial use; public access is not presented as a blanket license.

The underlying agency services are linked in each JSON receipt under `property_support/records/`. The public collector stores the exact query, unedited response, retrieval time, and SHA-256 digest.

## Blind challenge

The private Massachusetts holdout now has a 100-item challenge with opaque item identifiers, shuffled questions, a strict prediction schema, a salted gold commitment, and an Ed25519 signature. Gold, source receipts, the item map, and the commitment nonce remain owner-only. The public commitment fixes 34 FEMA, 33 historic-district, and 33 EPA proximity questions without exposing them.

The scorer freezes the submission hash before loading gold and checks wrong property, wrong source, unsupported answer, unusable citation, stale evidence, and failure to abstain. Its property check requires the requested and matched official addresses plus a coordinate within 25 meters of the held-out official point. A correct boolean tied to the wrong property is a failure.

The current public OpenAI API run is a real vendor-model baseline, but it is not an external or blind vendor-system evaluation. The dated `gpt-4.1-mini-2025-04-14` model abstained on all 33 closed-book items, producing no critical errors and no accepted answers. The new private challenge is ready for a property or government-AI vendor to run with its actual tools.

## What remains outside the code

NIST's AI RMF Playbook recommends documented test sets and metrics, separate testing teams or independent assessors, and checking that evaluation actors have enough independence and resources. The challenge now supplies the technical separation. It becomes an external result only after an unaffiliated participant submits a frozen prediction file. It becomes independent professional review only if a qualified reviewer examines the evidence and method, can report adverse findings, discloses conflicts, and signs the attestation.

Relevant references:

- [NIST AI RMF Playbook, Measure](https://airc.nist.gov/airmf-resources/playbook/measure/)
- [FGDC geospatial positioning accuracy standard](https://www.fgdc.gov/standards/projects/accuracy/part3/chapter3)
- [City of Tampa Address Point](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/StreetsandAddresses/MapServer/0)
- [City of Tampa Building Footprint](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Location/MapServer/0)
- [DC GIS Address Points](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Location_WebMercator/FeatureServer/0)
- [Cook County Address Points](https://gis.cookcountyil.gov/traditional/rest/services/addressZipCode/MapServer/0)
- [Miami-Dade GeoAddress](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/GeoAddress_gdb/FeatureServer/0)
