import subprocess
import textwrap


def test_cover_letter_review_flags_and_revises_with_stubbed_llm():
    script = textwrap.dedent(
        r"""
        import assert from "node:assert/strict";
        import { review } from "./src/node/review.js";

        const calls = [];
        const result = await review({
          draftText: "Invented Kubernetes migration. Strong SQL delivery.",
          kind: "cover_letter",
          offer: { language: "en", must_have: ["SQL"], keywords: ["Python"] },
          library: { skills: { technical: ["SQL"] }, roles: [] },
          completeFn: async (system, user) => {
            calls.push({ system, user });
            if (calls.length === 1) {
              return JSON.stringify({
                issues: [
                  { type: "fabrication", detail: "Kubernetes is not grounded in the library." },
                  { type: "coverage_gap", detail: "Python gap cannot be filled from the library." }
                ]
              });
            }
            return JSON.stringify({ revisedText: "Strong SQL delivery." });
          },
        });

        assert.equal(calls.length, 2);
        assert.equal(result.issues.length, 2);
        assert.equal(result.revisedText, "Strong SQL delivery.");
        assert(!result.revisedText.includes("Kubernetes"));
        """
    )
    subprocess.run(["node", "--input-type=module", "-e", script], check=True)


def test_cv_review_returns_structured_edits_without_revise_call():
    script = textwrap.dedent(
        r"""
        import assert from "node:assert/strict";
        import { review } from "./src/node/review.js";

        let calls = 0;
        const result = await review({
          draftText: "Old achievement text.",
          kind: "cv",
          offer: { language: "en", must_have: ["SQL"], keywords: [] },
          library: { roles: [{ company: "Acme", achievements: [{ text: { en: "Old achievement text." } }] }] },
          completeFn: async () => {
            calls += 1;
            return JSON.stringify({
              issues: [{ type: "coverage_gap", detail: "Use the existing SQL achievement." }],
              edits: { rephrase: [{ role: "Acme", achievementId: 0, text: "Improved SQL reporting accuracy." }] }
            });
          },
        });

        assert.equal(calls, 1);
        assert.equal(result.issues.length, 1);
        assert.equal(result.edits.rephrase[0].text, "Improved SQL reporting accuracy.");
        """
    )
    subprocess.run(["node", "--input-type=module", "-e", script], check=True)


def test_cv_review_edits_apply_only_to_existing_items():
    script = textwrap.dedent(
        r"""
        import assert from "node:assert/strict";
        import { applyCvReviewEdits } from "./src/node/generate-cv.js";

        const selected = [{
          company: "Acme",
          title: { en: "Analyst" },
          achievements: [
            { id: "a1", renderedText: "Built SQL dashboards." },
            { id: "a2", renderedText: "Automated reporting." }
          ]
        }];
        const edited = applyCvReviewEdits(selected, {
          rephrase: [
            { role: "Acme", achievementId: "a1", text: "Built SQL dashboards for 200 users." },
            { role: "Invented Corp", achievementId: "new", text: "Invented a new achievement." }
          ],
          drop: [{ role: "Acme", achievementId: "missing" }]
        }, "en");

        assert.equal(edited[0].achievements.length, 2);
        assert.equal(edited[0].achievements[0].renderedText, "Built SQL dashboards for 200 users.");
        assert.equal(edited[0].achievements[1].renderedText, "Automated reporting.");
        assert.equal(selected[0].achievements[0].renderedText, "Built SQL dashboards.");
        """
    )
    subprocess.run(["node", "--input-type=module", "-e", script], check=True)
