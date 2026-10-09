# Driftwatch documentation

## Start and use

- [Installation and updates](INSTALL.md)
- [FAQ / najczęstsze pytania](FAQ.md)
- User guide: [English](USER_GUIDE.en.md), [Polski](USER_GUIDE.pl.md)
- Administrator guide: [English](ADMIN_GUIDE.en.md), [Polski](ADMIN_GUIDE.pl.md)
- [Deterministic demo](DEMO.md)

## Engineering and operation

- [Monitoring semantics and limitations](MONITORING_SEMANTICS.md)
- [Architecture](ARCHITECTURE.md)
- Decisions: [record comparison](adr/001-record-diff.md),
  [database work queues](adr/002-db-queue.md), [optional AI](adr/003-ai-boundary.md)
- [Deployment and network boundary](DEPLOY.md)
- [Backup, restore and unfinished work](RECOVERY.md)
- [Security and secret scanning](../SECURITY.md)
- [Image advisories and scan interpretation](IMAGE_SECURITY.md)
- [Contributing and reproducible checks](../CONTRIBUTING.md)
- [Preparing a public portfolio repository](PUBLICATION.md)

## Deployment-specific runbooks

The following Polish templates need the operator's actual environment, owners
and measured evidence. They do not establish service guarantees by themselves.

- [Disaster recovery](DISASTER_RECOVERY.pl.md)
- [Incident response](INCIDENT_RESPONSE.pl.md)
- [Data, processors and retention](OPERATIONS_COMPLIANCE.pl.md)
- [Deployment verification checklist](PRODUCTION_READINESS.pl.md)

Keep instructions aligned with implemented behavior. After changing capture,
providers, authorization, schema or deployment topology, rerun the corresponding
tests and update the affected guide. Historical private audits are not part of
the public product documentation.
