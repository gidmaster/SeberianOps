---
title: Resource Management for Pods and Containers
date: 28.02.2026
slug: limit-request-k8s
summary: A study note about limit and request usage in k8s
tags:
  - devops
  - kubernetes
  - QoS in k8s
---

## Resources in Kubernetes

Resources in Kubernetes are CPU time and RAM that a node allocates for a specific pod or container. We control how containers utilize cluster resources via `requests` and `limits`.

This article focuses on `requests` — and specifically on what Kubernetes actually *does* with that value at every step, from the moment you apply a manifest to the moment a pod is running on a node.

## Resource Types

There are 4 resource types:

- `cpu` — CPU time, measured in millicores
- `memory` — RAM, measured in bytes
- `storage` — a specific resource type for PVCs
- `extended resources` — user-defined resources, maintained by administrators (e.g. GPU usage)

In this article we focus on the first two.

## What `requests` Actually Is

`requests` is the minimum amount of resources (`cpu` or `memory`) that Kubernetes guarantees for a pod or container.

That word *guarantees* deserves unpacking. It has two distinct meanings depending on where in the system you look:

- **At the scheduler level** — `requests` is the value the scheduler uses to decide *where* the pod can run and *which* node is the best fit.
- **At the node level** — `requests` is translated into OS-level primitives that actually enforce the guarantee at runtime.

We'll cover the node level in a follow-up. For now, let's trace exactly what the scheduler does with a `requests` value.

## How the Scheduler Uses `requests`

When you apply a manifest, the API server extracts the `requests` values and hands them to the scheduler. The scheduler's job is to find the best node. It does this in two phases: **Filtering** and **Scoring**.

### Phase 1 — Filtering

Filtering answers the question: *"Where can this pod actually run?"*

The scheduler checks every available node against the pod's requirements. If a node fails any requirement, it's removed from the list. Requirements include things like taints & tolerations, node affinity, port availability — but the most relevant one here is **Resource Fit**.

For each node, the scheduler looks at already-allocated resources:

```shell
for node in $(kubectl get nodes -o name); do
  echo "=== $node ==="
  kubectl describe $node | grep -A 5 "Allocated resources"
  echo
done
```

```
=== node/vm-cluster-node-3 ===
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests      Limits
  --------           --------      ------
  cpu                3 (37%)       4500m (56%)
  memory             5376Mi (33%)  5504Mi (34%)

=== node/vm-cluster-node-2 ===
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests        Limits
  --------           --------        ------
  cpu                1600m (20%)     600m (7%)
  memory             1519904Ki (9%)  1284384Ki (7%)

=== node/vm-cluster-node-1 ===
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests      Limits
  --------           --------      ------
  cpu                300m (3%)     0 (0%)
  memory             5260Mi (32%)  8490Mi (53%)
```

The scheduler checks two conditions:

```
free memory on node >= requests.memory
free CPU on node    >= requests.cpu
```

If either fails, the node is removed. If *no* node passes — the pod gets stuck in `Pending` state.

Filtering is binary: pass or fail. It produces a list of *viable* nodes, not a ranked list. That's the job of the next phase.

### Phase 2 — Scoring

Scoring answers the question: *"Which viable node is the best fit?"*

If only one node survived filtering, there's nothing to score — that node wins. If multiple nodes survived, the scheduler runs them through a set of scoring plugins. Each plugin scores each node from 0 to 10. The scores are combined and the node with the highest total wins.

Two plugins are central to how `requests` affects scoring.

#### Plugin 1 — `NodeResourcesFit` (LeastAllocated) — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/noderesources/fit.go)

The default strategy here is `LeastAllocated` — the scheduler prefers nodes that have the **most free resources** after placing the pod. The intuition is simple: spread the load, don't pile everything onto one node.

The formula for each resource:

$$
S_{cpu} = \frac{C_{cpu} - R_{cpu}}{C_{cpu}} \times 10
$$

$$
S_{mem} = \frac{C_{mem} - R_{mem}}{C_{mem}} \times 10
$$

Where $R$ is total requested resources on the node *including* the current pod, and $C$ is total allocatable capacity. The final score is the average:

$$
S_{LeastAllocated} = \frac{S_{cpu} + S_{mem}}{2}
$$

A node that is 20% utilized scores much higher than one at 80%. This is the primary force pushing pods toward emptier nodes.

An alternative strategy — `MostAllocated` — does the opposite, preferring to fill nodes as much as possible before using new ones. This is useful when you want to consolidate workloads and free up nodes for scale-down. It's not the default, but worth knowing it exists.

