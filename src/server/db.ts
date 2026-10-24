import type {
  Member,
  PlanningItem,
  Coach,
  Competition,
  HelloAssoItem,
  EmailTemplate,
  Participant
} from './seedData.ts';
import {
  SEASONS,
  INITIAL_COACHES,
  INITIAL_PLANNING,
  INITIAL_MEMBERS,
  INITIAL_COMPETITIONS,
  INITIAL_HELLOASSO_ITEMS,
  INITIAL_EMAIL_TEMPLATES
} from './seedData.ts';

class Database {
  private seasons = { ...SEASONS };
  private members: Member[] = [...INITIAL_MEMBERS];
  private planning: PlanningItem[] = [...INITIAL_PLANNING];
  private coaches: Coach[] = [...INITIAL_COACHES];
  private competitions: Competition[] = [...INITIAL_COMPETITIONS];
  private helloassoItems: HelloAssoItem[] = [...INITIAL_HELLOASSO_ITEMS];
  private emailTemplates: EmailTemplate[] = [...INITIAL_EMAIL_TEMPLATES];
  private whatsappTemplate: string = "Bonjour {first_name}, rappel de la séance d'escalade ALJ ce {jour} à {horaires}.";
  private resultsSettings = {
    notification_email: "admin@alj-escalade.fr",
    club_name: "JONAGE",
    auto_fetch_enabled: true
  };

  // Seasons
  getSeasons() {
    return this.seasons;
  }

  getSeasonTarifs(seasonName?: string) {
    const s = seasonName || this.seasons.active;
    const tarifsSet = new Set<string>();
    this.planning.forEach(p => {
      p.helloasso_tarifs.forEach(t => tarifsSet.add(t));
    });
    tarifsSet.add("Pratique autonome adultes");
    tarifsSet.add("Pratique autonome bloc");
    tarifsSet.add("Licence sèche");
    return {
      status: "success",
      season: s,
      tarifs: Array.from(tarifsSet)
    };
  }

  // Members
  getMembers(seasonName?: string) {
    const s = seasonName || this.seasons.active;
    const seasonMembers = this.members.filter(m => !m.season_name || m.season_name === s);
    
    // Build creneaux summary matching alj-members-sync expectations
    const creneauxMap = new Map<string, any>();
    this.planning.forEach(p => {
      creneauxMap.set(p.groupe, {
        groupe: p.groupe,
        categorie_age: p.categorie_age,
        type: p.type,
        tarifs: p.helloasso_tarifs
      });
    });

    return {
      season: s,
      members: seasonMembers,
      creneaux: Array.from(creneauxMap.values())
    };
  }

  getCompetitors() {
    // Only members registered to active competitions
    const activeComps = this.competitions.filter(c => c.statut !== "close");
    const activeIds = new Set<number>();
    activeComps.forEach(c => {
      c.participants?.forEach(p => activeIds.add(p.adherent_id));
    });
    return this.members.filter(m => activeIds.has(m.user_id));
  }

  getCompetitionMembers() {
    return this.members.map(m => ({
      id: m.user_id,
      user_id: m.user_id,
      nom: m.last_name,
      prenom: m.first_name,
      last_name: m.last_name,
      first_name: m.first_name,
      categorie: m.categorie || "U15-U19",
      creneau_groupe: m.creneau_groupe,
      licence_ffme: m.licence_ffme,
      passeport: m.passeport_orange || m.raw_passports || "Vert",
      email: m.email_primary,
      telephone: m.phone
    }));
  }

  updateMember(userId?: number, purchaseId?: number, orderRef?: string, fields: Partial<Member> = {}) {
    const idx = this.members.findIndex(m => 
      (userId && m.user_id === userId) ||
      (purchaseId && m.purchase_id === purchaseId) ||
      (orderRef && m.order_ref === orderRef)
    );
    if (idx === -1) return false;

    const current = this.members[idx];
    const updated = {
      ...current,
      ...fields,
      last_name: fields.last_name ? fields.last_name.toUpperCase() : current.last_name,
      first_name: fields.first_name || current.first_name
    };

    // Update derived fields if applicable
    if (fields.tarif_name) {
      const plan = this.planning.find(p => p.helloasso_tarifs.includes(fields.tarif_name!));
      if (plan) {
        updated.creneau_groupe = plan.groupe;
        updated.creneau_details = `${plan.jour} ${plan.horaires}`;
        updated.categorie = plan.categorie_age || plan.type;
      }
    }

    this.members[idx] = updated;
    return true;
  }

