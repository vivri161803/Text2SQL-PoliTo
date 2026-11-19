# Text2SQL PoliTo – Piano di implementazione (v2, semplificato)

19 nov 2026 · sostituisce la v1 (`PianoDiImplementazione_v1.md`, solo per archivio)

## Panoramica

L'esercitazione (`EsercitazionePoliTo.pdf`) diventa una pipeline Python riproducibile. I passi sono questi:

1. Una sola chiave OpenRouter chiama tutti i modelli.
2. Un modello forte genera domande e soluzioni attese.
3. DuckDB esegue ogni query su 5 istanze di database.
4. Un modello scrive i commenti in italiano, raggruppando i giudizi.
5. Typst produce il PDF finale con un solo comando.

Regola guida del progetto: **la soluzione più semplice vince**. Conta solo che il PDF finale abbia la forma descritta nella sezione Report. Come lo si ottiene è secondario.

Consegna: un solo file `MATRICOLA_TextSQL.pdf`, da caricare entro il 1 dicembre 2026 in "Elaborati" sul Portale della Didattica. Il "file Excel" del testo diventa una serie di schede dentro il PDF.

Accordi con il docente, per mail (da conservare con il progetto):
- OpenRouter al posto delle web app e di LM Studio;
- automazione completa: domande, soluzioni attese, analisi, commenti;
- report in prima persona singolare.

## Decisioni rispetto alla v1

Tolti:
- **Arbitro Opus sul gold.** I disaccordi della Parte 3 arrivano a me. In Parte 1 un disaccordo scarta il candidato.
- **Generatore Faker.** Ogni schema ha un'istanza base scritta da Opus, con righe trappola. Le altre 4 istanze nascono da mutazioni deterministiche in Python.
- **Secondo giudice e kappa in Parte 3.** Li sostituisce la mia lettura a campione delle griglie di reasoning.
- **Giro in italiano della Parte 3.** Fuori dal piano e fuori dal PDF.
- **Flag `incoerenza`.** L'esito lo calcola l'esecuzione e il modello scrive solo il commento.
- **Arbitro dei controlli statici sulla divisione.** Restano controlli statici semplici più un'indicazione del giudice solo per il pattern 4.
- **`results.xlsx`, LM Studio, transpilazione sempre attiva.**
- **Stack della v1:** `openai`, `pydantic`, `tenacity`, `pandas`, `pyyaml`, `jinja2`, `weasyprint`, `pygments`, `faker`.

Introdotti:
- **Giudizi raggruppati.** Una chiamata per prompt giudica tutti i modelli insieme.
- **Report in Typst** con dati in JSON, senza dipendenze di sistema.
- **Parametri espliciti per ogni modello**, senza `seed`.
- **Controllo di spesa** su ogni chiamata.
- **Output degli stadi in file JSON riscritti per intero**, senza file in sola aggiunta. Così i rilanci non creano duplicati.
- **Più varianti accettate di soluzione attesa** in Parte 3, una per interpretazione ragionevole.

Tenuti:
- equivalenza tra strategie (pattern 3, 5, 6) su tutte le istanze;
- secondo parere DeepSeek sul gold;
- cache su disco;
- EX su 5 istanze;
- testi in `narratives/` modificabili a mano;
- voce in prima persona;
- controlli finali sul file.

## Stack

Python ≥ 3.11. Pacchetti: `requests`, `duckdb`, `sqlglot`, `matplotlib`, `typst` (compilatore Typst come pacchetto pip, senza Pango, LaTeX o browser) e `python-dotenv`.

```sh
python3 -m venv .venv
.venv/bin/pip install requests duckdb sqlglot matplotlib typst python-dotenv
```

Scelte:
- `requests` al posto dell'SDK `openai`: i campi specifici di OpenRouter (`reasoning`, `reasoning_details`, `provider`, `usage.cost`) arrivano già nel JSON grezzo.
- Il retry è un ciclo di 4 tentativi con attesa esponenziale.
- Configurazione in un modulo Python (`src/config.py`), non in YAML.
- Validazione JSON con controlli espliciti sulle chiavi, senza pydantic.

## Struttura del repository

```text
.env                         # OPENROUTER_API_KEY, MATRICOLA, NOME, SPESA_MAX_USD=12
EsercitazionePoliTo.pdf      # testo dell'esercitazione (fonte)
src/
  config.py                  # modelli, parametri, percorsi
  assignment.py              # testi verbatim: prompt P1, schemi, Q1-Q10, prompt EN (vedi Appendice)
  llm.py                     # chat(): cache, retry, costo, reasoning, controllo di spesa
  db.py                      # DDL, istanze base, mutazioni, esecuzione con timeout
  evaluate.py                # confronto risultati, controlli statici, esito
  gold.py                    # domande P1, gold P1/P3, secondo parere, dati, validazione
  runs.py                    # run Parte 1, 2, 3 (giri 1-2, Q4/Q10 senza reasoning)
  judge.py                   # giudizi raggruppati, ottimizzatore prompt, confronti, narrative
  report.py                  # dati JSON per Typst, grafico, controlli finali, compilazione
  cli.py
data/schemas/*.sql           # 6 DDL scritti a mano in fase di sviluppo (biblioteca, p3_ex1..5)
data/gold_overrides.json     # decisioni mie sul gold, applicate per ultime
templates/report.typ
fixtures/                    # dati finti per report --draft
cache/                       # una risposta grezza per richiesta
outputs/                     # gold.json, dbs/, calls_p1.json, calls_p2.json, calls_p3.json,
                             # evals_p1.json ..., narratives/*.md, report/
```

