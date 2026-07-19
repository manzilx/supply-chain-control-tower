---
type: "query"
date: "2026-05-22T07:55:26.412309+00:00"
question: "Why does PurchaseRequisition bridge sourcing, projects, and the demo orchestration scripts?"
contributor: "graphify"
source_nodes: ["data_sourcing_pr_entity", "fixtures_seed_sourcing_walk_workflow", "data_projects_milestone_entity", "data_audit_event_entity"]
---

# Q: Why does PurchaseRequisition bridge sourcing, projects, and the demo orchestration scripts?

## Answer

The bridge node is 'PurchaseRequisition record' from .data/sourcing.json (the persisted snapshot), betweenness 0.233. It connects 3 communities: (1) references Milestone in .data/projects.json — the project/milestone the PR hangs off (M7.2 tenant_id inheritance via get_project->create_pr); (2) shares_data_with walk_workflow() in fixtures/seed_sourcing.py — the seeder that creates PRs; (3) references AuditEvent in .data/audit.json — every PR mutation emits an audit event. The top-4 betweenness nodes are all .data/*.json snapshot files, showing the structural center of gravity is the persisted in-memory state. The PR is highest because it joins the demand side (projects/BOM), supply side (RFQ/award/PO), and audit log.

## Source Nodes

- data_sourcing_pr_entity
- fixtures_seed_sourcing_walk_workflow
- data_projects_milestone_entity
- data_audit_event_entity