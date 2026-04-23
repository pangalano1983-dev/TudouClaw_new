"""通用门禁 Day 3 — cloud_delivery.yaml 预设行为测试.

Loads the shipped ``data/roles/cloud_delivery.yaml`` and verifies that
the patterns it declares actually block the commands they're meant to.

This is the "specification" of what cloud_delivery promises to protect
against — if someone loosens a pattern and breaks one of these, we want
the test to fail loudly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from app.auth import ToolPolicy           # noqa: E402
from app.role_preset_v2 import load_role_yaml   # noqa: E402
from app.role_preset_registry import RolePresetRegistry  # noqa: E402


_YAML = Path(_ROOT) / "data" / "roles" / "cloud_delivery.yaml"


@pytest.fixture(scope="module")
def preset():
    p = load_role_yaml(_YAML)
    assert p is not None, f"preset failed to load from {_YAML}"
    return p


@pytest.fixture
def tp_with_patterns(preset):
    tp = ToolPolicy()
    reg = RolePresetRegistry()
    reg._presets[preset.role_id] = preset
    reg.register_command_patterns_to_policy(tp)
    return tp


# ── preset structure ───────────────────────────────────────────────


def test_preset_loaded_shape(preset):
    assert preset.role_id == "cloud_delivery"
    assert preset.display_name == "云交付"
    assert preset.execution_mode == "plan_only"
    assert preset.category == "operations"
    assert preset.icon == "cloud"
    # Has a substantial system prompt (not empty).
    assert len(preset.system_prompt) > 200
    assert "plan_only" in preset.system_prompt or "plan" in preset.system_prompt


def test_preset_allows_read_and_plan_tools(preset):
    # Important: agent MUST be able to read / write files in workspace
    # (to produce the delivery package) and run tests (to verify scripts).
    for tool in ("read_file", "write_file", "bash", "run_tests"):
        assert tool in preset.allowed_tools, f"{tool} should be allowed"


def test_preset_has_all_expected_pattern_labels(preset):
    labels = {cp["label"] for cp in preset.command_patterns}
    # Core IaC write operations
    assert "cd_tf_apply" in labels
    assert "cd_tf_destroy" in labels
    assert "cd_tf_state" in labels
    # K8s write ops
    assert "cd_kubectl_write" in labels
    assert "cd_helm_write" in labels
    # Remote exec
    assert "cd_ansible_playbook" in labels
    assert "cd_ansible_adhoc_write" in labels
    assert "cd_ssh_remote" in labels
    # Cloud CLI writes
    assert "cd_aws_write" in labels
    assert "cd_aliyun_write" in labels
    assert "cd_gcloud_write" in labels
    # DB writes
    assert "cd_sql_ddl" in labels
    assert "cd_db_exec" in labels


def test_all_patterns_are_valid_regex(preset):
    import re as _re
    for cp in preset.command_patterns:
        pat = cp["pattern"]
        _re.compile(pat, _re.IGNORECASE)   # raises if invalid


# ── negative: these commands must be blocked ──────────────────────


@pytest.mark.parametrize("cmd,expected_label", [
    # Terraform writes
    ("terraform apply", "cd_tf_apply"),
    ("terraform apply -auto-approve", "cd_tf_apply"),
    ("  terraform apply ./main.tf", "cd_tf_apply"),
    ("TERRAFORM APPLY", "cd_tf_apply"),
    ("terraform destroy", "cd_tf_destroy"),
    ("terraform state rm aws_instance.foo", "cd_tf_state"),
    ("terraform state mv aws_s3.a aws_s3.b", "cd_tf_state"),
    ("terraform state push terraform.tfstate", "cd_tf_state"),

    # Kubernetes writes
    ("kubectl apply -f deploy.yaml", "cd_kubectl_write"),
    ("kubectl delete pod webapp", "cd_kubectl_write"),
    ("kubectl replace -f updated.yaml", "cd_kubectl_write"),
    ("kubectl rollout restart deploy/webapp", "cd_kubectl_write"),
    ("kubectl rollout undo deploy/webapp", "cd_kubectl_write"),
    ("kubectl create secret generic foo --from-literal=k=v",
     "cd_kubectl_write"),
    ("kubectl scale deploy/webapp --replicas=3", "cd_kubectl_write"),

    # Helm writes
    ("helm install myapp ./chart", "cd_helm_write"),
    ("helm upgrade myapp ./chart", "cd_helm_write"),
    ("helm rollback myapp 1", "cd_helm_write"),
    ("helm uninstall myapp", "cd_helm_write"),

    # Remote exec — playbook always blocked (unless --check)
    ("ansible-playbook deploy.yml", "cd_ansible_playbook"),
    ("ansible-playbook -i prod.ini site.yml", "cd_ansible_playbook"),
    # Ad-hoc shell/command/raw/script modules = write ops
    ("ansible all -m shell -a 'rm -rf /tmp/x'", "cd_ansible_adhoc_write"),
    ("ansible webservers -m command -a 'systemctl restart nginx'",
     "cd_ansible_adhoc_write"),
    ("ansible all -m raw -a 'uptime'", "cd_ansible_adhoc_write"),
    ("ssh deploy@prod.example.com", "cd_ssh_remote"),
    ("scp file.tgz deploy@prod:/tmp/", "cd_ssh_remote"),
    ("rsync -av ./dist root@prod:/var/www/", "cd_ssh_remote"),

    # Cloud CLIs
    ("aws ec2 create-instance --image-id ami-123", "cd_aws_write"),
    ("aws s3 put-object --bucket x --key y", "cd_aws_write"),
    ("aws iam delete-user --user-name foo", "cd_aws_write"),
    ("aliyun ecs CreateInstance --Name foo", "cd_aliyun_write"),
    ("aliyun ecs DeleteInstance --InstanceId i-xx", "cd_aliyun_write"),
    ("gcloud compute instances create myvm", "cd_gcloud_write"),
    ("gcloud run deploy myapp", "cd_gcloud_write"),

    # SQL / DB
    ("DROP TABLE users", "cd_sql_ddl"),
    ("TRUNCATE TABLE orders", "cd_sql_ddl"),
    ("ALTER SCHEMA public RENAME TO p2", "cd_sql_ddl"),
    ("psql -h prod --execute \"DROP TABLE x\"", "cd_db_exec"),
    ("mysql -h prod --execute \"DELETE FROM x\"", "cd_db_exec"),
])
def test_dangerous_command_blocked(tp_with_patterns, cmd, expected_label):
    m = tp_with_patterns.find_matching_command_pattern(
        {"command": cmd},
        agent_role="cloud_delivery",
    )
    assert m is not None, f"command should be blocked: {cmd!r}"
    assert m["label"] == expected_label, (
        f"{cmd!r} matched {m['label']!r} but expected {expected_label!r}"
    )
    # All labels in this preset mean DENY (not needs_approval).
    assert m["verdict"] == "deny"
    # Tag includes the role for downstream artifact grouping.
    assert "cloud_delivery" in (m.get("tags") or [])


# ── positive: read-only / plan commands must NOT be blocked ──────


@pytest.mark.parametrize("cmd", [
    # Plan / diff / validate — explicitly safe
    "terraform plan",
    "terraform plan -out=x.tfplan",
    "terraform validate",
    "terraform fmt -check",
    "kubectl diff -f deploy.yaml",
    "kubectl get pods",
    "kubectl describe deploy/webapp",
    "kubectl logs webapp-xxx",
    "helm template myapp ./chart",
    "helm lint ./chart",
    "helm status myapp",
    "ansible-playbook deploy.yml --check",     # dry-run
    "ansible --version",
    "ansible all -m ping",                     # harmless connectivity probe
    "ansible all -m setup --tree /tmp/facts",  # read-only facts module
    # Cloud CLI reads
    "aws ec2 describe-instances",
    "aws s3 ls",
    "aws iam list-users",
    "aliyun ecs DescribeInstances",
    "gcloud compute instances list",
    "gcloud config get-value project",
    # SQL reads (not DDL)
    "SELECT * FROM users LIMIT 10",
    # DB connect without --execute
    "psql -h localhost",
    "mysql -u root -p",
    # General shell utilities
    "ls -la",
    "cat terraform.tfplan",
    "pytest tests/",
    "python generate_iac.py",
])
def test_safe_command_not_blocked(tp_with_patterns, cmd):
    m = tp_with_patterns.find_matching_command_pattern(
        {"command": cmd},
        agent_role="cloud_delivery",
    )
    assert m is None, (
        f"cloud_delivery should NOT block {cmd!r}, "
        f"but it hit {m and m.get('label')!r}"
    )


# ── scope correctness: other roles are NOT affected ──────────────


def test_cloud_delivery_patterns_isolated_to_role(tp_with_patterns):
    # A coder should be allowed to terraform apply (no role-scoped pattern
    # for them), so the cloud_delivery patterns must not leak.
    m = tp_with_patterns.find_matching_command_pattern(
        {"command": "terraform apply"},
        agent_role="coder",
    )
    assert m is None


def test_cloud_delivery_registered_as_role_scope(preset):
    tp = ToolPolicy()
    reg = RolePresetRegistry()
    reg._presets[preset.role_id] = preset
    reg.register_command_patterns_to_policy(tp)
    for cp in tp.list_command_patterns():
        assert cp["scope"] == "role:cloud_delivery", (
            f"expected role-scoped pattern, got {cp}"
        )


def test_full_chain_returns_deny_for_cloud_delivery(tp_with_patterns):
    """End-to-end: ToolPolicy.check_tool should return ('deny', reason)
    for a cloud_delivery agent running terraform apply — through the
    full rule chain, not just the lookup helper."""
    # We need a way to make check_tool see the role. The rule itself
    # uses hub.get_agent(...).role — since that requires a hub, we
    # emulate the lookup by patching.
    import app.auth_rules.command_patterns as cp_rule

    class _Stub:
        class _Agent:
            role = "cloud_delivery"
        agents = {"a-x": _Agent()}

    _hub = _Stub()
    import app.hub as hub_mod
    _orig = getattr(hub_mod, "get_hub", None)
    hub_mod.get_hub = lambda: _hub
    try:
        verdict, reason = tp_with_patterns.check_tool(
            "bash",
            {"command": "terraform apply -auto-approve"},
            agent_id="a-x",
        )
        assert verdict == "deny"
        assert "terraform" in reason.lower() or "cd_tf" in reason.lower() or "prod" in reason.lower()
    finally:
        if _orig:
            hub_mod.get_hub = _orig
