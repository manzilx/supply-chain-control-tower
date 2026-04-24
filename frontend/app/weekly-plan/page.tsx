"use client";

import { PageHeader } from "@/components/page-header";
import { WeeklyPlanView } from "@/components/weekly-plan-view";
import { fetchWeeklyPlan } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

export default function WeeklyPlanPage() {
  const plan = useAsync(fetchWeeklyPlan, []);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Weekly plan"
        title="This Week's Action Plan"
        description="Auto-generated from expediting, planning, sourcing, vendor intel, and commercial rollups. Every item has a why, expected impact, owner, due date, and supporting data."
        right={
          <button className="btn btn-secondary" onClick={() => plan.reload()}>
            Rebuild
          </button>
        }
      />
      <WeeklyPlanView plan={plan.data} loading={plan.loading} error={plan.error} />
    </div>
  );
}
