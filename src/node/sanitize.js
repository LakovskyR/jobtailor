const PUNCTUATION = new Map([
  ["\u2014", " - "],
  ["\u2013", " - "],
  ["\u2018", "'"],
  ["\u2019", "'"],
  ["\u201A", "'"],
  ["\u201C", '"'],
  ["\u201D", '"'],
  ["\u201E", '"'],
  ["\u2026", "..."],
]);

export function clean(text) {
  let value = String(text ?? "");
  value = value.replace(/[\u200B-\u200D\uFEFF\u00AD\u2060]/g, "");
  value = value.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, "");
  value = value.replace(/[\u2013\u2014\u2018\u2019\u201A\u201C\u201D\u201E\u2026]/g, (match) => PUNCTUATION.get(match) ?? "");
  value = value.replace(/[ \t\f\v]+/g, " ");
  value = value.replace(/ *\n */g, "\n");
  value = value.replace(/\n{3,}/g, "\n\n");
  return value.trim();
}
