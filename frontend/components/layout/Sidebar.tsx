"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CandlestickChart,
  LayoutDashboard,
  Activity,
  Receipt,
  ShieldAlert,
  FlaskConical,
  Wallet,
} from "lucide-react";
import { motion } from "framer-motion";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/wallet", label: "Wallet", icon: Wallet },
  { href: "/signals", label: "Signals", icon: Activity },
  { href: "/trades", label: "Trades", icon: Receipt },
  { href: "/risk", label: "Risk", icon: ShieldAlert },
  { href: "/validation", label: "Validation", icon: FlaskConical },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed top-0 left-0 h-screen w-[240px] flex flex-col bg-zinc-900/80 border-r border-zinc-800 z-50">
      {/* Brand header */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2">
          <span className="text-emerald-400"><CandlestickChart size={22} /></span>
          <span className="text-[15px] font-medium text-zinc-100">
            AlphaCore
          </span>
        </div>
        <p className="text-[12px] text-zinc-500 mt-0.5 ml-8">
          Autonomous crypto quant
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-[10px] rounded-md text-[14px] transition-colors ${
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              }`}
            >
              <span><Icon size={18} /></span>
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* System status */}
      <div className="px-5 pb-5">
        <div className="flex items-center gap-2">
          <motion.div
            className="w-[7px] h-[7px] rounded-full bg-emerald-500"
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          />
          <span className="text-[12px] text-zinc-400">Live</span>
        </div>
        <span className="inline-block mt-1 text-[10px] font-medium text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">
          Testnet
        </span>
      </div>
    </aside>
  );
}
