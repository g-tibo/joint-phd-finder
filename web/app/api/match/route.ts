import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { FACULTY, partnerCodes } from "@/lib/faculty";
import type { Faculty } from "@/lib/faculty";

export async function GET() {
  return NextResponse.json({ serverKey: !!process.env.ANTHROPIC_API_KEY });
}

const MODEL = "claude-haiku-4-5-20251001";

// Tighter shortlist than SG Collab Finder: the Joint-PhD directory is smaller
// and we usually pre-filter by one side of the partnership, so 80 is plenty.
const SHORTLIST_SIZE = 80;

type Body = {
  userType: "faculty" | "prospective" | "current";
  facultySide?: "ntu" | "partner";
  facultyId?: string;
  partners?: string[];
  project: string;
};

const STOPWORDS = new Set([
  "a","an","and","are","as","at","be","by","for","from","has","have","in","into",
  "is","it","of","on","or","that","the","this","to","was","were","will","with",
  "we","our","its","their","they","i","my","you","your","can","could","would",
  "should","but","not","no","do","does","did","using","use","used","based",
  "about","more","some","any","other","many","new","study","studies","research",
  "project","work","interest","interests","area","areas","topic","topics",
  "looking","find","want","wants","need","needs","develop","developing",
]);

function tokenize(s: string): string[] {
  return (s.toLowerCase().match(/[a-z][a-z-]+/g) ?? [])
    .filter((t) => t.length > 2 && !STOPWORDS.has(t));
}

function shortlist(query: string, pool: Faculty[], size: number): Faculty[] {
  const qTokens = new Set(tokenize(query));
  if (qTokens.size === 0) return pool.slice(0, size);
  const scored = pool.map((f) => {
    const areas = (f.research_areas ?? []).join(" ").toLowerCase();
    const summary = (f.summary ?? "").toLowerCase();
    const title = (f.title ?? "").toLowerCase();
    const roles = (f.roles ?? []).join(" ").toLowerCase();
    let score = 0;
    for (const t of qTokens) {
      if (areas.includes(t)) score += 5;
      if (roles.includes(t)) score += 2;
      if (title.includes(t)) score += 1;
      if (summary.includes(t)) score += 1;
    }
    return { f, score };
  });
  scored.sort((a, b) => b.score - a.score);
  if (scored[0].score === 0) return pool.slice(0, size);
  return scored.slice(0, size).map((s) => s.f);
}

function compact(records: Faculty[]) {
  return records.map((f) => ({
    id: f.id,
    name: f.name,
    partner_university: f.partner_university,
    department: f.department ?? "",
    title: f.title ?? "",
    research_areas: (f.research_areas ?? []).slice(0, 8),
    summary: (f.summary ?? "").slice(0, 500),
  }));
}

function stripFences(s: string): string {
  return s.trim().replace(/^```(?:json)?\s*|\s*```$/g, "").trim();
}