CLI:

```sh
python -m src.cli check                 # step 0
python -m src.cli gold
python -m src.cli run --part 1|2|3 [--round 1|2]
python -m src.cli eval --part 1|2|3 [--round 1|2]
python -m src.cli report [--draft]
```

Ogni stadio legge i file degli stadi precedenti e **riscrive per intero** il proprio file di output, come dizionario indicizzato per `call_id`. Se cambio il gold, rilancio gli stadi a valle. Non c'è altro meccanismo di invalidazione.

## Client LLM (`src/llm.py`)

`chat(alias, messages, role="tested"|"support", **overrides) -> dict`

1. Legge l'ID e i parametri da `config.py`. Invia **solo** i parametri elencati per quel modello e nessun `seed` globale.
2. Aggiunge sempre `"usage": {"include": true}`, così la risposta riporta il costo.
3. Il campo `"provider": {"require_parameters": true}` va solo nelle chiamate che passano `reasoning`.
4. Cache: la chiave è lo sha256 del JSON canonico (chiavi ordinate) di `base_url`, `model`, `messages` e dei parametri inviati. Il file in `cache/` contiene la risposta completa, il costo e la latenza. Se la risposta arriva dalla cache, il record riporta il costo originale.
5. Errori:
   - 429 e 5xx: retry con backoff;
   - **402: errore fatale**, senza retry;
   - risposta con `finish_reason="length"` e contenuto vuoto: non va in cache. Si ritenta una volta con `max_tokens` raddoppiato. Se fallisce di nuovo, il record ha `format_ok=false` e la categoria "formato dell'output".
6. Controllo di spesa: prima di ogni chiamata non in cache somma i costi in `cache/` e si ferma se il totale supera `SPESA_MAX_USD`.
7. Il record restituito contiene:
   - identificazione: `call_id`, `role`, `part`, `item_id`, `pattern`, `strategy`, `round`, `model_alias`;
   - risposta: `model_served`, `provider`, `generation_id`, `params_sent`, `prompt`, `raw_output`, `reasoning`, `reasoning_type`, `finish_reason`, `sql`, `format_ok`;
   - consumi: `usage`, `cost_usd`, `latency_s`, `timestamp`.

   `call_id` è l'hash di (part, item_id, strategy, round, model_alias).

Il reasoning si prende da `message.reasoning`. Il tipo si legge da `message.reasoning_details[].type`: testo completo o riassunto. Se manca, il campo vale "non esposto dall'API".

