# Sotto Homebrew Tap

This tap provides an **unadvertised preview** of the Sotto command-line
interface. The package and automated checks are available, but the isolated
identity workflow and live updater proposal have not yet been exercised. Do
not treat this preview as launch-ready or use it for critical production
secrets. See the [release-readiness record](releases/READINESS.md).

The formula packages the existing signed Sotto CLI release for macOS 15 or
later. Apple Silicon is the primary platform. Intel Homebrew is Tier 3 and
best-effort; Homebrew plans to end Intel support in or after September 2027.
Linux is not supported by this tap. See [Homebrew's support tiers](https://docs.brew.sh/Support-Tiers)
for current platform details.

## Install and update

Install the preview with:

```sh
brew install getsotto/tap/sotto
```

Update Homebrew's formula metadata and upgrade Sotto with:

```sh
brew update
brew upgrade getsotto/tap/sotto
```

The formula installs Bash, Zsh, and Fish completion definitions. Shells may
need their completion search path configured; follow Homebrew's
[shell-completion guidance](https://docs.brew.sh/Shell-Completion) for your
shell. The formula does not edit shell startup files.

## Start using Sotto

From the directory you want to use as a project, run:

```sh
sotto init
```

This creates a local identity and project and prints an Emergency Kit. Store
that kit somewhere safe: a new device needs it to unlock the account. Do not
paste the kit or master password into a terminal command, issue, or support
message. Initialising Sotto uses this macOS user's local data directory and
Keychain; Homebrew installation itself does not initialise an identity.

Add a secret and run a command with it in the environment:

```sh
sotto set API_TOKEN
sotto run -- npm start
```

The CLI prompts for secret values. `sotto run` supplies them to the child
process without printing them. Local use does not require server login;
`sotto login` and `sotto push` are optional when you want to sync encrypted
state.

For the full CLI guide, see the [Sotto README](https://github.com/getsotto/sotto#readme)
and its [security policy](https://github.com/getsotto/sotto/blob/main/SECURITY.md).

## Existing installations and PATH

Homebrew does not remove another `sotto` binary or change your shell
configuration. If a command still uses an older installation, inspect every
match and the Homebrew executable:

```sh
which -a sotto
brew list --versions sotto
brew --prefix getsotto/tap/sotto
"$(brew --prefix)/bin/sotto" --version
```

The first path reported by your shell is the one it runs. Choose which copy
you want on `PATH`; only remove an older binary after confirming its location
and installation method. Your project `sotto.toml`, local identity, encrypted
data, and Keychain entries are separate from the formula.

## Remove the package

To remove only the Homebrew-managed package, run:

```sh
brew uninstall getsotto/tap/sotto
```

The formula has no uninstall hook. This removes the Homebrew package; it does
not delete Sotto project files, local data, identities, Keychain entries, or
other Sotto installations. Keep a secure copy of your Emergency Kit before
removing Sotto or changing devices.

## Support and security

Sotto is pre-1.0 software and has not had a third-party cryptographic audit.
The CLI, package, and service may change before 1.0. Review the [security
policy](https://github.com/getsotto/sotto/blob/main/SECURITY.md) and
[threat model](https://github.com/getsotto/sotto/blob/main/docs/THREAT-MODEL.md)
before deciding whether it suits your data.

See [CONTRIBUTING.md](CONTRIBUTING.md) for maintainer and contributor
guidance. This repository is licensed under Apache-2.0; see [LICENSE](LICENSE).
