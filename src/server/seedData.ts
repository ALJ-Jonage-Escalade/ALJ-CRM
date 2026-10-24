export interface Member {
  user_id: number;
  purchase_id: number;
  last_name: string;
  first_name: string;
  birth_date: string;
  age: number | null;
  gender: string;
  address: string;
  zip_code: string;
  city: string;
  phone: string;
  email_primary: string;
  email_secondary: string;
  emergency1_name: string;
  emergency1_phone: string;
  emergency2_name: string;
  emergency2_phone: string;
  payer: string;
  payer_email: string;
  tarif_name: string;
  creneau_groupe: string;
  creneau_details: string;
  categorie: string;
  amount: number;
  status: string;
  status_norm: string;
  badge_rouge: string;
  autonomie_bloc: string;
  licence_ffme: string;
  health_commitment: string;
  photo_auth: string;
  document_sante: string;
  order_ref: string;
  order_date: string;
  email_sent_date: string;
  commentaires_correctif: string;
  season_name: string;
  passeport_orange: string;
  raw_passports?: string;
  raw_diplomas?: string;
}

export interface PlanningItem {
  id: number;
  groupe: string;
  type: string;
  categorie_age: string;
  jour: string;
  horaires: string;
  encadrants: string[];
  helloasso_tarifs: string[];
  naissance_min: string;
  naissance_max: string;
  whatsapp_link: string;
}

export interface Coach {
  id: number;
  nom: string;
  email?: string;
  telephone?: string;
  actif?: boolean;
}

export interface Participant {
  adherent_id: number;
  nom: string;
  prenom: string;
  categorie: string;
  selectionne: boolean;
  statut_paiement: "non_invite" | "en_attente" | "paye" | "annule_perdu" | "annule_reporte";
  montant_paye?: number;
  date_paiement?: string;
  reference_paiement?: string;
}

export interface Competition {
  id: number | string;
  nom: string;
  date_competition: string;
  prix: number;
  statut: "en_preparation" | "en_cours" | "close";
  helloasso_ref: string;
  coach_ids: number[];
  participants: Participant[];
  resultats_url?: string;
}

export interface HelloAssoItem {
  id_item: number;
  date: string;
  order_ref: string;
  payer_name: string;
  payer_email: string;
  user_name: string;
  tarif_name: string;
  amount: number;
  state: "Processed" | "Authorized" | "Canceled";
  competition_id?: number | null;
  adherent_id?: number | null;
  is_ignored?: boolean;
  commentaire?: string;
}

export interface EmailTemplate {
  name: string;
  subject: string;
  body: string;
  sender_email?: string;
  sender_name?: string;
}

export const SEASONS = {
  seasons: ["2026-2027", "2025-2026"],
  active: "2026-2027"
};

export const INITIAL_COACHES: Coach[] = [
  { id: 1, nom: "Severus Snape", email: "severus.snape@hogwarts.example", telephone: "06 12 34 56 78", actif: true },
  { id: 2, nom: "Minerva McGonagall", email: "minerva.mcgonagall@hogwarts.example", telephone: "06 23 45 67 89", actif: true },
  { id: 3, nom: "Filius Flitwick", email: "filius.flitwick@hogwarts.example", telephone: "06 34 56 78 90", actif: true },
  { id: 4, nom: "Pomona Sprout", email: "pomona.sprout@hogwarts.example", telephone: "06 45 67 89 01", actif: true },
  { id: 5, nom: "Remus Lupin", email: "remus.lupin@hogwarts.example", telephone: "06 56 78 90 12", actif: true },
  { id: 6, nom: "Rubeus Hagrid", email: "rubeus.hagrid@hogwarts.example", telephone: "06 67 89 01 23", actif: true },
  { id: 7, nom: "Stéphane Loridant", email: "stephane.loridant@orange.fr", telephone: "06 78 90 12 34", actif: true },
  { id: 8, nom: "David Lopez", email: "lopez.dav@gmail.com", telephone: "06 89 01 23 45", actif: true },
];

