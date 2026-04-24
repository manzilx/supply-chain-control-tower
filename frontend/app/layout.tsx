import "./globals.css";

import { Shell } from "@/components/shell/shell";
import { StoreProvider } from "@/lib/store-context";

export const metadata = {
  title: "Supply Chain Control Tower",
  description: "AI-assisted supply chain control tower for engineering companies.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <StoreProvider>
          <Shell>{children}</Shell>
        </StoreProvider>
      </body>
    </html>
  );
}
