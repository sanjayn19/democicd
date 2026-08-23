# Promotion evidence

Promotion automation writes two forms of audit evidence:

- `runs/<environment>-<run-id>.json`: the complete batch selected by one manual workflow run.
- `records/<environment>/pr-<number>.json`: the immutable relationship between a source PR, its squash commit on `main`, and the generated promotion commit.

The PROD workflow reads the matching PTEST record from the `ptest` branch and rejects the source PR if the recorded source SHA differs.

