#let data = json("data.json")
#let draft = data.meta.draft

// ---------- stile ----------
#let accent = rgb("#1f4e79")
#let muted = luma(105)
#let ok-c = rgb("#2e7d32")
#let mid-c = rgb("#c88a00")
#let bad-c = rgb("#c62828")

#set page(
  paper: "a4", margin: (x: 2.2cm, top: 2.4cm, bottom: 2.2cm), numbering: "1",
  header: context {
    if counter(page).get().first() > 1 {
      set text(8pt, fill: muted)
      [Text2SQL – #data.meta.nome #h(1fr) Matricola #data.meta.matricola]
      v(-0.5em)
      line(length: 100%, stroke: 0.4pt + luma(200))
    }
  },
  background: if draft { rotate(-45deg, text(90pt, fill: luma(235))[BOZZA]) } else { none },
)
#set text(size: 10.5pt, lang: "it")
#set par(justify: true, leading: 0.65em, spacing: 1em)
#set heading(numbering: "1.1")
#set table(stroke: 0.4pt + luma(205), inset: 5pt)
#set figure(gap: 0.8em)

#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(width: 100%, below: 1.2em, stroke: (bottom: 1.4pt + accent), inset: (bottom: 7pt),
    text(20pt, weight: "bold", fill: accent, it))
}
#show heading.where(level: 2): it => block(above: 1.6em, below: 0.9em, sticky: true,
  text(14pt, weight: "bold", fill: accent, it))
#show heading.where(level: 3): it => block(above: 1.2em, below: 0.6em, sticky: true,
  text(11.5pt, weight: "bold", it))

// ---------- helper ----------
#let sqlblock(s, size: 8.5pt) = block(width: 100%, fill: luma(246), stroke: (left: 2pt + accent),
  inset: (x: 9pt, y: 7pt), radius: 2pt, breakable: true,
  text(size: size, raw(if s == none { "(nessuna query)" } else { s }, lang: "sql", block: true)))
#let plain(s, size: 8pt) = block(width: 100%, fill: luma(250), stroke: 0.4pt + luma(210),
  inset: (x: 9pt, y: 7pt), radius: 2pt, breakable: true,
  text(size: size, raw(s, block: true)))
#let note(body) = block(width: 100%, fill: luma(248), stroke: 0.4pt + luma(215), inset: 9pt, radius: 3pt,
  breakable: true)[#set par(justify: false); #body]
#let esito-color(e) = if e == "corretta" or e == "sì" { ok-c } else if e == "parzialmente corretta" or e == "parzialmente" { mid-c } else { bad-c }
#let esito-box(e) = {
  let c = if e == "corretta" { rgb("#c8e6c9") } else if e == "parzialmente corretta" { rgb("#fff0b3") } else { rgb("#f8c8c8") }
  box(fill: c, stroke: 0.5pt + esito-color(e), inset: (x: 6pt, y: 2.5pt), radius: 3pt, text(size: 9pt, weight: "bold", e))
}
#let prose(s) = {
  for p in s.split("\n\n") {
    if p.starts-with("## ") {
      block(above: 1.2em, below: 0.5em, sticky: true, text(weight: "bold", fill: accent, p.slice(3)))
    } else { par(p) }
  }
}
#let lst(a) = if a.len() == 0 { "nessuno" } else { a.join("; ") }
#let lab(t) = text(size: 8pt, weight: "bold", fill: accent, tracking: 0.04em, upper(t))
#let lab-only(t) = block(above: 1em, below: 0.4em, sticky: true, lab(t))
#let field(label, body) = block(above: 1em, below: 0.4em, breakable: true)[#lab(label) \ #v(0.15em) #body]
#let fmt(x) = if x == none { "-" } else { str(calc.round(x * 100, digits: 0)) + "%" }
#let hcell(t) = table.cell(fill: accent, text(fill: white, weight: "bold", size: 9.5pt, t))
#let zebra = (x, y) => if y == 0 { none } else if calc.odd(y) { luma(247) } else { none }
#let model-block(alias, color, body) = block(breakable: true, width: 100%, above: 1.1em, inset: (left: 10pt, y: 2pt),
  stroke: (left: 2.5pt + color))[
  #text(weight: "bold", size: 11pt)[#alias]
  #body
]

