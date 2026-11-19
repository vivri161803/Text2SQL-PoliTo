# Pipeline Text2SQL PoliTo, versione semplificata

* **Author:** vivri161803
* **Date:** 2026-11-19

## Overview

È una pipeline Python che produce il PDF `<MATRICOLA>_TextSQL.pdf` descritto in `PianoDiImplementazione.md`: stessa struttura, stessi form, tabelle, grafici e appendici. L'unico vincolo rigido è la forma del documento finale. Il modo in cui viene prodotto è libero.

Il docente ha approvato tre cose: OpenRouter al posto delle web app e di LM Studio, l'automazione completa (domande, soluzioni attese, analisi, commenti) e la prima persona nel report.

Vincoli:
- scadenza 1 dicembre 2026;
- circa 2 giorni di lavoro;
- 15 $ di credito API.

Il flusso resta in 4 stadi: gold → run → eval → report. Gli stadi si passano file JSON/JSONL, e una cache su disco congela le risposte.

## Analysis

La revisione ha usato 7 lenti: design, accuratezza tecnica, semplicità, comprensibilità, prontezza all'implementazione, struttura e compromessi eliminabili. Le 7 lenti concordano: **il progetto non è pronto per scrivere codice**. Il motivo non è l'architettura. Sono tre lacune nelle informazioni di partenza, insieme a un budget sottostimato. Qui sotto i risultati sono ordinati per priorità.

Ho filtrato le proposte dei revisori con lo stesso criterio che hai fissato tu: entra solo ciò che protegge la forma del PDF o la correttezza dei numeri EX. Diverse proposte aggiungerebbero meccanismi (`source_hash`, `--freeze`, selezione delle istanze per mutazione delle query) che vanno contro l'obiettivo di semplificare. Le ho messe tra le alternative, non tra le decisioni.

### Blocchi (da risolvere prima del codice)

1. **La specifica contraddice i tagli accettati, e CLAUDE.md dice "the spec wins".**
   - Il piano descrive ancora Faker, l'arbitro Opus, lo stato `arbitrato`, il secondo giudice con kappa, il giro in italiano obbligatorio e la tabella completa dei controlli statici.
   - Se Claude Code implementa il piano così com'è, costruisce proprio i pezzi che hai tagliato.
   - Correzione: una sezione "Decisioni e semplificazioni (19 nov)" subito dopo la Panoramica, poi il testo superato va corretto o barrato. CLAUDE.md va ridotto a comandi, invarianti e rimandi alle sezioni del piano.

2. **Il testo dell'esercitazione non è nel repository.** Mancano:
   - il prompt d'esempio della Parte 1, che va riprodotto "parola per parola";
   - lo schema Biblioteca con gli asterischi;
   - i 5 schemi della Parte 3;
   - le domande Q1-Q10 alla lettera;
   - i nomi esatti dei campi dei form;
   - le domande di analisi della Parte 3.

   Senza questo materiale i prompt e il template sono ipotesi. Correzione: trascriverlo in `data/assignment.md` e ricavarne un elenco dei campi del PDF (`form_fields.yaml`). Il controllo finale verifica il PDF contro quell'elenco.

3. **I parametri di default rischiano di rendere alcuni modelli irraggiungibili.**
   - Con `require_parameters: true`, OpenRouter instrada solo verso provider che supportano *tutti* i parametri inviati.
   - Anthropic non supporta `seed`, e con il reasoning attivo non accetta `temperature=0`.
   - I modelli di reasoning OpenAI (gpt-5.5) rifiutano una temperature diversa dal default.
   - Molti provider dei modelli piccoli non supportano `seed`.

   Il risultato possibile è "no endpoints" proprio su Opus, che fa gold, giudizi e testi, o su GPT-5.5. Correzione:
   - parametri espliciti per ogni modello in `models.yaml`;
   - niente `seed`, perché la riproducibilità la dà già la cache;
   - `require_parameters` solo dove si passa il reasoning;
   - allo step 0 una vera chiamata da 1 token per ogni modello, con i parametri esatti, invece del solo `GET /models`.

