# Production model bundles

This directory contains small, versioned model bundles that have passed the
evaluation project's production-contract checks. Each bundle is immutable and
must be validated before integration:

```bash
linkrag-eval ltr validate-bundle --model-dir models/<model-version>
```

Local training inputs, Blind datasets, run outputs, and databases remain under
`runs/` and are intentionally not versioned.
