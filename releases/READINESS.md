# Homebrew release readiness

**Status: preview only. Promotion to the main Sotto installation guides is not
approved.** The automated package matrix and updater's safe manual no-op path
are verified. Three launch checks remain: enabling workflow PR creation, a
controlled bot-created update PR with current-head checks, and the isolated
Apple Silicon identity workflow.

## Verified package and release evidence

- Formula source: [`Formula/sotto.rb`](../Formula/sotto.rb), last changed in
  [`40e4fce`](https://github.com/getsotto/homebrew-tap/commit/40e4fce90bae3ee7c196d87d6c817a38c7af3a54).
- Packaged CLI: v0.9.0. The formula pins the Apple Silicon and Intel archives
  and their SHA-256 digests.
- The [PR 1 run](https://github.com/getsotto/homebrew-tap/actions/runs/38964013095)
  passed signed-input verification, Homebrew style/audit, and native install,
  smoke, architecture, completion, documentation, and removal-preservation
  checks across macOS 15/26 and Apple Silicon/Intel.
- The [PR 2 run](https://github.com/getsotto/homebrew-tap/actions/runs/38965655257)
  passed the same six required contexts, including controlled package upgrade
  and recovery fixtures.
- The [PR 3 run](https://github.com/getsotto/homebrew-tap/actions/runs/38967349311)
  passed all six required contexts on the updater change. Main branch
  protection requires these contexts with strict current-base validation.
- Default workflow token permissions are read-only. PR 3 scopes write access
  by job.
- The [manual updater run](https://github.com/getsotto/homebrew-tap/actions/runs/38969361529)
  completed successfully on the merged updater at `023092f`. It verified the
  explicit v0.9.0 input and returned `no-op` because that version is already
  packaged. It did not create or change a PR.
- PR 3's 39 local unit tests cover release policy, proposal edit protection,
  check-run ordering, API failure recovery, and incident deduplication and
  closure. The live incident reporter has not created or closed a real issue.

The automated support matrix is macOS 15 and 26 on Apple Silicon and Intel.
macOS 15 is the formula's minimum. Apple Silicon is the primary target. Intel
Homebrew is Tier 3 and best-effort, and Homebrew says Intel support will end in
or after September 2027. These statements describe the tap's tested builds;
they do not extend Homebrew's own support tier.

## Outstanding launch checks

| Check | State | Evidence still needed |
| --- | --- | --- |
| Allow GitHub Actions to create pull requests | Disabled | `GET /repos/getsotto/homebrew-tap/actions/permissions/workflow` returned `default_workflow_permissions: read` and `can_approve_pull_request_reviews: false`. The combined create-and-approve setting must be enabled before the updater can open a proposal. The workflow itself must continue to avoid approving or merging PRs. |
| Bot-created update PR and exact-head checks | Not run | After enabling the setting, wait for a genuine newer published release and verify that the merged updater opens a PR with `GITHUB_TOKEN` and all six formula checks pass on its current head. Do not invent a release or weaken version admission. Close the proposal without merging to exercise suppression. |
| Isolated Apple Silicon identity workflow | Not run | In a disposable macOS user or VM with its own Homebrew installation, install the formula, initialise a disposable identity/project, lock, unlock, run a canary check that prints only presence, uninstall the formula, and confirm the disposable project/data remain. |
| Scheduled updater run | Not yet observed | Inspect the first scheduled run after merge and confirm its selected version, outcome, and any incident handling. |
| Intel identity and unlock | Not tested | No Intel Keychain result is implied by the automated install matrix or Apple Silicon smoke. |

### Isolated Apple Silicon smoke procedure

Run this only from a disposable macOS account or VM with its own Homebrew
installation. Do not use the maintainer's normal account, its Homebrew prefix,
or a separate `SOTTO_DATA_DIR` as a substitute for Keychain isolation.

1. Record the tap commit, `sw_vers`, `uname -m`, `brew --version`, and
   `brew install getsotto/tap/sotto`; record `sotto --version` and
   `file "$(command -v sotto)"`.
2. In a temporary project directory, run `sotto init`. Use a new disposable
   identity and project, and store the printed Emergency Kit only in the
   disposable environment.
3. Run `sotto set HOMEBREW_CANARY` and enter a fixed, non-sensitive test
   phrase at the hidden prompt.
4. Run `sotto lock`, then `sotto unlock`. Confirm the normal hidden password
   prompt unlocks the identity.
5. Run
   `sotto run -- sh -c 'test -n "$HOMEBREW_CANARY" && echo canary-present'`.
   Record only the exit status and `canary-present` output; never print the
   canary value.
6. Run `brew uninstall getsotto/tap/sotto`. Confirm the temporary project's
   `sotto.toml` and the disposable account's
   `~/Library/Application Support/sotto/store.db` still exist. Do not copy
   database, project contents, kit, password, or canary into the evidence.
7. Destroy the disposable account or VM and its test data after recording the
   result.

On 16 October 2026 the available host was an Apple M4 MacBook Air on macOS
26.5.2 with Homebrew 7.0.9. Only the maintainer's normal account was
available, and no macOS VM was configured. The tap was not installed in that
account. The isolated identity smoke was therefore not run; no identity,
Keychain entry, password, Emergency Kit, or secret was created or inspected.

Do not promote the Homebrew command in the core or extension installation
guides until the two launch checks above are recorded and a maintainer confirms
readiness. An update PR passing package checks alone does not complete this
gate.

## Migration, removal, and recovery

Moving from another Sotto installation method does not require a data
migration. The same CLI uses the current macOS user's local Sotto data and
Keychain. Install the Homebrew formula, then inspect executable resolution with
`which -a sotto` and `"$(brew --prefix)/bin/sotto" --version`. Keep the old
binary until the Homebrew executable works and you have deliberately chosen
which copy should appear first on `PATH`. Do not remove or replace unrelated
installations as an automatic migration step.

`brew upgrade getsotto/tap/sotto` installs the current formula. The tap does
not provide versioned formulae or promise an automatic downgrade. If a release
is found to be faulty, maintainers should hold that version and prepare a
reviewed forward fix or a compatibility-verified rollback. Users should stop
using a confirmed bad CLI, preserve their local data and Emergency Kit, and
follow the incident's reviewed instructions. Do not reset an identity or
delete Sotto data to troubleshoot a package installation. `brew uninstall getsotto/tap/sotto` removes the Homebrew-managed package; CI verifies that
package removal leaves unrelated executable and Sotto state fixtures intact.

For a Homebrew installation problem, first inspect the formula, installed
version, resolved paths, and linked executable:

```sh
brew info getsotto/tap/sotto
brew list --versions sotto
which -a sotto
"$(brew --prefix)/bin/sotto" --version
```

After checking for an upstream incident, reinstall only the formula with
`brew reinstall getsotto/tap/sotto`. For a workflow incident, follow [the
maintainer runbook](README.md). Schedule events run only
from the default branch and may be delayed; public-repository schedules are
automatically disabled after 60 days without repository activity. Check the
workflow's enabled state and latest run. A write-access maintainer can
re-enable a disabled workflow; if its scheduling actor is suspended, change
the cron entry in a reviewed commit to restart scheduled runs.

See [Homebrew support tiers](https://docs.brew.sh/Support-Tiers),
[Homebrew shell completions](https://docs.brew.sh/Shell-Completion),
[GitHub scheduled workflow troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows),
and [GitHub workflow enablement](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
for the upstream behaviours referenced here. Sotto is pre-1.0 and has not
received a third-party cryptographic audit; see the [security policy](https://github.com/getsotto/sotto/blob/main/SECURITY.md)
and [threat model](https://github.com/getsotto/sotto/blob/main/THREAT-MODEL.md).
