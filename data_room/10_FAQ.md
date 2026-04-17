# GenorovaAI - FAQ

Date: April 17, 2026

## What is GenorovaAI today?

GenorovaAI is a prototype computational research-support platform for molecule
scoring, explanation, comparison, and authenticated chat-based analysis.

## What is the strongest part of the product right now?

The strongest current workflows are scoring known molecules, explaining outputs,
comparing candidates, and demonstrating responsible trust boundaries in a real
web product.

## Is GenorovaAI experimentally validated?

No. This room does not present GenorovaAI as experimentally validated. Outputs
are computational only unless explicitly reproduced outside the platform.

## Is GenorovaAI clinically validated?

No. Nothing in the current product should be interpreted as clinical
validation, clinical recommendation, or evidence of patient benefit.

## Does the platform have real authentication?

Yes. The current product includes signup, login, logout, `/auth/me`, and
cookie-backed sessions for a protected workspace.

## Is the app multi-user?

It now has a real multi-user foundation through authenticated accounts and
protected sessions. It is still early-stage, and long-term user-bound history
and broader SaaS account features are not yet fully built out.

## Is molecule generation solved?

No. The generation pipeline exists, but recent project status notes still show
that generation validity is the main technical weakness. The product should not
currently be sold as a reliable de novo generator.

## Are the scores model predictions or measured lab results?

They are computational outputs. Some fields are exact descriptor calculations,
while others are heuristic or proxy signals. They are not wet-lab measurements.

## What is actually deployed?

The configured deployment path is a FastAPI service in `genorova/src/api.py`
that builds and serves the React frontend from `app/frontend`.

## Why does this room avoid stronger scientific claims?

Because older repo materials are not perfectly consistent. This room uses the
most conservative, current, evidence-backed story rather than the most
ambitious one.

## What remains before GenorovaAI is investor- or pilot-ready?

- cleaner scientific evidence packaging
- stronger generation benchmarks
- more durable user history and report storage
- monitoring and operational hardening
- billing and quota controls

## What is the right way to evaluate GenorovaAI today?

Evaluate it as a software and product foundation for computational
research-support workflows, not as a solved drug-discovery platform.
