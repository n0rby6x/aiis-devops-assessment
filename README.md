# DevOps Homework — Solution

A small Flask service, containerized, deployed to Kubernetes via Helm, provisioned with
Terraform, built and shipped through a GitHub Actions pipeline.

```
.
├── app/                        # Python (Flask) application + Dockerfile + tests
├── helm/                       # Helm chart for the app
├── terraform/                  # Terraform that provisions the namespace + helm_release
└── .github/workflows/ci.yml    # CI/CD pipeline (GitHub Actions)
```

---

## GitHub repository setup (do this once, before pushing)

The pipeline expects three branches, one per environment, and a handful of secrets/variables.
None of this is guessable from the code — set these up once in the repo before the first push.

### Branches

Create three branches: **`dev`**, **`uat`**, **`main`**. The workflow derives the target
environment straight from the branch name:

| Branch  | Environment | Namespace     |
|---------|-------------|---------------|
| `dev`   | `dev`       | `myapp-dev`   |
| `uat`   | `uat`       | `myapp-uat`   |
| `main`  | `prod`      | `myapp-prod`  |

Right now, only **`dev`** is actively used — pushing to `uat`/`main` will run through the
exact same pipeline (that's the point of deriving everything from the branch), you just
don't need to touch them yet.

### GitHub Environments — and their secrets/variables

Under **Settings → Environments**, create three environments named exactly **`dev`**,
**`uat`**, **`prod`** (matching the table above — note `main` branch maps to a `prod`
*environment*, not an environment literally called `main`). No protection rules are needed
on `dev` for now; once real deploys exist, add **required reviewers** to `uat`/`prod` for a
manual approval gate (that's the GitHub equivalent of GitLab's `when: manual`).

Everything environment-specific lives **on the environment itself**, not in the workflow
file or as repo-wide config — open each environment's page and you'll find separate
**Environment secrets** and **Environment variables** sections. This is what makes
`uat`/`prod` a config change later, not a code change (different AWS account/region per
environment, for example, just works).

For **`dev`** (the only one you need right now), add:

**Environment secrets** (Settings → Environments → `dev` → Environment secrets):

| Name                     | Value                    |
|--------------------------|--------------------------|
| `AWS_ACCESS_KEY_ID`      | your AWS access key      |
| `AWS_SECRET_ACCESS_KEY`  | your AWS secret key      |

**Environment variables** (Settings → Environments → `dev` → Environment variables):

| Name                | Example value    | What it's for                                         |
|---------------------|------------------|--------------------------------------------------------|
| `AWS_REGION`         | `eu-central-1`   | passed to `configure-aws-credentials` and `terraform plan -var="aws_region=..."` |
| `NAMESPACE`          | `myapp-dev`      | Kubernetes namespace, `terraform plan -var="namespace=..."` |
| `IMAGE_REPOSITORY`   | `myapp`          | `terraform plan -var="image_repository=..."` — keep as `myapp` on GHCR; would become the full ECR URL if you switch registries later |

You don't need a variable for the environment *name* itself (`dev`) — the workflow already
knows which environment a job is running under (`github.environment`), and passes that
straight into `terraform plan -var="environment=..."`. Nothing else needs a secret — pushing
to GHCR uses the automatically-provided `GITHUB_TOKEN`.

When you're ready to activate `uat`/`prod`, repeat the same 5 entries (2 secrets + 3
variables) on those environments' pages with their own values — the workflow doesn't change.

### What the AWS credentials are (and aren't) used for right now

