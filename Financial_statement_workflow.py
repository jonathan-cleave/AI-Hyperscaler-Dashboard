"""
Financial Statement Data Workflow - Python / Colab Version
Course: Financial Ratio Analytics

Purpose
-------
This script shows how financial-statement data can be pulled, cleaned,
processed, and summarized using public company data.

Main workflow:
    source -> download -> parse -> clean -> align -> compute -> flag -> interpret

Recommended use
---------------
Google Colab is the recommended environment for this Python version.

Colab setup cell:
    !pip install -q requests pandas numpy beautifulsoup4 lxml openpyxl yfinance

Then upload or paste this file and run:
    %run financial_statement_workflow_colab_canvas.py

Before running
--------------
1. Replace USER_AGENT with a real class/contact email.
2. Replace TICKER if you want a different company.
3. Yahoo/yfinance is included only as a convenience comparison source.
   SEC EDGAR/XBRL is the official structured-data source.
"""

# ==========================================================
# 0. Imports and user settings
# ==========================================================

import os
import re
import sys
import time
from urllib.parse import urljoin

try:
    import requests
    import numpy as np
    import pandas as pd
    from bs4 import BeautifulSoup
except ImportError as e:
    print("Missing a required Python package.")
    print("In Colab, run this first:")
    print("!pip install -q requests pandas numpy beautifulsoup4 lxml openpyxl yfinance")
    print(f"Import error: {e}")
    sys.exit(0)

try:
    import yfinance as yf
except Exception:
    yf = None


# ----------------------------------------------------------
# Edit these lines for your project
# ----------------------------------------------------------

USER_AGENT = "CalPoly Financial Analytics Course contact: jacleave@calpoly.edu"
TICKER = "META"

COMPANY_NEWS_URL = (
    "https://www.intc.com/news-events/press-releases/detail/1767/"
    "intel-reports-first-quarter-2026-financial-results"
)
PATH = "C:/Users/jonat/Documents/Calpoly MSBA/Spring/Finance Analytics/Project 2/"
OUT_DIR = PATH + f"financial_statement_workflow_output_{TICKER}"


# ==========================================================
# 1. General helpers
# ==========================================================

def ensure_output_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def write_csv(df, filename):
    ensure_output_dir()
    path = os.path.join(OUT_DIR, filename)
    df.to_csv(path, index=False)
    return path


def safe_num(x):
    try:
        if x is None or x == "":
            return np.nan
        return float(x)
    except Exception:
        return np.nan


def safe_int(x):
    try:
        if x is None or x == "":
            return np.nan
        return int(x)
    except Exception:
        return np.nan


def safe_date(x):
    try:
        if x is None or x == "":
            return pd.NaT
        return pd.to_datetime(x, errors="coerce")
    except Exception:
        return pd.NaT


def safe_divide(num, den):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    if isinstance(out, pd.Series):
        return out.replace([np.inf, -np.inf], np.nan)
    if pd.isna(out) or np.isinf(out):
        return np.nan
    return out


def coalesce_any(df, cols):
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return pd.Series(np.nan, index=df.index)
    out = df[existing[0]].copy()
    for c in existing[1:]:
        out = out.combine_first(df[c])
    return out


def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


# ==========================================================
# 2. Web and SEC helpers
# ==========================================================

def sec_get(url, sleep_seconds=0.35):
    time.sleep(sleep_seconds)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    return requests.get(url, headers=headers, timeout=30)


def sec_get_json(url, sleep_seconds=0.35):
    response = sec_get(url, sleep_seconds=sleep_seconds)

    print("\nSEC request:", url)
    print("Status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))

    if response.status_code >= 300:
        print("First 500 characters of SEC response:")
        print(response.text[:500])
        raise RuntimeError(f"SEC request failed. Status {response.status_code}. URL: {url}")

    try:
        return response.json()
    except Exception as e:
        print("SEC response was not valid JSON.")
        print("First 500 characters of response:")
        print(response.text[:500])
        raise RuntimeError(
            "SEC did not return JSON. Check USER_AGENT, internet access, "
            "proxy settings, or SEC rate limits."
        ) from e


def safe_read_html(url, user_agent=None):
    if user_agent is None:
        user_agent = USER_AGENT
    try:
        response = requests.get(url, headers={"User-Agent": user_agent}, timeout=30)
        if response.status_code >= 300:
            print(f"HTML page unavailable. Status {response.status_code}. URL: {url}")
            return None
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"HTML page unavailable: {url}")
        print(f"Error: {e}")
        return None


