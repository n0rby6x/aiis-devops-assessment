# Code Review

Thanks for getting this into a shape where we could talk about it — this is a totally
normal state for a first pass. Below are the **top 5 things I'd fix first**, roughly in the
order I'd tackle them (most blocking first). I've kept this short on purpose; happy to pair
on any of these.

---

## 1. `terraform/main.tf` doesn't actually parse

```hcl
set {
  name  = "image.tag"
  value =              # <- nothing here
}

set {
  name  = "environment"
  value = prod          # <- bare word, not a string
}
```

`terraform validate` will fail on this immediately — `value = ` needs an expression, and
`prod` needs to be either a quoted string `"prod"` or (better) a reference to the
`environment` variable that's already declared in `variables.tf` but never used anywhere:

```hcl
set {
  name  = "image.tag"
  value = var.image_tag
}

set {
  name  = "environment"
  value = var.environment
}
```

**Why this is #1:** nothing downstream of this file can be tested or reviewed until it
parses — it's a hard blocker, not a style nit.

---

## 2. The namespace is hardcoded to `"production"`, ignoring the `namespace` variable

```hcl
resource "kubernetes_namespace" "homework" {
  metadata {
    name = "production"
  }
}
```

You already declared a `namespace` variable in `variables.tf` — but this resource never
reads it. As written, **every apply goes to `production`**, regardless of what anyone
passes in. That's the kind of thing that turns into an incident (someone testing something
"safely" and accidentally touching prod). Use the variable:

```hcl
resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
  }
}
```

General habit worth building: if a variable exists, grep for it before you ship — an unused
variable is often a sign a hardcoded value snuck in by mistake.

---

## 3. The Helm chart's Service will never route traffic to any pod

```yaml
# service.yaml
selector:
  app: myapps        # <- extra "s"
```
```yaml
# deployment.yaml -> pod template labels
labels:
  app: myapp
```

This is the nastiest kind of bug: `helm install` succeeds, `kubectl get pods` shows
`Running`, and yet nothing works, because the Service's selector doesn't match the pod
labels — the Service has zero endpoints. `kubectl get endpoints myapp` would show this
immediately (empty).

Fix the typo, but also — longer term — don't hand-write the same label in three
places (Service selector, Deployment selector, pod template labels). Put one
`_helpers.tpl` with a single `labels`/`selectorLabels` definition and `include` it
everywhere. One typo, one place to fix it, instead of three places that can silently drift
apart.

Related, same category of bug: `ingress.yaml` points its backend at a service called
`homeworks`, which doesn't exist in this chart at all (the Service is named `myapp`). Same
root cause — names typed by hand in multiple files instead of templated from one source of
truth.

---

## 4. `containerPort` doesn't match where the app actually listens

```yaml
# deployment.yaml
ports:
  - containerPort: 5000
```

But the Service targets `8080`, and (per the app spec) the app listens on `8080`. Right now
this "works" only by accident of Kubernetes not validating the port number against
anything — traffic sent to the pod on 8080 will actually reach the container (Kubernetes
doesn't enforce `containerPort` for routing), but the field is misleading/wrong
documentation-as-code, and if anyone ever adds a `livenessProbe`/`readinessProbe` against
`ports: http` by name, it'll break. Fix the number, and consider driving both the Service's
`targetPort` and the Deployment's `containerPort` from a single `values.yaml` field so they
can't diverge again.

While you're in this file: there's no `readinessProbe`/`livenessProbe` and no
`resources` (requests/limits) at all. For a chart that's about to run in a shared cluster,
I'd treat these as close to non-negotiable — without a readiness probe, Kubernetes sends
traffic to a pod before your app is actually ready to serve it (e.g. right after start-up),
and without resource requests, a single misbehaving pod can starve everything else on the
node. Small addition, disproportionately useful.

---

## 5. There's no CI pipeline yet — nothing here is automated

I don't see a `.gitlab-ci.yml` / `.github/workflows` at all. Before this goes further, I'd
want at minimum:
- a **lint/test stage** that runs on every push (even just `flake8`/`pytest` for the app
  once it exists, plus `helm lint` and `terraform validate` — all three would have caught
  issues #1–#4 automatically, for free, on every commit),
- a **build stage** that builds and pushes the image with an immutable tag (commit SHA, not
  just `latest` — otherwise you can't ever answer "which code is actually running in
  staging right now?"),
- a **deploy stage**, even a manual one to start with.

This isn't about process for its own sake — items 1, 3, and 4 above are exactly the class of
bug that a `terraform validate` / `helm lint` / `helm template` step in CI catches in 10
seconds, before a human ever has to notice a broken Service by debugging it live in a
cluster.

---

## Not in the top 5, but quick wins if you have 5 more minutes
- Pin the `hashicorp/kubernetes` and `hashicorp/helm` provider versions in `providers.tf`
  (no `required_providers` block currently — you're on whatever latest happens to resolve
  at apply-time).
- `outputs.tf` is empty — even just the namespace and release name would help whoever
  runs this next.
- `ingress.yaml` has no `.Values`-driven host/path — it's hardcoded to `myapp.local`,
  which means every environment gets the same Ingress rule.

Overall this is a solid skeleton to review against — the structure (app / helm / terraform)
is right, these are all fixable in an afternoon, and none of them require rethinking the
approach. Ping me when you've had a pass at these and I'll do a second look.
