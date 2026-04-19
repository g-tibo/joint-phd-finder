import { FACULTY, PARTNER_UNIVERSITIES, PARTNER_NAME } from "@/lib/faculty";

function coverageSentence(): string {
  const counts: Record<string, number> = {};
  for (const f of FACULTY) {
    counts[f.partner_university] = (counts[f.partner_university] ?? 0) + 1;
  }
  const parts = PARTNER_UNIVERSITIES.filter((u) => counts[u.code]).map(
    (u) =>
      `${PARTNER_NAME[u.code]} (${counts[u.code]}${
        u.partnership_type ? `, Joint PhD ${u.partnership_type}` : ""
      })`,
  );
  if (parts.length <= 1) return parts.join("");
  if (parts.length === 2) return parts.join(" and ");
  return parts.slice(0, -1).join(", ") + ", and " + parts[parts.length - 1];
}

export default function AboutPage() {
  const coverage = coverageSentence();

  return (
    <article className="max-w-none">
      <h1 className="text-3xl font-semibold tracking-tight">About</h1>

      <p className="mt-4 text-black/75 dark:text-white/75">
        <strong>NTU Joint PhD Finder</strong> is a directory of faculty at NTU
        and its Joint PhD partner universities, designed to help both faculty
        and prospective students identify supervisors or co-supervisors for a
        Joint PhD programme. See the NTU Graduate College page on{" "}
        <a
          className="text-accent hover:underline"
          href="https://www.ntu.edu.sg/graduate-college/admissions/programme/Joint-PhD-Programmes"
          target="_blank"
          rel="noopener noreferrer"
        >
          Joint PhD Programmes
        </a>{" "}
        for the official programme list and terms.
      </p>

      <p className="mt-4 text-black/75 dark:text-white/75">
        The directory currently covers {coverage}. For the partner universities
        this first release focuses on <strong>biology</strong> faculty only, as
        a template. NTU coverage spans the schools already indexed in the{" "}
        <a
          className="text-accent hover:underline"
          href="https://sg-collab-finder.vercel.app/"
          target="_blank"
          rel="noopener noreferrer"
        >
          SG Collab Finder
        </a>{" "}
        project, filtered to NTU.
      </p>

      <h2 className="mt-8 text-xl font-semibold">Two flavours of Joint PhD</h2>
      <ul className="mt-2 list-disc pl-6 text-black/75 dark:text-white/75 space-y-1">
        <li>
          <strong>Joint PhD Degree</strong> — a single jointly-awarded degree
          from both universities. Currently: Sorbonne University.
        </li>
        <li>
          <strong>Joint PhD Supervision</strong> — each institution awards its
          own degree, but supervision and training are shared. Currently:
          Technical University of Munich, University of Turin.
        </li>
      </ul>

      <h2 className="mt-8 text-xl font-semibold">How AI Match works</h2>
      <p className="text-black/75 dark:text-white/75">
        Tell the site whether you are a faculty member, a prospective PhD
        student, or a current PhD student. The form adapts: faculty get
        partner-side matches (or NTU-side if they&rsquo;re abroad); prospective
        students get <em>supervisor team</em> suggestions pairing an NTU
        faculty with one or more partner faculty; current students pick their
        NTU supervisor and get complementary partner-side co-supervisor
        suggestions. Your description and the directory are sent to
        Anthropic&rsquo;s Claude API; nothing is stored here.
      </p>

      <h2 className="mt-8 text-xl font-semibold">Privacy</h2>
      <p className="text-black/75 dark:text-white/75">
        All profile content is aggregated from public institutional web pages.
        No user accounts, no tracking, no analytics. Match queries are sent to
        Anthropic&rsquo;s API only for ranking and are not retained by this
        site. Profiles are a snapshot and may be out of date — each card
        links back to the canonical institutional page.
      </p>

      <h2 className="mt-8 text-xl font-semibold">Corrections and removal</h2>
      <p className="text-black/75 dark:text-white/75">
        If you&rsquo;re listed here and would like your entry corrected or
        removed, email{" "}
        <a className="text-accent hover:underline" href="mailto:thibault@ntu.edu.sg">
          thibault@ntu.edu.sg
        </a>
        . Suggestions for additional partner universities and departments are
        welcome.
      </p>

      <h2 className="mt-8 text-xl font-semibold">Colophon</h2>
      <p className="text-black/75 dark:text-white/75">
        Created and maintained by{" "}
        <a
          className="text-accent hover:underline"
          href="https://www.thibaultlab.com/biography"
          target="_blank"
          rel="noopener noreferrer"
        >
          Guillaume Thibault
        </a>{" "}
        (School of Biological Sciences, Nanyang Technological University).
        Adapted from{" "}
        <a
          className="text-accent hover:underline"
          href="https://github.com/g-tibo/sg-collab-finder"
          target="_blank"
          rel="noopener noreferrer"
        >
          SG Collab Finder
        </a>
        . Built with Next.js, Tailwind, and the Anthropic SDK.
      </p>
    </article>
  );
}
