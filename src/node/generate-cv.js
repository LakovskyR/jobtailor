#!/usr/bin/env node
/**
 * Generate a tailored CV (.docx) from the experience library, ranked against a parsed offer.
 *
 * Usage:
 *   node src/node/generate-cv.js --lang en --offer jobs/offer.json --out output/cv/CV_EN.docx
 *   node src/node/generate-cv.js --lang fr                      (untailored, full library)
 *
 * Single-column, ATS-safe layout (no tables/sidebars — ATS parsers can't read table text) with
 * accent section headings and clear hierarchy. Selects and rephrases from the library, never invents.
 */
import { readFileSync } from "node:fs";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import yaml from "js-yaml";
import { clean } from "./sanitize.js";
import { complete } from "./llm.js";
import { AlignmentType, BorderStyle, Document, Packer, Paragraph, TextRun } from "docx";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const ACCENT = "C2570F";
const RULE = "D9D2C6";
const MUTED = "6F6A60";

// Coerce anything to an array so a malformed library field (string/object where a list is expected)
// never crashes a .map/.join. LLM output isn't guaranteed to match the schema exactly.
const arr = (v) => (Array.isArray(v) ? v : v == null ? [] : [v]);

function parseArgs(argv) {
  const args = { lang: "en", offer: null, out: null };
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, "");
    if (key in args) args[key] = argv[i + 1];
  }
  return args;
}

function loadLibrary() {
  if (process.env.JOBTAILOR_LIBRARY_JSON) return JSON.parse(process.env.JOBTAILOR_LIBRARY_JSON);
  for (const name of ["experience-library.yaml", "experience-library.example.yaml"]) {
    const p = path.join(ROOT, "config", name);
    try {
      return yaml.load(readFileSync(p, "utf8"));
    } catch {
      /* try next */
    }
  }
  throw new Error("No experience library found in config/. Copy the .example.yaml first.");
}

function loadSettings() {
  for (const name of ["settings.yaml", "settings.example.yaml"]) {
    const p = path.join(ROOT, "config", name);
    try {
      return yaml.load(readFileSync(p, "utf8"));
    } catch {
      /* try next */
    }
  }
  return { cv: { achievements_per_role: 3, sections: ["headline", "summary", "experience", "skills", "education", "certifications"] } };
}

function pickLang(value, lang) {
  if (value && typeof value === "object" && !Array.isArray(value)) return clean(value[lang] ?? Object.values(value)[0]);
  return clean(value);
}

function joinParts(parts) {
  return parts.map((p) => clean(p)).filter(Boolean).join(" | ");
}

function certLabel(cert) {
  if (typeof cert === "string") return clean(cert);
  if (cert && typeof cert === "object") return joinParts([cert.name ?? cert.title ?? cert.label, cert.year ?? cert.date]);
  return "";
}

function langLabel(entry) {
  if (typeof entry === "string") return clean(entry);
  if (entry && typeof entry === "object") return joinParts([entry.name, entry.level]);
  return "";
}

function tokenize(value) {
  return new Set(String(value ?? "").toLowerCase().match(/[a-zÀ-ÿ0-9][a-zÀ-ÿ0-9+#/]*/g) ?? []);
}

function overlapScore(text, offerTerms) {
  const tokens = tokenize(text);
  let score = 0;
  for (const term of offerTerms) {
    const termTokens = tokenize(term);
    if (termTokens.size && [...termTokens].every((token) => tokens.has(token))) score += termTokens.size;
  }
  return score;
}

export function rankAchievements(library, offer, lang, settings = loadSettings()) {
  const offerTerms = offer ? [...arr(offer.must_have), ...arr(offer.keywords)] : [];
  const limit = settings.cv?.achievements_per_role ?? 3;
  return arr(library.roles).map((role) => {
    const roleText = [role.company, pickLang(role.title, lang), ...arr(role.tags)].join(" ");
    const achievements = arr(role.achievements)
      .map((achievement, index) => {
        const text = pickLang(achievement.text, lang);
        const tags = arr(achievement.tags).join(" ");
        return {
          ...achievement,
          renderedText: text,
          score: overlapScore(`${roleText} ${text} ${tags}`, offerTerms),
          originalIndex: index,
        };
      })
      .sort((a, b) => b.score - a.score || a.originalIndex - b.originalIndex)
      .slice(0, limit);
    return { ...role, achievements };
  });
}

function sectionHeading(label) {
  return new Paragraph({
    spacing: { before: 220, after: 80 },
    border: { bottom: { color: RULE, size: 6, space: 2, style: BorderStyle.SINGLE } },
    children: [new TextRun({ text: clean(label).toUpperCase(), bold: true, size: 21, color: ACCENT })],
  });
}

function line(text, opts = {}) {
  return new Paragraph({
    alignment: opts.align,
    spacing: { after: opts.after ?? 60, before: opts.before ?? 0 },
    children: [new TextRun({ text: clean(text), size: opts.size ?? 21, bold: opts.bold, italics: opts.italics, color: opts.color })],
  });
}

function labelled(label, value, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 60 },
    children: [
      new TextRun({ text: `${clean(label)}: `, bold: true, size: 20 }),
      new TextRun({ text: clean(value), size: 20 }),
    ],
  });
}

