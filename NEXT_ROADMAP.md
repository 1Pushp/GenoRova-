# Next Roadmap

## Immediate Next Steps

### Model Quality Improvements

- Add explicit BOS/EOS handling to the sequence pipeline
- Improve decode-time stopping behavior and malformed-string handling
- Add generation-time validity checks during training, not only after training
- Re-run checkpoint comparison after the first decoding fixes

### Scientific Evaluation Improvements

- Track RDKit validity during training checkpoints
- Add fixed benchmark prompts and fixed evaluation seeds for easier before/after comparison
- Expand evaluation reporting with a compact history table across experiments

### Product Improvements

- Keep the chat-first demo flow as the default experience
- Continue replacing user-facing `clinical_score` wording with `model score` where safe
- Add clearer empty-state messaging where generation returns no trustworthy fresh output

### Infrastructure / Reliability Improvements

- Fix the `lr_scheduler.step()` ordering warning in `train.py`
- Add a few more tests around generation fallback and trust payload fields
- Keep checkpoint/vocab compatibility checks strict across all runtime entrypoints

## Short-Term Next Sprint

### Model Quality Improvements

- Retrain with corrected sequence handling
- Compare pretrain vs fine-tune checkpoints again after decoding fixes
- Add a small teacher-forced validation sanity pass that samples decoded outputs during training

### Scientific Evaluation Improvements

- Add clearer experiment naming and version metadata to evaluation outputs
- Build a simple experiment table summarizing:
  - checkpoint
  - vocab
  - validity
  - uniqueness
  - novelty
  - average model score

### Product Improvements

- Add a cleaner "analysis mode" positioning pass across docs and API docs
- Improve report/export wording so it never overstates scientific confidence

### Customer / Pilot Readiness

- Prepare a concise pilot-safe usage guide
- Define a narrow early-user story:
  - molecule scoring
  - explanation
  - comparison
  - prototype research support

## Medium-Term Goals

### Model Quality Improvements

- Reach materially non-zero, repeatable RDKit-valid generation on benchmark runs
- Improve uniqueness and novelty without collapsing validity
- Decide whether the current VAE design should be iterated or replaced

### Scientific Evaluation Improvements

- Separate heuristic ranking, proxy scores, and any future real docking signals cleanly
- Add a more formal benchmark set for known reference molecules and target use cases
- Introduce experiment tracking robust enough for repeatable model comparisons

### Infrastructure / Reliability Improvements

- Expand tests beyond smoke coverage into artifact/reporting regression checks
- Standardize model, vocab, and output versioning
- Create a more explicit release checklist for future demo builds

### Customer / Pilot Readiness

- Narrow the product story to a realistic pilot scope
- Prepare a founder-ready "what it is / what it is not" onboarding pack
- Add usage logging and demo analytics only if needed for real pilot conversations

### Investor-Readiness Milestones

- Demonstrate honest product value even before generation quality is solved
- Show a measurable improvement arc on validity and checkpoint quality
- Present Genorova as a disciplined computational workflow prototype with a clear technical roadmap, not as a solved drug-discovery platform

## Practical Priority Order

1. Fix generation quality at the sequence/decoding level
2. Re-measure with the existing evaluation workflow
3. Keep the product positioned around safe analysis and research-support value
4. Package repeatable progress evidence for pilots, mentors, and investors
