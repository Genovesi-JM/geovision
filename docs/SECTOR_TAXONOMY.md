# GeoVision canonical sector taxonomy

Phase 34 defines one ordered six-sector vocabulary for the public website,
onboarding, account profiles, mobile clients, catalogue filters, KPI responses,
Assets, sector modules, fixtures, and release evidence. Customer-facing code
uses the public identifier; shared operational records use the technical Asset
sector. These are related values, not interchangeable strings.

## Canonical registry

The order below is the presentation order everywhere. Portuguese labels and
marketing anchors are exact product copy and must not be independently renamed
by a client.

| Order | Public ID | Portuguese label | Marketing anchor | Technical Asset sector | Capability module | Capability discovery |
|---:|---|---|---|---|---|---|
| 1 | `agriculture` | Agricultura & Pecuária | `#agricultura-pecuaria` | `AGRICULTURE` | `agriculture` | `GET /sectors/agriculture/capabilities` |
| 2 | `construction_infrastructure` | Construção & Infraestruturas | `#construcao-infraestruturas` | `INFRASTRUCTURE` | `infrastructure` | `GET /sectors/infrastructure/capabilities` |
| 3 | `environment` | Ambiente | `#ambiente` | `ENVIRONMENTAL` | `environmental` | `GET /sectors/environmental/capabilities` |
| 4 | `mining` | Mineração | `#mineracao` | `MINING` | `mining` | `GET /sectors/mining/capabilities` |
| 5 | `industry_energy_utilities` | Indústria, Energia & Utilities | `#industria-energia-utilities` | `INDUSTRY_ENERGY_UTILITIES` | `industry_energy_utilities` | `GET /sectors/industry-energy-utilities/capabilities` |
| 6 | `ports_logistics` | Portos & Logística | `#portos-logistica` | `PORTS_LOGISTICS` | `ports_logistics` | `GET /sectors/ports-logistics/capabilities` |

The canonical marketing page is `sectors.html`; deployments may expose it as
`/sectors`. The anchor slugs are navigation fragments, not API identifiers.
The public IDs are used by account/site selection, KPI and catalogue responses,
and client preferences. Uppercase values belong to the generic Asset, Dataset,
KPI-definition, and other technical evidence records. Capability-module names
select backend packages and rollout keys.

Construction and infrastructure form one public sector. Agriculture and
livestock form one public sector. Mining remains distinct from industry, and
Portos & Logística remains distinct from Indústria, Energia & Utilities.

## Maturity and evidence

The label on the public page describes commercial maturity; it does not claim
that a provider is connected or that a KPI has scientific, engineering, safety,
navigation, or compliance authority.

| Public ID | Public maturity | Implemented evidence boundary |
|---|---|---|
| `agriculture` | Available by configuration | Activated source-fused Agriculture package, map/report context, and cautious rules. Crop, season, sensor, and regional applicability still require Gate 14a approval. |
| `construction_infrastructure` | Custom projects | Activated infrastructure package with progress, comparisons, maps, reports, and synthetic fixtures. Project evidence and engineering interpretation remain review-gated. |
| `environment` | Custom projects | Activated environmental package with comparisons, maps, reports, and provenance-preserving evidence. Environmental conclusions require accountable specialist review. |
| `mining` | Specialized applications | Activated mining package with repeatable evidence workflows. It must not infer geotechnical, extraction, or safety conclusions from absent or weak data. |
| `industry_energy_utilities` | Expanding | Phase 34 capability package and source-dependent operational KPI catalogue. Missing sources remain unavailable; equipment, energy, engineering, compliance, and control claims require separate validated evidence and authorization. |
| `ports_logistics` | Expanding | Activated port/logistics inspection, comparison, map, report, and IoT evidence workflow. Maritime data is supplementary context only and remains provider/licence-gated. |

All customer-visible KPIs must carry their canonical public ID. A sector being
enabled does not permit synthetic healthy values, invented measurements, or an
automatic operational recommendation. Missing or weak evidence stays
`NO_DATA`, `UNKNOWN`, or review-required under the shared intelligence rules.

## Compatibility aliases

Aliases are accepted at input boundaries only. APIs and newly written records
return or persist the canonical value.

| Legacy input | Canonical public ID |
|---|---|
| `agro`, `agropecuaria`, `agriculture_livestock`, `livestock` | `agriculture` |
| `construction`, `construction_and_infrastructure`, `infrastructure` | `construction_infrastructure` |
| `ambiental`, `environmental` | `environment` |
| `mine`, `mines`, `quarry` | `mining` |
| `industry`, `industrial`, `energy`, `industry_energy`, `solar`, `utilities` | `industry_energy_utilities` |
| `port`, `ports`, `portos`, `logistics`, `ports_and_logistics`, `ports_industrial` | `ports_logistics` |

