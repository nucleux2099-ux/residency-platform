"use client";

import { Menu } from "lucide-react";

export function MobileHeader({ onOpenSidebar }: { onOpenSidebar: () => void }) {
    return (
        <header className="md:hidden sticky top-0 z-30 flex items-center justify-between p-4 bg-white border-b border-slate-200">
            <div className="flex items-center gap-3">
                <button
                    onClick={onOpenSidebar}
                    className="p-2 -ml-2 text-slate-600 hover:bg-slate-100 rounded-lg"
                    aria-label="Open menu"
                >
                    <Menu className="w-6 h-6" />
                </button>
                <h1 className="text-lg font-bold text-slate-800 tracking-tight">Residency Platform</h1>
            </div>
        </header>
    );
}
