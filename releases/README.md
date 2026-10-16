# Release planning records

This runbook covers the tap's preview release updater. The current launch
evidence and remaining promotion gates are in
[`READINESS.md`](READINESS.md).

The release planner reads `held-versions.json` and `rollbacks.json` and prints
a report and formula patch. It does not write to GitHub or modify the checkout.
It requires Python 3 and Cosign; release inputs are downloaded from the
versioned Sotto GitHub release and verified against the signed checksum
manifest before a patch is proposed.

Run a dry report for a specific version with:

```sh
python3 scripts/plan_release.py --version 0.9.0
```

Omit `--version` to inspect GitHub's latest stable release. Use `--format json`
for the structured report consumed by later tooling. `--manual-retry` requires
an explicit version and only reopens a previously closed, unchanged proposal;
it does not bypass release verification, held-version policy, or version
ordering.

## Automated proposals and incident recovery

The scheduled updater runs daily at 06:17 UTC. It selects the highest
published stable semantic version, verifies its release inputs, and opens or
reuses one ready-for-review pull request per version. A manual run requires an
exact published version tag. Set the manual retry option only when reopening a
closed, unchanged proposal; a hold, changed release input, or downgrade remains
blocked.

Closing an automated update PR without merging records that version as
skipped, so the schedule will not reopen it. To retry that unchanged release,
run `update-release.yml` manually with the exact version and enable
`manual_retry`. A hold is different: it blocks scheduled discovery and manual
dispatch, and can only be cleared through a reviewed change to
`held-versions.json` after the incident is resolved. Do not use manual retry
to bypass a hold, changed signed input, or version ordering.

The updater uses the repository's `GITHUB_TOKEN`, creates a signed-off bot
commit, and never approves or merges its own pull request. Since GitHub can
place pull-request runs created by `GITHUB_TOKEN` in an approval-required
state, the updater explicitly dispatches the formula workflow on the proposal
branch. It waits for all six required checks on that exact head and fails if
the head changes while checks run. Maintainers review and merge the proposal
themselves; a workflow check run is not a pull request review or approval.

Scheduled failures create or update one issue labelled
`sotto-release-updater-failure`, including the failure stage, candidate when
known, and run link. Repeated failures update that same issue. The workflow
closes it only after this run completes the proposal path and verifies all
required checks on the current proposal head. For an unchanged open proposal,
it dispatches validation when a required check is missing or its latest run
failed. If every check is already green, that no-op does not close an older
incident; inspect it and close it manually after confirming the underlying
failure is resolved. A held version or skipped release alone does not count as
recovery. Check the Actions schedule and latest run as part of routine
maintenance; a disabled schedule cannot report that it has stopped. GitHub
runs scheduled workflows only from the default branch and may delay or drop
schedule runs during high load. In a public repository, GitHub disables
scheduled workflows after 60 days without repository activity. Check the
workflow's enabled state and last run in Actions. Re-enable a disabled
workflow there; if the scheduling actor was suspended, change the cron entry
in a reviewed commit to restart scheduled runs.

If a failure issue remains open, inspect the referenced logs and proposal
branch before retrying. Correct the underlying problem, then run the exact tag
manually when the candidate was skipped after a transient failure. Do not
delete or overwrite maintainer edits to a proposal branch. Resolve unexpected
branch contents or duplicate proposals by hand, and close an incident only
after the current-head checks confirm recovery.

## Held versions

Add a held release under the `versions` object in `held-versions.json`, keyed by
its plain semantic version. Include a concise `reason` and an incident or
review reference. A held version is blocked for both discovery and explicit
tag runs. Remove a hold only through a separate reviewed change after the
incident is resolved.

## Reviewed rollback records

Add a specific `from` and `to` pair to `rollbacks.json` only after review has
confirmed that the older CLI can safely read the affected user data. Include
the incident, a link or reference to compatibility evidence, set
`compatibility_verified` to `true`, and record `reviewed_by` and an ISO
`reviewed_at` date. The planner will authorise only that exact current-to-target
pair. An ordinary older release remains skipped, and a held target remains
blocked. Do not use a rollback record to claim safety without tested evidence.
