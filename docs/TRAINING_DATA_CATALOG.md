# Training data catalog

The maintained dataset descriptions and audit reuse rules are in the
[Polish training data catalog](PL/DANE_TRENINGOWE.md). Read it before rediscovering
or profiling G01–G05 V2. These names refer to versioned material, with substantial
retention between versions; they are not independent corpora.

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


## G05 V2: both Gemma 4 variants

Catalog updated 2026-11-03; the historical G01–G04 audit remains dated 2026-11-02.
Private material: `data/training/gemma-g05-v2-20261103-ready/manifest.json`.
G05 V2 retains G04 and adds 288 executed PL/EN conversations across four real
FileSkill functions: 832 train, 224 validation and 160 diagnostic holdout records.
Execution receipts and independent fixture-state checks are not human reviews or
model results. The frozen G04 and historical evidence remain unchanged.

E4B IT and 12B IT have separate pinned profiles, native loaders/processors,
tokenizers and selective assistant masks. Holdout is excluded from training.
A separate 24-case reserve checks summary, translation and image retention with
authored lexical oracles; audio remains unqualified. Training and model evaluation
require GPU. See [Gemma preparation](GEMMA4_OPERATOR.md) for atomic session steps,
identity limits and deferred hardware qualification.