export const INITIAL_PLANNING: PlanningItem[] = [
  {
    id: 1,
    groupe: "Enfants 2017-2019 (U8-U10)",
    type: "cours",
    categorie_age: "U8-U10",
    jour: "Mercredi",
    horaires: "14:00-15:30",
    encadrants: ["Rubeus Hagrid", "Pomona Sprout"],
    helloasso_tarifs: ["Enfants nés en 2017, 2018, 2019 - Mercredi 14h"],
    naissance_min: "2017-01-01",
    naissance_max: "2019-12-31",
    whatsapp_link: "https://chat.whatsapp.com/sample-u8-u10"
  },
  {
    id: 2,
    groupe: "Collège Groupe A (U12-U15)",
    type: "cours",
    categorie_age: "U12-U15",
    jour: "Lundi",
    horaires: "18:30-20:00",
    encadrants: ["Filius Flitwick"],
    helloasso_tarifs: ["Collège nés 2012 à 2015 - Lundi 18h30"],
    naissance_min: "2012-01-01",
    naissance_max: "2015-12-31",
    whatsapp_link: "https://chat.whatsapp.com/sample-college-a"
  },
  {
    id: 3,
    groupe: "Lycée & Jeunes (U16-U18)",
    type: "cours",
    categorie_age: "U16-U18",
    jour: "Jeudi",
    horaires: "18:30-20:00",
    encadrants: ["Remus Lupin"],
    helloasso_tarifs: ["Lycée nés 2009 à 2011 - Jeudi 18h30"],
    naissance_min: "2009-01-01",
    naissance_max: "2011-12-31",
    whatsapp_link: "https://chat.whatsapp.com/sample-lycee"
  },
  {
    id: 4,
    groupe: "Compétition Jeunes (U11-U13)",
    type: "compétition",
    categorie_age: "U11-U13",
    jour: "Mercredi",
    horaires: "16:00-18:00",
    encadrants: ["Severus Snape", "Minerva McGonagall"],
    helloasso_tarifs: ["Compétition U11-U13"],
    naissance_min: "2014-01-01",
    naissance_max: "2017-12-31",
    whatsapp_link: "https://chat.whatsapp.com/sample-comp-u11-u13"
  },
  {
    id: 5,
    groupe: "Compétition Ados/Adultes (U15-U19)",
    type: "compétition",
    categorie_age: "U15-U19",
    jour: "Vendredi",
    horaires: "18:00-20:00",
    encadrants: ["Severus Snape"],
    helloasso_tarifs: ["Compétition U15 U17 - nés 2008 à 2013"],
    naissance_min: "2008-01-01",
    naissance_max: "2013-12-31",
    whatsapp_link: "https://chat.whatsapp.com/sample-comp-u15-u19"
  },
  {
    id: 6,
    groupe: "Adultes Débutants & Perfectionnement",
    type: "cours",
    categorie_age: "Adultes",
    jour: "Mardi",
    horaires: "20:00-22:00",
    encadrants: ["Minerva McGonagall"],
    helloasso_tarifs: ["Cours adultes débutants"],
    naissance_min: "",
    naissance_max: "",
    whatsapp_link: "https://chat.whatsapp.com/sample-adultes-cours"
  },
  {
    id: 7,
    groupe: "Autonome Voies",
    type: "autonome",
    categorie_age: "Adultes",
    jour: "Lundi / Jeudi",
    horaires: "20:00-22:30",
    encadrants: [],
    helloasso_tarifs: ["Pratique autonome adultes"],
    naissance_min: "",
    naissance_max: "",
    whatsapp_link: "https://chat.whatsapp.com/sample-autonome"
  },
  {
    id: 8,
    groupe: "Autonome Bloc",
    type: "autonome",
    categorie_age: "Adultes",
    jour: "Samedi",
    horaires: "10:00-12:00",
    encadrants: [],
    helloasso_tarifs: ["Pratique autonome bloc"],
    naissance_min: "",
    naissance_max: "",
    whatsapp_link: "https://chat.whatsapp.com/sample-bloc"
  }
];

