"""Seeded tenants and users for the M7 RBAC/multi-tenant layer.

In-memory only; mirrors the persistence pattern used by the rest of the app.
Each tenant gets one user per role so the persona picker on the login screen
shows the full role matrix for every tenant.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .schemas import Persona, Tenant, User


_tenants: Dict[str, Tenant] = {
    "arcforge": Tenant(
        tenant_id="arcforge",
        name="Arcforge Engineering",
        sector="Power Systems EPC",
    ),
    "northwind": Tenant(
        tenant_id="northwind",
        name="Northwind Heavy Engineering",
        sector="Industrial EPC",
    ),
    "helios": Tenant(
        tenant_id="helios",
        name="Helios Offshore",
        sector="Offshore Oil & Gas",
    ),
}


def _seed_users() -> Dict[str, User]:
    users: Dict[str, User] = {}
    for tenant in _tenants.values():
        slug = tenant.tenant_id
        domain = {
            "arcforge": "arcforge.com",
            "northwind": "northwind.co",
            "helios": "helios-offshore.com",
        }[slug]
        roster = [
            ("admin", "Admin", "admin"),
            ("head", "Procurement Head", "procurement_head"),
            ("buyer", "Senior Buyer", "buyer"),
            ("expeditor", "Lead Expeditor", "expeditor"),
            ("viewer", "Project Controls Viewer", "viewer"),
            ("store", "Site Storekeeper", "storekeeper"),
        ]
        for short, title, role in roster:
            user_id = f"{slug}-{short}-01"
            users[user_id] = User(
                user_id=user_id,
                email=f"{short}@{domain}",
                display_name=f"{tenant.name.split()[0]} {title}",
                tenant_id=slug,
                role=role,  # type: ignore[arg-type]
            )
    return users


_users: Dict[str, User] = _seed_users()


def list_tenants() -> List[Tenant]:
    return list(_tenants.values())


def get_tenant(tenant_id: str) -> Optional[Tenant]:
    return _tenants.get(tenant_id)


def list_users(tenant_id: Optional[str] = None) -> List[User]:
    if tenant_id is None:
        return list(_users.values())
    return [u for u in _users.values() if u.tenant_id == tenant_id]


def get_user(user_id: str) -> Optional[User]:
    return _users.get(user_id)


def list_personas() -> List[Persona]:
    """Public list for the login persona picker."""

    out: List[Persona] = []
    for user in _users.values():
        tenant = _tenants[user.tenant_id]
        out.append(
            Persona(
                user_id=user.user_id,
                display_name=user.display_name,
                email=user.email,
                role=user.role,
                tenant_id=user.tenant_id,
                tenant_name=tenant.name,
            )
        )
    # Stable ordering: by tenant name, then by role priority.
    role_order = {"admin": 0, "procurement_head": 1, "buyer": 2, "expeditor": 3, "viewer": 4, "storekeeper": 5}
    out.sort(key=lambda p: (p.tenant_name, role_order.get(p.role, 99)))
    return out