# ==========================================================
# 3. SEC ticker-to-CIK and filings
# ==========================================================

def get_sec_company_tickers():
    url = "https://www.sec.gov/files/company_tickers.json"
    raw = sec_get_json(url)

    rows = []
    for _, item in raw.items():
        cik = int(item.get("cik_str"))
        rows.append({
            "ticker": str(item.get("ticker", "")).upper(),
            "title": item.get("title"),
            "cik": cik,
            "cik10": str(cik).zfill(10),
        })
    return pd.DataFrame(rows)


def lookup_cik(ticker):
    tickers = get_sec_company_tickers()
    result = tickers[tickers["ticker"] == ticker.upper()].copy()
    if result.empty:
        raise ValueError(f"Ticker not found in SEC company_tickers.json: {ticker}")
    return result.iloc[[0]].reset_index(drop=True)


def get_submissions(cik10):
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    return sec_get_json(url)


def flatten_recent_filings(submissions_json):
    recent = submissions_json.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])

    if len(accession_numbers) == 0:
        return pd.DataFrame()

    df = pd.DataFrame({
        "accessionNumber": recent.get("accessionNumber", []),
        "filingDate": recent.get("filingDate", []),
        "reportDate": recent.get("reportDate", []),
        "acceptanceDateTime": recent.get("acceptanceDateTime", []),
        "form": recent.get("form", []),
        "size": recent.get("size", []),
        "isXBRL": recent.get("isXBRL", []),
        "isInlineXBRL": recent.get("isInlineXBRL", []),
        "primaryDocument": recent.get("primaryDocument", []),
        "primaryDocDescription": recent.get("primaryDocDescription", []),
    })

    df["filingDate"] = pd.to_datetime(df["filingDate"], errors="coerce")
    df["reportDate"] = pd.to_datetime(df["reportDate"], errors="coerce")
    df["accession_clean"] = df["accessionNumber"].str.replace("-", "", regex=False)

    return df[
        [
            "accessionNumber", "accession_clean", "filingDate", "reportDate",
            "form", "primaryDocument", "primaryDocDescription",
            "acceptanceDateTime", "isXBRL", "isInlineXBRL", "size"
        ]
    ]


def get_filing_url(cik_int, accession_clean, primary_document):
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_int}/{accession_clean}/{primary_document}"
    )


# ==========================================================
# 4. SEC Company Facts / XBRL
# ==========================================================

def get_companyfacts(cik10):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    return sec_get_json(url)


def extract_company_concept(facts_json, tag, unit="USD"):
    gaap = facts_json.get("facts", {}).get("us-gaap", {})
    if tag not in gaap:
        return pd.DataFrame()

    concept = gaap[tag]
    units = concept.get("units", {})
    if unit not in units:
        return pd.DataFrame()

    rows = []
    for r in units[unit]:
        rows.append({
            "tag": tag,
            "label": concept.get("label", tag),
            "description": concept.get("description", np.nan),
            "start": safe_date(r.get("start")),
            "end": safe_date(r.get("end")),
            "filed": safe_date(r.get("filed")),
            "fy": safe_int(r.get("fy")),
            "fp": r.get("fp"),
            "form": r.get("form"),
            "frame": r.get("frame"),
            "val": safe_num(r.get("val")),
            "accn": r.get("accn"),
        })
    return pd.DataFrame(rows)


def clean_xbrl(xbrl_long):
    if xbrl_long.empty:
        return pd.DataFrame()

    df = xbrl_long.copy()
    df = df[
        df["end"].notna()
        & df["val"].notna()
        & df["form"].isin(["10-K", "10-Q", "8-K"])
    ].copy()

    df = df.sort_values(
        ["tag", "fy", "fp", "form", "end", "filed"],
        ascending=[True, True, True, True, True, False],
    )

    df = df.drop_duplicates(
        subset=["tag", "fy", "fp", "form", "end"],
        keep="first",
    )
    return df.reset_index(drop=True)


# ==========================================================
# 5. Ratio construction
# ==========================================================

