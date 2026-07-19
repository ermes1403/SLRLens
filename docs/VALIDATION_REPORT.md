# SLR Lens 2.0 — rapporto di validazione

Data: 19 luglio 2026

Ambiente: Windows 11 Home, AMD Ryzen 5 3500U (4 core / 8 thread), 5,9 GB RAM

Algoritmi: Latent Dirichlet Allocation e Latent Semantic Indexing reale tramite TF-IDF + TruncatedSVD.

## Protocollo

La modalità rigorosa ha eseguito:

- K da 2 a 8;
- tre seed indipendenti per K (`42`, `7`, `101`);
- 21 modelli LDA per dataset;
- 21 modelli LSI per dataset quando il confronto è abilitato;
- 25 iterazioni batch per replica;
- stessa matrice document-term per tutti i candidati;
- selezione tramite rank aggregato dichiarato:
  - UMass 28%;
  - NPMI 28%;
  - stabilità 22%;
  - diversità 10%;
  - esclusività 7%;
  - perplexity 5%.

La stabilità confronta i termini principali dei topic tra seed dopo il matching ottimo dei topic. La mappa usa t-SNE su TF-IDF ridotto con TruncatedSVD.

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

## Benchmark Q002

File: `Q002_.csv`

- documenti: 144;
- abstract disponibili: 144;
- keyword disponibili: 136;
- DOI validi: 129;
- modelli addestrati: 21;
- tempo complessivo: 62,2 secondi;
- K robusto selezionato: 2;
- UMass: -0,9837;
- NPMI: 0,0429;
- stabilità: 55,9%;
- topic diversity: 81,7%;
- esclusività: 73,2%;
- assegnazioni forti: 68,8%;
- documenti incerti: 65;
- outlier semantici: 15.

Topic:

1. `generative AI · software development · code` — 61 paper;
2. `large language model · agile · software development lifecycle` — 83 paper.

La modalità esplorativa sullo stesso intervallo K=2…8 ha addestrato sette modelli in 17,7 secondi. Usa un solo seed, viene quindi indicata nell'interfaccia come screening e non come optimum certificato.

## Confronto LDA vs LSI su Q002

Modalità rigorosa, K=2…8, tre seed:

- tempo totale LDA + LSI: 80,0 secondi;
- overhead specifico LSI: 4,5 secondi;
- LDA selezionato: K=2, NPMI 0,0429, stabilità 55,9%;
- LSI selezionato: K=4, NPMI 0,2218, stabilità 100%;
- diversità LSI: 75,0%;
- varianza spiegata LSI: 5,71%.

I quattro componenti LSI sono stati calcolati realmente e risultano molto sbilanciati: 125, 7, 6 e 6 documenti. La bassa varianza spiegata segnala che il corpus Q002 è semanticamente omogeneo e che il risultato LSI va letto come decomposizione esplorativa, non come tassonomia definitiva.

## Benchmark file MySLR del professore

File: `mySLR_dataset.xlsx`

- documenti: 291;
- abstract disponibili: 291;
- keyword disponibili: 275;
- DOI validi: 286;
- modelli addestrati: 21;
- tempo complessivo: 120,2 secondi;
- K robusto selezionato: 2;
- UMass: -1,1979;
- NPMI: 0,0324;
- stabilità: 60,1%;
- topic diversity: 86,7%;
- esclusività: 74,2%;
- assegnazioni forti: 70,8%;
- documenti incerti: 123;
- outlier semantici: 30.

Topic:

1. `large language model · test · code` — 174 paper;
2. `requirements · large language model · software` — 117 paper.

Il controllo outlier ha evidenziato record potenzialmente fuori perimetro, tra cui farming, biomedical statistics e radar systems.

## Interpretazione

Entrambi i corpus sono fortemente omogenei rispetto alle query di origine. Aumentare K produce più gruppi, ma riduce sensibilmente la stabilità tra seed. SLR Lens non presenta quindi un numero di topic come “ottimale” solo perché richiesto dall’utente.

Non è possibile certificare un rapporto di velocità “10× rispetto a MySLR” senza misurare MySLR sullo stesso computer, stesso file e stesso intervallo di K. I tempi di SLR Lens riportati sopra sono misurati e riproducibili.
