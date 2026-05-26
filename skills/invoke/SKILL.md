---
description: >
  Use when working with Strong-OpX — a CLI tool that unifies cloud deployments across AWS, Azure, and
  Google Cloud. Covers installation, project and environment setup, vars and secrets management, deploy,
  Terraform, Helm, Kubernetes, Docker image builds, compute instance management, SSH/SCP, and AWS MFA.
  Auto-invokes when strong-opx.yml is present or user asks about strong-opx commands.
---

# Strong-OpX Agent Guide

Strong-OpX (`strong-opx`) unifies infrastructure management across cloud providers. Projects are defined by
`strong-opx.yml` at the repo root. Per-environment configuration lives in `environments/<env>/config.yml` by
default, but if `dirname` is set in `strong-opx.yml`, all infra paths are prefixed with that directory
(e.g. `dirname: ops` → `ops/environments/<env>/config.yml`).

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

### How the active project/environment is resolved
When no `--project` flag is given, strong-opx resolves the project in this order:

1. **Directory tree walk** — walks up from the current directory looking for `strong-opx.yml`. If found and
   the project is registered, it is used. Running commands from inside the project directory Just Works.
2. **`STRONG_OPX_PROJECT` env var** — used if no config file is found in the tree.
3. **Interactive registry prompt** — if neither of the above resolves, the user is prompted to pick from
   all registered projects.

If the found `strong-opx.yml` names a project that isn't registered (or is registered at a different path),
an error is raised — fix it with `strong-opx project register <path>`.

When no `--env` flag is given, strong-opx resolves the environment in this order:

1. **Auto-select** — if the project has exactly one environment, it is used automatically.
2. **`STRONG_OPX_ENVIRONMENT` env var** — used when multiple environments exist.
3. **Interactive prompt** — if the env var is not set, the user is prompted to pick from available environments.

### Scaffold an environment
Run from inside the project directory:
```bash
strong-opx g environment
```
Creates `environments/<env>/config.yml` (or `<dirname>/environments/<env>/config.yml` if `dirname` is set).
Typical names: `staging`, `production`, `development`, `default`.

---

## 3. `strong-opx.yml` Structure

```yaml
name: <project-name>          # Required. Do not change after init.
dirname: ops                  # Optional. Moves all infra paths under this dir.
                              # e.g. ops/environments/<env>/config.yml,
                              #      ops/terraform/, ops/kubectl/, etc.

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

# AWS override for this environment:
aws:
  region: us-west-2
```

---

## 5. Vars and Secrets

### How vars work

Vars are key-value pairs made available to every wrapped tool. They are assembled from three sources,
merged in this order (later sources win):

1. **Built-ins** — `ENVIRONMENT` is always available.
2. **Project vars files** — paths specified under `vars:` in `strong-opx.yml`. These files can contain
   encrypted secrets.
3. **Environment config vars** — `vars:` block inside `environments/<env>/config.yml`. Plain values only;
   no secrets here. These take final precedence, making them the right place for per-environment overrides.

   This file is often **generated by Terraform** so that infrastructure outputs (cluster names, IPs, subnet
   IDs, etc.) flow automatically into subsequent `deploy` or `kubectl` runs. A typical pattern uses a
   `null_resource` with a `local-exec` provisioner to write the file on every `terraform apply`:

   ```hcl
   resource "null_resource" "env-config" {
     triggers = { always_run = timestamp() }

     provisioner "local-exec" {
       command = <<HEREDOC
   cat<<EOF > ${path.module}/../environments/${var.ENVIRONMENT}/config.yml
   # Generated — changes will be overwritten on next terraform apply
   aws:
     region: ${var.AWS_REGION}
   kubernetes:
     cluster_name: ${local.cluster_name}
   vars:
     VPC_ID: ${module.vpc.vpc_id}
     REDIS_HOST: ${aws_elasticache_cluster.redis.cache_nodes[0].address}
   EOF
   HEREDOC
     }
   }
   ```

   Because `ENVIRONMENT` and other vars are auto-passed to Terraform as `TF_VAR_*`, the `var.ENVIRONMENT`
   reference above resolves without any extra wiring.

### Vars file path formats

```yaml
# Single path (template string supported):
vars: vars/{{ ENVIRONMENT }}.yml

# Per-environment map:
vars:
  production: vars/prod.yml
  staging:
    - vars/common.yml
    - vars/staging.yml

# Mixed list (common + per-env overrides):
vars:
  - vars/common.yml
  - vars/{{ ENVIRONMENT }}.yml
  - production: vars/sensitive.yml
    staging: vars/fake.yml
```

If a specified path is missing, a warning is shown (not an error).

### Vars file format

```yaml
DB_HOST: my-database.example.com
IMAGE_TAG: latest

DB_PASSWORD: !vault |
  $STRONG_OPX_VAULT;1.1;AES256
  66616131303039623636633836343466663534303236613561336663336531356233346563393330
  ...
```

Encrypted values are decrypted automatically before being passed to any tool — no manual step required.

### How vars are passed to each tool

| Tool | Mechanism |
|---|---|
| Terraform | `TF_VAR_<NAME>` env vars — only `variable` blocks in `terraform/*.tf`; missing required raise error |
| Packer | `PKR_VAR_<NAME>` env vars — same behaviour, scans `packer/` files for `variable` blocks |
| Ansible | `--extra-vars` JSON file — all vars auto-passed |
| Docker build | Only vars explicitly listed via `--build-arg VAR1 VAR2` are passed as build args |
| kubectl / Helm | Files rendered by template engine first; vars substituted in place, not passed to the tool |

### Encrypting and decrypting

```bash
# Encrypt a value directly:
strong-opx vars encrypt --value "my-secret-value"

# Encrypt named variables already in vars files:
strong-opx vars encrypt --vars VAR_NAME_1 VAR_NAME_2
```

Both commands print the encrypted value(s) to the console only — the vars file is **not** updated
automatically. Copy the output and replace the plain-text value in the file manually.

> **Ask the user before decrypting.** Decryption exposes all variables including secrets in the terminal.

```bash
strong-opx vars decrypt
```

---

## 6. Deploy

> **Always confirm with the user before deploying to production or staging.**

```bash
strong-opx deploy --project <project-name> --env <env>
# Deploy a specific kubectl subdirectory:
strong-opx deploy --project <project-name> --env <env> kubectl/subdir
```

Kubernetes platform: scans `kubectl/` directory (or `<dirname>/kubectl/` if `dirname` is set) and applies
all YAMLs. Files named `foo.<env>.yml` are applied only to the matching environment.

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

Backend config goes in `environments/<env>/.tfbackend` (or `<dirname>/environments/<env>/.tfbackend`).
Shared `.tf` files go in `terraform/` (or `<dirname>/terraform/`) at project root.

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
The `--profile` here is the base profile name (without `--mfa`). Long-term credentials stay in
`my-profile--mfa`; temporary credentials are written to `my-profile` — so callers always use the plain
profile name (e.g. `my-profile`), not `my-profile--mfa`.

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
