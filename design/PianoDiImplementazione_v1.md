# Text2SQL PoliTo – Piano di implementazione con OpenRouter

Nov 18, 2026 · @Carlo Bianchi

## Panoramica

L'esercitazione diventa una pipeline Python riproducibile: una sola chiave OpenRouter chiama tutti i modelli, un modello forte genera domande e soluzioni attese, DuckDB esegue ogni query su database sintetici e un giudice LLM scrive le analisi. Il PDF finale esce da un comando.

Decisioni chiave:

- **Consegna**: un solo file `MATRICOLA_TextSQL.pdf` entro il 1 dicembre 2026, caricato in "Elaborati" sul Portale della Didattica. Il "file Excel" del testo diventa una serie di tabelle dentro il PDF; l'Excel resta solo come file di lavoro.
- **Accesso ai modelli**: OpenRouter (API compatibile OpenAI) sostituisce le web app di Parte 1 e 3 e LM Studio di Parte 2. Nel report dichiari ID esatto, parametri.
- **Valutazione**: execution accuracy su più istanze del database (test suite), controlli statici con sqlglot sulla strategia richiesta, giudice LLM per i commenti in italiano. Il giudice riceve l'esito dell'esecuzione, quindi commenta fatti verificati.

**Voce del report**: come concordato con il docente, il report presenta tutto in prima persona singolare, seguendo i passi della richiesta ("ho formulato la domanda", "ho scritto la soluzione attesa", "ho analizzato la risposta"). La pipeline è il tuo strumento di lavoro e nel report non compare.

**Soluzioni attese**: generate da Claude Opus 5.5, verificate da un secondo modello indipendente e dall'equivalenza tra strategie. Ti arrivano da rivedere solo i casi in disaccordo.

- **Modelli di supporto** (generazione, giudice) di famiglie non testate, Anthropic e DeepSeek, così nessun modello giudica se stesso.
- **Pattern**: il testo cita "3, 6, 7" per le soluzioni multiple, ma l'elenco va da 0 a 6. I pattern multipli sono 3 (JOIN/IN/INTERSECT), 5 (NOT IN/EXCEPT) e 6 (CTE/correlazione): in Parte 1 servono quindi 11 prompt per 7 domande.

## Architettura del progetto

Un solo repository con quattro stadi indipendenti, gold → run → eval → report, che si passano file JSON/JSONL. Ogni stadio si rilancia da solo e una cache su disco evita di ripagare chiamate già fatte.

&#91;embedded content: pipeline · 4 stadi, un ciclo di correzione in Parte 3\]

Il gold alimenta sia i run sia la valutazione; in Parte 3 l'esito della valutazione torna ai run come prompt aggiornato.

Stack: Python 3.12, `openai` (con `base_url="https://openrouter.ai/api/v1"`), `duckdb`, `sqlglot`, `faker`, `pydantic`, `tenacity`, `pandas`, `jinja2`, `weasyprint`, `pyyaml`, `python-dotenv`.

```text
text2sql-polito/
  .env                      # OPENROUTER_API_KEY, MATRICOLA
  config/models.yaml        # alias -> ID OpenRouter + parametri (tabella sezione Modelli)
  data/schemas/             # DDL: biblioteca.sql, p3_ex1.sql ... p3_ex5.sql
  data/questions/           # part1.yaml (7 domande), part3.yaml (Q1-Q10, testo dato)
  src/llm.py                # client unico: retry, cache, log costo, estrazione reasoning
  src/prompts.py            # template IT Parte 1/2, EN/IT Parte 3, suffissi di strategia
  src/gold/                 # generate_questions, generate_gold, build_dbs, validate_gold
  src/run/                  # part1.py, part2.py, part3.py
  src/eval/                 # execute.py, compare.py, static_checks.py, judge.py
  src/report/               # build_report.py + templates/report.html.j2
  cache/                    # una risposta grezza per hash di richiesta
  outputs/                  # gold.json, dbs/*.duckdb, calls.jsonl, evals.jsonl, report/
```

Il client `src/llm.py` è il pezzo da scrivere per primo:

