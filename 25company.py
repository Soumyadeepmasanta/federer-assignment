from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st


APP_TITLE = "Federer Company Research Tracker"
DEFAULT_TARGET_CSV = Path(__file__).with_name("federer_target_companies.csv")

CITY_OPTIONS = [
    "Hyderabad",
    "Pune",
    "Ahmedabad",
    "Chennai",
    "Coimbatore",
    "Vadodara",
    "Bengaluru",
    "Indore",
    "Surat",
    "Ludhiana",
    "Kolhapur",
]

SEGMENT_OPTIONS = [
    "Specialty biotech",
    "Specialty diagnostics & life-science tools",
    "Custom synthesis & specialty chemicals",
    "Performance chemicals",
    "Complex APIs & regulated pharma",
    "Medical devices",
    "Hybrid seeds & specialty agri-inputs",
    "Specialty food & nutraceutical ingredients",
    "Industrial sensors & instrumentation (ISI)",
    "Animal health & veterinary biologics",
    "Technical textiles & specialty yarns",
    "Precision auto components & engineering (PACE)",
    "Specialty food processing",
    "Designer / artisanal manufacturing",
]

DISQUALIFIERS = [
    "Trader / distributor / importer",
    "Service company without proprietary specialized service",
    "Generic pharma / bulk API / branded generics",
    "Subsidiary of a large group",
    "Recently acquired by a larger group",
    "PE / VC controlled",
    "Revenue above Rs.500Cr",
    "No real website",
    "No visible activity in last 2 years",
    "Outside accessible India operations",
]

GROWTH_SIGNALS = [
    "Hiring: 5+ open roles in last 6 months",
    "Facility: plant / capacity expansion in last 18 months",
    "Certifications: approval / certification in last 2 years",
    "Website: current site or active news updates",
    "Financial: revenue growth or new export markets",
]

SCORE_RULES = {
    "Differentiated": {
        "code": "C3",
        "weight": 20,
        "weak": "Commodity product, no visible IP or capability moat",
        "moderate": "Some technical depth but limited proof",
        "strong": "Patents, DSIR, regulatory approvals, proprietary products, specialized equipment, or market-shaping capability",
    },
    "Decision-maker quality": {
        "code": "C4",
        "weight": 15,
        "weak": "Non-technical promoter, no systems thinking evidence",
        "moderate": "Gen-2 with formal education or some structured operations evidence",
        "strong": "Science-founder, elite engineering pedigree, or operator who built ERP/costing/formal planning infrastructure",
    },
    "Growing sector": {
        "code": "C5",
        "weight": 15,
        "weak": "Declining or stagnant sector",
        "moderate": "Stable sector without a specific tailwind",
        "strong": "PLI, Make-in-India, China+1, export, or government-support tailwinds",
    },
    "Growth signals": {
        "code": "C6",
        "weight": 15,
        "weak": "No visible activity in 2 years",
        "moderate": "One verified signal",
        "strong": "Two or more verified signals",
    },
    "Systems maturity": {
        "code": "C7",
        "weight": 20,
        "weak": "No ERP, digital systems, or structured process evidence",
        "moderate": "Some evidence such as IT roles or software mentions",
        "strong": "ERP/SAP, MIS, dashboards, structured costing, or digital infrastructure clearly in use",
    },
    "Leadership succession": {
        "code": "C8",
        "weight": 15,
        "weak": "Solo founder, no gen-2, no professional managers",
        "moderate": "Gen-2 exists or one professional senior hire",
        "strong": "Operational gen-2, multiple professional managers, independent directors, or distinct senior portfolios",
    },
}

EXPORT_COLUMNS = [
    "company",
    "website",
    "city",
    "segment",
    "basket",
    "what_they_make",
    "revenue_estimate",
    "decision_maker",
    "e1_producer",
    "e2_accessible",
    "growth_signal_count",
    "total_score",
    "band",
    "verdict",
    "personalization_hook",
    "source_links",
    "c3_score",
    "c4_score",
    "c5_score",
    "c6_score",
    "c7_score",
    "c8_score",
    "notes",
]

PRODUCER_KEYWORDS = [
    "manufacture",
    "manufacturer",
    "manufacturing",
    "plant",
    "facility",
    "factory",
    "works",
    "machining",
    "cnc",
    "vmc",
    "die casting",
    "forging",
    "assembly",
    "tooling",
    "sensor",
    "instrument",
    "calibrator",
]

TRADER_KEYWORDS = [
    "trader",
    "distributor",
    "reseller",
    "dealer",
    "importer",
    "wholesaler",
    "authorized distributor",
]

