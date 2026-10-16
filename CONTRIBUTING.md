# Contributing

Contributions to the Sotto Homebrew tap are welcome. Keep changes focused on
the formula, its release checks, or the documentation and maintenance of this
tap.

## Pull requests

Describe the user-visible result, the reason for the change, and the checks
you ran. Include relevant output or links, and state clearly when a platform
or behaviour has not been verified. Keep pull requests ready for review.

Use British English in prose. Commit subjects should be descriptive,
lowercase, and have no conventional prefix. Pull request titles may use a
conventional prefix.

## Validation

Run the checks documented for the files you change and report the exact
commands and results in your pull request. Do not claim that formula or
release checks passed unless you ran them successfully.

Use disposable fixtures for tests. Do not use real Sotto vaults, Keychain
identities, passwords, or other secret values in tests, logs, screenshots, or
pull request evidence. Package checks must not initialise or unlock a user's
identity or modify their Sotto data.

## Developer Certificate of Origin

Every commit must include a sign-off under the
[Developer Certificate of Origin](https://developercertificate.org). Sign
your commits with `git commit -s`, using your own configured name and email.
Automated commits must use the bot's own identity and sign-off; they must not
impersonate a maintainer.

## Licence

By submitting a contribution, you agree that it will be licensed under the
Apache License 2.0, as provided in [LICENSE](LICENSE).