export const INITIAL_EMAIL_TEMPLATES: EmailTemplate[] = [
  {
    name: "Bienvenue au club",
    subject: "Bienvenue à l'ALJ Escalade Jonage {first_name} !",
    body: "Bonjour {first_name},\n\nNous avons le plaisir de vous confirmer votre inscription à la section Escalade de l'Amicale Laïque de Jonage pour la saison {season}.\n\nCréneau : {creneau}\nHoraires : {horaires}\nLieu : Mur d'escalade du Gymnase de Jonage\n\nÀ très bientôt sur les prises !\nL'équipe ALJ Escalade",
    sender_name: "ALJ Escalade Jonage"
  },
  {
    name: "Convocation compétition",
    subject: "Convocation : {name_competition}",
    body: "Bonjour {first_name},\n\nTu es sélectionné(e) pour participer à la compétition {name_competition} le {date_competition}.\n\nMerci de confirmer ta présence et de finaliser le règlement des frais d'inscription via le lien HelloAsso avant le délai imparti.\n\nSportivement,\nLes coachs ALJ Escalade",
    sender_name: "Coachs ALJ Escalade"
  },
  {
    name: "Rappel licence FFME",
    subject: "Rappel : Activation de votre licence FFME",
    body: "Bonjour {first_name},\n\nVotre licence FFME est en attente de finalisation. Merci de vous connecter sur votre espace MyFFME (https://www.myffme.fr) pour téléverser votre certificat médical ou valider votre questionnaire de santé.\n\nBonne grimpe !\nALJ Jonage Escalade",
    sender_name: "Bureau ALJ Escalade"
  }
];