PACE_KEYWORDS = [
    "auto component",
    "automotive",
    "precision machined",
    "cnc",
    "vmc",
    "gear",
    "shaft",
    "forging",
    "die casting",
    "sheet metal",
    "tooling",
    "transmission",
    "iatf",
]

ISI_KEYWORDS = [
    "sensor",
    "instrument",
    "instrumentation",
    "transmitter",
    "controller",
    "calibrator",
    "analyzer",
    "flow meter",
    "pressure",
    "temperature",
    "process control",
    "data logger",
]

DIFFERENTIATION_KEYWORDS = [
    "patent",
    "proprietary",
    "r&d",
    "research and development",
    "as9100",
    "iatf",
    "iso 13485",
    "iso 9001",
    "5-axis",
    "scada",
    "cmm",
    "drdo",
    "oem",
    "export",
    "custom",
]

DECISION_MAKER_KEYWORDS = [
    "founder",
    "managing director",
    "md",
    "phd",
    "iit",
    "engineer",
    "director",
    "promoter",
    "experience",
    "leadership",
]

SECTOR_TAILWIND_KEYWORDS = [
    "ev",
    "electric vehicle",
    "aerospace",
    "defence",
    "defense",
    "export",
    "china+1",
    "make in india",
    "automation",
    "industry 4.0",
    "oem",
]

GROWTH_KEYWORDS = [
    "expansion",
    "new plant",
    "new facility",
    "capacity",
    "hiring",
    "career",
    "careers",
    "export",
    "new product",
    "certified",
    "2025",
    "2026",
]

SYSTEMS_KEYWORDS = [
    "erp",
    "sap",
    "mis",
    "dashboard",
    "scada",
    "iso",
    "iatf",
    "as9100",
    "quality management",
    "cmm",
    "traceability",
    "gamp",
    "calibration",
]

SUCCESSION_KEYWORDS = [
    "second generation",
    "gen-2",
    "son",
    "daughter",
    "professional management",
    "ceo",
    "coo",
    "cfo",
    "management team",
    "board",
    "independent director",
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)

    def text(self) -> str:
        return " ".join(self.parts)


def page_setup() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; }
        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
        }
        .status-pass {
            color: #166534;
            font-weight: 700;
        }
        .status-fail {
            color: #991b1b;
            font-weight: 700;
        }
        .small-note {
            color: #475569;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def blank_company() -> dict[str, object]:
    return {
        "company": "",
        "website": "",
        "city": "Pune",
        "segment": "Precision auto components & engineering (PACE)",
        "basket": "A",
        "what_they_make": "",
        "revenue_estimate": "",
        "decision_maker": "",
        "e1_producer": True,
        "e2_accessible": True,
        "growth_signal_count": 0,
        "total_score": 0,
        "band": "D - Not ICP",
        "verdict": "",
        "personalization_hook": "",
        "source_links": "",
        "c3_score": 0,
        "c4_score": 0,
        "c5_score": 0,
        "c6_score": 0,
        "c7_score": 0,
        "c8_score": 0,
        "notes": "",
    }


def blank_reject() -> dict[str, object]:
    return {
        "company": "",
        "website": "",
        "city": "Pune",
        "segment": "Precision auto components & engineering (PACE)",
        "reason": DISQUALIFIERS[0],
        "evidence": "",
        "source_links": "",
        "date_checked": str(date.today()),
    }


def seed_state() -> None:
    if "companies" not in st.session_state:
        st.session_state.companies = []
    csv_version = DEFAULT_TARGET_CSV.stat().st_mtime if DEFAULT_TARGET_CSV.exists() else None
    if DEFAULT_TARGET_CSV.exists() and (
        not st.session_state.companies
        or st.session_state.get("loaded_default_csv_version") != csv_version
    ):
        st.session_state.companies = pd.read_csv(DEFAULT_TARGET_CSV).to_dict("records")
        st.session_state.loaded_default_csv_version = csv_version
    st.session_state.setdefault("rejects", [])
    st.session_state.setdefault("target_city", "Pune")
    st.session_state.setdefault(
        "target_segments",
        [
            "Precision auto components & engineering (PACE)",
            "Industrial sensors & instrumentation (ISI)",
        ],
    )
    st.session_state.setdefault("researcher", "")


def criterion_score(label: str, key_prefix: str) -> tuple[int, str]:
    rule = SCORE_RULES[label]
    option = st.radio(
        f"{rule['code']} {label} ({rule['weight']} pts)",
        ["Weak", "Moderate", "Strong"],
        horizontal=True,
        key=f"{key_prefix}_{rule['code']}_level",
    )
    if option == "Weak":
        score = 0
        help_text = rule["weak"]
    elif option == "Moderate":
        score = rule["weight"] // 2
        help_text = rule["moderate"]
    else:
        score = rule["weight"]
        help_text = rule["strong"]
    st.caption(help_text)
    return score, option


def score_band(total: int) -> str:
    if total >= 80:
        return "A - Strong Federer"
    if total >= 60:
        return "B - Probable Federer"
    if total >= 40:
        return "C - Borderline"
    return "D - Not ICP"


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url:
        return ""
    if not raw_url.startswith(("http://", "https://")):
        return f"https://{raw_url}"
    return raw_url


def fetch_website_text(raw_url: str) -> tuple[str, str]:
    url = normalize_url(raw_url)
    if not url:
        return "", "No website link provided."
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 Federer research checker"},
            timeout=12,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return "", f"Could not fetch website: {exc}"

    parser = TextExtractor()
    parser.feed(response.text)
    text = parser.text()
    if not text:
        return "", "Website loaded, but no readable text was found."
    return text[:30000], f"Fetched {len(text):,} text characters from {urlparse(url).netloc}."


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword in lowered]


