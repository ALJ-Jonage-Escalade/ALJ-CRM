import { Router } from 'express';
import type { Request, Response } from 'express';
import { db } from './db.ts';

export const apiRouter = Router();

// Seasons & Tarifs
apiRouter.get('/seasons', (req: Request, res: Response) => {
  res.json(db.getSeasons());
});

apiRouter.get('/season-tarifs', (req: Request, res: Response) => {
  const season = req.query.season as string | undefined;
  res.json(db.getSeasonTarifs(season));
});

// Members
apiRouter.get('/members', (req: Request, res: Response) => {
  const season = req.query.season as string | undefined;
  res.json(db.getMembers(season));
});

apiRouter.get('/members/competitors', (req: Request, res: Response) => {
  res.json(db.getCompetitors());
});

apiRouter.post('/members/update', (req: Request, res: Response) => {
  const { user_id, purchase_id, order_ref, fields } = req.body;
  const ok = db.updateMember(user_id, purchase_id, order_ref, fields);
  if (!ok) {
    return res.status(400).json({ status: "error", message: "Adhérent introuvable." });
  }
  res.json({
    status: "success",
    message: "Fiche adhérent mise à jour avec succès.",
    user_id,
    fields
  });
});

apiRouter.post(['/members/create', '/members/add'], (req: Request, res: Response) => {
  const member = db.createMember(req.body);
  res.json({
    status: "success",
    message: "Adhérent ajouté avec succès.",
    member
  });
});

// Competitions
apiRouter.get('/competitions', (req: Request, res: Response) => {
  res.json(db.getCompetitions());
});

apiRouter.post('/competitions', (req: Request, res: Response) => {
  const comp = db.saveCompetition(req.body);
  res.json(comp);
});

apiRouter.patch('/competitions/:id', (req: Request, res: Response) => {
  const comp = db.saveCompetition({ ...req.body, id: req.params.id });
  res.json(comp);
});

apiRouter.delete('/competitions/:id', (req: Request, res: Response) => {
  const ok = db.deleteCompetition(req.params.id);
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.post('/competitions/archive-past', (req: Request, res: Response) => {
  const count = db.archivePastCompetitions();
  res.json({ status: "success", archived_count: count });
});

apiRouter.post('/competitions/:id/participants', (req: Request, res: Response) => {
  const { adherent_id, selectionne } = req.body;
  const part = db.addParticipant(req.params.id, Number(adherent_id), selectionne);
  if (!part) return res.status(404).json({ error: "Compétition ou adhérent introuvable" });
  res.json(db.getCompetition(req.params.id));
});

apiRouter.patch('/competitions/:id/participants/:adherent_id', (req: Request, res: Response) => {
  const part = db.updateParticipant(req.params.id, Number(req.params.adherent_id), req.body);
  if (!part) return res.status(404).json({ error: "Participant introuvable" });
  res.json(db.getCompetition(req.params.id));
});

apiRouter.delete('/competitions/:id/participants/:adherent_id', (req: Request, res: Response) => {
  const ok = db.deleteParticipant(req.params.id, Number(req.params.adherent_id));
  if (!ok) return res.status(404).json({ error: "Participant introuvable" });
  res.json(db.getCompetition(req.params.id));
});

apiRouter.post('/competitions/:id/participants/:adherent_id/cancel', (req: Request, res: Response) => {
  const option = req.body.option || "perdu";
  const part = db.cancelParticipant(req.params.id, Number(req.params.adherent_id), option);
  res.json(db.getCompetition(req.params.id));
});

apiRouter.post('/competitions/:id/participants/:adherent_id/manual-payment', (req: Request, res: Response) => {
  const { montant, reference } = req.body;
  const part = db.manualPayment(req.params.id, Number(req.params.adherent_id), Number(montant) || 0, reference);
  res.json(db.getCompetition(req.params.id));
});

apiRouter.post('/competitions/:id/fetch-results', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Résultats synchronisés avec succès.", nb_resultats: 4 });
});

apiRouter.post('/competitions/:id/check-all-paid', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Vérification des paiements effectuée." });
});

apiRouter.post('/competitions/cron/fetch-results', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Cron de résultats terminé avec succès." });
});

// Coaches
apiRouter.get('/coaches', (req: Request, res: Response) => {
  res.json(db.getCoaches());
});

apiRouter.post('/coaches', (req: Request, res: Response) => {
  const { nom, email, telephone } = req.body;
  const coach = db.addCoach(nom, email, telephone);
  res.json(coach);
});

apiRouter.put('/coaches/:id', (req: Request, res: Response) => {
  const coach = db.updateCoach(Number(req.params.id), req.body);
  if (!coach) return res.status(404).json({ error: "Coach introuvable" });
  res.json(coach);
});

