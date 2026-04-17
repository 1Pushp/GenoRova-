# Project Summary

## One-Line Summary

Genorova is a prototype AI-assisted computational molecule analysis platform that helps users score, explain, compare, and review candidate molecules through a chat-style interface.

## Short Paragraph Summary

I built Genorova as an end-to-end prototype that combines a molecule-analysis backend, a chat-first frontend, ranking and comparison workflows, and an evaluation pipeline for generative model quality. The current product is demo-ready as a research-support tool: it can rank candidates, score valid SMILES strings, explain molecular properties, compare candidates, and handle weak generation honestly through trust messaging and fallback behavior. The generative model itself is still under active improvement, and the project is positioned transparently around computational support rather than experimental validation.

## Key Highlights

- Built a chat-based computational molecule analysis product with structured backend responses and scientific trust messaging
- Added a protected workspace with guided onboarding, session handling, and evidence-weighted candidate presentation
- Added scoring, explanation, comparison, rendering, and safe fallback workflows for demo-safe usage
- Created a baseline reliability suite plus smoke checks, runtime status, and backup scripts for safer demos
- Built a generation evaluation workflow that measures validity, uniqueness, novelty, and checkpoint quality
- Diagnosed major generation blockers honestly, including vocab mismatch risk, decoding problems, and weak checkpoint quality

## Honest Limitation Note

The biggest current limitation is de novo generation quality: recent checkpoint comparisons showed essentially 0% RDKit-valid molecules in the evaluated seeded runs, so the project should not yet be presented as a reliable molecule generator.

## Current Status Note

Current status: demo-ready prototype / research-support tool, with strong product framing and honest limitation handling, but not yet ready to claim robust generative performance, scientific validation, or production readiness.
