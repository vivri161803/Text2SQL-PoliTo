"""Testi verbatim dell'esercitazione (Appendice A1-A6 della specifica)."""

PROMPT_P1 = """Sei un assistente AI per la risoluzione di query in linguaggio SQL partendo da una domanda testuale.
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
Codice SQL:"""

DOMANDA_P0 = "Mostra il titolo e l’anno di pubblicazione dei libri del genere “fantasy” con almeno 3 copie disponibili ordinati a partire dal più recente."

FK_BIBLIOTECA = [
    "LIBRO.id_autore → AUTORE",
    "PRESTITO_LIBRO.id_libro → LIBRO",
    "PRESTITO_LIBRO.id_lettore → LETTORE",
    "SALA.id_dipendente_responsabile → DIPENDENTE",
    "PRENOTAZIONE_SALA.id_lettore → LETTORE",
    "PRENOTAZIONE_SALA.id_sala → SALA",
]
CAMPI_OPZIONALI = ["data_morte", "data_restituzione", "note"]

STRATEGY_LINES = {
    "JOIN": "Risolvi la query utilizzando obbligatoriamente l’operatore JOIN.",
    "IN": "Risolvi la query utilizzando obbligatoriamente l’operatore IN con una subquery.",
    "INTERSECT": "Risolvi la query utilizzando obbligatoriamente l’operatore INTERSECT.",
    "NOT IN": "Risolvi la query utilizzando obbligatoriamente l’operatore NOT IN con una subquery.",
    "EXCEPT": "Risolvi la query utilizzando obbligatoriamente l’operatore EXCEPT.",
    "CTE": "Risolvi la query utilizzando obbligatoriamente una Common Table Expression (clausola WITH).",
    "Correlazione": "Risolvi la query utilizzando obbligatoriamente una subquery correlata.",
}

# pattern -> (contenuto, strategie). Strategie [None] = prompt senza riga di strategia.
PATTERNS = {
    0: ("Proiezione: WHERE (+ ORDER BY)", [None]),
    1: ("JOIN", [None]),
    2: ("GROUP BY + HAVING + aggregata", [None]),
    3: ("JOIN / IN / INTERSECT", ["JOIN", "IN", "INTERSECT"]),
    4: ("Divisione", [None]),
    5: ("NOT IN / EXCEPT", ["NOT IN", "EXCEPT"]),
    6: ("CTE / correlazione", ["CTE", "Correlazione"]),
}


def prompt_items():
    """Gli 11 prompt della Parte 1: lista di (pattern, strategia)."""
    return [(p, s) for p, (_, strategie) in PATTERNS.items() for s in strategie]


def build_prompt_p1(domanda, strategia=None):
    text = PROMPT_P1
    if strategia is None:
        text = text.replace("{riga_strategia}\n", "").replace("\n\n\nCodice", "\n\nCodice")
        return text.format(domanda=domanda)
    return text.format(domanda=domanda, riga_strategia=STRATEGY_LINES[strategia])


# Schemi Parte 3: esercizio -> lista di (tabella, colonne, chiave primaria)
SCHEMI_P3 = {
    1: [
        ("BOOK_PUBLISHED", ["ISBN", "Title", "AuthorCode", "Genre"], ["ISBN"]),
        ("AUTHOR", ["AuthorCode", "AuthorName", "DateOfBirth", "City"], ["AuthorCode"]),
        ("SALE", ["SaleCode", "ISBN", "Date", "Time", "Price"], ["SaleCode"]),
    ],
    2: [
        ("STUDENT", ["StudentCode", "StudentName", "SchoolType", "SchoolYear", "Section"], ["StudentCode"]),
        ("TEACHER", ["TeacherCode", "TeacherName", "Profession"], ["TeacherCode"]),
        ("CONSULTATION", ["TeacherCode", "Date", "StartTime", "Duration", "Topic", "ConsultationCost", "StudentCode"],
         ["TeacherCode", "Date", "StartTime"]),
    ],
    3: [
        ("CLASSROOM", ["ClassroomCode", "ClassroomName", "Capacity"], ["ClassroomCode"]),
        ("COURSE", ["CourseCode", "CourseName", "ECTSCredit", "EnrolledCount"], ["CourseCode"]),
        ("LECTURE", ["ClassroomCode", "Date", "StartTime", "CourseCode"], ["ClassroomCode", "Date", "StartTime"]),
    ],
    4: [
        ("ROUTE", ["RouteCode", "OriginAirport", "DestinationAirport", "Duration"], ["RouteCode"]),
        ("FLIGHT", ["RouteCode", "Date", "DepartureTime", "AircraftID"], ["RouteCode", "Date", "DepartureTime"]),
        ("TICKET", ["TicketCode", "RouteCode", "Date", "DepartureTime", "PassengerName"], ["TicketCode"]),
        ("BOARDING_PASS", ["TicketCode", "SeatNumber"], ["TicketCode"]),
    ],
    5: [
        ("CUSTOMER", ["CustomerCode", "CustomerName", "DocumentType", "DocumentNumber"], ["CustomerCode"]),
        ("HOTEL", ["HotelCode", "HotelName", "Municipality", "Province", "StarRating"], ["HotelCode"]),
        ("HOTEL_ROOM", ["RoomNumber", "HotelCode", "RoomType"], ["RoomNumber", "HotelCode"]),
        ("BOOKING", ["RoomNumber", "HotelCode", "StartDate", "EndDate", "CustomerCode"],
         ["RoomNumber", "HotelCode", "StartDate"]),
    ],
}

