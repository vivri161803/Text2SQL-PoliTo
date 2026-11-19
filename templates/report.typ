#let data = json("data.json")
#let draft = data.meta.draft

#set page(
  paper: "a4", margin: 2cm, numbering: "1",
  background: if draft { rotate(-45deg, text(90pt, fill: luma(235))[BOZZA]) } else { none },
)
#set text(size: 10pt, lang: "it")
#set par(justify: true)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => { pagebreak(weak: true); it }

// ---------- helper ----------
#let sqlblock(s, size: 8pt) = block(width: 100%, fill: luma(245), inset: 6pt, radius: 3pt,
  text(size: size, raw(if s == none { "(nessuna query)" } else { s }, lang: "sql", block: true)))
#let plain(s, size: 8pt) = block(width: 100%, fill: luma(250), stroke: 0.4pt + luma(200), inset: 6pt, radius: 3pt,
  text(size: size, raw(s, block: true)))
#let esito-box(e) = {
  let c = if e == "corretta" { rgb("#c8e6c9") } else if e == "parzialmente corretta" { rgb("#fff3b0") } else { rgb("#f8c8c8") }
  box(fill: c, inset: (x: 5pt, y: 2pt), radius: 3pt, strong(e))
}
#let prose(s) = {
  for p in s.split("\n\n") {
    if p.starts-with("## ") { block(above: 1em, below: 0.4em, text(weight: "bold", p.slice(3))) } else { par(p) }
  }
}
#let lst(a) = if a.len() == 0 { "nessuno" } else { a.join("; ") }
#let field(label, body) = block(above: 0.6em, below: 0.4em)[*#label* \ #body]
#let fmt(x) = if x == none { "-" } else { str(calc.round(x * 100, digits: 0)) + "%" }

// ---------- frontespizio ----------
#align(center + horizon)[
  #text(24pt, weight: "bold")[#data.meta.titolo] \ #v(1em)
  #text(14pt)[#data.meta.master] \ #v(2em)
  #text(14pt)[#data.meta.nome] \ Matricola #data.meta.matricola \ #v(1em)
  #data.meta.data
]
#pagebreak()
#outline(depth: 2)

// ---------- metodologia ----------
= Metodologia
#prose(data.metodologia.testo)
#table(columns: (auto, 1fr, 1fr, auto), align: left, inset: 4pt,
  [*Alias*], [*ID servito*], [*Parametri inviati*], [*Parte*],
  ..data.metodologia.modelli.map(m => (m.alias, text(size: 8pt, m.id), text(size: 8pt, m.params), str(m.parte))).flatten())
#for n in data.metodologia.note [- #n \ ]

