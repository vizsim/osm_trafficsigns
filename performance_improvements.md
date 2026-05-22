# Performance improvements

Brainstorm-Doku, kein verbindlicher Plan. Ausgangslage: Berlin-Test-Lauf hängt
~25 Min auf `process_ways` + `process_zones`, bei 100 % auf **einem** Core und
~650 MB RAM (von 48 GB). Das System hat also reichlich CPU- und RAM-Reserven —
die Pipeline ist single-threaded + nutzt teure globale Ops.

## Wo's gerade hakt

Drei Datenpunkte gemessen (Bremen klein, Neukölln mittel, Berlin gross):

| Stage | Bremen | Neukölln | Berlin | Skalierung Berlin/Bremen |
| --- | ---: | ---: | ---: | ---: |
| import (pyosmium) | 1 s | 2 s | 18 s | 18× (linear in PBF) |
| sign nodes | <1 s | <1 s | 2 s | ~10× (linear) |
| **sign ways** | <1 s | **3 s** | **6:28 min** | **≫1000×** (quadratisch) |
| **sign zones** | <1 s | **5 s** | **~25-30 min** | **≫1500×** (gleicher Stil wie ways) |
| merge + write | <1 s | <1 s | ?? | erwartet linear |
| **Gesamt** | **~3 s** | **~10 s** | **>30 min** | |

Input-Größen-Vergleich:

| | Bremen | Neukölln | Berlin |
| --- | ---: | ---: | ---: |
| sign nodes | 315 | 505 | 1 711 |
| sign ways | 1 108 | 590 | 7 533 |
| zone ways | 277 | 1 027 | 23 773 |
| highways | 71 946 | 34 623 | 464 493 |
| sign_ways × highways | 80 M | 20 M | **3,5 G** |
| zone_ways × highways | 20 M | 36 M | **11 G** |

Die expensive Stages sind beide in `process_ways` / `process_zones` und
teilen die gleiche Substruktur (`_junction_buffers` + `_place_endpoint_nodes`).
Neukölln läuft proportional zu Bremen (~3× Zeit für ~5× sign_nodes), Berlin
ist überlinear schlimmer — bestätigt die N×M-Skalierung im inneren Loop.

## Bonus: schnelle Iterations-Loop für Performance-Arbeit

Statt jedes Mal das volle Berlin (~30+ Min) zu testen, lohnt sich ein
**Mini-Extract** — z.B. nur ein Bezirk:

```bash
# 1. Polygon von Nominatim als GeoJSON
curl -s -A 'osm_trafficsigns/1.0' \
  'https://nominatim.openstreetmap.org/search?q=Neuk%C3%B6lln,+Berlin&format=geojson&polygon_geojson=1&limit=5' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
                f=next(f for f in d['features'] if f['properties']['osm_id']==162902); \
                json.dump({'type':'FeatureCollection','features':[f]}, sys.stdout)" \
  > osm/neukoelln.geojson

# 2. Berlin → Neukölln zuschneiden + auf nur relevante Tags filtern
osmium extract -p osm/neukoelln.geojson osm/berlin-latest.osm.pbf -o osm/neukoelln.osm.pbf --overwrite
osmium tags-filter osm/neukoelln.osm.pbf nw/traffic_sign w/highway -o osm/neukoelln-filtered.osm.pbf --overwrite

# 3. Pipeline (10 Sekunden!)
uv run tsp -i osm/neukoelln-filtered.osm.pbf -o output/neukoelln_signs.parquet
```

→ **Performance-Optimierungen im 10-Sekunden-Loop iterieren**, statt nach jeder
Änderung 30 Min Berlin zu warten. Wenn Neukölln in <2 s läuft, wird Berlin
~1-3 Min schaffen (entsprechend skaliert).

---

## A. Sindex-per-Way statt globaler Union — ✅ **IMPLEMENTIERT**

> Vorschlag vom User. Risiko: minimal. Logisch identisch, nur anderer Pfad.
>
> **Status**: umgesetzt in [src/tsp/ways.py:_junction_buffers](src/tsp/ways.py)
> und [src/tsp/zones.py](src/tsp/zones.py). Pipeline-Tests bleiben grün.
>
> **Gemessener Effekt auf Neukölln** (505 sign nodes, 590 sign ways,
> 34k highways):
>
> | Stage | Before A | After A | Speedup |
> | --- | ---: | ---: | ---: |
> | import | 2 s | 1 s | 2× |
> | sign_ways | 3 s | **1 s** | **3×** |
> | zones | 4 s | **2 s** | **2×** |
> | **Total** | **11.2 s** | **6.1 s** | **1.8×** |
>
> Auf Berlin (mit 13× mehr ways/zones × 13× mehr highways = 170×
> Kombinationen) wird der Effekt überproportional größer sein.

