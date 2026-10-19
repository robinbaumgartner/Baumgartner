import io
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="Baumgartner Real Estate Intelligence", page_icon="🏢", layout="wide")

# ==============================================================
# Baumgartner Real Estate Intelligence — V0.2
# Architecture: Overview -> 5 analytical levels -> Decision Center
# ==============================================================

HEADERS = {"User-Agent": "Baumgartner-Real-Estate-Intelligence/0.2"}
NYFED_EFFR = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
TREASURY_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
ECB_API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
BBK_API = "https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}"
EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"

# Live sources already connected. Additional V1 metrics appear as planned metrics on each level.
SERIES = {
    "Fed Funds": {
        "kind": "nyfed_effr", "unit": "%", "source": "Federal Reserve Bank of New York",
        "url": "https://www.newyorkfed.org/markets/reference-rates/effr", "frequency": "täglich", "history_years": 10,
    },
    "US 10Y": {
        "kind": "treasury_10y", "unit": "%", "source": "U.S. Department of the Treasury",
        "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve",
        "frequency": "täglich", "history_years": 10,
    },
    "EZB Einlagenzins": {
        "kind": "ecb", "flow": "FM", "key": "D.U2.EUR.4F.KR.DFR.LEV", "unit": "%",
        "source": "EZB Data Portal", "url": "https://data.ecb.europa.eu/data/datasets/FM/FM.D.U2.EUR.4F.KR.DFR.LEV",
        "frequency": "bei Änderung / täglich fortgeschrieben", "history_years": 10,
    },
    "Bund 10Y": {
        "kind": "bbk", "flow": "BBSSY", "key": "D.REN.EUR.A630.000000WT1010.A", "unit": "%",
        "source": "Deutsche Bundesbank", "url": "https://www.bundesbank.de/de/statistiken/geld-und-kapitalmaerkte/zinssaetze-und-renditen/tageswerte-der-renditen-bundeswertpapiere-772218",
        "frequency": "täglich", "history_years": 10,
    },
    "Bauzins >10J": {
        "kind": "bbk", "flow": "BBIM1", "key": "M.DE.B.A2C.P.R.A.2250.EUR.N", "unit": "%",
        "source": "Deutsche Bundesbank", "url": "https://www.bundesbank.de/de/statistiken/geld-und-kapitalmaerkte/zinssaetze-und-renditen/wohnungsbaukredite-an-private-haushalte-hypothekarkredite-auf-wohngrundstuecke-615036",
        "frequency": "monatlich", "history_years": 20,
    },
    "Hauspreisindex DE": {
        "kind": "eurostat_hpi", "dataset": "prc_hpi_q", "unit": "Index",
        "source": "Eurostat", "url": "https://ec.europa.eu/eurostat/databrowser/view/prc_hpi_q/default/table",
        "frequency": "quartalsweise", "history_years": 20,
    },
}