def score_from_hits(hits: list[str], weight: int, moderate_count: int = 1, strong_count: int = 3) -> int:
    if len(hits) >= strong_count:
        return weight
    if len(hits) >= moderate_count:
        return weight // 2
    return 0


def find_existing_company(company: str, website: str) -> dict[str, object] | None:
    df = dataframe_from_state(st.session_state.get("companies", []), EXPORT_COLUMNS)
    if df.empty:
        return None

    company_key = company.strip().lower()
    website_key = normalize_url(website).replace("https://", "").replace("http://", "").strip("/").lower()
    for row in df.to_dict("records"):
        row_company = str(row.get("company", "")).lower()
        row_website = str(row.get("website", "")).replace("https://", "").replace("http://", "").strip("/").lower()
        company_match = company_key and (company_key in row_company or row_company in company_key)
        website_match = website_key and (website_key in row_website or row_website in website_key)
        if company_match or website_match:
            return row
    return None


def infer_segment(text: str) -> str:
    pace_hits = keyword_hits(text, PACE_KEYWORDS)
    isi_hits = keyword_hits(text, ISI_KEYWORDS)
    if len(pace_hits) >= len(isi_hits) and pace_hits:
        return "Precision auto components & engineering (PACE)"
    if isi_hits:
        return "Industrial sensors & instrumentation (ISI)"
    return st.session_state.target_segments[0] if st.session_state.target_segments else SEGMENT_OPTIONS[0]


