# Promotion strategy

## Why `main` must not be merged into PROD

`main` is an integration stream. If PR-A and PR-B are merged to `main`, but only PR-A is qualified for PROD, a `main -> prod` PR contains both. A label on PR-A cannot make a branch merge selective.

The template therefore uses the source PR's immutable squash commit as the unit of promotion. Automation applies that exact patch to a temporary branch based on the target environment and opens a normal reviewable PR.

## Branch roles

| Branch | Role | How it changes |
| --- | --- | --- |
| `main` | Integration and source-of-truth history | Feature PRs only, squash merged after CI/review |
| `pdev` | Development deployment branch | Bot fast-forwards it to every new `main` SHA |
| `ptest` | Selective test deployment branch | Generated promotion PRs only |
| `prod` | Selective production deployment branch | Generated promotion PRs only |

No developer commits directly to an environment branch.

## State transitions

1. A feature PR is squash-merged into `main`.
2. `sync-and-deploy-pdev.yml` fast-forwards `pdev` to the same SHA.
3. The source PR is labeled `promote:ptest`.
4. The manual PTEST workflow selects all eligible labeled source PRs in merge-time order.
5. It creates one batch branch from `ptest`, applies each source squash commit, writes audit records, and opens a PR into `ptest`.
6. CI validates the generated PR. Reviewers merge it using **Create a merge commit**. This preserves every PR-specific promotion SHA. The branch push deploys PTEST.
7. The deployment workflow validates the exact branch SHA, deploys it, runs post-deployment checks, and uploads evidence.
8. Only after all deployment steps pass does finalization replace `promote:ptest` with `promoted:ptest` on each source PR represented by a newly added manifest.
9. A source PR may then receive `promote:prod`.
10. The PROD workflow verifies the exact source SHA against its PTEST record before opening a PROD promotion PR.
11. A protected PROD environment approval gates deployment; `promoted:prod` is added only after PROD deployment and checks pass.

If an environment PR merge succeeds but deployment fails, the request label remains. Repair the deployment issue and re-run the original push-triggered workflow so it retains the exact `before` and `after` SHA range. A manual redeploy performs validation but deliberately does not infer which manifests should change labels.

## Multiple developers and ordering

Candidates are sorted by the time they were merged into `main`. This preserves the integration order. If two approved PRs modify the same file, both are applied in that order. If a selected PR depends on an unselected PR, its patch will usually conflict or tests should fail; teams should additionally document dependencies in the source PR and label dependent PRs together.

For critical repositories, extend `promote.py` to parse a required PR-body field such as `Depends-On: #123` and fail when the dependency is not already present in the target branch or current batch.

## Why squash merge is mandatory

The workflow needs a one-to-one relationship:

`source PR -> one main commit -> one promotion patch`

Merge commits can include unrelated first-parent history when moved to an older environment branch. Rebase merge can create several new commits and GitHub's `merge_commit_sha` is not a reliable representation of the complete PR delta. The promotion engine checks that the selected commit has one parent and that its changed file set equals the source PR file set.

This restriction applies to source PRs into `main`. Generated promotion and rollback PRs into `ptest` or `prod` must use merge commits so their individual promotion or revert SHAs remain in environment history. Squashing a promotion batch would make PR-specific rollback impossible without reconstructing the patch.

## Batching rule

One manual run creates one promotion PR. A second run is rejected while an earlier promotion PR for the environment is open. This prevents overlapping batches built from different target baselines.

## Label truth model

`promote:<environment>` means requested. `promoted:<environment>` means the target runtime was successfully deployed and passed post-deployment checks, not merely that an environment-branch PR merged. Rollback state follows the same rule: `rolledback:<environment>` is added only after the reverted branch state is deployed and checked.

The deployment finalizer accepts only new JSON manifests under `.promotion/runs/`, verifies that the push is a fast-forward, checks that each promotion or revert commit is an ancestor of the deployed SHA, and makes comment creation idempotent for safe workflow re-runs.

## Recommended improvement for large systems

For containerized or packaged applications, the stronger model is build-once artifact promotion: deploy the same immutable artifact digest to each environment and keep branches only for source history. DAG repositories often deploy files directly, so this template keeps environment branches and verifies patches. If the DAG deployment platform supports versioned bundles, prefer promoting the bundle digest and a release manifest instead of reconstructing code branches.
