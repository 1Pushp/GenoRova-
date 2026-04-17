# GenorovaAI - Scientific Limitations

Date: April 17, 2026

## Standard Scientific Position

GenorovaAI is a computational research-support platform. It produces a mixture
of exact descriptor calculations, heuristic rankings, and proxy signals. It
does not currently provide experimental proof or clinical validation.

## Outputs That Are Straightforward To Trust

These are standard computational calculations when the input SMILES is valid:

- RDKit parsing validity
- molecular weight
- LogP
- QED
- SA score
- hydrogen-bond donor and acceptor counts
- similarity calculations under a fixed fingerprint definition

## Outputs That Must Be Labeled Conservatively

These are useful for screening and discussion, but should not be framed as
validated scientific conclusions:

- model score or ranking score
- toxicity or safety heuristics
- proxy confidence statements
- scaffold-similarity binding proxies
- any generation-time quality impression from fallback outputs

## Current Generation Limitation

The most important technical weakness remains generation quality.

Current project status documents record that a recent checkpoint comparison
showed essentially `0%` RDKit-valid molecules in the seeded evaluation run used
for that review. That makes one point clear:

- the generation pipeline exists
- it is not yet supportable to present GenorovaAI as a reliable de novo
  molecule generator

## Docking And Validation Limits

This room deliberately avoids making strong docking claims because older repo
artifacts are not fully consistent with each other. The conservative position
is:

- validation endpoints and computational scoring layers exist
- some older reports describe docking-backed conclusions too strongly
- docking, when discussed at all, should be treated as computational support
  only unless independently reproduced and documented cleanly

## Novelty And Patentability Limits

This room does not claim that GenorovaAI has already discovered a novel,
patentable lead compound. Older repo artifacts include known-compound matches,
which means:

- novelty must be checked carefully and consistently
- a known compound cannot be presented as a novel discovery
- patentability is outside the scope of the current platform

## What Is Required Before Stronger Scientific Claims

- cleaner benchmark reporting
- repeatable generation validity improvements
- explicit separation of exact calculations vs heuristic estimates
- reproducible docking or external computational confirmation where relevant
- wet-lab validation before any efficacy or safety claim

## Bottom Line

GenorovaAI is appropriate today for computational analysis, prioritization, and
discussion support. It is not appropriate today for claims of experimental
validation, clinical readiness, or validated novel-drug discovery.
