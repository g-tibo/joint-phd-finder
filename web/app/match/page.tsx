"use client";

import { useEffect, useMemo, useState } from "react";
import type { Faculty } from "@/lib/faculty";
import {
  FACULTY,
  NTU_FACULTY,
  PARTNER_NAME,
  PARTNER_TYPE,
  partnerCodes,
} from "@/lib/faculty";
import { FacultyCard } from "@/components/FacultyCard";

type SingleMatch = { id: string; rationale: string };
type TeamMatch = {
  ntu_id: string;
  partner_ids: string[];
  rationale: string;
};
type MatchResponse =
  | { kind: "single"; matches: SingleMatch[] }
  | { kind: "team"; matches: TeamMatch[] };

type UserType = "faculty" | "prospective" | "current";
type FacultySide = "ntu" | "partner";

const KEY_STORAGE = "joint-phd-finder-anthropic-key";

// A small checkbox grid for selecting one-or-many partner universities.
// "All" clears the selection. When nothing is ticked, we treat it as "All".
function PartnerPicker({
  value,
  onChange,
  exclude,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  exclude?: string;
}) {
  const codes = partnerCodes().filter((c) => c !== "NTU" && c !== exclude);
  const allSelected = value.length === 0 || value.length === codes.length;
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() => onChange([])}
        className={
          "text-xs rounded-full px-3 py-1 border transition " +
          (allSelected
            ? "bg-accent text-white border-accent"
            : "border-black/15 dark:border-white/15 hover:border-accent/50")
        }
      >
        All partners
      </button>
      {codes.map((c) => {
        const on = value.includes(c);
        const t = PARTNER_TYPE[c];
        return (
          <button
            key={c}
            type="button"
            onClick={() => onChange(on ? value.filter((x) => x !== c) : [...value, c])}
            className={
              "text-xs rounded-full px-3 py-1 border transition flex items-center gap-1.5 " +
              (on
                ? "bg-accent text-white border-accent"
                : "border-black/15 dark:border-white/15 hover:border-accent/50")
            }
          >
            <span>{PARTNER_NAME[c] ?? c}</span>
            {t && (
              <span className="text-[9px] uppercase tracking-wide font-semibold">
                {t}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// Searchable faculty picker backed by an HTML <datalist>. Stores the selected
// faculty by id; the visible input shows the name for autocomplete.
function FacultyPicker({
  pool,
  value,
  onChange,
  placeholder,
  listId,
}: {
  pool: Faculty[];
  value: string;
  onChange: (id: string) => void;
  placeholder: string;
  listId: string;
}) {
  const byName = useMemo(() => {
    const m: Record<string, string> = {};
    for (const f of pool) {
      const label = `${f.name} — ${f.department ?? ""}`.trim();
      m[label] = f.id;
    }
    return m;
  }, [pool]);
  const selected = pool.find((f) => f.id === value);
  const [text, setText] = useState(
    selected ? `${selected.name} — ${selected.department ?? ""}` : "",
  );
  return (
    <>
      <input
        list={listId}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          const id = byName[e.target.value.trim()];
          onChange(id ?? "");
        }}
        placeholder={placeholder}
        className="w-full rounded-lg border border-black/15 dark:border-white/15 bg-white dark:bg-neutral-900 px-3 py-2 text-sm"
      />
      <datalist id={listId}>
        {Object.keys(byName).map((label) => (
          <option key={label} value={label} />
        ))}
      </datalist>
    </>
  );
}

export default function MatchPage() {
  const [userType, setUserType] = useState<UserType>("faculty");
  const [facultySide, setFacultySide] = useState<FacultySide>("ntu");
  const [facultyId, setFacultyId] = useState("");
  const [partners, setPartners] = useState<string[]>([]);
  const [project, setProject] = useState("");

  const [apiKey, setApiKey] = useState("");
  const [keyFromServer, setKeyFromServer] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [response, setResponse] = useState<MatchResponse | null>(null);

  useEffect(() => {
    fetch("/api/match").then(async (r) => {
      const j = await r.json().catch(() => ({ serverKey: false }));
      setKeyFromServer(!!j.serverKey);
    });
    const stored = localStorage.getItem(KEY_STORAGE);
    if (stored) setApiKey(stored);
  }, []);

  // Reset selections when switching user type so stale state doesn't leak
  // across branches (e.g. partner-uni picks don't carry over from PhD to
  // faculty flow where the meaning differs).
  function changeUserType(t: UserType) {
    setUserType(t);
    setFacultyId("");
    setPartners([]);
    setResponse(null);
    setError("");
  }

  const byId = useMemo(
    () => new Map<string, Faculty>(FACULTY.map((f) => [f.id, f])),
    [],
  );

  const partnerPoolForFaculty = useMemo(
    () => FACULTY.filter((f) => f.partner_university !== "NTU"),
    [],
  );

  async function submit() {
    setError("");
    setResponse(null);
    if (!project.trim()) {
      setError("Describe your project first.");
      return;
    }
    if (!keyFromServer && !apiKey.trim()) {
      setError("Paste an Anthropic API key, or ask the site owner to configure one.");
      return;
    }
    if (apiKey) localStorage.setItem(KEY_STORAGE, apiKey);

    // Validate per-branch required selections.
    if (userType === "current" && !facultyId) {
      setError("Select your current NTU supervisor first.");
      return;
    }

    setLoading(true);
    try {
      const r = await fetch("/api/match", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(apiKey ? { "x-anthropic-key": apiKey } : {}),
        },
        body: JSON.stringify({
          userType,
          facultySide: userType === "faculty" ? facultySide : undefined,
          facultyId: facultyId || undefined,
          partners: partners.length ? partners : undefined,
          project,
        }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t || `Request failed (${r.status})`);
      }
      const j = (await r.json()) as MatchResponse;
      setResponse(j);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <section className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">AI Match</h1>
        <p className="mt-2 text-black/70 dark:text-white/70 max-w-2xl">
          Describe your project. Claude will rank faculty across NTU and the
          Joint PhD partner universities. Your description and the directory
          are sent to the Anthropic API; nothing is stored by this site.
        </p>
      </section>

      {/* User-type selector — drives which sub-fields are shown. */}
      <section className="mb-5">
        <label className="block text-sm font-medium mb-2">I am a…</label>
        <div className="flex flex-wrap gap-2">
          {[
            { k: "faculty" as const, label: "Faculty member" },
            { k: "prospective" as const, label: "Prospective PhD student" },
            { k: "current" as const, label: "Current PhD student" },
          ].map(({ k, label }) => (
            <button
              key={k}
              type="button"
              onClick={() => changeUserType(k)}
              className={
                "text-sm rounded-lg px-3 py-1.5 border transition " +
                (userType === k
                  ? "bg-accent text-white border-accent"
                  : "border-black/15 dark:border-white/15 hover:border-accent/50")
              }
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* ---------- Branch 1: Faculty ---------- */}
      {userType === "faculty" && (
        <section className="mb-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              I am a faculty member at…
            </label>
            <div className="flex flex-wrap gap-2">
              {[
                { k: "ntu" as const, label: "NTU" },
                { k: "partner" as const, label: "A partner university" },
              ].map(({ k, label }) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setFacultySide(k);
                    setFacultyId("");
                    setPartners([]);
                  }}
                  className={
                    "text-sm rounded-lg px-3 py-1.5 border transition " +
                    (facultySide === k
                      ? "bg-accent text-white border-accent"
                      : "border-black/15 dark:border-white/15 hover:border-accent/50")
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {facultySide === "ntu" && (
            <>
              <div>
                <label className="block text-sm font-medium mb-2">
                  Your NTU profile (optional — lets us factor in your research areas)
                </label>
                <FacultyPicker
                  pool={NTU_FACULTY}
                  value={facultyId}
                  onChange={setFacultyId}
                  placeholder="Start typing your name…"
                  listId="ntu-faculty-list"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">
                  Search which partner universities?
                </label>
                <PartnerPicker value={partners} onChange={setPartners} />
              </div>
            </>
          )}

          {facultySide === "partner" && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Your profile at the partner university (optional)
              </label>
              <FacultyPicker
                pool={partnerPoolForFaculty}
                value={facultyId}
                onChange={setFacultyId}
                placeholder="Start typing your name…"
                listId="partner-faculty-list"
              />
              <p className="mt-1 text-xs text-black/50 dark:text-white/40">
                We'll rank NTU faculty as potential Joint PhD partners.
              </p>
            </div>
          )}
        </section>
      )}

      {/* ---------- Branch 2: Prospective PhD student ---------- */}
      {userType === "prospective" && (
        <section className="mb-5">
          <label className="block text-sm font-medium mb-2">
            Search which partner universities?
          </label>
          <PartnerPicker value={partners} onChange={setPartners} />
          <p className="mt-2 text-xs text-black/50 dark:text-white/40">
            We'll suggest supervisor teams — one NTU faculty paired with one or
            more partner faculty — matched to your project.
          </p>
        </section>
      )}

      {/* ---------- Branch 3: Current PhD student ---------- */}
      {userType === "current" && (
        <section className="mb-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              Your current NTU supervisor
            </label>
            <FacultyPicker
              pool={NTU_FACULTY}
              value={facultyId}
              onChange={setFacultyId}
              placeholder="Start typing your supervisor's name…"
              listId="current-supervisor-list"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">
              Search which partner universities?
            </label>
            <PartnerPicker value={partners} onChange={setPartners} />
          </div>
        </section>
      )}

      <label className="block text-sm font-medium mb-1">Project description</label>
      <textarea
        value={project}
        onChange={(e) => setProject(e.target.value)}
        placeholder={
          userType === "prospective"
            ? "e.g., I want to study the role of autophagy in neurodegeneration using C. elegans and mouse models, ideally combining genetics (NTU) with advanced imaging (partner)."
            : "Describe your project, question, or the technique you're looking to complement."
        }
        className="w-full min-h-[160px] rounded-lg border border-black/15 dark:border-white/15 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30"
      />

      {!keyFromServer && (
        <div className="mt-4">
          <label className="block text-sm font-medium mb-1">
            Anthropic API key{" "}
            <span className="text-black/50 dark:text-white/40 font-normal">
              (stored locally, never sent to this site)
            </span>
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-ant-…"
            className="w-full rounded-lg border border-black/15 dark:border-white/15 bg-white dark:bg-neutral-900 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={submit}
          disabled={loading}
          className="rounded-lg bg-accent text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {loading ? "Finding matches…" : "Find matches"}
        </button>
        {error && <span className="text-sm text-accent">{error}</span>}
      </div>

      {response?.kind === "single" && response.matches.length > 0 && (
        <section className="mt-8">
          <h2 className="text-sm font-medium text-black/60 dark:text-white/60 mb-3">
            Top matches
          </h2>
          <div className="grid gap-3">
            {response.matches.map((m, i) => {
              const f = byId.get(m.id);
              if (!f) return null;
              return <FacultyCard key={m.id} f={f} rank={i + 1} rationale={m.rationale} />;
            })}
          </div>
        </section>
      )}

      {response?.kind === "team" && response.matches.length > 0 && (
        <section className="mt-8 space-y-5">
          <h2 className="text-sm font-medium text-black/60 dark:text-white/60">
            Suggested supervisor teams
          </h2>
          {response.matches.map((t, i) => {
            const ntu = byId.get(t.ntu_id);
            const partners = t.partner_ids
              .map((pid) => byId.get(pid))
              .filter((x): x is Faculty => !!x);
            if (!ntu) return null;
            return (
              <div
                key={`${t.ntu_id}-${i}`}
                className="rounded-xl border border-accent/30 bg-accent/5 p-4 space-y-3"
              >
                <div className="flex items-baseline gap-2">
                  <span className="text-xs font-mono bg-accent/10 text-accent px-1.5 py-0.5 rounded">
                    Team #{i + 1}
                  </span>
                  <p className="text-sm italic text-black/70 dark:text-white/70">
                    {t.rationale}
                  </p>
                </div>
                <div className="grid gap-3">
                  <FacultyCard f={ntu} />
                  {partners.map((p) => (
                    <FacultyCard key={p.id} f={p} />
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      )}
    </>
  );
}
