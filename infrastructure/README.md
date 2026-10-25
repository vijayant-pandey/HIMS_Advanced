# Infrastructure (Artifact C)

Nothing is provisioned yet. Following spec 34.4, the system is built and tested locally (Stage A)
before any AWS spend. AWS work starts at Stage B with the Development environment
(HIMS-OPS-003 and HIMS-OPS-005).

Target layout (spec 30.4):

```text
infrastructure/
  terraform/
    modules/        network, ecs-service, rds-postgres, redis, object-storage, kms, secrets,
                    monitoring, customer-environment
    environments/   development, qa, staging, production
    customers/      one directory of inputs per hospital organization (no copy-pasted stacks)
  docker/
  scripts/
  runbooks/
```

The backend image already supports every ECS role: API, worker, beat, outbox dispatcher and the
migration job. See `backend/Dockerfile`.