export const INITIAL_MEMBERS: Member[] = [
  {
    user_id: 101,
    purchase_id: 1001,
    last_name: "POTTER",
    first_name: "Harry",
    birth_date: "2010-07-31",
    age: 16,
    gender: "Homme",
    address: "4 Privet Drive",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 11 22 33 44",
    email_primary: "harry.potter@alj-escalade.fr",
    email_secondary: "lily.potter@alj-escalade.fr",
    emergency1_name: "Sirius Black",
    emergency1_phone: "06 99 88 77 66",
    emergency2_name: "Remus Lupin",
    emergency2_phone: "06 88 77 66 55",
    payer: "Lily POTTER",
    payer_email: "lily.potter@alj-escalade.fr",
    tarif_name: "Compétition U15 U17 - nés 2008 à 2013",
    creneau_groupe: "Compétition Ados/Adultes (U15-U19)",
    creneau_details: "Vendredi 18:00-20:00",
    categorie: "U15-U19",
    amount: 260.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748921",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical validé MyFFME",
    order_ref: "CMD-2026-0001",
    order_date: "2026-06-25",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "Passé en compétition après test de niveau",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu, Rouge",
    raw_diplomas: "Initiateur SAE"
  },
  {
    user_id: 102,
    purchase_id: 1002,
    last_name: "GRANGER",
    first_name: "Hermione",
    birth_date: "2010-09-19",
    age: 16,
    gender: "Femme",
    address: "12 Rue des Oliviers",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 22 33 44 55",
    email_primary: "hermione.granger@alj-escalade.fr",
    email_secondary: "jean.granger@orange.fr",
    emergency1_name: "Jean Granger",
    emergency1_phone: "06 77 66 55 44",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Jean GRANGER",
    payer_email: "jean.granger@orange.fr",
    tarif_name: "Compétition U15 U17 - nés 2008 à 2013",
    creneau_groupe: "Compétition Ados/Adultes (U15-U19)",
    creneau_details: "Vendredi 18:00-20:00",
    categorie: "U15-U19",
    amount: 260.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748922",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0002",
    order_date: "2026-06-25",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu",
    raw_diplomas: "Juge de bloc"
  },
  {
    user_id: 103,
    purchase_id: 1003,
    last_name: "WEASLEY",
    first_name: "Ron",
    birth_date: "2011-03-01",
    age: 15,
    gender: "Homme",
    address: "Le Terrier, Rue du Port",
    zip_code: "69330",
    city: "Meyzieu",
    phone: "06 33 44 55 66",
    email_primary: "ron.weasley@alj-escalade.fr",
    email_secondary: "molly.weasley@orange.fr",
    emergency1_name: "Molly Weasley",
    emergency1_phone: "06 66 55 44 33",
    emergency2_name: "Arthur Weasley",
    emergency2_phone: "06 55 44 33 22",
    payer: "Molly WEASLEY",
    payer_email: "molly.weasley@orange.fr",
    tarif_name: "Compétition U15 U17 - nés 2008 à 2013",
    creneau_groupe: "Compétition Ados/Adultes (U15-U19)",
    creneau_details: "Vendredi 18:00-20:00",
    categorie: "U15-U19",
    amount: 260.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748923",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0003",
    order_date: "2026-06-26",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "Réduction fratrie appliquée",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert"
  },
  {
    user_id: 104,
    purchase_id: 1004,
    last_name: "WEASLEY",
    first_name: "Ginny",
    birth_date: "2012-08-11",
    age: 14,
    gender: "Femme",
    address: "Le Terrier, Rue du Port",
    zip_code: "69330",
    city: "Meyzieu",
    phone: "06 33 44 55 67",
    email_primary: "ginny.weasley@alj-escalade.fr",
    email_secondary: "molly.weasley@orange.fr",
    emergency1_name: "Molly Weasley",
    emergency1_phone: "06 66 55 44 33",
    emergency2_name: "Arthur Weasley",
    emergency2_phone: "06 55 44 33 22",
    payer: "Molly WEASLEY",
    payer_email: "molly.weasley@orange.fr",
    tarif_name: "Collège nés 2012 à 2015 - Lundi 18h30",
    creneau_groupe: "Collège Groupe A (U12-U15)",
    creneau_details: "Lundi 18:30-20:00",
    categorie: "U12-U15",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Non",
    autonomie_bloc: "Oui",
    licence_ffme: "748924",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0004",
    order_date: "2026-06-26",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "",
    raw_passports: "Jaune, Orange"
  },
  {
    user_id: 105,
    purchase_id: 1005,
    last_name: "LONGBOTTOM",
    first_name: "Neville",
    birth_date: "2010-07-30",
    age: 16,
    gender: "Homme",
    address: "8 Allée des Primevères",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 44 55 66 77",
    email_primary: "neville.longbottom@alj-escalade.fr",
    email_secondary: "augusta.longbottom@free.fr",
    emergency1_name: "Augusta Longbottom",
    emergency1_phone: "06 44 33 22 11",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Augusta LONGBOTTOM",
    payer_email: "augusta.longbottom@free.fr",
    tarif_name: "Lycée nés 2009 à 2011 - Jeudi 18h30",
    creneau_groupe: "Lycée & Jeunes (U16-U18)",
    creneau_details: "Jeudi 18:30-20:00",
    categorie: "U16-U18",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748925",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0005",
    order_date: "2026-06-27",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert"
  },
  {
    user_id: 106,
    purchase_id: 1006,
    last_name: "LOVEGOOD",
    first_name: "Luna",
    birth_date: "2011-02-13",
    age: 15,
    gender: "Femme",
    address: "21 Chemin des Collines",
    zip_code: "69330",
    city: "Jons",
    phone: "06 55 66 77 88",
    email_primary: "luna.lovegood@alj-escalade.fr",
    email_secondary: "xeno.lovegood@chicaneur.fr",
    emergency1_name: "Xenophilius Lovegood",
    emergency1_phone: "06 33 22 11 00",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Xenophilius LOVEGOOD",
    payer_email: "xeno.lovegood@chicaneur.fr",
    tarif_name: "Lycée nés 2009 à 2011 - Jeudi 18h30",
    creneau_groupe: "Lycée & Jeunes (U16-U18)",
    creneau_details: "Jeudi 18:30-20:00",
    categorie: "U16-U18",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748926",
    health_commitment: "Oui",
    photo_auth: "Non",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0006",
    order_date: "2026-06-28",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "Refus droit à l'image",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu"
  },
  {
    user_id: 107,
    purchase_id: 1007,
    last_name: "MALFOY",
    first_name: "Draco",
    birth_date: "2010-06-05",
    age: 16,
    gender: "Homme",
    address: "1 Manoir des Hauteurs",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 66 77 88 99",
    email_primary: "draco.malfoy@alj-escalade.fr",
    email_secondary: "narcissa.malfoy@prestige.fr",
    emergency1_name: "Narcissa Malfoy",
    emergency1_phone: "06 22 11 00 99",
    emergency2_name: "Lucius Malfoy",
    emergency2_phone: "06 11 00 99 88",
    payer: "Narcissa MALFOY",
    payer_email: "narcissa.malfoy@prestige.fr",
    tarif_name: "Compétition U15 U17 - nés 2008 à 2013",
    creneau_groupe: "Compétition Ados/Adultes (U15-U19)",
    creneau_details: "Vendredi 18:00-20:00",
    categorie: "U15-U19",
    amount: 260.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748927",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0007",
    order_date: "2026-06-29",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu, Rouge"
  },
  {
    user_id: 108,
    purchase_id: 1008,
    last_name: "DIGGORY",
    first_name: "Cedric",
    birth_date: "2009-09-24",
    age: 17,
    gender: "Homme",
    address: "15 Rue de la Victoire",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 77 88 99 00",
    email_primary: "cedric.diggory@alj-escalade.fr",
    email_secondary: "amos.diggory@orange.fr",
    emergency1_name: "Amos Diggory",
    emergency1_phone: "06 00 99 88 77",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Amos DIGGORY",
    payer_email: "amos.diggory@orange.fr",
    tarif_name: "Compétition U15 U17 - nés 2008 à 2013",
    creneau_groupe: "Compétition Ados/Adultes (U15-U19)",
    creneau_details: "Vendredi 18:00-20:00",
    categorie: "U15-U19",
    amount: 260.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748928",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0008",
    order_date: "2026-06-30",
    email_sent_date: "2026-07-01",
    commentaires_correctif: "Capitaine équipe compétitions",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu, Rouge, Blanc"
  },
  {
    user_id: 109,
    purchase_id: 1009,
    last_name: "CHANG",
    first_name: "Cho",
    birth_date: "2010-11-15",
    age: 15,
    gender: "Femme",
    address: "5 Impasse des Hirondelles",
    zip_code: "69330",
    city: "Villette-d'Anthon",
    phone: "06 88 99 00 11",
    email_primary: "cho.chang@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Mme Chang",
    emergency1_phone: "06 12 98 34 76",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Mme CHANG",
    payer_email: "mme.chang@wanadoo.fr",
    tarif_name: "Lycée nés 2009 à 2011 - Jeudi 18h30",
    creneau_groupe: "Lycée & Jeunes (U16-U18)",
    creneau_details: "Jeudi 18:30-20:00",
    categorie: "U16-U18",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Non",
    autonomie_bloc: "Oui",
    licence_ffme: "748929",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0009",
    order_date: "2026-07-02",
    email_sent_date: "2026-07-05",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "",
    raw_passports: "Jaune, Orange"
  },
  {
    user_id: 110,
    purchase_id: 1010,
    last_name: "CREEVEY",
    first_name: "Colin",
    birth_date: "2018-04-12",
    age: 8,
    gender: "Homme",
    address: "3 Place du Village",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 99 00 11 22",
    email_primary: "colin.creevey@alj-escalade.fr",
    email_secondary: "dennis.creevey.pere@gmail.com",
    emergency1_name: "M. Creevey",
    emergency1_phone: "06 45 67 89 10",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "M. CREEVEY",
    payer_email: "dennis.creevey.pere@gmail.com",
    tarif_name: "Enfants nés en 2017, 2018, 2019 - Mercredi 14h",
    creneau_groupe: "Enfants 2017-2019 (U8-U10)",
    creneau_details: "Mercredi 14:00-15:30",
    categorie: "U8-U10",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Non",
    autonomie_bloc: "Non",
    licence_ffme: "748930",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0010",
    order_date: "2026-07-03",
    email_sent_date: "2026-07-05",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "",
    raw_passports: "Blanc"
  },
  {
    user_id: 111,
    purchase_id: 1011,
    last_name: "BLACK",
    first_name: "Sirius",
    birth_date: "1980-11-03",
    age: 46,
    gender: "Homme",
    address: "12 Square Grimmauld",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 99 88 77 66",
    email_primary: "sirius.black@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Remus Lupin",
    emergency1_phone: "06 56 78 90 12",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Sirius BLACK",
    payer_email: "sirius.black@alj-escalade.fr",
    tarif_name: "Pratique autonome adultes",
    creneau_groupe: "Autonome Voies",
    creneau_details: "Lundi / Jeudi 20:00-22:30",
    categorie: "Adultes",
    amount: 150.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748931",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical validé",
    order_ref: "CMD-2026-0011",
    order_date: "2026-07-04",
    email_sent_date: "2026-07-05",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu, Rouge",
    raw_diplomas: "Ouvreur de club SAE"
  },
  {
    user_id: 112,
    purchase_id: 1012,
    last_name: "TONKS",
    first_name: "Nymphadora",
    birth_date: "1988-05-20",
    age: 38,
    gender: "Femme",
    address: "7 Rue de la Métamorphose",
    zip_code: "69330",
    city: "Meyzieu",
    phone: "06 55 44 33 21",
    email_primary: "nymphadora.tonks@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Remus Lupin",
    emergency1_phone: "06 56 78 90 12",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Nymphadora TONKS",
    payer_email: "nymphadora.tonks@alj-escalade.fr",
    tarif_name: "Pratique autonome bloc",
    creneau_groupe: "Autonome Bloc",
    creneau_details: "Samedi 10:00-12:00",
    categorie: "Adultes",
    amount: 150.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Non",
    autonomie_bloc: "Oui",
    licence_ffme: "748932",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0012",
    order_date: "2026-07-05",
    email_sent_date: "2026-07-08",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "",
    raw_passports: "Jaune, Orange"
  },
  {
    user_id: 113,
    purchase_id: 1013,
    last_name: "SHACKLEBOLT",
    first_name: "Kingsley",
    birth_date: "1975-08-14",
    age: 51,
    gender: "Homme",
    address: "44 Avenue de la République",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 12 34 99 88",
    email_primary: "kingsley.shacklebolt@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Alastor Moody",
    emergency1_phone: "06 01 02 03 04",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Kingsley SHACKLEBOLT",
    payer_email: "kingsley.shacklebolt@alj-escalade.fr",
    tarif_name: "Cours adultes débutants",
    creneau_groupe: "Adultes Débutants & Perfectionnement",
    creneau_details: "Mardi 20:00-22:00",
    categorie: "Adultes",
    amount: 210.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748933",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0013",
    order_date: "2026-07-06",
    email_sent_date: "2026-07-08",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert"
  },
  {
    user_id: 114,
    purchase_id: 1014,
    last_name: "DELACOUR",
    first_name: "Fleur",
    birth_date: "1994-10-30",
    age: 32,
    gender: "Femme",
    address: "9 Boulevard des Alpes",
    zip_code: "69330",
    city: "Pusignan",
    phone: "06 23 45 67 12",
    email_primary: "fleur.delacour@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Bill Weasley",
    emergency1_phone: "06 34 56 78 23",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Fleur DELACOUR",
    payer_email: "fleur.delacour@alj-escalade.fr",
    tarif_name: "Pratique autonome voies",
    creneau_groupe: "Autonome Voies",
    creneau_details: "Lundi / Jeudi 20:00-22:30",
    categorie: "Adultes",
    amount: 150.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748934",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Attestation QS-Sport",
    order_ref: "CMD-2026-0014",
    order_date: "2026-07-07",
    email_sent_date: "2026-07-08",
    commentaires_correctif: "",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu"
  },
  {
    user_id: 115,
    purchase_id: 1015,
    last_name: "KRUM",
    first_name: "Viktor",
    birth_date: "1993-04-06",
    age: 33,
    gender: "Homme",
    address: "33 Rue du Stade",
    zip_code: "69330",
    city: "Jonage",
    phone: "06 34 56 78 99",
    email_primary: "viktor.krum@alj-escalade.fr",
    email_secondary: "",
    emergency1_name: "Igor Karkaroff",
    emergency1_phone: "06 99 11 22 33",
    emergency2_name: "",
    emergency2_phone: "",
    payer: "Viktor KRUM",
    payer_email: "viktor.krum@alj-escalade.fr",
    tarif_name: "Pratique autonome voies",
    creneau_groupe: "Autonome Voies",
    creneau_details: "Lundi / Jeudi 20:00-22:30",
    categorie: "Adultes",
    amount: 150.0,
    status: "Validé",
    status_norm: "Validé",
    badge_rouge: "Oui",
    autonomie_bloc: "Oui",
    licence_ffme: "748935",
    health_commitment: "Oui",
    photo_auth: "Oui",
    document_sante: "Certificat médical",
    order_ref: "CMD-2026-0015",
    order_date: "2026-07-08",
    email_sent_date: "2026-07-10",
    commentaires_correctif: "Niveau 8a falaise",
    season_name: "2026-2027",
    passeport_orange: "Validé",
    raw_passports: "Vert, Bleu, Rouge, Blanc"
  }
];

