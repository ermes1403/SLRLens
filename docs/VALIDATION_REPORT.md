# SLR Lens 2.2 — rapporto di validazione

Data: 19 luglio 2026

Ambiente: Windows 11 Home, AMD Ryzen 5 3500U (4 core / 8 thread), 5,9 GB RAM

Algoritmi: Latent Dirichlet Allocation e Latent Semantic Indexing reale tramite TF-IDF + TruncatedSVD.

## Protocollo

La validazione comparativa con MySLR ha eseguito:

- K=2, K=3 e K=4;
- tre seed indipendenti per K (`42`, `7`, `101`);
- nove modelli LDA;
- nove modelli LSI;
- 25 iterazioni batch per replica;
- stessa matrice document-term per tutti i candidati;
- selezione tramite rank aggregato dichiarato:
  - UMass 28%;
  - NPMI 28%;
  - stabilità 22%;
  - diversità 10%;
  - esclusività 7%;
  - perplexity 5%.

La stabilità confronta i termini principali dei topic tra seed dopo il matching ottimo dei topic. La mappa documentale usa t-SNE su TF-IDF ridotto con TruncatedSVD. L’Interactive LDA Explorer usa distanze Jensen-Shannon e classical MDS.

Per LSI la perplexity non viene calcolata perché non è matematicamente applicabile. I documenti sono associati ai componenti tramite magnitudine relativa, esplicitamente distinta da una probabilità.

## Test automatici

Risultato: `5 passed`.

Copertura:

- normalizzazione e deduplicazione;
- rimozione del boilerplate editoriale;
- normalizzazione LLM/LLMs/large language model;
- distinzione tra configurazione richiesta e optimum;
- metriche multi-criterio;
- incertezza per documento;
- export CSV, JSON e ZIP riproducibile.
- implementazione LSI reale e possibilità di disattivarla esplicitamente.
- payload completo e selezionabile per ogni K;
- coordinate, prevalenza e profili di rilevanza per l’Interactive LDA Explorer;
- separazione dei campi pesati e consolidamento frase estesa/acronimo.

## Benchmark Q002

File: `Q002_.csv`

- documenti: 144;
- abstract disponibili: 144;
- keyword disponibili: 136;
- DOI validi: 129;
- modelli addestrati: 9 LDA + 9 LSI;
- tempo complessivo: 32,9 secondi;
- K robusto selezionato: 2;
- UMass: -1,0889;
- NPMI: 0,0183;
- stabilità: 46,3%;
- topic diversity: 80,0%;
- esclusività: 66,9%.

Topic:

1. `generative AI · software development · large language model` — 95 paper;
2. `large language model · multi agent · software` — 49 paper.

K=3 ha ottenuto la NPMI migliore (`0,0528`) e gruppi `64/45/35`, ma una stabilità inferiore (`41,5%`). K=4 ha ottenuto NPMI `0,0425`, stabilità `38,0%` e gruppi `53/34/28/29`.

Il software conserva e rende esplorabili tutti e tre i modelli. La raccomandazione K=2 non impedisce quindi di adottare K=3 quando l’interpretazione sostantiva della ricerca lo giustifica.

## Confronto con MySLR

Gli screenshot MySLR riportano:

- K=2: UMass -1,38 e log perplexity -7,13;
- K=3: UMass -1,44, log perplexity -7,15 e gruppi 35/60/49;
- K=4: UMass -1,63, log perplexity -7,18 e gruppi 24/54/45/21.

Per K=3 le dimensioni ordinate sono simili: MySLR `60/49/35`, SLR Lens `64/45/35`. L’export MySLR ha però permesso il confronto sui 144 documenti: ARI `0,00066`, NMI `0,01391` e accuratezza dopo la migliore permutazione `38,9%`. Le due soluzioni sono quindi sostanzialmente differenti nonostante le dimensioni aggregate simili.

Il confronto completo e i limiti di interpretazione sono in `docs/MYSLR_COMPARISON.md`.

## Interpretazione

Il corpus è fortemente omogeneo rispetto alla query di origine. Aumentare K produce gruppi tematici più specifici, ma riduce la stabilità tra seed. SLR Lens non presenta quindi un numero di topic come “ottimale” solo perché richiesto dall’utente.

Non è possibile certificare un rapporto di velocità “10× rispetto a MySLR” senza misurare MySLR sullo stesso computer, stesso file e stesso intervallo di K. I tempi di SLR Lens riportati sopra sono misurati e riproducibili.
