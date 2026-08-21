# GroundTruth-Geo evidence contract

This contract defines what a public gold answer must contain before it can be
scored as verified. It applies to the 33 public example cases. Private test
cases follow the same contract but are not stored in this public repository.

## Required evidence

Every case must include:

1. the address that was asked;
2. the address returned by an official geocoder, with coordinates;
3. the exact official query URL used for the answer;
4. the unedited JSON returned by that query;
5. the retrieval time in UTC;
6. a SHA-256 digest of each official response;
7. a written, machine-checkable rule that turns the source record into the
   gold answer; and
8. an explicit review state.

A general agency home page is not record-level evidence. A current-looking
label is not evidence of a current check. A negative answer is valid only when
the official query completed successfully and returned zero qualifying records.

## Property identity

The benchmark uses the United States Census Geocoder as its default property
identity check. A case fails closed when the geocoder returns no match or a
different property. A reviewed landmark alias may be used only when an official
government page independently identifies the requested address and the alias is
listed in the refresh code.

## Public task rules

### FEMA Special Flood Hazard Area

- Official source: FEMA National Flood Hazard Layer, Flood Hazard Zones.
- Spatial rule: the geocoded point must intersect exactly one effective flood
  hazard polygon.
- Gold rule: `in_sfha` is true only when FEMA's `SFHA_TF` field is `T`.
- The FEMA zone is copied from `FLD_ZONE`.

This is a point-in-polygon screen. It is not a parcel survey, elevation
certificate, lender determination, or Letter of Map Change review.

### National Register historic district

- Official source: National Park Service National Register polygon service.
- Spatial rule: query all polygons intersecting the geocoded point.
- Gold rule: include only records whose `ResType` is `district` and whose
  `STATUS` is `Listed`.

Buildings, objects, sites and structures do not count as historic districts.
The task does not claim complete state or local historic-district coverage.

### Federal cleanup site nearby

- Official source: EPA Envirofacts map service, Superfund and Brownfields
  layers.
- Spatial rule: query both layers within 0.25 statute mile of the geocoded
  point.
- Gold rule: count unique returned program records across the two layers.

The radius and included programs are part of the question. The task does not
claim to include every state cleanup program or every regulated facility.

## Review states

- `verified`: the identity and official record queries passed and the stored
  answer was derived by the documented rule.
- `blocked`: identity or source evidence is incomplete, ambiguous or failed.
- `superseded`: a newer reviewed case replaced this one.

Automated verification is not independent review. Public documentation must
say so until a qualified external reviewer has signed the audit manifest.

## Coordinate sensitivity

Center-point verification and coordinate sensitivity are separate gates. The
third GEOS/PROJ implementation must reproduce the center answer before a case
can pass. Its 57-position perturbation matrix then labels the case as stable
through the tested positions, sensitive, boundary-contact, or unavailable.

A sensitive result does not invalidate the stored center answer. It prevents
the system from presenting that answer with ordinary confidence when a small
change in the approximate geocoded coordinate changes the official spatial
result. Sensitive, boundary-contact and unavailable cases require abstention,
stronger property-location evidence, or qualified review.

Stronger property-location evidence is stored as a separate support record; it
never silently replaces the original point task. An official property support
requires one exact local address result linked to one public building footprint
or parcel. Address, geometry, currency, and redistribution eligibility are
checked separately. Whole-property review returns `certain_yes`, `certain_no`
or `mixed`; it does not force a binary answer when a decision boundary crosses
the building or parcel.

The primary class uses this precedence: `geometry_unavailable`,
`boundary_contact`, `sensitive`, then `stable_through_100m_tested`. The report
also stores every applicable flag, so a boundary-contact case that changes
under perturbation retains both `boundary_contact` and `sensitive`; primary
class precedence never erases the overlapping risk.
