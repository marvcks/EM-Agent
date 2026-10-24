# EditRetro CPU single-step retrosynthesis

| ID | Contract |
| --- | --- |
| ER-001 | Pin upstream commit and user checkpoint; retain the model, vocabulary, tokenizer and decoding algorithm. Replace four device transfers for CPU. Strict state loading must have zero missing or unexpected keys. |
| ER-002 | Accept one connected product SMILES, at most 128 atoms including hydrogens. Bound top-k and augmentations to 1–20. Use the shared science queue, lifecycle and verified result gate; no LLM on manual submission. |
| ER-003 | Show a SMILES form with the supplied document example, prediction controls and ranked precursor SMILES. Explain that this is single-step prediction and rank is not calibrated probability. |
| ER-004 | Mount the frozen CPU runtime independently and read-only; candidate image and runtime lock match. Discover the bundled Agent skill without overwriting user skills. Preserve existing state and tools through deployment and rollback. |

Native acceptance uses the supplied document product, canonical SMILES comparison, strict checkpoint loading, valid unique candidates, measured wall time and peak memory. A successful example does not establish benchmark accuracy or experimental feasibility. The supplied full candidate ranking is a comparison reference rather than a byte-for-byte reproducibility claim.
