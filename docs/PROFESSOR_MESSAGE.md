# Messaggio pronto per il professore

Buongiorno Professore,

prima di inviarLe il link ho ampliato significativamente il prototipo. SLR Lens non è più soltanto un'alternativa più rapida al topic modeling di MySLR: è diventato un ambiente unico che integra topic modeling, validazione e bibliometric/science mapping, evitando di spostare e riallineare i dati tra MySLR e Bibliometrix/Biblioshiny.

In particolare, la piattaforma ora include:

- LDA e LSI realmente calcolati, con scelta ed esplorazione di più valori di K;
- confronto multi-metrica con coherence UMass/NPMI, perplexity, stabilità multi-seed, diversità ed esclusività;
- Interactive LDA Explorer, t-SNE per ogni K, probabilità e incertezza per singolo documento;
- confronto quantitativo con MySLR mediante ARI, NMI e matrice di corrispondenza;
- produzione scientifica, citazioni, fonti e documenti più influenti;
- Bradford, Lotka e indici h/g/m degli autori nel corpus;
- reti di collaborazione tra autori, istituzioni e paesi, con indicatori SCP/MCP;
- co-word network, thematic map, trend topic, Three-Field Plot ed evoluzione tematica;
- co-citazione e bibliographic coupling quando l'export contiene le cited references;
- pacchetto riproducibile con assegnazioni, probabilità, seed, parametri, versioni, fingerprint del corpus e tabelle bibliometriche.

Ho cercato di introdurre anche una garanzia metodologica importante: il software non simula le analisi quando mancano i dati. Per esempio, nel file Scopus di prova le cited references non sono presenti; quindi co-citazione e coupling vengono sospesi e l'interfaccia indica esattamente quale campo riesportare.

Sul corpus di prova da 144 documenti, in modalità rapida, l'intera analisi LDA+LSI per K=2,3,4 insieme alla suite bibliometrica è stata completata in circa 9 secondi sulla macchina di sviluppo. Il sistema ha ricostruito 924 citazioni, 103 fonti, 562 autori, 32 paesi e una rete concettuale di 43 keyword con 175 relazioni.

Mi farebbe molto piacere conoscere il Suo parere, in particolare su tre aspetti:

1. ritiene utile l'integrazione diretta tra topic modeling e science mapping per il workflow di una SLR?
2. quali analisi considera indispensabili per una validazione accademica del software?
3. avrebbe senso impostare una comparazione sperimentale controllata con MySLR e Biblioshiny, sugli stessi dataset e con criteri condivisi?

Se per Lei va bene, posso prepararLe anche una breve demo guidata e un export Scopus completo di cited references, così da mostrare l'intera struttura intellettuale.

Grazie.