PROMPT_P3_EN = """You are an AI assistant that solves SQL queries starting from a textual question.
You will be given as input the logical schema of the tables to use and the textual question.
You must return as output only the SQL code.

Tables:

{tables}

Question:

{domanda}

SQL code:"""

Q_P3 = {
    1: (1, 'Display the name of the authors who have published at least one book in the "fantasy" genre but have never published a book in the "adventure" genre that has been sold in more than 5,000 copies.'),
    2: (1, "Display the title and genre of books for which at least 4,000 copies have been sold overall, and that in April 2025 had a revenue higher than the one obtained in January 2025."),
    3: (2, "Display the teacher's name and the student's name for all teacher-student pairs who have carried out consultations together for a total of more than 10 hours and who have never had more than one consultation together on the same day."),
    4: (2, "Display the teacher's name and the maximum daily amount earned for consultations given to first-year students (specified in the SchoolYear field), considering only those teachers who have conducted consultations on a number of different days greater than the average."),
    5: (3, "Display the code, name, and number of ECTS credits of the courses for which, in January 2024, more than two lectures were held on the same day."),
    6: (3, "Display the code and name of the classrooms in which all the lectures of (at least) one course were held."),
    7: (4, "Display the names of the passengers for flights on August 28, 2024, departing from Turin airport, for whom a ticket was issued but no boarding pass was issued."),
    8: (4, "Considering the month of August 2024, for routes on which more than 30 flights were operated and no flight had fewer than 200 passengers, display the route code, date, departure time, origin airport, and destination airport of each flight on the route."),
    9: (5, "Display the code and name of customers who have made bookings at hotels that have the fewest number of rooms within their municipality."),
    10: (5, "Display the names of pairs of customers who, in at least one hotel, have made the same number of bookings, and who, in at least one hotel, have booked rooms for the same total number of days."),
}


def build_prompt_p3(q):
    es, domanda = Q_P3[q]
    righe = []
    for nome, cols, pk in SCHEMI_P3[es]:
        chiave = pk[0] if len(pk) == 1 else "(" + ", ".join(pk) + ")"
        righe.append(f"{nome}({', '.join(cols)}) with primary key {chiave}")
    return PROMPT_P3_EN.format(tables="\n".join(righe), domanda=domanda)


# A6: chiavi dei form, usate dai controlli finali del report
FORM_KEYS_P12 = ["pattern", "domanda", "soluzione_attesa", "prompt", "modelli"]  # modelli: sql, analisi
FORM_KEYS_P3_MODEL = [
    "reasoning", "sql", "reasoning_corretto", "passi_mancanti", "passi_errati",
    "passi_fuori_ordine", "passi_ridondanti", "commento_reasoning",
    "soluzione_corretta", "segue_reasoning", "commento_soluzione",
    "prompt_aggiornato", "reasoning_aggiornato", "sql_aggiornato",
]
FORM_KEYS_P3_QUERY = ["soluzione_attesa", "prompt", "confronto_reasoning", "confronto_soluzione"]
FORM_KEYS_NR = ["output", "sql", "output_corretto", "commento_output", "soluzione_corretta",
                "commento_soluzione", "confronto_gpt_reasoning", "confronto_gpt_soluzione"]
