class Sotto < Formula
  desc "Manage local identities and run commands with project secrets"
  homepage "https://github.com/getsotto/sotto"
  license "Apache-2.0"
  depends_on macos: :sequoia

  if Hardware::CPU.arm?
    url "https://github.com/getsotto/sotto/releases/download/v0.11.0/sotto-v0.11.0-aarch64-apple-darwin.tar.gz"
    sha256 "73e42b0e1d78ee27a72d1b4dd57b1ee8add7b909e1c65d4c908e3c553daadac7"
  else
    url "https://github.com/getsotto/sotto/releases/download/v0.11.0/sotto-v0.11.0-x86_64-apple-darwin.tar.gz"
    sha256 "642be0052b13f163ef729ebd304af81ed0c5bab09660b177f827f5d068f167c7"
  end

  def install
    target = Hardware::CPU.arm? ? "aarch64-apple-darwin" : "x86_64-apple-darwin"
    stage = "sotto-v#{version}-#{target}"
    root = Pathname(stage).directory? ? Pathname(stage) : Pathname(".")

    bin.install root/"sotto"
    bash_completion.install root/"completions/sotto.bash" => "sotto"
    zsh_completion.install root/"completions/sotto.zsh" => "_sotto"
    fish_completion.install root/"completions/sotto.fish"
    doc.install root/"LICENSE", root/"SECURITY.md", root/"THREAT-MODEL.md"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/sotto --version")
    assert_match "Usage:", shell_output("#{bin}/sotto --help")
  end
end