LEVELS = {
    "1 · USA / Global": {
        "question": "Wird globales Kapital gerade billiger oder teurer – und steigt oder sinkt der Risikoappetit?",
        "live": ["Fed Funds", "US 10Y"],
        "metrics": [
            ("Fed Funds Rate", "Wie stark bremst oder stimuliert die US-Notenbank?", "Hoher/steigender Zins = Kapital bleibt teuer."),
            ("US 2Y Treasury", "Was erwartet der Markt für die Fed in den nächsten Jahren?", "Steigend = Markt erwartet länger hohe Leitzinsen."),
            ("US 10Y Treasury", "Globaler Referenzzins für langfristiges Kapital.", "Steigend = Druck auf langfristige Finanzierung weltweit."),
            ("2Y–10Y Zinskurve", "Wie sieht der Markt Wachstum und Geldpolitik?", "Starke Inversion kann auf restriktive Bedingungen hindeuten."),
            ("Core PCE", "Kerninflation, auf die die Fed besonders achtet.", "Hartnäckig hoch = weniger Raum für Zinssenkungen."),
            ("US Arbeitsmarkt", "Kann die Fed lockern, ohne Inflation neu anzufachen?", "Schwächerer Arbeitsmarkt = tendenziell mehr Lockerungsspielraum."),
            ("EUR/USD / Dollar", "Wie stark ist der Dollar gegenüber Europa?", "Sehr starker Dollar kann importierte Inflation in Europa erhöhen."),
            ("Credit Spreads", "Wie nervös sind Kreditmärkte?", "Steigend = Risiko wird teurer, Kapital vorsichtiger."),
        ],
        "forecasts": ["Fed Summary of Economic Projections", "Fed Dot Plot", "IMF World Economic Outlook", "OECD Economic Outlook"],
        "risks": ["US-Fiskalpolitik / hohe Treasury-Emissionen", "USA–China-Handelskonflikte", "Nahost / Ölpreis", "Taiwan / Lieferketten"],
        "transmission": "Globales Zins- und Risikoumfeld → beeinflusst europäische Langfristzinsen, EUR/USD und Risikoaufschläge.",
    },
    "2 · Eurozone / EZB": {
        "question": "Wie wirken globale Bedingungen und EZB-Politik direkt auf europäische Finanzierung?",
        "live": ["EZB Einlagenzins", "Bund 10Y"],
        "metrics": [
            ("EZB-Einlagenzins", "Offizieller Kernzins der Euro-Geldpolitik.", "Hoch = kurzfristiges Geld bleibt teuer."),
            ("€STR", "Tatsächlicher kurzfristiger Euro-Geldmarktzins.", "Zeigt, was Banken sehr kurzfristig tatsächlich zahlen."),
            ("€STR Forward Curve", "Was erwartet der Markt für künftige EZB-Zinsen?", "Fallend = Markt rechnet mit Lockerung."),
            ("HICP Inflation", "Gesamtinflation im Euroraum.", "Über Ziel = EZB kann weniger aggressiv lockern."),
            ("Kerninflation", "Inflation ohne stark schwankende Komponenten.", "Hartnäckig hoch = struktureller Preisdruck."),
            ("Bund 2Y", "Kurzfristige deutsche Zinserwartung.", "Reagiert stark auf EZB-Erwartungen."),
            ("Bund 10Y", "Wichtiger Anker für deutsche Langfristfinanzierung.", "Steigend = Druck auf Bau- und Unternehmenszinsen."),
            ("ECB Bank Lending Survey", "Werden Banken lockerer oder strenger?", "Strenger = Kredit wird trotz gleichem Zins schwerer verfügbar."),
        ],
        "forecasts": ["ECB Staff Macroeconomic Projections", "Europäische Kommission Economic Forecast", "IMF Euro Area Forecast"],
        "risks": ["Russland/Ukraine → Energie", "Nahost → Energie & Transport", "USA–EU-Handel", "China-Nachfrage für Europa"],
        "transmission": "EZB + Bundrenditen + Bankenverhalten → bestimmen Finanzierungskosten und Kreditverfügbarkeit in Deutschland.",
    },
    "3 · Deutschland Makro": {
        "question": "Haben deutsche Haushalte genug Einkommen, Arbeitsplatzsicherheit und Vertrauen für große Immobilienentscheidungen?",
        "live": [],
        "metrics": [
            ("Reales BIP", "Wächst oder schrumpft die Wirtschaft?", "Schwach = geringere Dynamik, aber nicht automatisch schwache Immobiliennachfrage."),
            ("Arbeitslosenquote", "Wie sicher fühlen sich Haushalte beim Einkommen?", "Steigend = Käufer werden vorsichtiger."),
            ("Beschäftigung", "Wie viele Menschen sind tatsächlich in Arbeit?", "Stabil = wichtige Stütze für Wohnen und Kredite."),
            ("Reallöhne", "Steigt Einkommen schneller als Preise?", "Steigend = reale Kaufkraft verbessert sich."),
            ("Verfügbares Einkommen", "Was bleibt Haushalten wirklich zum Konsumieren/Sparen?", "Steigend = bessere Finanzierbarkeit."),
            ("Inflation / Kerninflation", "Wie stark steigen Lebenshaltungskosten?", "Hoch = belastet Kaufkraft und Zinsen."),
            ("ifo Geschäftsklima", "Wie sehen Unternehmen die nächsten Monate?", "Frühindikator für Investitionen und Beschäftigung."),
            ("Konsumklima", "Wie kaufbereit sind Haushalte?", "Schwach = größere Anschaffungen werden verschoben."),
            ("Unternehmensinsolvenzen", "Wie viel Stress gibt es in der Wirtschaft?", "Steigend = Risiko für Jobs und regionale Nachfrage."),
            ("Industrie / Auftragseingänge", "Besonders wichtig für Süddeutschland.", "Schwach = Risiko für export- und industrieabhängige Regionen."),
        ],
        "forecasts": ["Bundesbank-Prognose", "Sachverständigenrat", "Bundesregierung", "ifo", "IMF / OECD Deutschland"],
        "risks": ["Energiepreise", "Auto-/Industrieschwäche", "China-/Exportabhängigkeit", "Fiskal- und Infrastrukturpolitik"],
        "transmission": "Einkommen + Jobs + Vertrauen → bestimmen, ob Haushalte Immobilien tatsächlich kaufen oder mieten können und wollen.",
    },
    "4 · Finanzierung / Kreditmarkt": {
        "question": "Wie teuer und wie verfügbar ist Geld für Käufer und Projektentwickler?",
        "live": ["Bund 10Y", "Bauzins >10J"],
        "metrics": [
            ("Bauzins 5J", "Kurzere Zinsbindung.", "Zeigt Preis für eher flexible Finanzierung."),
            ("Bauzins 10J", "Standardanker für private Käufer.", "Steigend = gleiche Rate finanziert weniger Kaufpreis."),
            ("Bauzins 15/20J", "Preis langfristiger Sicherheit.", "Großer Aufschlag = langfristiges Zinsrisiko wird teuer bewertet."),
            ("Wohnungsbau-Kreditneugeschäft", "Wie viele neue Kredite werden wirklich abgeschlossen?", "Steigend = Käufer kehren tatsächlich zurück."),
            ("Kreditstandards", "Wie streng prüfen Banken?", "Verschärfung = mehr Eigenkapital / weniger Zusagen."),
            ("Kreditnachfrage", "Wollen Haushalte überhaupt neue Kredite?", "Steigend = bessere Nachfragebasis."),
            ("Pfandbrief-Renditen", "Refinanzierungskosten deutscher Banken.", "Steigend = Bauzinsen können hoch bleiben."),
            ("Spread Bauzins – Bund 10Y", "Wie viel Aufschlag verlangt die Bank über dem Kapitalmarkt?", "Steigend = Bankmargen/Risikoaufschläge nehmen zu."),
            ("CRE / Developer Lending", "Konditionen für Projektentwickler.", "Strenger = Projekte brauchen mehr Eigenkapital und Vorverkauf."),
        ],
        "forecasts": ["ECB/Deutsche Bank Lending Surveys", "Bundesbank Finanzstabilitätsbericht", "EZB Financial Stability Review"],
        "risks": ["Finanzmarktstress", "Bankenverluste / CRE-Risiken", "plötzlicher Inflationsschub", "starke Bund-/Treasury-Renditebewegungen"],
        "transmission": "Finanzierungskosten + Kreditverfügbarkeit → bestimmen Käuferbudget, Vorverkaufsgeschwindigkeit und deine eigene Projektfinanzierung.",
    },
    "5 · Immobilienmarkt Deutschland": {
        "question": "Was passiert tatsächlich mit Preisen, Transaktionen, Angebot, Mieten und Baukosten?",
        "live": ["Hauspreisindex DE"],
        "metrics": [
            ("Wohnimmobilienpreisindex", "Was passiert mit den tatsächlichen Wohnpreisen?", "Steigend + mehr Transaktionen = robuster als Preissteigerung allein."),
            ("Neubaupreisindex", "Wie entwickelt sich speziell Neubau?", "Für Developer direkter als Gesamtmarkt."),
            ("Bestandspreise", "Wie attraktiv ist Neubau relativ zum Bestand?", "Großer Neubauaufschlag kann Absatz bremsen."),
            ("Transaktionszahl", "Wie viele Käufe finden wirklich statt?", "Steigend = Nachfrage wird real, nicht nur theoretisch."),
            ("Transaktionsvolumen", "Wie viel Kapital fließt in Immobilien?", "Steigend = Liquidität des Marktes nimmt zu."),
            ("Baugenehmigungen", "Wie viel zukünftiges Angebot wird vorbereitet?", "Fallend = potenziell weniger Konkurrenz später."),
            ("Baufertigstellungen", "Wie viel neues Angebot kommt tatsächlich auf den Markt?", "Niedrig = Angebotsknappheit kann zunehmen."),
            ("Bauüberhang", "Wie viele genehmigte Wohnungen wurden noch nicht gebaut?", "Hoch = Pipeline kann später wieder Angebot erzeugen."),
            ("Baukostenindex", "Wie schnell steigen deine Herstellungskosten?", "Schneller als Verkaufspreise = Margendruck."),
            ("Neu-/Angebotsmieten", "Wie stark ist Mietnachfrage?", "Steigend = Halten wird relativ attraktiver."),
        ],
        "forecasts": ["BBSR Wohnungsmarktprognosen", "Bundesbank Immobilienanalysen", "ifo Baukonjunktur", "ausgewählte CBRE/JLL/Savills Marktberichte"],
        "risks": ["Baukosten-/Materialschock", "Regulatorische Änderungen", "Förderpolitik", "starker Nachfragerückgang", "regionale Überangebote"],
        "transmission": "Preise + Nachfrage + Angebot + Kosten → bestimmen deine reale Projektmarge und ob Verkaufen oder Halten attraktiver ist.",
    },
}

