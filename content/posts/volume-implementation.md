---
title: How Kubernetes Mounts Volumes into a Container
date: 02.07.2026
slug: k8s-mount-volumes
summary: How Kubernetes mounts volumes into a container — a detailed walk from kubectl apply to kubelet and runtime actions.
tags:
  - devops
  - kubernetes
  - volumes
---

## Disclaimer

The goal of this article is to understand how volumes are created and mounted into a container's filesystem. We focus on two of the simplest volume types: `EmptyDir`, a true ephemeral volume tied to the pod's lifecycle, and `HostPath`, which points directly at a path on the node's filesystem and can outlive the pod if it's rescheduled onto the same node. They aren't the same category, but they're a useful pair to compare because the kubelet handles them so differently.

We'll briefly touch on how the manifest passes through the API server, etcd, controller manager, and scheduler, then spend most of the article on what the kubelet and the container runtime actually do.

## Preparations

We start with a manifest that has two volumes of different types: `HostPath` and `EmptyDir`.

```yaml
# pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: ephemeral-pod
spec:
  containers:
  - name: app
    image: nginx
    volumeMounts:
    - name: temp-storage
      mountPath: /tmp/data
    - name: host-logs
      mountPath: /var/log/host
  volumes:
  - name: temp-storage
    emptyDir:
      sizeLimit: 1Gi
  - name: host-logs
    hostPath:
      path: /var/log/app
      type: DirectoryOrCreate
```

## K8s Handling the Manifest

### kubectl (client side)

When we hit enter, `kubectl` does several things before anything touches the cluster:

* It reads `pod.yaml`, parses it, and validates the structure locally.
* Because we used `apply` (not `create`), kubectl computes a three-way merge patch. It compares the last-applied configuration (stored in the `kubectl.kubernetes.io/last-applied-configuration` annotation), your new file, and the live object. This is what makes `apply` declarative and idempotent.
* It reads our kubeconfig to find the API server address and our credentials (certs, tokens, etc.).
* It sends an HTTPS request to the API server. For a brand-new object this is essentially a `POST` to `/api/v1/namespaces/{ns}/pods`; for an existing one it's a `PATCH`.

### API server (kube-apiserver)

The API server is the only component that talks to etcd, so everything funnels through it:

* **Authentication** — Who are you? (client cert, bearer token, OIDC, etc.)
* **Authorization** — Are you allowed to create a Pod in this namespace? (RBAC checks.)
* **Admission control** — A series of admission plugins run. Mutating admission webhooks/controllers may modify the object first (e.g., inject defaults, sidecars, set default resource limits); validating admission webhooks run afterward and can reject it.
* **Schema validation** — The object is validated against the built-in schema and defaults are applied.

Once it passes all of that, the API server writes the Pod object into etcd.

### etcd

etcd is the cluster's consistent key-value store — the single source of truth. The Pod spec is persisted here. At this moment the Pod exists as desired state, but `spec.nodeName` is still empty and no container is running anywhere. The API server acknowledges the write, and kubectl prints something like `pod/ephemeral-pod created`.

### Controllers and the scheduler (watching, not polling)

Kubernetes components don't poll etcd directly. Instead they establish watches through the API server and react to events.

* **Controller manager (kube-controller-manager)** — for a bare Pod created directly, no controller does much, because it's just a Pod — there's no higher-level object like a Deployment or ReplicaSet behind it.
* **Scheduler (kube-scheduler)** — watches for Pods with no `nodeName` assigned. It picks up our new Pod and runs a two-phase process: filtering (which nodes can even fit this Pod — resource requests, taints/tolerations, node selectors, affinity rules) and scoring (ranking the surviving nodes to find the best one). In our case nothing special happens, since we didn't specify any requests, limits, or affinity — a less-loaded node gets picked by the default `LeastAllocated` scoring strategy (covered in more depth in the [requests article](/post/limit-request-k8s)).

