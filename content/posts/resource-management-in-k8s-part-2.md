---
title: Resource Management for Pods and Containers — Limits
date: 13.03.2026
slug: limits-k8s
summary: A deep dive into resource.limits — why they are invisible to the scheduler, how they become hard kernel ceilings on the node, and what actually happens when a container hits them.
series: k8s-resource-management
series_title: "Kubernetes Resource Management"
series_part: 2
tags:
  - devops
  - kubernetes
  - QoS in k8s
---

## Resources in Kubernetes

This is the second article in the series. The [first article](/post/limit-request-k8s) covered `requests` in depth — how the scheduler uses it to place pods, and how it becomes kernel primitives on the node via cgroups and OOM scoring. This article covers `limits`, which travels a different path through the same chain.

Resources in Kubernetes are CPU time and RAM that a node allocates for a specific pod or container. We control how containers utilize cluster resources via `requests` and `limits`. There are 4 resource types:

- `cpu` — CPU time, measured in millicores
- `memory` — RAM, measured in bytes
- `storage` — a specific resource type for PVCs
- `extended resources` — user-defined resources, maintained by administrators (e.g. GPU usage)

This article focuses on `cpu` and `memory` limits.

## What Node Capacity Actually Means

Before talking about limits, it's worth establishing what capacity is actually available on a node — because the answer is not simply "however much RAM and CPU the machine has."

A node with 16 GB RAM and 8 vCPU does not make all of that available to pods. Kubelet carves out several reservations before pods can use anything:

```
allocatable = capacity - kube-reserved - system-reserved - eviction-threshold
```

| Component | What it is | Who sets it |
|-----------|-----------|-------------|
| `capacity` | Physical resources on the node | Hardware / cloud provider |
| `kube-reserved` | Reserved for Kubernetes system components (kubelet, container runtime, etc.) | Cluster operator via kubelet config |
| `system-reserved` | Reserved for OS-level processes (kernel, sshd, journald, etc.) | Cluster operator via kubelet config |
| `eviction-threshold` | Memory buffer kubelet keeps free to avoid node instability | Cluster operator, default ~100Mi |
| **`allocatable`** | **What pods can actually use** | Derived |

A concrete example with a typical production node:

```
capacity:
  cpu:    8000m
  memory: 16384Mi

kube-reserved:
  cpu:    200m
  memory: 512Mi

system-reserved:
  cpu:    100m
  memory: 256Mi

eviction-threshold:
  memory: 200Mi

allocatable:
  cpu:    7700m      ← 8000 - 200 - 100
  memory: 15416Mi    ← 16384 - 512 - 256 - 200
```

You can verify this on any node:

```shell
kubectl describe node <node-name> | grep -A 6 "Allocatable"

Allocatable:
  cpu:    7700m
  memory: 15416Mi
  pods:   110
```

This is the number the scheduler uses when checking Resource Fit — not raw capacity. It is also the ceiling against which kubelet runs its own local Resource Fit check during admission (described in the [requests article](/post/limit-request-k8s)). A pod that requests more than `allocatable` will never be scheduled, even on an otherwise empty node.

This matters for `limits` specifically because of overcommit: the sum of all pod `limits` on a node is routinely far above `allocatable`. That's intentional and expected. But it means the safety net — the guarantee that the node won't fall over — is not the limits themselves. It's the eviction threshold, the QoS-based kill order, and the kernel's OOM killer. All of which depend on `requests`, not `limits`. That's why understanding allocatable capacity is the right starting point for understanding what limits actually protect.

## What `limits` Actually Is

If `requests` is a *floor* — the minimum Kubernetes guarantees to a pod — then `limits` is a *ceiling*: the maximum a container is allowed to consume.

But the nature of that ceiling is fundamentally different from the `requests` guarantee. `requests` is a promise *to the pod* — the scheduler and the kernel both work to ensure the pod gets at least that much. `limits` is a promise *to the node* — a declaration that this container will never consume more than this amount, protecting other workloads from being starved.

