import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import yaml from "js-yaml";
import { clean } from "./sanitize.js";
import { complete } from "./llm.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function stripFence(text) {
  return String(text ?? "").trim()
    .replace(/^```[a-zA-Z0-9]*\s*/, "")
    .replace(/\s*```$/, "")
    .trim();
}

function parseJson(text) {
  const stripped = stripFence(text);
  try {
    return JSON.parse(stripped);
  } catch {
    const match = stripped.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("review did not return JSON");
    return JSON.parse(match[0]);
  }
}

function normalizeIssues(value) {
  if (!Array.isArray(value)) return [];
  return value.map((issue) => {
    if (typeof issue === "string") return { type: "issue", detail: clean(issue) };
    return {
      type: clean(issue?.type || issue?.category || "issue"),
      detail: clean(issue?.detail || issue?.message || issue?.text || ""),
    };
  }).filter((issue) => issue.detail);
}

function normalizeEdits(value) {
  const edits = value && typeof value === "object" ? value : {};
  const list = (items) => (Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : []);
  return {
    drop: list(edits.drop),
    rephrase: list(edits.rephrase).map((item) => ({ ...item, text: clean(item.text) })).filter((item) => item.text),
    reorder: list(edits.reorder),
  };
}

function promptBody({ draftText, kind, offer, library, styleProfile }) {
  const template = readFileSync(path.join(ROOT, "prompts", "review.md"), "utf8");
  return template
    .replace("{{kind}}", kind)
    .replace("{{draft_text}}", draftText)
    .replace("{{offer}}", JSON.stringify(offer ?? {}, null, 2))
    .replace("{{library}}", yaml.dump(library ?? {}, { lineWidth: 100 }))
    .replace("{{style_profile}}", styleProfile ? yaml.dump(styleProfile, { lineWidth: 100 }) : "");
}

export async function review({ draftText, kind, offer, library, styleProfile, completeFn = complete }) {
  const cleanedDraft = clean(draftText);
  if (!cleanedDraft) return { issues: [], revisedText: "" };

  const system =
    "You are a strict job-application reviewer. Return JSON only. Flag fabrications, " +
    "fixable keyword gaps, language drift, and structure issues. Never invent experience.";
  const reviewRaw = await completeFn(system, promptBody({
    draftText: cleanedDraft,
    kind,
    offer,
    library,
    styleProfile,
  }));
  const reviewResult = parseJson(reviewRaw);
  const issues = normalizeIssues(reviewResult.issues);
  if (kind === "cv") {
    return { issues, edits: normalizeEdits(reviewResult.edits), revisedText: cleanedDraft };
  }
  if (!issues.length) return { issues, revisedText: cleanedDraft };

  const reviseSystem =
    "Revise the draft once using only facts present in the provided library. Do not add new claims, " +
    "new metrics, new employers, or new skills. If a gap cannot be filled from the library, leave it out. " +
    "Return JSON only with a revisedText string.";
  const reviseRaw = await completeFn(reviseSystem, JSON.stringify({
    kind,
    issues,
    offer,
    library,
    styleProfile: styleProfile ?? null,
    draftText: cleanedDraft,
  }, null, 2));
  const reviseResult = parseJson(reviseRaw);
  return { issues, edits: normalizeEdits(reviewResult.edits), revisedText: clean(reviseResult.revisedText || cleanedDraft) };
}

export function logReviewIssues(kind, issues) {
  for (const issue of issues) {
    console.error(`[review:${kind}] ${issue.type}: ${issue.detail}`);
  }
}