1. Una funzione `chat(model_alias, messages, **overrides) -> CallRecord` che legge ID e parametri da `models.yaml`.
2. Parametri di default: `temperature=0`, `seed=42` dove supportato, `max_tokens` 4096 in Parte 1-2 e 16000 in Parte 3 (il reasoning consuma lo stesso budget di output).
3. Reasoning via `extra_body={"reasoning": {...}}`; aggiungi `"provider": {"require_parameters": true}` così OpenRouter instrada solo verso provider che rispettano quei parametri.
4. Dalla risposta salva `message.content`, `message.reasoning`, `message.reasoning_details` (il tipo dice se è testo grezzo o riassunto), `model` effettivamente servito, provider, `usage` e costo.
5. Cache: chiave = sha256 di modello + messaggi + parametri, file in `cache/`. Retry con backoff su 429 e 5xx.

Ogni chiamata diventa una riga di `outputs/calls.jsonl` con: `part`, `item_id`, `pattern`, `strategy`, `lang`, `prompt_version` (base/aggiornato), `model_alias`, `model_served`, `prompt`, `raw_output`, `reasoning`, `reasoning_type`, `sql`, `format_ok`, `usage`, `cost_usd`, `latency_s`, `timestamp`.

Estrazione dello SQL: togli i blocchi ```` ```sql ````, tieni l'ultimo statement che inizia con `SELECT` o `WITH`, e segna `format_ok=false` se il modello ha scritto altro oltre al codice (il prompt chiede "solamente il codice SQL": è un'osservazione utile per l'analisi).

Esecuzione: DuckDB, perché supporta `INTERSECT`, `EXCEPT`, CTE, subquery correlate e quasi tutte le funzioni data dei dialetti comuni. Ogni SQL passa da `sqlglot.transpile(sql, read="postgres", write="duckdb")` (fallback `read="mysql"`), poi gira con un timeout di 10 s (`con.interrupt()` da un thread). Verifica allo step 0 che le colonne accentate (`nazionalità`, `capacità`) passino sia in DuckDB sia in sqlglot; se no, nel DDL vanno tra virgolette.

Lanci previsti, da una CLI unica: `python -m src.cli gold`, `run --part 1|2|3`, `eval --part N`, `report`.

## Modelli per parte

Tutti gli ID qui sotto sono nel catalogo OpenRouter a oggi. Allo step 0 uno script li verifica con `GET /api/v1/models` e si ferma se ne manca uno: i nomi cambiano spesso, quindi in `models.yaml` cambi solo l'ID.

| Parte | Ruolo | ID OpenRouter | Parametri | Note |
| --- | --- | --- | --- | --- |
| 1 | ChatGPT | `openai/gpt-chat-latest` | `temperature=0` | Modello della chat ChatGPT, senza reasoning. È un alias: nel report va il `model_served` |
| 1 | Gemini | `google/gemini-3.8-flash` | `reasoning.effort="minimal"` | Flash come nell'app; se esce una Flash stabile più recente, usa quella |
| 1 | Codestral | `mistralai/codestral-2508` | `temperature=0` | Nessun reasoning né strumenti, come chiede il testo per le Chat |
| 2 | \~1B | `meta-llama/llama-3.2-1b-instruct` | `temperature=0` | Limite inferiore della scala |
| 2 | \~3B | `meta-llama/llama-3.2-3b-instruct` | `temperature=0` |  |
| 2 | \~4B | `google/gemma-3-4b-it` | `temperature=0` |  |
| 2 | 8B | `mistralai/ministral-8b-2512` | `temperature=0` | Confronto diretto con Codestral (stessa casa) |
| 2 | 8B | `qwen/qwen3-vl-8b-instruct` | `temperature=0` | Famiglia Qwen3 suggerita dal testo; variante VL, risponde normalmente a testo |
| 2 | opzionale | Qwen3-4B, Qwen3-8B, Phi-4-mini (3.8B) in LM Studio | stesso client, `base_url=http://localhost:1234/v1` | I modelli citati dal testo non sono su OpenRouter in taglia ≤ 8B; `microsoft/phi-4` è 14B, oltre il limite |
| 3 | Gemini 2.5 Flash | `google/gemini-2.5-flash` | reasoning dinamico di default | Restituisce un riassunto dei pensieri |
| 3 | Qwen3-235B-A22B | `qwen/qwen3-235b-a22b-thinking-2507` | `reasoning.max_tokens=4096` | Release 2507 dello stesso modello, solo thinking; reasoning completo |
| 3 | ChatGPT con reasoning | `openai/gpt-5.5` | `reasoning.effort="medium"` | OpenAI espone solo un riassunto del ragionamento, come l'interfaccia ChatGPT |
| 3 | ChatGPT senza reasoning (Q4, Q10) | `openai/gpt-5.5` | `reasoning.effort="none"` | Se il modello lo rifiuta (reasoning obbligatorio) usa `openai/gpt-chat-latest` |
| supporto | Generatore domande e gold, giudice, ottimizzatore di prompt | `anthropic/claude-opus-5.5` | effort `high` per il gold, `medium` per il giudice | Famiglia non testata: niente auto-preferenza |
| supporto | Secondo parere sul gold | `deepseek/deepseek-v4.1-flash-1017` | reasoning attivo | Indipendente da Anthropic e dai modelli testati, costo trascurabile |
| supporto | Arbitro dei disaccordi | `anthropic/claude-opus-5.5` | `reasoning.effort="high"` | Solo sui pochi casi in cui gold e secondo parere divergono |

