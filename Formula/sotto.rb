class Sotto < Formula
  desc "Manage local identities and run commands with project secrets"
  homepage "https://github.com/getsotto/sotto"
  license "Apache-2.0"
  depends_on macos: :sequoia

  if Hardware::CPU.arm?
    url "https://github.com/getsotto/sotto/releases/download/v0.9.0/sotto-v0.9.0-aarch64-apple-darwin.tar.gz"
    sha256 "0c62436bd0864c3a710c3bef1e62f9281ec794fe6d4263e3288659fa7b9cdc8c"
  else
    url "https://github.com/getsotto/sotto/releases/download/v0.9.0/sotto-v0.9.0-x86_64-apple-darwin.tar.gz"
    sha256 "a6c650f02ee09c3cc2418e287a56f96e14266813a55a59c1bc8c6e0db2cf3725"
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
    %w[bash zsh fish].each do |shell|
      assert_match "sotto", shell_output("#{bin}/sotto completions #{shell}")
    end
  end
end