The pipeline authenticates to AWS on every `terraform-plan` run (`aws-actions/configure-aws-credentials`),
and `terraform/providers.tf` has an `aws` provider block wired up and ready. **No AWS
resources are created** — there's no S3 bucket, no DynamoDB table, no EKS cluster, nothing
billable. The `terraform apply` step doesn't exist yet, on purpose: applying needs a real,
reachable target (a real EKS cluster, or a self-hosted runner that can see a local
kind/k3d cluster), and standing that up wasn't the goal here. This setup gets you a genuine,
working `terraform plan` in CI — with real credentials flowing all the way from GitHub
Secrets through Actions into Terraform — without paying for or provisioning anything. See
[Production Improvements](#production-improvements) for what to add when there's a real
target.

---

## Quick start (local Kubernetes: kind / minikube / k3d)

```bash
# 1. Build the image
cd app
docker build -t myapp:local .

# 2. Load it into your local cluster (pick the one you use)
kind load docker-image myapp:local --name <your-cluster>
# or: minikube image load myapp:local
# or: k3d image import myapp:local -c <your-cluster>

# 3. Deploy with Helm directly
cd ../helm
helm upgrade --install myapp . \
  --set image.repository=myapp \
  --set image.tag=local \
  --set environment=dev \
  --create-namespace -n myapp-dev

# 4. Test it
kubectl port-forward -n myapp-dev svc/myapp 8080:80
curl http://localhost:8080/health
curl http://localhost:8080/version
curl http://localhost:8080/env
curl -X POST http://localhost:8080/config -H 'Content-Type: application/json' \
  -d '{"name":"database_url","value":"postgres://example"}'
curl http://localhost:8080/config/database_url
curl -X DELETE http://localhost:8080/config/database_url
```

### Or run it with just Docker (no k8s)

```bash
docker build -t myapp:local ./app
docker run --rm -p 8080:8080 -e ENVIRONMENT=dev myapp:local
curl http://localhost:8080/health
```

### Or deploy via Terraform (wraps the Helm chart)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # adjust as needed
terraform init
terraform apply -var="image_tag=local" -var="environment=dev" -var="namespace=myapp-dev"
```

### Run the tests

```bash
cd app
pip install -r requirements-dev.txt
pytest -v
```

---

## What I changed

### Application (`app/`)
The app skeleton didn't exist as runnable code — I implemented it from scratch in **Python
/ Flask**, per the endpoint contract in `app/README.md`:
- `GET /health`, `GET /version`, `GET /env` — straightforward, `/env` reads `ENVIRONMENT`.
- `POST /config`, `GET /config/{name}`, `DELETE /config/{name}` — backed by an in-memory
  dict guarded by a lock (safe for gunicorn's threaded workers within one process).
- Added input validation (400 on a missing `name`/`value`) and a 404 for unknown config
  keys, plus JSON error handlers, since the spec didn't cover error paths explicitly.
- Added a `pytest` suite (`app/tests/test_main.py`, 8 tests, all passing) covering every
  endpoint and the happy/error paths for `/config`.

### Dockerfile
Written from scratch: multi-stage build (deps installed into a venv in a `builder` stage,
copied into a slim runtime stage), a non-root user (uid 10001), `HEALTHCHECK`, and
`gunicorn` as the production entrypoint instead of the Flask dev server.

### Helm chart (`helm/`)
The provided chart had several bugs that would have made it fail outright:
- **`service.yaml` selector bug**: selected `app: myapps` (typo) while the Deployment's
  pods carried `app: myapp` — the Service would never have routed to any pod. Fixed and
  switched to the standard `app.kubernetes.io/name` + `app.kubernetes.io/instance`
  selector labels via `_helpers.tpl` (a hardcoded label doesn't survive multiple releases
  of the same chart in one namespace).
- **`ingress.yaml`** pointed at a backend Service named `homework`, which doesn't exist in
  this chart (the Service is `myapp`) — fixed to reference the templated Service name, and
  made the whole Ingress conditional on `ingress.enabled` (a local kind/minikube cluster
  usually has no ingress controller, so it should default to off) plus templated
  host/path/class instead of hardcoded values.
- **`deployment.yaml`** hardcoded `containerPort: 5000`, while the app / Service /
  `values.yaml` all use `8080` — fixed to read from `values.service.targetPort` so it can't
  drift again. Also added: `_helpers.tpl` (name/fullname/labels, the standard Helm chart
  scaffold pattern), readiness/liveness probes against `/health`, resource
  requests/limits, `securityContext`/`podSecurityContext` (non-root, dropped
  capabilities), `ServiceAccount` template, optional `HorizontalPodAutoscaler`, and
  `imagePullPolicy`/`imagePullSecrets` support.
- **`values.yaml`** was minimal (4 keys); expanded it with all of the above so the chart is
  usable beyond the happy path (pull policy, probes, resources, ingress toggle, autoscaling
  toggle, security context, service account).
- Added `templates/NOTES.txt` so `helm install` prints how to reach the app.

### Terraform (`terraform/`)
The original `main.tf` didn't even parse (`value = ` with nothing after it, `value = prod`
without quotes) and had a chart path (`../helm/homework`) that doesn't exist:
- Fixed the `helm_release` to point at `${path.module}/../helm` (the real chart location)
  and to actually pass `var.image_tag` / `var.environment` as values.
- The namespace resource hardcoded `name = "production"` while a `namespace` **variable**
  already existed and was simply unused — wired it up (`var.namespace`), so you're no
  longer one `terraform apply` away from silently deploying into `production`.
- `variables.tf` had no defaults/descriptions/validation — added sensible defaults so the
  module is usable for a local demo, a `validation` block on `environment`, and two new
  variables the module actually needed (`image_repository`, `release_name`) plus
  `kubeconfig_path`/`kube_context` so `providers.tf` isn't hardcoded to
  `~/.kube/config`.
- `outputs.tf` was empty — added `namespace`, `release_name`, `release_status`,
  `app_version`.
- `providers.tf` had no `required_providers` block (version-unpinned providers are a
  common source of "works on my machine") — pinned `hashicorp/kubernetes` and
  `hashicorp/helm`.
- Added `wait = true` / `timeout = 300` on the `helm_release` so `terraform apply` actually
  waits for the Deployment to become ready instead of reporting success the instant the
  Helm release object is created.
- Added `terraform.tfvars.example`.
- Added an `aws` provider (pinned `hashicorp/aws ~> 5.0`) and an `aws_region` variable,
  wired to the credentials/region the CI pipeline now passes in. It isn't used by any
  resource yet — see the CI/CD section below for why, and the "Production Improvements"
  section for what plugs into it next (S3 state backend, ECR, EKS).

### CI/CD (`.github/workflows/ci.yml`)
There was no pipeline file in the repo, so this is new — a **GitHub Actions** workflow
(originally drafted for GitLab CI, then switched over, then reshaped again around a
`dev`/`uat`/`main` branch strategy and real AWS credentials — see below). Jobs, in
dependency order: `setup` → `lint-python` / `lint-helm` / `lint-terraform` (parallel) →
`test` → `build-image` → `terraform-plan`.

- **`setup`**: reads the branch name once and derives which GitHub **Environment**
  (`dev`/`uat`/`prod`) this run targets, exposed as a job output. Every other job that
  cares reads this output instead of re-implementing the branch → environment mapping.
- **Lint jobs** (parallel): `flake8` for the app, `helm lint` + `helm template` for the
  chart (`azure/setup-helm`), `terraform fmt -check` + `terraform validate`
  (`hashicorp/setup-terraform`).
- **`test`**: `pytest`, with the JUnit report uploaded as a build artifact.
- **`build-image`**: builds and pushes to **GHCR** (`ghcr.io`, the zero-config registry for
  a GitHub repo — no extra secrets needed, auth uses the built-in `GITHUB_TOKEN`), tagged
  with the immutable commit SHA and an `<environment>-latest` floating tag (`dev-latest`,
  `uat-latest`, `prod-latest`). Uses `docker/build-push-action` with GitHub Actions cache
  so repeated builds are fast. Skipped for pull requests (a PR shouldn't be pushing images),
  so PRs are gated on lint+test only.
- **`terraform-plan`**: runs as a job scoped to the target GitHub **Environment**
  (`dev`/`uat`/`prod`) — which means it automatically picks up that environment's own
  secrets/variables rather than anything repo-wide: `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
  (secrets) authenticate to AWS via `aws-actions/configure-aws-credentials`, and
  `AWS_REGION`/`NAMESPACE`/`IMAGE_REPOSITORY` (variables) feed straight into
  `terraform plan -var=...`. The `environment` value itself doesn't need a variable —
  it comes from the built-in `github.environment` context, since the job is already
  scoped to it. This is also what the manual-approval gate hangs off: once you add
  required reviewers to `uat`/`prod`, this job pauses for approval — same mechanism
  GitLab's `when: manual` uses under a different name.
- **No `apply`/deploy job, on purpose.** Applying needs a real, reachable Kubernetes target
  (an actual EKS cluster, or a self-hosted runner that can see a local kind/k3d cluster),
  and there isn't one right now — see the "GitHub repository setup" section above for the
  reasoning, and "Production Improvements" below for what to add when there is a real
  target. The pipeline still proves the full chain works — AWS creds → Terraform → a valid
  plan — end to end, with zero billable AWS resources.
- Triggers on `push` to `dev`/`uat`/`main` and on `pull_request` into any of them.

---

## Assumptions

- **Language/framework**: Python + Flask (allowed by the brief, small footprint, simple to
  read for reviewers who may not know Go).
- **Config store persistence**: the brief doesn't ask for a database, so the config store
  is in-memory. This is explicitly **not** shared across replicas/restarts — see Known
  Limitations.
- **Cloud target**: the app/Helm side stays provider-agnostic (works the same against a
  local kind/k3d/minikube cluster or a real one). AWS was added specifically for
  credentials/Terraform-provider wiring per your request — not as a hard dependency of the
  app itself.
- **Container registry**: the pipeline uses **GHCR** (`ghcr.io`), since that's zero-config
  for any GitHub repo (auth via the built-in `GITHUB_TOKEN`, no extra secrets to set up).
  Switching to **ECR** would need an existing repository to push into — since no AWS
  resources exist yet (by design, see below), I left this on GHCR rather than half-wiring
  an ECR push that would fail on a missing repo.
- **AWS credentials, no AWS resources**: you asked for the AWS keys to be wired end-to-end
  but for nothing to actually be provisioned on AWS — the focus is a working `terraform
  plan`, not `apply`. So the `aws` provider is configured and authenticated in CI, but no
  `aws_*` resource exists yet (no S3 bucket, no DynamoDB table, no EKS cluster, no ECR
  repo) — see "GitHub repository setup" above and "Production Improvements" below for what
  each of S3/ECR/EKS needs once you're ready to actually stand them up.
- **Manual approval gate**: implemented via GitHub **Environments** with required
  reviewers, rather than an in-YAML "manual" flag — this needs a one-time setting in the
  repo (Settings → Environments), it's not something a workflow file alone can express. Not
  turned on for `dev` (no need to gate your own active branch); worth turning on for
  `uat`/`prod` once real deploys exist.
- **Ingress**: left `disabled` by default in `values.yaml`, since a bare local cluster
  (kind/minikube without an addon) has no ingress controller — `port-forward` is the
  friction-free path for a reviewer to try this.
- **`environment` values**: constrained to `dev`/`uat`/`prod` in the Terraform `validation`
  block, matching the three branches 1:1.
- **Namespace-per-environment** (`myapp-dev` / `myapp-uat` / `myapp-prod`) rather than one
  shared namespace with three releases, matching how most teams isolate environments on a
  shared cluster.

## Known limitations (intentionally out of scope)

- **Config store is in-memory, per-pod**: with `replicaCount > 1`, a `POST /config` on one
  pod won't be visible on another, and everything is lost on restart. A production version
  needs an external store (Redis, a ConfigMap/Secret via the k8s API, or a real database).
  I called this out rather than silently building a fake "shared" store that would still
  break on restarts.
- **No authentication/authorization** on `/config` — anyone who can reach the Service can
  read/write/delete config. Fine for a homework demo, not for anything real.
- **No TLS** for the Ingress (no cert-manager wiring) — `tls: []` is there as a slot to fill
  in, not configured.
- **No CI secret/vault integration beyond AWS/GHCR** — the pipeline authenticates to AWS
  (for the `terraform-plan` job) and to GHCR (built-in `GITHUB_TOKEN`); it does **not**
  have credentials to reach any real Kubernetes cluster, which is exactly why there's no
  `apply`/deploy job yet. Wiring an actual self-hosted runner (or OIDC to a cloud provider)
  + real cluster credentials is the next step once a target exists.
- **No image vulnerability scanning / SBOM / signing** in the pipeline (see Production
  Improvements).
- **Local Terraform state, no remote backend** — `providers.tf` has a commented-out `S3`
  backend block ready to go, but enabling it needs an actual S3 bucket + DynamoDB table to
  exist first (a `terraform init` against a non-existent bucket just fails), which
  contradicts "no AWS resources yet." Fine for this exercise; not fine for a team — see
  Production Improvements.
- I did not have Docker/Helm/Terraform CLIs available in the sandbox I wrote this in, so
  `docker build`, `helm lint`/`template`, and `terraform validate`/`plan` were **not**
  executed end-to-end by me — I reviewed every file by hand for correctness instead. I did
  run the Python test suite (8/8 passing) and a YAML/flake8 syntax check on everything.
  Please run the "Quick start" commands above to confirm on your machine — if something
  doesn't line up I'd genuinely like to know, that's useful signal for the interview.

## Production improvements

If this were going to production, in rough priority order:

1. **State & config**: move `/config` to a real backing store (managed Postgres/Redis) or,
   if the intent really is "runtime config," to native k8s ConfigMaps/Secrets managed
   through the k8s API with an operator pattern — not application-owned in-memory state.
2. **Terraform remote state + locking**: create the S3 bucket + DynamoDB table and uncomment
   the `backend "s3"` block already sitting in `providers.tf`, plus split `environment`s
   into separate state keys/workspaces so a `uat` apply can never touch `prod` state.
3. **Real deploy target + `terraform apply`**: either point the `kubernetes`/`helm`
   providers at a real EKS cluster (`aws eks update-kubeconfig` + an `aws_eks_cluster` data
   source in CI, `hashicorp/aws` is already pinned and ready) or add a self-hosted runner
   that can reach the existing local kind/k3d cluster — then add the actual `apply` job the
   pipeline is currently missing on purpose.
4. **Container registry**: if moving off GHCR, push to ECR instead (create the repository
   with Terraform, then swap `docker/login-action` for `aws-actions/amazon-ecr-login` in
   `build-image`) — the AWS credentials are already flowing through the pipeline for this.
5. **Image supply chain**: vulnerability scanning (Trivy/Grype) as a CI gate, SBOM
   generation, and image signing (cockpit/cosign) before the image is allowed to be
   deployed; pin base images by digest, not just tag.
6. **Secrets management**: External Secrets Operator / Sealed Secrets / Vault instead of
   any `set` for sensitive values; the current pipeline is fine for non-secret config only.
7. **Observability**: `/metrics` (Prometheus format) endpoint, structured JSON logging,
   OpenTelemetry tracing, and a `ServiceMonitor` in the Helm chart; add a `PodDisruptionBudget`
   and proper `topologySpreadConstraints` for multi-AZ resilience.
8. **Progressive delivery**: canary or blue/green rollout (Argo Rollouts/Flagger) instead
   of a plain rolling update, with automated rollback on failed health checks/SLO burn.
9. **Policy & security**: `NetworkPolicy` to restrict pod-to-pod traffic, OPA/Gatekeeper or
   Kyverno admission policies (e.g. enforce non-root, no `:latest` in prod, required
   resource limits), and a dedicated least-privilege k8s ServiceAccount/RBAC per
   environment instead of the CI job having broad cluster access.
10. **GitOps**: swap the `terraform apply`-from-CI deploy step for Argo CD/Flux watching a
    Git repo of rendered manifests/Helm values — better auditability and drift detection
    than "CI pushes state."
11. **Multi-arch images** (`linux/amd64` + `arm64`) via `docker buildx` if the target fleet
    needs it.
12. **API hardening**: request size limits, rate limiting, input schema validation (e.g.
    pydantic) instead of ad-hoc `if` checks, and OpenAPI spec generation for the four
    JSON endpoints.

---

## API reference (implemented exactly as specified)

| Method | Path              | Body                                         | Response                                   |
|--------|-------------------|-----------------------------------------------|---------------------------------------------|
| GET    | `/health`         | –                                             | `{"status": "ok"}`                          |
| GET    | `/version`        | –                                             | `{"version": "1.0.0"}`                      |
| GET    | `/env`            | –                                             | `{"environment": "<ENVIRONMENT env var>"}`  |
| POST   | `/config`         | `{"name": "...", "value": "..."}`             | `{"name": "...", "value": "..."}` (201)     |
| GET    | `/config/{name}`  | –                                             | `{"name": "...", "value": "..."}` or 404    |
| DELETE | `/config/{name}`  | –                                             | `{"deleted": true\|false}`                  |
