# Scheduling the Customer Feature Intelligence adapters

`backend/python/scripts/customer_intelligence/*.py` are standalone,
idempotent sync scripts — not connectors wired into the registry (see
`docs/indexing-service.md` §8 for why). They are not scheduled by anything
in this repo; pick whichever fits your deployment:

## Docker Compose

Add one-shot services with a restart policy, or run them from an external
cron on the host:

```yaml
  chargebee-sync:
    build: ./backend/python
    command: python -m scripts.customer_intelligence.chargebee_sync
    env_file: ../../.env
    depends_on:
      - app
    restart: "no"   # trigger via host cron / systemd timer, not restart loops
```

## Kubernetes

Run each adapter as a `CronJob` using the same image as the indexing
deployment:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: chargebee-sync
spec:
  schedule: "*/30 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: chargebee-sync
              image: <same image as the indexing/app deployment>
              command: ["python", "-m", "scripts.customer_intelligence.chargebee_sync"]
              envFrom:
                - secretRef:
                    name: <app secret with CHARGEBEE_*, INTELLIGENCE_INTAKE_TOKEN, etc.>
```

Recommended cadence: revenue snapshots (Chargebee) daily; support/CRM signal
adapters (Freshdesk, Salesforce) every 15–30 minutes. Each script's module
docstring lists the env vars it needs.
