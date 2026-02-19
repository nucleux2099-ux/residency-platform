"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, FileText, Settings, HeartPulse, Activity, BookOpen, PenTool } from "lucide-react";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Patients", href: "/patients", icon: Users },
  { label: "Data Ingestion", href: "/ingestion", icon: FileText },
  { label: "Atom Chat", href: "/chat", icon: MessageSquare, description: "AI Assistant" }, // If explicit route exists, else widget
];

// Helper to check active state
function NavLink({ href, label, icon: Icon }: { href: string, label: string, icon: any }) {
  const pathname = usePathname();
  const isActive = pathname.startsWith(href);

  return (
    <Link
      href={href}
      className={`
        flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
        ${isActive
          ? "bg-primary-50 text-primary-700 ring-1 ring-primary-200/50"
          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
        }
      `}
    >
      <Icon className={`w-4 h-4 ${isActive ? "text-primary-600" : "text-slate-400"}`} />
      {label}
    </Link>
  );
}

import { MessageSquare } from "lucide-react";

export function Sidebar() {
  return (
    <aside className="sidebar flex flex-col h-full bg-white border-r border-slate-200">
      {/* Brand */}
      <div className="p-6 pb-4">
        <h1 className="text-xl font-bold text-slate-900 tracking-tight leading-none">
          Residency<span className="text-primary-600">.Platform</span>
        </h1>
        <p className="text-xs text-slate-500 mt-1 font-medium">Thesis: Pancreatic SVT</p>
      </div>

      {/* Main Nav */}
      <nav className="px-3 py-2 space-y-1">
        <div className="px-3 pb-2 pt-1">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Menu</p>
        </div>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} />
        ))}
      </nav>

      <div className="my-4 border-t border-slate-100 mx-6"></div>

      {/* Secondary Nav / Status */}
      <nav className="px-3 space-y-1">
        <div className="px-3 pb-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">System</p>
        </div>
        <div className="px-3 py-2 text-xs text-slate-500 bg-slate-50 rounded-lg mx-3 border border-slate-100">
          <div className="flex justify-between items-center mb-1">
            <span className="font-medium">Status</span>
            <span className="flex h-2 w-2 rounded-full bg-green-500"></span>
          </div>
          <p>Vault: Connected</p>
          <p className="mt-1">v0.1.0-alpha</p>
        </div>
      </nav>

      {/* Footer */}
      <div className="mt-auto p-4 border-t border-slate-100">
        <div className="flex items-center gap-3 px-2">
          <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-700 font-bold text-xs">
            SB
          </div>
          <div>
            <p className="text-sm font-medium text-slate-700">Dr. Bhatla</p>
            <p className="text-xs text-slate-400">Resident</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
