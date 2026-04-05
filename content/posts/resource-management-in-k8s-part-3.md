---
title: Resource Management for Pods and Containers — QoS Classes
date: 15.04.2026
slug: qos-k8s
summary: How Kubernetes classifies pods into QoS classes, what that classification writes into the kernel, and how it determines kill order under memory pressure.
series: k8s-resource-management
series_title: "Kubernetes Resource Management"
series_part: 3
tags:
  - devops
  - kubernetes
  - QoS in k8s
---

## What This Article Is About

This is the third article in the series. The [first article](/post/limit-request-k8s)
covered `requests` — how the scheduler uses it to place pods, and how it becomes
kernel primitives via cgroups and OOM scoring. The [second article](/post/limits-k8s)
covered `limits` — why `limits` are invisible to the scheduler, how they become hard
kernel ceilings, and what happens when a container hits them.

Both articles ended at the same place: `oom_score_adj`. The first mentioned it in
passing as a consequence of QoS class. The second showed that hitting `memory.max`
triggers an in-cgroup OOM kill, and noted that chronic memory pressure eventually
leads to `CrashLoopBackOff`. Neither article explained the mechanism that connects
QoS classification to kernel kill priority — or what happens when the pressure
isn't coming from inside a single container, but from the node as a whole.

That's what this article is about.

## A Short Recap

Resources in Kubernetes are CPU time and RAM allocated to a pod or container,
controlled via `requests` and `limits`. There are four resource types:

- `cpu` — CPU time, measured in millicores
- `memory` — RAM, measured in bytes
- `storage` — used for PVCs
- `extended resources` — user-defined resources such as GPUs

This article focuses on `cpu` and `memory`, specifically on what happens when
their `requests` and `limits` values are combined — or absent.

## What Quality of Service Is

Quality of Service (QoS) in Kubernetes is a classification system. Kubernetes
looks at how `requests` and `limits` are configured for every container in a pod
and assigns the pod one of three classes: `Guaranteed`, `Burstable`, or
`BestEffort`.

The classification has two effects. The primary one is kill priority under node
memory pressure: when the node runs low on memory and needs to reclaim it, QoS
class determines which pods are evicted first. The secondary effect is CPU
scheduling weight: QoS class influences how the kernel distributes CPU time
under contention.

Neither effect is visible during normal operation. QoS only matters when
something is wrong.

## How Classes Are Assigned

The classification rules are applied per-pod, based on the combined
configuration of all containers in the pod (including init containers).

### Guaranteed

A pod is `Guaranteed` if every container — without exception — has both
`requests` and `limits` set for CPU and memory, and the values are equal:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "128Mi"
```

If any single container in the pod omits a request, omits a limit, or has
`requests != limits` for either resource, the pod is not `Guaranteed`.

There is one shortcut: if you set only `limits` and omit `requests`, Kubernetes
automatically sets `requests` equal to `limits`. This means a pod with only
`limits` defined can still qualify as `Guaranteed` — as long as limits are set
for all containers on both CPU and memory.

### BestEffort

A pod is `BestEffort` if no container has any `requests` or `limits` set at all:

```yaml
resources: {}
```

Any resource configuration — even a single `requests.cpu` on a single
container — disqualifies the pod from `BestEffort` and moves it to `Burstable`.

### Burstable

Everything else is `Burstable`. This is the most common class in practice. A
pod is `Burstable` if it doesn't qualify as `Guaranteed` and isn't
`BestEffort` — meaning at least one container has at least one `requests` or
`limits` value set, but the pod as a whole doesn't meet the strict
`requests == limits` requirement across all containers and resources.

### Multi-Container Pods

For pods with multiple containers, the classification considers all of them
together. A pod with three containers where two are `Guaranteed`-equivalent and
one is `BestEffort`-equivalent is classified as `Burstable` — the weakest
configuration of any container determines the pod's class.

You can check the assigned class on any running pod:

```shell
$ kubectl get pod <pod-name> -o jsonpath='{.status.qosClass}'
Guaranteed
```

## Two Distinct OOM Scenarios

Before looking at how QoS translates into kernel values, it's important to
distinguish two different situations where OOM kills happen. The previous
article covered the first. This article is primarily about the second.

**Scenario 1: In-cgroup OOM kill.** A single container exceeds its own
`memory.max` value. The kernel's OOM killer fires scoped to that container's
cgroup and kills a process inside it. This is a local event — it doesn't
involve other pods, doesn't consult QoS class, and doesn't use
`oom_score_adj` for target selection across the node. The target is the
process inside that cgroup with the highest OOM score. QoS class is
irrelevant here because the boundary is already set by `memory.max`.

**Scenario 2: Node-level memory pressure.** The node as a whole is running
low on memory. `memory.max` values haven't been hit — the problem is that
the sum of all container memory usage is approaching the node's physical
limit. Kubelet detects this condition, raises a `MemoryPressure` taint on
the node, and begins evicting pods. The kernel's node-level OOM killer can
also fire independently if the situation becomes critical before kubelet
acts. Both kubelet eviction and the kernel OOM killer use `oom_score_adj`
to determine kill order — and `oom_score_adj` is set based on QoS class.

QoS class is only meaningful in Scenario 2.

## What Triggers Node Memory Pressure

Kubelet continuously monitors node memory usage. When available memory drops
below a configurable eviction threshold (default `100Mi`, but tunable via
`--eviction-hard`), kubelet sets the `MemoryPressure` condition on the node
and begins evicting pods.

```shell
kubectl describe node <node-name> | grep -A 5 "Conditions"
```

```
Conditions:
  Type             Status
  MemoryPressure   True      ← node is under memory pressure
  DiskPressure     False
  PIDPressure      False
  Ready            True