Having chosen a node, the scheduler doesn't launch anything itself. It performs a binding: it tells the API server to set `spec.nodeName` on the Pod, and the API server writes that update back to etcd.

So far, the kubelet has learned via the Watch API that the pod has been assigned to its node. Here's where it gets interesting.

## Kubelet and Runtime

### Stage 1: Kubelet Receives the Pod and Reconciles Volumes

Once the scheduler binds `ephemeral-pod` to a node, the kubelet on that node picks it up via its pod watch. The kubelet's Volume Manager runs a reconciliation loop comparing the "desired state of world" (volumes this pod needs) against the "actual state of world" (what's currently mounted). It computes that two volumes must be set up before any container can start.

Volume setup in the kubelet happens through the volume plugin interface. Each volume type has a plugin implementing operations conceptually named `SetUp` (and `TearDown`). Some volume types also go through `MountDevice` (attach/format for block devices), but neither `emptyDir` nor `hostPath` needs that — they're node-local and require no attachment.

### Stage 2: Preparing Each Volume on the Host

**The `EmptyDir` (`temp-storage`, `1Gi` limit)**

The kubelet's `emptyDir` plugin creates a directory on the host under the kubelet's pod directory, following this pattern:

```shell
/var/lib/kubelet/pods/<pod-UID>/volumes/kubernetes.io~empty-dir/temp-storage/
```

Because we didn't specify a medium, the default medium is disk (the node's filesystem), so this is just a plain directory created with `os.MkdirAll` — no special mount happens for the storage itself at this point.

The interesting part is `sizeLimit: 1Gi`. How this is enforced depends on the kubelet's configuration for local storage capacity isolation: without filesystem-quota-based monitoring enabled, the limit is enforced reactively — the kubelet periodically checks disk usage on the directory via its eviction/monitoring machinery, and evicts the pod if usage exceeds `1Gi`. With project quotas enabled (XFS/ext4 `prjquota`), the kernel enforces the limit at write time instead, giving a hard cap. (Worth double-checking the exact feature-gate names against the current Kubernetes version before you rely on this in production — they've shifted between releases.)

If we had specified `medium: Memory`, the kubelet would instead mount a tmpfs:

```shell
mount -t tmpfs -o size=1073741824 tmpfs /var/lib/kubelet/pods/<UID>/volumes/kubernetes.io~empty-dir/temp-storage
```

and the kernel would enforce the size limit directly.

**The `HostPath` (`host-logs`, `/var/log/app`, `DirectoryOrCreate`)**

The `hostPath` plugin is much simpler and, notably, does not create any new directory under `/var/lib/kubelet`. It uses the host path directly. Because we set `type: DirectoryOrCreate`, the plugin checks whether `/var/log/app` exists on the node:

* If it doesn't exist, the kubelet creates it (mode `0755`, owned by root, since the kubelet itself runs as root).
* If it exists but isn't a directory, setup fails with an error. The `type` field is a safety check — with a plain `hostPath` (no `type`), Kubernetes wouldn't verify anything at all, which is why explicit types are recommended.

No mount is performed here either. The host path is used as-is and passed straight to the runtime.

After Stage 2, the kubelet has two absolute host paths ready:

```shell
/var/lib/kubelet/pods/<UID>/volumes/kubernetes.io~empty-dir/temp-storage
/var/log/app
```

### Stage 3: Kubelet Builds the CRI Request

Now the kubelet talks to the container runtime over the CRI gRPC API, typically over a Unix socket like `/run/containerd/containerd.sock`. Container creation happens in two conceptual steps:

1. `RunPodSandbox` creates the pod's sandbox — the "pause" container that holds the shared namespaces (network, IPC, etc.).
2. `CreateContainer` is then called for your app container.

The crucial part is the `CreateContainerRequest`'s `ContainerConfig`, which contains a list of mounts. The kubelet translates each `volumeMount` into a CRI `Mount` message that references the host path it prepared in Stage 2:

```yaml
mounts: [
  {
    host_path:      "/var/lib/kubelet/pods/<UID>/volumes/kubernetes.io~empty-dir/temp-storage",
    container_path: "/tmp/data",
    readonly:       false,
    propagation:    PROPAGATION_PRIVATE
  },
  {
    host_path:      "/var/log/app",
    container_path: "/var/log/host",
    readonly:       false,
    propagation:    PROPAGATION_PRIVATE
  }
]
```

Note that from the CRI's perspective, both volumes are now identical — just a host path that needs to appear at a container path. The runtime has no idea one was an `emptyDir` and the other a `hostPath`. That abstraction was fully resolved by the kubelet.

## Stage 4: CRI Runtime Generates the OCI Spec

The CRI runtime (`containerd` via its CRI plugin, or CRI-O) takes this request and produces an OCI runtime specification (`config.json`). Each CRI mount becomes an entry in the OCI spec's mounts array, expressed as a Linux bind mount:

```json
{
  "destination": "/tmp/data",
  "type": "bind",
  "source": "/var/lib/kubelet/pods/<UID>/volumes/kubernetes.io~empty-dir/temp-storage",
  "options": ["rbind", "rprivate", "rw"]
},
{
  "destination": "/var/log/host",
  "type": "bind",
  "source": "/var/log/app",
  "options": ["rbind", "rprivate", "rw"]
}
```

`PROPAGATION_PRIVATE` from CRI maps to the `rprivate` mount propagation option, meaning mount events don't propagate between host and container.

## Stage 5: `runc` and the Kernel Perform the Actual Mounts

`containerd` then invokes the OCI runtime (`runc`) to create and start the container. This is where the real Linux work happens: `runc` calls `clone()` to create a new process with the `CLONE_NEWNS` flag (along with other namespace flags), giving the container a fresh mount namespace. This isolates the container's view of the filesystem tree from the host.

Inside this new namespace, `runc` sets up the root filesystem. It typically uses `pivot_root` to switch the process's root to the container's rootfs (the unpacked nginx image layers, usually assembled via an overlayfs mount). Before or during this, it processes each mount in the OCI spec.

For each bind mount, `runc` issues the `mount(2)` syscall. Conceptually, for our two volumes:

```c
// emptyDir → /tmp/data
mount("/var/lib/kubelet/pods/<UID>/volumes/kubernetes.io~empty-dir/temp-storage",
      "<container-rootfs>/tmp/data",
      NULL, MS_BIND | MS_REC, NULL);

// hostPath → /var/log/host
mount("/var/log/app",
      "<container-rootfs>/var/log/host",
      NULL, MS_BIND | MS_REC, NULL);
```

A bind mount makes an existing directory tree appear at a second location — it doesn't copy data; both paths point at the same underlying inodes/dentries. This is why writes inside the container at `/tmp/data` instantly appear in the host's kubelet pod directory, and why anything in `/var/log/app` on the node is immediately visible at `/var/log/host` inside the container.

`runc` then applies the propagation flag with a second call — e.g. `mount(NULL, target, NULL, MS_PRIVATE | MS_REC, NULL)` for `rprivate` — and remounts read-only if requested, with `MS_REMOUNT | MS_RDONLY`. If the container path (`/tmp/data`) doesn't already exist in the image's rootfs, `runc` creates it first.

Because all of this happens inside the container's mount namespace, these mounts are invisible in the host's default namespace mount table — the host only sees the plain kubelet directory and `/var/log/app`, not the bind targets.

## Summary

Neither `emptyDir` nor `hostPath` involves anything exotic under the hood — no CSI driver, no attach/detach cycle, no block device. `emptyDir` just gets a fresh directory (or a tmpfs) prepared by the kubelet; `hostPath` reuses a directory that already exists on the node. Both end up as plain Linux bind mounts, set up by `runc` inside the container's own mount namespace, right before the application process starts. Everything Kubernetes-specific — the volume type, the size limit, the `DirectoryOrCreate` check — is resolved before the runtime ever sees it; from `containerd` downward, it's all just host paths and `mount(2)` calls.