// ---------- frontespizio ----------
#page(numbering: none, header: none)[
  #v(5cm)
  #block(stroke: (left: 4pt + accent), inset: (left: 14pt, y: 4pt))[
    #text(30pt, weight: "bold", fill: accent)[#data.meta.titolo] \ #v(0.6em)
    #text(13pt, fill: muted)[#data.meta.master]
  ]
  #v(3cm)
  #text(15pt, weight: "bold")[#data.meta.nome] \
  #text(12pt)[Matricola #data.meta.matricola] \ #v(0.5em)
  #text(11pt, fill: muted)[#data.meta.data]
]
#pagebreak(weak: true)
#show outline.entry.where(level: 1): it => { v(0.6em); strong(it) }
#outline(depth: 2, indent: 1.2em)

// ---------- metodologia ----------
= Metodologia
#prose(data.metodologia.testo)
#v(0.5em)
#table(columns: (auto, 1fr, 1.2fr, auto), align: left + horizon, fill: zebra,
  hcell[Alias], hcell[ID servito], hcell[Parametri inviati], hcell[Parte],
  ..data.metodologia.modelli.map(m => (strong(m.alias), text(size: 8pt, m.id), text(size: 8pt, m.params), str(m.parte))).flatten())
#v(0.5em)
#for n in data.metodologia.note [- #n \ ]

// ---------- tabella EX ----------
#let ex-table(sec) = {
  let ms = sec.modelli
  let cells = ()
  for (pat, row) in sec.tabella.pairs() {
    cells.push(strong[P#pat])
    for m in ms {
      let v = row.at(m).at(0)
      let c = if v >= 0.999 { rgb("#d4edd6") } else if v >= 0.5 { rgb("#fff0b3") } else { rgb("#f8d0d0") }
      cells.push(table.cell(fill: c)[#strong[#fmt(v)] #text(size: 8pt, fill: muted)[(base #fmt(row.at(m).at(1)))]])
    }
  }
  align(center, table(columns: (auto,) + (1fr,) * ms.len(), align: center + horizon,
    hcell[Pattern], ..ms.map(m => hcell(m)), ..cells))
  text(size: 8.5pt, fill: muted)[Accuratezza di esecuzione (EX) su 5 istanze; tra parentesi quella sulla sola istanza base.]
}

#let card-p12(c) = block(breakable: true, width: 100%, above: 2em)[
  #block(fill: accent.lighten(88%), inset: (x: 10pt, y: 8pt), radius: 3pt, width: 100%, sticky: true)[
    #text(weight: "bold", size: 12pt, fill: accent)[Pattern #c.pattern#if c.strategia != none [ – #c.strategia]]
    #h(1fr) #text(size: 9pt, fill: muted)[#c.pattern_desc]
  ]
  #field("Domanda")[#c.domanda]
  #lab-only("Soluzione attesa")
  #for s in c.soluzioni [
    #if c.soluzioni.len() > 1 [#text(size: 8.5pt, fill: muted)[#emph(s.strategia)]]
    #sqlblock(s.sql)
  ]
  #lab-only("Prompt")
  #plain(c.prompt)
  #for m in c.modelli [
    #model-block(m.alias, esito-color(m.esito))[
      #h(0.8em) #esito-box(m.esito)
      #sqlblock(m.sql)
      #note[#lab("Analisi") \ #v(0.1em) #m.analisi]
    ]
  ]
]

// ---------- Parte 1 ----------
= Parte 1 – Modelli proprietari
#ex-table(data.p1)
#for c in data.p1.schede [#card-p12(c)]
== Commento generale
#prose(data.p1.commento)

// ---------- Parte 2 ----------
= Parte 2 – Modelli open source (≤ 8B)
#ex-table(data.p2)
#figure(image(data.p2.grafico, width: 85%), caption: [Accuratezza (EX) per numero di parametri.])
#for c in data.p2.schede [#card-p12(c)]
== Sintesi e confronto con la Parte 1
#prose(data.p2.sintesi)

