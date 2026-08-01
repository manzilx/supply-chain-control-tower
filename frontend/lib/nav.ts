// Single source of truth for the primary navigation — consumed by both the
// desktop sidebar and the mobile drawer so the two can never drift apart.

export type NavGroup = "plan" | "sourcing" | "monitor" | "operate" | "store" | "intelligence" | "settings";

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
  { href: "/inventory", label: "Inventory", group: "store" },
  { href: "/store/grn-triage", label: "GRN Triage", group: "store" },
  { href: "/store/grns", label: "GRN Register", group: "store" },
  { href: "/store/devices", label: "Field Devices", group: "store" },
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
  store: "Site Store",
  intelligence: "Intelligence",
  settings: "Settings",
};

export const GROUP_ORDER: NavGroup[] = [
  "plan",
  "sourcing",
  "monitor",
  "operate",
  "store",
  "intelligence",
  "settings",
];

export function navGroups(): { group: NavGroup; items: NavItem[] }[] {
  return GROUP_ORDER.map((group) => ({
    group,
    items: NAV.filter((item) => item.group === group),
  }));
}

/**
 * Single-letter keys for g-then-key navigation — one per live NAV route.
 * Keys must be unique (navShortcutMap keys by letter, so a duplicate silently
 * shadows the earlier route), must not be "g" (the arming key re-arms the
 * sequence before the target lookup runs, so "g" can never be a destination),
 * and must not collide with the standalone keys keyboard-shortcuts.tsx owns
 * ("i" toggles the Copilot, "?" opens help).
 */
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
  "/inventory": "n", // iNventory
  "/store/grn-triage": "q", // triage Queue
  "/store/grns": "h", // GRN History
  "/store/devices": "k", // field Kit
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