// Build an augmented "effective query" for the faculty-branches where the
// user optionally selected their own profile. We mix the profile's research
// areas + summary into the query so the ranker considers overlap with the
// searcher's own expertise, not just the prompt.
function augmentQuery(base: string, self?: Faculty): string {
  if (!self) return base;
  const bits = [
    ...(self.research_areas ?? []),
    self.title ?? "",
    (self.summary ?? "").slice(0, 400),
  ].filter(Boolean);
  return `${base}\n\n[Searcher's own profile]\n${bits.join(". ")}`;
}

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const { userType, facultySide, facultyId, partners, project } = body;
  if (!project || typeof project !== "string") {
    return NextResponse.json({ error: "missing project" }, { status: 400 });
  }

  const userKey = req.headers.get("x-anthropic-key") || undefined;
  const apiKey = userKey || process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "No Anthropic API key available. Paste one on the AI Match page." },
      { status: 400 },
    );
  }
  const client = new Anthropic({ apiKey });

  const byId = new Map(FACULTY.map((f) => [f.id, f]));
  const self = facultyId ? byId.get(facultyId) : undefined;
  // When specific partners are selected we only search those; empty array / undefined
  // means "all partners".
  const partnerSet = new Set(partners ?? []);
  const includesPartner = (pu: string) =>
    pu !== "NTU" && (partnerSet.size === 0 || partnerSet.has(pu));

  // -------------------------------------------------------------- //
  // Route per-branch to the right pool + prompt shape.
  // -------------------------------------------------------------- //

  if (userType === "faculty" && facultySide === "ntu") {
    // Rank partner-uni faculty for an NTU-based searcher.
    const pool = FACULTY.filter((f) => includesPartner(f.partner_university));
    return singleRank({
      client,
      pool,
      query: augmentQuery(project, self),
      system: `You rank potential Joint-PhD collaborators at NTU's partner universities (outside NTU) for an NTU-based faculty member.
Return strict JSON { "matches": [ { "id", "rationale" } ] }. Return up to 10.
- Only use ids that appear in the directory.
- Rationale (≤ 30 words) must name the specific overlap: shared systems, diseases, organisms, techniques, or methods.
- Prefer stronger specificity over seniority.
- Prefer matches that would plausibly co-supervise an NTU PhD student.
- Output JSON only. No prose, no fences.`,
    });
  }

  if (userType === "faculty" && facultySide === "partner") {
    // Rank NTU faculty for a partner-university faculty member.
    const pool = FACULTY.filter((f) => f.partner_university === "NTU");
    return singleRank({
      client,
      pool,
      query: augmentQuery(project, self),
      system: `You rank potential NTU Joint-PhD collaborators for a faculty member based at a partner university.
Return strict JSON { "matches": [ { "id", "rationale" } ] }. Return up to 10.
- Only use ids that appear in the directory.
- Rationale (≤ 30 words) must name the specific overlap: shared systems, diseases, organisms, techniques, or methods.
- Prefer stronger specificity over seniority.
- Output JSON only.`,
    });
  }

  if (userType === "current") {
    // Current PhD: supervisor is required, returns partner-faculty matches.
    if (!self || self.partner_university !== "NTU") {
      return NextResponse.json(
        { error: "Select your current NTU supervisor first." },
        { status: 400 },
      );
    }
    const pool = FACULTY.filter((f) => includesPartner(f.partner_university));
    const query =
      `${project}\n\n[My NTU supervisor's research]\n${(self.research_areas ?? []).join(", ")}. ${
        self.summary ?? ""
      }`.slice(0, 4000);
    return singleRank({
      client,
      pool,
      query,
      system: `You rank potential Joint-PhD co-supervisors at partner universities for a current NTU PhD student whose main NTU supervisor is fixed.
Return strict JSON { "matches": [ { "id", "rationale" } ] }. Return up to 10.
- The rationale (≤ 30 words) should explain how the partner faculty complements the student's project AND the NTU supervisor's line of work — e.g. a method, model system, or clinical angle the NTU lab lacks.
- Only use ids that appear in the directory.
- Output JSON only.`,
    });
  }

  if (userType === "prospective") {
    // Team-pairing mode. To stop one large partner (like Sorbonne) dominating
    // the shortlist and every team, we shortlist separately *per partner* and
    // send each partner's candidates as its own labeled block. The prompt then
    // requires every team to include one PI from EACH selected partner — so a
    // 3-partner selection produces teams of 1 NTU + 1 Sorbonne + 1 TUM + 1 Turin.
    const ntuPool = FACULTY.filter((f) => f.partner_university === "NTU");
    const selectedPartners = partnerCodes().filter(
      (c) => c !== "NTU" && (partnerSet.size === 0 || partnerSet.has(c)),
    );
    if (selectedPartners.length === 0) {
      return NextResponse.json(
        { error: "Select at least one partner university." },
        { status: 400 },
      );
    }
    // Budget: give each partner ~25 candidates, NTU ~40 — keeps input tokens
    // bounded regardless of how many partners are in play.
    const perPartner = Math.max(15, Math.floor(80 / selectedPartners.length));
    const ntuShort = compact(shortlist(project, ntuPool, 40));
    const partnerBlocks = selectedPartners.map((code) => {
      const pool = FACULTY.filter((f) => f.partner_university === code);
      return { code, records: compact(shortlist(project, pool, perPartner)) };
    });

    const partnerRule =
      selectedPartners.length === 1
        ? `- Each team's partner_ids MUST contain exactly one id from PARTNER_${selectedPartners[0].toUpperCase()}.`
        : `- Each team's partner_ids MUST contain exactly one id from EACH of these partner directories, in this order: ${selectedPartners
            .map((c) => `PARTNER_${c.toUpperCase()}`)
            .join(", ")}. A team is invalid if any of those partners is missing.`;

    const system = `You suggest Joint-PhD supervisor teams for a prospective PhD student.
Each team pairs exactly one NTU faculty (the main supervisor) with one partner-university faculty from EACH selected partner directory (co-supervisors). Teams should combine complementary expertise (e.g. model systems + methods, biology + engineering, wet lab + computational).

Return strict JSON:
{ "matches": [ { "ntu_id": "<NTU id>", "partner_ids": ["<id>", ...], "rationale": "<one sentence, ≤ 50 words>" } ] }

Rules:
- Return 4 to 6 teams.
- Each team's ntu_id MUST come from NTU_DIRECTORY.
${partnerRule}
- Rationale names the complementary overlap across the whole team.
- Prefer NTU faculty diversity across teams (don't re-use the same NTU PI unless they're genuinely the best fit for another team).
- Output JSON only. No prose, no fences.`;

    const directoryText = [
      `NTU_DIRECTORY (JSON):\n${JSON.stringify(ntuShort)}`,
      ...partnerBlocks.map(
        (b) =>
          `\n\nPARTNER_${b.code.toUpperCase()} (JSON):\n${JSON.stringify(b.records)}`,
      ),
    ].join("");
    const projectText = `\n\nPROJECT:\n${project.trim()}`;

    try {
      const resp = await client.messages.create({
        model: MODEL,
        max_tokens: 3000,
        system,
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: directoryText, cache_control: { type: "ephemeral" } },
              { type: "text", text: projectText },
            ],
          },
        ],
      });
      const text = resp.content
        .map((b) => (b.type === "text" ? b.text : ""))
        .join("");
      let parsed: { matches: { ntu_id: string; partner_ids: string[]; rationale: string }[] };
      try {
        parsed = JSON.parse(stripFences(text));
      } catch {
        return NextResponse.json(
          { error: "Model did not return JSON", raw: text },
          { status: 502 },
        );
      }
      // Enforce the per-partner coverage rule server-side too — Claude mostly
      // follows it but dropping incomplete teams guarantees the guarantee.
      const knownIds = new Set(FACULTY.map((f) => f.id));
      const idToPartner = new Map(FACULTY.map((f) => [f.id, f.partner_university]));
      const clean = (parsed.matches ?? [])
        .map((m) => ({
          ntu_id: m.ntu_id,
          partner_ids: (m.partner_ids ?? []).filter((id) => knownIds.has(id)),
          rationale: m.rationale,
        }))
        .filter((m) => {
          if (!knownIds.has(m.ntu_id)) return false;
          if (idToPartner.get(m.ntu_id) !== "NTU") return false;
          const teamPartners = new Set(
            m.partner_ids.map((id) => idToPartner.get(id)).filter(Boolean),
          );
          // Every selected partner uni must be represented on the team.
          return selectedPartners.every((c) => teamPartners.has(c));
        })
        .slice(0, 6);
      return NextResponse.json({ kind: "team", matches: clean });
    } catch (e: any) {
      const msg = e?.error?.message || e?.message || "Upstream error";
      return NextResponse.json({ error: msg }, { status: 502 });
    }
  }

  return NextResponse.json({ error: "unknown userType" }, { status: 400 });
}