def build_analysis(
    company: str,
    website: str,
    city: str,
    pasted_evidence: str,
    fetch_site: bool,
) -> dict[str, object]:
    existing = find_existing_company(company, website)
    website_text = ""
    fetch_status = "Website fetch skipped."
    if fetch_site and website:
        website_text, fetch_status = fetch_website_text(website)

    text_parts = [company, website_text, pasted_evidence]
    if existing:
        text_parts.extend(str(existing.get(col, "")) for col in EXPORT_COLUMNS)
    evidence_text = " ".join(text_parts)
    lowered = evidence_text.lower()

    producer_hits = keyword_hits(evidence_text, PRODUCER_KEYWORDS)
    trader_hits = keyword_hits(evidence_text, TRADER_KEYWORDS)
    city_hits = keyword_hits(evidence_text, [city.lower(), "india", "pune", "chakan", "bhosari", "pimpri", "talegaon"])

    e1_pass = bool(producer_hits) and len(trader_hits) < 2
    e2_pass = bool(city_hits)
    if existing:
        e1_pass = str(existing.get("e1_producer", "True")).lower() == "true"
        e2_pass = str(existing.get("e2_accessible", "True")).lower() == "true"

    disqualifiers: list[str] = []
    if trader_hits and not producer_hits:
        disqualifiers.append("Looks like a trader/distributor, not a producer.")
    if any(word in lowered for word in ["subsidiary", "division of", "group company of"]):
        disqualifiers.append("Possible large-group subsidiary. Verify promoter control.")
    if any(word in lowered for word in ["private equity", "pe-backed", "vc-backed", "venture capital"]):
        disqualifiers.append("Possible PE/VC control. Verify ownership.")
    if any(word in lowered for word in ["generic pharma", "bulk api", "branded generic"]):
        disqualifiers.append("Possible generic pharma/bulk API profile.")
    if any(word in lowered for word in ["revenue above rs.500cr", "above rs.500cr", "above 500cr"]):
        disqualifiers.append("Revenue may exceed Rs.500Cr.")
    if website and not website_text and fetch_site and not existing:
        disqualifiers.append("Website could not be read; needs manual source verification.")

    diff_hits = keyword_hits(evidence_text, DIFFERENTIATION_KEYWORDS)
    decision_hits = keyword_hits(evidence_text, DECISION_MAKER_KEYWORDS)
    sector_hits = keyword_hits(evidence_text, SECTOR_TAILWIND_KEYWORDS)
    growth_hits = keyword_hits(evidence_text, GROWTH_KEYWORDS)
    systems_hits = keyword_hits(evidence_text, SYSTEMS_KEYWORDS)
    succession_hits = keyword_hits(evidence_text, SUCCESSION_KEYWORDS)

    scores = {
        "c3_score": score_from_hits(diff_hits, 20, moderate_count=1, strong_count=3),
        "c4_score": score_from_hits(decision_hits, 15, moderate_count=1, strong_count=3),
        "c5_score": score_from_hits(sector_hits, 15, moderate_count=1, strong_count=2),
        "c6_score": 15 if len(growth_hits) >= 2 else 8 if growth_hits else 0,
        "c7_score": score_from_hits(systems_hits, 20, moderate_count=1, strong_count=3),
        "c8_score": score_from_hits(succession_hits, 15, moderate_count=1, strong_count=2),
    }

    if existing:
        for key in scores:
            scores[key] = int(float(existing.get(key, scores[key]) or 0))

    total = sum(scores.values()) if e1_pass and e2_pass and not disqualifiers else 0
    band = score_band(total)
    include = e1_pass and e2_pass and not disqualifiers and total >= 60
    needs_research = e1_pass and e2_pass and not disqualifiers and 40 <= total < 60

    if include:
        verdict = "Include in Federer list"
        decision = "YES"
    elif needs_research:
        verdict = "Borderline: research further before including"
        decision = "MAYBE"
    else:
        verdict = "Do not include yet"
        decision = "NO"

    if existing:
        verdict = f"{verdict} (matched existing pipeline row)"

    segment = str(existing.get("segment")) if existing else infer_segment(evidence_text)
    source_links = str(existing.get("source_links", "")) if existing else normalize_url(website)

    evidence_summary = {
        "Producer signals": producer_hits,
        "Trader/distributor risks": trader_hits,
        "Location signals": city_hits,
        "Differentiation signals": diff_hits,
        "Decision-maker signals": decision_hits,
        "Sector tailwind signals": sector_hits,
        "Growth signals": growth_hits,
        "Systems signals": systems_hits,
        "Succession signals": succession_hits,
    }

    return {
        "company": company or str(existing.get("company", "")) if existing else company,
        "website": website or str(existing.get("website", "")) if existing else website,
        "city": city,
        "segment": segment,
        "basket": "C" if "PACE" in segment else "B",
        "what_they_make": str(existing.get("what_they_make", "")) if existing else summarize_product(evidence_text),
        "revenue_estimate": str(existing.get("revenue_estimate", "Not verified")) if existing else "Not verified by automatic checker",
        "decision_maker": str(existing.get("decision_maker", "")) if existing else ", ".join(decision_hits) or "Not visible from supplied evidence",
        "e1_producer": e1_pass,
        "e2_accessible": e2_pass,
        "growth_signal_count": len(growth_hits),
        "total_score": total,
        "band": band,
        "verdict": verdict,
        "decision": decision,
        "personalization_hook": str(existing.get("personalization_hook", "")) if existing else build_hook(company, segment, diff_hits, systems_hits),
        "source_links": source_links,
        "notes": build_notes(fetch_status, disqualifiers, evidence_summary),
        "disqualifiers": disqualifiers,
        "fetch_status": fetch_status,
        "evidence_summary": evidence_summary,
        **scores,
    }


def summarize_product(text: str) -> str:
    hits = keyword_hits(text, PACE_KEYWORDS + ISI_KEYWORDS + PRODUCER_KEYWORDS)
    if not hits:
        return "Product/service not clear from supplied evidence."
    return "Likely in-house producer based on signals: " + ", ".join(hits[:10])


def build_hook(company: str, segment: str, diff_hits: list[str], systems_hits: list[str]) -> str:
    strongest = diff_hits[:2] + systems_hits[:2]
    if strongest:
        return f"{company or 'This company'} shows {segment} fit through {', '.join(strongest)} signals."
    return f"{company or 'This company'} needs more source evidence before a strong personalization hook."


