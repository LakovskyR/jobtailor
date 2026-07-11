#!/usr/bin/env node
/**
 * Generate a tailored cover letter (.docx) from the experience library and parsed offer.
 * Renders a proper letter header (sender, date, company/role) above the body.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import yaml from "js-yaml";
import { Document, Packer, Paragraph, TextRun } from "docx";
import { clean } from "./sanitize.js";
import { complete } from "./llm.js";
import { rankAchievements } from "./generate-cv.js";
import { logReviewIssues, review } from "./review.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function parseArgs(argv) {
  const args = { offer: null, out: null, lang: null, review: true };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--no-review") {
      args.review = false;
      continue;
    }
    const key = argv[i].replace(/^--/, "");
    if (key in args) {
      args[key] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function loadYamlConfig(baseName, { example = true } = {}) {
  if (baseName === "experience-library" && process.env.JOBTAILOR_LIBRARY_JSON) {
    return JSON.parse(process.env.JOBTAILOR_LIBRARY_JSON);
  }
  if (baseName === "style-profile" && process.env.JOBTAILOR_STYLE_JSON) {
    return JSON.parse(process.env.JOBTAILOR_STYLE_JSON);
  }
  const names = example ? [`${baseName}.yaml`, `${baseName}.example.yaml`] : [`${baseName}.yaml`];
  for (const name of names) {
    const p = path.join(ROOT, "config", name);
    if (existsSync(p)) return yaml.load(readFileSync(p, "utf8"));
  }
  return null;
}

function pickLang(value, lang) {
  if (value && typeof value === "object" && !Array.isArray(value)) return clean(value[lang] ?? Object.values(value)[0]);
  return clean(value);
}

function flattenProofs(library, offer, lang, settings) {
  return rankAchievements(library, offer, lang, settings)
    .flatMap((role) => (role.achievements ?? []).map((achievement) => ({
      role: pickLang(role.title, lang),
      company: role.company,
      text: clean(achievement.renderedText),
      score: achievement.score,
    })))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
}

function styleDefault(library) {
  return {
    register: "formal",
    person: "first",
    tone: ["professional", "concise"],
    sentence_length: "medium",
    paragraph_count: 4,
    salutation: "Dear Hiring Manager,",
    sign_off: "Kind regards,",
    signature: library.person?.name ?? "",
    avoid: [],
    signature_phrases: [],
  };
}

function lowerFirst(text) {
  if (!text) return "";
  return text.charAt(0).toLowerCase() + text.slice(1);
}

function composeDeterministic(library, offer, style, lang, settings) {
  const proofs = flattenProofs(library, offer, lang, settings);
  const salutation = style.salutation || "Dear Hiring Manager,";
  const signOff = style.sign_off || "Kind regards,";
  const signature = style.signature || library.person?.name || "";
  const company = offer.company || "your team";
  const title = offer.title || "the role";
  const terms = [...(offer.must_have ?? []), ...(offer.keywords ?? [])].slice(0, 5).join(", ");
  const paragraphs = [
    salutation,
    `What draws me to ${company} is the chance to bring ${pickLang(library.person?.headline, lang)} to ${title}${terms ? `, with direct relevance to ${terms}` : ""}.`,
    ...proofs.slice(0, 3).map((proof) => `At ${proof.company}, as ${proof.role}, I ${lowerFirst(proof.text)} This is the kind of grounded, measurable work I would bring to ${company}.`),
    `I would welcome the opportunity to discuss how this experience can support ${company}'s priorities for ${title}.\n\n${signOff}\n${signature}`.trim(),
  ];
  return paragraphs.filter(Boolean).join("\n\n");
}

async function composeWithLlm(library, offer, style) {
  const prompt = readFileSync(path.join(ROOT, "prompts", "cover-letter.md"), "utf8")
    .replace("{{library}}", yaml.dump(library, { lineWidth: 100 }))
    .replace("{{offer}}", JSON.stringify(offer, null, 2))
    .replace("{{style_profile}}", style ? yaml.dump(style, { lineWidth: 100 }) : "");
  const system = prompt.split("## System", 2)[1].split("## Input", 1)[0].trim();
  return complete(system, prompt);
}

function headerParagraphs(library, offer, lang) {
  const person = library.person ?? {};
  const out = [];
  const name = clean(person.name);
  if (name) out.push(new Paragraph({ children: [new TextRun({ text: name, bold: true, size: 28 })] }));
  const contact = [person.location, person.email, person.links?.linkedin].filter(Boolean).map(clean).join("   ");
  if (contact) out.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: contact, size: 18 })] }));
  let dateStr = "";
  try {
    dateStr = new Date().toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    dateStr = "";
  }
  if (dateStr) out.push(new Paragraph({ children: [new TextRun({ text: dateStr, size: 20 })] }));
  const company = clean(offer.company);
  const role = clean(offer.title);
  if (company) out.push(new Paragraph({ spacing: { before: 120 }, children: [new TextRun({ text: company, bold: true, size: 22 })] }));
  if (role) out.push(new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: role, size: 20 })] }));
  return out;
}

function renderLetter(text, library, offer, lang) {
  const body = text.split(/\n{2,}/).map((paragraph) => new Paragraph({
    spacing: { after: 180 },
    children: paragraph.split(/\n/).flatMap((line, index) => [
      ...(index ? [new TextRun({ break: 1 })] : []),
      new TextRun({ text: line, size: 22 }),
    ]),
  }));
  return new Document({
    sections: [{ properties: {}, children: [...headerParagraphs(library, offer, lang), ...body] }],
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.offer) throw new Error("Pass --offer jobs/offer.json");
  const library = loadYamlConfig("experience-library");
  const settings = loadYamlConfig("settings") ?? {};
  const style = loadYamlConfig("style-profile", { example: false }) ?? styleDefault(library);
  const offer = JSON.parse(readFileSync(path.resolve(args.offer), "utf8"));
  const lang = args.lang || offer.language || "en";
  let letter;
  try {
    letter = await composeWithLlm(library, offer, style);
  } catch (err) {
    console.error(`[warn] ${err.message} Falling back to deterministic letter.`);
    letter = composeDeterministic(library, offer, style, lang, settings);
  }
  for (const avoid of style.avoid ?? []) {
    if (avoid) letter = letter.replaceAll(avoid, "");
  }
  const reviewEnabled = args.review && settings.generation?.review !== false;
  if (reviewEnabled) {
    try {
      const result = await review({ draftText: letter, kind: "cover_letter", offer, library, styleProfile: style });
      logReviewIssues("cover_letter", result.issues);
      letter = result.revisedText;
    } catch (err) {
      console.error(`[warn] review skipped (${err.message}).`);
    }
  }
  letter = clean(letter);
  const out = args.out ?? path.join(ROOT, settings.output?.cover_letter_dir ?? "output/cover-letters", `cover-letter-${lang}.docx`);
  mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  writeFileSync(path.resolve(out), await Packer.toBuffer(renderLetter(letter.trim(), library, offer, lang)));
  console.error(`Wrote ${out}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