def build_annual_ratios(df):
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["fy"] = df["fy"]

    revenue = coalesce_any(df, [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ])
    gross_profit = coalesce_any(df, ["GrossProfit"])
    operating_income = coalesce_any(df, ["OperatingIncomeLoss"])
    pretax_income = coalesce_any(df, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ])
    net_income = coalesce_any(df, ["NetIncomeLoss"])
    cash = coalesce_any(df, [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ])
    short_term_investments = coalesce_any(df, ["ShortTermInvestments"])
    inventory = coalesce_any(df, ["InventoryNet"])
    current_assets = coalesce_any(df, ["AssetsCurrent"])
    total_assets = coalesce_any(df, ["Assets"])
    current_liabilities = coalesce_any(df, ["LiabilitiesCurrent"])
    equity = coalesce_any(df, [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ])
    current_debt = coalesce_any(df, [
        "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"
    ])
    long_term_debt = coalesce_any(df, ["LongTermDebtNoncurrent", "DebtNoncurrent"])

    total_debt = current_debt.fillna(0) + long_term_debt.fillna(0)
    total_debt[current_debt.isna() & long_term_debt.isna()] = np.nan

    cfo = coalesce_any(df, ["NetCashProvidedByUsedInOperatingActivities"])
    capex_raw = coalesce_any(df, ["PaymentsToAcquirePropertyPlantAndEquipment"])
    capex = capex_raw.abs()
    depreciation_amortization = coalesce_any(df, [
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationExpense",
    ])
    free_cash_flow = cfo - capex
    ebitda_proxy = operating_income + depreciation_amortization

    out["revenue"] = revenue
    out["gross_profit"] = gross_profit
    out["operating_income"] = operating_income
    out["pretax_income"] = pretax_income
    out["net_income"] = net_income
    out["current_assets"] = current_assets
    out["current_liabilities"] = current_liabilities
    out["cash"] = cash
    out["short_term_investments"] = short_term_investments
    out["total_debt"] = total_debt
    out["total_assets"] = total_assets
    out["equity"] = equity
    out["cfo"] = cfo
    out["capex"] = capex
    out["free_cash_flow"] = free_cash_flow

    out["gross_margin"] = safe_divide(gross_profit, revenue)
    out["operating_margin"] = safe_divide(operating_income, revenue)
    out["net_margin"] = safe_divide(net_income, revenue)
    out["current_ratio"] = safe_divide(current_assets, current_liabilities)
    out["quick_ratio"] = safe_divide(current_assets - inventory, current_liabilities)
    out["cash_ratio"] = safe_divide(cash + short_term_investments, current_liabilities)
    out["debt_to_equity"] = safe_divide(total_debt, equity)
    out["debt_to_assets"] = safe_divide(total_debt, total_assets)
    out["debt_to_ebitda_proxy"] = safe_divide(total_debt, ebitda_proxy)
    out["cfo_to_debt"] = safe_divide(cfo, total_debt)
    out["fcf_to_debt"] = safe_divide(free_cash_flow, total_debt)
    out["capex_to_revenue"] = safe_divide(capex, revenue)
    out["asset_turnover"] = safe_divide(revenue, total_assets)
    out["return_on_assets"] = safe_divide(net_income, total_assets)
    out["return_on_equity"] = safe_divide(net_income, equity)

    return out


def flag_ratio(value, green_rule, yellow_rule):
    if pd.isna(value):
        return "Missing"
    if green_rule(value):
        return "Green"
    if yellow_rule(value):
        return "Yellow"
    return "Red"


def build_latest_dashboard(annual_ratios):
    if annual_ratios.empty:
        return pd.DataFrame()

    latest = annual_ratios.sort_values("fy", ascending=False).iloc[0]

    metric_rules = {
        "current_ratio": (lambda x: x > 1.5, lambda x: x >= 1.0),
        "quick_ratio": (lambda x: x > 1.0, lambda x: x >= 0.7),
        "operating_margin": (lambda x: x > 0.15, lambda x: x >= 0.05),
        "debt_to_equity": (lambda x: x < 0.75, lambda x: x <= 1.5),
        "cfo_to_debt": (lambda x: x > 0.20, lambda x: x >= 0.08),
        "fcf_to_debt": (lambda x: x > 0.10, lambda x: x >= 0.03),
        "capex_to_revenue": (lambda x: x < 0.10, lambda x: x <= 0.25),
    }

    rows = []
    for metric, rules in metric_rules.items():
        value = latest.get(metric, np.nan)
        rows.append({
            "fiscal_year": latest["fy"],
            "metric": metric,
            "value": value,
            "flag": flag_ratio(value, rules[0], rules[1]),
        })

    return pd.DataFrame(rows)


# ==========================================================
# 6. Text helpers
# ==========================================================

