# Branching Model (2026-02-06)

## Structure

```
upstream/main (oraios/serena)
    │
    ├── origin/main (ketema/serena) — synced from upstream
    │       │
    │       └── local feature branches for upstream PRs
    │           (branch from main, PR to upstream, no personal changes)
    │
    └── origin/ketema — personal development branch
            │
            ├── Rebases from upstream/main when possible
            ├── Contains all personal/experimental work
            └── Feature branches off ketema for focused work
                (merge back into ketema when complete)
```

## Rules

1. **`ketema`** is the personal base branch (fork of upstream). All ongoing work lives here.
2. **Feature branches** branch off `ketema` for focused work, merge back into `ketema`.
3. **Rebase from `upstream/main`** into `ketema` when upstream moves and we want to sync.
4. **Upstream contributions**: Branch from **local `main`** (not `ketema`), create PR to `upstream/main`. This keeps personal changes out of upstream PRs.
5. **`main`** stays synced with `upstream/main` — it's the clean upstream mirror.

## Remotes

- `origin` = `git@github.com:ketema/serena.git` (personal fork)
- `upstream` = `git@github.com:oraios/serena.git` (source repo)
