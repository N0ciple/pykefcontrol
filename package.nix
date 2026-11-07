{
  lib,
  buildPythonPackage,
  hatchling,
  aiohttp,
  urllib3,
  zeroconf,
  pytestCheckHook,
  pytest-asyncio,
  pytest-timeout,
  trustme,
}:

let
  pyproject = lib.importTOML ./pyproject.toml;
in
buildPythonPackage {
  pname = "pykefcontrol";
  inherit (pyproject.project) version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./pyproject.toml
      ./README.md
      ./LICENSE
      ./pykefcontrol
      ./tests
      ./scripts
    ];
  };

  build-system = [ hatchling ];

  dependencies = [
    aiohttp
    urllib3
  ];

  optional-dependencies.discovery = [ zeroconf ];

  nativeCheckInputs = [
    pytestCheckHook
    pytest-asyncio
    pytest-timeout
    trustme
  ];

  pythonImportsCheck = [ "pykefcontrol" ];

  meta = {
    description = "Control KEF W2-platform wireless speakers (LS50 Wireless II, LS60, LSX II, XIO, LS LUXE...)";
    homepage = "https://github.com/N0ciple/pykefcontrol";
    license = lib.licenses.mit;
    mainProgram = "pykefcontrol";
  };
}