#### Plugin 2 — `NodeResourcesBalancedAllocation` — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/noderesources/balanced_allocation.go)

`LeastAllocated` cares about *how much* is used. `BalancedAllocation` cares about *the ratio* between CPU and memory usage. Even a lightly loaded node can score poorly here if it has, say, 80% of CPU allocated but only 10% of memory — because that imbalance leaves the other resource stranded and unusable for most workloads.

The math:

**Step 1: Compute resource fractions** (projected utilization after placing the pod)

$$
F_{cpu} = \min\left(1.0,\ \frac{R_{cpu}}{C_{cpu}}\right), \quad F_{mem} = \min\left(1.0,\ \frac{R_{mem}}{C_{mem}}\right)
$$

**Step 2: Compute imbalance**

$$
D = \left| F_{cpu} - F_{mem} \right|
$$

- $D = 0$ → perfectly balanced (e.g. 50% CPU & 50% RAM)
- $D = 1$ → completely imbalanced (e.g. 100% CPU & 0% RAM)

**Step 3: Score**

$$
S_{raw} = (1 - D) \times 100
$$

Or fully expanded:

$$
S_{raw} = \left(1 - \left| \frac{R_{cpu}}{C_{cpu}} - \frac{R_{mem}}{C_{mem}} \right|\right) \times 100
$$

The Scheduler Framework then normalizes all plugin scores to 0–10 and combines them. The node with the highest combined score is selected for binding.

#### How the two plugins work together

`LeastAllocated` and `BalancedAllocation` pull in the same general direction but optimize for different things. The first pushes pods toward empty nodes. The second ensures that whichever node is chosen, its CPU and memory are utilized proportionally. Together they describe a scheduler that is trying to keep the cluster both *spread* and *efficient*.

You can tune the weight of each resource within `BalancedAllocation` via `KubeSchedulerConfiguration`:

```yaml
pluginConfig:
  - name: NodeResourcesBalancedAllocation
    args:
      resources:
        - name: cpu
          weight: 1
        - name: memory
          weight: 2  # memory imbalance penalized 2x more
```

#### Other Scoring Plugins

Resource-based scoring is the dominant logic when `requests` are in play, but the scheduler runs several other plugins in the same pass. A few worth knowing:

**`DefaultPodTopologySpread` / Pod Spreading** — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/podtopologyspread/scoring.go) — prefers nodes with fewer pods of the same type already running. Improves fault tolerance by avoiding concentration. Can tip the decision when resource scores between nodes are close.

**`ImageLocality`** — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/imagelocality/image_locality.go) — prefers nodes that already have the container image cached locally. A node with the full image scores higher than one that would need to pull it. Not about resources at all, but directly affects startup latency and can be surprisingly influential for large images.

**`InterPodAffinity`** — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/interpodaffinity/scoring.go) — scores nodes based on affinity and anti-affinity rules between pods. Important to be aware of because it can *override* resource-based scores when rules are explicitly set — a node that looks worse on resources may win if affinity rules strongly favor it.

**`TaintToleration`** — [source](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/framework/plugins/tainttoleration/taint_toleration.go) — has both a filtering role (hard taints block scheduling) and a scoring role. Nodes with fewer unmatched taints score higher, subtly steering pods away from nodes that weren't intended for general workloads.

None of these are about `requests` values directly, but they all participate in the same final score. The node the scheduler picks is the winner across *all* of these plugins combined — not just the one with the most free resources. The default weights for every plugin are defined in [`default_plugins.go`](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/apis/config/v1/default_plugins.go) — worth reading to see exactly what the scheduler prioritizes out of the box.

### What the Scheduler Guarantees — and What It Doesn't

After scoring, the API server sends a binding command to kubelet on the winning node, and the pod starts. At this point the scheduler's job is done.

It's worth being precise about what the scheduler's `requests` check actually guarantees: it guarantees that *at scheduling time*, enough resources were declared available on the node. It does not guarantee that those resources will be available at runtime if other pods on the node are consuming more than their declared requests.

That enforcement — the actual runtime guarantee — happens at the OS level, via cgroups for CPU and the OOM killer for memory. That's the subject of the next section.

## What Happens On the Node When a Pod Is Scheduled

Before diving into cgroups, let's look at the full picture of what happens on the node — from kubelet receiving the binding to a process actually running in an isolated environment.