```

When `MemoryPressure` is `True`, kubelet stops admitting new `BestEffort`
pods to this node and begins selecting existing pods for eviction. The
selection is based on QoS class, then on how far the pod's memory usage
exceeds its request.

The kernel's node-level OOM killer operates independently of kubelet. If
memory is exhausted before kubelet's eviction loop runs — which can happen
under sudden memory spikes — the kernel fires first and selects victims using
`oom_score_adj` directly. Kubelet eviction is the intended mechanism.
The kernel OOM killer is the safety net.

## `oom_score_adj` — The Kernel Side of QoS

`oom_score_adj` is a per-process Linux kernel parameter that adjusts a
process's likelihood of being selected by the OOM killer. It ranges from
-1000 to +1000. A higher value makes the process a more likely kill target.
A value of -1000 makes a process completely immune to OOM kills.

Kubelet sets `oom_score_adj` for each container's main process based on
the pod's QoS class:

| QoS class | `oom_score_adj` | Kill priority |
|-----------|-----------------|---------------|
| `Guaranteed` | -997 | Last — nearly immune |
| `Burstable` | 2 to 999 | Middle — depends on memory request |
| `BestEffort` | 1000 | First — always the primary target |

The value for `Burstable` pods is not fixed. It is calculated per-pod based
on the pod's memory request relative to total node memory:

$$
\text{oom\_score\_adj} = \min\left( \max\left( 2,\ 1000 - \frac{1000 \cdot \text{memoryRequestBytes}}{\text{machineMemoryCapacityBytes}} \right),\ 999 \right)
$$

The fraction `(1000 × memoryRequestBytes) / machineMemoryCapacityBytes` is
rounded up — 934.12 becomes 935.

The consequence of this formula: a `Burstable` pod that requests more memory
gets a lower (safer) `oom_score_adj`. A pod requesting 12 GB on a 16 GB node
gets a score close to 2 — nearly as protected as `Guaranteed`. A pod
requesting 100 MB on the same node gets a score close to 999 — nearly as
exposed as `BestEffort`.

This is intentional. The kernel treats a larger memory commitment as a signal
that the pod is more important to keep alive. A pod that declared a large
request is expected to actually need that memory; a pod that declared a tiny
request is more likely to be safely killed without major consequence.

You can verify the value on a running node:

```shell
# Find the PID of the container's main process
cat /proc/<pid>/status | grep OOMScore

OOMScoreAdj: 461
```

Or by reading the file directly:

```shell
cat /proc/<pid>/oom_score_adj
```

## The Pause Container

Each pod has a `pause` container — a minimal process that holds the pod's
network namespace open for the lifetime of the pod. If the pause process is
killed, the network namespace is destroyed. All containers in the pod lose
their network connectivity and are effectively killed regardless of their
own OOM scores.

For this reason, kubelet assigns the pause container `oom_score_adj = -998` —
one point safer than `Guaranteed` app containers at -997. This ensures the
pause process is the absolute last thing the OOM killer targets within a pod,
even if the pod itself is `Guaranteed`.

The pause container does not consume meaningful memory in normal operation
(typically under 1 MB), so its presence at -998 does not affect node-level
OOM decisions in practice. It is a protection measure, not a scheduling factor.

## The Full Chain: From QoS Class to Kernel

Here is how the QoS classification connects to kernel enforcement, following
the same chain structure as the previous articles:

```
kubectl apply
    │
    ▼
API Server stores PodSpec
    │
    ▼
Scheduler places pod on node
# QoS class not used for scheduling — only requests matter here
    │
    ▼