function bullet(text) {
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 60 },
    children: [new TextRun({ text: clean(text), size: 21 })],
  });
}

const LABELS = {
  en: { experience: "Experience", skills: "Skills", technical: "Technical", business: "Business", languages: "Languages", education: "Education", certifications: "Certifications" },
  fr: { experience: "Expérience", skills: "Compétences", technical: "Techniques", business: "Atouts", languages: "Langues", education: "Formation", certifications: "Certifications" },
};

function renderDoc(library, selectedRoles, offer, lang, settings) {
  const sections = settings.cv?.sections ?? ["headline", "summary", "experience", "skills", "education", "certifications"];
  const L = LABELS[lang] || LABELS.en;
  const person = library.person ?? {};
  const children = [];

  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 40 },
    children: [new TextRun({ text: clean(person.name), bold: true, size: 40, color: "1C130C" })],
  }));
  if (sections.includes("headline")) {
    const hl = pickLang(person.headline, lang);
    if (hl) children.push(line(hl, { align: AlignmentType.CENTER, size: 22, color: ACCENT, after: 40 }));
  }
  const contact = [person.location, person.email, person.links?.linkedin].map(clean).filter(Boolean).join("  |  ");
  if (contact) children.push(line(contact, { align: AlignmentType.CENTER, size: 18, color: MUTED, after: 160 }));

  if (sections.includes("experience")) {
    const roleBlocks = selectedRoles.filter((r) => joinParts([pickLang(r.title, lang), r.company]) || arr(r.achievements).some((a) => a.renderedText));
    if (roleBlocks.length) {
      children.push(sectionHeading(L.experience));
      for (const role of roleBlocks) {
        const titleLine = joinParts([pickLang(role.title, lang), role.company]);
        const dates = [role.start, role.end].filter(Boolean).join(" - ");
        if (titleLine) children.push(line(titleLine, { bold: true, size: 22, before: 120, after: 20 }));
        if (dates) children.push(line(dates, { italics: true, size: 18, color: MUTED, after: 60 }));
        for (const ach of arr(role.achievements)) {
          if (ach.renderedText) children.push(bullet(ach.renderedText));
        }
      }
    }
  }

  if (sections.includes("skills")) {
    const tech = arr(library.skills?.technical).map(clean).filter(Boolean);
    const biz = arr(library.skills?.business).map(clean).filter(Boolean);
    if (tech.length || biz.length) {
      children.push(sectionHeading(L.skills));
      if (tech.length) children.push(labelled(L.technical, tech.join(", ")));
      if (biz.length) children.push(labelled(L.business, biz.join(", ")));
    }
  }

  const langs = arr(person.languages).map(langLabel).filter(Boolean);
  if (langs.length) {
    children.push(sectionHeading(L.languages));
    children.push(line(langs.join("  |  "), { size: 20 }));
  }

  if (sections.includes("education")) {
    const edus = arr(library.education).map((e) => joinParts([pickLang(e.degree, lang), e.school, e.year])).filter(Boolean);
    if (edus.length) {
      children.push(sectionHeading(L.education));
      for (const e of edus) children.push(line(e, { after: 60 }));
    }
  }

  if (sections.includes("certifications")) {
    const certs = arr(library.certifications).map(certLabel).filter(Boolean);
    if (certs.length) {
      children.push(sectionHeading(L.certifications));
      for (const c of certs) children.push(line(c, { after: 50 }));
    }
  }

  return new Document({ sections: [{ properties: {}, children }] });
}

