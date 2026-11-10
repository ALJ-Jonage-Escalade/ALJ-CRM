/* API of the communications theme (server: api/communications/): e-mail templates and sending, the WhatsApp text,
   payment attestations. Conventions of every service: frontend/AGENTS.md § API services. */
import { unwrap, type ApiClient, type Schemas } from "../lib/client";

/** Return type inferred on purpose: each method answers the body type of its route in the contract. */
export function createCommunicationsApi(client: ApiClient) {
  return {
    // ------------------------------------------------------------ E-mails
    emailTemplates: () => unwrap(client.GET("/api/email-templates")),
    /** Creates the template, or renames and updates the one named old_name. */
    saveEmailTemplate: (body: Schemas["EmailTemplateUpdate"]) => unwrap(client.POST("/api/email-templates", { body })),
    removeEmailTemplate: (name: string) =>
      unwrap(client.DELETE("/api/email-templates/{template_name}", { params: { path: { template_name: name } } })),
    /** Whether the server can send e-mails (SMTP configured). */
    emailStatus: () => unwrap(client.GET("/api/email-status")),
    /** Sends each recipient the subject and body with their variables filled in (or a saved template's). */
    sendEmail: (body: Schemas["EmailSendRequest"]) => unwrap(client.POST("/api/send-email", { body })),

    // ------------------------------------------------------------ WhatsApp
    whatsappTemplate: () => unwrap(client.GET("/api/whatsapp-template")),
    saveWhatsappTemplate: (template: string) => unwrap(client.POST("/api/whatsapp-template", { body: { template } })),

    // ------------------------------------------------------------ Payment attestations
    /** The attestation PDF. */
    attestationPdf: (body: Schemas["AttestationRequest"]) => unwrap(client.POST("/api/attestations/preview", { body, parseAs: "blob" })),
    sendAttestation: (body: Schemas["AttestationSend"]) => unwrap(client.POST("/api/attestations/send", { body })),
  };
}