That distinction has a concrete consequence: `requests` participates in scheduling decisions, `limits` does not. A node is never rejected because a pod's `limits` exceed available resources. Only `requests` matter for placement.

## `limits` and the Scheduler — Intentional Absence

When the scheduler runs Filtering and Scoring, it reads `requests` values from the PodSpec and compares them against node allocatable resources. `limits` values are read but not used for any placement decision.

This is intentional and is the foundation of **overcommit** — a deliberate design choice in Kubernetes. You can schedule pods whose `limits` sum to far more than the node physically has. The assumption is that not all containers will hit their limits simultaneously, so the node can be utilized more efficiently.

The consequence is equally deliberate: if that assumption turns out to be wrong and multiple containers approach their limits at the same time, something has to give. That "something" is enforced entirely at the node level — by the kernel, not the scheduler. This is where `limits` becomes real.

## What Happens On the Node When a Pod Is Scheduled

The schema below mirrors the one from the [requests article](/post/limit-request-k8s). The annotations show where `limits` travel differently — they skip the pod-level cgroup entirely and land only at the container level, written by runc.

```
kubectl apply
    │
    ▼
API Server stores PodSpec
    │
    ▼
Scheduler: Filtering → Scoring → writes Binding to API Server
# limits not used in scheduling decisions — only requests matter here
    │
    ▼
Kubelet watches API Server, sees pod assigned to its node
    │
    ├─► Kubelet admission checks
    │   limits validated for correctness (must be >= requests if both set)
    │   limits NOT used in Resource Fit check — only requests are
    │
    ├─► Creates pod-level cgroup hierarchy
    │   limits are NOT written here — pod-level cgroup has no hard ceiling
    │   (the pod envelope is defined by requests, not limits)
    │
    ▼
Kubelet → gRPC (protobuf) → containerd
    │
    ├─► RunPodSandbox:
    │   sandbox cgroup created, no limits written for pause container
    │
    ├─► CreateContainer + StartContainer (per app container):
    │   containerd translates CRI spec → OCI spec (config.json)
    │   limits land in config.json here:
    │       cpu.max     = "quota period"  ← e.g. "50000 100000" = 50% of one core
    │       memory.max  = bytes           ← hard memory ceiling
    │   containerd → shim → runc
    │       runc writes cpu.max + memory.max to container-level cgroup
    │       runc writes PID → cgroup.procs
    │       runc calls clone() + execve()  ← process is running
    │
    ▼
Linux kernel enforces:
    cpu.max      → CFS bandwidth control: process throttled when quota exhausted
    memory.max   → hard limit: process receives SIGKILL (OOM kill) if exceeded
```

Two things stand out compared to the `requests` chain. First, `limits` skip the pod-level cgroup — there is no pod-level hard ceiling. Each container has its own independent ceiling, and nothing at the pod level prevents two containers in the same pod from both hitting their individual limits simultaneously. Second, while `requests` are written by kubelet before the runtime is called, `limits` are written by runc at the very end of the chain, directly into the container-level cgroup. The cgroup hierarchy itself is described in detail in the [requests article](/post/limit-request-k8s).

## What the Kernel Enforces

### `cpu.max` → CFS Bandwidth Control

CPU limits are enforced via the **CFS bandwidth controller**. The `cpu.max` file contains two values: a quota and a period.

```
# cat /sys/fs/cgroup/kubepods/burstable/pod<uid>/<container-id>/cpu.max
50000 100000
```

This means: within every 100ms period, this container may consume at most 50ms of CPU time. Once the quota is exhausted, the kernel **throttles** the container — its processes are placed in a throttled state and cannot run until the next period begins, even if the node has idle CPU capacity available.

The conversion from a manifest value to `cpu.max`:

```
quota  = limit_millicores / 1000 * period
period = 100000 (microseconds) — default

# Example: limits.cpu = 500m
quota = 500 / 1000 * 100000 = 50000
cpu.max = "50000 100000"
```

The critical point: **throttling does not kill the process**. A throttled container is alive and will resume when the next period starts. From the outside it appears slow or unresponsive. This is why CPU limit violations are often invisible — there's no event, no restart, no error in `kubectl describe`. The container just runs slower than expected.

