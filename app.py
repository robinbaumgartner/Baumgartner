import io
import json
import math
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Baumgartner Real Estate Intelligence", page_icon="🏢", layout="wide")

# -----------------------------
# Configuration
# -----------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
ECB_API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
BBK_API = "https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}"
EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"

SERIES = {
    "Fed Funds": {
        "kind": "fred",
        "id": "EFFR",
        "unit": "%",
        "source": "Federal Reserve / FRED",
        "url": "https://fred.stlouisfed.org/series/EFFR",
        "frequency": "täglich",
        "history_years": 10,
    },
    "US 10Y": {
        "kind": "fred",
        "id": "DGS10",
        "unit": "%",
        "source": "U.S. Treasury / FRED",
        "url": "https://fred.stlouisfed.org/series/DGS10",
        "frequency": "täglich",
        "history_years": 10,
    },
    "EZB Einlagenzins": {
        "kind": "ecb",
        "flow": "FM",
        "key": "D.U2.EUR.4F.KR.DFR.LEV",
        "unit": "%",
        "source": "EZB Data Portal",
        "url": "https://data.ecb.europa.eu/data/datasets/FM/FM.D.U2.EUR.4F.KR.DFR.LEV",
        "frequency": "bei Zinsänderungen / täglich fortgeschrieben",
        "history_years": 10,
    },
    "Bund 10Y": {
        "kind": "bbk",
        "flow": "BBSSY",
        "key": "D.REN.EUR.A630.000000WT1010.A",
        "unit": "%",
        "source": "Deutsche Bundesbank",
        "url": "https://www.bundesbank.de/de/statistiken/geld-und-kapitalmaerkte/zinssaetze-und-renditen/tageswerte-der-renditen-bundeswertpapiere-772218",
        "frequency": "täglich",
        "history_years": 10,
    },
    "Bauzins >10J": {
        "kind": "bbk",
        "flow": "BBIM1",
        "key": "M.DE.B.A2C.P.R.A.2250.EUR.N",
        "unit": "%",
        "source": "Deutsche Bundesbank",
        "url": "https://www.bundesbank.de/de/statistiken/geld-und-kapitalmaerkte/zinssaetze-und-renditen/wohnungsbaukredite-an-private-haushalte-hypothekarkredite-auf-wohngrundstuecke-615036",
        "frequency": "monatlich",
        "history_years": 20,
    },
    "Hauspreisindex DE": {
        "kind": "eurostat_hpi",
        "dataset": "prc_hpi_q",
        "unit": "Index",
        "source": "Eurostat (amtlicher Häuserpreisindex)",
        "url": "https://ec.europa.eu/eurostat/databrowser/view/prc_hpi_q/default/table",
        "frequency": "quartalsweise",
        "history_years": 20,
    },
}

# -----------------------------
# Helpers
# -----------------------------
HEADERS = {"User-Agent": "Baumgartner-Real-Estate-Intelligence/0.1"}


