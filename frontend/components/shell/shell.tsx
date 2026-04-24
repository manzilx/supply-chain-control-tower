import type { ReactNode } from "react";

import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen flex">
      <div className="app-grid-backdrop" aria-hidden />
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col relative z-[1]">
        <TopBar />
        <main className="flex-1 px-6 py-6 max-w-[1400px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
