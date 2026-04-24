"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import type { ScorecardComponent } from "@/lib/types";

type Props = {
  components: ScorecardComponent[];
  compareTo?: ScorecardComponent[] | null;
  compareLabel?: string;
};

export function ScorecardRadar({ components, compareTo, compareLabel }: Props) {
  const data = components.map((c) => {
    const row: Record<string, string | number> = {
      dimension: c.label,
      value: c.score,
    };
    if (compareTo) {
      const peer = compareTo.find((p) => p.dimension === c.dimension);
      row.compare = peer ? peer.score : 0;
    }
    return row;
  });

  return (
    <div className="h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="75%">
          <PolarGrid stroke="rgba(132, 165, 191, 0.2)" />
          <PolarAngleAxis
            dataKey="dimension"
            tick={{ fill: "#9db0c1", fontSize: 12 }}
          />
          <PolarRadiusAxis
            domain={[0, 100]}
            angle={90}
            tick={{ fill: "#9db0c1", fontSize: 10 }}
            stroke="rgba(132, 165, 191, 0.2)"
          />
          <Radar
            name="Vendor"
            dataKey="value"
            stroke="#57d4c0"
            fill="#57d4c0"
            fillOpacity={0.35}
          />
          {compareTo ? (
            <Radar
              name={compareLabel ?? "Compare"}
              dataKey="compare"
              stroke="#f0b44c"
              fill="#f0b44c"
              fillOpacity={0.18}
            />
          ) : null}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
