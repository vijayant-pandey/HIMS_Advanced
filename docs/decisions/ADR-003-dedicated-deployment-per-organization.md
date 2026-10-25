# ADR-003: Dedicated deployment/database per hospital organization

**Status:** Accepted (specification section 22)

**Decision:** Each hospital organization receives a dedicated deployment and database; branches (facilities) share that organization's environment by default.

**Reason:** Stronger isolation, independent recovery and customer-specific configuration.

**Trade-off:** More infrastructure, migration and operational automation.

**In code:** `HIMS_DEPLOYMENT_ID` identifies the customer deployment; cache keys and Celery queues are prefixed with it; see ADR-009.
