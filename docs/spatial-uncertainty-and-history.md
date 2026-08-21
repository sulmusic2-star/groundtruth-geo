# Spatial uncertainty, third-engine review and source history

## Why this layer exists

The Census Geocoder says its coordinates are interpolated or approximated from
MAF/TIGER address ranges. They are useful property-location evidence, but they
are not surveyed parcel or building coordinates. A point can therefore be
correctly processed by a spatial service while still being too close to a
mapped decision boundary for an address-level conclusion to be robust.

GroundTruth-Geo now tests that risk directly. This does not assign an assumed
error radius to the Census Geocoder. It asks a narrower, reproducible question:
would the stored answer change if the stored point moved through a declared
matrix?

## Three separated implementations

1. `refresh_evidence.py` obtains the center-point official record and derives
   the gold answer.
2. `replicated_review.py` re-derives the answer from stored raw responses using
   only the Python standard library.
3. `geospatial_review.py` reconstructs stored government geometry with GEOS via
   Shapely and performs geodesic operations with PROJ via PyProj. It imports
   neither earlier implementation.

`collect_spatial_evidence.py` is only a collector. For polygon tasks it requests
all features intersecting a 150-meter envelope and permits at most 0.0000005
degree geometry generalization (about 5.6 cm at the equator). For the EPA task
it collects candidates within 0.35 mile, which is greater than the 0.25-mile
decision radius plus the 100-meter perturbation maximum. A failed source call
blocks the complete capture; it cannot become a negative answer.

The third engine applies Esri's documented even-odd polygon fill rule, clips
large source polygons to the tested neighborhood, checks geometry validity,
uses a boundary-inclusive `covers` predicate, and calculates EPA distances on
the WGS84 ellipsoid. An exact or sub-decimeter mapped boundary contact receives
its own class.

## Perturbation matrix and decisions

Each complete case has 57 positions:

- the stored center;
- radii of 1, 2, 5, 10, 25, 50 and 100 meters; and
- eight bearings at every nonzero radius.

The outcome classes are:

- `stable_through_100m_tested`: no sampled position changed or became
  unresolved;
- `sensitive`: at least one sampled position changed or became unresolved;
- `boundary_contact`: the center is within 0.10 meter of the reconstructed
  mapped decision boundary; and
- `geometry_unavailable`: geometry cannot support a center derivation.

The primary class uses unavailable, boundary-contact, sensitive, then stable
precedence. Every applicable flag is also retained, so a case can be both
boundary-contact and sensitive without either fact being hidden.

Stable means only stable at the declared 57 positions. It is not a survey,
parcel determination, probability estimate, or proof that every point inside a
100-meter circle has the same answer. Sensitive does not mean the stored center
answer is wrong. It means the answer should be shown with stronger location
evidence, abstention, or qualified review rather than ordinary confidence.

## Observed August 21, 2026 result

| Collection | Center cases passed | Perturbation samples | Stable | Sensitive | Unresolved samples |
|---|---:|---:|---:|---:|---:|
| Public | 33/33 | 1,881 | 26 | 7 | 0 |
| Private Massachusetts | 100/100 | 5,700 | 77 | 23 | 0 |

The public report and receipt are in `proof/`. The private detailed report is
mode `0600` in the private holdout workspace; the public receipt contains only
aggregate counts and a digest.

These are stratified benchmark results, not Massachusetts or U.S. field
accuracy estimates. The three implementations are controlled by the same
project owner and may share conceptual assumptions. They are not independent
human or professional review.

## Historical source-change corpus

`source_history.py` records separate digests for:

- the stored answer;
- property identity;
- official qualifying records;
- neighborhood feature attributes;
- geometry;
- raw evidence bytes; and
- layer schema and raw metadata.

It classifies changes in priority order as classification, property identity,
geometry, record, metadata-only, unavailable, added/removed, or unchanged.
Snapshots link to the previous manifest by SHA-256 and model entity, activity,
agent and revision concepts from W3C PROV.

Two real August 21 captures, eight minutes apart, seed the history. Their replay
found all 33 case-level classifications, identities, records and geometries
unchanged; FEMA and NPS layer metadata changed without a schema or case-level
semantic change. This short replay proves the diff mechanism on live captures,
not long-term stability or a historical change rate. The synthetic corpus in
`tests/fixtures/source_change_corpus.json` proves only that every change class
is detected correctly; it is explicitly not evidence that a government source
made those edits. A later live capture is required for the first real temporal
comparison across a meaningful time interval.

## Primary technical references

- [Census Geocoder documentation](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html)
- [ArcGIS REST query operation](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/)
- [ArcGIS REST geometry objects and ring rules](https://developers.arcgis.com/rest/services-reference/enterprise/geometry-objects/)
- [OGC Simple Features Access](https://www.ogc.org/standards/sfa/)
- [Shapely predicates](https://shapely.readthedocs.io/en/stable/predicates.html)
- [PyProj geodesic API](https://pyproj4.github.io/pyproj/stable/api/geod.html)
- [FGDC National Standard for Spatial Data Accuracy](https://www.fgdc.gov/standards/projects/accuracy/part3/chapter3)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [FEMA Flood Risk Analysis and Mapping standards](https://www.fema.gov/sites/default/files/documents/fema_rm-flood-risk-analysis-mapping-policy-rev14.pdf)
