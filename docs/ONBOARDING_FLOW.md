# GeoVision customer onboarding flow

GeoVision supports self-service onboarding and service-first onboarding with
one identity and one authorization model. A customer never has to recreate an
Asset or choose a separate account type because GeoVision performed the work
before they joined.

## Self-service onboarding

```text
Register or external identity
  -> User
  -> create Organization and initial Workspace
  -> active owner memberships
  -> create/import Asset
  -> enable entitled modules
  -> acquire, monitor, order, and receive results
```

The client sends `X-Workspace-ID` after selection. Canonical customer routes
resolve and validate organization/workspace memberships before reading or
changing workspace resources. One User may switch among multiple organizations
and workspaces without creating another login. Legacy company-scoped IoT
management endpoints retain their historical tenant boundary during the
compatibility period; customer intelligence and deep links use the canonical
workspace Asset boundary.

## Service-first onboarding

```text
GeoVision creates first-party service/order
  -> Operations creates or links Workspace and Asset
  -> private contractor/staff assignment and Acquisition
  -> Dataset, processing, KPI/Observation/Action, Report
  -> invite intended customer to the existing scope/result
  -> customer authenticates and accepts one-time invitation
  -> memberships become active
  -> invitation notification is claimed by that User
  -> typed invitation link opens the authorized Workspace, Asset, published
     Report, service result, or Order
```

Action links are created separately by recipient-bound action notifications
after onboarding. They are not invitation target types; opening either kind of
link performs a fresh authorization check.

The invitation stores a token digest, expiry, intended email, target type, and
GeoVision IDs. Token-bearing URLs are encrypted only in the pending delivery
payload and never copied into event, inbox, audit, or provider-log text. Replay,
expiry, target tampering, identity mismatch, and cross-tenant acceptance fail
closed.

Opening a notification is a new authorization decision. The server verifies
the recipient, active membership, workspace, required permission, target
ownership, lifecycle, and customer visibility before returning an app and
portal path.

## Customer navigation

The mobile customer surface is Home, Assets, Actions, Services, and More. The
desktop portal can expose deeper contextual navigation from the capability
response. Neither surface invents permissions from hidden UI state.

Internal Operations is separate. Contractors see only their current
assignment, bounded job context, approved files, and permitted transitions.
They cannot enumerate customer memberships, internal pricing/margins,
unassigned jobs, provider credentials, or other contractors.

## Operator checklist

1. Confirm the organization and workspace are the intended customer boundary.
2. Reuse or create the canonical Asset; do not ask the customer to duplicate it.
3. Link the service/order, fulfilment job, assignment, mission, dataset, and
   report using GeoVision IDs.
4. Publish only reviewed customer-visible results.
5. Invite the exact intended email with the narrowest useful target.
6. Confirm acceptance, inbox claim, deep-link resolution, and service/order
   history in the selected workspace.
7. Revoke the invitation or membership immediately if scope or recipient is
   wrong; old links will then fail authorization.
