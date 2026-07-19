// Single source of truth for the primary navigation — consumed by both the
// desktop sidebar and the mobile drawer so the two can never drift apart.

export type NavGroup = "plan" | "sourcing" | "monitor" | "operate" | "intelligence" | "settings";

export type NavItem = {
  href: string;
  label: string;
  group: NavGroup;
};

export const NAV: NavItem[] = [
  { href: "/projects", label: "Projects", group: "plan" },
  { href: "/ingest", label: "Ingest Data", group: "plan" },
  { href: "/sourcing", label: "Sourcing", group: "sourcing" },
  { href: "/approvals", label: "Approvals", group: "sourcing" },
  { href: "/overview", label: "Overview", group: "monitor" },
  { href: "/weekly-plan", label: "Weekly Plan", group: "monitor" },
  { href: "/risks", label: "Risks", group: "monitor" },
  { href: "/vendors", label: "Vendors", group: "operate" },
  { href: "/expediting", label: "Expediting", group: "operate" },
  { href: "/logistics", label: "Logistics", group: "operate" },
  { href: "/pos", label: "Purchase Orders", group: "operate" },
  { href: "/commercial", label: "Commercial", group: "operate" },
  { href: "/agent", label: "Agent", group: "intelligence" },
  { href: "/simulate", label: "Simulate", group: "intelligence" },
  { href: "/audit", label: "Audit Trail", group: "monitor" },
  { href: "/integrations", label: "SAP / Integrations", group: "settings" },
];

export const GROUP_LABEL: Record<NavGroup, string> = {
  plan: "Plan",
  sourcing: "Sourcing",
  monitor: "Monitor",
  operate: "Operate",
  intelligence: "Intelligence",
  settings: "Settings",
};

export const GROUP_ORDER: NavGroup[] = [
  "plan",
  "sourcing",
  "monitor",
  "operate",
  "intelligence",
  "settings",
];

export function navGroups(): { group: NavGroup; items: NavItem[] }[] {
  return GROUP_ORDER.map((group) => ({
    group,
    items: NAV.filter((item) => item.group === group),
  }));
}

/** Single-letter keys for g-then-key navigation — one per live NAV route. */
export const NAV_SHORTCUT_KEY: Record<string, string> = {
  "/projects": "p",
  "/ingest": "d",
  "/sourcing": "s",
  "/approvals": "a",
  "/overview": "o",
  "/weekly-plan": "w",
  "/risks": "r",
  "/vendors": "v",
  "/expediting": "e",
  "/logistics": "l",
  "/pos": "b",
  "/commercial": "c",
  "/agent": "t",
  "/simulate": "m",
  "/audit": "u",
  "/integrations": "f",
};

export type NavShortcut = { key: string; href: string; label: string };

/** g-then-key destinations in sidebar order — derived from NAV so shortcuts can't drift. */
export function navShortcuts(): NavShortcut[] {
  return NAV.flatMap((item) => {
    const key = NAV_SHORTCUT_KEY[item.href];
    return key ? [{ key, href: item.href, label: item.label }] : [];
  });
}

export function navShortcutMap(): Record<string, NavShortcut> {
  return Object.fromEntries(navShortcuts().map((s) => [s.key, s]));
}