apiRouter.delete('/coaches/:id', (req: Request, res: Response) => {
  const ok = db.deleteCoach(Number(req.params.id));
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.get('/competition-members', (req: Request, res: Response) => {
  res.json(db.getCompetitionMembers());
});

// Planning
apiRouter.get('/planning', (req: Request, res: Response) => {
  res.json(db.getPlanning());
});

apiRouter.post('/planning', (req: Request, res: Response) => {
  res.json(db.getPlanning());
});

apiRouter.post('/planning/item', (req: Request, res: Response) => {
  const item = db.savePlanningItem(req.body);
  res.json(item);
});

apiRouter.delete('/planning/item/:id', (req: Request, res: Response) => {
  const ok = db.deletePlanningItem(Number(req.params.id));
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.get('/planning/export', (req: Request, res: Response) => {
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="planning_escalade.csv"');
  let csv = "ID,Groupe,Type,Jour,Horaires,Encadrants,Tarifs\n";
  db.getPlanning().forEach(p => {
    csv += `"${p.id}","${p.groupe}","${p.type}","${p.jour}","${p.horaires}","${p.encadrants.join(', ')}","${p.helloasso_tarifs.join('; ')}"\n`;
  });
  res.send(csv);
});

// Presence
apiRouter.get('/presence/config', (req: Request, res: Response) => {
  res.json(db.getPresenceConfig());
});

apiRouter.post('/presence/export', (req: Request, res: Response) => {
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="feuilles_de_presence.csv"');
  res.send("Groupe,Nom,Prenom,Date\n");
});

// Email templates
apiRouter.get('/email-templates', (req: Request, res: Response) => {
  res.json({ templates: db.getEmailTemplates() });
});

apiRouter.post('/email-templates', (req: Request, res: Response) => {
  const tpl = db.saveEmailTemplate(req.body);
  res.json(tpl);
});

apiRouter.delete('/email-templates/:name', (req: Request, res: Response) => {
  const ok = db.deleteEmailTemplate(req.params.name);
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.get('/email-status', (req: Request, res: Response) => {
  res.json({ status: "ready", quota_remaining: 500 });
});

apiRouter.post('/send-email', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Email envoyé avec succès." });
});

apiRouter.post('/preview-email', (req: Request, res: Response) => {
  res.json({ status: "success", preview_html: `<div style="padding:16px;">${req.body.body || ""}</div>` });
});

// WhatsApp
apiRouter.get('/whatsapp-template', (req: Request, res: Response) => {
  res.json({ template: db.getWhatsappTemplate() });
});

apiRouter.post('/whatsapp-template', (req: Request, res: Response) => {
  db.saveWhatsappTemplate(req.body.template || "");
  res.json({ status: "success" });
});

// Attestations
apiRouter.post('/attestations/preview', (req: Request, res: Response) => {
  res.json({ status: "success", preview_url: "#" });
});

apiRouter.post('/attestations/send', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Attestation envoyée par e-mail." });
});

// HelloAsso
apiRouter.get('/helloasso/items', (req: Request, res: Response) => {
  res.json(db.getHelloAssoItems());
});

apiRouter.put('/helloasso/items/:id/ignore', (req: Request, res: Response) => {
  const ok = db.ignoreHelloAssoItem(Number(req.params.id));
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.put('/helloasso/items/:id/link', (req: Request, res: Response) => {
  const { competition_id, adherent_id, commentaire } = req.body;
  const ok = db.linkHelloAssoItem(Number(req.params.id), Number(competition_id), Number(adherent_id), commentaire);
  res.json({ status: ok ? "success" : "not_found" });
});

apiRouter.post('/helloasso/sync', (req: Request, res: Response) => {
  res.json(db.syncHelloAsso());
});

// FFME
apiRouter.get('/ffme/stats', (req: Request, res: Response) => {
  res.json(db.getFfmeStats());
});

apiRouter.post('/ffme/preview', (req: Request, res: Response) => {
  res.json({ status: "success", valid_records: 12, errors: [] });
});

apiRouter.post('/ffme/import', (req: Request, res: Response) => {
  res.json({ status: "success", imported: 12 });
});

apiRouter.get('/ffme/export', (req: Request, res: Response) => {
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="export_licences_ffme.csv"');
  let csv = "Nom,Prenom,DateNaissance,Sexe,LicenceFFME,CertificatMedical\n";
  db.getMembers().members.forEach(m => {
    csv += `"${m.last_name}","${m.first_name}","${m.birth_date}","${m.gender}","${m.licence_ffme}","${m.document_sante}"\n`;
  });
  res.send(csv);
});

// Integrations / System
apiRouter.get('/auth/google/status', (req: Request, res: Response) => {
  res.json({ status: "connected", email: "admin@alj-escalade.fr", expires_in_days: 180 });
});

apiRouter.get('/auth/google/login', (req: Request, res: Response) => {
  const returnTo = (req.query.return_to as string) || "/bureau/parametres";
  res.redirect(returnTo);
});

apiRouter.post('/auth/google/test', (req: Request, res: Response) => {
  res.json({
    status: "ok",
    results: {
      auth: "OK",
      drive: "OK",
      gmail: "OK"
    }
  });
});

apiRouter.post('/auth/google/update-token', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Jeton Google OAuth actualisé." });
});

apiRouter.get('/cloud-db/status', (req: Request, res: Response) => {
  res.json({
    db_exists: true,
    healthy: true,
    records_count: db.getMembers().members.length,
    last_sync: new Date().toISOString()
  });
});

apiRouter.post('/cloud-db/sync', (req: Request, res: Response) => {
  res.json({ status: "success", message: "Base synchronisée avec succès." });
});

apiRouter.get('/dashboard', (req: Request, res: Response) => {
  res.json({
    members_total: db.getMembers().members.length,
    competitions_active: db.getCompetitions().filter(c => c.statut !== "close").length,
    coaches_count: db.getCoaches().length,
    seasons: db.getSeasons()
  });
});

apiRouter.get('/settings/competitions-results', (req: Request, res: Response) => {
  res.json(db.getResultsSettings());
});

apiRouter.post('/settings/competitions-results', (req: Request, res: Response) => {
  res.json(db.updateResultsSettings(req.body));
});

apiRouter.get('/web-version', (req: Request, res: Response) => {
  res.json({ web_version: "25" });
});
