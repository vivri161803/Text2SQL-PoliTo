CREATE TABLE AUTORE (
  id_autore INTEGER PRIMARY KEY,
  nome VARCHAR NOT NULL,
  cognome VARCHAR NOT NULL,
  nazionalità VARCHAR NOT NULL,
  data_nascita DATE NOT NULL,
  data_morte DATE
);
CREATE TABLE LIBRO (
  id_libro INTEGER PRIMARY KEY,
  id_autore INTEGER NOT NULL REFERENCES AUTORE(id_autore),
  titolo VARCHAR NOT NULL,
  anno_pubblicazione INTEGER NOT NULL,
  genere VARCHAR NOT NULL,
  numero_copie INTEGER NOT NULL
);
CREATE TABLE LETTORE (
  id_lettore INTEGER PRIMARY KEY,
  nome VARCHAR NOT NULL,
  cognome VARCHAR NOT NULL,
  email VARCHAR NOT NULL,
  telefono VARCHAR NOT NULL,
  indirizzo VARCHAR NOT NULL,
  data_iscrizione DATE NOT NULL
);
CREATE TABLE PRESTITO_LIBRO (
  id_libro INTEGER NOT NULL REFERENCES LIBRO(id_libro),
  id_lettore INTEGER NOT NULL REFERENCES LETTORE(id_lettore),
  data_prestito DATE NOT NULL,
  data_restituzione DATE,
  note VARCHAR,
  PRIMARY KEY (id_libro, id_lettore, data_prestito)
);
CREATE TABLE DIPENDENTE (
  id_dipendente INTEGER PRIMARY KEY,
  nome VARCHAR NOT NULL,
  cognome VARCHAR NOT NULL,
  ruolo VARCHAR NOT NULL,
  data_assunzione DATE NOT NULL,
  email VARCHAR NOT NULL,
  telefono VARCHAR NOT NULL
);
CREATE TABLE SALA (
  id_sala INTEGER PRIMARY KEY,
  id_dipendente_responsabile INTEGER NOT NULL REFERENCES DIPENDENTE(id_dipendente),
  nome VARCHAR NOT NULL,
  capacità INTEGER NOT NULL,
  piano INTEGER NOT NULL,
  tipologia VARCHAR NOT NULL
);
CREATE TABLE PRENOTAZIONE_SALA (
  id_lettore INTEGER NOT NULL REFERENCES LETTORE(id_lettore),
  data DATE NOT NULL,
  ora_inizio TIME NOT NULL,
  ora_fine TIME NOT NULL,
  id_sala INTEGER NOT NULL REFERENCES SALA(id_sala),
  note VARCHAR,
  PRIMARY KEY (id_lettore, data, ora_inizio)
);
