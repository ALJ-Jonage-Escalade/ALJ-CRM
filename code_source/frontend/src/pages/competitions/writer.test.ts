import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/client";
import type { Competition } from "./competitions";
import { competitionItself, createWriter, OFFLINE_MESSAGE, WRITE_NOT_SENT_MESSAGE, type WriterDeps } from "./writer";

const COMP: Competition = { id: 10, nom: "Coupe", participants: [] };

function writerWith(online = true) {
  const deps: WriterDeps = { online: () => online, apply: vi.fn(), dropped: vi.fn(), reload: vi.fn(), toast: vi.fn() };
  return { writer: createWriter(deps), deps };
}

describe("writer", () => {
  it("refuses at once offline, without calling the API", async () => {
    const { writer, deps } = writerWith(false);
    const call = vi.fn(async () => COMP);
    expect(await writer.run(call)).toBeUndefined();
    expect(call).not.toHaveBeenCalled();
    expect(deps.toast).toHaveBeenCalledWith(OFFLINE_MESSAGE, 6000);
  });

  it("shows the competition the answer carries, reloads and says it is done", async () => {
    const { writer, deps } = writerWith();
    const answer = await writer.run(async () => ({ added: 2, competition: COMP }), {
      competition: (a) => a.competition,
      done: (a) => `${a.added} ajoutés`,
    });
    expect(answer).toEqual({ added: 2, competition: COMP });
    expect(deps.apply).toHaveBeenCalledWith(COMP);
    expect(deps.reload).toHaveBeenCalled();
    expect(deps.toast).toHaveBeenCalledWith("2 ajoutés");
    expect(writer.busy.value).toBe(false);
  });

  it("applies nothing for a write that does not answer a competition", async () => {
    const { writer, deps } = writerWith();
    await writer.run(async () => COMP);
    expect(deps.apply).not.toHaveBeenCalled();
    await writer.run(async () => COMP, { competition: competitionItself });
    expect(deps.apply).toHaveBeenCalledWith(COMP);
  });

  it.each([
    [new ApiError(0, "network", "x"), WRITE_NOT_SENT_MESSAGE],
    [new ApiError(409, "changed", "Modifié entre-temps"), "❌ Modifié entre-temps"],
  ])("tells a refusal (%s)", async (error, message) => {
    const { writer, deps } = writerWith();
    expect(await writer.run(() => Promise.reject(error))).toBeUndefined();
    expect(deps.toast).toHaveBeenCalledWith(message, 9000);
  });

  it("leaves a refusal to the caller that handles it", async () => {
    const { writer, deps } = writerWith();
    await writer.run(() => Promise.reject(new ApiError(404, null, "x")), { refused: (e) => e.status === 404 });
    expect(deps.toast).not.toHaveBeenCalled();
  });

  it("logs a bug and says so, rather than calling it a network failure", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { writer, deps } = writerWith();
    await writer.run(() => Promise.reject(new RangeError("bug")), { refused: () => true });
    expect(error).toHaveBeenCalled();
    expect(deps.toast).toHaveBeenCalledWith("❌ Erreur inattendue.", 9000);
    error.mockRestore();
  });
});
