# DAG source

The three Python files are deliberately independent examples. In a real repository, keep shared code in a versioned package such as `plugins/` or `src/`, and make dependency changes explicit in the source PR.

Environment-specific project IDs, buckets, connections, variables, secrets, and schedules should be injected by deployment configuration. Do not edit the DAG differently on `pdev`, `ptest`, and `prod` branches.

