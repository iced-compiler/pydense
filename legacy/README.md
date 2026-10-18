# Legacy PyDense v0.2 (sigil dialect)

These files are the pre-1.0 implementation, kept only so that `benchmarks/corpus_fidelity.py --backend legacy`
can reproduce the before/after comparison in the README. They are not installed, not supported, and not
compatible with the v1.0 `.dpy` grammar (see `docs/SPEC.md`).

Measured on 109 CPython stdlib files (4,630 top-level statements): 73.6% round-trip fidelity, 37% o200k token
reduction with annotations stripped. The v1.0 grammar replaces the sigils and macros after tiktoken measurements
showed they were token-neutral or negative (`docs/SPEC.md` §12).