```
kubectl apply
    │
    ▼
API Server stores PodSpec
    │
    ▼
Scheduler: Filtering → Scoring → writes Binding to API Server
# Described in previous section
    │
    ▼
Kubelet watches API Server, sees pod assigned to its node
    │
    ├─► Kubelet admission checks (including Resource Fit)
    │
    ├─► Creates pod-level cgroup hierarchy
    │   writes cpu.weight + memory.min  ← requests values land here
    │
    ▼
Kubelet → gRPC (protobuf) → containerd
    │
    ├─► RunPodSandbox:
    │   containerd creates container-level cgroup for sandbox
    │   containerd → shim → runc → pause container running
    │   network namespace created, held open by pause
    │
    ├─► CreateContainer + StartContainer (per app container):
    │   containerd translates CRI spec → OCI spec (config.json)
    │   containerd → shim → runc
    │       runc creates pid, mnt, uts namespaces
    │       runc sets up overlayfs rootfs
    │       runc writes PID → cgroup.procs  ← process joins cgroup
    │       runc calls clone() + execve()   ← process is running
    │
    ▼
Linux kernel enforces:
    cpu.weight   → CFS/EEVDF scheduling weight under contention
    memory.min   → memory reclaim protection
```

As `requests` travels through this chain it is translated several times — from a manifest value, to a protobuf field, to an OCI spec entry, to a cgroupfs file. At each layer it means something slightly different but consistent. Let's look at each step in detail.

### Step 1 — Kubelet Admission Checks

Kubelet doesn't trust the scheduler blindly. Before doing any work, it runs its own admission chain — a set of checks against the node's *current, real-time state*. This is necessary because the scheduler works from a cached view of the cluster. Between the moment the scheduler decided "this node has enough room" and the moment kubelet receives the binding, other pods may have been scheduled onto the same node and the cache may be stale.

The admission chain ([source](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/lifecycle/predicate.go)):

| Check | What it validates | Failure result |
|-------|------------------|----------------|
| Predicate checks | NodeAffinity, Taints, Tolerations — same logic as scheduler filtering, re-run locally | Pod rejected, event `FailedScheduling` |
| Volume checks | PVCs available, secrets and ConfigMaps exist and are mountable | Pod waits with status `ContainerCreating` |
| Image pull | Registry access, image existence | `ErrImagePull` / `ImagePullBackOff` |
| Security context | RunAsRoot, capabilities, SELinux labels | Rejected by `PodSecurity` admission |
| **Resource Fit** | `requests` and `limits` against node's actual allocatable resources | Pod status `OutOfcpu` or `OutOfmemory`, back to pending |

The Resource Fit check is the most important one for our topic. Kubelet computes:

```
sum of requests (all currently running pods)
+ requests of the new pod
≤ node allocatable
```

For both CPU and memory independently. Note that *node allocatable* is not the same as total node capacity. Kubelet subtracts its own reserved resources and the eviction threshold before doing the check:

```
allocatable = capacity - kube-reserved - system-reserved - eviction-threshold
```

This means a node may appear to have free capacity from the outside while kubelet correctly rejects new pods because the safety margins are already consumed.

If Resource Fit fails, the pod is not rejected permanently — it goes back to `Pending` and the scheduler will attempt to place it again, possibly on a different node. Only after all admission checks pass does kubelet proceed to the next step.

### Step 2 — Kubelet Creates the cgroup Hierarchy

With admission passed, kubelet creates the cgroup tree for the pod *before* calling the container runtime. This is an important ordering: the resource envelope exists at the kernel level before any process is spawned inside it.

The hierarchy kubelet creates:

```
/sys/fs/cgroup/
└── kubepods/                        ← root for all Kubernetes workloads
    └── burstable/                   ← QoS class (covered in the QoS article)
        └── pod<uid>/                ← pod-level cgroup  ← kubelet creates this
                cpu.weight           ← sum of container requests
                memory.min           ← sum of container requests
```

The container-level cgroups inside the pod directory are created later by containerd. Kubelet owns the outer boundary; the runtime owns the inner ones.

> **cgroupv1 vs cgroupv2:** The parameter name for CPU weight changed between versions. In cgroupv1, CPU priority is set via `cpu.shares` — an arbitrary unit where the default is 1024, and values are compared relatively between siblings. In cgroupv2, this was replaced by `cpu.weight` — a cleaner scale of 1 to 10000, default 100, with the same relative semantics. Kubernetes >= 1.25 supports cgroupv2 properly. The mapping kubelet uses: `cpu.weight = 1 + ((millicores - 1) * 9999) / 255000`. The concept is identical in both versions — relative share under contention — only the scale and file name differ.

