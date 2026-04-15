# Demo Script

## 60-90 Second Demo Flow

1. Open Genorova chat and state the framing clearly.
2. Score a known molecule to show structured computational analysis.
3. Ask Genorova to explain the molecule simply.
4. Compare it with another molecule or with the current best ranked molecule.
5. If asked about generation, show the honest fallback behavior and explain that fresh generation quality is still being improved.

## Short Demo Disclaimer

"Genorova is currently a prototype computational research-support system. The strongest part of the product today is scoring, explanation, comparison, and responsible scientific framing. It is not experimentally validated, and fresh molecule generation is still under active improvement."

## Exact Prompts To Type

### Prompt 1: Score

`Score this molecule: CCO`

What to say:
- "This shows the structured property and model-score layer."

### Prompt 2: Explain

`Explain this molecule simply`

What to say:
- "The chat layer can translate computational output into more accessible language."

### Prompt 3: Compare

`Compare it with the best one`

What to say:
- "This is the safest high-value workflow today: compare and reason about known valid molecules."

### Prompt 4: Optimize

`Make it less toxic`

What to say:
- "Genorova can suggest follow-up thinking and tradeoffs, while still staying explicit about limitations."

## Backup Prompts

Use these if the flow needs a reset or generation is weak:

- `Score this molecule: CC(=O)Oc1ccccc1C(=O)O`
- `Explain this molecule simply`
- `Compare metformin with the best one`
- `Optimize it for oral delivery`
- `Show the top computational candidates for diabetes`

## Safest Features To Demonstrate

- chat interface
- scoring a known molecule
- molecule explanation
- molecule comparison
- trust messaging and limitations
- safe fallback behavior when generation is weak

## What To Avoid Saying

Do not say:
- "These are validated drug candidates."
- "This has been experimentally proven."
- "The model reliably generates new drugs."
- "This docking result confirms efficacy."
- "This is ready for pharma deployment."

Prefer saying:
- "computational ranking"
- "prototype research-support output"
- "not experimentally validated"
- "useful for analysis, prioritization, and explanation"

## If Generation Comes Up

Safe wording:

"Generation quality is still the main technical blocker. We now handle that honestly in-product by showing safe fallback molecules or an explicit failure state instead of pretending a valid fresh candidate was produced."

## Best Demo Narrative

Genorova today is strongest as a trustworthy computational molecule analysis assistant. The demo should emphasize responsible UX, explainability, and disciplined handling of model limitations.
