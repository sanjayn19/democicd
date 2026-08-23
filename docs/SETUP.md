# GitHub setup

## Repository settings

- Default branch: `main`
- Enable repository merge methods: Squash merge and Create a merge commit
- Disable: Rebase merge
- Use branch rulesets to require Squash merge for `main` and merge commits for `ptest`/`prod`
- Automatically delete head branches after merge
- Require signed commits if that is an organization standard

## Branch rules

### `main`

- Require pull requests and two approvals as appropriate
- Require the `validate` check from the GitHub Actions app
- Require CODEOWNERS review for `.github/workflows/`, `scripts/`, `config/`, and `.promotion/`
- Dismiss stale approvals
- Require conversation resolution
- Block force pushes and deletion
- Require squash as the allowed merge method

For a personal, single-collaborator demo repository, set required approvals to zero and do not require CODEOWNERS review. GitHub does not allow the PR author to approve their own PR, so enable those review gates only after adding at least one independent collaborator who can review the owner’s changes.

### `pdev`

- Block human pushes
- Allow the promotion bot to fast-forward from `main`
- Block force pushes and deletion

### `ptest`

- Require PRs
- Require the `validate` check from the GitHub Actions app
- Require release/QA approval
- Allow only PRs carrying `promotion:ptest` by policy or reviewer process
- Require merge commits for generated promotion/rollback PRs; do not squash the batch
- Block force pushes and deletion

### `prod`

- Require PRs and production-owner approval
- Require the `validate` check from the GitHub Actions app
- Require signed commits if compatible with the bot identity
- Allow only generated PRs carrying `promotion:prod`
- Require merge commits for generated promotion/rollback PRs; do not squash the batch
- Block force pushes and deletion

## Environments

Create `pdev`, `ptest`, and `prod` under repository Environments.

- Restrict deployment branches to the matching branch.
- Require reviewers for `ptest` and `prod`.
- Keep cloud credentials in the matching environment or use cloud workload identity federation.
- Configure environment-specific variables such as DAG bucket or workspace ID.

## Promotion bot token

Store a token as repository secret `PROMOTION_BOT_TOKEN`.

For production, use a GitHub App installation token with least privilege:

- Contents: Read and write
- Pull requests: Read and write
- Issues: Read and write, because PR labels and comments use issue endpoints
- Metadata: Read
- Workflows: Read only, unless the bot must update workflow files

The bot should be an allowed actor for the `pdev`, `ptest`, and `prod` branch rules. Avoid a broadly scoped classic PAT.

Every GitHub-maintained action in this template is pinned to a reviewed full commit SHA, with the release version recorded in an inline comment. Keep Dependabot enabled so it proposes reviewed SHA updates without making workflow execution depend on a mutable version tag.

## Deployment integration

`deploy-environment.yml` validates the DAGs, builds a ZIP plus SHA-256 manifest, deploys the exact checked-out SHA, runs `scripts/post_deploy_checks.py`, and uploads evidence. Only then does it run `scripts/finalize_deployment.py` to update source PR labels for manifests added by that push.

Replace the local deployment adapter and sample smoke check with your actual Composer/Airflow deployment and runtime verification. Useful gates include DAG-bag import health, scheduler visibility, environment API health, canary DAG completion, and required business smoke tests. Keep finalization after every required gate. For private cloud endpoints, use a self-hosted runner in the approved network and workload identity federation rather than a service-account key.

The PTEST/PROD deployment workflow grants its scoped `GITHUB_TOKEN` `issues: write` so it can update source PR labels and audit comments after success. It does not need repository-content write access. Keep pull-request creation on `PROMOTION_BOT_TOKEN` so bot-created events trigger the expected CI workflows.

If a push-triggered deployment fails after its environment PR merged, re-run that original workflow after recovery. A manual `workflow_dispatch` redeploy intentionally skips label finalization because it does not carry a trustworthy promotion push range.

## Initial branch setup

This ZIP contains a local Git repository in which `main`, `pdev`, `ptest`, and `prod` initially point to the same commit. After creating an empty GitHub repository:

```bash
git remote add origin git@github.com:YOUR_ORG/YOUR_REPO.git
git push -u origin main
git push origin pdev ptest prod
```

Alternatively, push `main` and run the manual **Bootstrap environment branches** workflow once.
