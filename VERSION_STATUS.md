# Version Status

## What Genorova Is

Genorova is currently a prototype computational molecule analysis and research-support system. It combines:
- a chat-style product interface
- property scoring and molecule explanation
- comparison and follow-up analysis
- a generative model pipeline that is still under active stabilization

It is not a validated drug-discovery engine, not a docking-backed decision system, and not a clinical recommendation tool.

## What Is Working Now

- FastAPI backend with active `/api/chat`, `/api/score`, `/api/stats`, and safe `/generate` flows
- Chat interface with session memory, structured molecule cards, and inline trust messaging
- Molecule scoring for valid SMILES strings using the current Genorova ranking logic and RDKit-derived properties
- Molecule explanation, comparison, and follow-up prompts that are demo-safe
- Safe fallback behavior when fresh generation is weak or unavailable
- Baseline pytest suite covering data loading, preprocessing, API behavior, chat behavior, rendering, and training smoke paths
- Generation evaluation workflow with checkpoint comparison, ranking artifacts, and debugging outputs

## What Is Partially Working

- Ranked molecule retrieval for demos
  - This works reliably when using previously scored valid molecules, database rows, or known reference fallbacks.
- Runtime generation path
  - Checkpoint/vocab mismatch risk has been reduced with stricter loading checks.
  - The path is safer, but molecule quality is still poor.
- Product demo flow
  - Strong for scoring, explanation, and comparison.
  - Weak for claiming fresh de novo generation quality.

## What Is Not Yet Solved

- De novo generation quality is not yet reliable.
- Day 5 evaluation showed essentially 0% RDKit-valid molecules across the compared checkpoints in the seeded comparison.
- The likely causes are already diagnosed but not yet fixed:
  - missing BOS/EOS handling
  - malformed decoding behavior
  - repetitive token streams
  - train/inference mismatch
  - weak stage checkpoints

## Current Maturity Level

Current maturity: prototype / research-support tool

Best framing today:
- useful for computational molecule scoring and explanation
- useful for demos of safe scientific UX and product thinking
- not ready to claim reliable generative performance
- not production-ready for pharma or regulated use

## Scientific Limitations

- Outputs are computational only and not experimentally validated.
- Current "model score" is an internal ranking signal, not proof of efficacy or safety.
- The active product should not be used to imply docking confirmation, biological activity, or clinical readiness.
- Fresh generation results should be treated cautiously until validity improves materially.

## Demo-Safe Use Cases

- Score a known SMILES string
- Explain a molecule in simple or scientific language
- Compare two molecules and discuss property tradeoffs
- Review previously scored valid molecules
- Show trust messaging, fallback behavior, and scientific responsibility in the UI

## Current Safest Product Workflows

1. Start in chat with a known molecule or simple prompt.
2. Use scoring to show properties, model ranking, and caveats.
3. Use explanation and comparison to show reasoning and follow-up support.
4. If generation is requested, present fallback results honestly and explain the current limitation.

## Current Bottom Line

Genorova is ready to demo as an honest, presentation-ready computational molecule analysis prototype. It is not yet ready to demo as a strong de novo molecule generator.