The six exact Portuguese labels, their accent-free variants joined with `_`,
and the marketing slugs in the registry are also accepted at input boundaries.
This includes the comma-bearing label `Indústria, Energia & Utilities`, which
must be recognized as one value before a comma-separated sector list is split.
Only explicitly registered comma-bearing labels are joined; unknown extension
values and punctuation remain visible for rejection or manual review rather
than being swallowed by a partial alias match. Public write payloads are bounded
to six selections.

Technical compatibility normalization follows the same separation:

- `AGRO`, `AGRICULTURE_LIVESTOCK`, and `LIVESTOCK` become `AGRICULTURE`;
- `CONSTRUCTION`, `CONSTRUCTION_AND_INFRASTRUCTURE`, and
  `CONSTRUCTION_INFRASTRUCTURE` become `INFRASTRUCTURE`;
- `ENVIRONMENT` and `AMBIENTAL` become `ENVIRONMENTAL`;
- `QUARRY` becomes `MINING`;
- `INDUSTRY`, `INDUSTRIAL`, `INDUSTRY_ENERGY`, `ENERGY`, `SOLAR`, and
  `UTILITIES` become `INDUSTRY_ENERGY_UTILITIES`;
- `PORT`, `PORTS`, `LOGISTICS`, `PORTS_AND_LOGISTICS`, and
  `PORTS_INDUSTRIAL` become `PORTS_LOGISTICS`.

The historical capability paths under `/sectors/industry` and
`/sectors/ports`, and the historical per-Asset `/ports/*` paths, remain hidden
compatibility aliases during client cutover. New clients use the canonical
paths in the registry above and `/assets/{asset_id}/ports-logistics/*`.
Infrastructure and environmental package names remain technical names; they do
not replace their public IDs.

Historical database IDs, catalogue product IDs/slugs, deterministic fixture
IDs, package directories, test filenames, and serialized audit references may
retain an old token when changing it would break identity or traceability. They
are internal compatibility references: customer labels, sector filters,
responses, and all new sector fields still use the six canonical values.

## Rollout and workspace configuration

The logical rollout identities follow capability-module names. Effective keys
are:

```text
geovision.sectors.agriculture
geovision.sectors.infrastructure
geovision.sectors.environmental
geovision.sectors.mining
geovision.sectors.industry_energy_utilities
geovision.sectors.ports
```

`ports_logistics` deliberately resolves through the deployed compatibility key
`geovision.sectors.ports`. A later change to
`geovision.sectors.ports_logistics` needs a dual-read or external flag migration
with measured rollout evidence; Phase 34 does not silently rename the remote
control-plane key.

Rollout is only a deny/allow decision layered over current membership,
Workspace status, module entitlement, and role permissions. It cannot grant a
capability that those checks deny. Legacy Workspace module names may be read
during migration, but newly written module lists use canonical capability-module
names.

Workspace experience responses expose both `sector` and `sectors`. The
historical singular field is a compatibility projection containing the first
canonical public ID only; `sectors` is the ordered, de-duplicated complete
selection. A comma-separated selection is never returned as if it were one
sector identifier. New web and mobile clients use `sectors` for display and
retain `sector` only where a primary context is required.

## Persistence migration and release rules

The additive `phase34_sector_taxonomy_v1` migration normalizes known persisted
public and technical aliases without deleting records, rewriting unknown
extension values, or guessing ambiguous tenant scope. Its release expectations
are:

1. normalize account, company, site, catalogue, Asset, Dataset, KPI-definition,
   fixture, and module-selection values where their meaning is known;
2. normalize the historical `PORTS_INDUSTRIAL` compatibility value to
   `PORTS_LOGISTICS`, while explicit industrial/energy/utilities evidence uses
   `INDUSTRY_ENERGY_UTILITIES`; do not guess that an ambiguous historical row
   belongs to Industry/Energy/Utilities;
3. never normalize `mining` to industry or combine ports/logistics with
   industrial/energy/utilities on a new write;
4. retain read aliases and hidden HTTP aliases until web, mobile, stored data,
   and external consumers have cut over;
5. rehearse upgrade, downgrade, and re-upgrade against a production-like copy,
   then verify record counts, tenant ownership, canonical values, one Alembic
   head, and the exact release digest.

Downgrade compatibility must preserve data even when an older application can
only understand a broader legacy label. Removing an alias requires measured
usage evidence and a separately reviewed release; Phase 34 does not authorize
destructive cleanup.

## Change discipline

`backend/app/sector_taxonomy.py` is the backend source of truth. Browser and
Flutter registries must mirror it through contract tests. Any future sector
change updates, in the same phase, the registry order, labels and anchors,
account/onboarding choices, mobile representation, catalogue filters, KPI
routing, Asset normalization, demo fixtures, rollout mapping, documentation,
and cross-surface tests.
