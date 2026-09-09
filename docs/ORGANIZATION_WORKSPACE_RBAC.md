# Organization, workspace, and RBAC boundary

Phase 4 establishes one GeoVision identity across any number of customer
organizations and workspaces. Authorization is evaluated from persisted
memberships on every request; an email address is contact/invitation metadata,
not an authorization key.

## Canonical model and compatibility names

The existing production tables remain in place to avoid destructive renames:

| Canonical concept | SQLAlchemy compatibility class | Existing table |
| --- | --- | --- |
| Organization | `Company` (`Organization` alias) | `companies` |
| Workspace | `Account` (`Workspace` alias) | `accounts` |
| Organization membership | `CompanyUser` (`OrganizationMembership` alias) | `company_users` |
| Workspace membership | `AccountMember` (`WorkspaceMembership` alias) | `account_members` |

Every workspace now has a required `organization_id`. Organizations contain
the customer/legal boundary and carry name, type, country, IANA timezone,
status, and timestamps. Workspaces are operational subdivisions and carry the
existing sector/profile/module configuration plus their own lifecycle status.

The `organization_rbac_v1` migration links existing accounts to the company of
their onboarding owner or earliest owner membership. If no compatible company
exists, it creates a deterministic organization without removing or rewriting
the account. It then materializes missing organization memberships for current
workspace users. Existing admin users receive a separate
`GV_SUPER_ADMIN` assignment. The migration supports downgrade/re-upgrade and
never authorizes a runtime request by matching email.

## Customer roles

Roles are lowercase in the API/database to preserve existing clients. They map
to the product roles OWNER, ADMIN, MANAGER, MEMBER, VIEWER, and FINANCE.

| Role | Read | Contribute/operate | Manage workspaces | Manage members | Billing | Ownership transfer |
| --- | --- | --- | --- | --- | --- | --- |
| `owner` | Yes | Yes | Yes | Yes | Yes | Yes |
| `admin` | Yes | Yes | Yes | Yes | Yes | No |
| `manager` | Yes | Yes | Yes | No | No | No |
| `member` | Yes | Contribute | No | No | No | No |
| `viewer` | Yes | No | No | No | No | No |
| `finance` | Yes | No | No | No | Yes | No |

Unknown historical customer roles fail closed. The migration maps `operator`
to `manager`, `client`/`cliente`/`customer` to `member`, and other unknown
values to `viewer`. An organization must always retain at least one active
owner. Organization role/status changes propagate to its workspace membership
rows so legacy endpoints enforce the same result.

Membership lifecycle values are `invited`, `active`, `suspended`, and
`revoked`. Pending email invitations have no `user_id` and cannot authorize
access. The Phase 6 invitation service stores only a one-time token digest and
binds the membership to the matching authenticated identity at acceptance; see
`docs/INVITATION_ONBOARDING_DEEP_LINKS.md`.

## Internal GeoVision roles

Internal roles are stored only in `internal_role_assignments`, never in
customer membership rows:

- `GV_SUPER_ADMIN`
- `GV_OPERATIONS`
- `GV_ANALYST`
- `GV_SUPPORT`
- `GV_FINANCE`
- `GV_INVENTORY`
- `GV_SALES`

The legacy `users.role = admin` value is a temporary authorization bridge and
is backfilled to `GV_SUPER_ADMIN`. New staff permissions must be assigned in
the internal-role table. Internal roles appear in the normalized authorization
context but not in the customer organization list. The internal Operations UI
remains a separate permission surface.

## Request context and server enforcement

Clients select a workspace per request with `X-Workspace-ID`. The historical
`X-Account-ID` header remains an alias during migration. Supplying both with
different values is rejected. Selection is intentionally stateless: the
server verifies the membership each time and returns a normalized context:

- immutable `user_id` and `identity_subject`;
- active workspace and organization IDs;
- customer workspace/organization roles;
- separate internal roles;
- effective permissions.

The current user's earliest active workspace is used only when no selection is
sent. Organization/company services read the already-validated context, so IoT
and other compatibility endpoints follow the selected organization instead of
silently choosing the first company. A requested workspace outside the user's
membership returns an authorization failure, and customer organization routes
return a non-enumerating not-found response for inaccessible organizations.

Canonical endpoints are under `/organizations`:

- list/create organizations and their initial workspace;
- read the caller's organization and membership;
- list/create workspaces subject to permission;
- list/add/invite/update/revoke members subject to permission;
- read or validate/select a workspace context.

The existing `/accounts`, `/me`, admin-company, and `X-Account-ID` contracts
remain available as compatibility surfaces. New `/accounts` creation also
creates a canonical organization and owner membership.

## Operational cutover

1. Back up the database and pause membership/account writes.
2. Run `alembic upgrade head`; the migration performs its data backfill online.
3. Confirm every account has a non-null organization and review deterministic
   fallback organizations whose contact address ends in
   `@invalid.geovision.local`.
4. Review migrated role mappings and the active-owner count for every
   organization.
5. Verify a multi-workspace user can select each workspace and cannot select a
   workspace outside their memberships.
6. Resume writes and monitor authorization failures. Keep the legacy header and
   class/table aliases until all deployed clients use canonical vocabulary.

Rollback removes the new links/lifecycle columns and internal-role table but
does not delete deterministic organizations or memberships created during the
backfill; retaining those rows is safer than deleting customer data.
