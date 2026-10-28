// Links shown on the landing page. Placeholders until the author fills them in.
export const SITE = {
  author: "Ruklay Pousajja",
  role: "Senior Data & AI Engineer",
  cvUrl: "#cv-placeholder",
  linkedinUrl: "#linkedin-placeholder",
  githubUrl: "https://github.com/ruklay-mt/governed-ai-portfolio",
  repoUrl: "https://github.com/ruklay-mt/governed-ai-portfolio",
} as const;

/** Link to an eval case file on GitHub (presets link to the exact case CI runs). */
export function evalCaseUrl(evalFile: string, caseId: string): string {
  return `${SITE.repoUrl}/blob/main/${evalFile}#:~:text=${encodeURIComponent(`id: ${caseId}`)}`;
}
