1. Do you need to purchase AWS before development?
No. You can begin development without paying for AWS. I recommend starting locally, building the application foundation, and introducing AWS when you are ready to validate cloud infrastructure and deployment.
What you need to purchase or set up
Item	Do you need to pay immediately?	Recommendation
Python, Django, DRF	No	Use the local development environment.
React, TypeScript, Node.js	No	Pin supported versions in the repository.
PostgreSQL, Redis, Celery	No, for local use	Run them locally or through Docker Compose.
Git and VS Code	No	Use Git for version control and VS Code for development.
GitHub repository and Issues	Not necessarily	Start with a private repository and GitHub Issues/Projects.
Paid GitHub plan	Possibly	Consider GitHub Team for a company-owned repository, collaboration, and private deployment-environment secrets. Note: in private repositories, environment required-reviewer approvals need GitHub Enterprise; on Team, the production approval gate must be implemented another auditable way (see spec section 32.8 and the open decision in section 36).
AWS	Not during initial development	Start cloud deployment when you need to validate managed infrastructure, networking, IAM, backups and CI/CD.
Stedi and other payer integrations	Not for initial mock development	Arrange provider access, sandbox testing and any required commercial onboarding when implementing actual integrations.
Domain name	Not immediately	Purchase when hosted environments need stable public domains.
Additional monitoring/security products	Not immediately	Start with cloud-native monitoring, automated checks and appropriate access controls; add products as requirements justify them.

My recommendation: spend nothing on AWS while you establish your local application and tests. Use a GitHub Organization for business ownership, and introduce AWS Dev first. Add QA, Staging and Production infrastructure as you implement the deployment pipeline and approach hospital validation.


2. Your four managed environments and local development
Your model is clear: local development plus four managed environments.
Local — Developer workstation

Write code, run tests, debug Django/React and use local PostgreSQL, Redis and Celery. Use synthetic data.


Development

Automatically deploy approved merges from the development branch. Validate integration and basic workflows.


QA

Functional, regression, API, integration, permission and clinical workflow testing.


Staging — Pre-production

Production-like architecture and configuration. Perform user acceptance testing, release checks and final validation.


Production

Real hospital operations. Only approved releases, restricted deployment access and verified recovery procedures.


A critical distinction: Staging should replicate Production's architecture and application behavior, not its live patient data or credentials. Use synthetic or formally approved de-identified data. Keep each environment's database, secrets and access boundaries separate. Staging can use smaller infrastructure than Production if performance and capacity testing are handled deliberately.
3. The GitHub ticket-to-production process
Your desired workflow is correct. I would implement it with protected branches and controlled artifact promotion.
Step	Activity	Required gate
1	Create a GitHub Issue with scope, acceptance criteria, dependencies and tests.	Ticket approved and ready
2	Create a feature branch from develop.	Ticket linked to branch
3	Implement the change and add tests locally.	Local tests pass
4	Open a pull request to develop.	Code review, CI and security checks pass
5	Merge into develop; automatically deploy Development.	Development smoke and integration tests pass
6	Create a release candidate and promote it to QA.	QA regression and acceptance tests pass
7	Promote that candidate to Staging.	Final validation and authorized sign-off
8	Promote the approved candidate to Production.	Production approval, migration/recovery checks and post-deployment smoke tests

I recommend develop for ongoing integration, main for the production release history, and short-lived feature branches. A release branch can be used to stabilize a particular version.

The important engineering rule is to build the application artifact once and promote the same immutable artifact through QA, Staging and Production. Do not rebuild a different version at each stage. Store the commit SHA, image digest, database migration version, test results and approval evidence for every deployment.

If QA or Staging finds a problem, create a defect ticket, fix it through a pull request, build a new candidate and repeat the affected validation gates. Never fix Production by manually editing the running server.
4. What makes this production-grade rather than a toy?
Beyond the features, the platform needs measurable proof that it behaves safely under failure. Before go-live, I would require at least:
- Automated tenant isolation, authorization and sensitive-document access tests.
- PostgreSQL concurrency tests for bed assignment, inventory and payment posting.
- Idempotency tests for claim submissions and background tasks.
- Clinical workflow validation with authorized hospital professionals.
- A demonstrated backup restoration and disaster-recovery exercise.
- Separate deployment credentials and database isolation for every hospital organization.
- Verified QA and Staging sign-off, with auditable promotion history.
- A documented process for clinical downtime, incidents, recovery and reconciliation.
Your v2 document now establishes the framework for those controls. The next engineering task is to break the specification into GitHub Epics and implementation tickets, beginning with the platform foundation, identity and authorization, dedicated-customer provisioning, data architecture and CI/CD pipeline.
5. Cost items not yet budgeted
Item	When needed	Notes
Per-customer AWS unit cost	Before pricing the first contract	Each dedicated production stack (Multi-AZ RDS, ElastiCache, ECS Fargate, ALB, NAT, WAF, logs, backups) has a fixed monthly baseline per hospital organization. Estimate it in the AWS Pricing Calculator per region (us-east-1 / ap-south-1) and define isolation tiers so smaller hospitals remain viable.
Licensed clinical content	Before the affected domain ships	Drug-interaction knowledge base (different vendors for US and India), CPT (AMA license), DRG grouper for US inpatient claims. SNOMED CT, LOINC and RxNorm are free but carry license obligations.
Stedi and payer transactions	Before live US insurance workflows	Per-transaction or contract pricing; confirm with Stedi.
Messaging	Before notifications ship	SMS (India DLT registration required), email (e.g. Amazon SES), WhatsApp Business if used.
Compliance and assurance	Before production	Penetration test, SOC 2/HITRUST if US customers require it, legal review, cyber insurance.
AWS BAA	Before any US PHI reaches AWS	No fee; accept in AWS Artifact and use only HIPAA-eligible services for PHI.
Team	Throughout	Engineering, QA, clinical informatics and DevOps salaries will usually exceed infrastructure cost.