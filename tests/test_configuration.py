"""Configuration guard.

Fails when a setting exists in code or IaC but is missing from
docs/07-configuration-reference.md, or when the azd wrapper stops passing a
main.bicep parameter through.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "07-configuration-reference.md").read_text(encoding="utf-8")
INFRA = ROOT / "infra"


def _documented(name: str) -> bool:
    return f"`{name}`" in DOC


def _bicep_params(path: Path) -> list[str]:
    return re.findall(r"^param\s+(\w+)\s", path.read_text(encoding="utf-8"), re.M)


def _bicep_outputs(path: Path) -> list[str]:
    return re.findall(r"^output\s+(\w+)\s", path.read_text(encoding="utf-8"), re.M)


def test_azd_parameters_are_quoted_and_documented():
    params = json.loads((INFRA / "azd.parameters.json").read_text(encoding="utf-8"))["parameters"]
    missing = []
    for name, spec in params.items():
        value = spec["value"]
        assert isinstance(value, str), f"{name}: azd substitutions must be quoted strings"
        for var in re.findall(r"\$\{(\w+)", value):
            if not _documented(var):
                missing.append(var)
    assert not missing, f"azd variables missing from 07-configuration-reference.md: {missing}"


def test_azd_bicep_params_all_have_substitutions():
    params = json.loads((INFRA / "azd.parameters.json").read_text(encoding="utf-8"))["parameters"]
    missing = [p for p in _bicep_params(INFRA / "azd.bicep") if p not in params]
    assert not missing, f"azd.bicep params without an azd.parameters.json entry: {missing}"


def test_azd_bicep_passes_every_main_bicep_parameter():
    azd = (INFRA / "azd.bicep").read_text(encoding="utf-8")
    block = azd[azd.index("module app 'main.bicep'"):]
    block = block[block.index("params: {"):]
    passed = set(re.findall(r"^\s{4}(\w+):", block, re.M))
    missing = [p for p in _bicep_params(INFRA / "main.bicep") if p not in passed]
    assert not missing, f"azd.bicep does not pass these main.bicep params: {missing}"


def test_outputs_are_upper_snake_and_documented():
    outputs = _bicep_outputs(INFRA / "azd.bicep")
    assert outputs, "azd.bicep has no outputs"
    bad = [o for o in outputs if not re.fullmatch(r"[A-Z][A-Z0-9_]*", o)]
    assert not bad, f"azd outputs must be UPPER_SNAKE_CASE: {bad}"
    missing = [o for o in outputs if not _documented(o)]
    assert not missing, f"outputs missing from 07-configuration-reference.md: {missing}"


def test_main_bicep_params_documented():
    missing = [p for p in _bicep_params(INFRA / "main.bicep") if not _documented(p)]
    assert not missing, f"main.bicep params missing from 07-configuration-reference.md: {missing}"


def test_hook_variables_documented():
    names = set()
    for ps1 in (INFRA / "hooks").glob("*.ps1"):
        names |= set(re.findall(r"Get-EnvValue\s+-Name\s+'(\w+)'", ps1.read_text(encoding="utf-8")))
    assert names, "no hook variables found"
    missing = sorted(n for n in names if not _documented(n))
    assert not missing, f"hook variables missing from 07-configuration-reference.md: {missing}"


def test_runtime_env_vars_documented_and_in_env_example():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    names = set()
    for py in list(ROOT.glob("*.py")) + list((ROOT / "session_handlers").glob("*.py")) + \
            list((ROOT / "local_clients").glob("*.py")):
        names |= set(re.findall(r"os\.(?:getenv|environ\.get)\(\s*\"(\w+)\"", py.read_text(encoding="utf-8")))
    assert "AZURE_AI_ENDPOINT" in names
    missing_doc = sorted(n for n in names if not _documented(n))
    missing_example = sorted(n for n in names if not re.search(rf"^#?\s*{n}=", env_example, re.M))
    assert not missing_doc, f"runtime variables missing from 07-configuration-reference.md: {missing_doc}"
    assert not missing_example, f"runtime variables missing from .env.example: {missing_example}"


def test_tooling_and_compose_vars_documented():
    names = set()
    for py in (ROOT / "scripts").glob("*.py"):
        names |= set(re.findall(r"os\.environ\.get\(\s*\"(\w+)\"", py.read_text(encoding="utf-8")))
    names |= set(re.findall(r"\$\{(\w+)", (ROOT / "docker-compose.local.yml").read_text(encoding="utf-8")))
    missing = sorted(n for n in names if not _documented(n))
    assert not missing, f"tooling / compose variables missing from 07-configuration-reference.md: {missing}"


def test_default_model_is_consistent():
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    default = re.search(r'os\.getenv\("VOICE_LIVE_MODEL",\s*"([^"]+)"\)', config).group(1)
    example = re.search(r"^VOICE_LIVE_MODEL=(\S+)", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M).group(1)
    assert default == example, f"config.py default {default!r} != .env.example {example!r}"
    assert f"| `VOICE_LIVE_MODEL` | `{default}` |" in DOC, "07 must state the same default model"
