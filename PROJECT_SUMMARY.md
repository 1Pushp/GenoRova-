# Project Summary

## One-Line Summary

Genorova is a prototype AI-assisted computational molecule analysis platform that helps users score, explain, compare, and review candidate molecules through a chat-style interface.

## Short Paragraph Summary

I built Genorova as an end-to-end prototype that combines a molecule-analysis backend, a chat-first frontend, scoring and comparison workflows, and an evaluation pipeline for generative model quality. The current product is presentation-ready as a research-support tool: it can score valid SMILES strings, explain molecular properties, compare candidates, and handle weak generation honestly through trust messaging and fallback behavior. The generative model itself is still under active improvement, and the project is positioned transparently around computational support rather than experimental validation.

## Key Highlights

- Built a chat-based computational molecule analysis product with structured backend responses and scientific trust messaging
- Added scoring, explanation, comparison, rendering, and safe fallback workflows for demo-safe usage
- Created a baseline reliability suite with pytest to protect active training, API, chat, and rendering paths
- Built a generation evaluation workflow that measures validity, uniqueness, novelty, and checkpoint quality
- Diagnosed major generation blockers honestly, including vocab mismatch risk, decoding problems, and weak checkpoint quality

## Honest Limitation Note

The biggest current limitation is de novo generation quality: recent checkpoint comparisons showed essentially 0% RDKit-valid molecules in the evaluated seeded runs, so the project should not yet be presented as a reliable molecule generator.

## Current Status Note

Current status: presentation-ready prototype / research-support tool, with strong product framing and honest limitation handling, but not yet ready to claim robust generative performance or scientific validation.
