"use client";

import { useState } from "react";

// NTU serves images with `Cross-Origin-Resource-Policy: same-site`, which
// blocks cross-origin embedding. Route those through our own /api/img proxy.
const HOSTS_NEEDING_PROXY = new Set(["www.ntu.edu.sg", "dr.ntu.edu.sg"]);

function imgSrc(url: string): string {
  try {
    const u = new URL(url);
    if (HOSTS_NEEDING_PROXY.has(u.host)) {
      return `/api/img?u=${encodeURIComponent(url)}`;
    }
  } catch {
    /* fall through */
  }
  return url;
}

// Renders a faculty headshot with a graceful fallback placeholder. Some source
// sites (e.g. IBPS) list photo URLs that 404, either because they were never
// uploaded or were removed; onError swaps in the "no photo" tile so broken
// links don't leak into the UI.
export function FacultyPhoto({ url }: { url?: string }) {
  const [broken, setBroken] = useState(false);
  if (!url || broken) {
    return (
      <div className="w-20 h-20 rounded-lg bg-black/5 dark:bg-white/5 shrink-0 grid place-items-center text-xs text-black/40 dark:text-white/40">
        no photo
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={imgSrc(url)}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
      className="w-20 h-20 rounded-lg object-cover bg-black/5 dark:bg-white/5 shrink-0"
    />
  );
}