def _get(url, **kwargs):
    r = requests.get(url, timeout=25, headers=HEADERS, **kwargs)
    r.raise_for_status()
    return r


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred(series_id: str) -> pd.DataFrame:
    r = _get(FRED_CSV.format(series_id=series_id))
    df = pd.read_csv(io.StringIO(r.text))
    date_col = df.columns[0]
    value_col = df.columns[1]
    df = df.rename(columns={date_col: "date", value_col: "value"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().sort_values("date")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb(flow: str, key: str) -> pd.DataFrame:
    params = {
        "format": "csvdata",
        "detail": "dataonly",
        "startPeriod": (date.today() - timedelta(days=365 * 12)).isoformat(),
    }
    r = _get(ECB_API.format(flow=flow, key=key), params=params)
    df = pd.read_csv(io.StringIO(r.text))
    # ECB CSV normally exposes TIME_PERIOD + OBS_VALUE
    date_col = next((c for c in df.columns if c.upper() == "TIME_PERIOD"), None)
    value_col = next((c for c in df.columns if c.upper() == "OBS_VALUE"), None)
    if date_col is None or value_col is None:
        raise ValueError(f"ECB-Format unerwartet: {list(df.columns)[:12]}")
    out = df[[date_col, value_col]].rename(columns={date_col: "date", value_col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().sort_values("date")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_bbk(flow: str, key: str) -> pd.DataFrame:
    params = {
        "format": "sdmx_csv",
        "detail": "dataonly",
        "startPeriod": "2000-01-01" if key.startswith("D.") else "2000-01",
    }
    r = _get(BBK_API.format(flow=flow, key=key), params=params)
    df = pd.read_csv(io.StringIO(r.text))
    # Bundesbank SDMX-CSV uses TIME_PERIOD and OBS_VALUE.
    date_col = next((c for c in df.columns if c.upper() == "TIME_PERIOD"), None)
    value_col = next((c for c in df.columns if c.upper() == "OBS_VALUE"), None)
    if date_col is None or value_col is None:
        raise ValueError(f"Bundesbank-Format unerwartet: {list(df.columns)[:12]}")
    out = df[[date_col, value_col]].rename(columns={date_col: "date", value_col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().sort_values("date")


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_eurostat_hpi(dataset: str) -> pd.DataFrame:
    # Germany, total dwellings, index 2015=100 (quarterly). If Eurostat changes a code,
    # the error is shown in the dashboard instead of silently substituting another series.
    params = {"geo": "DE", "purchase": "TOTAL", "unit": "I15_Q", "lang": "en"}
    r = _get(EUROSTAT_API.format(dataset=dataset), params=params)
    payload = r.json()

    # Eurostat JSON-stat: decode time dimension positions to values.
    dim = payload.get("dimension", {})
    time_dim = dim.get("time", {})
    time_index = time_dim.get("category", {}).get("index", {})
    values = payload.get("value", {})
    if not time_index:
        raise ValueError("Eurostat-Antwort enthält keine Zeitdimension. Prüfe unit/purchase-Filter.")

    # With all non-time dimensions filtered to one value, flattened indexes map 1:1 to time slots.
    ordered_times = sorted(time_index.items(), key=lambda kv: kv[1])
    rows = []
    for t_label, pos in ordered_times:
        raw = values.get(str(pos), values.get(pos))
        if raw is not None:
            rows.append((t_label, raw))

    if not rows:
        raise ValueError("Eurostat lieferte keine HPI-Werte für Deutschland.")

    out = pd.DataFrame(rows, columns=["period", "value"])
    # Convert 2026-Q1 -> quarter-start timestamp
    out["date"] = pd.PeriodIndex(out["period"], freq="Q").to_timestamp()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out[["date", "value"]].dropna().sort_values("date")


def load_series(cfg: dict) -> pd.DataFrame:
    if cfg["kind"] == "fred":
        return fetch_fred(cfg["id"])
    if cfg["kind"] == "ecb":
        return fetch_ecb(cfg["flow"], cfg["key"])
    if cfg["kind"] == "bbk":
        return fetch_bbk(cfg["flow"], cfg["key"])
    if cfg["kind"] == "eurostat_hpi":
        return fetch_eurostat_hpi(cfg["dataset"])
    raise ValueError(f"Unbekannter Adapter: {cfg['kind']}")


def pct_change_nearest(df: pd.DataFrame, days: int):
    if len(df) < 2:
        return None
    latest_date = df.iloc[-1]["date"]
    target = latest_date - pd.Timedelta(days=days)
    prior = df[df["date"] <= target]
    if prior.empty:
        return None
    old = prior.iloc[-1]["value"]
    new = df.iloc[-1]["value"]
    if old == 0 or pd.isna(old) or pd.isna(new):
        return None
    return (new / old - 1) * 100


def pp_change_nearest(df: pd.DataFrame, days: int):
    if len(df) < 2:
        return None
    latest_date = df.iloc[-1]["date"]
    target = latest_date - pd.Timedelta(days=days)
    prior = df[df["date"] <= target]
    if prior.empty:
        return None
    return float(df.iloc[-1]["value"] - prior.iloc[-1]["value"])


def percentile_rank(df: pd.DataFrame, years=10):
    if df.empty:
        return None
    cutoff = df.iloc[-1]["date"] - pd.DateOffset(years=years)
    vals = df.loc[df["date"] >= cutoff, "value"].dropna()
    if vals.empty:
        return None
    current = vals.iloc[-1]
    return float((vals <= current).mean() * 100)


def fmt(v, unit):
    if v is None or pd.isna(v):
        return "–"
    if unit == "%":
        return f"{v:.2f} %"
    if unit == "Index":
        return f"{v:.1f}"
    return f"{v:.2f}"


# -----------------------------
# UI
# -----------------------------
st.title("Baumgartner Real Estate Intelligence")
st.caption("V0.1 · Globales Finanzierungsumfeld → deutscher Immobilienmarkt · Primärquellen soweit möglich")

with st.sidebar:
    st.header("Ansicht")
    chart_years = st.slider("Chart-Historie (Jahre)", 1, 20, 10)
    st.toggle("Datenquellen anzeigen", value=True, key="show_sources")
    if st.button("Daten neu laden"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Live bedeutet: zuletzt von der offiziellen Quelle veröffentlichter Wert. Monats- und Quartalsdaten sind naturgemäß nicht tagesaktuell.")

loaded = {}
errors = {}
with st.spinner("Offizielle Daten werden geladen …"):
    for name, cfg in SERIES.items():
        try:
            loaded[name] = load_series(cfg)
        except Exception as exc:
            errors[name] = str(exc)

# Top KPI cards
st.subheader("Kernindikatoren")
cols = st.columns(3)
for i, (name, cfg) in enumerate(SERIES.items()):
    with cols[i % 3]:
        if name in loaded and not loaded[name].empty:
            df = loaded[name]
            current = float(df.iloc[-1]["value"])
            latest_date = df.iloc[-1]["date"]
            if cfg["unit"] == "%":
                delta = pp_change_nearest(df, 365)
                delta_text = None if delta is None else f"{delta:+.2f} pp ggü. ~1J"
            else:
                delta = pct_change_nearest(df, 365)
                delta_text = None if delta is None else f"{delta:+.1f} % ggü. ~1J"
            st.metric(name, fmt(current, cfg["unit"]), delta_text)
            st.caption(f"Stand: {latest_date.date()} · {cfg['frequency']}")
        else:
            st.metric(name, "Keine Daten")
            st.caption("Quelle aktuell nicht abrufbar")

if errors:
    with st.expander(f"Datenstatus: {len(errors)} Quelle(n) mit Fehler", expanded=False):
        for name, err in errors.items():
            st.warning(f"**{name}:** {err}")

st.divider()

# Main charts
left, right = st.columns(2)
chart_groups = [
    (left, "Globaler Zinsanker", ["Fed Funds", "US 10Y"]),
    (right, "Euro / Deutschland", ["EZB Einlagenzins", "Bund 10Y", "Bauzins >10J"]),
]

for col, title, names in chart_groups:
    with col:
        st.subheader(title)
        frames = []
        for n in names:
            if n not in loaded:
                continue
            d = loaded[n].copy()
            cutoff = d.iloc[-1]["date"] - pd.DateOffset(years=chart_years)
            d = d[d["date"] >= cutoff]
            d["Serie"] = n
            frames.append(d)
        if frames:
            plot_df = pd.concat(frames, ignore_index=True)
            fig = px.line(plot_df, x="date", y="value", color="Serie", labels={"date": "", "value": "% p.a."})
            fig.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=10, b=10), height=360)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Noch keine Daten verfügbar.")

st.subheader("Deutscher Häuserpreisindex")
if "Hauspreisindex DE" in loaded:
    d = loaded["Hauspreisindex DE"].copy()
    cutoff = d.iloc[-1]["date"] - pd.DateOffset(years=chart_years)
    d = d[d["date"] >= cutoff]
    fig = px.line(d, x="date", y="value", labels={"date": "", "value": "Index (2015=100)"})
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320)
    st.plotly_chart(fig, width="stretch")
else:
    st.info("Hauspreisindex konnte nicht geladen werden; siehe Datenstatus.")

st.divider()
st.subheader("Historischer Kontext")
rows = []
for name, cfg in SERIES.items():
    if name not in loaded or loaded[name].empty:
        continue
    df = loaded[name]
    rows.append({
        "Kennzahl": name,
        "Aktuell": fmt(float(df.iloc[-1]["value"]), cfg["unit"]),
        "10J-Perzentil": f"{percentile_rank(df, 10):.0f} %" if percentile_rank(df, 10) is not None else "–",
        "Datenstand": str(df.iloc[-1]["date"].date()),
        "Frequenz": cfg["frequency"],
        "Quelle": cfg["source"],
    })
if rows:
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

if st.session_state.get("show_sources", True):
    st.subheader("Quellen")
    for name, cfg in SERIES.items():
        st.markdown(f"- **{name}:** [{cfg['source']}]({cfg['url']})")

st.caption("Hinweis: Dieses Dashboard ist ein Entscheidungs- und Analysewerkzeug, keine Anlage- oder Finanzierungsberatung. Daten können von den Primärquellen revidiert werden.")
