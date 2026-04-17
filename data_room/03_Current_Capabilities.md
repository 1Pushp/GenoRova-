# GenorovaAI - Current Capabilities

Date: April 17, 2026

## Complete Today

Product and access:

- one canonical frontend experience launches through `App.jsx`
- authenticated signup, login, logout, and current-user bootstrap
- protected workspace access for the chat flow

Computational workflows:

- score valid SMILES strings
- explain molecules in plain language or technical framing
- compare molecules and discuss property tradeoffs
- present platform stats and trust boundaries in-product
- serve an HTML report surface

Quality and reliability:

- baseline automated tests are passing
- frontend production build is passing
- trust messaging is aligned to research-support rather than clinical claims

## Partial Today

Generation:

- generation routes and pipeline exist
- fallback behavior is safer than before
- generation quality is still not strong enough for confident de novo claims

User continuity:

- auth sessions persist across refresh
- protected chat is tied to an authenticated user
- long-lived, user-facing conversation history and reporting by account are not
  yet fully productized

Scientific workflows:

- validation endpoints exist
- some outputs are exact descriptor calculations
- several outputs remain heuristic or proxy signals and must not be framed as
  experimental results

## Pending

SaaS/commercial:

- billing and subscriptions
- usage metering and quotas
- mature account settings and billing surfaces

Operations:

- monitoring and alerting
- backup and restore procedures
- public uptime verification and incident handling

Scientific maturity:

- repeatable non-trivial generation validity
- stronger benchmark reporting
- external docking confirmation where claimed
- wet-lab validation

## Safest Current Use Cases

- score a known molecule
- explain computed properties and caveats
- compare two known molecules
- demonstrate responsible trust messaging
- show authenticated access to a protected research workspace

## Workflows To Avoid Overstating

Do not currently present GenorovaAI as:

- a reliable de novo molecule generator
- a platform that has experimentally confirmed candidates
- a clinical or medicinal recommendation engine
- a production-hardened biotech SaaS