def build_notes(fetch_status: str, disqualifiers: list[str], evidence_summary: dict[str, list[str]]) -> str:
    lines = [fetch_status]
    if disqualifiers:
        lines.append("Risks: " + "; ".join(disqualifiers))
    for label, hits in evidence_summary.items():
        if hits:
            lines.append(f"{label}: {', '.join(hits[:8])}")
    return "\n".join(lines)


def dataframe_from_state(records: list[dict[str, object]], columns: list[str] | None = None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    if columns:
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        return df[columns]
    return df


def csv_download(df: pd.DataFrame, filename: str, label: str) -> None:
    st.download_button(
        label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


def methodology_text() -> str:
    target_segments = ", ".join(st.session_state.target_segments)
    researcher = st.session_state.researcher or "Researcher name"
    return f"""# Methodology: Target Company Research

Researcher: {researcher}
City selected: {st.session_state.target_city}
Segment focus: {target_segments}

## Search logic
1. Built an initial longlist from company websites, industry directories, LinkedIn, job posts, news, certification pages, export references, and MCA/financial data where available.
2. Treated city as operational presence, not just registered office. A company counted only when founder, plant, R&D, or primary operations were reachable in the selected city.
3. Screened each company through E1 Producer and E2 Accessible before scoring.
4. Excluded traders, distributors, pure service intermediaries, generic pharma, large group subsidiaries, PE/VC-controlled companies, companies above Rs.500Cr revenue, inactive companies, and placeholder websites.

## Scoring logic
Only companies passing both gates were scored out of 100:
- C3 Differentiated: 20
- C4 Decision-maker quality: 15
- C5 Growing sector: 15
- C6 Growth signals: 15
- C7 Systems maturity: 20
- C8 Leadership succession: 15

Each criterion was scored as Weak, Moderate, or Strong based on visible evidence. Growth signals were counted from hiring, facility expansion, new certifications, website/news activity, and financial/export growth. Strong C6 required at least two verified signals.

## Output interpretation
- 80-100: A - Strong Federer
- 60-79: B - Probable Federer
- 40-59: C - Borderline, research further
- Below 40: D - Not ICP

## Verification discipline
Every included company should include source links and a short personalization hook. Rejected companies are retained in the fail list so the final submission shows the expected research yield and avoids hiding investigated misses.
"""


def render_header() -> None:
    st.title(APP_TITLE)
    st.caption("A Streamlit workstation for DeepThought's Business Analytics internship assignment.")
    c1, c2, c3, c4 = st.columns(4)
    pass_df = dataframe_from_state(st.session_state.companies, EXPORT_COLUMNS)
    reject_df = dataframe_from_state(st.session_state.rejects)
    with c1:
        st.metric("Included", len(pass_df))
    with c2:
        st.metric("Rejected", len(reject_df))
    with c3:
        investigated = len(pass_df) + len(reject_df)
        st.metric("Investigated", investigated)
    with c4:
        yield_rate = 0 if investigated == 0 else round(len(pass_df) / investigated * 100, 1)
        st.metric("Yield", f"{yield_rate}%")


def render_setup_tab() -> None:
    st.subheader("Research Scope")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        st.session_state.target_city = st.selectbox(
            "Target city",
            CITY_OPTIONS,
            index=CITY_OPTIONS.index(st.session_state.target_city),
        )
    with col2:
        st.session_state.target_segments = st.multiselect(
            "Target segment(s)",
            SEGMENT_OPTIONS,
            default=st.session_state.target_segments,
        )
    with col3:
        st.session_state.researcher = st.text_input("Researcher", st.session_state.researcher)

    st.info(
        "Use the tracker as a working file: add rejects as you screen, then score only companies that pass E1 and E2."
    )
    st.markdown("### Assignment Gates")
    gate1, gate2 = st.columns(2)
    with gate1:
        st.markdown("**E1 Producer**")
        st.write("Own product, plant, facility, studio, R&D, or proprietary specialized delivery capability.")
    with gate2:
        st.markdown("**E2 Accessible**")
        st.write("Physical India operations DeepThought can reach with on-site Fellows.")


def render_analyzer_tab() -> None:
    st.subheader("Analyze Company")
    st.write("Enter a company name, website link, or paste evidence. The checker applies E1/E2, disqualifiers, and C3-C8 scoring.")

    with st.form("analyzer_form"):
        col1, col2, col3 = st.columns([1.1, 1.3, 0.8])
        with col1:
            company = st.text_input("Company name", placeholder="Example: JAL Precision Products")
            city = st.selectbox("Required operational city", CITY_OPTIONS, index=CITY_OPTIONS.index(st.session_state.target_city))
        with col2:
            website = st.text_input("Website link", placeholder="https://company.com")
            fetch_site = st.checkbox("Fetch and scan website text", value=True)
        with col3:
            st.markdown("**Target segments**")
            st.caption("PACE and ISI are selected in Scope.")
            strict_city = st.checkbox("Strict city gate", value=True)

        pasted_evidence = st.text_area(
            "Paste extra evidence",
            placeholder="Paste About page text, LinkedIn summary, certification lines, revenue notes, founder details, hiring news, etc.",
            height=180,
        )
        submitted = st.form_submit_button("Run Federer analysis", use_container_width=True)

    if submitted:
        selected_city = city if strict_city else "India"
        st.session_state.last_analysis = build_analysis(
            company=company.strip(),
            website=website.strip(),
            city=selected_city,
            pasted_evidence=pasted_evidence,
            fetch_site=fetch_site,
        )

    analysis = st.session_state.get("last_analysis")
    if not analysis:
        st.info("Tip: a website link gives the checker more evidence. If a website blocks automated reading, paste the About/Products/Certifications text manually.")
        return

    decision = str(analysis["decision"])
    if decision == "YES":
        st.success(str(analysis["verdict"]))
    elif decision == "MAYBE":
        st.warning(str(analysis["verdict"]))
    else:
        st.error(str(analysis["verdict"]))

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Decision", decision)
    with m2:
        st.metric("Score", f"{analysis['total_score']}/100")
    with m3:
        st.metric("Band", str(analysis["band"]).split(" - ")[0])
    with m4:
        st.metric("Growth Signals", int(analysis["growth_signal_count"]))

    gate1, gate2, gate3 = st.columns(3)
    with gate1:
        st.markdown("**E1 Producer**")
        st.markdown("PASS" if analysis["e1_producer"] else "FAIL")
    with gate2:
        st.markdown("**E2 Accessible**")
        st.markdown("PASS" if analysis["e2_accessible"] else "FAIL")
    with gate3:
        st.markdown("**Segment Fit**")
        st.markdown(str(analysis["segment"]))

    if analysis["disqualifiers"]:
        st.markdown("### Auto-disqualifier Risks")
        for risk in analysis["disqualifiers"]:
            st.write(f"- {risk}")

    st.markdown("### Score Breakdown")
    breakdown = pd.DataFrame(
        [
            {"Code": "C3", "Criterion": "Differentiated", "Score": analysis["c3_score"], "Weight": 20},
            {"Code": "C4", "Criterion": "Decision-maker quality", "Score": analysis["c4_score"], "Weight": 15},
            {"Code": "C5", "Criterion": "Growing sector", "Score": analysis["c5_score"], "Weight": 15},
            {"Code": "C6", "Criterion": "Growth signals", "Score": analysis["c6_score"], "Weight": 15},
            {"Code": "C7", "Criterion": "Systems maturity", "Score": analysis["c7_score"], "Weight": 20},
            {"Code": "C8", "Criterion": "Leadership succession", "Score": analysis["c8_score"], "Weight": 15},
        ]
    )
    st.dataframe(breakdown, use_container_width=True, hide_index=True)

    st.markdown("### Evidence Signals")
    evidence_summary = analysis["evidence_summary"]
    evidence_rows = [
        {"Signal Type": label, "Detected Evidence": ", ".join(hits) if hits else "None"}
        for label, hits in evidence_summary.items()
    ]
    st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)

    st.markdown("### Research Output")
    out1, out2 = st.columns(2)
    with out1:
        st.text_area("What they make", str(analysis["what_they_make"]), height=100)
        st.text_area("Personalization hook", str(analysis["personalization_hook"]), height=100)
    with out2:
        st.text_area("Decision-maker evidence", str(analysis["decision_maker"]), height=100)
        st.text_area("Notes", str(analysis["notes"]), height=100)

    action1, action2 = st.columns(2)
    with action1:
        if st.button("Add this company to target pipeline", use_container_width=True):
            row = {col: analysis.get(col, "") for col in EXPORT_COLUMNS}
            st.session_state.companies.append(row)
            st.success("Added to target pipeline.")
    with action2:
        if st.button("Add this company to fail list", use_container_width=True):
            reject = blank_reject()
            reject.update(
                {
                    "company": str(analysis["company"]),
                    "website": str(analysis["website"]),
                    "city": str(analysis["city"]),
                    "segment": str(analysis["segment"]),
                    "reason": "; ".join(analysis["disqualifiers"]) or str(analysis["verdict"]),
                    "evidence": str(analysis["notes"]),
                    "source_links": str(analysis["source_links"]),
                    "date_checked": str(date.today()),
                }
            )
            st.session_state.rejects.append(reject)
            st.success("Added to fail list.")


def render_add_company_tab() -> None:
    st.subheader("Add Scored Company")
    with st.form("company_form", clear_on_submit=True):
        top1, top2, top3 = st.columns([1.2, 1.2, 0.7])
        with top1:
            company = st.text_input("Company name")
            website = st.text_input("Website")
            city = st.selectbox("Operational city", CITY_OPTIONS, index=CITY_OPTIONS.index(st.session_state.target_city))
        with top2:
            segment = st.selectbox("Segment", SEGMENT_OPTIONS)
            basket = st.selectbox("Basket", ["A", "B", "C"])
            revenue = st.text_input("Revenue estimate", placeholder="Example: Rs.120Cr FY24")
        with top3:
            e1 = st.checkbox("E1 Producer", value=True)
            e2 = st.checkbox("E2 Accessible", value=True)
            growth_signals = st.multiselect("Growth signals", GROWTH_SIGNALS)

        what_they_make = st.text_area("What they make / deliver in-house", height=90)
        decision_maker = st.text_input("Decision-maker / leadership evidence")

        st.markdown("### Federer Score")
        score_cols = st.columns(2)
        scores: dict[str, int] = {}
        levels: dict[str, str] = {}
        labels = list(SCORE_RULES.keys())
        for idx, label in enumerate(labels):
            with score_cols[idx % 2]:
                score, level = criterion_score(label, "add")
                code = SCORE_RULES[label]["code"].lower()
                scores[f"{code}_score"] = score
                levels[code] = level

        c6_auto = 15 if len(growth_signals) >= 2 else 8 if len(growth_signals) == 1 else 0
        use_auto_c6 = st.checkbox(
            f"Use growth signal count to set C6 automatically ({c6_auto} pts)",
            value=True,
        )
        if use_auto_c6:
            scores["c6_score"] = c6_auto

        total = sum(scores.values()) if e1 and e2 else 0
        band = score_band(total)
        st.metric("Calculated Federer score", f"{total}/100", band)

        personalization_hook = st.text_area("Personalization hook", height=70)
        verdict = st.text_area("Verdict / caveats", height=80)
        source_links = st.text_area("Source links", placeholder="One URL per line", height=80)
        notes = st.text_area("Notes / evidence", height=90)

        submitted = st.form_submit_button("Add company", use_container_width=True)

    if submitted:
        if not company.strip():
            st.error("Company name is required.")
            return
        if not e1 or not e2:
            st.warning("This company failed an eligibility gate. Add it to the reject list instead.")
            return

        record = blank_company()
        record.update(
            {
                "company": company.strip(),
                "website": website.strip(),
                "city": city,
                "segment": segment,
                "basket": basket,
                "what_they_make": what_they_make.strip(),
                "revenue_estimate": revenue.strip(),
                "decision_maker": decision_maker.strip(),
                "e1_producer": e1,
                "e2_accessible": e2,
                "growth_signal_count": len(growth_signals),
                "total_score": total,
                "band": band,
                "verdict": verdict.strip(),
                "personalization_hook": personalization_hook.strip(),
                "source_links": source_links.strip(),
                "notes": notes.strip(),
            }
        )
        record.update(scores)
        st.session_state.companies.append(record)
        st.success(f"Added {company.strip()} with score {total}/100.")


def render_reject_tab() -> None:
    st.subheader("Fail List")
    with st.form("reject_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            company = st.text_input("Rejected company")
            website = st.text_input("Website ")
            city = st.selectbox("City ", CITY_OPTIONS, index=CITY_OPTIONS.index(st.session_state.target_city))
        with col2:
            segment = st.selectbox("Segment ", SEGMENT_OPTIONS)
            reason = st.selectbox("Primary reason", DISQUALIFIERS)
            checked = st.date_input("Date checked", value=date.today())
        evidence = st.text_area("Evidence / note", height=90)
        source_links = st.text_area("Source links ", height=80)
        submitted = st.form_submit_button("Add rejected company", use_container_width=True)

    if submitted:
        if not company.strip():
            st.error("Company name is required.")
            return
        record = blank_reject()
        record.update(
            {
                "company": company.strip(),
                "website": website.strip(),
                "city": city,
                "segment": segment,
                "reason": reason,
                "evidence": evidence.strip(),
                "source_links": source_links.strip(),
                "date_checked": str(checked),
            }
        )
        st.session_state.rejects.append(record)
        st.success(f"Added {company.strip()} to the fail list.")

    reject_df = dataframe_from_state(st.session_state.rejects)
    if not reject_df.empty:
        st.dataframe(reject_df, use_container_width=True, hide_index=True)
        csv_download(reject_df, "federer_rejected_companies.csv", "Download fail list CSV")


def render_pipeline_tab() -> None:
    st.subheader("Pipeline")
    df = dataframe_from_state(st.session_state.companies, EXPORT_COLUMNS)
    if df.empty:
        st.info("No scored companies yet. Add your first pass candidate from the scoring tab.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        band_filter = st.multiselect("Band", sorted(df["band"].dropna().unique()), default=sorted(df["band"].dropna().unique()))
    with col2:
        city_filter = st.multiselect("City", sorted(df["city"].dropna().unique()), default=sorted(df["city"].dropna().unique()))
    with col3:
        min_score = st.slider("Minimum score", 0, 100, 0)

    filtered = df[
        df["band"].isin(band_filter)
        & df["city"].isin(city_filter)
        & (pd.to_numeric(df["total_score"], errors="coerce").fillna(0) >= min_score)
    ].sort_values(["total_score", "company"], ascending=[False, True])

    st.dataframe(filtered, use_container_width=True, hide_index=True)
    csv_download(filtered, "federer_target_companies.csv", "Download target CSV")

    st.markdown("### Score Distribution")
    chart_df = filtered[["company", "total_score"]].set_index("company")
    st.bar_chart(chart_df)


def render_import_export_tab() -> None:
    st.subheader("Import / Export")
    st.write("Paste or upload a previous CSV to continue work in this session.")

    uploaded = st.file_uploader("Upload target CSV", type=["csv"])
    pasted = st.text_area("Or paste CSV content", height=130)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Import target companies", use_container_width=True):
            source = uploaded.read().decode("utf-8") if uploaded else pasted
            if source.strip():
                imported = pd.read_csv(StringIO(source))
                st.session_state.companies = imported.to_dict("records")
                st.success(f"Imported {len(imported)} target rows.")
            else:
                st.error("Upload a CSV or paste CSV text first.")
    with col2:
        if st.button("Clear current session data", use_container_width=True):
            st.session_state.companies = []
            st.session_state.rejects = []
            st.success("Cleared in-memory tracker data.")

    targets = dataframe_from_state(st.session_state.companies, EXPORT_COLUMNS)
    rejects = dataframe_from_state(st.session_state.rejects)
    if not targets.empty:
        csv_download(targets, "federer_target_companies.csv", "Download all target rows")
    if not rejects.empty:
        csv_download(rejects, "federer_rejected_companies.csv", "Download all reject rows")

    st.markdown("### Methodology Draft")
    text = methodology_text()
    st.download_button(
        "Download methodology Markdown",
        data=text.encode("utf-8"),
        file_name="methodology.md",
        mime="text/markdown",
        use_container_width=True,
    )
    st.text_area("Methodology text", text, height=360)


def render_reference_tab() -> None:
    st.subheader("Scoring Reference")
    rows = []
    for label, rule in SCORE_RULES.items():
        rows.append(
            {
                "Code": rule["code"],
                "Criterion": label,
                "Weight": rule["weight"],
                "Weak": rule["weak"],
                "Moderate": rule["moderate"],
                "Strong": rule["strong"],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Auto-disqualifiers")
        for item in DISQUALIFIERS:
            st.write(f"- {item}")
    with col2:
        st.markdown("### Growth Signal Thresholds")
        for item in GROWTH_SIGNALS:
            st.write(f"- {item}")


def main() -> None:
    page_setup()
    seed_state()
    render_header()

    setup, analyzer, add, pipeline, rejects, exports, reference = st.tabs(
        ["Scope", "Analyze Company", "Score Company", "Pipeline", "Fail List", "Exports", "Rubric"]
    )
    with setup:
        render_setup_tab()
    with analyzer:
        render_analyzer_tab()
    with add:
        render_add_company_tab()
    with pipeline:
        render_pipeline_tab()
    with rejects:
        render_reject_tab()
    with exports:
        render_import_export_tab()
    with reference:
        render_reference_tab()


if __name__ == "__main__":
    main()
