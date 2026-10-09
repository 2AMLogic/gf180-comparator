# `adapt_samples_r2.py` -- hardened adapter (revision 2)

`adapt_samples.py` and `README.md` in this directory are append-only evidence
and stay byte-identical. `adapt_samples_r2.py` is the current revision: same
population-sigma formula, same 1e-6 tolerance and the same negative-control
shift as `adapt_samples.py`, so on the committed record it writes the same
sample-set document. It additionally refuses non-finite draws or record
statistics, non-positive-integer `n_samples`, and non-finite computed results;
nothing is written unless all checks pass, and output is strict JSON.

Regressions: `sim/harness/tests/test_adapt_samples.py`.

Use it in place of `adapt_samples.py` in the "Reproduce" command of `README.md`:

```bash
python3 sim/comparator-offset-mc/yield/adapt_samples_r2.py \
    sim/comparator-offset-mc/records/20260910-124917-4805118.json \
    sim/comparator-offset-mc/yield/samples-20260910-124917-4805118.json
```
