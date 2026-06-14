import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src" / "python"))

import parse_offer  # noqa: E402


def test_extract_fields_from_sample_offer_text():
    text = pathlib.Path("tests/fixtures/sample-offer.txt").read_text(encoding="utf-8")
    result = parse_offer.extract_fields(text)
    assert result["title"] == "Senior Data Analyst"
    assert result["company"] == "Globex"
    assert result["language"] == "en"
    assert {"SQL", "Python", "Power BI"} <= set(result["must_have"])
    assert "dbt" in result["nice_to_have"]
    assert "segmentation" in result["keywords"]
    assert result["raw_text"] == text


def test_extract_text_from_linkedin_like_html_repairs_text_and_title():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Globex hiring Senior Data Analyst | LinkedIn">
        <meta property="og:description" content="Globex is hiring a Senior Data Analyst with SQL.">
      </head>
      <body>
        <section class="show-more-less-html__markup">
          Required: SQL, Python, Power BI. Nice to have: dbt. You will analyze segmentation.
          We value candidates who donÃ¢â‚¬â„¢t ignore dashboards.
        </section>
      </body>
    </html>
    """
    fetched = parse_offer.extract_text_from_html(html)
    title, company = parse_offer.parse_title_company(fetched.title)

    assert title == "Senior Data Analyst"
    assert company == "Globex"
    assert "don't ignore dashboards" in fetched.text
    assert "Globex is hiring" in fetched.meta_description


def test_parse_url_returns_paste_text_fallback(monkeypatch):
    def fail(_url):
        return parse_offer.FetchResult(text="", error="basic: blocked")

    monkeypatch.setattr(parse_offer, "fetch_offer", fail)

    result = parse_offer.parse_url("https://www.linkedin.com/jobs/view/123")

    assert result["read_error"] == "basic: blocked"
    assert "Paste the description text instead" in result["fallback_message"]
    assert result["raw_text"] == ""
