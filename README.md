# SLR Lens

Applicazione web locale per analizzare export Scopus e dataset MySLR con **Latent Dirichlet Allocation (LDA)** e un confronto reale con **Latent Semantic Indexing (LSI)**. La versione 2 privilegia validazione scientifica, velocità e riproducibilità.

## Funzioni

- import CSV/XLSX Scopus e riconoscimento automatico delle colonne;
- deduplicazione tramite DOI, EID e titolo normalizzato;
- selezione manuale dei paper;
- normalizzazione di concetti scientifici e rimozione del boilerplate editoriale;
- confronto parallelo di più numeri di topic e repliche indipendenti;
- selezione multi-metrica: UMass, NPMI, stabilità, diversità, esclusività e perplexity;
- curva comparativa LDA vs LSI sugli stessi K e sullo stesso corpus;
- LSI reale con TF-IDF + TruncatedSVD, componenti, salienze ed explained variance;
- topic, termini, distribuzione temporale, documenti rappresentativi;
- probabilità complete, entropia e documenti con assegnazione incerta;
- outlier semantici e relazioni TF-IDF tra documenti;
- mappa t-SNE, analisi autori e bibliometria;
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

Il numero di topic non viene scelto con una singola metrica. Il rank dichiarato combina UMass (28%), NPMI (28%), stabilità (22%), diversità (10%), esclusività (7%) e perplexity (5%). Se viene analizzato un solo K, il software lo dichiara come configurazione richiesta e non come optimum.

LSI usa una selezione separata basata su UMass, NPMI, stabilità, diversità ed explained variance. La perplexity viene indicata come non applicabile: LSI è una decomposizione lineare firmata, non un modello probabilistico. LSI è spesso indicato in letteratura anche come LSA.

Ogni pacchetto di riproducibilità include fingerprint SHA-256 del corpus, versioni delle librerie, seed, parametri, metriche di tutti i candidati, termini e probabilità complete per documento.