4. **Budget sottostimato di circa 1,5-2 volte.**
   - Le chiamate dei run sono già 183. Con un giudizio Opus per ognuna, più gold, sintesi e secondo parere, si arriva a circa 375-400 chiamate.
   - La stima dei revisori è 17-20 $ nel caso peggiore, senza aver verificato i prezzi di Opus 5.5.
   - Se il limite di spesa della chiave scatta a metà della Parte 3, il PDF resta incompleto.
   - Correzione principale: **giudice raggruppato**, cioè una chiamata Opus per prompt che giudica le risposte di tutti i modelli. Le chiamate di giudizio scendono da circa 150 a circa 35, e i commenti escono più coerenti tra loro.
   - Aggiungere un totale di spesa progressivo in `llm.py` e trattare l'HTTP 402 come errore fatale, senza retry.

### Correzioni importanti (non bloccano la partenza, ma toccano il PDF)

5. **Le mutazioni dei database, così come sono descritte, non funzionano.**
   - "Duplicare righe dove la PK lo consente" non fa nulla, perché ogni tabella ha una PK.
   - Ridurre i domini con un UPDATE rompe le PK composte che contengono Date/Time (CONSULTATION, LECTURE, FLIGHT, BOOKING).
   - Una mutazione può rendere vuoto il risultato del gold. Due risultati vuoti coincidono e gonfiano EX.

   Correzione:
   - operatori deterministici in Python con seed fisso:
     - aggiungere righe figlie con PK nuove;
     - mettere a NULL le colonne nullabili;
     - spostare date e numeri di ±1 intorno alle soglie delle domande;
     - eliminare solo righe figlie.
   - Tenere i valori letterali usati dalle domande, per esempio 'fantasy'.
   - Richiedere che il gold sia non vuoto su almeno 3 istanze su 5.

6. **`esito` calcolato in modo deterministico.**
   - EX=1 → corretta.
   - EX=0 con `colonne_extra` o `duplicati` → parzialmente corretta.
   - Altrimenti → errata.

   Il giudice riceve l'esito e scrive solo il commento e le categorie d'errore. L'esito evidenziato su una scheda non può più contraddire la tabella EX, e il flag `incoerenza` diventa superfluo. **Questo sostituisce un meccanismo che avevi scelto di tenere: va deciso.**

7. **Righe duplicate in `calls.jsonl` ed `evals.jsonl`.** I file sono in sola aggiunta e un rilancio scrive di nuovo le stesse righe. Ne vengono EX contato due volte, schede doppie e costi gonfiati. Correzione:
   - un `call_id` = hash di (parte, domanda, strategia, lingua, giro, modello);
   - si tiene solo l'ultima riga per chiave;
   - un campo `role: tested | support` tiene le chiamate di supporto fuori dalle tabelle.

8. **Le decisioni manuali sul gold non sopravvivono a un rilancio.** Correzione: un file `data/gold_overrides.yaml`, scritto da te e applicato per ultimo. Ogni voce arriva già compilata con le due query e le righe che differiscono. `report` si rifiuta di partire finché resta un caso `da_rivedere`.
   - In Parte 1 un disaccordo indica una domanda ambigua. Il candidato si scarta e si prende il successivo dei 3, senza passare da te.
   - In Parte 3 i disaccordi saranno probabilmente più di 3. Rivedili il giorno 1, subito dopo `gold`.

9. **Risposte troncate.** Gemini 2.5 Flash, GPT-5.5 e Qwen thinking possono consumare tutti i 16000 token nel reasoning e restituire SQL vuoto con `finish_reason=length`. Correzione:
   - salvare `finish_reason`;
   - un retry con un limite al reasoning;
   - non mettere in cache le risposte troncate.

   In più, allo step 0, una chiamata della Parte 3 per modello per verificare che il reasoning arrivi davvero. Da quel campo dipendono l'Appendice B e gli estratti.