You can verify throttling directly:

```shell
# Check throttling stats for a container
cat /sys/fs/cgroup/kubepods/burstable/pod<uid>/<container-id>/cpu.stat

nr_periods 1023
nr_throttled 311          ← number of periods where quota was exhausted
throttled_time 4891234567 ← total nanoseconds spent throttled
```

Or via kubectl:

```shell
kubectl top pod <pod-name> --containers
```

If a container consistently reports CPU usage near its limit, throttling is almost certainly occurring even if the pod appears healthy.

### `memory.max` → Hard Memory Ceiling and OOM Kill

Memory limits are fundamentally different from CPU limits. There is no concept of "memory throttling" — you cannot slow down memory consumption the way the kernel can pause CPU execution. When a container exceeds `memory.max`, the kernel has only one option: **kill a process**.

This is handled by the kernel's OOM killer. When a container's memory usage hits `memory.max`, the kernel triggers an OOM kill scoped to that cgroup — it looks for a process to kill within the container, not across the whole node. The target is selected based on `oom_score_adj` (covered in the [requests article](/post/limit-request-k8s)) and memory usage. In practice, with a single-process container, it's always the main process that gets killed.

**What you see when it happens:**

The container's last status in `kubectl describe pod`:

```
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
  Started:      ...
  Finished:     ...
```

Exit code 137 = 128 + 9 (SIGKILL). The kernel sent SIGKILL to the process, the container runtime caught the exit, and Kubernetes recorded the reason.

On the node itself, the kernel logs the event:

```
kernel: Memory cgroup out of memory: Killed process 12345 (myapp)
        total-vm:524288kB, anon-rss:198432kB, file-rss:4096kB
```

**What happens next** depends on the pod's `restartPolicy`. With the default `Always`, kubelet restarts the container. If memory pressure is chronic — the container always reaches its limit — the restart loop continues, and the pod enters `CrashLoopBackOff`. This is one of the most common sources of `CrashLoopBackOff` in production and one of the least obvious, because the symptom (repeated restarts) looks identical to an application crash.

**The difference from node-level OOM:** When a container hits `memory.max`, the OOM kill is scoped to that container's cgroup. The kernel does not look at other pods or the node as a whole — it kills within the boundary. This is cgroup isolation working as intended. A node-level OOM (where the node itself runs out of memory) is a different event entirely, handled by the node-level OOM killer using `oom_score_adj` to select victims across all processes — which is where QoS class becomes critical. That's covered in the next article.

## The Asymmetry Between CPU and Memory Limits

This is worth stating explicitly because it surprises engineers who assume limits behave the same way for both resources:

| | CPU limit hit | Memory limit hit |
|---|---|---|
| Kernel mechanism | CFS bandwidth throttle | OOM kill |
| Process state | Alive, paused until next period | Dead |
| Pod state | Running | Restarting (or CrashLoopBackOff) |
| Visible in kubectl | No — pod appears healthy | Yes — `OOMKilled`, exit code 137 |
| Recovers automatically | Yes — next 100ms period | Only if restartPolicy allows |
| Impact | Latency increase, throughput drop | Service interruption |

The practical implication: **a CPU-limited container fails silently, a memory-limited container fails loudly**. CPU throttling is one of the hardest performance problems to diagnose in Kubernetes precisely because nothing looks wrong from the outside. Memory OOM kills are obvious but more disruptive.

This asymmetry is also why setting limits requires different thinking for CPU and memory. A tight CPU limit degrades performance gradually and invisibly. A tight memory limit causes hard failures. Many teams set memory limits conservatively (close to actual usage) without realizing they're one traffic spike away from an OOM kill loop.

## What's Next

`limits` and `requests` don't exist in isolation — Kubernetes looks at their *relationship* to classify pods into QoS classes: `Guaranteed`, `Burstable`, and `BestEffort`. That classification then feeds directly back into OOM kill priority and eviction order when the node is under pressure. That's the subject of the next article.
