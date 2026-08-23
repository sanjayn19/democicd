# Rollback runbook

## PTEST: rollback one promoted source PR

Do not merge `main` or reset the whole `ptest` branch. Find `.promotion/records/ptest/pr-<number>.json`, then create a rollback branch from `ptest` and revert the recorded `promotion_sha`:

```bash
git fetch origin ptest
git switch -c rollback/ptest/pr-123 origin/ptest
git revert <promotion_sha>
git push -u origin rollback/ptest/pr-123
```

The supplied **Create selective rollback PR** workflow performs these steps from the recorded SHA and labels the generated PR `rollback:ptest`. Run CI and merge it using **Create a merge commit** after QA approval. The branch push must then deploy and pass post-deployment checks. Only after that success does finalization remove `promoted:ptest` from the source PR and add `rolledback:ptest` plus `reject:ptest` until a corrective source PR is ready.

If the rollback PR merges but deployment fails, the previous labels remain because the runtime may still contain the old version. Recover the deployment and re-run the original push workflow; do not manually claim the rollback succeeded.

If later promoted commits depend on the bad change, revert the dependency set as one reviewed rollback batch or use a forward fix.

## PROD: rollback one promoted source PR

Use `.promotion/records/prod/pr-<number>.json` to identify the exact PROD promotion commit. Create a rollback PR from `prod`, revert that commit, and pass the protected PROD approval and deployment checks.

After the rollback deployment and checks succeed, automation changes the source PR labels. Then:

1. Confirm `promoted:prod` was removed and `rolledback:prod` plus `reject:prod` were added.
2. Reconcile `main` through a normal corrective or revert PR.
3. Promote the corrective PR through PDEV, PTEST, and PROD.

## When Git revert is not enough

- Database/data migrations may be irreversible.
- DAG runs already started by the bad version may continue.
- External messages, files, or API calls may have side effects.
- Reverting an older commit may conflict with later changes.

In these cases, freeze promotion, use the application recovery plan, and prefer a forward fix or restored immutable deployment bundle. Never assume source rollback restores data or external state.

## Emergency branch rollback

If the entire latest promotion batch must be removed, revert the generated promotion PR merge commit on the environment branch. This removes exactly that batch, but it also removes every source PR included in it. Use this only when all batch members should be rolled back.
