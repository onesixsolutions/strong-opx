---
name: strong-opx
description: >
  Use when working with Strong-OpX — a CLI tool that unifies cloud deployments across AWS, Azure, and
  Google Cloud. Covers installation, project and environment setup, vars and secrets management, deploy,
  Terraform, Helm, Kubernetes, Docker image builds, compute instance management, SSH/SCP, and AWS MFA.
  Auto-invokes when strong-opx.yml is present or user asks about strong-opx commands.
---

# Strong-OpX Agent Guide

Strong-OpX (`strong-opx`) unifies infrastructure management across cloud providers. Projects are defined by
`strong-opx.yml` at the repo root. Per-environment configuration lives in `environments/<env>/config.yml`.

---

## 1. Verify Installation

```bash
strong-opx --version
```

If missing, install into a venv:

```bash
python -m venv strong-opx-venv
source strong-opx-venv/bin/activate
pip install strong-opx          # from PyPI
# or from source:
pip install -e ./strong-opx
```

Add alias to shell profile so the venv doesn't need to be activated manually:

```bash
alias strong-opx=$(which strong-opx)
```

---

## 2. Project Lifecycle

### Create a new project
```bash
strong-opx project create <project-name>
```
Creates `<project-name>/` directory with `strong-opx.yml` and registers it in the global registry.

### Register an existing project
```bash
git clone git@github.com:org/<project-name>
strong-opx project register ./<project-name>
```

### Scaffold an environment
Run from inside the project directory:
```bash
strong-opx g environment
```
Creates `environments/<env>/config.yml`. Typical names: `staging`, `production`, `development`, `default`.

---

## 3. `strong-opx.yml` Structure

```yaml
name: <project-name>          # Required. Do not change after init.

strong_opx:                   # Optional
  required_version: ">=1.4"
  templating_engine: basic    # 'basic' (default) or 'jinja2'

# Provider config — pick one:
aws:
  region: us-east-1
# azure:
#   subscription_id: ...
#   resource_group: ...
#   tenant_id: ...
# gcloud:
#   project: my-gcp-project
#   compute_region: us-central1

secret:
  provider: aws_ssm           # aws_ssm | keyvault (Azure)
  parameter: my-secret-{{ ENVIRONMENT }}
  secret_length: 24

vars: vars/{{ ENVIRONMENT }}.yml
# OR per-environment:
# vars:
#   production: vars/prod.yml
#   staging:
#     - vars/common.yml
#     - vars/staging.yml
```

---

## 4. `environments/<env>/config.yml` Structure

```yaml
vars:
  KEY: value                  # Non-secret vars only

# Kubernetes platform (auto-selected when this key is present):
kubernetes:
  cluster_name: my-eks-cluster
  service_role: arn:aws:iam::...

# Generic/VM platform (auto-selected when 'hosts' is present):
hosts:
  primary:
    - 10.0.1.10
  bastion:
    - 52.1.2.3               # Special group — routes private-IP connections

# SSH config (required for Generic platform):
ssh:
  user: ubuntu
  key: ~/.ssh/id_rsa

# AWS override for this environment:
aws:
  region: us-west-2
  aws_profile: my-profile
```

---

## 5. Vars and Secrets

### Encrypt a variable value
```bash
strong-opx vars encrypt --value "my-secret-value"
```
Prints the encrypted string — paste it into the vars file manually.

### Encrypt named variables from vars files
```bash
strong-opx vars encrypt --vars VAR_NAME_1 VAR_NAME_2
```

### Decrypt variables
> **Ask the user before decrypting.** Decryption exposes secrets in the terminal.

```bash
strong-opx vars decrypt --vars VAR_NAME_1
```

---

## 6. Deploy

> **Always confirm with the user before deploying to production or staging.**

```bash
strong-opx deploy --project <project-name> --env <env>
# Deploy a specific kubectl subdirectory:
strong-opx deploy --project <project-name> --env <env> kubectl/subdir
```

Kubernetes platform: scans `kubectl/` directory and applies all YAMLs. Files named `foo.<env>.yml`
are applied only to the matching environment.

Generic platform: runs Ansible playbooks via `ansible-playbook`.

---

## 7. Terraform

```bash
# Safe — always okay to run:
strong-opx terraform init --env <env>
strong-opx terraform plan --env <env>

# Destructive — confirm with user before running:
strong-opx terraform apply --env <env>
strong-opx terraform destroy --env <env>

# Pass extra args after --:
strong-opx terraform apply --env <env> -- -var="key=value"
```

Backend config goes in `environments/<env>/.tfbackend` (plain key=value, no block wrapper).
Shared `.tf` files go in `terraform/` at project root.

---

## 8. Helm