Kubelet computes QoS class from PodSpec
    │
    ├─► Classifies pod: Guaranteed / Burstable / BestEffort
    │   based on requests and limits across all containers
    │
    ├─► Creates pod-level cgroup under the matching QoS subdirectory:
    │   /sys/fs/cgroup/kubepods/guaranteed/pod<uid>/
    │   /sys/fs/cgroup/kubepods/burstable/pod<uid>/
    │   /sys/fs/cgroup/kubepods/besteffort/pod<uid>/
    │
    ├─► Calculates oom_score_adj per container:
    │   Guaranteed  → -997
    │   BestEffort  → 1000
    │   Burstable   → 2 to 999 (formula above)
    │
    ▼
Kubelet → gRPC → containerd → runc
    │
    ├─► runc writes container PID to cgroup.procs
    │   (process is now under the cgroup hierarchy)
    │
    ├─► runc (or kubelet via /proc) writes oom_score_adj to:
    │   /proc/<pid>/oom_score_adj
    │
    ▼
Linux kernel:
    cgroup location  → determines OOM kill scope and priority
    oom_score_adj    → adjusts kill likelihood within scope
    memory.min       → protects against reclaim (from requests)
    memory.max       → hard ceiling, in-cgroup OOM (from limits)
```

The cgroup directory itself encodes the QoS class. The kernel doesn't know
about Kubernetes QoS classes — it only knows about `oom_score_adj` values and
cgroup boundaries. The mapping from class to value is done entirely by kubelet
before the process starts.

## QoS and the cgroup Hierarchy

The three QoS classes map directly to three subdirectories under
`/sys/fs/cgroup/kubepods/`:

```
/sys/fs/cgroup/kubepods/
├── guaranteed/
│   └── pod<uid>/
│       └── <container-id>/
├── burstable/
│   └── pod<uid>/
│       └── <container-id>/
└── besteffort/
    └── pod<uid>/
        └── <container-id>/
```

This placement is meaningful beyond organization. The kernel's memory reclaim
and OOM kill logic operates on the cgroup hierarchy. When the node is under
pressure, the kernel can target entire cgroup subtrees. `BestEffort` pods, all
grouped under `besteffort/`, are structurally separated from `Guaranteed` pods
under `guaranteed/`. The hierarchy makes the kill ordering easier to enforce
at the kernel level.

You can inspect this on any node:

```shell
ls /sys/fs/cgroup/kubepods/burstable/ | head -5
```

```
pod3f2a1b4c-...
pod7e9d0c12-...
pod1a4f8e23-...
```

## QoS and CPU

CPU QoS doesn't have a kill mechanism. There is no "CPU OOM kill" — a
container that exceeds its CPU request is throttled (if it also has a limit)
or competes for time (if it doesn't). QoS class affects CPU behavior through
a different channel: `cpu.weight` in the cgroup hierarchy.

When kubelet creates the pod-level cgroup, it sets `cpu.weight` based on the
sum of CPU requests across the pod's containers. The QoS class subtree itself
also has a `cpu.weight` that reflects the aggregate weight of all pods in that
class.

The practical effect: under CPU contention, processes in higher-priority
cgroups (with higher `cpu.weight`) get proportionally more CPU time. A
`Guaranteed` pod with `cpu.weight=10000` (the maximum) will receive far more
CPU time than a `BestEffort` pod during a contention event.

The `BestEffort` subtree gets `cpu.weight=2` — the minimum — which means
`BestEffort` pods are the first to be starved of CPU time when the node is
busy, in the same way they are the first to be killed when the node is low
on memory. The behavior is consistent across both resources.

You can verify the weight for any container:

```shell
cat /sys/fs/cgroup/kubepods/burstable/pod<uid>/<container-id>/cpu.weight
```

```
100
```

## What You Should Take Away

The three QoS classes are not a resource management feature — they are a
failure management feature. They only matter when something is going wrong on
the node, and they determine who pays the price.

A few practical points worth keeping in mind:

Pods without any `requests` or `limits` are `BestEffort` and will be killed
first. This is often unintentional — it happens when teams omit resource
configuration entirely. Check with:

```shell
kubectl get pods -A -o json | \
  jq '.items[] | select(.status.qosClass == "BestEffort") | 
  .metadata.namespace + "/" + .metadata.name'
```

`Guaranteed` pods are the safest but also the least efficient — a pod with
`requests == limits` can never burst. On a lightly loaded node, a
`Guaranteed` pod with `cpu: 500m` will never use more than 500 millicores
even if the node has plenty of idle capacity.

`Burstable` is the right class for most production workloads — set
`requests` accurately to reflect normal usage, set `limits` to cap runaway
consumption, and accept that the pod can be evicted under extreme node
pressure. The eviction order within `Burstable` is determined by how far
above its memory request the pod is currently running.

## What's Next

The next article covers `ResourceQuota` and `LimitRange` kinds in Kubernetes
as final part of this series.