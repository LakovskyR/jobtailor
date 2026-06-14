import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function loadEnv() {
  const envPath = path.join(ROOT, ".env");
  if (!existsSync(envPath)) return;
  for (const raw of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    if (process.env[key.trim()] === undefined) {
      process.env[key.trim()] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
    }
  }
}

export async function complete(system, user) {
  loadEnv();
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is not set; copy .env.example to .env and fill it in.");
  }
  // OpenAI by default; point OPENAI_BASE_URL at any OpenAI-compatible endpoint (e.g. Groq) to
  // run without an OpenAI key. See .env.example.
  const baseUrl = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");

  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      // Browser-like UA: some OpenAI-compatible hosts (e.g. Groq behind Cloudflare) 403 the default agent.
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-4o-mini",
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      temperature: 0.2,
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenAI request failed (${response.status}): ${await response.text()}`);
  }
  const data = await response.json();
  return data.choices[0].message.content.trim();
}