Fonti: [catalogo modelli OpenRouter](https://openrouter.ai/api/v1/models), [documentazione reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens).

## Ground truth automatica (stadio `gold`)

Non scrivi a mano né domande né soluzioni attese: Claude Opus 5.5 le genera, e una soluzione diventa "attesa" solo se supera tre controlli automatici. Lo stesso stadio costruisce i database su cui tutto viene eseguito.

1. **DDL.** Opus scrive `biblioteca.sql` dalla descrizione del testo (PK, FK, `NOT NULL` sui campi senza asterisco, tipi `DATE`/`TIME`/`INTEGER`/`VARCHAR`/`DECIMAL`) e i 5 schemi della Parte 3. Lo script li carica in DuckDB: se non compilano, rigenera.
2. **Domande Parte 1** (`generate_questions`). Una chiamata per pattern con schema, definizione del pattern e questi vincoli:
   - Pattern 0: usa la domanda d'esempio del testo ("libri fantasy con almeno 3 copie"), che va completata.
   - Domanda in italiano, senza ambiguità, con le colonne di output nominate esplicitamente (rende possibile il confronto automatico).
   - Pattern 3, 5, 6: la stessa domanda deve avere risposta identica con ogni strategia. Per `INTERSECT` proietta chiavi o usa `DISTINCT` (INTERSECT elimina i duplicati, una JOIN no); per `NOT IN` usa una colonna non nullabile, altrimenti NOT IN ed EXCEPT divergono sui `NULL`.
   - Pattern 4: domanda "per ogni / tutti" (es. lettori che hanno preso in prestito tutti i libri di un dato autore).
   - Coprire tabelle diverse (sale, dipendenti, prenotazioni), non solo LIBRO.
   - Output JSON: `id`, `pattern`, `domanda`, `colonne_output`, `assunzioni`, `gold_sql` per ogni strategia. Chiedi 3 candidati per pattern: la validazione tiene il primo che passa tutto.
3. **Gold Parte 3.** I testi Q1-Q10 sono dati. Opus scrive la soluzione e un elenco esplicito delle interpretazioni (es. Q1: "copie vendute" = numero di righe di SALE per ISBN; Q3: unità di `Duration`). Le interpretazioni finiscono nel report e nell'input del giudice, che deve accettare letture alternative ragionevoli.
4. **Database di test** (`build_dbs`). Per ogni schema 5 istanze DuckDB:
   - Istanza base: un generatore Faker `it_IT` con seed fisso (20-60 righe per tabella, PK e FK rispettate) più righe "trappola" scritte da Opus per ogni domanda, perché gli errori tipici diano risultati diversi dal gold: `DISTINCT` mancante, `NOT IN` con `NULL`, `>` contro `>=`, `HAVING` dimenticato, prestiti con `data_restituzione` nulla, autori senza libri, pareggi.
   - 4 istanze casuali: stesso generatore, seed diversi e domini piccoli (pochi generi, poche date) per forzare collisioni. È l'idea della "test suite accuracy" (Zhong, Yu, Klein, EMNLP 2020): una query sbagliata difficilmente coincide col gold su tutte le istanze.
   - Vincolo: sull'istanza base il gold deve restituire almeno una riga e non tutta la tabella.
5. **Validazione** (`validate_gold`), su tutte le 5 istanze:
   - Equivalenza tra strategie: per i pattern 3, 5, 6 tutte le varianti danno lo stesso risultato.
   - Conformità al pattern: controllo statico con sqlglot che il gold usi il costrutto richiesto (vedi Valutazione automatica).
   - Secondo parere: DeepSeek V4.1 scrive la propria query da domanda e schema, senza vedere il gold. Risultati uguali su tutte le istanze → `verificato`.
   - Disaccordo → Claude Opus 5.5 (`reasoning.effort="high"`) riceve le due query e le righe che differiscono, decide e motiva → `arbitrato`. Se giudica la domanda ambigua: in Parte 1 la domanda si riscrive, in Parte 3 si registra l'interpretazione scelta.

Risultato: `outputs/gold.json` con stato `verificato`, `arbitrato` o `da_rivedere` per ogni voce. Tu leggi solo gli ultimi due: da prevedere 0-3 casi.

## Parte 1 – modelli proprietari

Parte 1 sono 11 prompt × 3 modelli = 33 chiamate, tutte in italiano sullo schema Biblioteca.

1. **Prompt base** in `prompts.py`: il testo d'esempio del PDF parola per parola (ruolo, "solamente il codice SQL", `Tabelle:` con le chiavi primarie, nota sull'asterisco, `Domanda:`, `Codice SQL:`). Inviato come unico messaggio `user`, senza system prompt, per imitare la chat web.
2. **Varianti di strategia**: prima di `Codice SQL:` aggiungi una riga fissa, es. "Risolvi la query utilizzando obbligatoriamente l'operatore INTERSECT." Lista completa:

