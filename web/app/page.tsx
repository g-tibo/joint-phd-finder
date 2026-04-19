"use client";

import { useMemo, useState } from "react";
import {
  FACULTY,
  PARTNER_NAME,
  PARTNER_TYPE,
  partnerCodes,
  departments,
  search,
} from "@/lib/faculty";
import { FacultyCard } from "@/components/FacultyCard";

export default function BrowsePage() {
  const [q, setQ] = useState("");
  const [partner, setPartner] = useState("");
  const [dept, setDept] = useState("");

  const codes = partnerCodes();
  const deptOptions = useMemo(
    () => (partner ? departments(partner) : []),
    [partner],
  );
  const results = useMemo(
    () =>
      search(q, {
        partner: partner || undefined,
        department: dept || undefined,
      }),
    [q, partner, dept],
  );

  // Counts per partner, so visitors can see the size of each sub-directory
  // without having to select the filter first.
  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const f of FACULTY) {
      m[f.partner_university] = (m[f.partner_university] ?? 0) + 1;
    }
    return m;
  }, []);

  return (
    <>
      <section className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          NTU Joint PhD faculty finder
        </h1>
        <p className="mt-2 text-black/70 dark:text-white/70 max-w-2xl">
          Browse {FACULTY.length} faculty across NTU and its Joint PhD partner
          universities. Jump to{" "}
          <a href="/match" className="text-accent hover:underline">
            AI Match
          </a>{" "}
          to describe your project and get ranked suggestions — tailored for
          faculty or prospective PhD students.
        </p>
      </section>

      {/* Partner-university chip row — fast filter + shows counts + Degree/Supervision tag. */}
      <section className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => {
            setPartner("");
            setDept("");
          }}
          className={
            "text-xs rounded-full px-3 py-1 border transition " +
            (partner === ""
              ? "bg-accent text-white border-accent"
              : "border-black/15 dark:border-white/15 hover:border-accent/50")
          }
        >
          All ({FACULTY.length})
        </button>
        {codes.map((code) => {
          const t = PARTNER_TYPE[code];
          return (
            <button
              key={code}
              onClick={() => {
                setPartner(code);
                setDept("");
              }}
              className={
                "text-xs rounded-full px-3 py-1 border transition flex items-center gap-1.5 " +
                (partner === code
                  ? "bg-accent text-white border-accent"
                  : "border-black/15 dark:border-white/15 hover:border-accent/50")
              }
            >
              <span>
                {PARTNER_NAME[code] ?? code} ({counts[code] ?? 0})
              </span>
              {t && (
                <span
                  className={
                    "text-[9px] uppercase tracking-wide font-semibold px-1 rounded " +
                    (t === "Degree"
                      ? "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300"
                      : "bg-sky-500/20 text-sky-700 dark:text-sky-300")
                  }
                >
                  {t}
                </span>
              )}
            </button>
          );
        })}
      </section>

      <section
        className={`mb-4 grid gap-3 ${
          partner ? "md:grid-cols-[1fr_auto]" : "md:grid-cols-1"
        }`}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search names, departments, keywords…"
          className="rounded-lg border border-black/15 dark:border-white/15 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        {partner && (
          <select
            value={dept}
            onChange={(e) => setDept(e.target.value)}
            className="rounded-lg border border-black/15 dark:border-white/15 bg-white dark:bg-neutral-900 px-3 py-2 text-sm"
          >
            <option value="">All departments</option>
            {deptOptions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        )}
      </section>

      <p className="text-xs text-black/50 dark:text-white/40 mb-3">
        {results.length} result{results.length === 1 ? "" : "s"}
      </p>

      <div className="grid gap-3">
        {results.map((f) => (
          <FacultyCard key={f.id} f={f} />
        ))}
      </div>
    </>
  );
}