export const INITIAL_COMPETITIONS: Competition[] = [
  {
    id: 1729000000001,
    nom: "Diagon Alley Bouldering Cup",
    date_competition: "2026-09-18",
    prix: 12.0,
    statut: "close",
    helloasso_ref: "",
    coach_ids: [1],
    participants: [
      { adherent_id: 101, nom: "POTTER", prenom: "Harry", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 12.0, date_paiement: "2026-09-10" },
      { adherent_id: 102, nom: "GRANGER", prenom: "Hermione", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 12.0, date_paiement: "2026-09-11" },
      { adherent_id: 107, nom: "MALFOY", prenom: "Draco", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 12.0, date_paiement: "2026-09-12" },
      { adherent_id: 108, nom: "DIGGORY", prenom: "Cedric", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 12.0, date_paiement: "2026-09-12" }
    ],
    resultats_url: "https://mycompet.ffme.fr/resultats/diagon-alley-2026"
  },
  {
    id: 1729000000002,
    nom: "Hogwarts Lead Open",
    date_competition: "2026-11-05",
    prix: 15.0,
    statut: "en_cours",
    helloasso_ref: "hogwarts-lead-open-dev",
    coach_ids: [1, 2],
    participants: [
      { adherent_id: 101, nom: "POTTER", prenom: "Harry", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 15.0, date_paiement: "2026-10-15" },
      { adherent_id: 102, nom: "GRANGER", prenom: "Hermione", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 15.0, date_paiement: "2026-10-16" },
      { adherent_id: 103, nom: "WEASLEY", prenom: "Ron", categorie: "U15-U19", selectionne: true, statut_paiement: "en_attente" },
      { adherent_id: 107, nom: "MALFOY", prenom: "Draco", categorie: "U15-U19", selectionne: true, statut_paiement: "paye", montant_paye: 15.0, date_paiement: "2026-10-18" },
      { adherent_id: 108, nom: "DIGGORY", prenom: "Cedric", categorie: "U15-U19", selectionne: true, statut_paiement: "en_attente" }
    ],
    resultats_url: ""
  },
  {
    id: 1729000000003,
    nom: "Championnat Régional Bloc U15-U19",
    date_competition: "2026-12-03",
    prix: 20.0,
    statut: "en_preparation",
    helloasso_ref: "",
    coach_ids: [1, 3],
    participants: [
      { adherent_id: 101, nom: "POTTER", prenom: "Harry", categorie: "U15-U19", selectionne: true, statut_paiement: "non_invite" },
      { adherent_id: 102, nom: "GRANGER", prenom: "Hermione", categorie: "U15-U19", selectionne: true, statut_paiement: "non_invite" },
      { adherent_id: 107, nom: "MALFOY", prenom: "Draco", categorie: "U15-U19", selectionne: true, statut_paiement: "non_invite" }
    ],
    resultats_url: ""
  },
  {
    id: 1729000000004,
    nom: "Rencontre Amicale Jons / Jonage",
    date_competition: "2027-01-16",
    prix: 8.0,
    statut: "en_preparation",
    helloasso_ref: "",
    coach_ids: [2],
    participants: [
      { adherent_id: 104, nom: "WEASLEY", prenom: "Ginny", categorie: "U12-U15", selectionne: true, statut_paiement: "non_invite" },
      { adherent_id: 105, nom: "LONGBOTTOM", prenom: "Neville", categorie: "U16-U18", selectionne: true, statut_paiement: "non_invite" },
      { adherent_id: 106, nom: "LOVEGOOD", prenom: "Luna", categorie: "U16-U18", selectionne: true, statut_paiement: "non_invite" }
    ],
    resultats_url: ""
  }
];