  createMember(data: any): Member {
    const newUserId = Math.max(...this.members.map(m => m.user_id), 100) + 1;
    const newPurchaseId = Math.max(...this.members.map(m => m.purchase_id), 1000) + 1;
    const season = data.season || this.seasons.active;
    const tarif = data.tarif_name || data.fields?.tarif_name || "Pratique autonome adultes";
    const plan = this.planning.find(p => p.helloasso_tarifs.includes(tarif));

    const newMember: Member = {
      user_id: newUserId,
      purchase_id: newPurchaseId,
      last_name: (data.last_name || data.fields?.last_name || "NOUVEAU").toUpperCase(),
      first_name: data.first_name || data.fields?.first_name || "Adhérent",
      birth_date: data.birth_date || data.fields?.birth_date || "2000-01-01",
      age: 24,
      gender: data.gender || data.fields?.gender || "Homme",
      address: data.address || data.fields?.address || "",
      zip_code: data.zip_code || data.fields?.zip_code || "69330",
      city: data.city || data.fields?.city || "Jonage",
      phone: data.phone || data.fields?.phone || "",
      email_primary: data.email_primary || data.fields?.email_primary || "",
      email_secondary: data.email_secondary || data.fields?.email_secondary || "",
      emergency1_name: data.emergency1_name || data.fields?.emergency1_name || "",
      emergency1_phone: data.emergency1_phone || data.fields?.emergency1_phone || "",
      emergency2_name: "",
      emergency2_phone: "",
      payer: data.payer || `${data.first_name} ${data.last_name}`,
      payer_email: data.payer_email || data.email_primary || "",
      tarif_name: tarif,
      creneau_groupe: plan ? plan.groupe : "Autonome",
      creneau_details: plan ? `${plan.jour} ${plan.horaires}` : "Lundi / Jeudi 20:00-22:30",
      categorie: plan ? plan.categorie_age : "Adultes",
      amount: plan ? (plan.type === "compétition" ? 260 : plan.type === "cours" ? 210 : 150) : 150,
      status: "Validé",
      status_norm: "Validé",
      badge_rouge: data.badge_rouge || "Non",
      autonomie_bloc: data.autonomie_bloc || "Oui",
      licence_ffme: data.licence_ffme || "",
      health_commitment: "Oui",
      photo_auth: "Oui",
      document_sante: "Attestation QS-Sport",
      order_ref: `MANUAL-${season.slice(0, 4)}-${newPurchaseId}`,
      order_date: new Date().toISOString().split("T")[0],
      email_sent_date: "",
      commentaires_correctif: "Créé manuellement dans le bureau",
      season_name: season,
      passeport_orange: ""
    };

    this.members.unshift(newMember);
    return newMember;
  }

  // Competitions
  getCompetitions(): Competition[] {
    return this.competitions;
  }

  getCompetition(id: number | string): Competition | undefined {
    return this.competitions.find(c => String(c.id) === String(id));
  }

  saveCompetition(data: any): Competition {
    const newId = data.id || Date.now();
    const existingIdx = this.competitions.findIndex(c => String(c.id) === String(newId));

    const comp: Competition = {
      id: newId,
      nom: data.nom || "Nouvelle compétition",
      date_competition: data.date_competition || new Date().toISOString().split("T")[0],
      prix: Number(data.prix) || 0,
      statut: data.statut || "en_preparation",
      helloasso_ref: data.helloasso_ref || "",
      coach_ids: Array.isArray(data.coach_ids) ? data.coach_ids : [],
      participants: Array.isArray(data.participants) ? data.participants : [],
      resultats_url: data.resultats_url || ""
    };

    if (existingIdx >= 0) {
      this.competitions[existingIdx] = { ...this.competitions[existingIdx], ...comp };
      return this.competitions[existingIdx];
    } else {
      this.competitions.unshift(comp);
      return comp;
    }
  }