# -----------------------------
# Data helpers
# -----------------------------
def _get(url, **kwargs):
    last_exc = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=45, headers=HEADERS, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nyfed_effr(history_years=10):
    end = date.today(); start = end - timedelta(days=366 * history_years)
    payload = _get(NYFED_EFFR, params={"startDate": start.isoformat(), "endDate": end.isoformat(), "type": "rate"}).json()
    rows = payload.get("refRates", [])
    if not rows: raise ValueError("NY Fed lieferte keine EFFR-Beobachtungen.")
    out = pd.DataFrame(rows)[["effectiveDate", "percentRate"]].rename(columns={"effectiveDate":"date","percentRate":"value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce"); out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().drop_duplicates("date").sort_values("date")

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_treasury_10y(history_years=10):
    rows=[]; current_year=date.today().year
    for year in range(current_year-history_years, current_year+1):
        r=_get(TREASURY_XML, params={"data":"daily_treasury_yield_curve","field_tdr_date_value":str(year)})
        root=ET.fromstring(r.content)
        for entry in root.iter():
            if entry.tag.rsplit("}",1)[-1] != "entry": continue
            fields={node.tag.rsplit("}",1)[-1]:node.text for node in entry.iter()}
            if fields.get("NEW_DATE") and fields.get("BC_10YEAR") not in (None,""):
                rows.append((fields["NEW_DATE"][:10], fields["BC_10YEAR"]))
    if not rows: raise ValueError("U.S. Treasury lieferte keine 10Y-Beobachtungen.")
    out=pd.DataFrame(rows,columns=["date","value"]); out["date"]=pd.to_datetime(out["date"],errors="coerce"); out["value"]=pd.to_numeric(out["value"],errors="coerce")
    return out.dropna().drop_duplicates("date").sort_values("date")

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb(flow,key):
    r=_get(ECB_API.format(flow=flow,key=key),params={"format":"csvdata","detail":"dataonly","startPeriod":(date.today()-timedelta(days=365*12)).isoformat()})
    df=pd.read_csv(io.StringIO(r.text)); dc=next((c for c in df.columns if c.upper()=="TIME_PERIOD"),None); vc=next((c for c in df.columns if c.upper()=="OBS_VALUE"),None)
    if dc is None or vc is None: raise ValueError("ECB-Format unerwartet")
    out=df[[dc,vc]].rename(columns={dc:"date",vc:"value"}); out["date"]=pd.to_datetime(out["date"],errors="coerce"); out["value"]=pd.to_numeric(out["value"],errors="coerce")
    return out.dropna().sort_values("date")

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_bbk(flow,key):
    r=_get(BBK_API.format(flow=flow,key=key),params={"format":"sdmx_csv","detail":"dataonly","startPeriod":"2000-01-01" if key.startswith("D.") else "2000-01"})
    df=pd.read_csv(io.StringIO(r.text),sep=None,engine="python"); dc=next((c for c in df.columns if c.upper()=="TIME_PERIOD"),None); vc=next((c for c in df.columns if c.upper()=="OBS_VALUE"),None)
    if dc is None or vc is None: raise ValueError("Bundesbank-Format unerwartet")
    out=df[[dc,vc]].rename(columns={dc:"date",vc:"value"}); out["date"]=pd.to_datetime(out["date"],errors="coerce"); out["value"]=pd.to_numeric(out["value"],errors="coerce")
    return out.dropna().sort_values("date")

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_eurostat_hpi(dataset):
    payload=_get(EUROSTAT_API.format(dataset=dataset),params={"geo":"DE","purchase":"TOTAL","unit":"I15_Q","lang":"en"}).json()
    time_index=payload.get("dimension",{}).get("time",{}).get("category",{}).get("index",{}); values=payload.get("value",{})
    rows=[]
    for label,pos in sorted(time_index.items(),key=lambda kv:kv[1]):
        raw=values.get(str(pos),values.get(pos))
        if raw is not None: rows.append((label,raw))
    if not rows: raise ValueError("Eurostat lieferte keine HPI-Werte")
    out=pd.DataFrame(rows,columns=["period","value"]); out["date"]=pd.PeriodIndex(out["period"],freq="Q").to_timestamp(); out["value"]=pd.to_numeric(out["value"],errors="coerce")
    return out[["date","value"]].dropna().sort_values("date")

def load_series(cfg):
    return {
        "nyfed_effr": lambda: fetch_nyfed_effr(cfg.get("history_years",10)),
        "treasury_10y": lambda: fetch_treasury_10y(cfg.get("history_years",10)),
        "ecb": lambda: fetch_ecb(cfg["flow"],cfg["key"]),
        "bbk": lambda: fetch_bbk(cfg["flow"],cfg["key"]),
        "eurostat_hpi": lambda: fetch_eurostat_hpi(cfg["dataset"]),
    }[cfg["kind"]]()

def fmt(v,unit):
    if v is None or pd.isna(v): return "–"
    return f"{v:.2f} %" if unit=="%" else (f"{v:.1f}" if unit=="Index" else f"{v:.2f}")

def pp_change(df,days=365):
    if len(df)<2:return None
    target=df.iloc[-1]["date"]-pd.Timedelta(days=days); prior=df[df["date"]<=target]
    return None if prior.empty else float(df.iloc[-1]["value"]-prior.iloc[-1]["value"])

def pct_change(df,days=365):
    if len(df)<2:return None
    target=df.iloc[-1]["date"]-pd.Timedelta(days=days); prior=df[df["date"]<=target]
    if prior.empty or prior.iloc[-1]["value"]==0:return None
    return float((df.iloc[-1]["value"]/prior.iloc[-1]["value"]-1)*100)

def historical_percentile(df, years=10):
    if df.empty:return None
    cutoff=df.iloc[-1]["date"]-pd.DateOffset(years=years); vals=df[df["date"]>=cutoff]["value"].dropna()
    if vals.empty:return None
    return float((vals<=vals.iloc[-1]).mean()*100)

# -----------------------------
# Interpretation helpers (transparent rule-based interim engine)
# -----------------------------
def signal_from_percentile(p, inverted=False):
    if p is None:return ("⚪","Noch keine belastbare Einordnung")
    # for rates/costs: high percentile is restrictive; inverted can be used for positive metrics later
    if inverted:
        if p>=70:return ("🟢","unterstützend")
        if p<=30:return ("🔴","belastend")
    else:
        if p>=70:return ("🔴","restriktiv / teuer")
        if p<=30:return ("🟢","locker / günstig")
    return ("🟡","neutral / gemischt")

def level_assessment(level_name, loaded):
    if level_name.startswith("1"):
        p=historical_percentile(loaded.get("US 10Y",pd.DataFrame()),10) if "US 10Y" in loaded else None
        icon,label=signal_from_percentile(p)
        body="Langfristige US-Renditen sind der wichtigste globale Zinsanker in dieser ersten Version. Je höher sie historisch stehen, desto größer ist der Druck auf weltweite Finanzierungskosten."
        return icon,label,body
    if level_name.startswith("2"):
        p=historical_percentile(loaded.get("Bund 10Y",pd.DataFrame()),10) if "Bund 10Y" in loaded else None
        icon,label=signal_from_percentile(p)
        body="Für Deutschland zählt nicht nur der EZB-Leitzins, sondern vor allem, was am langen Ende der Zinskurve passiert. Eine hohe Bundrendite kann Bauzinsen trotz EZB-Lockerung hoch halten."
        return icon,label,body
    if level_name.startswith("3"):
        return "⚪","noch unvollständig","Diese Ebene wird belastbar, sobald BIP, Arbeitsmarkt, Reallöhne, Inflation und Vertrauensindikatoren live angebunden sind."
    if level_name.startswith("4"):
        p=historical_percentile(loaded.get("Bauzins >10J",pd.DataFrame()),10) if "Bauzins >10J" in loaded else None
        icon,label=signal_from_percentile(p)
        body="Der Bauzins zeigt direkt, wie viel Kaufpreis sich private Käufer bei gleicher Monatsrate leisten können. Gleichzeitig ist er ein guter Indikator für dein Absatzrisiko."
        return icon,label,body
    if level_name.startswith("5"):
        return "🟡","noch teilweise angebunden","Der Häuserpreisindex zeigt nur die Preisrichtung. Für eine echte Marktbeurteilung brauchen wir zusätzlich Transaktionen, Neubaupreise, Genehmigungen, Fertigstellungen, Mieten und Baukosten."
    return "⚪","offen",""

def business_impact(level_name):
    mapping={
        "1":"Hohe globale Renditen können deutsche Langfristzinsen hoch halten. Das erschwert Käuferfinanzierung und kann zugleich schwächere Wettbewerber aus dem Markt drängen.",
        "2":"EZB, Bundrenditen und Bankenverhalten bestimmen, ob sich Finanzierung in Deutschland tatsächlich entspannt. Für dich sind sinkende Langfristzinsen wichtiger als eine reine EZB-Senkung.",
        "3":"Stabile Jobs und steigende Reallöhne stützen Käufer und Mieter. Schwache Stimmung kann Transaktionen trotzdem bremsen – selbst wenn die Haushalte finanziell noch könnten.",
        "4":"Diese Ebene trifft dein Geschäft direkt: Bauzins und Kreditstandards beeinflussen Vorverkauf, Käuferbudget, Eigenkapitalbedarf und deine Projektfinanzierung.",
        "5":"Hier zeigt sich das Endergebnis: Wenn Nachfrage zurückkommt, während Neubau knapp bleibt und Kosten beherrschbar sind, verbessert sich deine Developer-Marge.",
    }
    return mapping.get(level_name[0],"")

# -----------------------------
# Load data once
# -----------------------------
loaded={}; errors={}
with st.spinner("Offizielle Daten werden geladen …"):
    for name,cfg in SERIES.items():
        try: loaded[name]=load_series(cfg)
        except Exception as exc: errors[name]=str(exc)

# -----------------------------
# Sidebar / navigation
# -----------------------------
st.sidebar.title("Baumgartner REI")
page=st.sidebar.radio("Navigation", ["Overview"]+list(LEVELS.keys())+["Decision Center"], index=0)
chart_years=st.sidebar.slider("Chart-Historie",1,20,10)
if st.sidebar.button("Daten neu laden"):
    st.cache_data.clear(); st.rerun()
st.sidebar.divider()
st.sidebar.caption("Blau = harte Daten · Gelb = Markterwartung · Violett = institutionelle Prognose · Rot = Risikoszenario")

# -----------------------------
# UI helpers
# -----------------------------
def kpi_card(name):
    cfg=SERIES[name]
    if name not in loaded or loaded[name].empty:
        st.metric(name,"Keine Daten"); st.caption("Quelle aktuell nicht abrufbar"); return
    df=loaded[name]; current=float(df.iloc[-1]["value"])
    if cfg["unit"]=="%":
        d=pp_change(df,365); delta=None if d is None else f"{d:+.2f} pp ggü. ~1J"
    else:
        d=pct_change(df,365); delta=None if d is None else f"{d:+.1f} % ggü. ~1J"
    st.metric(name,fmt(current,cfg["unit"]),delta)
    st.caption(f"Stand {df.iloc[-1]['date'].date()} · {cfg['source']}")

def chart_for(names,title):
    frames=[]
    for n in names:
        if n not in loaded or loaded[n].empty: continue
        d=loaded[n].copy(); d=d[d["date"]>=d.iloc[-1]["date"]-pd.DateOffset(years=chart_years)]; d["Serie"]=n; frames.append(d)
    if not frames:
        st.info("Für diesen Chart sind noch keine Live-Daten verfügbar."); return
    plot_df=pd.concat(frames,ignore_index=True)
    fig=px.line(plot_df,x="date",y="value",color="Serie",labels={"date":"","value":"Wert"})
    fig.update_layout(legend_title_text="",height=340,margin=dict(l=10,r=10,t=20,b=10))
    st.plotly_chart(fig,width="stretch")

def metric_explainers(level):
    for metric,why,signal in level["metrics"]:
        with st.expander(metric, expanded=False):
            st.markdown(f"**Was ist das?** {why}")
            st.markdown(f"**Warum wichtig?** {signal}")

def forecast_box(level):
    c1,c2=st.columns(2)
    with c1:
        st.markdown("### 🟪 Institutionelle Prognosen")
        st.caption("Was erwarten offizielle Institutionen für die Zukunft?")
        for x in level["forecasts"]: st.markdown(f"- {x}")
        st.info("Die konkreten Forecast-Werte und Revisionen werden in der nächsten Datenrunde live angebunden.")
    with c2:
        st.markdown("### 🟥 Geopolitik & externe Risiken")
        st.caption("Nur Risiken mit nachvollziehbarem wirtschaftlichem Übertragungskanal.")
        for x in level["risks"]: st.markdown(f"- {x}")

def assessment_box(level_name,level):
    icon,label,body=level_assessment(level_name,loaded)
    st.markdown("### Ebenen-Einschätzung")
    c1,c2=st.columns([1,3])
    with c1:
        st.markdown(f"## {icon} {label}")
    with c2:
        st.write(body)
    st.markdown("**Einfluss auf die nächste Ebene**")
    st.info(level["transmission"])
    st.markdown("**Direkter Einfluss auf dein Business**")
    st.success(business_impact(level_name))
    st.caption("Aktuell regelbasiert und transparent. Später kann hier zusätzlich eine echte KI-Zusammenfassung über API laufen.")

# -----------------------------
# Overview
# -----------------------------
if page=="Overview":
    st.title("Baumgartner Real Estate Intelligence")
    st.caption("Vom globalen Kapitalmarkt bis zur konkreten Developer-Entscheidung")

    st.markdown("## Marktbild auf einen Blick")
    cols=st.columns(5)
    for i,lname in enumerate(LEVELS):
        icon,label,_=level_assessment(lname,loaded)
        with cols[i]:
            st.markdown(f"**{lname.split('·',1)[1].strip()}**")
            st.markdown(f"### {icon}")
            st.caption(label)

    st.divider()
    st.markdown("## Kausalkette")
    st.markdown("**USA / Global** → **Eurozone / EZB** → **Deutschland Makro** → **Finanzierung** → **Immobilienmarkt** → **deine Projektentscheidung**")
    st.caption("Die App soll nicht nur Werte zeigen, sondern erklären, wie ein Signal in die nächste Ebene weitergereicht wird.")

    c1,c2,c3=st.columns(3)
    with c1:kpi_card("US 10Y")
    with c2:kpi_card("Bund 10Y")
    with c3:kpi_card("Bauzins >10J")

    st.markdown("## Gesamtinterpretation")
    global_sig=level_assessment("1 · USA / Global",loaded)
    euro_sig=level_assessment("2 · Eurozone / EZB",loaded)
    fin_sig=level_assessment("4 · Finanzierung / Kreditmarkt",loaded)
    st.info(f"**Aktueller Prototyp:** Global {global_sig[0]} {global_sig[1]}, Eurozone {euro_sig[0]} {euro_sig[1]}, Finanzierung {fin_sig[0]} {fin_sig[1]}. Für ein belastbares finales Marktregime fehlen noch Deutschland-Makro und die vollständige Immobilienmarktseite.")

    st.markdown("### Was würde die Einschätzung verändern?")
    st.markdown("- **Positiver:** fallende US-/Bund-Langfristzinsen, lockerere Kreditstandards, steigendes Kreditneugeschäft und Transaktionen bei weiter knappem Neubauangebot.\n- **Negativer:** erneuter Inflationsschub, deutlich steigende Arbeitslosigkeit, verschärfte Kreditstandards oder Baukosten, die stärker als Verkaufspreise steigen.")

    if errors:
        with st.expander(f"Datenstatus: {len(errors)} Quelle(n) mit Fehler"):
            for n,e in errors.items(): st.warning(f"**{n}:** {e}")

# -----------------------------
# Level pages
# -----------------------------
elif page in LEVELS:
    level=LEVELS[page]
    st.title(page)
    st.markdown(f"### Leitfrage: {level['question']}")

    st.markdown("## 🟦 1. Harte Daten")
    if level["live"]:
        cols=st.columns(min(3,len(level["live"])))
        for i,n in enumerate(level["live"]):
            with cols[i%len(cols)]: kpi_card(n)
        chart_for(level["live"],page)
    else:
        st.info("Die Kennzahlen dieser Ebene sind strukturell definiert, aber noch nicht live angebunden.")

    st.markdown("### Welche Zahlen gehören hierher – und warum?")
    metric_explainers(level)

    st.markdown("## 🟨 2. Markterwartungen")
    st.info("Hier erscheinen künftig Forward Curves, Marktpreise und Erwartungen, die zeigen, was Investoren bereits für die Zukunft einpreisen. Diese Erwartungen werden bewusst getrennt von harten Ist-Daten dargestellt.")

    st.markdown("## 3. Prognosen & Risiken")
    forecast_box(level)

    st.markdown("## 4. Interpretation & Business-Impact")
    assessment_box(page,level)

    st.markdown("### Worauf jetzt achten?")
    st.caption("Diese Beobachtungspunkte werden später automatisch aus den Kennzahlen mit dem größten Einfluss auf die aktuelle These ausgewählt.")

# -----------------------------
# Decision center
# -----------------------------
else:
    st.title("Decision Center")
    st.caption("Die fünf Ebenen werden hier nicht gemittelt, sondern kausal miteinander verknüpft.")

    st.markdown("## Signal-Kette")
    for lname,level in LEVELS.items():
        icon,label,_=level_assessment(lname,loaded)
        st.markdown(f"**{lname}** → {icon} {label}")
        st.caption(level["transmission"])

    st.divider()
    st.markdown("## Finales Business-Signal")
    st.warning("Noch **vorläufig**, weil Deutschland-Makro, Kreditvolumen/Kreditstandards sowie Neubauangebot/Baukosten noch nicht vollständig live angebunden sind.")
    st.markdown("### Vorläufige Konsequenz für dein Modell")
    st.write("Solange langfristige Finanzierung teuer bleibt, sollte ein Neubauprojekt nicht auf zukünftige Zinssenkungen angewiesen sein. Attraktiv werden Projekte vor allem dann, wenn Verkaufspreise konservativ funktionieren, Baukosten beherrscht werden und der Vorverkauf ausreichend Nachfrage bestätigt. Ein langfristiger Bestand ist selektiver zu prüfen, wenn Mietrendite und Fremdkapitalkosten eng beieinanderliegen.")

    c1,c2=st.columns(2)
    with c1:
        st.markdown("### Chancen")
        st.markdown("- weniger Neubaukonkurrenz bei hoher Finanzierungshürde\n- mögliche Verkäufer-/Developer-Stresssituationen\n- steigende Preissetzungsmacht, wenn Nachfrage zurückkehrt bevor Angebot nachzieht\n- günstige Grundstücksbasis kann überproportional wertvoll werden")
    with c2:
        st.markdown("### Risiken")
        st.markdown("- Käuferbudget sinkt bei hohen Bauzinsen\n- Baukosten können Margen schneller auffressen als Preise steigen\n- strengere Kreditstandards erhöhen Eigenkapitalbedarf\n- schwacher Arbeitsmarkt kann Transaktionen trotz Wohnraummangel bremsen")

    st.markdown("### Konkrete Handlungslogik")
    st.markdown("1. **Verkaufen/entwickeln:** nur wenn das Projekt bereits mit konservativen Preisen trägt.\n2. **Vorverkauf:** als echter Nachfragetest nutzen, nicht nur als Finanzierungsschritt.\n3. **Finanzierung:** keine Kalkulation auf erhoffte Zinssenkungen aufbauen.\n4. **Baukosten:** früh absichern und Developer-Spread beobachten.\n5. **Bestand:** nur halten, wenn Rendite, Cashflow und Zinsrisiko auch heute tragfähig sind.")

    st.markdown("### Was würde unsere These ändern?")
    st.success("**Bullisher:** Bund 10Y und Bauzinsen fallen, Kreditstandards lockern sich, Transaktionen steigen, Fertigstellungen bleiben niedrig und Baukosten beruhigen sich.")
    st.error("**Bearisher:** erneuter Inflationsschub, Langfristzinsen steigen, Arbeitslosigkeit zieht deutlich an, Banken verschärfen Standards und Verkaufspreise fallen schneller als Baukosten.")

st.divider()
st.caption("V0.2 · Harte Daten werden niemals durch Schätzwerte ersetzt. Markterwartungen, institutionelle Prognosen und Risikoszenarien werden separat gekennzeichnet. Dieses Dashboard ist ein Analysewerkzeug, keine Anlage- oder Finanzierungsberatung.")
