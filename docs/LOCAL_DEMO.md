# Local demonstration

The extracted directory is already a Git repository with `main`, `pdev`, `ptest`, and `prod` pointing to the same initial commit.

Simulate normal development:

```bash
git switch main
git switch -c feature/change-sales-dag
sed -i.bak 's/30 3/45 3/' dags/sales_transform.py
git add dags/sales_transform.py
git commit -m "Change sales DAG schedule"
git switch main
git merge --squash feature/change-sales-dag
git commit -m "Change sales DAG schedule (#1)"
git branch -f pdev main
```

The GitHub label workflows require a real GitHub remote and cannot be fully simulated offline. The local repository is intended to let you inspect history and test how an isolated squash commit can be applied to `ptest` without including other `main` commits.

