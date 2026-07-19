# Confronto verificato MySLR vs SLR Lens

Data: 19 luglio 2026

Corpus: `Q002_.csv`, 144 documenti unici, 144 abstract, 136 record con keyword e 129 DOI validi.

## Evidenze disponibili

Per MySLR sono disponibili screenshot delle configurazioni K=2, K=3 e K=4, dell’Interactive LDA Explorer e della t-SNE. È inoltre disponibile l’export `mySLR_dataset_topic (1).xlsx` del modello K=3, con 144 righe, 144 titoli, 144 DOI e assegnazioni `35/60/49`.

Di conseguenza:

- si possono confrontare metriche dichiarate, numerosità dei topic e termini visibili;
- per K=3 si possono calcolare Adjusted Rand Index, Normalized Mutual Information e concordanza documento-per-documento;
- per K=2 e K=4 restano disponibili soltanto le evidenze degli screenshot.

## Risultati osservati

| K | MySLR UMass | MySLR log perplexity | MySLR documenti per topic | SLR Lens UMass | SLR Lens NPMI | Stabilità SLR Lens | SLR Lens documenti per topic |
|---:|---:|---:|---|---:|---:|---:|---|
| 2 | -1,38 | -7,13 | non visibile nell’output allegato | -1,0889 | 0,0183 | 46,3% | 95 / 49 |
| 3 | -1,44 | -7,15 | 35 / 60 / 49 | -1,0906 | 0,0528 | 41,5% | 64 / 45 / 35 |
| 4 | -1,63 | -7,18 | 24 / 54 / 45 / 21 | -1,1058 | 0,0425 | 38,0% | 53 / 34 / 28 / 29 |

Tempi SLR Lens, modalità rigorosa, K=2/3/4, tre seed per K, LDA e LSI abilitati: 32,9 secondi sul computer di validazione.

Le scale di perplexity e coerenza non devono essere confrontate come se fossero identiche: MySLR usa Gensim e un proprio pre-processing; SLR Lens usa scikit-learn, pesatura esplicita dei campi e vocabolario normalizzato. UMass è riportata affiancata perché ha la stessa direzione interpretativa, ma corpus tokenizzato, smoothing e top termini possono differire.

## Interpretazione

K=3 mostra una convergenza soltanto nelle dimensioni aggregate: ordinando i gruppi, MySLR produce `60/49/35` e SLR Lens `64/45/35`. L’abbinamento completo dimostra però che i paper non coincidono nei gruppi:

- 129 documenti abbinati tramite DOI;
- 15 documenti abbinati tramite titolo normalizzato;
- copertura: 144/144;
- ARI: 0,00066;
- NMI: 0,01391;
- accuratezza dopo la migliore permutazione dei topic: 38,9%.

Matrice di corrispondenza, righe MySLR e colonne SLR Lens:

| | SLR 1 | SLR 2 | SLR 3 |
|---|---:|---:|---:|
| MySLR 1 | 14 | 15 | 6 |
| MySLR 2 | 29 | 14 | 17 |
| MySLR 3 | 21 | 16 | 12 |

La migliore permutazione associa MySLR 1→SLR 2, MySLR 2→SLR 1 e MySLR 3→SLR 3. ARI e NMI prossimi a zero indicano soluzioni sostanzialmente differenti, non un semplice scambio delle etichette.

SLR Lens raccomanda K=2 perché la scelta non dipende dalla sola coerenza: K=2 conserva maggiore stabilità, diversità, esclusività e perplexity. K=3 ha la NPMI migliore tra i tre candidati, quindi rimane una possibile lettura sostantiva del corpus, ma non replica le assegnazioni MySLR. K=4 è esplorabile ma meno stabile.

Gli screenshot MySLR mostrano inoltre termini poco informativi o isolati, per esempio `flourish`, `spoco`, `internship`, `clinical` e `ros hd`. SLR Lens normalizza acronimi e frasi del dominio, filtra boilerplate e impedisce ai bigrammi di attraversare i confini dei campi pesati. Questo produce etichette più leggibili, ma costituisce una scelta metodologica diversa, non una garanzia automatica di superiorità.

## Funzioni aggiunte dopo il confronto

- selezione immediata di K=2, K=3, K=4 o qualsiasi candidato calcolato;
- aggiornamento coerente di KPI, topic, distribuzione temporale, incertezza e bibliometria per il K scelto;
- Interactive LDA Explorer reale:
  - distanze Jensen-Shannon tra distribuzioni topic-term;
  - proiezione MDS deterministica;
  - cerchi proporzionali alla prevalenza;
  - selezione del topic;
  - slider λ tra probabilità nel topic ed esclusività rispetto al corpus;
- t-SNE per ogni K:
  - stessa geometria semantica TF-IDF + TruncatedSVD per rendere confrontabili i modelli;
  - colori, confidenza e tooltip aggiornati con le assegnazioni del K scelto;
  - filtro temporale;
- conservazione ed export delle distribuzioni complete per tutti i candidati;
- eliminazione di n-grammi artificiali prodotti dai confini tra campi duplicati;
- consolidamento di frase estesa e acronimo, ad esempio `software development lifecycle (SDLC)`.
- validazione esterna caricabile dall’interfaccia con matching DOI/titolo, ARI, NMI, accuratezza allineata e matrice di corrispondenza per ogni K.

## Verifica mancante per un confronto definitivo

Per completare lo stesso confronto su K=2 e K=4 servono i rispettivi export MySLR “dataset per topic”. La validazione esterna integrata in SLR Lens li può confrontare senza modifiche, usando DOI e fallback sul titolo.