// ---------- Parte 3 ----------
= Parte 3 – Modelli con reasoning
#for q in data.p3.queries [
  #pagebreak(weak: true)
  #heading(level: 2)[Q#q.q]
  #field("Domanda")[#q.domanda]
  #lab-only("Soluzione attesa")
  #sqlblock(q.soluzione_attesa)
  #field("Interpretazioni considerate")[#lst(q.interpretazioni)]
  #lab-only("Prompt")
  #if q.q == 1 { plain(q.prompt) } else { text(size: 8.5pt, fill: muted)[(prompt completo in Appendice A)] }
  #for m in q.modelli [
    #model-block(m.alias, esito-color(m.soluzione_corretta))[
      #text(size: 8.5pt, fill: muted)[(reasoning: #m.reasoning_tipo)]
      #lab-only("Reasoning (estratto, prime 15 righe; completo in Appendice B)")
      #plain(m.reasoning_estratto, size: 7.5pt)
      #lab-only("Soluzione SQL")
      #sqlblock(m.sql)
      #lab-only("Analisi del reasoning")
      #note[
        #grid(columns: (4.2cm, 1fr), row-gutter: 5pt, column-gutter: 6pt,
          text(fill: muted)[Reasoning corretto], strong(m.reasoning_corretto),
          text(fill: muted)[Passi mancanti], lst(m.passi_mancanti),
          text(fill: muted)[Passi errati], lst(m.passi_errati),
          text(fill: muted)[Passi in ordine errato], lst(m.passi_fuori_ordine),
          text(fill: muted)[Ridondanti/inefficienti], lst(m.passi_ridondanti))
        #v(0.2em) #m.commento_reasoning
      ]
      #lab-only("Analisi della soluzione")
      #note[
        Soluzione corretta: #strong[#m.soluzione_corretta] #h(1em) Segue il reasoning: #strong[#m.segue_reasoning] \
        #v(0.2em) #m.commento_soluzione
      ]
      #lab-only("Prompt aggiornato")
      #if m.r2 == none { text(size: 9.5pt)[Non necessario: la soluzione era corretta al primo giro.] } else [
        #plain(m.prompt_aggiornato)
        #lab-only("Reasoning (aggiornato)")
        #plain(m.r2.reasoning_estratto, size: 7.5pt)
        #lab-only("Soluzione SQL (aggiornata)")
        #sqlblock(m.r2.sql)
        #lab-only("Analisi (giro 2)")
        #note[
          Reasoning corretto: #strong[#m.r2.reasoning_corretto]. #m.r2.commento_reasoning \
          #v(0.2em) Soluzione corretta: #strong[#m.r2.soluzione_corretta]. #m.r2.commento_soluzione
        ]
      ]
    ]
  ]
  #field("Confronto modelli (reasoning)")[#q.confronto_reasoning]
  #field("Confronto modelli (soluzione SQL)")[#q.confronto_soluzione]
]

#pagebreak(weak: true)
== Q4 e Q10: GPT senza reasoning
#for n in data.p3.nr [
  #block(breakable: true, above: 1.4em)[
    #heading(level: 3, numbering: none)[Q#n.q]
    #field("Output")[#n.output]
    #lab-only("Soluzione")
    #sqlblock(n.sql)
    #lab-only("Analisi dell'output")
    #note[Output corretto: #strong[#n.output_corretto]. #n.commento_output]
    #lab-only("Analisi della soluzione")
    #note[Soluzione corretta: #strong[#n.soluzione_corretta]. #n.commento_soluzione]
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
  #block(breakable: true, above: 1em)[#lab(p.id) #v(0.2em) #plain(p.prompt)]
]
= Appendice B – Reasoning completi
#for r in data.appendici.B [
  #block(breakable: true, above: 1.2em)[#lab(r.q + " – " + r.alias) #v(0.2em) #text(size: 7.5pt, raw(r.reasoning, block: true))]
]
= Appendice C – DDL e database di test
#for d in data.appendici.C.ddl [
  #lab-only(d.nome)
  #sqlblock(d.sql, size: 8pt)
]
#heading(level: 2, numbering: none)[Righe per tabella e istanza]
#table(columns: (auto, 1fr, auto, auto, auto, auto, auto), align: (left, left, right, right, right, right, right),
  fill: zebra, inset: 3.5pt,
  hcell[Schema], hcell[Tabella], hcell[base], hcell[m1], hcell[m2], hcell[m3], hcell[m4],
  ..data.appendici.C.stats.map(s => (s.schema, s.tabella, ..s.righe.map(str))).flatten())
#heading(level: 2, numbering: none)[Mutazioni]
#for m in data.appendici.C.mutazioni [- #m \ ]
= Appendice D – Chiamate e costi
#table(columns: (1fr, auto, auto), align: (left, right, right), fill: zebra,
  hcell[Modello], hcell[Chiamate], hcell[Costo (USD)],
  ..data.appendici.D.map(r => (r.alias, str(r.chiamate), str(calc.round(r.costo, digits: 3)))).flatten())
