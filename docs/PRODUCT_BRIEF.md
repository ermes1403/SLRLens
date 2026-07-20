# SLR Lens 3 — Product brief

## Visione

SLR Lens 3 è una piattaforma locale di research intelligence per systematic literature review. Integra in un unico flusso ciò che normalmente richiede passaggi separati tra un software di selezione/analisi SLR, un ambiente di topic modeling e Bibliometrix/Biblioshiny.

Non è una replica grafica di MySLR. Il suo elemento distintivo è la connessione verificabile tra:

1. corpus e qualità dei metadati;
2. topic probabilistici LDA e struttura semantica LSI;
3. incertezza delle assegnazioni;
4. performance bibliometrica;
5. struttura concettuale, sociale e intellettuale della letteratura;
6. export riproducibile e confronto esterno con MySLR.

## Problema risolto

Nel workflow tradizionale il ricercatore esporta i dati da Scopus, esegue topic modeling in un sistema, trasferisce i record in Biblioshiny, riconfigura le analisi e poi riconcilia manualmente risultati e identificativi. Questo aumenta tempi, errori di allineamento e difficoltà di riproduzione.

SLR Lens mantiene lo stesso record come unità di analisi dall'importazione all'export. Topic, citazioni, autori, paesi, keyword, reti e indicatori restano collegati allo stesso documento.

## Funzioni integrate

### Topic intelligence

- LDA probabilistico reale e LSI reale tramite TF-IDF + TruncatedSVD.
- Scelta libera di K e confronto simultaneo di più configurazioni.
- UMass, NPMI, perplexity, stabilità multi-seed, diversità ed esclusività.
- Interactive LDA Explorer con Jensen–Shannon/MDS e controllo lambda.
- t-SNE per ciascun K, filtro temporale e probabilità per documento.
- Audit di incertezza, entropia, assegnazioni forti e outlier semantici.
- Confronto quantitativo con export MySLR tramite ARI, NMI e accuratezza allineata.

### Performance bibliometrica

- produzione scientifica annuale e tasso di crescita composto;
- citazioni totali, medie, mediane e annualizzate;
- documenti più citati;
- impatto citazionale per topic LDA;
- Open Access, tipologie documentali e copertura metadati.

### Fonti e autori

- fonti più produttive;
- zone e nucleo di Bradford;
- produttività autoriale intera e frazionata;
- indici h, g e m calcolati sul corpus;
- distribuzione di Lotka e stima del parametro beta;
- fonti dinamiche nel tempo.

### Struttura sociale

- rete pesata di co-authorship;
- istituzioni più presenti;
- paesi di produzione scientifica;
- SCP/MCP e tasso di collaborazione internazionale;
- rete di collaborazione tra paesi;
- collaboration index e autori medi per documento.

### Struttura concettuale

- rete pesata di co-word da Author Keywords e Index Keywords;
- thematic map con centralità esterna e densità interna dichiarate;
- trend topic annuali;
- Three-Field Plot Autori → Keyword → Fonti;
- evoluzione tematica tra finestre temporali con similarità di Jaccard.

### Struttura intellettuale

- co-citation network dei riferimenti;
- bibliographic coupling tra documenti;
- top cited references;
- attivazione automatica solo quando l'export contiene `References` o `Cited references`.

Se il dato necessario manca, l'interfaccia spiega quale campo esportare. Non produce zeri ambigui né valori simulati.

## Differenze rispetto a MySLR

| Area | MySLR osservato | SLR Lens 3 |
|---|---|---|
| Topic modeling | LDA, più configurazioni e visualizzazioni | LDA + LSI reali, multi-metrica, multi-seed, K esplorabile |
| Validazione | Coherence/perplexity | Coherence, perplexity, stabilità, diversità, esclusività, ARI/NMI esterni |
| Incertezza | Assegnazione prevalente | Probabilità completa, entropia, secondo topic, outlier |
| Bibliometria | Analisi essenziali | Performance + fonti/autori/documenti + strutture concettuale/sociale/intellettuale |
| Tracciabilità | Output applicativo | SHA-256, versioni, seed, parametri, CSV e JSON riproducibili |
| Metadati mancanti | Risultato non sempre esplicito | Gate metodologico: calcolo consentito solo con campi adeguati |
| Workflow | Topic analysis separata da Bibliometrix | Pipeline unica document-level |

## Benchmark sul corpus del professore

Dataset Q002 Scopus, 144 documenti:

- 144 abstract disponibili e 136 record con Author Keywords;
- 129 DOI validi;
- 924 citazioni;
- 103 fonti, 562 autori, 32 paesi;
- Bradford: 14 fonti nella zona 1 per 49 paper, 42 nella zona 2 per 48 paper, 47 nella zona 3 per 47 paper;
- rete keyword: 43 nodi e 175 archi;
- LDA e LSI su K=2,3,4 più bibliometria: circa 9 secondi in modalità rapida sulla macchina di sviluppo.

L'export di prova non contiene cited references: co-citazione e bibliographic coupling risultano correttamente sospesi. Per una demo completa occorre riesportare da Scopus includendo il campo References.

## Innovazione

Il valore non è “avere più grafici”, ma poter attraversare tre livelli di evidenza senza perdere la tracciabilità:

- dal topic a ogni documento e alla sua probabilità;
- dal topic al suo impatto bibliometrico;
- dalle keyword ai fronti di ricerca e alla loro evoluzione;
- dagli autori alle collaborazioni e ai paesi;
- dai risultati al pacchetto che consente di ripetere e controllare l'analisi.

Questo rende SLR Lens utilizzabile non solo per presentare una mappa, ma per motivare decisioni di screening, interpretazione e sintesi in una tesi o in una review.

## Limiti dichiarati

- Gli indici h/g/m sono corpus-level e non equivalgono ai profili completi Scopus degli autori.
- L'estrazione dei paesi dipende dalla qualità delle stringhe di affiliazione.
- Le mappe tematiche dipendono dalla copertura e normalizzazione delle keyword.
- Co-citazione e coupling richiedono cited references.
- La selezione automatica di K è un supporto decisionale, non una verità assoluta: tutti i candidati restano esplorabili.

## Demo consigliata

1. Importare Q002 e mostrare deduplica/copertura.
2. Avviare K=2,3,4 in modalità rapida.
3. Confrontare LDA e LSI e aprire l'Interactive LDA Explorer.
4. Mostrare documenti incerti e confronto ARI/NMI con MySLR.
5. Aprire Bibliometric Intelligence: Bradford, h/g/m, collaboration network, thematic map, Three-Field Plot.
6. Mostrare il gate References come prova che l'app non simula analisi non supportate.
7. Scaricare il pacchetto riproducibile.

## Riferimenti funzionali

L'inventario è stato allineato alle funzioni ufficiali descritte da Bibliometrix/Biblioshiny: livelli Sources–Authors–Documents, Three-Field Plot, Bradford e Lotka, strutture concettuale–intellettuale–sociale e workflow SAAS.

- https://www.bibliometrix.org/biblioshiny/
- https://www.bibliometrix.org/software/
- https://www.bibliometrix.org/vignettes/Introduction_to_bibliometrix.html