### Step 3 — Kubelet Calls the CRI

Kubelet communicates with containerd via gRPC using protobuf — not JSON or YAML. The interface is defined in [`api.proto`](https://github.com/kubernetes/cri-api/blob/master/pkg/apis/runtime/v1/api.proto).

It sends two types of calls:

**`RunPodSandbox`** — sets up the shared pod environment. containerd creates the network namespace, starts the `pause` container (which does nothing except hold the namespaces open for the pod's lifetime), and creates the sandbox-level cgroup. The pause container is a real container — containerd spawns a shim and calls runc for it just like any other container.

**`CreateContainer` + `StartContainer`** — one pair per app container. containerd receives the CRI spec in protobuf format and translates it into an **OCI runtime spec** — a `config.json` file written to a bundle directory on disk. This is the moment where Kubernetes concepts disappear and everything becomes pure Linux primitives:

```json
"linux": {
  "resources": {
    "unified": {
      "cpu.weight": "100",
      "memory.min": "67108864",   ← from requests
      "memory.max": "134217728",  ← from limits
      "cpu.max": "50000 100000"   ← from limits
    }
  },
  "cgroupsPath": "kubepods-burstable-pod<uid>.slice:containerd:<container-id>"
}
```

### Step 4 — containerd-shim + runc

containerd spawns a **containerd-shim** process for each container — a lightweight process that stays alive for the container's lifetime and manages I/O, exit codes, and signals. The shim then calls **runc**, which does the actual low-level work:

- Creates the remaining namespaces: `pid`, `mnt`, `uts` (the network namespace was already created for the sandbox by the pause container step)
- Sets up the **overlayfs** rootfs from the image layers
- Creates the container-level cgroup directory under the pod cgroup
- Writes the new PID into `cgroup.procs` — this is the moment the process joins the cgroup, *before* `execve()` is called
- Calls `clone()` + `execve()` — the process is now running inside all namespaces, under the cgroup

The ordering of the last two steps matters: the process is inside the cgroup before it becomes the application. There is no moment where it runs outside its resource envelope.

### What the Kernel Enforces

Once the process is running, enforcement is entirely at the kernel level — Kubernetes is no longer involved.

**`cpu.weight` → CFS/EEVDF scheduling weight**

The kernel scheduler uses weights as *relative shares* under contention. If the node is idle, a container can use far more CPU than its request value — the weight only matters when multiple processes compete for CPU time. This is why `requests` do not cap CPU usage. A request of `100m` does not mean the container is limited to 100 millicores — it means the container is *guaranteed* at least that share when the node is busy. Capping is the job of `limits`, enforced via `cpu.max`.

**`memory.min` → memory reclaim protection**

`memory.min` instructs the kernel's memory reclaim system: *do not reclaim pages from this cgroup under memory pressure*. When the node is running low on memory and the kernel needs to free pages, it skips cgroups with `memory.min` set and targets those without it first. This is the actual runtime enforcement of the `requests` guarantee — not a Kubernetes mechanism, a direct kernel memory management instruction.

**`oom_score_adj` → OOM kill priority**

`memory.min` protects against *reclaim* — the gradual process of freeing unused pages. But if memory pressure becomes critical and reclaim isn't enough, the kernel's OOM killer steps in and terminates a process outright. `oom_score_adj` is the knob that determines which process gets killed first.

The value ranges from -1000 to +1000. A higher score means the process is a more likely kill target. Kubelet sets this per container based on QoS class — which is determined by how `requests` and `limits` are configured:

| QoS class | `oom_score_adj` | Meaning |
|-----------|----------------|---------|
| `Guaranteed` | -997 | Nearly unkillable — requests == limits for all containers |
| `Burstable` | 2 to 999 (scaled by memory request) | Killed before Guaranteed, after BestEffort |
| `BestEffort` | 1000 | Killed first — no requests or limits set at all |

The exact value for `Burstable` pods is calculated as: `1000 - (1000 * memoryRequest / machineMemoryCapacity)`. A pod requesting more memory gets a lower (safer) score — the kernel treats a larger memory commitment as a signal that the pod is more important.

This is why `requests` affect OOM behavior even indirectly: the QoS class is derived from the relationship between `requests` and `limits`, and the QoS class determines `oom_score_adj`. The full QoS classification logic is covered in the next article.