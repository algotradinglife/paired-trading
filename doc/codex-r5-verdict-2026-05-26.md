# Codex R5 verdict

## Per-question

Q1 (statistical interpretation): Yes. As an unconditional policy rule, the R4 basis is no longer defensible. The v1 result was marginal even before the deep-data rerun: n=74, mean -1.59%, CI ending at +0.02%, so it did not cleanly exclude zero. The v2 replacement estimate is n=324, mean -0.10%, CI [-0.99%, +0.82%], hit 48.8%, which puts the effect near zero.

Alternative interpretation: a recent-regime effect is plausible, but not actionable without an ex ante regime indicator. Post-Aug-2023 is negative, but earlier chunks are positive or near zero.

Q2 (D1/D2/D3 recommendation): Choose D1 for production. Remove `CN-top-supp-fade` as an unconditional 0.80 de-weight and revert top+higher=supporting to pass-through weight 1.00. D2 is acceptable only as discretionary risk friction, not as a statistically validated rule. D3 is not defensible unless paired with a validated regime gate. Preferred D4: remove now, shadow-test a pre-specified regime-conditioned version.

Q3 (walk-forward regime usage): "Works only when regime resembles post-2023" is a research hypothesis, not a policy rule. Chunk[2] top+supporting is negative (-1.02%), but a bootstrap check gives roughly CI [-2.36%, +0.26%], still crossing zero. Fold asymmetry is too weak to ship.

Q4 (F8 weakening): Correct conclusion: F8 is still positive, but R4 overstated magnitude. v2 is n=306, mean +1.19%, CI [+0.26%, +2.14%], hit 57.5%. Because CN policy already uses weight 1.00, leave it at 1.00. Do not add a boost without separate walk-forward validation. Update reason fields from +3.81% to +1.19%.

Q5 (filter-tuning ceiling): Yes. Increasing sample size 4.3x did not produce any walk-forward-stable cells. Current B-topology filters are mostly sorting regime-conditional effects. New detector classes such as exhaustion/capitulation and first-pullback are the right next research direction.

Q6 (CZCE impact): CZCE does not explain the collapse. In h=20 raw rows, CZCE top+supporting is positive in both samples (+1.19%), while its share falls from 17.6% in v1 to 4.0% in v2. Non-CZCE top+supporting moves from -2.18% in v1 to -0.16% in v2, so the reduction comes from newly deep non-CZCE history.

Q7 (additional): Treat v2 as a replacement estimate, not an independent confirmation sample. Correct R4 language: top+higher=supporting was marginal, not cleanly significant. Revalidate coal-complex and preferred-universe hints on v2. If consumers use horizons beyond h=20, repeat the verdict there. Future reviews should use blocked/clustered resampling by symbol/date where possible.

## Recommended policy changes

- Remove `CN-top-supp-fade` as an unconditional 0.80 de-weight.
- Set top+higher=supporting to pass-through weight 1.00 unless a future regime-gated version passes walk-forward.
- Update `_apply_cn_futures` comments/reasons to cite v2: top+higher=supporting n=324, mean -0.10%, CI [-0.99%, +0.82%].
- Keep `F8-cn-no-boost` at weight 1.00 and update docs to n=306, mean +1.19%, CI [+0.26%, +2.14%].
- Keep `CN1-top-passthrough` at weight 1.00.
- Add D4 research item: test a pre-specified regime-conditioned top+supporting fade before any reintroduction.

## Methodology flags

- The main lesson is replacement-sample shrinkage: the deeper sample moved R4 magnitudes sharply toward zero or reversed signs.
- Walk-forward stability remains the gating constraint.
- CZCE shallow coverage is a caveat, but not the observed driver of the policy reversal.
- Future detector work should be validated as new signal-generation capacity, not another B-topology filter-tuning pass.