```bash
# Apply all charts defined in strong-opx.yml:
strong-opx helm apply --env <env>

# Run any helm command (after --):
strong-opx helm --env <env> -- list
strong-opx helm --env <env> -- repo update
```

Helm charts are configured in `strong-opx.yml` under the `helm:` key:

```yaml
helm:
  repos:
    autoscaler: https://kubernetes.github.io/autoscaler
  charts:
    - name: cluster-autoscaler
      repo: autoscaler
      chart: cluster-autoscaler
      version: "9.29.0"
      namespace: kube-system
      environment: production   # optional: restrict to one env
      values: helm/autoscaler-values.yml
```

---

## 9. Kubernetes / kubectl

```bash
# Run any kubectl command (after --):
strong-opx kubectl --env <env> -- get pods -n default

# Refresh kubeconfig (after cluster redeploy):
strong-opx kubectl --env <env> --update-kubeconfig -- version

# Install a K8s plugin:
strong-opx k8s <plugin> install --env <env>

# Run a plugin operation:
strong-opx k8s <plugin> <operation> --env <env>
```

---

## 10. Docker

```bash
# Build only:
strong-opx docker:build --env <env>

# Build and push to registry:
strong-opx docker:build --env <env> --push
```

Images are tagged: `latest`, `<env>-latest`, and `<env>-<revision>.<git-sha>`.
Note: if two environments share the same AWS region and image name, `latest` will collide — use `<env>-latest`.

---

## 11. Packer

```bash
strong-opx packer build --env <env>
# Extra packer flags passed directly:
strong-opx packer -debug build --env <env>
```

---

## 12. Compute Instances

```bash
# Safe — read-only:
strong-opx compute status --env <env>

# Confirm with user before running:
strong-opx compute start --env <env>
strong-opx compute stop --env <env>
strong-opx compute restart --env <env>
```

---

## 13. SSH / SCP

```bash
# Connect by IP:
strong-opx ssh <private-ip> --env <env>

# Connect by host group:
strong-opx ssh primary --env <env>

# Connect to nth host in a group:
strong-opx ssh primary:1 --env <env>

# Pass extra ssh flags after --:
strong-opx ssh primary --env <env> -- -L 8080:localhost:8080

# Download file from server:
strong-opx scp <host> @</remote/path/file> /local/dir --env <env>

# Upload file to server:
strong-opx scp <host> /local/file @</remote/path/> --env <env>
```

---

## 14. Ansible Playbook

```bash
# Run a playbook (inventory set automatically from environment):
strong-opx playbook <playbook.yml> --env <env>

# Pass extra ansible-playbook flags after --:
strong-opx playbook deploy.yml --env <env> -- --tags deploy
```

---

## 15. Run Remote Command

```bash
strong-opx run <host> --env <env> -- <command> [args]
```

Runs the command on the remote server over SSH and streams output locally.

---

## 16. AWS Setup

### Configure AWS profile (prompts for keys, detects MFA):
```bash
strong-opx aws:configure
```
Stores credentials in `~/.aws/credentials`. MFA profiles are suffixed with `--mfa`.

### Refresh temporary MFA credentials:
```bash
strong-opx aws:mfa --token <6-digit-code> --profile <profile-name>
# Optional duration (seconds):
strong-opx aws:mfa --token 123456 --profile my-profile --duration 3600
```

---

## 17. Config

```bash
# View a config value:
strong-opx config <key>

# Set a config value:
strong-opx config <key> <value>
```

Available config keys: `ssh.user`, `ssh.key`, `git.ssh.key`, `terraform.executable`,
`docker.executable`, `ansible.playbook.executable`, `aws.aws_profile`, `kubectl.executable`.

---

## 18. Templating

Strong-OpX supports two engines (`basic` default, `jinja2` opt-in via `strong_opx.templating_engine`).

Basic engine delimiters:
- `{{ variable }}` — print variable
- `{% if condition %}...{% endif %}` — conditional
- `{% for x in list %}...{% endfor %}` — loop
- `{# comment #}` — ignored

Built-in variables always available: `ENVIRONMENT`.

Filters: `{{ value|uppercase }}`, `|lowercase`, `|titlecase`, `|base64`, `|datetime`, `|join:', '`.

---

## Permission Guidelines

| Operation | Permission level |
|---|---|
| `status`, `plan`, `init`, `config` (read) | Safe — run freely |
| `start`, `stop`, `restart` compute | Confirm with user |
| `deploy`, `helm apply` | Confirm with user; extra caution for production |
| `terraform apply`, `terraform destroy` | Always confirm with user |
| `vars decrypt` | Always confirm — exposes secrets in terminal |
| `docker:build --push` | Confirm for production environments |
