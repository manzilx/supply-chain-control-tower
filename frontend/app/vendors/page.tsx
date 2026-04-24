"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { fetchVendorConcentration, fetchVendorIntel } from "@/lib/api";
import { formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { Grade } from "@/lib/types";

const GRADE_TONE: Record<Grade, string> = {
  A: "severity-low",
  B: "severity-low",
  C: "severity-medium",
  D: "severity-high",
  F: "severity-critical",
};

export default function VendorsPage() {
  const intel = useAsync(fetchVendorIntel, []);
  const concentration = useAsync(fetchVendorConcentration, []);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (intel.data ?? []).filter(
      (v) =>
        !q ||
        v.vendor.toLowerCase().includes(q) ||
        v.category.toLowerCase().includes(q) ||
        v.country.toLowerCase().includes(q),
    );
  }, [intel.data, query]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Vendors"
        title="Vendor Intelligence"
        description="Approved suppliers scored across delivery, quality, price, responsiveness, claims, and risk. Click a vendor for the full scorecard + alternates."
      />

      <section className="panel space-y-3">
        <h2 className="m-0 text-lg font-bold">Category Concentration</h2>
        {concentration.loading ? (
          <EmptyState title="Loading..." />
        ) : (concentration.data ?? []).length === 0 ? (
          <EmptyState title="No categories" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Vendors</th>
                  <th>Total Spend</th>
                  <th>Top Vendor</th>
                  <th>Top Share</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(concentration.data ?? []).map((c) => (
                  <tr key={c.category}>
                    <td className="font-semibold text-ink">{c.category}</td>
                    <td>{c.vendor_count}</td>
                    <td>{formatMoney(c.total_spend_usd)}</td>
                    <td>
                      <Link
                        href={`/vendors/${encodeURIComponent(c.top_vendor)}`}
                        className="text-accent hover:underline"
                      >
                        {c.top_vendor}
                      </Link>
                    </td>
                    <td className={c.top_vendor_share_pct >= 70 ? "text-warning font-bold" : ""}>
                      {c.top_vendor_share_pct.toFixed(0)}%
                    </td>
                    <td>
                      {c.single_source ? (
                        <span className="badge severity-high">Single source</span>
                      ) : c.top_vendor_share_pct >= 70 ? (
                        <span className="badge severity-medium">Concentrated</span>
                      ) : (
                        <span className="badge severity-low">Diversified</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="flex-1 min-w-[200px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Search</span>
          <input
            placeholder="Name, category, country..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="text-xs text-muted pb-2">{rows.length} vendors</div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {intel.loading ? (
          <div className="p-6"><EmptyState title="Loading vendors..." /></div>
        ) : intel.error ? (
          <div className="p-6 text-[#ff9d9d]">{intel.error}</div>
        ) : rows.length === 0 ? (
          <div className="p-6"><EmptyState title="No vendors" /></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Category</th>
                <th>Country</th>
                <th>Score</th>
                <th>Grade</th>
                <th>OTD</th>
                <th>PPM</th>
                <th>Spend</th>
                <th>Flags</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.vendor}>
                  <td className="font-semibold text-ink">
                    <Link href={`/vendors/${encodeURIComponent(v.vendor)}`} className="hover:underline">
                      {v.vendor}
                    </Link>
                  </td>
                  <td className="text-muted">{v.category}</td>
                  <td className="text-muted">{v.country}</td>
                  <td className="font-bold">{v.composite_score}</td>
                  <td>
                    <span className={`badge ${GRADE_TONE[v.composite_grade]}`}>{v.composite_grade}</span>
                  </td>
                  <td>{v.on_time_delivery_pct.toFixed(0)}%</td>
                  <td className={v.quality_ppm > 1000 ? "text-warning font-semibold" : ""}>{v.quality_ppm}</td>
                  <td>{formatMoney(v.annual_spend_usd)}</td>
                  <td>
                    {v.single_source_exposure ? (
                      <span className="badge severity-high">Single source</span>
                    ) : v.flags_count > 0 ? (
                      <span className="badge severity-medium">{v.flags_count} flag{v.flags_count === 1 ? "" : "s"}</span>
                    ) : (
                      <span className="text-muted text-xs">—</span>
                    )}
                  </td>
                  <td>
                    <Link
                      className="btn btn-secondary text-xs"
                      href={`/vendors/${encodeURIComponent(v.vendor)}`}
                    >
                      Scorecard
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