async function translateFields(values, lang) {
  const langName = lang === "fr" ? "French" : lang === "en" ? "English" : lang;
  const system =
    `Translate the string values of this JSON object into ${langName}. Return a JSON object with ` +
    `EXACTLY the same keys, each value translated. Keep proper nouns, company names, software/tool ` +
    `names (SQL, Excel, Power BI, ...), acronyms and numbers unchanged. Do not add, remove or invent ` +
    `information. Output JSON only, no commentary, no code fences.`;
  const raw = (await complete(system, JSON.stringify(values))).trim()
    .replace(/^```[a-zA-Z0-9]*\s*/, "")
    .replace(/\s*```$/, "")
    .trim();
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object") throw new Error("translation did not return an object");
  return parsed;
}

// Best-effort: translate the visible CV text into the offer's language (like the cover letter).
// Falls back to the source-language CV if there is no key or the call/parse fails.
async function localizeToLang(library, selected, lang) {
  if (!lang) return [library, selected];
  const values = {};
  const headline = pickLang(library.person?.headline, lang);
  if (headline) values.headline = headline;
  selected.forEach((role, ri) => {
    const title = pickLang(role.title, lang);
    if (title) values[`r${ri}_title`] = title;
    arr(role.achievements).forEach((a, ai) => {
      if (a.renderedText) values[`r${ri}_a${ai}`] = a.renderedText;
    });
  });
  arr(library.skills?.technical).forEach((s, i) => { const c = clean(s); if (c) values[`st${i}`] = c; });
  arr(library.skills?.business).forEach((s, i) => { const c = clean(s); if (c) values[`sb${i}`] = c; });
  arr(library.education).forEach((e, i) => { const d = pickLang(e.degree, lang); if (d) values[`edu${i}`] = d; });
  if (!Object.keys(values).length) return [library, selected];

  const t = await translateFields(values, lang);
  const lib = JSON.parse(JSON.stringify(library));
  const sel = JSON.parse(JSON.stringify(selected));
  if (t.headline) (lib.person ??= {}).headline = t.headline;
  sel.forEach((role, ri) => {
    if (t[`r${ri}_title`]) role.title = t[`r${ri}_title`];
    arr(role.achievements).forEach((a, ai) => {
      if (t[`r${ri}_a${ai}`]) a.renderedText = t[`r${ri}_a${ai}`];
    });
  });
  if (lib.skills?.technical) lib.skills.technical = arr(lib.skills.technical).map((s, i) => t[`st${i}`] ?? s);
  if (lib.skills?.business) lib.skills.business = arr(lib.skills.business).map((s, i) => t[`sb${i}`] ?? s);
  if (Array.isArray(lib.education)) lib.education = lib.education.map((e, i) => (t[`edu${i}`] ? { ...e, degree: t[`edu${i}`] } : e));
  return [lib, sel];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const library = loadLibrary();
  const settings = loadSettings();
  const offer = args.offer ? JSON.parse(readFileSync(path.resolve(args.offer), "utf8")) : null;
  const selected = rankAchievements(library, offer, args.lang, settings);
  let lib = library;
  let sel = selected;
  try {
    [lib, sel] = await localizeToLang(library, selected, args.lang);
  } catch (err) {
    console.error(`[warn] CV translation skipped (${err.message}); keeping source language.`);
  }
  const out = args.out ?? path.join(ROOT, settings.output?.cv_dir ?? "output/cv", `CV_${args.lang.toUpperCase()}.docx`);
  mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  const buffer = await Packer.toBuffer(renderDoc(lib, sel, offer, args.lang, settings));
  writeFileSync(path.resolve(out), buffer);
  console.error(`Wrote ${out}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(err.message);
    process.exit(1);
  });
}
