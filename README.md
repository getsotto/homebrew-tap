# Sotto Homebrew Tap

This repository distributes the Sotto command-line interface through a
Homebrew tap. The formula is an unadvertised preview for Sotto v0.9.0. Its
automated native platform and package lifecycle checks pass. Sotto's main
installation guides will promote the command after the isolated manual-use
and maintenance/recovery checks are complete.

The formula packages the existing CLI release for macOS 15 or later. Apple
Silicon is the primary platform. Intel Homebrew is Tier 3 and is best-effort;
Homebrew plans to remove Intel support in or after September 2027. Linux is
not supported by this tap.

The formula is an unadvertised preview. Sotto's main installation guides will
add it after the manual-use and maintenance checks are complete. See
[Homebrew's support tiers](https://docs.brew.sh/Support-Tiers) for the Intel
support details.

Install the preview with:

```sh
brew install getsotto/tap/sotto
```

To check which executable your shell will run, use `which -a sotto`. An older
installation earlier on `PATH` can take precedence. Choose which executable
to use deliberately; this tap does not remove other installations or change
your shell configuration. Homebrew installation does not initialise an
identity or project.

For installation options available today, see the [Sotto installation
guide](https://github.com/getsotto/sotto#install). Learn more about Sotto in
the [main repository](https://github.com/getsotto/sotto).

The Sotto CLI is pre-1.0 software. See the main repository's
[security policy](https://github.com/getsotto/sotto/blob/main/SECURITY.md) for
its security status and reporting guidance.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and sign-off
instructions. This repository is licensed under the Apache License 2.0; see
[LICENSE](LICENSE).
