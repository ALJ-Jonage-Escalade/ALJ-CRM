import { describe, expect, it } from "vitest";
import goldenText from "./templateVariables.golden.json?raw";
import {
  amountText,
  DEMO_VALUES,
  firstNameText,
  lastNameText,
  renderHtml,
  renderTemplate,
  TEMPLATE_VARIABLES,
  templateError,
  toKeys,
  toLabels,
  type TemplateKind,
} from "./templateVariables";

/** The cases shared with the server (tests/domain/test_email_variables_golden.py): both must give the same text. */
interface Golden {
  variables: { key: string; label: string; kinds: string[]; demo: string; aliases: string[] }[];
  render: { text: string; values: Record<string, string>; html?: boolean; expected: string }[];
  html: { text: string; values: Record<string, string>; expected: string }[];
  amounts: { amount: number | null; expected: string }[];
  names: { first_name: string; last_name: string; expected: [string, string] }[];
  convert: { text: string; keys: string; labels: string }[];
  errors: { texts: string[]; kind?: TemplateKind; expected: string | null }[];
}
const golden = JSON.parse(goldenText) as Golden;

describe("template variables, as the server", () => {
  it("lists the server's variables", () => {
    expect(TEMPLATE_VARIABLES).toEqual(golden.variables);
  });

  it.each(golden.render)("renders %#", (c) => {
    expect(renderTemplate(c.text, c.values, { html: c.html })).toBe(c.expected);
  });

  it.each(golden.html)("builds the HTML part %#", (c) => {
    expect(renderHtml(c.text, c.values)).toBe(c.expected);
  });

  it.each(golden.amounts)("formats the amount $amount", (c) => {
    expect(amountText(c.amount)).toBe(c.expected);
  });

  it.each(golden.names)("writes $first_name $last_name", (c) => {
    expect([firstNameText(c.first_name), lastNameText(c.last_name)]).toEqual(c.expected);
  });

  it.each(golden.convert)("converts %#", (c) => {
    expect([toKeys(c.text), toLabels(c.text)]).toEqual([c.keys, c.labels]);
  });

  it.each(golden.errors)("validates %#", (c) => {
    expect(templateError(c.texts, c.kind)).toBe(c.expected);
  });

  it("has a demo value for each variable", () => {
    expect(renderTemplate("{Prénom} : {Montant de la compétition}", DEMO_VALUES)).toBe("Alex : 15,50");
  });
});
