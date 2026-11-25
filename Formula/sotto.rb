class Sotto < Formula
  desc "Manage local identities and run commands with project secrets"
  homepage "https://github.com/getsotto/sotto"
  license "Apache-2.0"
  depends_on macos: :sequoia

  if Hardware::CPU.arm?
    url "https://github.com/getsotto/sotto/releases/download/v0.11.1/sotto-v0.11.1-aarch64-apple-darwin.tar.gz"
    sha256 "bafefb55febf59f47f3f15e45220bc5f2998573d11d553fe8f7837534baee132"
  else
    url "https://github.com/getsotto/sotto/releases/download/v0.11.1/sotto-v0.11.1-x86_64-apple-darwin.tar.gz"
    sha256 "be4628895e04bfcd869a2f3efca12e84971fdfff39a6cb02ac8b6094ae60bc02"
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
