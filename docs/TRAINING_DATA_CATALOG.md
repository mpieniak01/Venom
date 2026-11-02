# Training data catalog

The maintained dataset descriptions and audit reuse rules are in the
[Polish training data catalog](PL/DANE_TRENINGOWE.md). Read it before rediscovering
or profiling G01–G04. The four names refer to versioned material, with substantial
retention between versions; they are not four independent corpora.

The canonical host also has a private `data/training/README.md`, individual
`data/training/catalog/G01.md`–`G04.md` cards and durable evidence under
`data/training/catalog/analyses/2026-11-02/`. Those files stay outside Git. Public
project documentation contains descriptions and aggregates only, never raw rows,
private recipes or tool transcripts.

Check the stored dataset identities before reusing audit results. Unchanged
source hashes permit reuse of structural, duplicate and split findings. A new
model still requires its own tokenizer/template, loss-mask and protocol checks;
it does not alone require a new full audit of unchanged source data. Missing
local evidence must remain explicitly unverified.

The catalog records known duplicate content in G01, the retained HF subset,
selective supervision, diagnostic holdout limits and fit for FunctionGemma 270M
and Granite Nano 350M. It separates material preparation from actual model
training, deployment and evaluation.

For execution, see [Remote training](REMOTE_TRAINING.md).
