# SLR Lens

Applicazione web locale per analizzare export Scopus e dataset MySLR con **Latent Dirichlet Allocation (LDA)**, **Latent Semantic Indexing (LSI)** e una suite integrata di **bibliometric intelligence**. La versione 3 unisce topic modeling, science mapping, audit dell'incertezza e analisi bibliometrica in un solo workflow riproducibile.

## Funzioni

- import CSV/XLSX Scopus e riconoscimento automatico delle colonne;
- deduplicazione tramite DOI, EID e titolo normalizzato;
- selezione manuale dei paper;
- normalizzazione di concetti scientifici e rimozione del boilerplate editoriale;
- confronto parallelo di più numeri di topic e repliche indipendenti;
- scelta successiva di qualsiasi K già calcolato, senza nuovo addestramento;
- selezione multi-metrica: UMass, NPMI, stabilità, diversità, esclusività e perplexity;
- curva comparativa LDA vs LSI sugli stessi K e sullo stesso corpus;
- LSI reale con TF-IDF + TruncatedSVD, componenti, salienze ed explained variance;
- topic, termini, distribuzione temporale, documenti rappresentativi;
- probabilità complete, entropia e documenti con assegnazione incerta;
- validazione esterna contro export MySLR con matching DOI/titolo, ARI, NMI e matrice di corrispondenza;
- outlier semantici e relazioni TF-IDF tra documenti;
- Interactive LDA Explorer con distanza Jensen-Shannon, MDS e rilevanza λ;
- t-SNE comparabile tra K, ricolorata con le assegnazioni del modello scelto e filtro temporale;
- analisi autori e bibliometria;
- produzione scientifica annuale, impatto e documenti più citati;
- Bradford, Lotka e indici h/g/m calcolati nel corpus;
- reti di co-autorship, affiliazioni e collaborazione SCP/MCP tra paesi;
- co-word network, thematic map, trend topic, Three-Field Plot ed evoluzione tematica;
- co-citazione e bibliographic coupling condizionali alla presenza delle cited references;
- citazioni, fonti, open access, tipologie documentali e impatto per topic;
- export CSV, metodologia JSON e ZIP completo per la riproducibilità.

## Avvio

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Aprire `http://127.0.0.1:8000`.

## Perché è più rapido

La matrice document-term viene costruita una sola volta e condivisa tra le configurazioni parallele. La modalità rapida usa una replica online per K. La modalità rigorosa usa batch learning, 25 iterazioni e tre seed indipendenti per ogni K: la concordanza dei termini tra le repliche misura la stabilità reale.

## Metodo

Il testo pesato è formato da `2× Title + Abstract + 3× Author Keywords`. La pipeline normalizza concetti equivalenti (per esempio LLM/LLMs/large language model), elimina note di copyright ed editore, applica stopword inglesi e scientifiche, unigrammi e bigrammi.

I campi pesati sono separati prima della costruzione dei bigrammi, così la duplicazione di titolo e keyword non può produrre n-grammi artificiali ai confini. Anche le coppie “frase estesa + acronimo”, come `software development lifecycle (SDLC)`, vengono consolidate in un solo concetto.

Il numero di topic non viene scelto con una singola metrica. Il rank dichiarato combina UMass (28%), NPMI (28%), stabilità (22%), diversità (10%), esclusività (7%) e perplexity (5%). Se viene analizzato un solo K, il software lo dichiara come configurazione richiesta e non come optimum.

LSI usa una selezione separata basata su UMass, NPMI, stabilità, diversità ed explained variance. La perplexity viene indicata come non applicabile: LSI è una decomposizione lineare firmata, non un modello probabilistico. LSI è spesso indicato in letteratura anche come LSA.

Ogni pacchetto di riproducibilità include fingerprint SHA-256 del corpus, versioni delle librerie, seed, parametri, metriche di tutti i candidati, termini e probabilità complete per documento, tabelle bibliometriche, reti keyword, thematic map e stato di copertura delle references.

## Benchmark verificato

Sul corpus Scopus Q002 usato nel confronto con MySLR:

- 144/144 record elaborati, senza duplicati;
- 924 citazioni, 103 fonti, 562 autori e 32 paesi ricostruiti;
- 43 nodi e 175 archi nella rete di co-word;
- LDA + LSI per K=2,3,4 e suite bibliometrica completati in circa 9 secondi in modalità rapida sulla macchina di sviluppo.

Il tempo dipende dall'hardware e dalla modalità scelta. Non viene dichiarato un vantaggio “10×” senza un benchmark controllato sulla stessa macchina.

Il confronto verificato con gli screenshot MySLR sul corpus Q002 è documentato in [`docs/MYSLR_COMPARISON.md`](docs/MYSLR_COMPARISON.md).
