# GeoVision permissions matrix

`backend/app/modules/organizations/domain.py` is the executable authority for
role-to-permission mappings. Membership must also be active and in the selected
organization/workspace. `platform:admin` satisfies any permission check; no
other role is an implicit wildcard.

## Customer roles

The persisted role values are `viewer`, `member`, `finance`, `manager`,
`admin`, and `owner`.

| Permission | Viewer | Member | Finance | Manager | Admin | Owner |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `organization:read` | Yes | Yes | Yes | Yes | Yes | Yes |
| `organization:manage` | No | No | No | No | Yes | Yes |
| `organization:manage_members` | No | No | No | No | Yes | Yes |
| `organization:transfer_ownership` | No | No | No | No | No | Yes |
| `workspace:read` | Yes | Yes | Yes | Yes | Yes | Yes |
| `workspace:contribute` | No | Yes | No | Yes | Yes | Yes |
| `workspace:operate` | No | No | No | Yes | Yes | Yes |
| `workspace:manage` | No | No | No | Yes | Yes | Yes |
| `asset:read` | Yes | Yes | Yes | Yes | Yes | Yes |
| `asset:create` | No | Yes | No | Yes | Yes | Yes |
| `asset:update` | No | Yes | No | Yes | Yes | Yes |
| `asset:archive` | No | No | No | Yes | Yes | Yes |
| `report:read` | Yes | Yes | Yes | Yes | Yes | Yes |
| `billing:read` | No | No | Yes | No | Yes | Yes |
| `billing:manage` | No | No | Yes | No | Yes | Yes |

Unknown historical customer roles fail closed. Compatibility aliases map
`operator` to manager and `client`, `cliente`, or `customer` to member.

## Internal GeoVision roles

| Internal role | Exact permissions |
|---|---|
| `GV_SUPER_ADMIN` | `platform:admin`, `operations:access`, `support:access`, `analytics:review`, `billing:internal`, `inventory:internal`, `sales:internal`, `report:read`, `report:generate`, `report:review`, `report:publish` |
| `GV_OPERATIONS` | `operations:access`, `report:read`, `report:generate` |
| `GV_ANALYST` | `analytics:review`, `report:read`, `report:generate`, `report:review`, `report:publish` |
| `GV_SUPPORT` | `support:access` |
| `GV_FINANCE` | `billing:internal` |
| `GV_INVENTORY` | `inventory:internal` |
| `GV_SALES` | `sales:internal` |

Internal roles live only in internal role assignments. They are never written
to customer membership rows or exposed as public contractor/seller identities.

## Canonical customer-route enforcement sequence

```text
valid token
  -> active User
  -> active organization membership
  -> active selected workspace membership
  -> effective customer plus internal permissions
  -> module entitlement / rollout gate where applicable
  -> tenant-filtered resource lookup
  -> lifecycle and optimistic-version guard for mutation
```

An inaccessible tenant resource should normally return a non-disclosing 404.
Notification deep links repeat the scope and target checks at open time, so an
old inbox row cannot preserve access after membership revocation. Legacy
mobile drone compatibility routes enforce selected-Workspace Asset access and
the read, contribute, or operate permission appropriate to each action. Legacy
company-scoped IoT fleet-management routes are the documented compatibility
exception; their customer-facing KPI/observation/action projection and deep
links are workspace-scoped.
