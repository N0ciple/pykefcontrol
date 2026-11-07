{
  lib,
  buildPythonPackage,
  hatchling,
  aiohttp,
  requests,
}:

buildPythonPackage {
  pname = "pykefcontrol";
  version = "0.9.3";
  pyproject = true;

  src = lib.cleanSource ./.;

  build-system = [ hatchling ];

  dependencies = [
    aiohttp
    requests
  ];

  pythonImportsCheck = [ "pykefcontrol" ];

  meta = {
    description = "Python library for controlling KEF speakers (LS50W2, LSX2, LS60)";
    homepage = "https://github.com/N0ciple/pykefcontrol";
    license = lib.licenses.mit;
  };
}
