"use client";

import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { MobileHeader } from "./MobileHeader";
import { X } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className="app-shell relative">
      {/* Mobile Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 md:hidden backdrop-blur-sm transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar Wrapper */}
      <div className={`
        fixed inset-y-0 left-0 z-50 w-[280px] bg-white transform transition-transform duration-300 ease-in-out md:translate-x-0 md:static md:h-screen
        ${isSidebarOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"}
      `}>
        <div className="md:hidden absolute top-4 right-4">
          <button onClick={() => setIsSidebarOpen(false)} className="p-1 text-slate-500 hover:text-slate-900">
            <X className="w-6 h-6" />
          </button>
        </div>
        <Sidebar />
      </div>

      <main className="app-shell__main flex-1 min-w-0 bg-slate-50">
        <MobileHeader onOpenSidebar={() => setIsSidebarOpen(true)} />
        <div className="app-shell__content p-4 md:p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
