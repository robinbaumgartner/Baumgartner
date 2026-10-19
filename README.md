# Baumgartner Real Estate Intelligence — Prototype V0.1

Erste lauffähige Version des Immobilien-Makro-Dashboards.

## Enthaltene Live-Serien

- Effective Federal Funds Rate (Federal Reserve / FRED)
- US 10Y Treasury Yield (U.S. Treasury / FRED)
- EZB-Einlagenzins (ECB Data Portal)
- Rendite 10-jähriger Bundeswertpapiere (Deutsche Bundesbank)
- Effektivzins deutscher Wohnungsbaukredite mit Zinsbindung >10 Jahre (Deutsche Bundesbank)
- Deutscher Häuserpreisindex (Eurostat)

Alle Daten werden beim Öffnen bzw. nach Ablauf des Caches direkt aus den jeweiligen Datenquellen geladen. Bei Ausfall oder Änderung einer API zeigt das Dashboard einen Fehler an, statt erfundene Ersatzwerte zu verwenden.

## Starten — einfachste Variante

1. Python installieren: https://www.python.org/downloads/
2. Diesen Ordner auf dem Computer speichern.
3. In Windows im Ordner ein Terminal / PowerShell öffnen.
4. Einmalig ausführen:

```bash
pip install -r requirements.txt
```

5. Danach starten mit:

```bash
streamlit run app.py
```

6. Der Browser öffnet das Dashboard automatisch. Falls nicht, im Terminal angezeigte lokale Adresse öffnen (typischerweise `http://localhost:8501`).

## Späterer Online-Betrieb

Der gleiche Code kann auf Streamlit Community Cloud oder einem anderen Hosting-Dienst veröffentlicht werden. Dafür eignet sich ein GitHub-Repository. Dann ist kein lokaler Start mehr nötig; du öffnest nur noch eine Webadresse.

## Nächste Ausbaustufe

- US 2Y, Core PCE, EUR/USD
- Eurozone Inflation / Kerninflation
- deutsches BIP, Inflation, Arbeitslosigkeit, Reallöhne
- Kreditneugeschäft und ECB Bank Lending Survey
- Baugenehmigungen, Fertigstellungen und Baukosten
- Regionalmarkt Unterallgäu / Memmingen
- eigenes Projektmodul mit Verkaufen-vs.-Halten-Rechner
- transparent berechnete Financing- und Developer-Environment-Scores
