# Feature: Household Management (Household Context)

**Parent shape:** [personal-finance](../../ideas/personal-finance/SHAPE.md)
**Bounded context:** Household (supporting subdomain)
**Package:** `internal/household/`

## User Outcome

Users can create households, invite members by email, assign roles (owner/admin/member/viewer), and switch between personal and household contexts. Solo users have zero overhead — household UI only appears after creating/joining one.

## Scope

### Domain Layer (`internal/household/domain/household/`)
- **Household aggregate root**: id, name, default_currency, created_by, members[]
  - **Invariants**: exactly one owner, max 10 members, owner cannot be removed, no duplicate invites
- **Member child entity**: id, user_id, role, status (active/invited/removed)
- **Role value object**: owner, admin, member, viewer — with permission matrix
- **Invitation separate aggregate**: id, household_id, invited_email, token, expires_at, status (pending/accepted/expired/revoked)

### Application Layer (`internal/household/app/command/`)
- **CreateHousehold**: create with current user as owner
- **InviteMember**: generate token, create invitation, emit MemberInvited
- **AcceptInvitation**: validate token, add member, emit MemberAccepted
- **ChangeMemberRole**: enforce role transition rules
- **RemoveMember**: soft remove, emit MemberRemoved
- **TransferOwnership**: owner-only

### Middleware (`internal/common/`)
- **HouseholdContext middleware**: reads X-Household-ID header, verifies membership, injects HouseholdContext (household_id, user_id, role, is_personal) into request context
- **Permission check**: HasPermission(ctx, action) verifies role permissions

### Domain Events
- `HouseholdCreated` — seed default categories
- `MemberInvited` — trigger email notification
- `MemberAccepted` — seed personal categories for new member, update household member count
- `MemberRemoved` — anonymize attribution to "Former Member"
- `RoleChanged` — audit log

### Database Migrations
- `households`, `household_members`, `household_invitations` tables
- `audit_log` table for shared action tracking

## Dependencies

- `auth-user-management` — requires authenticated user context and UserRegistered event

## Risks

- Permission model complexity (4 roles × 15+ actions)
- Invitation flow edge cases (expired tokens, existing vs new users)
- Every downstream feature must use HouseholdContext middleware
- Household aggregate invariants (exactly one owner) must be enforced at domain level

## Handoff Summary

Implement internal/household/ bounded context per DDD structure. Household aggregate root with Members as child entities, Role value object, domain invariants. Invitation as separate aggregate with token lifecycle. All command handlers. PostgreSQL repos with scope-aware queries. HouseholdContext middleware. Permission enforcement via rolePermissions map. Audit log table + async event handler. Emit domain events (MemberAccepted triggers cross-context category seeding). Next.js: household switcher, invitation flow, member management.

---
*Materialized from shape: 2026-03-20*