  deleteCompetition(id: number | string): boolean {
    const lenBefore = this.competitions.length;
    this.competitions = this.competitions.filter(c => String(c.id) !== String(id));
    return this.competitions.length < lenBefore;
  }

  archivePastCompetitions(): number {
    const today = new Date().toISOString().split("T")[0];
    let count = 0;
    this.competitions.forEach(c => {
      if (c.date_competition < today && c.statut !== "close") {
        c.statut = "close";
        count++;
      }
    });
    return count;
  }

  addParticipant(compId: number | string, adherentId: number, selectionne = true): Participant | null {
    const comp = this.getCompetition(compId);
    if (!comp) return null;
    const member = this.members.find(m => m.user_id === adherentId);
    if (!member) return null;

    let part = comp.participants.find(p => p.adherent_id === adherentId);
    if (!part) {
      part = {
        adherent_id: adherentId,
        nom: member.last_name,
        prenom: member.first_name,
        categorie: member.categorie || "U15-U19",
        selectionne,
        statut_paiement: "non_invite"
      };
      comp.participants.push(part);
    } else {
      part.selectionne = selectionne;
    }
    return part;
  }

  updateParticipant(compId: number | string, adherentId: number, data: Partial<Participant>): Participant | null {
    const comp = this.getCompetition(compId);
    if (!comp) return null;
    const part = comp.participants.find(p => p.adherent_id === adherentId);
    if (!part) return null;
    Object.assign(part, data);
    return part;
  }

  deleteParticipant(compId: number | string, adherentId: number): boolean {
    const comp = this.getCompetition(compId);
    if (!comp) return false;
    const before = comp.participants.length;
    comp.participants = comp.participants.filter(p => p.adherent_id !== adherentId);
    return comp.participants.length < before;
  }

  cancelParticipant(compId: number | string, adherentId: number, option = "perdu"): Participant | null {
    const comp = this.getCompetition(compId);
    if (!comp) return null;
    const part = comp.participants.find(p => p.adherent_id === adherentId);
    if (!part) return null;
    part.statut_paiement = option === "reporte" ? "annule_reporte" : "annule_perdu";
    return part;
  }

  manualPayment(compId: number | string, adherentId: number, amount: number, ref?: string): Participant | null {
    const comp = this.getCompetition(compId);
    if (!comp) return null;
    const part = comp.participants.find(p => p.adherent_id === adherentId);
    if (!part) return null;
    part.statut_paiement = "paye";
    part.montant_paye = amount;
    part.date_paiement = new Date().toISOString().split("T")[0];
    part.reference_paiement = ref || "Paiement manuel direct";
    return part;
  }

  // Coaches
  getCoaches(): Coach[] {
    return this.coaches;
  }

  addCoach(nom: string, email?: string, telephone?: string): Coach {
    const newId = Math.max(...this.coaches.map(c => c.id), 0) + 1;
    const coach: Coach = {
      id: newId,
      nom: nom.trim(),
      email: email || `${nom.toLowerCase().replace(/\s+/g, ".")}@alj-escalade.fr`,
      telephone: telephone || "",
      actif: true
    };
    this.coaches.push(coach);
    return coach;
  }

  updateCoach(id: number, data: Partial<Coach>): Coach | null {
    const coach = this.coaches.find(c => c.id === id);
    if (!coach) return null;
    Object.assign(coach, data);
    return coach;
  }

  deleteCoach(id: number): boolean {
    const before = this.coaches.length;
    this.coaches = this.coaches.filter(c => c.id !== id);
    // remove coach from competitions
    this.competitions.forEach(comp => {
      comp.coach_ids = comp.coach_ids.filter(cid => cid !== id);
    });
    return this.coaches.length < before;
  }

  // Planning
  getPlanning(): PlanningItem[] {
    return this.planning;
  }