// -------------------------------------------------------------- //
// Helpers
// -------------------------------------------------------------- //

async function singleRank(args: {
  client: Anthropic;
  pool: Faculty[];
  query: string;
  system: string;
}) {
  const { client, pool, query, system } = args;
  if (pool.length === 0) {
    return NextResponse.json(
      { error: "No candidates in the selected partner universities." },
      { status: 400 },
    );
  }
  const directory = compact(shortlist(query, pool, SHORTLIST_SIZE));
  const directoryText = `DIRECTORY (JSON):\n${JSON.stringify(directory)}`;
  const projectText = `\n\nPROJECT:\n${query.trim()}`;

  try {
    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: 2000,
      system,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: directoryText, cache_control: { type: "ephemeral" } },
            { type: "text", text: projectText },
          ],
        },
      ],
    });
    const text = resp.content
      .map((b) => (b.type === "text" ? b.text : ""))
      .join("");
    let parsed: { matches: { id: string; rationale: string }[] };
    try {
      parsed = JSON.parse(stripFences(text));
    } catch {
      return NextResponse.json(
        { error: "Model did not return JSON", raw: text },
        { status: 502 },
      );
    }
    const knownIds = new Set(pool.map((f) => f.id));
    parsed.matches = (parsed.matches ?? [])
      .filter((m) => knownIds.has(m.id))
      .slice(0, 10);
    return NextResponse.json({ kind: "single", matches: parsed.matches });
  } catch (e: any) {
    const msg = e?.error?.message || e?.message || "Upstream error";
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
