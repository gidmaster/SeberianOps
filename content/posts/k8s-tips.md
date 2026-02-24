---
title: Kubernetes Tips
date: 20.02.2026
slug: k8s-tips
summary: Some practical k8s tips from the trenches
tags:
  - devops
  - kubernetes
---

## K8s Tips

Things I wish I knew earlier about Kubernetes.

Check your pod status:
```bash
kubectl get pods -n production
kubectl describe pod <pod-name>
```

A simple deployment manifest:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: myapp
          image: myapp:latest
```

Force a rollout:
```python
import subprocess
result = subprocess.run(
    ["kubectl", "rollout", "restart", "deployment/myapp"],
    capture_output=True
)
print(result.stdout.decode())
```