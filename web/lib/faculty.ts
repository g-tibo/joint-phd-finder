import data from "@/public/faculty.json";

export type PartnershipType = "Degree" | "Supervision" | null;

export type Faculty = {
  id: string;
  name: string;
  institution: string;
  partner_university: string;
  partnership_type: PartnershipType;
  department?: string;
  title?: string;
  roles?: string[];
  research_areas?: string[];
  summary?: string;
  email?: string;
  profile_url: string;
  lab_url?: string;
  scholar_url?: string;
  orcid?: string;
  photo_url?: string;
};

// Canonical display names + partnership type for each partner_university code.
// Keep this as the single source of truth so UI labels and filters stay in sync.
export const PARTNER_UNIVERSITIES: {
  code: string;
  name: string;
  partnership_type: PartnershipType;
}[] = [
  { code: "NTU", name: "Nanyang Technological University", partnership_type: null },
  { code: "Sorbonne", name: "Sorbonne University", partnership_type: "Degree" },
  { code: "TUM", name: "Technical University of Munich", partnership_type: "Supervision" },
  { code: "Turin", name: "University of Turin", partnership_type: "Supervision" },
];

export const PARTNER_NAME: Record<string, string> = Object.fromEntries(
  PARTNER_UNIVERSITIES.map((u) => [u.code, u.name]),
);

export const PARTNER_TYPE: Record<string, PartnershipType> = Object.fromEntries(
  PARTNER_UNIVERSITIES.map((u) => [u.code, u.partnership_type]),
);

function lastNameKey(name: string): string {
  if (name.includes(",")) {
    return name.split(",")[0].trim().toLowerCase();
  }
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1].toLowerCase();
}

export const FACULTY: Faculty[] = (data as Faculty[])
  .slice()
  .sort(
    (a, b) =>
      lastNameKey(a.name).localeCompare(lastNameKey(b.name)) ||
      a.name.localeCompare(b.name),
  );

// NTU and each partner university as separate groups — used across Browse + Match
// whenever we need to pair NTU supervisors with partner co-supervisors.
export const NTU_FACULTY: Faculty[] = FACULTY.filter(
  (f) => f.partner_university === "NTU",
);
export const PARTNER_FACULTY: Faculty[] = FACULTY.filter(
  (f) => f.partner_university !== "NTU",
);

export function partnerCodes(): string[] {
  // Only return codes that are actually represented in the current dataset,
  // preserving the canonical order defined in PARTNER_UNIVERSITIES.
  const present = new Set(FACULTY.map((f) => f.partner_university));
  return PARTNER_UNIVERSITIES.map((u) => u.code).filter((c) => present.has(c));
}

export function departments(partnerCode?: string): string[] {
  const pool = partnerCode
    ? FACULTY.filter((f) => f.partner_university === partnerCode)
    : FACULTY;
  return Array.from(
    new Set(pool.map((f) => f.department).filter((x): x is string => !!x)),
  ).sort();
}

export function search(
  query: string,
  filters: { partner?: string; department?: string },
): Faculty[] {
  const q = query.trim().toLowerCase();
  return FACULTY.filter((f) => {
    if (filters.partner && f.partner_university !== filters.partner) return false;
    if (filters.department && f.department !== filters.department) return false;
    if (!q) return true;
    const hay = [
      f.name,
      f.title ?? "",
      f.department ?? "",
      f.institution,
      f.partner_university,
      ...(f.research_areas ?? []),
      ...(f.roles ?? []),
      f.summary ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}