Estrazione dello SQL:
- togliere i blocchi ```` ```sql ````;
- tenere l'ultimo statement che inizia con `SELECT` o `WITH`;
- `format_ok=false` se c'è altro testo.

Il testo che resta, tolto lo SQL, è `nl_output`: serve al campo "Output" di Q4/Q10.

## Modelli e parametri

Gli ID sono quelli della v1. Allo step 0 ognuno riceve una **chiamata reale** con i parametri esatti, non basta il catalogo. Se un ID non risponde, si cambia solo in `config.py`.

| Parte | Alias | ID OpenRouter | Parametri inviati | `max_tokens` |
| --- | --- | --- | --- | --- |
| 1 | gpt | `openai/gpt-chat-latest` | `temperature=0` | 4096 |
| 1 | gemini | `google/gemini-3.8-flash` | `temperature=0`, `reasoning.effort="minimal"` | 4096 |
| 1 | codestral | `mistralai/codestral-2508` | `temperature=0` | 4096 |
| 2 | llama-1b | `meta-llama/llama-3.2-1b-instruct` | `temperature=0` | 4096 |
| 2 | llama-3b | `meta-llama/llama-3.2-3b-instruct` | `temperature=0` | 4096 |
| 2 | gemma-4b | `google/gemma-3-4b-it` | `temperature=0` | 4096 |
| 2 | ministral-8b | `mistralai/ministral-8b-2512` | `temperature=0` | 4096 |
| 2 | qwen3-8b | `qwen/qwen3-vl-8b-instruct` | `temperature=0` | 4096 |
| 3 | gemini-2.5 | `google/gemini-2.5-flash` | `reasoning.enabled=true` (esplicito, per ricevere i pensieri) | 16000 |
| 3 | qwen3-235b | `qwen/qwen3-235b-a22b-thinking-2507` | `reasoning.max_tokens=4096` | 16000 |
| 3 | gpt-r | `openai/gpt-5.5` | `reasoning.effort="medium"` (nessuna `temperature`) | 16000 |
| 3 | gpt-nr (Q4, Q10) | `openai/gpt-5.5` | `reasoning.effort="none"`; se rifiutato, `openai/gpt-chat-latest` con `temperature=0`, dichiarandolo nel report | 4096 |
| supporto | opus-gold | `anthropic/claude-opus-5.5` | `reasoning.effort="high"` (nessuna `temperature`) | 16000 |
| supporto | opus-judge | `anthropic/claude-opus-5.5` | `reasoning.effort="low"` in Parte 1-2, `"medium"` in Parte 3 | 12000 |
| supporto | opus-text | `anthropic/claude-opus-5.5` | `reasoning.effort="low"` (narrative, confronti, ottimizzatore) | 6000 |
| supporto | deepseek | `deepseek/deepseek-v4.1-flash-1017` | `reasoning.enabled=true` | 8000 |

Ogni alias ha anche due campi:
- `in_report`: vale `true` solo per i modelli testati;
- `params_b`: il numero di parametri in miliardi, per l'asse x del grafico della Parte 2.

## Step 0 (`check`)

1. Una chiamata reale per ogni alias con un prompt minimo. Stampa per ognuno `model_served`, provider, costo e parametri accettati.
2. Per i 3 modelli della Parte 3, una chiamata con Q1: verifica che `reasoning` non sia vuoto e stampa `reasoning_type`.
3. `gpt-nr`: verifica che `effort="none"` venga accettato. In caso contrario attiva il fallback.
4. DuckDB e sqlglot con le colonne accentate (`nazionalità`, `capacità`): `CREATE`, `SELECT` e parse. Se uno dei due fallisce, nei DDL e nei prompt le colonne vanno tra virgolette doppie.
5. Compilazione Typst di una pagina di prova con SQL e caratteri accentati.

## Database (`src/db.py`)

**DDL.** I 6 file `data/schemas/*.sql` si scrivono una volta in fase di sviluppo, con le chiavi dell'Appendice:
- PK e FK;
- `NOT NULL` su tutti i campi senza asterisco;
- tipi `DATE`, `TIME`, `INTEGER`, `VARCHAR`, `DECIMAL`.

In Parte 3 le FK sono quelle implicite nei nomi, per esempio `SALE.ISBN → BOOK_PUBLISHED`. Non si generano a runtime.

**Istanza base**: una chiamata `opus-gold` per schema, dopo le domande e il gold.
- Input: DDL, domande dello schema, soluzioni attese.
- Output: `INSERT` con 20-60 righe per tabella, più righe trappola per ogni domanda. Le trappole fanno dare risultati diversi dal gold agli errori tipici:
  - `DISTINCT` mancante;
  - `>` contro `>=`;
  - `HAVING` dimenticato;
  - prestiti con `data_restituzione` nulla;
  - autori senza libri;
  - pareggi.
- La trappola sui `NULL` riguarda una colonna nullabile *diversa* da quella usata da `NOT IN`, che è non nullabile per regola.
- Se il gold di una domanda restituisce 0 righe, o tutta la tabella, si chiede a Opus una sola patch di `INSERT` per quella domanda, da aggiungere in coda, al massimo 2 volte.

**4 istanze mutate**, deterministiche e con seed fisso. Partono dalla base e non toccano mai chiavi né tabelle padre, quindi le FK restano valide per costruzione.

| Istanza | Mutazione |
| --- | --- |
| m1 | elimina il 30% delle righe di ogni tabella figlia |
| m2 | mette a `NULL` il 50% dei valori delle colonne nullabili |
| m3 | duplica il 30% delle righe figlie con chiave nuova (`INSERT OR IGNORE`): intero → max+1, data/ora → +1 giorno |
| m4 | m1 + m2 + m3 con un seed diverso |

Le mutazioni non toccano i valori letterali usati dalle domande (es. 'fantasy') e il gold resta interpretabile.

Vincolo: ogni gold deve restituire almeno una riga su almeno 3 istanze su 5. Lo stadio stampa il numero di righe per ogni istanza.

**Esecuzione.**
- Connessione `read_only` e timeout di 10 s con `threading.Timer(10, con.interrupt)`.
- Prima si esegue lo SQL così com'è in DuckDB.
- Solo se fallisce per parse o binder, si prova `sqlglot.transpile(read="postgres", write="duckdb")` e poi `read="mysql"`.
- Il gold segue lo stesso percorso.
- Il record salva `exec_sql` e `dialect_path`.
- Esiti possibili: `ok`, `parse_error`, `exec_error` (con messaggio), `timeout`.

## Ground truth (`gold`)

1. **Domande Parte 1**: una sola chiamata `opus-gold` per tutti i pattern, con 3 candidati per pattern. Vincoli:
   - P0 usa la domanda d'esempio del testo, alla lettera.
   - Domande in italiano, senza ambiguità, con le colonne di output nominate.
   - Coprire tabelle diverse: sale, dipendenti, prenotazioni, non solo LIBRO.
   - P3, P5 e P6 hanno una soluzione per strategia, con lo stesso risultato. Per INTERSECT si proiettano chiavi o si usa `DISTINCT`; per NOT IN si usano colonne non nullabili.
   - P4 è una domanda "per ogni / tutti".
   - Se il gold ha `ORDER BY` esterno, il candidato dichiara `order_by`: indici delle colonne di output e direzione.
   - Output JSON: `id`, `pattern`, `domanda`, `colonne_output`, `order_by`, `gold_sql` per strategia.
2. **Gold Parte 3**: una chiamata `opus-gold` per query (10). Output:
   - `interpretazioni` (es. Q1: "copie vendute" = righe di SALE per ISBN);
   - `gold_sql`;
   - `varianti_accettate`: una query per ogni interpretazione alternativa ragionevole, eventualmente nessuna;
   - `order_by`.
3. **Dati**: istanze base e mutate (sezione Database).
4. **Validazione**, su tutte e 5 le istanze:
   - equivalenza tra le strategie (P3, P5, P6);
   - controllo statico sulla strategia;
   - vincolo sul numero di righe;
   - secondo parere: `deepseek` scrive la propria query partendo da domanda, schema, `colonne_output` e interpretazioni, senza vedere il gold. Il confronto usa lo stesso `evaluate.py`; in Parte 3 basta la coincidenza con una qualsiasi variante accettata.
5. **Esiti**:
   - Tutto concorda → `verificato`.
   - Parte 1, un controllo fallisce → si passa al candidato successivo. Se finiscono i 3 candidati, la voce diventa `da_rivedere`.
   - Parte 3, disaccordo con DeepSeek → la voce diventa `da_rivedere`. In `gold_overrides.json` compare già compilata con le due query e fino a 10 righe che differiscono. Io scelgo la query o aggiungo una variante accettata, e lo stato diventa `rivisto`.
6. **Regole sui casi da rivedere.** `report` non parte se resta una voce `da_rivedere`. I casi della Parte 3 si rivedono il giorno 1, subito dopo `gold`. Per una voce senza soluzione mi do al massimo 20 minuti, poi scrivo il gold a mano.

## Parte 1 – modelli proprietari

11 prompt × 3 modelli = 33 chiamate.

1. **Prompt**: il testo d'esempio del PDF parola per parola (Appendice A1), inviato come unico messaggio `user`, senza system prompt.
2. **Riga di strategia**: per i pattern 3, 5 e 6 si aggiunge prima di `Codice SQL:` una riga fissa, presa dalla tabella in Appendice A2.

| Pattern | Contenuto | Prompt |
| --- | --- | --- |
| 0 | Proiezione: `WHERE` (+ `ORDER BY`) | 1 |
| 1 | `JOIN` | 1 |
| 2 | `GROUP BY` + `HAVING` + aggregata | 1 |
| 3 | JOIN / IN / INTERSECT | 3 |
| 4 | Divisione | 1 |
| 5 | NOT IN / EXCEPT | 2 |
| 6 | CTE / correlazione | 2 |

3. `run --part 1`, poi `eval --part 1`.
4. **Commento generale**: una chiamata `opus-text` riceve le tabelle aggregate e scrive `narratives/p1_commento_generale.md` con:
   - i punti forti e deboli di ogni LLM;
   - il confronto tra LLM;
   - il confronto tra tipi di prompt.

Il testo dell'esercitazione cita i pattern "3, 6, 7". L'elenco va però da 0 a 6, quindi i pattern a soluzione multipla sono 3, 5 e 6. In metodologia va una riga che lo spiega.

## Parte 2 – modelli open source ≤ 8B

Gli stessi 11 prompt della Parte 1, byte per byte, su 5 modelli: 55 chiamate.

1. `run --part 2`, poi `eval --part 2`. Il provider di ogni chiamata è salvato e indica la quantizzazione dichiarata.
2. **Sintesi**: una chiamata `opus-text` con le metriche delle Parti 1 e 2 scrive `narratives/p2_sintesi.md`. Domande guida:
   - a che taglia il modello smette di produrre SQL eseguibile;
   - quali pattern cedono per primi;
   - quanto spesso i modelli ignorano il formato o la strategia;
   - quanto distano dal migliore modello proprietario.

## Parte 3 – modelli con reasoning

Le chiavi primarie sono in Appendice A3, perché nel PDF sono sottolineate e la sottolineatura si perde copiando il testo.

1. **Prompt inglese** (Appendice A4): è la traduzione del template della Parte 1, perché il PDF cita un esempio in inglese che non contiene. Le domande Q1-Q10 sono copiate alla lettera.
2. **Giro 1**: `run --part 3 --round 1`, 30 chiamate. `eval --part 3 --round 1`.
3. **Prompt aggiornati**, solo per le coppie query-modello con EX=0. Una chiamata `opus-text` per query, che copre tutti i modelli sbagliati.
   - Input: prompt, reasoning, SQL del modello, esito, categorie d'errore e interpretazioni. **Non** riceve il gold né i commenti del giudice.
   - Controllo anti-leak: si rifiuta un prompt che contiene sequenze SQL, cioè la regex `\bSELECT\b[\s\S]*\bFROM\b`, oppure un frammento di 8 token consecutivi del gold, esclusi i nomi dello schema.
   - Si rigenera al massimo 2 volte, poi decido io.
   - Il risultato va in `outputs/p3_prompts_r2.json`.
4. **Giro 2**: `run --part 3 --round 2` legge solo `p3_prompts_r2.json`, poi `eval --part 3 --round 2`. Un solo giro di correzione.
5. **Q4 e Q10 senza reasoning**: `gpt-nr` con lo stesso prompt usato da `gpt-r`, aggiornato se esiste. Il report mostra `nl_output` nel campo Output e `sql` nel campo Soluzione.
6. **Confronti**:
   - Una chiamata `opus-text` per query scrive `narratives/p3_qNN_confronti.md`, con le sezioni "Confronto modelli (reasoning)" e "Confronto modelli (soluzione SQL)".
   - Per Q4 e Q10 anche "Confronto modelli GPT (reasoning)" e "Confronto modelli GPT (soluzione SQL)", dentro la chiamata di giudizio di `gpt-nr`.

## Valutazione (`eval`)

**L'esito lo decide l'esecuzione.** Il modello di supporto scrive soltanto i commenti.

### 1. Confronto dei risultati (`evaluate.py`)

- **Normalizzazione:**
  - `NULL` come token;
  - `Decimal` e numeri in float, confrontati con `math.isclose(rel_tol=1e-6)`;
  - date e orari in formato ISO;
  - stringhe senza spazi ai bordi.
- **Colonne**: si confrontano come multinsiemi di tuple.
  - Stesso numero di colonne: si cerca una permutazione valida su **tutte** le istanze insieme. La ricerca si fa fino a 6 colonne; oltre, si confronta solo nell'ordine dato.
  - Il modello ha più colonne: si cercano sottoinsiemi della larghezza del gold. Se uno coincide, il risultato ha il flag `colonne_extra`.
  - Stesso insieme di righe ma molteplicità diverse: flag `duplicati`.
- **Ordinamento**: se il gold dichiara `order_by`, servono anche due condizioni:
  - il modello ha un `ORDER BY` esterno;
  - le righe del modello sono monotone sulle colonne `order_by`. I pareggi possono stare in qualsiasi ordine.

  Se manca una delle due, il risultato ha il flag `ordinamento`.
- **EX = 1** se il risultato coincide su tutte le 5 istanze, con almeno una variante accettata in Parte 3. Si riporta anche EX sulla sola istanza base.
- **Esito deterministico**:
  - EX=1 → `corretta`;
  - EX=0 con `colonne_extra`, `duplicati` o `ordinamento` come unico difetto → `parzialmente corretta`;
  - altrimenti → `errata`.

  In Parte 3, `soluzione_corretta` = sì solo con EX=1.

### 2. Controlli statici con sqlglot (`rispetta_strategia`)

Si parsano lo SQL originale e, se serve, la versione transpilata.

| Requisito | Controllo |
| --- | --- |
| P0 | `exp.Where` presente |
| JOIN | `exp.Join` presente, esplicita o implicita con virgola |
| P2 | `exp.Group`, `exp.Having`, almeno un `exp.AggFunc` |
| IN | `exp.In` con sottoquery, non sotto `exp.Not` |
| NOT IN | `exp.In` con sottoquery sotto `exp.Not` |
| INTERSECT / EXCEPT | `exp.Intersect` / `exp.Except` |
| CTE | `exp.With` |
| Correlazione | `qualify(ast, schema=SCHEMA)`, poi uno scope di `traverse_scope` con `is_correlated_subquery`. Se `qualify` fallisce, cioè con colonne inesistenti, il risultato è `non verificabile` |
| Divisione (P4) | doppio `NOT EXISTS`, oppure `HAVING COUNT(...) =` sottoquery, oppure `EXCEPT` annidato. Se nessuna forma è presente, decide il giudice (`strategy_source="judge"`) |

### 3. Giudizi raggruppati (`judge.py`)

**Parte 1 e 2**: una chiamata `opus-judge` per prompt, quindi 11 per parte.
- Input:
  - schema, domanda, soluzioni attese e strategia richiesta;
  - per ogni modello: SQL, esito ed EX, flag, fino a 5 righe mancanti o in più sulla prima istanza che fallisce, controlli statici, `format_ok`.
- Output JSON, con una voce per alias:

```json
{"gpt": {"categorie_errore": ["join"], "commento": "max 60 parole, in italiano", "divisione_ok": null}}
```

`divisione_ok` si compila solo in P4, quando il controllo statico non ha riconosciuto la forma.

**Parte 3**: una chiamata `opus-judge` per query e per giro, che copre tutti i modelli. L'input contiene anche il reasoning completo e le interpretazioni. L'output per ogni modello è questo:

```json
{"reasoning_corretto": "sì | parzialmente | no",
 "passi_mancanti": [], "passi_errati": [], "passi_fuori_ordine": [], "passi_ridondanti": [],
 "commento_reasoning": "...",
 "segue_reasoning": "sì | parzialmente | no",
 "commento_soluzione": "...",
 "categorie_errore": []}
```

Per `gpt-nr` (Q4, Q10) l'output aggiunge:
- `output_corretto` e `commento_output`;
- i due "Confronto modelli GPT".

**Controlli sui giudizi:**
- Chiavi presenti per ogni alias atteso, altrimenti un retry con l'errore in coda al messaggio (il numero di tentativo entra nella chiave di cache), poi revisione manuale.
- Il giudice riceve l'esito come dato di fatto e non lo può cambiare.
- Nell'input al giudice si usa sempre "soluzione attesa", mai "gold".

**Categorie d'errore fisse:**
- sintassi;
- dialetto;
- schema linking;
- join;
- filtro;
- aggregazione;
- HAVING;
- NULL;
- duplicati;
- ordinamento;
- colonne di output;
- strategia non rispettata;
- logica di divisione;
- subquery o correlazione;
- interpretazione della domanda;
- formato dell'output.

**Voce dei commenti**: prima persona singolare, tono di uno studente che analizza la risposta, senza citare giudici, modelli di supporto o pipeline.

**Controllo a campione**: leggo 10 giudizi, soprattutto griglie di reasoning della Parte 3, perché lì nessuna esecuzione fa da verità. Il controllo resta interno.

**Metriche per il report:**
- EX per modello e per pattern (5 istanze e solo base);
- conformità alla strategia;
- rispetto del formato;
- distribuzione delle categorie d'errore;
- costo e latenza dei modelli testati.

In Parte 3, in più:
- correttezza al giro 1 contro giro 2;
- quota di reasoning corretti;
- coerenza tra reasoning e soluzione.

## Narrative

File in `outputs/narratives/`:
- `p1_commento_generale.md`
- `p2_sintesi.md`
- `p3_qNN_confronti.md`: uno per query, con le sezioni GPT per Q4 e Q10
- `conclusioni.md`

Regole:
- Un file si genera solo se non esiste. Per rigenerarlo lo cancello.
- `report` li legge e non li sovrascrive mai, quindi le mie modifiche sopravvivono.
- Prima persona singolare e verbi della richiesta: "ho formulato", "ho scritto la soluzione attesa", "ho analizzato".

## Report (`report`, Typst)

`report.py` scrive `outputs/report/data.json`, ricavato da gold, calls, evals, narratives e `config.py`, più `p2_accuratezza.svg` (matplotlib). Poi compila `templates/report.typ` con `typst.compile(...)` in `outputs/report/<MATRICOLA>_TextSQL.pdf`. Il template legge i dati con `json("data.json")`.

### Struttura

1. **Frontespizio**: titolo, `NOME`, `MATRICOLA`, "Master Intelligenza Artificiale: Tecnologie, Modelli e Applicazioni", data.
2. **Metodologia** (1 pagina):
   - OpenRouter al posto delle web app e di LM Studio;
   - prompt identici;
   - tabella dei soli modelli testati, con ID servito e parametri inviati;
   - database: 5 istanze, una base e 4 derivate per mutazione;
   - criteri di correttezza e di strategia;
   - lettura "3, 6, 7" → 3, 5, 6;
   - fallback di `gpt-nr`, se usato.
3. **Parte 1**:
   - tabella EX modello × pattern, con EX solo base come colonna secondaria;
   - una scheda per prompt: Pattern, Domanda, Soluzione attesa (una per strategia), Prompt, e per ogni modello SQL generato e Analisi con l'esito evidenziato;
   - Commento generale.
4. **Parte 2**: stesse schede, con un blocco per modello impilato verticalmente, perché 5 colonne non stanno in un A4. Poi il grafico accuratezza per numero di parametri, con i due punti a 8B etichettati separatamente, e la sintesi.
5. **Parte 3**, per ogni query:
   - Soluzione attesa e interpretazioni;
   - Prompt;
   - per ogni modello: estratto del reasoning (15 righe), Soluzione SQL, griglia del reasoning, griglia della soluzione, Prompt aggiornato, Reasoning e Soluzione SQL aggiornati con la loro analisi;
   - i due Confronti.

   Segue una sezione Q4/Q10 senza reasoning: Output, Soluzione, analisi e i due Confronti GPT.
6. **Conclusioni** (mezza pagina).
7. **Appendici**:
   - **A**: prompt completi. Nel corpo il prompt compare per intero solo in P0 e Q1.
   - **B**: reasoning **completi**, corpo 7,5 pt. Corrisponde al campo "Reasoning (continua)".
   - **C**: DDL e statistiche dei database, cioè righe per tabella e per istanza, e descrizione delle mutazioni.
   - **D**: numero di chiamate e costo dei modelli testati.

### Campi che possono restare vuoti

Si riempiono con testi fissi:
- "Prompt aggiornato" e giro 2 per le coppie corrette al giro 1: "Non necessario: la soluzione era corretta al primo giro."
- Output vuoto di Q4/Q10: "Il modello ha restituito solo codice SQL."

### Impaginazione

- A4, numeri di pagina;
- SQL come blocchi `raw` di Typst con `lang: "sql"` (evidenziazione inclusa) e corpo 8 pt;
- schede con `block(breakable: true)` e titolo legato al contenuto.

### `report --draft`

Usa `fixtures/` per le sezioni senza dati reali e marca quei campi con `PENDING` e una filigrana. Serve dal giorno 1 per vedere tutte le sezioni, inclusa una scheda della Parte 3, Q4/Q10, le appendici e il grafico. Va provato con l'output più lungo disponibile.

### Controlli finali (build senza `--draft`)

- Il nome del file rispetta `^\d+_TextSQL\.pdf$`.
- Nessun `PENDING`, `TODO` o campo vuoto: ogni scheda ha tutte le chiavi dei form del testo (elenco in `report.py`).
- Ricerca senza distinzione di maiuscole su `data.json`, `narratives/` e template di: `opus`, `deepseek`, `fable`, `claude`, `anthropic`, `giudice`, `gold`, `pipeline`, `llm di supporto`. Stampa file e riga di ogni occorrenza da correggere.
- Nessuna voce `da_rivedere`.
- Il PDF compila; si stampa il numero di pagine.

## Costi

Stima delle chiamate:

| Blocco | Chiamate |
| --- | --- |
| gold | ≈ 37 (1 domande P1, 10 gold P3, 6 dati, ~20 DeepSeek) |
| Parte 1 | 33 + 11 giudizi + 1 sintesi |
| Parte 2 | 55 + 11 + 1 |
| Parte 3 | 30 + 10 giudizi + ≤10 ottimizzatore + ≤20 giro 2 + ≤10 giudizi + 2 Q4/Q10 + 2 giudizi + 10 confronti |
| conclusioni | 1 |
| **Totale** | **≈ 250, di cui circa 80 a Opus** |

Il prezzo di Opus 5.5 va letto allo step 0, che stampa il costo reale per chiamata. Dopo la Parte 1 si stampa la proiezione del totale. La chiave ha un limite di 15 $ e `SPESA_MAX_USD=12` ferma la pipeline prima del limite.

## Piano operativo

Giorno 1:
- [ ] Setup (30 min): venv, `.env`, chiave OpenRouter con limite di spesa, `src/assignment.py` dall'Appendice, i 6 DDL.
- [ ] `llm.py` e `check` (1 h).
- [ ] `report --draft` con fixtures (1 h). Si fa subito, perché il template è la forma del PDF.
- [ ] `db.py` ed `evaluate.py` (1 h 30), provati sul gold di P0 scritto a mano.
- [ ] `gold` (1 h): rivedere subito le voci `da_rivedere` della Parte 3.
- [ ] Parte 1 e Parte 2: `run` + `eval` (45 min).

Giorno 2:
- [ ] Parte 3 (2 h): giro 1, prompt aggiornati, giro 2, Q4/Q10, confronti.
- [ ] Narrative e report finale (1 h 30).
- [ ] Revisione (1 h): 10 giudizi a campione, testi in `narratives/`, lettura completa del PDF.
- [ ] Consegna con qualche giorno di margine.

## Rischi

| Rischio | Mitigazione |
| --- | --- |
| Soluzioni attese sbagliate | Equivalenza tra strategie, secondo parere DeepSeek, 5 istanze, revisione dei casi `da_rivedere` |
| Interpretazioni diverse in Parte 3 | Varianti accettate; le interpretazioni sono nel report |
| Modello irraggiungibile con certi parametri | Parametri per modello, chiamata reale allo step 0 |
| Reasoning troncato o assente | `finish_reason` salvato, retry senza cache, verifica allo step 0 |
| API diverse dalle web app | ID servito e parametri nel report, una riga in metodologia |
| Reasoning di GPT e Gemini solo riassunto | `reasoning_type` dichiarato nel report |
| Errori di dialetto | Prima DuckDB nativo, poi transpilazione; categoria "dialetto" |
| Risposte non deterministiche | La cache congela le risposte usate nel report |
| Spesa oltre il limite | Controllo prima di ogni chiamata, 402 fatale |
| Testi generici | Li rileggo e li ritocco in `narratives/` |

## Appendice – testo dell'esercitazione

Fonte: `EsercitazionePoliTo.pdf`. Questi testi vanno copiati identici in `src/assignment.py`.

### A1. Prompt Parte 1 (verbatim, senza le virgolette esterne)

```text
Sei un assistente AI per la risoluzione di query in linguaggio SQL partendo da una domanda testuale.
Ti verranno forniti in input lo schema logico delle tabelle da utilizzare e la domanda testuale.
Tu dovrai restituire come output solamente il codice SQL.

Tabelle:

LIBRO(id_libro, id_autore, titolo, anno_pubblicazione, genere, numero_copie) con chiave primaria id_libro
AUTORE(id_autore, nome, cognome, nazionalità, data_nascita, data_morte*) con chiave primaria id_autore
LETTORE(id_lettore, nome, cognome, email, telefono, indirizzo, data_iscrizione) con chiave primaria id_lettore
PRESTITO_LIBRO(id_libro, id_lettore, data_prestito, data_restituzione*, note*) con chiave primaria (id_libro, id_lettore, data_prestito)
SALA(id_sala, id_dipendente_responsabile, nome, capacità, piano, tipologia) con chiave primaria id_sala
DIPENDENTE(id_dipendente, nome, cognome, ruolo, data_assunzione, email, telefono) con chiave primaria id_dipendente
PRENOTAZIONE_SALA(id_lettore, data, ora_inizio, ora_fine, id_sala, note*) con chiave primaria (id_lettore, data, ora_inizio)

L’asterisco indica i campi opzionali.

Domanda:

{domanda}

{riga_strategia}
Codice SQL:
```

`{riga_strategia}` e la riga vuota che la precede si omettono quando non c'è strategia.

Domanda P0, alla lettera: `Mostra il titolo e l’anno di pubblicazione dei libri del genere “fantasy” con almeno 3 copie disponibili ordinati a partire dal più recente.`

Chiavi esterne (in corsivo nel PDF):
- `LIBRO.id_autore → AUTORE`;
- `PRESTITO_LIBRO.id_libro → LIBRO`, `PRESTITO_LIBRO.id_lettore → LETTORE`;
- `SALA.id_dipendente_responsabile → DIPENDENTE`;
- `PRENOTAZIONE_SALA.id_lettore → LETTORE`, `PRENOTAZIONE_SALA.id_sala → SALA`.

Campi opzionali: `data_morte`, `data_restituzione`, entrambi i `note`.

### A2. Righe di strategia

| Strategia | Riga |
| --- | --- |
| JOIN | Risolvi la query utilizzando obbligatoriamente l’operatore JOIN. |
| IN | Risolvi la query utilizzando obbligatoriamente l’operatore IN con una subquery. |
| INTERSECT | Risolvi la query utilizzando obbligatoriamente l’operatore INTERSECT. |
| NOT IN | Risolvi la query utilizzando obbligatoriamente l’operatore NOT IN con una subquery. |
| EXCEPT | Risolvi la query utilizzando obbligatoriamente l’operatore EXCEPT. |
| CTE | Risolvi la query utilizzando obbligatoriamente una Common Table Expression (clausola WITH). |
| Correlazione | Risolvi la query utilizzando obbligatoriamente una subquery correlata. |

### A3. Schemi Parte 3 con chiavi primarie

```text
Es.1  BOOK_PUBLISHED(ISBN, Title, AuthorCode, Genre)                         PK ISBN
      AUTHOR(AuthorCode, AuthorName, DateOfBirth, City)                       PK AuthorCode
      SALE(SaleCode, ISBN, Date, Time, Price)                                 PK SaleCode
Es.2  STUDENT(StudentCode, StudentName, SchoolType, SchoolYear, Section)      PK StudentCode
      TEACHER(TeacherCode, TeacherName, Profession)                           PK TeacherCode
      CONSULTATION(TeacherCode, Date, StartTime, Duration, Topic, ConsultationCost, StudentCode)
                                                                              PK (TeacherCode, Date, StartTime)
Es.3  CLASSROOM(ClassroomCode, ClassroomName, Capacity)                       PK ClassroomCode
      COURSE(CourseCode, CourseName, ECTSCredit, EnrolledCount)               PK CourseCode
      LECTURE(ClassroomCode, Date, StartTime, CourseCode)                     PK (ClassroomCode, Date, StartTime)
Es.4  ROUTE(RouteCode, OriginAirport, DestinationAirport, Duration)           PK RouteCode
      FLIGHT(RouteCode, Date, DepartureTime, AircraftID)                      PK (RouteCode, Date, DepartureTime)
      TICKET(TicketCode, RouteCode, Date, DepartureTime, PassengerName)       PK TicketCode
      BOARDING_PASS(TicketCode, SeatNumber)                                   PK TicketCode
Es.5  CUSTOMER(CustomerCode, CustomerName, DocumentType, DocumentNumber)      PK CustomerCode
      HOTEL(HotelCode, HotelName, Municipality, Province, StarRating)         PK HotelCode
      HOTEL_ROOM(RoomNumber, HotelCode, RoomType)                             PK (RoomNumber, HotelCode)
      BOOKING(RoomNumber, HotelCode, StartDate, EndDate, CustomerCode)        PK (RoomNumber, HotelCode, StartDate)
```

### A4. Prompt Parte 3 (inglese, traduzione del template della Parte 1)

```text
You are an AI assistant that solves SQL queries starting from a textual question.
You will be given as input the logical schema of the tables to use and the textual question.
You must return as output only the SQL code.

Tables:

{una riga per tabella: NOME(colonne) with primary key ...}

Question:

{domanda}

SQL code:
```

### A5. Domande Parte 3 (verbatim)

- **Q1** Display the name of the authors who have published at least one book in the "fantasy" genre but have never published a book in the "adventure" genre that has been sold in more than 5,000 copies.
- **Q2** Display the title and genre of books for which at least 4,000 copies have been sold overall, and that in April 2025 had a revenue higher than the one obtained in January 2025.
- **Q3** Display the teacher's name and the student's name for all teacher-student pairs who have carried out consultations together for a total of more than 10 hours and who have never had more than one consultation together on the same day.
- **Q4** Display the teacher's name and the maximum daily amount earned for consultations given to first-year students (specified in the SchoolYear field), considering only those teachers who have conducted consultations on a number of different days greater than the average.
- **Q5** Display the code, name, and number of ECTS credits of the courses for which, in January 2024, more than two lectures were held on the same day.
- **Q6** Display the code and name of the classrooms in which all the lectures of (at least) one course were held.
- **Q7** Display the names of the passengers for flights on August 28, 2024, departing from Turin airport, for whom a ticket was issued but no boarding pass was issued.
- **Q8** Considering the month of August 2024, for routes on which more than 30 flights were operated and no flight had fewer than 200 passengers, display the route code, date, departure time, origin airport, and destination airport of each flight on the route.
- **Q9** Display the code and name of customers who have made bookings at hotels that have the fewest number of rooms within their municipality.
- **Q10** Display the names of pairs of customers who, in at least one hotel, have made the same number of bookings, and who, in at least one hotel, have booked rooms for the same total number of days.

### A6. Campi dei form

- **Parte 1 e 2**:
  - Pattern di difficoltà, Domanda, Soluzione attesa, Prompt;
  - per ogni modello SQL generato e Analisi;
  - Commento generale in fondo.
- **Parte 3**, per query e modello:
  - Soluzione attesa, Prompt, Reasoning (+ continua), Soluzione SQL;
  - analisi del reasoning: corretto? passi mancanti, errati, in ordine errato, ridondanti o inefficienti? commento;
  - analisi della soluzione: corretta? segue il reasoning? commento;
  - Prompt aggiornato, Reasoning (aggiornato), Soluzione SQL (aggiornata), con analisi: reasoning corretto? commento; soluzione corretta? commento.

  Per query, inoltre: Confronto modelli (reasoning), Confronto modelli (soluzione SQL).
- **Q4 e Q10 senza reasoning**:
  - Output, Soluzione;
  - output corretto? commento; soluzione corretta? commento;
  - Confronto modelli GPT (reasoning), Confronto modelli GPT (soluzione SQL).
