# Release planning records

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
