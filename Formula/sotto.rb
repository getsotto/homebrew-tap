class Sotto < Formula
  desc "Manage local identities and run commands with project secrets"
  homepage "https://github.com/getsotto/sotto"
  license "Apache-2.0"
  depends_on macos: :sequoia

  if Hardware::CPU.arm?
    url "https://github.com/getsotto/sotto/releases/download/v0.10.2/sotto-v0.10.2-aarch64-apple-darwin.tar.gz"
    sha256 "ef47d2be26a665d0c72eb9df2575f1d3e3f4c6e6facc9e5970cc406a344c38de"
  else
    url "https://github.com/getsotto/sotto/releases/download/v0.10.2/sotto-v0.10.2-x86_64-apple-darwin.tar.gz"
    sha256 "29de3101cfe4516c40b960af42bc275f54d08518ae579bdb91186c29e04026f9"
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
