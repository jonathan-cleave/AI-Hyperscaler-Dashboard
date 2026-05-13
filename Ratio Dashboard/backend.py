from __future__ import annotations

import math
import socket
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
WORKBOOK_CANDIDATES = [
    BASE_DIR.parent / "Data" / "All Ratios.xlsx",
    BASE_DIR.parent / "Data" / "Ratios.xlsx",
    BASE_DIR / "Data" / "All Ratios.xlsx",
    BASE_DIR / "All Ratios.xlsx",
]
FIRMS_DATA_CANDIDATES = [
    BASE_DIR.parent / "Data" / "firms.parquet",
    BASE_DIR / "Data" / "firms.parquet",
    BASE_DIR.parent / "Data" / "globalcompfirms2025.xlsx",
    BASE_DIR / "Data" / "globalcompfirms2025.xlsx",
]

COMPANY_NAMES = {
    "AMZN": "Amazon",
    "MSFT": "Microsoft",
    "META": "Meta Platforms",
    "GOOG": "Alphabet",
    "GOOGL": "Alphabet",
}

DISPLAY_TICKERS = {"GOOG": "GOOGL"}
ORDER_HINT = ["AMZN", "MSFT", "META", "GOOG", "GOOGL"]

PERCENT_METRICS = {
    "Revenue Growth",
    "Gross Margin",
    "EBITDA Margin",
    "Operating Margin",
    "Net Profit Margin",
    "ROA",
    "ROE",
    "CapEx / Revenue",
    "PPE / Assets",
    "Asset Growth",
    "Op Cash / Revenue",
    "FCF Margin",
}

MULTIPLE_METRICS = {
    "Current Ratio",
    "Debt / Equity",
    "Interest Coverage",
    "P/E",
    "Price / Sales",
    "EV / EBITDA",
}

NAV_ITEMS = [
    {"key": "comparables", "label": "Comps Finder", "href": "/comparables"},
    {"key": "home", "label": "Broad Comparison", "href": "/"},
    {"key": "profitability", "label": "Profitability", "href": "/profitability"},
    {"key": "capital", "label": "Capital Intensity", "href": "/capital-intensity"},
    {"key": "leverage", "label": "Liquidity + Leverage", "href": "/leverage"},
    {"key": "cash_flow", "label": "Cash Flow", "href": "/cash-flow"},
    {"key": "valuation", "label": "Valuation", "href": "/valuation"},
    {"key": "insights", "label": "Final Insights", "href": "/insights"},
]

PAGE_META = {
    "home": {
        "title": "Broad Company Comparison",
        "eyebrow": "Hyperscaler finance dashboard",
        "subtitle": "Who is capturing the gains, who is carrying the capital burden, and where is financial risk building?",
    },
    "profitability": {
        "title": "Profitability Conversion",
        "eyebrow": "Margins and returns",
        "subtitle": "Measures which firms are converting cloud and AI demand into operating earnings, net income, and balance sheet returns.",
    },
    "capital": {
        "title": "Capital Intensity",
        "eyebrow": "Data center load",
        "subtitle": "Tracks how capex and infrastructure assets are absorbing revenue growth as AI workloads scale.",
    },
    "leverage": {
        "title": "Liquidity and Leverage",
        "eyebrow": "Financial flexibility",
        "subtitle": "Assesses balance sheet risk through liquidity, debt intensity, and interest coverage.",
    },
    "cash_flow": {
        "title": "Cash Flow Funding Capacity",
        "eyebrow": "Self funding test",
        "subtitle": "Shows whether operating cash flow is large enough to absorb AI and data center capex.",
    },
    "valuation": {
        "title": "Valuation and Implied Price",
        "eyebrow": "Comps plus workbook model",
        "subtitle": "Combines comparable-company assumptions from Comps with the MSFT Valuation worksheet and an interactive EV/EBITDA model.",
    },
    "comparables": {
        "title": "Comparable Company Finder",
        "eyebrow": "Distance-to pipeline",
        "subtitle": "Input any ticker and rank the top four comparable companies using the numeric distance pipeline from comps.ipynb.",
    },
    "insights": {
        "title": "Comparison and Final Insights",
        "eyebrow": "Presentation close",
        "subtitle": "Ranks the hyperscalers and answers who wins, who spends, and where risk is forming.",
    },
}


class DashboardDataError(RuntimeError):
    """Raised when the workbook cannot support a requested dashboard view."""


def display_ticker(ticker: Any) -> str:
    raw = str(ticker).strip().upper()
    return DISPLAY_TICKERS.get(raw, raw)


def company_name(ticker: Any) -> str:
    raw = str(ticker).strip().upper()
    return COMPANY_NAMES.get(raw, raw)


def metric_format(metric: str) -> str:
    if metric in PERCENT_METRICS:
        return "percent"
    if metric in MULTIPLE_METRICS:
        return "multiple"
    if metric in {"Revenue", "EBITDA", "CAPEX", "Net Debt", "EV", "Equity"}:
        return "money_m"
    return "number"


def find_workbook() -> Path:
    for candidate in WORKBOOK_CANDIDATES:
        if candidate.exists():
            return candidate
    checked = ", ".join(str(path) for path in WORKBOOK_CANDIDATES)
    raise DashboardDataError(f"Could not find All Ratios.xlsx. Checked: {checked}")


def find_firms_data() -> Path:
    for candidate in FIRMS_DATA_CANDIDATES:
        if candidate.exists():
            return candidate
    checked = ", ".join(str(path) for path in FIRMS_DATA_CANDIDATES)
    raise DashboardDataError(f"Could not find firms comparable-company data. Checked: {checked}")


def normalize_input_ticker(ticker: Any) -> str:
    text = str(ticker or "").strip().upper()
    if ":" in text:
        text = text.split(":")[-1]
    return text


def clean_column_name(name: Any) -> str:
    return str(name).strip().replace("\n", " ")


def read_standard_sheet(path: Path, sheet_name: str, required: bool = True) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except ValueError as exc:
        if required:
            raise DashboardDataError(f"Missing required sheet: {sheet_name}") from exc
        return pd.DataFrame()

    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [clean_column_name(col) for col in df.columns]

    if "Ticker" in df.columns:
        df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
    if "FY" in df.columns:
        df["FY"] = pd.to_datetime(df["FY"], errors="coerce")
        df = df[df["FY"].notna()]
        df["Year"] = df["FY"].dt.year.astype(int)
    if "Ticker" in df.columns:
        df = df[df["Ticker"].notna() & (df["Ticker"] != "NAN")]

    for col in df.columns:
        if col not in {"Ticker", "FY"}:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().any():
                df[col] = converted

    return df


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col not in {"Ticker", "FY", "Display Ticker", "Company"}:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def target_order(available_tickers: list[str]) -> list[str]:
    available = {str(t).upper() for t in available_tickers}
    ordered = [ticker for ticker in ORDER_HINT if ticker in available]
    return list(dict.fromkeys(ordered))