  savePlanningItem(item: any): PlanningItem {
    const id = item.id ? Number(item.id) : Math.max(...this.planning.map(p => p.id), 0) + 1;
    const planItem: PlanningItem = {
      id,
      groupe: item.groupe || "Nouveau créneau",
      type: item.type || "cours",
      categorie_age: item.categorie_age || "",
      jour: item.jour || "Lundi",
      horaires: item.horaires || "18:00-19:30",
      encadrants: Array.isArray(item.encadrants) ? item.encadrants : [],
      helloasso_tarifs: Array.isArray(item.helloasso_tarifs) ? item.helloasso_tarifs : [item.groupe],
      naissance_min: item.naissance_min || "",
      naissance_max: item.naissance_max || "",
      whatsapp_link: item.whatsapp_link || ""
    };

    const idx = this.planning.findIndex(p => p.id === id);
    if (idx >= 0) {
      this.planning[idx] = planItem;
    } else {
      this.planning.push(planItem);
    }
    return planItem;
  }

  deletePlanningItem(id: number): boolean {
    const before = this.planning.length;
    this.planning = this.planning.filter(p => p.id !== id);
    return this.planning.length < before;
  }

  // Email Templates
  getEmailTemplates(): EmailTemplate[] {
    return this.emailTemplates;
  }

  saveEmailTemplate(template: EmailTemplate): EmailTemplate {
    const idx = this.emailTemplates.findIndex(t => t.name === template.name);
    if (idx >= 0) {
      this.emailTemplates[idx] = template;
    } else {
      this.emailTemplates.push(template);
    }
    return template;
  }

  deleteEmailTemplate(name: string): boolean {
    const before = this.emailTemplates.length;
    this.emailTemplates = this.emailTemplates.filter(t => t.name !== name);
    return this.emailTemplates.length < before;
  }

  getWhatsappTemplate(): string {
    return this.whatsappTemplate;
  }

  saveWhatsappTemplate(template: string): void {
    this.whatsappTemplate = template;
  }

  // HelloAsso
  getHelloAssoItems(): HelloAssoItem[] {
    return this.helloassoItems;
  }

  linkHelloAssoItem(idItem: number, competitionId: number, adherentId: number, commentaire?: string): boolean {
    const item = this.helloassoItems.find(i => i.id_item === idItem);
    if (!item) return false;
    item.competition_id = competitionId;
    item.adherent_id = adherentId;
    item.is_ignored = false;
    if (commentaire) item.commentaire = commentaire;

    // Report payment to competition participant
    this.manualPayment(competitionId, adherentId, item.amount, `HelloAsso: ${item.order_ref}`);
    return true;
  }

  ignoreHelloAssoItem(idItem: number): boolean {
    const item = this.helloassoItems.find(i => i.id_item === idItem);
    if (!item) return false;
    item.is_ignored = !item.is_ignored;
    return true;
  }

  syncHelloAsso(): { stats: { nb_items: number, nb_new: number } } {
    return {
      stats: {
        nb_items: this.helloassoItems.length,
        nb_new: 0
      }
    };
  }

  // FFME stats
  getFfmeStats() {
    const total = this.members.length;
    const licensed = this.members.filter(m => Boolean(m.licence_ffme && m.licence_ffme.trim())).length;
    return {
      estimated_total: total,
      already_licensed: licensed,
      pending: total - licensed
    };
  }

  // Presence config
  getPresenceConfig() {
    const cours = this.planning.filter(p => p.type === "cours" || p.type === "compétition");
    return {
      status: "success",
      cours_groups: cours.map(c => ({
        id: c.id,
        nom: c.groupe,
        jour: c.jour,
        horaires: c.horaires,
        encadrants: c.encadrants
      })),
      autonomes_count: this.members.filter(m => m.creneau_groupe.toLowerCase().includes("autonome")).length
    };
  }

  // Settings
  getResultsSettings() {
    return this.resultsSettings;
  }

  updateResultsSettings(settings: Partial<typeof this.resultsSettings>) {
    Object.assign(this.resultsSettings, settings);
    return this.resultsSettings;
  }
}

export const db = new Database();
