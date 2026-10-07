"""azd template guards.

Static only: never signs in and never calls Azure. The hook tests run
preprovision.ps1 with deliberately bad input and expect a clean failure that
happens before the Azure CLI is touched.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
HOOKS = INFRA / "hooks"
PWSH = shutil.which("pwsh")


def test_azure_yaml_wiring():
    text = (ROOT / "azure.yaml").read_text(encoding="utf-8")
    assert re.search(r"^infra:\s*\n\s+provider:\s*bicep\s*\n\s+path:\s*infra\s*\n\s+module:\s*azd\s*$", text, re.M)
    for hook in ("preprovision", "postprovision"):
        block = text[text.index(f"  {hook}:"):]
        block = block[:block.index("continueOnError")]
        assert "shell: pwsh" in block and f"./infra/hooks/{hook}.ps1" in block, hook
    assert text.count("continueOnError: false") == 2


def test_azd_bicep_is_subscription_scoped():
    azd = (INFRA / "azd.bicep").read_text(encoding="utf-8")
    assert "targetScope = 'subscription'" in azd
    assert "module app 'main.bicep'" in azd
    assert "'azd-env-name': environmentName" in azd


def _bicep_allowed_regions() -> list[str]:
    main = (INFRA / "main.bicep").read_text(encoding="utf-8")
    block = main[main.index("@allowed(["):main.index("param location")]
    return re.findall(r"'([a-z0-9]+)'", block)


def test_region_allow_list_matches_hooks():
    common = (HOOKS / "common.ps1").read_text(encoding="utf-8")
    block = common[common.index("$script:AllowedRegions"):common.index(")", common.index("$script:AllowedRegions"))]
    hook_regions = re.findall(r"'([a-z0-9]+)'", block)
    assert sorted(hook_regions) == sorted(_bicep_allowed_regions())
    tier1 = re.findall(r"'([a-z0-9]+)'", common[common.index("$script:Tier1Regions"):].split("\n")[0])
    assert set(tier1) <= set(hook_regions)
    assert "northeurope" not in hook_regions, "northeurope has no Voice Live models (Learn, 2026-10-07)"


def test_gitignore_covers_local_state():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for entry in (".env", ".azure/", "demo-ids.local.json", "*.local.json"):
        assert entry in ignore, entry


def test_demo_ids_template_has_no_real_ids():
    text = (ROOT / "demo-ids.template.json").read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["_template"] is True and "workload" in doc
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I)


def _run_hook(script: str, extra: dict) -> subprocess.CompletedProcess:
    keep = {k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT",
                                                                    "USERPROFILE", "HOME", "PSMODULEPATH")}
    env = {**keep, **extra}
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(HOOKS / script)],
                          capture_output=True, text=True, env=env, timeout=120)


def test_hooks_parse():
    if not PWSH:
        return  # PowerShell 7 not installed on this runner
    for ps1 in [*HOOKS.glob("*.ps1"), INFRA / "deploy.ps1"]:
        cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{ps1}', [ref]$null, [ref]$e); if ($e) {{ $e | % {{ $_.ToString() }}; exit 1 }}")
        r = subprocess.run([PWSH, "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"{ps1.name}: {r.stdout}{r.stderr}"


GOOD = {"AZURE_ENV_NAME": "voice-avatar-test", "AZURE_LOCATION": "eastus2", "WORKLOAD_PREFIX": "avla",
        "DEMO_ENVIRONMENT": "dev"}


def test_preprovision_rejects_bad_env_name_before_az():
    if not PWSH:
        return
    r = _run_hook("preprovision.ps1", {**GOOD, "AZURE_ENV_NAME": "Bad-Name"})
    assert r.returncode != 0
    assert "AZURE_ENV_NAME must be" in r.stdout + r.stderr


def test_preprovision_rejects_bad_inputs():
    if not PWSH:
        return
    cases = {"WORKLOAD_PREFIX": ("Toolong123", "WORKLOAD_PREFIX must be"),
             "AZURE_LOCATION": ("northeurope", "AZURE_LOCATION must be one of"),
             "DEMO_ENVIRONMENT": ("staging", "DEMO_ENVIRONMENT must be one of"),
             "WRITE_DOTENV": ("yes", "WRITE_DOTENV must be one of")}
    for var, (value, message) in cases.items():
        r = _run_hook("preprovision.ps1", {**GOOD, var: value})
        assert r.returncode != 0, var
        assert message in r.stdout + r.stderr, f"{var}: {r.stdout}{r.stderr}"


def test_preprovision_requires_tenant_and_subscription():
    if not PWSH:
        return
    r = _run_hook("preprovision.ps1", dict(GOOD))
    assert r.returncode != 0
    assert "AZURE_TENANT_ID and AZURE_SUBSCRIPTION_ID must both be set" in r.stdout + r.stderr


def test_postprovision_requires_endpoint():
    if not PWSH:
        return
    r = _run_hook("postprovision.ps1", {"AZURE_ENV_NAME": "voice-avatar-test"})
    assert r.returncode != 0
    assert "AZURE_AI_ENDPOINT output is missing" in r.stdout + r.stderr