def make_text_features(text_file):
    if not os.path.exists(text_file):
        return pd.DataFrame()

    with open(text_file, "r", encoding="utf-8") as f:
        text = f.read()

    sentences = [s for s in split_sentences(text) if len(s) > 30]
    sentences_lower = [s.lower() for s in sentences]

    dictionary = [
        ("growth", r"growth|grow|increase|strong|strength|expansion|accelerat"),
        ("risk", r"risk|uncertain|weak|decline|pressure|headwind|constraint|shortage"),
        ("profitability", r"margin|profit|income|earnings|cost|pricing|yield"),
        ("liquidity", r"cash|liquidity|debt|capital|free cash flow|cash flow"),
        ("guidance", r"guidance|outlook|expect|forecast|second quarter|full year"),
    ]

    rows = []
    for category, pattern in dictionary:
        regex = re.compile(pattern)
        count = sum(bool(regex.search(s)) for s in sentences_lower)
        rows.append({"category": category, "pattern": pattern, "count": count})

    return pd.DataFrame(rows)


# ==========================================================
# 7. Main workflow
# ==========================================================

def main():
    ensure_output_dir()

    print(f"Workflow initialized for ticker: {TICKER}")
    print(f"Output folder: {os.path.abspath(OUT_DIR)}")

    try:
        company_id = lookup_cik(TICKER)
    except Exception as e:
        print("\nCould not complete SEC ticker lookup.")
        print("The script did not crash, but SEC data were not available.")
        print("Likely causes: internet access, SEC block, proxy, or USER_AGENT.")
        print(f"Details: {e}")
        diagnostic = pd.DataFrame([{
            "ticker": TICKER,
            "stage": "ticker_to_cik",
            "status": "failed",
            "message": str(e),
        }])
        write_csv(diagnostic, f"{TICKER}_diagnostic.csv")
        return

    print("\nCompany ID:")
    print(company_id)
    write_csv(company_id, f"{TICKER}_sec_company_id.csv")

    cik10 = company_id.loc[0, "cik10"]
    cik_int = int(company_id.loc[0, "cik"])

    try:
        submissions = get_submissions(cik10)
        recent_filings = flatten_recent_filings(submissions)
    except Exception as e:
        print("\nCould not retrieve SEC submissions.")
        print(f"Details: {e}")
        recent_filings = pd.DataFrame()

    if not recent_filings.empty:
        recent_annual_quarterly = (
            recent_filings[recent_filings["form"].isin(["10-K", "10-Q"])]
            .sort_values("filingDate", ascending=False)
            .copy()
        )

        recent_annual_quarterly["filing_url"] = recent_annual_quarterly.apply(
            lambda r: get_filing_url(cik_int, r["accession_clean"], r["primaryDocument"]),
            axis=1,
        )
    else:
        recent_annual_quarterly = pd.DataFrame()

    #write_csv(recent_annual_quarterly, f"{TICKER}_recent_10K_10Q_filings.csv")

    print("\nRecent 10-K and 10-Q filings:")
    if not recent_annual_quarterly.empty:
        print(recent_annual_quarterly[["form", "filingDate", "reportDate", "primaryDocument", "filing_url"]].head(10))
    else:
        print("No recent filings table available.")

    try:
        facts_json = get_companyfacts(cik10)
    except Exception as e:
        print("\nCould not retrieve SEC Company Facts.")
        print(f"Details: {e}")
        facts_json = {}

    available_us_gaap_tags = list(facts_json.get("facts", {}).get("us-gaap", {}).keys())
    print(f"\nNumber of available us-gaap tags: {len(available_us_gaap_tags)}")

    if available_us_gaap_tags:
        def tag_search(pattern):
            pattern_lower = pattern.lower()
            return (
                pd.DataFrame({"tag": available_us_gaap_tags})
                .query("tag.str.lower().str.contains(@pattern_lower)", engine="python")
                .sort_values("tag")
                .reset_index(drop=True)
            )

        print("\nExamples of Revenue tags:")
        print(tag_search("Revenue").head(20))
        print("\nExamples of Debt tags:")
        print(tag_search("Debt").head(20))
        print("\nExamples of Cash tags:")
        print(tag_search("Cash").head(20))

    common_usd_tags = [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "GrossProfit",
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "NetIncomeLoss",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ShortTermInvestments",
        "AccountsReceivableNetCurrent",
        "InventoryNet",
        "AssetsCurrent",
        "Assets",
        "LiabilitiesCurrent",
        "Liabilities",
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "DebtCurrent",
        "DebtNoncurrent",
        "ShortTermBorrowings",
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsOfDividends",
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationExpense",
    ]

    common_usd_tags = [t for t in common_usd_tags if t in available_us_gaap_tags]

    tables = []
    for tag in common_usd_tags:
        df = extract_company_concept(facts_json, tag, unit="USD")
        if not df.empty:
            tables.append(df)

    eps_table = extract_company_concept(facts_json, "EarningsPerShareDiluted", unit="USD/shares")
    shares_table = extract_company_concept(facts_json, "WeightedAverageNumberOfDilutedSharesOutstanding", unit="shares")

    for df in [eps_table, shares_table]:
        if not df.empty:
            tables.append(df)

    if tables:
        xbrl_long = pd.concat(tables, ignore_index=True)
        xbrl_long = xbrl_long.sort_values(["tag", "end", "filed"], ascending=[True, False, False])
    else:
        xbrl_long = pd.DataFrame()

    write_csv(xbrl_long, f"{TICKER}_xbrl_long_common_tags.csv")

    print(f"\nRows extracted from SEC Company Facts: {len(xbrl_long)}")
    if not xbrl_long.empty:
        print(xbrl_long["tag"].value_counts())

    xbrl_clean = clean_xbrl(xbrl_long)
    write_csv(xbrl_clean, f"{TICKER}_xbrl_clean.csv")

    if not xbrl_clean.empty:
        annual_long = (
            xbrl_clean[(xbrl_clean["form"] == "10-K") & (xbrl_clean["fp"] == "FY")]
            .sort_values(["tag", "fy", "filed"], ascending=[True, True, False])
            .drop_duplicates(subset=["tag", "fy"], keep="first")
            .copy()
        )

        annual_wide = (
            annual_long
            .pivot_table(index="fy", columns="tag", values="val", aggfunc="first")
            .reset_index()
            .sort_values("fy")
        )

        quarterly_long = (
            xbrl_clean[
                (xbrl_clean["form"] == "10-Q")
                & (xbrl_clean["fp"].isin(["Q1", "Q2", "Q3"]))
            ]
            .sort_values(["tag", "fy", "fp", "end", "filed"], ascending=[True, True, True, True, False])
            .drop_duplicates(subset=["tag", "fy", "fp", "end"], keep="first")
            .copy()
        )

        quarterly_wide = (
            quarterly_long
            .pivot_table(index=["fy", "fp", "end"], columns="tag", values="val", aggfunc="first")
            .reset_index()
            .sort_values("end")
        )
    else:
        annual_wide = pd.DataFrame()
        quarterly_wide = pd.DataFrame()

    #write_csv(annual_wide, f"{TICKER}_annual_xbrl_wide.csv")
    #write_csv(quarterly_wide, f"{TICKER}_quarterly_xbrl_wide.csv")

    print("\nAnnual XBRL wide table:")
    print(annual_wide.tail(5))

    print("\nQuarterly XBRL wide table:")
    print(quarterly_wide.tail(8))

    annual_ratios = build_annual_ratios(annual_wide)
    write_csv(annual_ratios, f"{TICKER}_annual_ratios.csv")

    print("\nAnnual ratio table:")
    print(annual_ratios.tail(8))

    dashboard = build_latest_dashboard(annual_ratios)
    #write_csv(dashboard, f"{TICKER}_latest_ratio_dashboard.csv")

    print("\nLatest dashboard:")
    print(dashboard)

    if not recent_annual_quarterly.empty:
        latest_url = recent_annual_quarterly.iloc[0]["filing_url"]
        print(f"\nLatest filing URL: {latest_url}")

        filing_html = safe_read_html(latest_url)
        if filing_html is not None:
            filing_text = filing_html.get_text(" ", strip=True)
            filing_text = re.sub(r"\s+", " ", filing_text)

            filing_text_file = os.path.join(OUT_DIR, f"{TICKER}_latest_filing_text.txt")
            with open(filing_text_file, "w", encoding="utf-8") as f:
                f.write(filing_text)

            keywords = [
                "liquidity", "capital resources", "risk", "demand", "supply",
                "margin", "restructuring", "debt", "cash flow", "guidance"
            ]
            pattern = re.compile("|".join([re.escape(k) for k in keywords]), re.IGNORECASE)

            sentences = [
                {"sentence_id": i + 1, "sentence": s}
                for i, s in enumerate(split_sentences(filing_text))
                if len(s) > 40
            ]
            filing_sentences = pd.DataFrame(sentences)

            if not filing_sentences.empty:
                keyword_hits = filing_sentences[
                    filing_sentences["sentence"].str.contains(pattern, na=False)
                ].head(100)
            else:
                keyword_hits = pd.DataFrame(columns=["sentence_id", "sentence"])

            #write_csv(keyword_hits, f"{TICKER}_latest_filing_keyword_hits.csv")
            print("\nFirst filing keyword hits:")
            print(keyword_hits.head(10))

    company_page = safe_read_html(
        COMPANY_NEWS_URL,
        user_agent="Mozilla/5.0 FinancialAnalyticsClass/1.0",
    )

    likely_call_materials = pd.DataFrame()

    if company_page is not None:
        links = []
        for a in company_page.find_all("a"):
            link_text = a.get_text(" ", strip=True)
            href = a.get("href")
            href_full = urljoin(COMPANY_NEWS_URL, href) if href else np.nan
            lower_text = f"{link_text} {href_full}".lower()

            if href_full and isinstance(href_full, str):
                links.append({
                    "link_text": link_text,
                    "href": href,
                    "href_full": href_full,
                    "lower_text": lower_text,
                })

        links_df = pd.DataFrame(links)
        if not links_df.empty:
            links_df = links_df.drop_duplicates(subset=["href_full"])
        else:
            links_df = pd.DataFrame(columns=["link_text", "href", "href_full", "lower_text"])

        #write_csv(links_df, f"{TICKER}_company_website_links.csv")

        if not links_df.empty:
            mask = links_df["lower_text"].str.contains(
                "earnings|prepared|remarks|transcript|call|presentation|financial-results|pdf",
                regex=True,
                na=False,
            )
            likely_call_materials = links_df[mask].drop_duplicates(subset=["href_full"]).copy()

        #write_csv(likely_call_materials, f"{TICKER}_likely_earnings_call_materials.csv")

    filing_features = make_text_features(os.path.join(OUT_DIR, f"{TICKER}_latest_filing_text.txt"))
    if not filing_features.empty:
        #write_csv(filing_features, f"{TICKER}_filing_text_features.csv")
        print("\nFiling text features:")
        print(filing_features)

    if yf is not None:
        try:
            ticker_obj = yf.Ticker(TICKER)

            yahoo_income = ticker_obj.financials.T.reset_index()
            yahoo_balance = ticker_obj.balance_sheet.T.reset_index()
            yahoo_cashflow = ticker_obj.cashflow.T.reset_index()

            #write_csv(yahoo_income, f"{TICKER}_yahoo_income_statement.csv")
            #write_csv(yahoo_balance, f"{TICKER}_yahoo_balance_sheet.csv")
            #write_csv(yahoo_cashflow, f"{TICKER}_yahoo_cash_flow_statement.csv")

            print("\nYahoo income statement preview:")
            print(yahoo_income.head())
        except Exception as e:
            print("\nYahoo Finance pull did not succeed. Continuing without it.")
            print(f"Details: {e}")
    else:
        print("\nyfinance is not installed. Skipping Yahoo comparison.")

    try:
        excel_path = os.path.join(OUT_DIR, f"{TICKER}_financial_statement_workflow.xlsx")
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            company_id.to_excel(writer, sheet_name="company_id", index=False)
            recent_annual_quarterly.to_excel(writer, sheet_name="recent_filings", index=False)

            if not xbrl_long.empty:
                (
                    xbrl_long["tag"]
                    .value_counts()
                    .rename_axis("tag")
                    .reset_index(name="count")
                    .to_excel(writer, sheet_name="xbrl_tag_counts", index=False)
                )

            annual_wide.to_excel(writer, sheet_name="annual_xbrl", index=False)
            quarterly_wide.to_excel(writer, sheet_name="quarterly_xbrl", index=False)
            annual_ratios.to_excel(writer, sheet_name="annual_ratios", index=False)
            dashboard.to_excel(writer, sheet_name="dashboard", index=False)

            if not likely_call_materials.empty:
                likely_call_materials.to_excel(writer, sheet_name="company_links", index=False)
    except Exception as e:
        print("\nExcel export did not succeed. CSV files were still created.")
        print(f"Details: {e}")

    print(f"\nDone. Output folder: {os.path.abspath(OUT_DIR)}")
    print("Main files created:")
    for file_name in sorted(os.listdir(OUT_DIR)):
        print(os.path.join(OUT_DIR, file_name))


if __name__ == "__main__":
    main()