export const INITIAL_HELLOASSO_ITEMS: HelloAssoItem[] = [
  {
    id_item: 5001,
    date: "2026-10-15T14:32:00Z",
    order_ref: "HA-9901",
    payer_name: "Lily POTTER",
    payer_email: "lily.potter@alj-escalade.fr",
    user_name: "Harry POTTER",
    tarif_name: "Inscription Hogwarts Lead Open",
    amount: 15.0,
    state: "Processed",
    competition_id: 1729000000002,
    adherent_id: 101,
    is_ignored: false,
    commentaire: "Rattaché automatiquement par nom"
  },
  {
    id_item: 5002,
    date: "2026-10-16T09:12:00Z",
    order_ref: "HA-9902",
    payer_name: "Jean GRANGER",
    payer_email: "jean.granger@orange.fr",
    user_name: "Hermione GRANGER",
    tarif_name: "Inscription Hogwarts Lead Open",
    amount: 15.0,
    state: "Processed",
    competition_id: 1729000000002,
    adherent_id: 102,
    is_ignored: false
  },
  {
    id_item: 5003,
    date: "2026-10-18T18:40:00Z",
    order_ref: "HA-9903",
    payer_name: "Narcissa MALFOY",
    payer_email: "narcissa.malfoy@prestige.fr",
    user_name: "Draco MALFOY",
    tarif_name: "Inscription Hogwarts Lead Open",
    amount: 15.0,
    state: "Processed",
    competition_id: 1729000000002,
    adherent_id: 107,
    is_ignored: false
  },
  {
    id_item: 5004,
    date: "2026-10-20T11:05:00Z",
    order_ref: "HA-9904",
    payer_name: "Inconnu DUPONT",
    payer_email: "dupont@test.fr",
    user_name: "Alex DUPONT",
    tarif_name: "Don au club",
    amount: 20.0,
    state: "Processed",
    is_ignored: true,
    commentaire: "Don libre sans lien compétition"
  }
];