**Status quo** in [src/tsp/ways.py:143](src/tsp/ways.py#L143):

```python
sign_union = unary_union(list(way_gdf["geom"]))               # ~7.5k LineStrings → 1 große MultiLineString
relevant = highway_gdf[highway_gdf.intersects(sign_union)]    # global intersect über 464k highways
```

Beide Operationen sind teuer:

- `unary_union` baut intern eine geometrisch komplexe Vereinigung, das Topologie-Modul von GEOS muss alle Schnittpunkte berechnen.
- `intersects(global_union)` ist zwar sindex-beschleunigt aber die *Predicate-Auswertung* selber muss gegen eine gigantische MultiLineString prüfen.

**Vorschlag**: per Sign-Way ein billiger Sindex-Lookup gegen `highway_gdf.sindex`:

```python
hw_sindex = highway_gdf.sindex
relevant_idx: set[int] = set()
for geom in way_gdf["geom"]:
    relevant_idx.update(hw_sindex.query(geom, predicate="intersects"))
relevant = highway_gdf.iloc[sorted(relevant_idx)]
```

- `query(geom, predicate='intersects')` macht zuerst Bbox-Filter via R-tree, dann exact-intersect nur für Kandidaten — also pro Sign-Way nur lokal.
- Spart die globale Union komplett.
- Reduziert die Größe von `relevant` (vermutlich) wenig, aber alle nachfolgenden Iterationen werden trotzdem schneller weil's am Bottleneck ist.

**Erwarteter Effekt**: 5-20× Speedup für diese Funktion, je nach Geometrie-Dichte.

Gleiches gilt für [src/tsp/zones.py:74](src/tsp/zones.py#L74) (`seg_union = unary_union(...)`).

---

## B. Doppelte Iteration in `_junction_buffers` zusammenfassen — ✅ **IMPLEMENTIERT**

> **Status**: umgesetzt in [src/tsp/ways.py:_junction_buffers](src/tsp/ways.py).
> Pipeline-Tests bleiben grün. Bonus: gleichzeitig die `iterrows()` auf
> direkte Series-Iteration umgestellt (`zip(relevant.geometry.values,
> relevant["highway"].values)`) — vermeidet pro-Zeile Series-Materialisierung.
>
> **Kumulierter Effekt nach A + B auf Neukölln**:
>
> | Stand | Total | sign_ways | zones |
> | --- | ---: | ---: | ---: |
> | Baseline | 11.2 s | 3 s | 4 s |
> | + A (sindex-per-way) | 6.1 s | 1 s | 2 s |
> | **+ B (single-pass + zip)** | **5.1 s** | **1 s** | **1 s** |
> | Speedup ggü. Baseline | **2.2×** | 3× | 4× |

In [src/tsp/ways.py:152](src/tsp/ways.py#L152) wurde `relevant` vorher **zweimal** durchlaufen:

```python
for _, hw in relevant.iterrows():           # Pass 1: snap-keys zählen
    for a, b in _segments(hw["geom"]):
        for c in (a, b):
            k = _snap_key(c[0], c[1])
            total[k] = total.get(k, 0) + 1
            ...

# ... 15 Zeilen später ...

for _, hw in relevant.iterrows():           # Pass 2: nochmal alles, nur um repräsentative Koordinaten zu merken
    for a, b in _segments(hw["geom"]):
        for c in (a, b):
            rep.setdefault(_snap_key(c[0], c[1]), c)
```

→ Loop 2 ist redundant — den `rep`-Dict in Loop 1 mit füllen.

**Risiko**: minimal. **Effekt**: 30-50% schneller in dieser Funktion (halbe Anzahl Iterationen).

---

## C. `iterrows()` durch parallel-zip auf .values ersetzen — ✅ **IMPLEMENTIERT**

> **Status**: alle 6 verbleibenden `iterrows()` in
> [src/tsp/ways.py](src/tsp/ways.py) und [src/tsp/zones.py](src/tsp/zones.py)
> entfernt (process_ways Step 3, `_place_endpoint_nodes` × 2, `process_zones` × 3).
> Pipeline-Tests bleiben grün.
>
> **Effekt auf Neukölln**: praktisch nicht messbar (5.1 → 5.2 s, im Rauschen).
> Neukölln ist zu klein — die betroffenen Loops haben dort jeweils nur
> ~600-1000 Iterationen, und der Overhead von iterrows ist auf dieser Größe
> sub-sekündlich. Für Berlin mit 7533 sign_ways und 464k highways sind die
> gleichen Loops zwei Größenordnungen länger — dort wird der Effekt sichtbar.

---

## Berlin-Lauf nach A + B + C — gemessen 2026-05-22

Vollständige Pipeline auf `osm/berlin-filtered.osm.pbf` (26 MB nach Tags-Filter).

| Stage | Baseline | Nach A+B+C | Speedup |
| --- | ---: | ---: | ---: |
| import (pyosmium) | 18 s | 20 s | ≈ 1× |
| sign_nodes | 2 s | 2 s | ≈ 1× |
| **sign_ways** | **6:28 min** (388 s) | **42 s** | **9.2×** |
| **sign_zones** | **~25-30 min** (~1500-1800 s) | **8:30 min** (510 s) | **~3×** |
| merge + write | <1 s | <1 s | – |
| **Gesamt** | **>30 min** | **9:36 min** (576 s) | **3-3.5×** |

System-Ressourcen (`/usr/bin/time -v`):

- Wall-clock: **9:36.16**
- User CPU: 574.66 s (~99,8 % auf einem Core — weiterhin single-threaded)
- Max-RAM: **855 MB** (vs. ~650 MB Baseline)

**Befund**:

- `process_ways` profitiert massiv (~9×) — A (sindex-per-way statt globale Union)
  und B (single-pass) sparen genau die quadratische N×M-Operation, die Baseline
  fünf Minuten gekostet hat.
- `process_zones` ist jetzt der größte verbleibende Brocken (88 % der
  Gesamtzeit). Code-Struktur ist nach C analog zu `ways.py`, aber bei
  23 773 zone ways × 464 k highways sind selbst die optimierten Pfade lang.
  Hier lohnt sich D (Shapely-2 vectorized snap-keys) oder E (multi-core),
  siehe unten.
- RAM-Anstieg (650 → 855 MB) ist unkritisch — die `relevant_idx`-Sets und
  cached `seg_by_sign` dicts kosten etwas Speicher, aber wir haben Reserven.

**Was als nächstes**, falls Berlin unter 3 min soll:

1. py-spy auf `process_zones` werfen — vermutlich dominiert der innere
   Segment-Loop oder der `buffer(8).exterior.intersection(seg)` pro Entrance.
2. Vectorize den Coord-Sammel-Loop in `process_zones` (Schritt 2 + Schritt 4)
   mit `shapely.get_coordinates` + `np.unique` (Idee D).
3. Multi-core ist wahrscheinlich Overkill — A+B+C plus D-Style-Vectorisierung
   sollten reichen für ~2 min.

---

### Originaler Vorschlag-Text (zur Doku, jetzt obsolet)

`iterrows()` materialisiert pro Zeile ein neues `pd.Series` — extrem teuer.
GeoPandas ist hier besonders schlimm weil Geometry-Spalten Python-Objekte sind.

Konkret in [src/tsp/ways.py](src/tsp/ways.py): die fünf `iterrows()`-Stellen
(`_junction_buffers` × 2, `_place_endpoint_nodes` × 1, plus zwei in
`process_ways`). Ähnlich [src/tsp/zones.py](src/tsp/zones.py) (× 3) und
[src/tsp/nodes.py](src/tsp/nodes.py) (× 1).

**Drop-in replacement**:

```python
for geom, hw_type in zip(relevant.geometry, relevant["highway"]):
    ...
```

oder

```python
for row in relevant.itertuples(index=False):
    geom, hw_type = row.geom, row.highway
    ...
```

**Effekt**: typischerweise 5-10× schneller.

---

## D. Shapely 2 vectorized API

GeoPandas 1.x verwendet intern bereits Shapely 2.0+. Statt der Python-Loops
über Segmente kann man die Koordinaten als 2D-NumPy-Arrays extrahieren und
vectorized snap-keyen:

```python
import shapely

# alle highway-coords als (N, 2)-Array
coords = shapely.get_coordinates(relevant.geometry.values)

# vectorized snap (rounding zur Snap-Grid)
keys = np.round(coords / SNAP).astype(np.int64)

# unique keys + counts in einem numpy-Call
unique_keys, counts = np.unique(keys, axis=0, return_counts=True)
```

Hier wird der innere Python-Loop komplett durch NumPy ersetzt. Erwartet
20-100× schneller als `iterrows()` + `_segments()`.

**Risiko**: höher — man muss aufpassen dass der Index-Mapping (welche
Koordinate gehört zu welcher Highway?) erhalten bleibt. Pro Highway kommt
`get_coordinates` einen flachen Array, man braucht den `lengths`-Returnwert
um pro Highway zu gruppieren.

---

## E. Multi-Core via `multiprocessing.Pool` oder Dask-GeoPandas

Aktuell 100% auf einem Core. Berlin hätte z.B. 8-16 Cores zu vergeben.

**Wo's einfach parallelisierbar ist**:

1. **Per-row Operationen** (Schritt 1 von `process_ways` — der `groupby` +
   `unary_union` pro Gruppe ist embarrasingly parallel). Mit `joblib.Parallel`
   in wenigen Zeilen einbaubar.

2. **Sindex-Queries pro Sign-Way** (Idee A oben). Statt seriell:

   ```python
   from joblib import Parallel, delayed
   results = Parallel(n_jobs=-1)(
       delayed(hw_sindex.query)(geom, predicate='intersects')
       for geom in way_gdf["geom"]
   )
   relevant_idx = set().union(*results)
   ```

3. **dask-geopandas** für Sub-GDF-Operationen: `ddf.intersects(...)` läuft
   automatisch parallel.

**Risiko**: mittel. Sindex-Objekte sind nicht immer pickle-bar, GeoPandas-DFs
sind groß → IPC kann den Speedup auffressen. Lohnt sich erst nach A-D.

---

## F. PostGIS-Style fast snap-grid mit `numpy + dict`

Die `_snap_key()` Funktion macht einen Tuple-Round + ist hashable.
Bei 464k Highways × ~5 Vertices = 2.3M Snap-Keys werden in ein Python-Dict
gestopft. Das ist im Vergleich zu numpy langsam (Hash overhead).

**Alternative**:

- Koordinaten als `(N, 2)` int64-Array (gesnapped)
- Mit `np.unique(axis=0, return_inverse=True, return_counts=True)` zählen
- ohne dict, ohne tuple

**Effekt**: 10-50× je nach data shape.

---

## G. Profile zuerst — `py-spy` als Sanity-Check

Bevor wir hier wild optimieren, lohnt sich 1 Min Profiling:

```bash
sudo apt install py-spy   # oder: uv tool install py-spy
py-spy record -o profile.svg --pid $(pgrep -f 'venv/bin/tsp') --duration 60
```

Erzeugt ein Flame-Graph. Wir sehen dann konkret welche Funktion wie viel CPU-Zeit
zieht. Mein aktueller Verdacht (`unary_union` + `iterrows`) ist bestens informierter
Bauchgefühl, aber Messung > Glaube.

---

## H. Niedrig-hängende Quick-Wins außerhalb der Pipeline

- **`tippecanoe` parallelisieren** — flag `-P` für parallel reading. Aktuell ist
  build_pmtiles single-threaded. Berlin-PMTiles wird schnell groß.

- **PBF-Vorfilter standardisieren** — schon dokumentiert ([README:64-78](README.md#L64)).
  Eventuell als Default-Step in der CLI mit `--auto-filter`.

- **Highway-Tabelle reduzieren** — wir laden alle Spalten (`name`,
  `oneway:bicycle`, `traffic_sign`, …), brauchen aber nur Geometrie + `highway`.
  In [osmread.py:108-119](src/tsp/osmread.py#L108) auf die wirklich genutzten
  Spalten beschränken. Lädt schneller + weniger RAM.

---

## Reihenfolge wenn man's anpackt

1. **A** (sindex-per-way) — sicherster + größter erwarteter Speedup
2. **B** (doppelte Iteration zusammenfassen) — Sekunden Arbeit, klar gewonnen
3. **C** (iterrows → itertuples) — mechanischer Refactor
4. **G** (profilen!) — vor weiterem Optimieren um zu sehen wo's NOCH hängt
5. **D** (NumPy-vectorized snap-keys) — wenn A-C nicht reicht
6. **E** (multi-core) — der größte Gewinn aber auch das größte Risiko, daher als letztes

Schritte 1-3 könnte man in 30-60 Min umsetzen + testen (Bremen-Tests müssen
weiter grün bleiben). Erwarteter Effekt: Berlin von ~30 Min auf 2-5 Min.

Schritt 5-6: erfordert Profiling + sorgfältige Validierung gegen Bremen-Output.

---

## Caveats

- **Determinismus**: Multi-core kann zu nicht-deterministischer Reihenfolge
  führen. Falls wir das brauchen (z.B. weil "der erste Treffer wins" Logik
  drin ist) muss man sortieren am Ende.
- **Tests**: `tests/test_pipeline.py` läuft gegen die synthetische Bremen-Mini-PBF
  und prüft konkrete Counts (3 sign nodes, etc.). Jeder Refactor muss die
  weiter grün halten.