// ---------- tabella EX ----------
#let ex-table(sec) = {
  let ms = sec.modelli
  let cells = ()
  for (pat, row) in sec.tabella.pairs() {
    cells.push([P#pat])
    for m in ms { cells.push([#fmt(row.at(m).at(0)) (base #fmt(row.at(m).at(1)))]) }
  }
  table(columns: (auto,) + (1fr,) * ms.len(), inset: 4pt, align: left,
    [*Pattern*], ..ms.map(m => [*#m*]), ..cells)
}

#let card-p12(c, per-model-stacked: false) = block(breakable: true, width: 100%, above: 1.2em)[
  #heading(level: 3, numbering: none)[Pattern #c.pattern#if c.strategia != none [ – #c.strategia]]
  #field("Pattern di difficoltà")[#c.pattern_desc]
  #field("Domanda")[#c.domanda]
  #field("Soluzione attesa")[]
  #for s in c.soluzioni [#text(size: 8pt)[#emph(s.strategia)] #sqlblock(s.sql)]
  #field("Prompt")[]
  #plain(c.prompt)
  #for m in c.modelli [
    #block(breakable: true, above: 0.8em, inset: (left: 6pt), stroke: (left: 1.5pt + luma(180)))[
      *#m.alias* #h(1em) #esito-box(m.esito)
      #sqlblock(m.sql)
      *Analisi:* #m.analisi
    ]
  ]
]

// ---------- Parte 1 ----------
= Parte 1 – Modelli proprietari
#ex-table(data.p1)
#for c in data.p1.schede [#card-p12(c)]
#heading(level: 2, numbering: none)[Commento generale]
#prose(data.p1.commento)

// ---------- Parte 2 ----------
= Parte 2 – Modelli open source (≤ 8B)
#ex-table(data.p2)
#for c in data.p2.schede [#card-p12(c)]
#figure(image(data.p2.grafico, width: 90%), caption: [Accuratezza (EX) per numero di parametri])
#heading(level: 2, numbering: none)[Sintesi e confronto con la Parte 1]
#prose(data.p2.sintesi)

// ---------- Parte 3 ----------
= Parte 3 – Modelli con reasoning
#for q in data.p3.queries [
  #heading(level: 2)[Q#q.q]
  #field("Domanda")[#q.domanda]
  #field("Soluzione attesa")[]
  #sqlblock(q.soluzione_attesa)
  #field("Interpretazioni considerate")[#lst(q.interpretazioni)]
  #field("Prompt")[]
  #if q.q == 1 { plain(q.prompt) } else { text(size: 8pt)[(prompt in Appendice A)] }
  #for m in q.modelli [
    #block(breakable: true, above: 1em, inset: (left: 6pt), stroke: (left: 1.5pt + luma(180)))[
      #strong[#m.alias] #text(size: 8pt)[(reasoning: #m.reasoning_tipo)]
      #field("Reasoning (estratto, prime 15 righe; completo in Appendice B)")[]
      #plain(m.reasoning_estratto, size: 7.5pt)
      #field("Soluzione SQL")[]
      #sqlblock(m.sql)
      #field("Analisi del reasoning")[Corretto: #m.reasoning_corretto. Passi mancanti: #lst(m.passi_mancanti). Passi errati: #lst(m.passi_errati). Passi in ordine errato: #lst(m.passi_fuori_ordine). Passi ridondanti o inefficienti: #lst(m.passi_ridondanti). \ #m.commento_reasoning]
      #field("Analisi della soluzione")[Corretta: #m.soluzione_corretta. Segue il reasoning: #m.segue_reasoning. \ #m.commento_soluzione]
      #field("Prompt aggiornato")[]
      #if m.r2 == none [Non necessario: la soluzione era corretta al primo giro.] else [
        #plain(m.prompt_aggiornato)
        #field("Reasoning (aggiornato)")[]
        #plain(m.r2.reasoning_estratto, size: 7.5pt)
        #field("Soluzione SQL (aggiornata)")[]
        #sqlblock(m.r2.sql)
        #field("Analisi")[Reasoning corretto: #m.r2.reasoning_corretto. #m.r2.commento_reasoning \ Soluzione corretta: #m.r2.soluzione_corretta. #m.r2.commento_soluzione]
      ]
    ]
  ]
  #field("Confronto modelli (reasoning)")[#q.confronto_reasoning]
  #field("Confronto modelli (soluzione SQL)")[#q.confronto_soluzione]
]

== Q4 e Q10: GPT senza reasoning
#for n in data.p3.nr [
  #block(breakable: true, above: 1em)[
    #heading(level: 3, numbering: none)[Q#n.q]
    #field("Output")[#n.output]
    #field("Soluzione")[]
    #sqlblock(n.sql)
    #field("Output corretto?")[#n.output_corretto. #n.commento_output]
    #field("Soluzione corretta?")[#n.soluzione_corretta. #n.commento_soluzione]
    #field("Confronto modelli GPT (reasoning)")[#n.confronto_gpt_reasoning]
    #field("Confronto modelli GPT (soluzione SQL)")[#n.confronto_gpt_soluzione]
  ]
]

// ---------- conclusioni ----------
= Conclusioni
#prose(data.conclusioni)

// ---------- appendici ----------
= Appendice A – Prompt completi
#for p in data.appendici.A [
  #block(breakable: true)[#strong[#p.id] #plain(p.prompt)]
]
= Appendice B – Reasoning completi
#for r in data.appendici.B [
  #block(breakable: true)[#strong[#r.q – #r.alias] #text(size: 7.5pt, raw(r.reasoning, block: true))]
]
= Appendice C – DDL e database di test
#for d in data.appendici.C.ddl [#strong[#d.nome] #sqlblock(d.sql)]
#table(columns: (auto, 1fr, auto, auto, auto, auto, auto), inset: 3pt, align: left,
  [*Schema*], [*Tabella*], [*base*], [*m1*], [*m2*], [*m3*], [*m4*],
  ..data.appendici.C.stats.map(s => (s.schema, s.tabella, ..s.righe.map(str))).flatten())
#for m in data.appendici.C.mutazioni [- #m \ ]
= Appendice D – Chiamate e costi
#table(columns: (1fr, auto, auto), inset: 3pt, align: left,
  [*Modello*], [*Chiamate*], [*Costo (USD)*],
  ..data.appendici.D.map(r => (r.alias, str(r.chiamate), str(calc.round(r.costo, digits: 3)))).flatten())