10. **La ricerca dei termini vietati ("voice grep") è in conflitto con la tabella modelli e con l'Appendice D.** Una tabella con "ID e parametri" e i costi per modello mostrerebbero Opus e DeepSeek. Correzione:
    - aggiungere in `models.yaml` i campi `in_report: bool` e `params_b`;
    - i costi di supporto vanno sotto un'etichetta neutra, per esempio "preparazione e analisi";
    - il grep si fa sul testo estratto dal PDF (`pdftotext`);
    - il materiale di input al giudice usa "soluzione attesa", non "gold".

11. **Campi vuoti legittimi.** "Prompt aggiornato" e giro 2 sono vuoti quando la risposta era già corretta. Anche l'Output di Q4/Q10 può essere vuoto. La regola "nessun campo vuoto" fallirebbe su tutti questi casi. Correzione: testi segnaposto fissi, per esempio "Non necessario: risposta corretta al primo giro".

12. **Esecuzione: prima DuckDB nativo, poi transpilazione.** Transpilare sempre da Postgres può cambiare la divisione intera e le funzioni data. Correzione:
    - DuckDB nativo prima; sqlglot postgres e poi mysql solo in caso di errore;
    - lo stesso percorso per gold e risposte;
    - aggiungere "dialetto" alle categorie d'errore, perché la tabella dei rischi la usa ma l'elenco no.

13. **Impaginazione.**
    - `page-break-inside: avoid` non vale per schede più alte di una pagina.
    - 5 SQL affiancati non entrano in un A4 verticale. Servono righe impilate o una pagina orizzontale.
    - `<pre>` richiede `pre-wrap`.
    - Il font va incorporato.
    - L'Appendice B può superare le 50 pagine: decidi ora carattere o limite.

14. **Ossatura del report.** Tre chiamate reali non bastano. Serve `report --draft` con dati finti per *tutte* le sezioni, compresa una scheda della Parte 3, Q4/Q10, le appendici e i grafici. La build finale fallisce se resta un segnaposto. Il pattern 0 ha la domanda già data dal testo, quindi si può partire da lì senza lo stadio gold.

### Dove i revisori contraddicono i tuoi tagli

- **Correlazione (taglio 5).** L'euristica "la sottoquery cita un alias esterno" manca i riferimenti non qualificati, frequenti nei modelli piccoli. Con lo schema già disponibile dal DDL, `qualify` + `is_correlated_subquery` costa poco. Proposta: `qualify` come controllo principale, l'euristica solo se `qualify` fallisce.
- **Giro in italiano (taglio 4).** "Facoltativo" significa logica condizionale nel template e una scelta all'ultimo momento. Proposta: tenerlo solo come esecuzione, senza giudice, cioè circa 30 chiamate economiche per la sola tabella EN contro IT. Oppure toglierlo formalmente dalla struttura con un flag.
- **Secondo giudice (taglio 3).** Senza secondo giudice, il reasoning della Parte 3 non ha più nessun controllo indipendente. Proposta: concentrare la tua lettura a campione sulle griglie del reasoning della Parte 3.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  - Il PDF con la stessa forma del piano: frontespizio, metodologia, Parti 1-3 con tutte le schede, conclusioni, appendici A-D.
  - EX su 5 istanze per mutazione.
  - Equivalenza tra strategie nei pattern 3, 5 e 6.
  - Secondo parere DeepSeek sul gold.
  - Giudice raggruppato con esito deterministico.
  - Testi in `narratives/` modificabili a mano.
  - Controlli finali: nome del file, termini vietati, campi del form.
  - Costo sotto i 15 $ con un controllo prima di ogni stadio.
* **Out-of-Scope Non-Goals:**
  - Arbitro Opus.
  - Generatore Faker.
  - Secondo giudice e kappa.
  - LM Studio.
  - Controllo statico completo della divisione, che decide il giudice.
  - Riproducibilità oltre le risposte registrate in cache.
  - `results.xlsx`, se non serve davvero.