def filter_targets(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Ticker" not in df.columns:
        return df
    order = target_order(df["Ticker"].dropna().astype(str).str.upper().unique().tolist())
    out = df[df["Ticker"].isin(order)].copy()
    out["Display Ticker"] = out["Ticker"].map(display_ticker)
    out["Company"] = out["Ticker"].map(company_name)
    out["Ticker Order"] = out["Ticker"].map({ticker: idx for idx, ticker in enumerate(order)})
    sort_cols = [col for col in ["Ticker Order", "Year"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)
    return out


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def safe_div(numerator: Any, denominator: Any) -> float | None:
    num = safe_float(numerator)
    den = safe_float(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(float(value)) or math.isinf(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    return value


def fmt_pct(value: Any, digits: int = 1) -> str:
    num = safe_float(value)
    return "n/a" if num is None else f"{num * 100:.{digits}f}%"


def fmt_x(value: Any, digits: int = 1) -> str:
    num = safe_float(value)
    return "n/a" if num is None else f"{num:.{digits}f}x"


def fmt_money_m(value: Any) -> str:
    num = safe_float(value)
    if num is None:
        return "n/a"
    sign = "-" if num < 0 else ""
    num = abs(num)
    if num >= 1_000_000:
        return f"{sign}${num / 1_000_000:.2f}T"
    if num >= 1_000:
        return f"{sign}${num / 1_000:.1f}B"
    return f"{sign}${num:.0f}M"


def fmt_price(value: Any) -> str:
    num = safe_float(value)
    return "n/a" if num is None else f"${num:,.2f}"


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.sort_values(["Ticker Order", "Year"]).groupby("Ticker", as_index=False).tail(1)


@lru_cache(maxsize=1)
def prepare_comparable_firms() -> dict[str, Any]:
    path = find_firms_data()
    if path.suffix.lower() == ".parquet":
        firms = pd.read_parquet(path)
    else:
        firms = pd.read_excel(path)

    firms = firms.dropna(how="all").dropna(axis=1, how="all")
    firms.columns = [clean_column_name(col) for col in firms.columns]

    required = ["Company Name", "Exchange:Ticker", "Industry Group", "Primary Sector", "SIC Code", "Country"]
    missing = [col for col in required if col not in firms.columns]
    if missing:
        raise DashboardDataError(f"Comparable-company data is missing required columns: {', '.join(missing)}")

    firms["Exchange:Ticker"] = firms["Exchange:Ticker"].astype(str).str.strip().str.split(":").str[-1].str.upper()
    firms = firms[firms["Exchange:Ticker"].notna() & (firms["Exchange:Ticker"] != "") & (firms["Exchange:Ticker"] != "NAN")]

    similar_df = firms.copy()
    similar_df = similar_df.drop(similar_df.columns[0:8], axis=1)
    similar_df = similar_df.replace([np.inf, -np.inf], np.nan)
    similar_df = similar_df.apply(pd.to_numeric, errors="coerce")
    similar_df = similar_df.dropna(axis=1, how="all")
    if similar_df.empty:
        raise DashboardDataError("Comparable-company data has no numeric fields after applying the comps.ipynb descriptor drop.")

    medians = similar_df.median(numeric_only=True)
    similar_df = similar_df.fillna(medians).fillna(0)

    means = similar_df.mean(axis=0)
    stds = similar_df.std(axis=0, ddof=0).replace(0, np.nan)
    scaled = ((similar_df - means) / stds).fillna(0)

    return {
        "path": str(path),
        "firms": firms,
        "scaled": scaled,
        "feature_count": int(scaled.shape[1]),
        "firm_count": int(firms.shape[0]),
    }


def comparable_mode_label(compare_by: str) -> str:
    labels = {
        "sic": "SIC",
        "industry": "Industry",
        "sector": "Sector",
        "all": "All",
        "none": "None",
    }
    return labels.get(compare_by, compare_by.title())


def comparable_mask(firms: pd.DataFrame, target_row: pd.Series, compare_by: str) -> pd.Series:
    if compare_by == "sic":
        return firms["SIC Code"] == target_row["SIC Code"]
    if compare_by == "industry":
        return firms["Industry Group"] == target_row["Industry Group"]
    if compare_by == "sector":
        return firms["Primary Sector"] == target_row["Primary Sector"]
    if compare_by == "all":
        return (
            (firms["SIC Code"] == target_row["SIC Code"])
            & (firms["Industry Group"] == target_row["Industry Group"])
            & (firms["Primary Sector"] == target_row["Primary Sector"])
        )
    if compare_by == "none":
        return pd.Series(True, index=firms.index)
    raise DashboardDataError("compare_by must be one of: sic, industry, sector, all, none.")


def comparable_value(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    return safe_float(row.get(column))


def find_comparable_companies(ticker: Any, compare_by: str = "none", n_comps: int = 4) -> dict[str, Any]:
    normalized_ticker = normalize_input_ticker(ticker)
    compare_by = str(compare_by or "none").strip().lower()
    n_comps = max(1, min(int(n_comps or 4), 12))

    if not normalized_ticker:
        raise DashboardDataError("Enter a ticker before running the comparable-company search.")

    prepared = prepare_comparable_firms()
    firms: pd.DataFrame = prepared["firms"]
    scaled: pd.DataFrame = prepared["scaled"]

    ticker_matches = firms.index[firms["Exchange:Ticker"] == normalized_ticker].tolist()
    if not ticker_matches:
        contains = firms[firms["Exchange:Ticker"].str.contains(normalized_ticker, na=False, regex=False)].head(8)
        suggestions = contains["Exchange:Ticker"].dropna().astype(str).tolist()
        message = f"Ticker {normalized_ticker} was not found in firms.parquet."
        if suggestions:
            message += f" Close matches: {', '.join(suggestions)}."
        raise DashboardDataError(message)

    target_idx = ticker_matches[0]
    target_row = firms.loc[target_idx]
    mask = comparable_mask(firms, target_row, compare_by)
    filtered_df = firms[mask].copy()
    candidate_idx = filtered_df.index

    distances = np.linalg.norm(
        scaled.loc[candidate_idx].values - scaled.loc[target_idx].values,
        axis=1,
    )

    distance_col = f"Distance_to_{normalized_ticker}"
    filtered_df[distance_col] = distances
    top_comps = (
        filtered_df[filtered_df["Exchange:Ticker"] != normalized_ticker]
        .sort_values(distance_col)
        .head(n_comps)
    )

    target_payload = {
        "company_name": str(target_row.get("Company Name", normalized_ticker)),
        "ticker": normalized_ticker,
        "sic_code": str(target_row.get("SIC Code", "")),
        "industry_group": str(target_row.get("Industry Group", "")),
        "primary_sector": str(target_row.get("Primary Sector", "")),
        "country": str(target_row.get("Country", "")),
        "market_cap": comparable_value(target_row, "Market Cap (in US $)"),
        "enterprise_value": comparable_value(target_row, "Enterprise Value (in US $)"),
        "ev_ebitda": comparable_value(target_row, "EV/EBITDA"),
        "ps": comparable_value(target_row, "PS"),
        "net_margin": comparable_value(target_row, "Net Profit Margin"),
    }

    matches = []
    for _, row in top_comps.iterrows():
        matches.append(
            {
                "company_name": str(row.get("Company Name", "")),
                "ticker": str(row.get("Exchange:Ticker", "")),
                "sic_code": str(row.get("SIC Code", "")),
                "industry_group": str(row.get("Industry Group", "")),
                "primary_sector": str(row.get("Primary Sector", "")),
                "country": str(row.get("Country", "")),
                "distance": safe_float(row.get(distance_col)),
                "market_cap": comparable_value(row, "Market Cap (in US $)"),
                "enterprise_value": comparable_value(row, "Enterprise Value (in US $)"),
                "ev_ebitda": comparable_value(row, "EV/EBITDA"),
                "ps": comparable_value(row, "PS"),
                "net_margin": comparable_value(row, "Net Profit Margin"),
            }
        )

    return sanitize(
        {
            "ticker": normalized_ticker,
            "compare_by": compare_by,
            "compare_by_label": comparable_mode_label(compare_by),
            "n_comps": n_comps,
            "target": target_payload,
            "matches": matches,
            "universe_count": int(len(filtered_df)),
            "feature_count": prepared["feature_count"],
            "firm_count": prepared["firm_count"],
            "data_source": prepared["path"],
            "distance_column": distance_col,
            "note": "Distances use the comps.ipynb pipeline: drop descriptor columns 0-7, coerce remaining fields to numeric, median-fill missing values, standardize, then rank Euclidean distance.",
        }
    )


def records_by_metric(df: pd.DataFrame, metric: str) -> list[dict[str, Any]]:
    needed = {"Ticker", "Display Ticker", "Company", "Year", metric}
    if df.empty or not needed.issubset(df.columns):
        return []
    subset = df[["Ticker", "Display Ticker", "Company", "Year", metric]].dropna(subset=["Year"])
    return [
        {
            "ticker": row["Ticker"],
            "display_ticker": row["Display Ticker"],
            "company": row["Company"],
            "year": int(row["Year"]),
            "value": safe_float(row[metric]),
        }
        for _, row in subset.iterrows()
    ]


def chart_direction(metric: str | None, title: str | None = None) -> str:
    lower_is_better = {
        "CapEx / Revenue",
        "PPE / Assets",
        "Asset Growth",
        "Debt / Equity",
        "Debt / Assets",
        "Debt / Capital",
        "P/E",
        "Price / Sales",
        "EV / EBITDA",
    }
    higher_is_better = {
        "Revenue Growth",
        "Gross Margin",
        "EBITDA Margin",
        "Operating Margin",
        "Net Profit Margin",
        "ROA",
        "ROE",
        "ROIC",
        "Current Ratio",
        "Quick Ratio",
        "Interest Coverage",
        "Op Cash / Revenue",
        "FCF Margin",
        "Revenue",
        "EBITDA",
        "CAPEX",
    }
    if metric in lower_is_better:
        return "Lower is Better"
    if metric in higher_is_better:
        return "Higher is Better"
    if title and "rank" in title.lower():
        return "Lower is Better"
    return "Higher is Better"


def make_line_chart(df: pd.DataFrame, metric: str, title: str | None = None) -> dict[str, Any]:
    if df.empty or metric not in df.columns:
        return {"id": slug(metric), "title": title or metric, "labels": [], "series": [], "format": metric_format(metric), "direction": chart_direction(metric, title)}
    years = sorted(df["Year"].dropna().astype(int).unique().tolist())
    series = []
    for ticker, group in df.sort_values(["Ticker Order", "Year"]).groupby("Ticker", sort=False):
        values = []
        by_year = group.set_index("Year")
        for year in years:
            values.append(safe_float(by_year.loc[year, metric]) if year in by_year.index else None)
        first = group.iloc[0]
        series.append(
            {
                "ticker": ticker,
                "display_ticker": first["Display Ticker"],
                "company": first["Company"],
                "values": values,
            }
        )
    return {
        "id": slug(metric),
        "title": title or metric,
        "metric": metric,
        "labels": years,
        "series": series,
        "format": metric_format(metric),
        "direction": chart_direction(metric, title),
    }


def make_latest_bar(df: pd.DataFrame, metric: str, title: str | None = None) -> dict[str, Any]:
    latest = latest_rows(df)
    if latest.empty or metric not in latest.columns:
        return {"id": f"{slug(metric)}-bar", "title": title or metric, "labels": [], "values": [], "format": metric_format(metric), "direction": chart_direction(metric, title)}
    latest = latest.sort_values("Ticker Order")
    return {
        "id": f"{slug(metric)}-bar",
        "title": title or metric,
        "metric": metric,
        "labels": latest["Display Ticker"].tolist(),
        "values": [safe_float(value) for value in latest[metric].tolist()],
        "format": metric_format(metric),
        "direction": chart_direction(metric, title),
    }


def slug(text: str) -> str:
    return (
        str(text)
        .strip()
        .lower()
        .replace("/", " ")
        .replace("+", " ")
        .replace("&", " ")
        .replace("%", "pct")
        .replace(".", "")
        .replace(" ", "-")
    )


def leader(latest: pd.DataFrame, metric: str, high_good: bool = True) -> pd.Series | None:
    if latest.empty or metric not in latest.columns:
        return None
    valid = latest.dropna(subset=[metric])
    if valid.empty:
        return None
    idx = valid[metric].idxmax() if high_good else valid[metric].idxmin()
    return valid.loc[idx]


def parse_comps(path: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    try:
        top = pd.read_excel(path, sheet_name="Comps")
        raw = pd.read_excel(path, sheet_name="Comps", header=None, dtype=object)
    except ValueError:
        errors.append("Missing Comps sheet. Valuation assumptions will be limited.")
        return {}

    top.columns = [clean_column_name(col) for col in top.columns]
    comps: dict[str, dict[str, Any]] = {}

    if "COMPS" in top.columns:
        top_rows = top[top["COMPS"].notna()].copy()
        for _, row in top_rows.iterrows():
            ticker = str(row.get("COMPS")).strip().upper()
            if ticker in {"NAN", ""}:
                continue
            if ticker not in comps:
                comps[ticker] = {}
            for col in ["EV", "EV/EBITDA", "WACC"]:
                if col in top.columns:
                    comps[ticker][col] = safe_float(row.get(col))

    header_row = None
    for idx, row in raw.iterrows():
        if any(str(cell).strip() == "Cost of Debt" for cell in row.tolist()):
            header_row = idx
            break

    if header_row is not None:
        header_values = raw.iloc[header_row, 1:].tolist()
        headers = [clean_column_name(value) for value in header_values if not pd.isna(value)]
        width = len(headers)
        lower = raw.iloc[header_row + 1 :, 1 : 1 + width].copy()
        lower.columns = headers
        lower = lower.dropna(how="all")
        if "COMPS" in lower.columns:
            lower = lower[lower["COMPS"].notna()]
            for _, row in lower.iterrows():
                ticker = str(row.get("COMPS")).strip().upper()
                if ticker in {"NAN", ""}:
                    continue
                if ticker not in comps:
                    comps[ticker] = {}
                for col in headers:
                    if col == "COMPS":
                        continue
                    key = f"Assumption {col}" if col == "WACC" and "WACC" in comps[ticker] else col
                    comps[ticker][key] = safe_float(row.get(col))
    else:
        errors.append("Could not locate the assumptions table in Comps.")

    return comps


def locate_cell(raw: pd.DataFrame, label: str) -> tuple[int, int] | None:
    target = label.strip().lower()
    for row_idx in range(raw.shape[0]):
        for col_idx in range(raw.shape[1]):
            value = raw.iat[row_idx, col_idx]
            if isinstance(value, str) and value.strip().lower() == target:
                return row_idx, col_idx
    return None


def date_header_cols(raw: pd.DataFrame, row_idx: int, start_col: int) -> list[int]:
    cols = []
    for col_idx in range(start_col + 1, raw.shape[1]):
        value = raw.iat[row_idx, col_idx]
        if not pd.isna(value):
            cols.append(col_idx)
    return cols


def extract_wide_table(raw: pd.DataFrame, title: str) -> dict[str, Any]:
    cell = locate_cell(raw, title)
    if cell is None:
        return {"title": title, "headers": [], "rows": []}

    title_row, label_col = cell
    header_row = None
    value_cols: list[int] = []
    for candidate in range(title_row, min(title_row + 3, raw.shape[0])):
        cols = date_header_cols(raw, candidate, label_col)
        if len(cols) >= 2:
            header_row = candidate
            value_cols = cols
            break

    if header_row is None:
        return {"title": title, "headers": [], "rows": []}

    headers = [str(raw.iat[header_row, col]).strip() for col in value_cols]
    rows = []
    blank_count = 0
    for row_idx in range(header_row + 1, raw.shape[0]):
        label = raw.iat[row_idx, label_col]
        if pd.isna(label):
            blank_count += 1
            if blank_count >= 2:
                break
            continue
        blank_count = 0
        label_text = str(label).strip()
        if label_text.isupper() and row_idx > header_row + 1:
            break
        rows.append(
            {
                "label": label_text,
                "values": [safe_float(raw.iat[row_idx, col]) for col in value_cols],
            }
        )
    return {"title": title, "headers": headers, "rows": rows}


def extract_label_table(raw: pd.DataFrame, anchor_label: str) -> dict[str, Any]:
    cell = locate_cell(raw, anchor_label)
    if cell is None:
        return {"headers": [], "rows": []}
    row_idx, label_col = cell
    header_row = row_idx - 1 if row_idx > 0 else row_idx
    value_cols = date_header_cols(raw, header_row, label_col)
    headers = [str(raw.iat[header_row, col]).strip() for col in value_cols]
    rows = []
    blank_count = 0
    for current in range(row_idx, raw.shape[0]):
        label = raw.iat[current, label_col]
        if pd.isna(label):
            blank_count += 1
            if blank_count >= 2:
                break
            continue
        blank_count = 0
        rows.append(
            {
                "label": str(label).strip(),
                "values": [safe_float(raw.iat[current, col]) for col in value_cols],
            }
        )
    return {"headers": headers, "rows": rows}


def extract_dcf_table(raw: pd.DataFrame) -> dict[str, Any]:
    cell = locate_cell(raw, "DCF")
    if cell is None:
        return {"headers": [], "rows": []}
    row_idx, label_col = cell
    value_cols = date_header_cols(raw, row_idx, label_col)
    headers = [str(raw.iat[row_idx, col]).strip() for col in value_cols]
    rows = []
    for current in range(row_idx + 1, raw.shape[0]):
        label = raw.iat[current, label_col]
        if pd.isna(label):
            break
        rows.append(
            {
                "label": str(label).strip(),
                "values": [safe_float(raw.iat[current, col]) for col in value_cols],
            }
        )
    return {"headers": headers, "rows": rows}


def parse_msft_valuation(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        raw = pd.read_excel(path, sheet_name="MSFT Valuation", header=None, dtype=object)
    except ValueError:
        errors.append("Missing MSFT Valuation sheet. The valuation page will use comps only.")
        return {}

    income = extract_wide_table(raw, "INCOME STATEMENTS")
    balance = extract_wide_table(raw, "BALANCE SHEETS")
    cash_flow = extract_label_table(raw, "EBIT")
    dcf = extract_dcf_table(raw)

    outputs = {}
    for label in ["EV", "Debt", "Cash", "Shares", "Price"]:
        cell = locate_cell(raw, label)
        if cell is not None:
            row_idx, col_idx = cell
            outputs[label] = safe_float(raw.iat[row_idx, col_idx + 1]) if col_idx + 1 < raw.shape[1] else None

    return {
        "ticker": "MSFT",
        "display_ticker": "MSFT",
        "income": income,
        "balance": balance,
        "cash_flow": cash_flow,
        "dcf": dcf,
        "outputs": outputs,
    }


def overlay_statement_column(
    target: pd.DataFrame,
    source: pd.DataFrame,
    source_col: str,
    target_col: str,
    transform: Any | None = None,
) -> pd.DataFrame:
    if source.empty or source_col not in source.columns or not {"Ticker", "Year"}.issubset(source.columns):
        return target

    source_values = source[["Ticker", "Year", source_col]].copy()
    source_values["Ticker"] = source_values["Ticker"].astype(str).str.strip().str.upper()
    source_values[source_col] = pd.to_numeric(source_values[source_col], errors="coerce")
    if transform is not None:
        source_values[source_col] = source_values[source_col].map(lambda value: transform(value) if safe_float(value) is not None else np.nan)

    keyed = (
        source_values.dropna(subset=["Ticker", "Year"])
        .groupby(["Ticker", "Year"], as_index=True)[source_col]
        .last()
    )
    if keyed.empty:
        return target

    keys = pd.MultiIndex.from_frame(target[["Ticker", "Year"]])
    mapped = pd.Series(keys.map(keyed), index=target.index)
    if target_col not in target.columns:
        target[target_col] = np.nan
    target[target_col] = pd.to_numeric(target[target_col], errors="coerce").combine_first(mapped)
    return target


def series_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    return numerator / denominator


def recalculate_dashboard_ratios(df: pd.DataFrame) -> pd.DataFrame:
    if "Revenue" in df.columns:
        df["Revenue Growth"] = df.groupby("Ticker")["Revenue"].pct_change()

    if {"Gross profit", "Revenue"}.issubset(df.columns):
        df["Gross Margin"] = series_divide(df["Gross profit"], df["Revenue"])

    if {"EBITDA", "Revenue"}.issubset(df.columns):
        df["EBITDA Margin"] = series_divide(df["EBITDA"], df["Revenue"])

    if {"EBIT", "Revenue"}.issubset(df.columns):
        df["Operating Margin"] = series_divide(df["EBIT"], df["Revenue"])

    if {"Net Income", "Revenue"}.issubset(df.columns):
        df["Net Profit Margin"] = series_divide(df["Net Income"], df["Revenue"])

    if {"Net Income", "Total Assets"}.issubset(df.columns):
        df["ROA"] = series_divide(df["Net Income"], df["Total Assets"])

    if {"Net Income", "Equity"}.issubset(df.columns):
        df["ROE"] = series_divide(df["Net Income"], df["Equity"])

    if {"Current Assets", "Current Liabilities"}.issubset(df.columns):
        df["Current Ratio"] = series_divide(df["Current Assets"], df["Current Liabilities"])

    if {"Total Debt", "Equity"}.issubset(df.columns):
        df["Debt / Equity"] = series_divide(df["Total Debt"], df["Equity"])

    if {"Total Debt", "Cash + Investments"}.issubset(df.columns):
        df["Net Debt"] = pd.to_numeric(df["Total Debt"], errors="coerce") - pd.to_numeric(df["Cash + Investments"], errors="coerce")

    if {"EBIT", "Interest Expense"}.issubset(df.columns):
        interest = pd.to_numeric(df["Interest Expense"], errors="coerce").abs().replace(0, np.nan)
        df["Interest Coverage"] = pd.to_numeric(df["EBIT"], errors="coerce") / interest

    if {"CAPEX", "Revenue"}.issubset(df.columns):
        df["CapEx / Revenue"] = series_divide(df["CAPEX"], df["Revenue"])

    if {"PPE Gross", "Total Assets"}.issubset(df.columns):
        df["PPE / Assets"] = series_divide(df["PPE Gross"], df["Total Assets"])

    if {"Operating Cash Flow", "Revenue"}.issubset(df.columns):
        df["Op Cash / Revenue"] = series_divide(df["Operating Cash Flow"], df["Revenue"])

    if {"Operating Cash Flow", "CAPEX", "Revenue"}.issubset(df.columns):
        df["FCF Margin"] = series_divide(
            pd.to_numeric(df["Operating Cash Flow"], errors="coerce") - pd.to_numeric(df["CAPEX"], errors="coerce"),
            df["Revenue"],
        )

    if "Total Assets" in df.columns:
        df["Asset Growth"] = df.groupby("Ticker")["Total Assets"].pct_change()
    else:
        df["Asset Growth"] = np.nan

    return df


def add_derived_ratios(
    ratios: pd.DataFrame,
    income_statement: pd.DataFrame,
    balance: pd.DataFrame,
    cash_flow: pd.DataFrame,
    comps: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    df = ratios.copy()
    df.columns = [clean_column_name(col) for col in df.columns]
    df = coerce_numeric_columns(df)
    df = filter_targets(df)

    if "Ticker" not in df.columns or "Year" not in df.columns:
        raise DashboardDataError("Ratios sheet must include Ticker and FY/year data.")

    df = df.sort_values(["Ticker Order", "Year"])
    workbook_ratio_cols = [
        "Revenue Growth",
        "Gross Margin",
        "EBITDA Margin",
        "Operating Margin",
        "Net Profit Margin",
        "ROA",
        "ROE",
        "Current Ratio",
        "Debt / Equity",
        "Interest Coverage",
        "CapEx / Revenue",
        "PPE / Assets",
        "Op Cash / Revenue",
        "FCF Margin",
        "Asset Growth",
    ]
    workbook_ratio_values = {
        col: pd.to_numeric(df[col], errors="coerce").copy()
        for col in workbook_ratio_cols
        if col in df.columns
    }

    statement_overlays = [
        (income_statement, "Total Revenue", "Revenue", None),
        (income_statement, "Gross Profit", "Gross profit", None),
        (income_statement, "Operating Income", "EBIT", None),
        (income_statement, "Net Income", "Net Income", None),
        (balance, "Cash, Cash Equiv. & Short Term Inv.", "Cash + Investments", None),
        (balance, "Total Current Assets", "Current Assets", None),
        (balance, "Total Assets", "Total Assets", None),
        (balance, "Total Current Liabilities", "Current Liabilities", None),
        (balance, "Total Equity", "Equity", None),
        (balance, "PP&E Gross", "PPE Gross", None),
        (balance, "Total Common Shares Outstanding", "Shares Outstanding", None),
        (cash_flow, "Cash from Operating Activities", "Operating Cash Flow", None),
        (cash_flow, "Capital Expenditures", "CAPEX", lambda value: abs(float(value))),
    ]
    for source, source_col, target_col, transform in statement_overlays:
        df = overlay_statement_column(df, source, source_col, target_col, transform)

    df = recalculate_dashboard_ratios(df)
    for col, workbook_values in workbook_ratio_values.items():
        # Preserve the Ratios sheet exactly for charted ratio fields. If a workbook
        # cell is blank, the dashboard should show a blank/gap instead of filling it
        # with a backend recalculation.
        df[col] = workbook_values

    shares_lookup = latest_share_lookup(balance)
    for ticker in df["Ticker"].dropna().unique():
        comp = comps.get(ticker, {})
        market_equity = safe_float(comp.get("Equity"))
        top_ev = safe_float(comp.get("EV"))
        latest_idx = df[df["Ticker"] == ticker]["Year"].idxmax()
        latest = df.loc[latest_idx]
        revenue = safe_float(latest.get("Revenue"))
        net_income = safe_float(latest.get("Net Income"))
        ebitda = safe_float(latest.get("EBITDA"))
        shares = shares_lookup.get(ticker)

        if market_equity is not None:
            df.loc[latest_idx, "P/E"] = safe_div(market_equity, net_income)
            df.loc[latest_idx, "Price / Sales"] = safe_div(market_equity, revenue)
            if shares:
                df.loc[latest_idx, "Current Price"] = safe_div(market_equity, shares)

        ev_ebitda = safe_float(comp.get("EV/EBITDA")) or safe_div(top_ev, ebitda)
        if ev_ebitda is not None:
            df.loc[latest_idx, "EV / EBITDA"] = ev_ebitda

    return df


def latest_share_lookup(balance: pd.DataFrame) -> dict[str, float]:
    if balance.empty or "Total Common Shares Outstanding" not in balance.columns:
        return {}
    filtered = filter_targets(coerce_numeric_columns(balance))
    if filtered.empty:
        return {}
    latest = latest_rows(filtered)
    return {
        row["Ticker"]: safe_float(row["Total Common Shares Outstanding"])
        for _, row in latest.iterrows()
        if safe_float(row["Total Common Shares Outstanding"]) is not None
    }


def company_cards(latest: pd.DataFrame, comps: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cards = []
    for _, row in latest.sort_values("Ticker Order").iterrows():
        ticker = row["Ticker"]
        cards.append(
            {
                "ticker": ticker,
                "display_ticker": row["Display Ticker"],
                "company": row["Company"],
                "year": int(row["Year"]),
                "revenue": safe_float(row.get("Revenue")),
                "revenue_growth": safe_float(row.get("Revenue Growth")),
                "operating_margin": safe_float(row.get("Operating Margin")),
                "capex_revenue": safe_float(row.get("CapEx / Revenue")),
                "fcf_margin": safe_float(row.get("FCF Margin")),
                "debt_equity": safe_float(row.get("Debt / Equity")),
                "ev_ebitda": safe_float(comps.get(ticker, {}).get("EV/EBITDA") or row.get("EV / EBITDA")),
            }
        )
    return cards


def capital_burden_chain(latest: pd.DataFrame) -> list[dict[str, Any]]:
    if latest.empty:
        return []
    capex = latest["CapEx / Revenue"] if "CapEx / Revenue" in latest.columns else pd.Series(dtype=float)
    max_capex = safe_float(capex.max()) or 1
    chain = []
    for _, row in latest.sort_values("Ticker Order").iterrows():
        value = safe_float(row.get("CapEx / Revenue"))
        ppe = safe_float(row.get("PPE / Assets"))
        fill = 18 if value is None else max(18, min(100, value / max_capex * 100))
        chain.append(
            {
                "ticker": row["Ticker"],
                "display_ticker": row["Display Ticker"],
                "company": row["Company"],
                "capex_revenue": value,
                "ppe_assets": ppe,
                "fill": fill,
            }
        )
    return chain


def home_takeaways(latest: pd.DataFrame) -> list[str]:
    if latest.empty:
        return []
    margin_leader = leader(latest, "Operating Margin", True)
    cash_leader = leader(latest, "FCF Margin", True)
    capex_leader = leader(latest, "CapEx / Revenue", True)
    liquidity_leader = leader(latest, "Current Ratio", True)
    value_low = leader(latest, "EV / EBITDA", False)
    takeaways = []
    if margin_leader is not None:
        takeaways.append(
            f"{margin_leader['Display Ticker']} is converting demand into operating profit most efficiently at {fmt_pct(margin_leader['Operating Margin'])} operating margin."
        )
    if capex_leader is not None:
        takeaways.append(
            f"{capex_leader['Display Ticker']} carries the heaviest current infrastructure burden with capex at {fmt_pct(capex_leader['CapEx / Revenue'])} of revenue."
        )
    if cash_leader is not None:
        takeaways.append(
            f"{cash_leader['Display Ticker']} has the strongest latest free-cash-flow margin at {fmt_pct(cash_leader['FCF Margin'])}, giving it more room to self-fund AI buildout."
        )
    if liquidity_leader is not None:
        takeaways.append(
            f"{liquidity_leader['Display Ticker']} has the most visible liquidity cushion with a {fmt_x(liquidity_leader['Current Ratio'])} current ratio."
        )
    if value_low is not None:
        takeaways.append(
            f"{value_low['Display Ticker']} screens at the lowest EV/EBITDA multiple in the workbook comps at {fmt_x(value_low['EV / EBITDA'])}."
        )
    return takeaways


def metric_commentary(latest: pd.DataFrame, metric: str, high_good: bool, context: str) -> dict[str, Any]:
    best = leader(latest, metric, high_good)
    opposite = leader(latest, metric, not high_good)
    if best is None:
        return {"title": metric, "body": f"{metric} is not available in the workbook."}
    body = f"{best['Display Ticker']} leads on {metric} at "
    body += fmt_pct(best[metric]) if metric in PERCENT_METRICS else fmt_x(best[metric])
    if opposite is not None and opposite["Ticker"] != best["Ticker"]:
        body += f", while {opposite['Display Ticker']} is the main contrast point."
    body += f" {context}"
    return {"title": metric, "body": body}


def risk_heatmap(df: pd.DataFrame) -> dict[str, Any]:
    metrics = ["Current Ratio", "Debt / Equity", "Interest Coverage"]
    if df.empty or not set(metrics).issubset(df.columns):
        return {"years": [], "companies": [], "rows": []}

    recent_years = sorted(df["Year"].dropna().astype(int).unique().tolist())[-8:]
    subset = df[df["Year"].isin(recent_years)].copy()

    def minmax(series: pd.Series, reverse: bool = False) -> pd.Series:
        clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
        lo = clean.min()
        hi = clean.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            scaled = pd.Series(50, index=series.index, dtype=float)
        else:
            scaled = (clean - lo) / (hi - lo) * 100
        return 100 - scaled if reverse else scaled

    interest = subset["Interest Coverage"].clip(lower=-25, upper=200)
    subset["Risk Score"] = (
        minmax(subset["Debt / Equity"]).fillna(50)
        + minmax(subset["Current Ratio"], reverse=True).fillna(50)
        + minmax(interest, reverse=True).fillna(50)
    ) / 3

    companies = [
        {"ticker": row["Ticker"], "display_ticker": row["Display Ticker"], "company": row["Company"]}
        for _, row in latest_rows(subset).sort_values("Ticker Order").iterrows()
    ]
    rows = []
    for year in recent_years:
        year_cells = []
        for company in companies:
            match = subset[(subset["Year"] == year) & (subset["Ticker"] == company["ticker"])]
            if match.empty:
                year_cells.append({"score": None, "label": "n/a", "alpha": 0.08})
            else:
                score = safe_float(match.iloc[0]["Risk Score"])
                year_cells.append(
                    {
                        "score": score,
                        "label": "n/a" if score is None else f"{score:.0f}",
                        "alpha": 0.12 if score is None else 0.18 + (score / 100) * 0.72,
                    }
                )
        rows.append({"year": year, "cells": year_cells})
    return {
        "years": recent_years,
        "companies": companies,
        "rows": rows,
        "explanation": "Relative 0-100 balance-sheet pressure score. Higher/brighter cells mean more risk pressure from higher debt/equity, lower current ratio, and lower interest coverage.",
    }


def build_bridge_chart(latest: pd.DataFrame) -> dict[str, Any]:
    labels = []
    cfo_values = []
    capex_values = []
    fcf_values = []
    for _, row in latest.sort_values("Ticker Order").iterrows():
        revenue = safe_float(row.get("Revenue")) or 0
        labels.append(row["Display Ticker"])
        cfo_values.append((safe_float(row.get("Op Cash / Revenue")) or 0) * revenue)
        capex_values.append(-(safe_float(row.get("CapEx / Revenue")) or 0) * revenue)
        fcf_values.append((safe_float(row.get("FCF Margin")) or 0) * revenue)
    return {
        "id": "cash-flow-bridge",
        "title": "Operating Cash Flow to Free Cash Flow Bridge",
        "labels": labels,
        "datasets": [
            {"label": "Operating cash flow", "values": cfo_values},
            {"label": "Capex pressure", "values": capex_values},
            {"label": "Free cash flow", "values": fcf_values},
        ],
        "format": "money_m",
        "direction": "Higher is Better",
        "color_by": "dataset",
    }


def build_multiples(ratios: pd.DataFrame) -> list[dict[str, Any]]:
    latest = latest_rows(ratios)
    multiples = []
    for _, row in latest.sort_values("Ticker Order").iterrows():
        multiples.append(
            {
                "ticker": row["Ticker"],
                "display_ticker": row["Display Ticker"],
                "company": row["Company"],
                "pe": safe_float(row.get("P/E")),
                "price_sales": safe_float(row.get("Price / Sales")),
                "ev_ebitda": safe_float(row.get("EV / EBITDA")),
                "current_price": safe_float(row.get("Current Price")),
            }
        )
    return multiples


def msft_valuation_default(msft_sheet: dict[str, Any], latest_row: pd.Series) -> dict[str, Any]:
    default: dict[str, Any] = {}
    income_rows = {row["label"]: row for row in msft_sheet.get("income", {}).get("rows", [])}
    headers = msft_sheet.get("income", {}).get("headers", [])
    revenue_row = income_rows.get("Revenue")
    if revenue_row and headers:
        values = revenue_row.get("values", [])
        latest_year = int(latest_row.get("Year", 0))
        header_years = [year_from_header(header) for header in headers]
        actual_idx = None
        next_idx = None
        for idx, year in enumerate(header_years):
            if year == latest_year:
                actual_idx = idx
            if year and year > latest_year and next_idx is None:
                next_idx = idx
        if actual_idx is not None and next_idx is not None:
            actual = safe_float(values[actual_idx])
            forecast = safe_float(values[next_idx])
            growth = safe_div(forecast - actual, actual) if actual not in (None, 0) else None
            if growth is not None:
                default["revenue_growth"] = growth
    outputs = msft_sheet.get("outputs", {})
    if safe_float(outputs.get("Shares")):
        default["shares"] = safe_float(outputs.get("Shares"))
    return default


def year_from_header(header: Any) -> int | None:
    text = str(header)
    for token in text.replace(",", " ").replace(".", " ").split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


def build_valuation_models(
    ratios: pd.DataFrame,
    balance: pd.DataFrame,
    comps: dict[str, dict[str, Any]],
    msft_sheet: dict[str, Any],
) -> dict[str, Any]:
    latest = latest_rows(ratios)
    shares_lookup = latest_share_lookup(balance)
    models = {}
    all_net_debt = [safe_float(value) for value in latest["Net Debt"].tolist()] if "Net Debt" in latest.columns else []
    all_net_debt = [value for value in all_net_debt if value is not None]
    net_debt_floor = min(all_net_debt + [-100_000])
    net_debt_ceiling = max(all_net_debt + [100_000])

    for _, row in latest.sort_values("Ticker Order").iterrows():
        ticker = row["Ticker"]
        comp = comps.get(ticker, {})
        shares = shares_lookup.get(ticker)
        market_equity = safe_float(comp.get("Equity"))
        current_price = safe_div(market_equity, shares) if market_equity is not None and shares else safe_float(row.get("Current Price"))
        base_revenue = safe_float(row.get("Revenue")) or 0
        default_growth = safe_float(row.get("Revenue Growth")) or 0.05
        default_margin = safe_float(row.get("EBITDA Margin")) or safe_div(row.get("EBITDA"), row.get("Revenue")) or 0.25
        default_multiple = safe_float(comp.get("EV/EBITDA")) or safe_float(row.get("EV / EBITDA")) or 15
        default_net_debt = safe_float(row.get("Net Debt")) or 0
        default_shares = shares or 1

        if ticker == "MSFT" and msft_sheet:
            msft_defaults = msft_valuation_default(msft_sheet, row)
            default_growth = msft_defaults.get("revenue_growth", default_growth)
            default_shares = msft_defaults.get("shares", default_shares)

        inputs = {
            "revenue_growth": default_growth,
            "ebitda_margin": default_margin,
            "exit_multiple": default_multiple,
            "net_debt": default_net_debt,
            "shares": default_shares,
        }
        models[ticker] = {
            "ticker": ticker,
            "display_ticker": row["Display Ticker"],
            "company": row["Company"],
            "base_year": int(row["Year"]),
            "base_revenue": base_revenue,
            "current_price": current_price,
            "inputs": inputs,
            "ranges": {
                "revenue_growth": {"min": -0.1, "max": 0.35, "step": 0.005},
                "ebitda_margin": {"min": 0.05, "max": 0.7, "step": 0.005},
                "exit_multiple": {"min": 5, "max": 45, "step": 0.25},
                "net_debt": {"min": net_debt_floor * 1.4, "max": net_debt_ceiling * 1.4, "step": 1000},
                "shares": {"min": default_shares * 0.5, "max": default_shares * 1.5, "step": 10},
            },
            "assumptions": {
                "wacc": safe_float(comp.get("WACC") or comp.get("Assumption WACC")),
                "cost_of_debt": safe_float(comp.get("Cost of Debt")),
                "cost_of_equity": safe_float(comp.get("Cost of Equity")),
                "tax_rate": safe_float(comp.get("Tax Rate")),
                "beta": safe_float(comp.get("Beta")),
                "rf": safe_float(comp.get("Rf")),
                "mrp": safe_float(comp.get("MRP")),
                "market_equity": market_equity,
                "debt": safe_float(comp.get("Debt")),
            },
        }
        models[ticker]["outputs"] = calculate_valuation(base_revenue, current_price, **inputs)
    return models


def calculate_valuation(
    base_revenue: float,
    current_price: float | None,
    revenue_growth: float,
    ebitda_margin: float,
    exit_multiple: float,
    net_debt: float,
    shares: float,
) -> dict[str, Any]:
    forecast_revenue = base_revenue * (1 + revenue_growth)
    forecast_ebitda = forecast_revenue * ebitda_margin
    enterprise_value = forecast_ebitda * exit_multiple
    equity_value = enterprise_value - net_debt
    implied_share_price = safe_div(equity_value, shares)
    upside_downside = None
    if implied_share_price is not None and current_price not in (None, 0):
        upside_downside = implied_share_price / current_price - 1
    return {
        "forecast_revenue": forecast_revenue,
        "forecast_ebitda": forecast_ebitda,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "implied_share_price": implied_share_price,
        "current_price": current_price,
        "upside_downside": upside_downside,
    }


def ranking_payload(ratios: pd.DataFrame) -> dict[str, Any]:
    latest = latest_rows(ratios)

    ranking_specs = [
        {
            "key": "profitability",
            "title": "Profitability",
            "metrics": [("Operating Margin", True), ("Net Profit Margin", True), ("ROA", True), ("ROE", True)],
            "note": "Higher margins and returns rank better.",
        },
        {
            "key": "capital_intensity",
            "title": "Capital Intensity Burden",
            "metrics": [("CapEx / Revenue", True), ("PPE / Assets", True), ("Asset Growth", True)],
            "note": "Higher scores indicate a heavier infrastructure load.",
        },
        {
            "key": "leverage_risk",
            "title": "Leverage Risk",
            "metrics": [("Debt / Equity", True), ("Current Ratio", False), ("Interest Coverage", False)],
            "note": "Higher scores indicate more balance-sheet pressure.",
        },
        {
            "key": "cash_flow",
            "title": "Cash Flow Strength",
            "metrics": [("Op Cash / Revenue", True), ("FCF Margin", True)],
            "note": "Higher cash conversion ranks better.",
        },
        {
            "key": "valuation",
            "title": "Valuation Attractiveness",
            "metrics": [("P/E", False), ("Price / Sales", False), ("EV / EBITDA", False)],
            "note": "Lower multiples rank as more attractive.",
        },
    ]

    rankings = []
    for spec in ranking_specs:
        scored = latest[["Ticker", "Display Ticker", "Company", "Ticker Order"]].copy()
        scores = []
        for metric, high_is_high_score in spec["metrics"]:
            if metric not in latest.columns:
                continue
            values = pd.to_numeric(latest[metric], errors="coerce")
            rank = values.rank(ascending=not high_is_high_score, method="min")
            scores.append(rank)
        if scores:
            scored["score"] = pd.concat(scores, axis=1).mean(axis=1)
            scored = scored.sort_values(["score", "Ticker Order"])
        else:
            scored["score"] = np.nan
        rankings.append(
            {
                "key": spec["key"],
                "title": spec["title"],
                "note": spec["note"],
                "items": [
                    {
                        "rank": idx + 1,
                        "ticker": row["Ticker"],
                        "display_ticker": row["Display Ticker"],
                        "company": row["Company"],
                        "score": safe_float(row["score"]),
                    }
                    for idx, (_, row) in enumerate(scored.iterrows())
                ],
            }
        )

    profit_leader = rankings[0]["items"][0] if rankings and rankings[0]["items"] else None
    burden_leader = rankings[1]["items"][0] if len(rankings) > 1 and rankings[1]["items"] else None
    risk_leader = rankings[2]["items"][0] if len(rankings) > 2 and rankings[2]["items"] else None

    conclusions = []
    if profit_leader:
        conclusions.append(
            {
                "question": "Who is capturing the gains?",
                "answer": f"{profit_leader['display_ticker']} ranks first on profitability conversion, making it the clearest current beneficiary of AI and cloud demand.",
            }
        )
    if burden_leader:
        conclusions.append(
            {
                "question": "Who is carrying the capital burden?",
                "answer": f"{burden_leader['display_ticker']} ranks as the heaviest capital-intensity case, with infrastructure spending absorbing more of the growth story.",
            }
        )
    if risk_leader:
        conclusions.append(
            {
                "question": "Where is financial risk building?",
                "answer": f"{risk_leader['display_ticker']} screens as the highest relative leverage-risk case, though the group remains far from a distressed balance-sheet profile.",
            }
        )

    rank_chart = {
        "id": "final-rank-chart",
        "title": "Category Rank Summary",
        "labels": [item["Display Ticker"] for item in latest.sort_values("Ticker Order").to_dict("records")],
        "datasets": [],
        "format": "rank",
        "direction": "Lower is Better",
        "color_by": "dataset",
    }
    for ranking in rankings:
        rank_by_ticker = {item["ticker"]: item["rank"] for item in ranking["items"]}
        rank_chart["datasets"].append(
            {
                "label": ranking["title"],
                "values": [rank_by_ticker.get(row["Ticker"]) for _, row in latest.sort_values("Ticker Order").iterrows()],
            }
        )

    return {"rankings": rankings, "conclusions": conclusions, "rank_chart": rank_chart}


def build_pages(
    ratios: pd.DataFrame,
    balance: pd.DataFrame,
    cash_flow: pd.DataFrame,
    comps: dict[str, dict[str, Any]],
    msft_valuation: dict[str, Any],
) -> dict[str, Any]:
    latest = latest_rows(ratios)

    pages: dict[str, Any] = {}
    pages["home"] = {
        "story_window": f"{int(ratios['Year'].min())}-{int(ratios['Year'].max())}",
        "cards": company_cards(latest, comps),
        "takeaways": home_takeaways(latest),
        "charts": [
            make_line_chart(ratios, "Revenue Growth", "Revenue Growth Trend"),
        ],
    }

    profitability_metrics = ["Operating Margin", "Net Profit Margin", "ROA", "ROE"]
    pages["profitability"] = {
        "line_charts": [make_line_chart(ratios, metric) for metric in profitability_metrics],
        "bar_charts": [make_latest_bar(ratios, "Operating Margin", "Latest Operating Margin")],
        "commentary": [
            metric_commentary(latest, "Operating Margin", True, "This is the cleanest view of core operating conversion."),
            metric_commentary(latest, "Net Profit Margin", True, "Net margin captures tax, interest, and below-the-line drag."),
            metric_commentary(latest, "ROA", True, "ROA matters because AI infrastructure increases the asset base."),
            metric_commentary(latest, "ROE", True, "ROE shows how strongly the equity base is being monetized."),
        ],
    }

    capital_metrics = ["CapEx / Revenue", "PPE / Assets", "Asset Growth"]
    pages["capital"] = {
        "line_charts": [make_line_chart(ratios, metric) for metric in capital_metrics],
        "bar_charts": [make_latest_bar(ratios, "CapEx / Revenue", "Latest Capex / Revenue")],
        "server_cards": capital_burden_chain(latest),
        "commentary": [
            metric_commentary(latest, "CapEx / Revenue", True, "A high ratio indicates that more revenue is being recycled into AI and data center capacity."),
            metric_commentary(latest, "PPE / Assets", True, "A higher fixed-asset mix makes the business more infrastructure-heavy."),
            metric_commentary(latest, "Asset Growth", True, "Rapid asset growth is a signal that balance sheets are expanding to support compute demand."),
        ],
    }

    leverage_metrics = ["Current Ratio", "Debt / Equity", "Interest Coverage"]
    pages["leverage"] = {
        "line_charts": [make_line_chart(ratios, metric) for metric in leverage_metrics],
        "bar_charts": [make_latest_bar(ratios, "Debt / Equity", "Latest Debt / Equity")],
        "heatmap": risk_heatmap(ratios),
        "commentary": [
            metric_commentary(latest, "Current Ratio", True, "Liquidity cushion matters if AI capex remains elevated."),
            metric_commentary(latest, "Debt / Equity", False, "Lower debt intensity preserves optionality during investment cycles."),
            metric_commentary(latest, "Interest Coverage", True, "Coverage shows whether earnings power comfortably absorbs financing costs."),
        ],
    }

    pages["cash_flow"] = {
        "line_charts": [
            make_line_chart(ratios, "Op Cash / Revenue", "Operating Cash Flow / Revenue"),
            make_line_chart(ratios, "FCF Margin", "Free Cash Flow Margin"),
        ],
        "bar_charts": [make_latest_bar(ratios, "FCF Margin", "Latest Free Cash Flow Margin")],
        "bridge_chart": build_bridge_chart(latest),
        "commentary": [
            metric_commentary(latest, "Op Cash / Revenue", True, "This is the source of internal funding capacity."),
            metric_commentary(latest, "FCF Margin", True, "Free cash flow margin is the residual after capex pressure hits."),
        ],
    }

    valuation_models = build_valuation_models(ratios, balance, comps, msft_valuation)
    multiples = build_multiples(ratios)
    pages["valuation"] = {
        "multiples": multiples,
        "multiple_charts": [
            make_latest_bar(ratios, "P/E", "Latest P/E"),
            make_latest_bar(ratios, "Price / Sales", "Latest Price / Sales"),
            make_latest_bar(ratios, "EV / EBITDA", "Latest EV / EBITDA"),
        ],
        "models": valuation_models,
        "initial_company": "MSFT" if "MSFT" in valuation_models else next(iter(valuation_models), None),
        "msft_valuation": msft_valuation,
        "formula": "Implied Share Price = (((Revenue x (1 + Revenue Growth)) x EBITDA Margin x Exit EV/EBITDA Multiple) - Net Debt) / Shares Outstanding",
    }

    pages["comparables"] = {
        "default_ticker": "MSFT",
        "default_compare_by": "none",
        "options": [
            {"value": "sic", "label": "SIC", "description": "Same SIC code"},
            {"value": "industry", "label": "Industry", "description": "Same industry group"},
            {"value": "sector", "label": "Sector", "description": "Same primary sector"},
            {"value": "all", "label": "All", "description": "SIC, industry, and sector all match"},
            {"value": "none", "label": "None", "description": "No categorical filter"},
        ],
        "pipeline_steps": [
            "Load Data/firms.parquet and normalize Exchange:Ticker to plain ticker symbols.",
            "Drop the first eight descriptor columns, then coerce the remaining columns to numeric fields.",
            "Replace missing values with feature medians, standardize each feature, and compute Euclidean distance.",
            "Filter by SIC, Industry, Sector, All, or None before ranking the top four matches.",
        ],
    }

    pages["insights"] = ranking_payload(ratios)
    return pages


def dashboard_workbook_signature() -> tuple[str, int, int]:
    workbook = find_workbook()
    stat = workbook.stat()
    return str(workbook), int(stat.st_mtime_ns), int(stat.st_size)


def load_dashboard_data() -> dict[str, Any]:
    return _load_dashboard_data_cached(*dashboard_workbook_signature())


@lru_cache(maxsize=4)
def _load_dashboard_data_cached(workbook_path: str, workbook_mtime_ns: int, workbook_size: int) -> dict[str, Any]:
    errors: list[str] = []
    workbook = Path(workbook_path)
    ratios_raw = read_standard_sheet(workbook, "Ratios")
    income_statement = read_standard_sheet(workbook, "Income Statement", required=False)
    balance = read_standard_sheet(workbook, "Balance Sheet")
    cash_flow = read_standard_sheet(workbook, "Cash Flow")
    comps = parse_comps(workbook, errors)
    msft_valuation = parse_msft_valuation(workbook, errors)
    ratios = add_derived_ratios(ratios_raw, income_statement, balance, cash_flow, comps)

    pages = build_pages(ratios, balance, cash_flow, comps, msft_valuation)
    data = {
        "workbook": str(workbook),
        "errors": errors,
        "companies": [
            {
                "ticker": row["Ticker"],
                "display_ticker": row["Display Ticker"],
                "company": row["Company"],
            }
            for _, row in latest_rows(ratios).sort_values("Ticker Order").iterrows()
        ],
        "years": sorted(ratios["Year"].dropna().astype(int).unique().tolist()),
        "pages": pages,
        "ratios_records": ratios.replace({np.nan: None}).to_dict("records"),
    }
    return sanitize(data)


load_dashboard_data.cache_clear = _load_dashboard_data_cached.cache_clear  # type: ignore[attr-defined]


def render_dashboard(page_key: str, template_name: str):
    try:
        data = load_dashboard_data()
        payload = data["pages"].get(page_key, {})
        errors = data.get("errors", [])
    except Exception as exc:
        payload = {"error": str(exc)}
        errors = [str(exc)]
    return render_template(
        template_name,
        page_key=page_key,
        meta=PAGE_META[page_key],
        nav_items=NAV_ITEMS,
        payload=payload,
        errors=errors,
    )


app = Flask(__name__)


@app.after_request
def prevent_dynamic_response_cache(response):
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type or "application/json" in content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.template_filter("pct")
def pct_filter(value: Any) -> str:
    return fmt_pct(value)


@app.template_filter("money_m")
def money_m_filter(value: Any) -> str:
    return fmt_money_m(value)


@app.template_filter("multiple")
def multiple_filter(value: Any) -> str:
    return fmt_x(value)


@app.template_filter("price")
def price_filter(value: Any) -> str:
    return fmt_price(value)


@app.template_filter("number")
def number_filter(value: Any) -> str:
    num = safe_float(value)
    return "n/a" if num is None else f"{num:,.0f}"


@app.route("/")
def index():
    return render_dashboard("home", "index.html")


@app.route("/profitability")
def profitability():
    return render_dashboard("profitability", "profitability.html")


@app.route("/capital-intensity")
def capital_intensity():
    return render_dashboard("capital", "capital_intensity.html")


@app.route("/leverage")
def leverage():
    return render_dashboard("leverage", "leverage.html")


@app.route("/cash-flow")
def cash_flow_page():
    return render_dashboard("cash_flow", "cash_flow.html")


@app.route("/valuation")
def valuation():
    return render_dashboard("valuation", "valuation.html")


@app.route("/comparables")
def comparables():
    return render_dashboard("comparables", "comparables.html")


@app.route("/insights")
def insights():
    return render_dashboard("insights", "insights.html")


@app.route("/api/health")
def health():
    data = load_dashboard_data()
    return jsonify({"status": "ok", "workbook": data["workbook"], "years": data["years"], "companies": data["companies"]})


@app.route("/api/page/<page_key>")
def page_data(page_key: str):
    data = load_dashboard_data()
    if page_key not in data["pages"]:
        return jsonify({"error": f"Unknown page: {page_key}"}), 404
    return jsonify(data["pages"][page_key])


@app.route("/api/valuation/calculate", methods=["POST"])
def valuation_calculate():
    data = load_dashboard_data()
    models = data["pages"]["valuation"]["models"]
    body = request.get_json(silent=True) or {}
    ticker = str(body.get("ticker", data["pages"]["valuation"]["initial_company"])).strip().upper()
    if ticker == "GOOGL" and "GOOG" in models:
        ticker = "GOOG"
    if ticker not in models:
        return jsonify({"error": f"Unknown company: {ticker}"}), 400

    model = models[ticker]
    defaults = model["inputs"]
    try:
        inputs = {
            "revenue_growth": float(body.get("revenue_growth", defaults["revenue_growth"])),
            "ebitda_margin": float(body.get("ebitda_margin", defaults["ebitda_margin"])),
            "exit_multiple": float(body.get("exit_multiple", defaults["exit_multiple"])),
            "net_debt": float(body.get("net_debt", defaults["net_debt"])),
            "shares": float(body.get("shares", defaults["shares"])),
        }
    except (TypeError, ValueError):
        return jsonify({"error": "Valuation inputs must be numeric."}), 400

    if inputs["shares"] == 0:
        return jsonify({"error": "Shares outstanding cannot be zero."}), 400

    outputs = calculate_valuation(
        base_revenue=float(model["base_revenue"]),
        current_price=model.get("current_price"),
        **inputs,
    )
    return jsonify(sanitize({"ticker": ticker, "display_ticker": model["display_ticker"], "inputs": inputs, "outputs": outputs}))


@app.route("/api/comparables")
def comparables_api():
    ticker = request.args.get("ticker", "MSFT")
    compare_by = request.args.get("compare_by", "none")
    try:
        result = find_comparable_companies(ticker=ticker, compare_by=compare_by, n_comps=4)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(start: int = 5000, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        if port_available(port):
            return port
    raise RuntimeError("No available local Flask port found.")


if __name__ == "__main__":
    port = choose_port()
    print(f"Dashboard running at http://127.0.0.1:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
