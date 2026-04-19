import type { Faculty } from "@/lib/faculty";
import { PARTNER_NAME } from "@/lib/faculty";

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

function partnerLabel(code: string): string {
  return PARTNER_NAME[code] ?? code;
}

export function FacultyCard({
  f,
  rank,
  rationale,
}: {
  f: Faculty;
  rank?: number;
  rationale?: string;
}) {
  return (
    <article className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4 flex gap-4 hover:shadow-sm transition-shadow">
      {f.photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imgSrc(f.photo_url)}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          className="w-20 h-20 rounded-lg object-cover bg-black/5 dark:bg-white/5 shrink-0"
        />
      ) : (
        <div className="w-20 h-20 rounded-lg bg-black/5 dark:bg-white/5 shrink-0 grid place-items-center text-xs text-black/40 dark:text-white/40">
          no photo
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 flex-wrap">
          {rank !== undefined && (
            <span className="text-xs font-mono bg-accent/10 text-accent px-1.5 py-0.5 rounded">
              #{rank}
            </span>
          )}
          <a
            href={f.profile_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium hover:underline"
          >
            {f.name}
          </a>
          {f.title && (
            <span className="text-xs text-black/60 dark:text-white/60">· {f.title}</span>
          )}
          {f.partnership_type && (
            <span
              className={
                "text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded " +
                (f.partnership_type === "Degree"
                  ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                  : "bg-sky-500/15 text-sky-700 dark:text-sky-300")
              }
              title={`Joint PhD ${f.partnership_type}`}
            >
              Joint PhD {f.partnership_type}
            </span>
          )}
        </div>
        <div className="text-xs text-black/60 dark:text-white/60 mt-0.5">
          {f.department ? `${f.department} · ` : ""}
          {partnerLabel(f.partner_university)}
        </div>
        {f.research_areas && f.research_areas.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {f.research_areas.slice(0, 8).map((a) => (
              <span
                key={a}
                className="text-[11px] bg-black/5 dark:bg-white/10 rounded px-1.5 py-0.5"
              >
                {a}
              </span>
            ))}
          </div>
        )}
        {rationale && (
          <p className="mt-2 text-sm text-black/70 dark:text-white/70 italic">{rationale}</p>
        )}
        {!rationale && f.summary && (
          <p className="mt-2 text-sm text-black/70 dark:text-white/70 line-clamp-3">
            {f.summary}
          </p>
        )}
        <div className="mt-2 flex gap-3 text-xs text-black/60 dark:text-white/60">
          {f.lab_url && (
            <a
              className="hover:underline"
              href={f.lab_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Lab site ↗
            </a>
          )}
          {f.scholar_url && (
            <a
              className="hover:underline"
              href={f.scholar_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Scholar ↗
            </a>
          )}
          {f.orcid && (
            <a
              className="hover:underline"
              href={f.orcid}
              target="_blank"
              rel="noopener noreferrer"
            >
              ORCID ↗
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
