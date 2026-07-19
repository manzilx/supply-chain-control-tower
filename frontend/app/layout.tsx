import "./globals.css";

import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/lib/toast-context";
import { CommandPalette } from "@/components/command-palette";
import { Copilot } from "@/components/copilot";
import { KeyboardShortcuts } from "@/components/keyboard-shortcuts";
import { RootFrame } from "@/components/shell/root-frame";

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
        <AuthProvider>
          <ToastProvider>
            <RootFrame>{children}</RootFrame>
            <CommandPalette />
            <Copilot />
            <KeyboardShortcuts />
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
