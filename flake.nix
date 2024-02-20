{
  description = "pykefcontrol flake file";

  inputs = {
    nixpkgs.url = "nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix.url = "github:nix-community/poetry2nix";
  };

  outputs = { nixpkgs, flake-utils, poetry2nix, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        poetryEnv = (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }).mkPoetryEnv {
          projectDir = ./.;
          preferWheels = true;
        };
      in
      {
        devShell = pkgs.mkShell {
          nativeBuildInputs = [
            poetryEnv
          ];
        };
      }
    );
}