| Pattern | Contenuto | Prompt |
| --- | --- | --- |
| 0 | Proiezione: `WHERE` (+ `ORDER BY`) | 1 |
| 1 | `JOIN` | 1 |
| 2 | `GROUP BY` + `HAVING` + aggregata | 1 |
| 3 | JOIN / IN / INTERSECT | 3 |
| 4 | Divisione | 1 |
| 5 | NOT IN / EXCEPT | 2 |
| 6 | CTE / correlazione | 2 |

3. **Esecuzione**: `python -m src.cli run --part 1` chiama GPT, Gemini e Codestral su ogni prompt e scrive `calls.jsonl`.
4. **Valutazione**: `eval --part 1` produce per ogni chiamata esito di esecuzione, conformità alla strategia, rispetto del formato e il commento del giudice (sezione Valutazione automatica).
5. **Commento generale**: una chiamata di sintesi a Opus con la tabella aggregata (accuratezza per modello × pattern, categorie di errore, conformità, formato). Scrive i tre punti del testo: punti forti e deboli di ogni LLM, confronto tra LLM, confronto tra tipi di prompt. Lo rileggi tu.

Campi del form e da dove arrivano:

| Campo del form | Fonte automatica |
| --- | --- |
| Pattern di difficoltà | `part1.yaml` |
| Domanda | `gold.json` (generata da Opus, validata) |
| Soluzione attesa | `gold.json`, una per strategia nei pattern 3, 5, 6 |
| Prompt | `prompts.py` + domanda + riga di strategia |
| GPT / Gemini / Codestral | `calls.jsonl`, campo `sql` (e `raw_output` se c'è testo extra) |
| Analisi GPT / Gemini / Codestral | `evals.jsonl`: commento del giudice + esito esecuzione |
| Commento generale | chiamata di sintesi, rivista da te |

## Parte 2 – modelli open source ≤ 8B

Parte 2 riusa gli stessi 11 prompt della Parte 1, byte per byte, su 5 modelli da 1B a 8B: 55 chiamate. Cambia solo l'alias del modello, così ogni differenza è attribuibile al modello.

1. `run --part 2` sui 5 modelli della tabella Modelli. Se vuoi restare fedele a LM Studio per Qwen3 e Phi-4-mini, aggiungili in `models.yaml` con `base_url: http://localhost:1234/v1`: il client non cambia.
2. `eval --part 2` identico alla Parte 1.
3. Annota per ogni modello la quantizzazione: in locale la scegli tu (es. Q4\_K\_M), su OpenRouter dipende dal provider, che è salvato in `calls.jsonl`.
4. Sintesi a Opus con le metriche di Parte 1 e Parte 2 insieme. Domande guida: a che taglia il modello smette di produrre SQL eseguibile, quali pattern cedono per primi (di solito divisione e correlazione), quanto spesso i piccoli ignorano "solamente il codice SQL" o la strategia imposta, quanto distano dal migliore modello proprietario.
5. Nel report: lo stesso form della Parte 1 con una colonna per modello, più un grafico accuratezza (asse y) per numero di parametri (asse x).

## Parte 3 – modelli con reasoning su query complesse

Parte 3 sono 10 query × 3 modelli in due giri (prompt base e, se serve, prompt aggiornato), più GPT senza reasoning su Q4 e Q10 e un giro in italiano: circa 95 chiamate.

Attenzione: nel PDF le chiavi primarie sono indicate solo dalla sottolineatura, che si perde copiando il testo. Eccole, da mettere nel DDL e nei prompt:

```text
Es.1  BOOK_PUBLISHED(ISBN)  AUTHOR(AuthorCode)  SALE(SaleCode)
Es.2  STUDENT(StudentCode)  TEACHER(TeacherCode)  CONSULTATION(TeacherCode, Date, StartTime)
Es.3  CLASSROOM(ClassroomCode)  COURSE(CourseCode)  LECTURE(ClassroomCode, Date, StartTime)
Es.4  ROUTE(RouteCode)  FLIGHT(RouteCode, Date, DepartureTime)  TICKET(TicketCode)  BOARDING_PASS(TicketCode)
Es.5  CUSTOMER(CustomerCode)  HOTEL(HotelCode)  HOTEL_ROOM(RoomNumber, HotelCode)  BOOKING(RoomNumber, HotelCode, StartDate)
```

1. **Prompt inglese**: il testo cita un "prompt in inglese fornito come esempio" che nel PDF non c'è, quindi traduci il template della Parte 1 ("You are an AI assistant that writes SQL queries from a textual question… Return only the SQL code. Tables: … with primary key … Question: … SQL code:"). Domande Q1-Q10 copiate alla lettera.
2. **Giro 1** (`run --part 3 --round 1`): 30 chiamate con i parametri di reasoning della tabella Modelli. Salva separati `reasoning` e `sql`. Il tipo di reasoning va dichiarato: Qwen restituisce il testo completo, Gemini e GPT un riassunto; se un modello non lo espone, il campo dice "non esposto dall'API".
3. **Valutazione giro 1**: esecuzione + giudice con la griglia del testo (reasoning corretto? passi mancanti, errati, fuori ordine, ridondanti? la soluzione segue il reasoning?).
4. **Prompt aggiornato**, solo per le coppie query-modello sbagliate. Opus riceve prompt, reasoning, SQL del modello e analisi del giudice, ma non il gold, e scrive integrazioni mirate (es. chiarire che "copies sold" sono righe di SALE, ricordare che una coppia docente-studente può avere più consulenze nello stesso giorno). Controllo anti-leak automatico: il nuovo prompt non può contenere SQL né frammenti del gold; se li contiene, si rigenera.
5. **Giro 2**: stesso modello, prompt aggiornato, poi stessa valutazione. Un solo giro di correzione, come nel testo.
6. **Q4 e Q10 senza reasoning**: GPT con `effort="none"` e lo stesso prompt usato con reasoning (aggiornato, se c'è). Campi Output (testo in linguaggio naturale, se il modello ne scrive) e Soluzione, con le domande di analisi del testo.
7. **Confronti**: per ogni query una chiamata di sintesi dai giudizi strutturati produce "Confronto modelli (reasoning)" e "Confronto modelli (soluzione SQL)"; per Q4 e Q10 anche "Confronto modelli GPT" con e senza reasoning.
8. **Giro in italiano**: il testo suggerisce di provare anche l'italiano dopo l'inglese. Rilancia il giro 1 con il prompt tradotto e riporta solo una tabella di accuratezza inglese contro italiano per modello.

## Valutazione automatica (stadio `eval`)

La correttezza la decide l'esecuzione, non un LLM: il giudice spiega l'esito e lo classifica, ma non può contraddirlo senza che il caso venga segnalato a te. Quattro livelli, in quest'ordine.

**1. Sintassi ed esecuzione.** sqlglot fa il parse e la traduzione in DuckDB, poi la query gira su ognuna delle 5 istanze. Esiti: `parse_error`, `exec_error` (con messaggio), `timeout`, `ok`.

**2. Confronto dei risultati** (`compare.py`), istanza per istanza:

- Normalizza i valori: `NULL` come token, numeri arrotondati a 4 decimali, `Decimal` in float, date e orari in ISO, stringhe senza spazi ai bordi.
- Se il gold ha `ORDER BY` al livello esterno confronta liste ordinate, altrimenti multinsiemi (`Counter` di tuple).
- Ordine delle colonne indifferente: con lo stesso numero di colonne prova le permutazioni, come la valutazione ufficiale di Spider.
- Colonne in più ma proiezione corretta → flag `colonne_extra` (parzialmente corretta). Stesso insieme ma molteplicità diverse → flag `duplicati` (tipico `DISTINCT` mancante).
- Metrica principale: EX = 1 se il risultato coincide su tutte le 5 istanze. Riporta anche EX sulla sola istanza base: la differenza mostra quante query "sembrano" giuste solo per caso.

**3. Controlli statici con sqlglot** (`static_checks.py`), sia sul gold sia sulle risposte:

| Requisito | Controllo sull'AST |
| --- | --- |
| Proiezione (P0) | `exp.Where` presente |
| JOIN | `exp.Join` presente (esplicita o implicita con virgola) |
| GROUP BY + HAVING + aggregata (P2) | `exp.Group`, `exp.Having`, almeno un `exp.AggFunc` |
| IN | `exp.In` con sottoquery, non negato |
| NOT IN | `exp.Not` sopra `exp.In` con sottoquery |
| INTERSECT / EXCEPT | `exp.Intersect` / `exp.Except` |
| CTE | `exp.With` |
| Correlazione | dopo `qualify`, uno scope di `traverse_scope` con `is_correlated_subquery` |
| Divisione (P4) | doppio `NOT EXISTS`, oppure `HAVING COUNT(…) = (SELECT COUNT(…) …)`, oppure `EXCEPT` annidato; in dubbio decide il giudice |

Ne esce `rispetta_strategia` (sì/no): una query corretta ma con la strategia sbagliata è un risultato da commentare, non un errore di esecuzione.

**4. Giudice LLM** (`judge.py`, Claude Opus 5.5, risposta JSON validata con pydantic). Input: schema, domanda, interpretazioni del gold, gold per ogni strategia, strategia richiesta, SQL del modello, esito su ogni istanza, fino a 5 righe mancanti o in più sulla prima istanza che fallisce, controlli statici, `format_ok`; in Parte 3 anche il reasoning.

Output Parte 1 e 2:

```json
{"esito": "corretta | parzialmente corretta | errata",
 "rispetta_strategia": true,
 "categorie_errore": ["join", "duplicati"],
 "commento": "max 60 parole, in italiano"}
```

Output Parte 3, ricalcato sulle domande del testo:

```json
{"reasoning_corretto": "sì | parzialmente | no",
 "passi_mancanti": [], "passi_errati": [], "passi_fuori_ordine": [], "passi_ridondanti": [],
 "commento_reasoning": "...",
 "soluzione_corretta": "sì | no",
 "segue_reasoning": "sì | parzialmente | no",
 "commento_soluzione": "...",
 "suggerimenti_prompt": []}
```

Categorie di errore fisse, così si possono contare: sintassi, schema linking (tabella o colonna errata o inventata), join, filtro, aggregazione, HAVING, NULL, duplicati, ordinamento, colonne di output, strategia non rispettata, logica di divisione, subquery o correlazione, interpretazione della domanda, formato dell'output.

Stile dei commenti: il giudice scrive `commento`, `commento_reasoning` e `commento_soluzione` in prima persona singolare, con il tono di uno studente che analizza la risposta, senza citare giudici, modelli di supporto o pipeline. Così i testi entrano nel report senza ritocchi.

Affidabilità del giudice:

- **Coerenza con l'esecuzione**: se `esito` contraddice EX il record prende il flag `incoerenza` e lo rivedi tu.
- **Reasoning (Parte 3)**: qui non c'è un'esecuzione che faccia da verità, quindi un secondo giudice (DeepSeek V4.1) compila la stessa griglia. Calcola l'accordo tra giudici (percentuale e kappa di Cohen su `reasoning_corretto`) e rileggi i casi in disaccordo.
- **Controllo a campione**: leggi 10 giudizi scelti a caso e annota se sei d'accordo. Il tasso d'accordo resta un controllo interno, fuori dal report.

Metriche aggregate per il report: EX per modello e per pattern, conformità alla strategia, rispetto del formato, distribuzione delle categorie d'errore, costo e latenza per modello; in Parte 3 anche correttezza al giro 1 contro giro 2, quota di reasoning corretti e coerenza reasoning-soluzione.

## Report finale (stadio `report`)

Il report è un PDF unico generato da `gold.json`, `calls.jsonl` ed `evals.jsonl` con un template Jinja2 → HTML → WeasyPrint, salvato come `outputs/report/<MATRICOLA>_TextSQL.pdf`. Il corpo resta sintetico, come chiedono le regole di consegna; il materiale lungo va in appendice.

Struttura:

1. **Frontespizio**: titolo, nome, matricola, Master, data.
2. **Metodologia** (1 pagina): come ho interrogato i modelli (OpenRouter al posto delle web app e di LM Studio: prompt identici, parametri fissi, riproducibilità), tabella modelli con ID e parametri, i database su cui ho eseguito le query, i criteri con cui ho valutato correttezza e strategia. Nessuna sezione su come sono state prodotte soluzioni attese e analisi.
3. **Parte 1**: tabella riassuntiva EX modello × pattern, poi una scheda per pattern con Pattern, Domanda, Soluzione attesa (una per strategia), Prompt, e per ogni modello SQL generato + Analisi con l'esito evidenziato. Chiude il Commento generale.
4. **Parte 2**: stesse schede con una colonna per modello, grafico accuratezza per taglia, confronto con la Parte 1.
5. **Parte 3**: per ogni query soluzione attesa e interpretazioni, prompt, e per ogni modello un estratto del reasoning (circa 15 righe), SQL, griglia di analisi del reasoning e della soluzione, prompt aggiornato e risultati del giro 2. Poi i due Confronti modelli. Sezione dedicata a Q4 e Q10 senza reasoning e tabella inglese contro italiano.
6. **Conclusioni** (mezza pagina).
7. **Appendici**: A prompt completi (lo schema si ripete identico, quindi nel corpo il prompt compare per intero solo in P0 e Q1), B reasoning completi (è il campo "Reasoning (continua)" del form), C DDL e statistiche dei database di test, D costo e numero di chiamate per modello.

Dettagli di impaginazione: A4, numeri di pagina via `@page`, SQL in monospace evidenziato con Pygments, `page-break-inside: avoid` sulle schede, grafici matplotlib in SVG.

I testi discorsivi (commenti generali, confronti, conclusioni) li scrive Opus in `outputs/narratives/*.md`. Il builder li legge da lì: modificali a mano e le tue modifiche sopravvivono a ogni rigenerazione del PDF.

Voce: il prompt di Opus per `narratives/` e per i commenti impone la prima persona singolare e i verbi della richiesta ("ho formulato", "ho scritto la soluzione attesa", "ho analizzato"), come concordato con il docente. Evita però frasi esplicite tipo "senza usare LLM": non servono e andrebbero oltre l'accordo. Conserva la mail del docente insieme al progetto.

Controlli automatici finali: nome file conforme a `^\d+_TextSQL\.pdf$`, nessun campo vuoto o `TODO`, ogni scheda con tutti i campi del form, PDF che si apre e numero di pagine stampato a console. Esporta anche un `results.xlsx` con le colonne del form: ti serve per lavorare, ma non va consegnato, perché la consegna è un file solo.

Controllo di coerenza della voce: il PDF non deve citare Opus, DeepSeek, Fable, "giudice" o "gold", e i testi devono essere in prima persona singolare. Lo script fa un grep e stampa le righe da sistemare.

## Piano operativo

Servono circa due giorni di lavoro: domani infrastruttura, gold, valutazione e Parti 1-2; il secondo giorno Parte 3, report e revisione. Scadenza: Dec 1, 2026. Puoi passare questo documento a Claude Code come specifica, uno stadio alla volta.

Giorno 1:

- [ ] Setup (45 min): account OpenRouter, 15 $ di credito, chiave con limite di spesa, `.env`, virtualenv e dipendenze. Script `check_models.py` che verifica gli ID di `models.yaml` e una prova DuckDB/sqlglot con le colonne accentate.
- [ ] Client `llm.py` (45 min): cache, retry, estrazione di reasoning e costo, una chiamata di prova per ogni modello.
- [ ] Stadio `gold` (2 h): DDL, domande Parte 1, gold Parte 1 e 3, 30 database DuckDB, validazione. Rileggi le voci `arbitrato` e `da_rivedere`.
- [ ] Stadio `eval` (1 h 30): `execute`, `compare`, `static_checks`, `judge`. Lo scrivi prima dei run: puoi collaudarlo subito sulle query del secondo parere DeepSeek.
- [ ] Parte 1 e Parte 2 (1 h): `run` + `eval`, prima occhiata alle tabelle EX.

Giorno 2:

- [ ] Parte 3 (2 h): giro 1, prompt aggiornati, giro 2, Q4/Q10 senza reasoning, giro in italiano, secondo giudice.
- [ ] Report builder (2 h): template, grafici, appendici, controlli finali sul file.
- [ ] Revisione (1 h 30): casi `incoerenza`, disaccordi tra giudici, 10 giudizi a campione, testi in `narratives/`.
- [ ] Consegna: carica `<MATRICOLA>_TextSQL.pdf` in "Elaborati" sul Portale della Didattica, con qualche giorno di margine sulla scadenza.

## Rischi, costi e cosa dichiarare

Con l'accordo del docente sulla prima persona, la questione di chi ha scritto cosa è chiusa. Restano i rischi tecnici qui sotto, quasi tutti sulla qualità dei dati e sul confronto con le web app.

| Rischio | Mitigazione nel piano | Nel report |
| --- | --- | --- |
| Soluzioni attese sbagliate, valutazione circolare | Famiglia non testata, secondo parere indipendente, equivalenza tra strategie, test su 5 istanze; rileggi i casi `arbitrato` e `da_rivedere` | Nulla: è controllo interno |
| API diverse dalle web app (system prompt, strumenti, versione) | ID e parametri fissati, `model_served` salvato | Una riga in metodologia |
| Modelli non identici al testo (Qwen3 release 2507, Gemini 2.5 Flash non più "experimental", Parte 2 su OpenRouter) | Stessa famiglia e taglia; opzione LM Studio per Qwen3 e Phi-4-mini | Sì, nella tabella modelli |
| Reasoning di GPT e Gemini solo in forma riassunta | Campo `reasoning_type` per ogni chiamata | Sì, limita la profondità dell'analisi |
| Errori dovuti al dialetto SQL (es. funzioni data di MySQL) e non alla logica | Transpilazione con sqlglot; categoria "dialetto" contata a parte | Solo se capita |
| Modelli piccoli quantizzati dal provider | Provider salvato per ogni chiamata | Sì, in Parte 2 |
| Risposte non deterministiche anche a `temperature=0` | La cache congela le risposte usate nel report | Una riga |
| Testi generati generici o ripetitivi | Stanno in `narratives/`, li rileggi e li ritocchi | Il report lo firmi tu: rileggilo tutto una volta |

Costo: circa 250 chiamate in tutto (≈ 33 Parte 1, 55 Parte 2, 95 Parte 3, il resto tra gold e giudici). La stima è nell'ordine di pochi dollari, dominata dai giudizi di Opus e dal reasoning della Parte 3; un limite di 15 $ sulla chiave basta e ti protegge da cicli sbagliati.