## Alternatives Weighed

- **Arbitro Opus sui disaccordi del gold.** Rifiutato dall'autore: i disaccordi previsti sono pochi e la revisione manuale costa meno di uno stadio in più.
- **Generatore Faker generico con chiavi esterne.** Rifiutato dall'autore: è il componente più costoso del gold. Al suo posto ci sono mutazioni di un'istanza base.
- **Secondo giudice DeepSeek con kappa di Cohen in Parte 3.** Rifiutato dall'autore: è un controllo interno che non entra nel PDF. Lo sostituisce la lettura manuale.
- **Controlli statici completi (`traverse_scope` per la correlazione, AST per la divisione).** Rifiutati dall'autore, ma i revisori propongono di recuperare `qualify` per la correlazione (vedi sopra).
- **Selezione delle istanze per mutazione delle query.** Con sqlglot si generano versioni "quasi giuste" del gold e si tengono le mutazioni dei dati che le distinguono meglio. È più rigorosa e non costa chiamate, ma aggiunge codice. Da valutare.
- **Opus scrive un generatore Python con seed per ogni schema**, al posto degli INSERT. Da valutare.
- **Solo 2 istanze** (base più una avversaria). Da valutare: riduce il codice, ma indebolisce il confronto tra EX sull'istanza base ed EX su tutte le istanze.
- **Giudice più economico per le Parti 1-2** (DeepSeek o Sonnet), oppure commenti da template per i casi con EX=1. Da valutare se il giudice raggruppato non basta a stare nel budget.
- **Saltare DeepSeek sui pattern 3, 5 e 6**, quando l'equivalenza tra strategie è già superata. Da valutare.
- **Scrivere a mano il DDL della Biblioteca e le 7 domande della Parte 1** (circa 35 minuti). Da valutare.
- **`source_hash` sugli artefatti, `--freeze` sulla cache, `manifest.json` dei database.** Proposti dai revisori, rinviati: aggiungono meccanismi che il criterio "solo la forma del PDF" non richiede.
- **Renderer di riserva (Chromium headless).** Rinviato: basta verificare WeasyPrint allo step 0.

## Key Decisions & Staging for Next Steps

Decisioni già prese:
- i 5 tagli;
- l'ossatura del report dal giorno 1;
- il mantenimento dell'equivalenza tra strategie, del secondo parere DeepSeek e della cache.

Decisioni chiuse il 19 nov (recepite in `PianoDiImplementazione.md` v2):
1. Esito deterministico da EX; il giudice scrive solo il commento; flag `incoerenza` rimosso.
2. Giudice raggruppato: una chiamata per prompt (Parti 1-2), per query e giro (Parte 3).
3. Giro in italiano rimosso dal piano e dal PDF.
4. Correlazione con `qualify` + `is_correlated_subquery`; se `qualify` fallisce → "non verificabile".
5. Appendice B con reasoning completi.
6. Stack sostituito: `requests`, `duckdb`, `sqlglot`, `matplotlib`, `typst`, `python-dotenv`; report in Typst (nessuna dipendenza di sistema).
7. Tutti gli altri rilievi risolti nel piano con la regola "easier is better".

Ordine di lavoro proposto:

**Giorno 1:**
1. Correggere il piano e CLAUDE.md, e trascrivere il testo dell'esercitazione.
2. Step 0:
   - chiamata reale per ogni modello;
   - verifica del reasoning della Parte 3;
   - `effort=none` per Q4/Q10;
   - WeasyPrint;
   - colonne accentate.
3. `llm.py` con controllo di spesa, gestione dei troncamenti e `call_id`.
4. Ossatura `report --draft` con dati finti.
5. `gold`, con la revisione della Parte 3 fatta subito.
6. `eval`.
7. Parti 1-2.

**Giorno 2:**
1. Parte 3, giri 1 e 2.
2. Q4/Q10.
3. Giro in italiano, se deciso.
4. Testi in `narratives/`.
5. Revisione e controlli finali.
