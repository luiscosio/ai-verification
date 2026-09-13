import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const skillDir = "/Users/luiscosio/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const workspaceDir = "/Users/luiscosio/Projects/ai-verification";
const sourcePath = path.join(workspaceDir, "docs/llama-receipts-activation-trace.pptx");
const buildDir = path.join(workspaceDir, ".codex-deck-fix");
const stagingDir = path.join(buildDir, "staging");
const finalPath = path.join(workspaceDir, "docs/llama-receipts-activation-trace-secure-v2.pptx");
const pythonExecutable = "/Users/luiscosio/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";

await fs.mkdir(stagingDir, { recursive: true });
const presentation = await PresentationFile.importPptx(await FileBlob.load(sourcePath));

const replace = (id, oldText, newText) => presentation.resolve(id).text.replace(oldText, newText);

replace("sh/65g3298r", "a first zero-knowledge proof of the native arithmetic", "a first integrity proof of the native arithmetic");
presentation.resolve("sh/m5cra54z").text = "Trace verifier\nPython, numpy, no model run; pinned topology";
presentation.resolve("sh/v6l4jq94").text = "GKR proof of a node\nExpander, M31 field, weights checked against GGUF";
presentation.resolve("sh/zi98nu94").text = "Trace verifier checks without model execution";
replace("sh/wbydknq1", "A first zero-knowledge proof of one node", "An integrity proof of one node");
presentation.resolve("sh/kfidonqx").text = "witness\npublic: q4, scales, mins,\nq8, s1, s2";
presentation.resolve("sh/ehwvat8n").text = "proof + public inputs\nExpander GKR proof";
presentation.resolve("sh/b2507exs").text = "verify proof\nchecks weights against its GGUF";
replace("sh/s7y5sv2x",
  "The 1536 by 1536 query projection of layer 7: witness from the opened bytes and the GGUF, circuit compiled, proof produced in 2.6 seconds, verified in 0.3 seconds without the weights, tampered sum rejected, float step within 2e-7.",
  "A 256 by 1536 key projection: public proof inputs checked against the GGUF, proof produced in 0.19 seconds, tampered sum rejected, float step within 2e-7.");
presentation.resolve("sh/nqlg3a5k").text = [
  "llama-receipts -m model.gguf -p \"...\" -n 32 --trace --out receipt.json       # prove",
  "verify_trace.py receipt.json --model model.gguf --expected-topology-sha256 HASH # verify",
  "spec-check trace receipt.json receipt.trace.json HASH                           # Lean",
  "zk_node.py receipt.json --model model.gguf                                      # one node",
].join("\n");

const verifierTable = presentation.resolve("tb/3uh4nud4");
verifierTable.cells.set(1, 0, "1. Root + content");
verifierTable.cells.set(1, 1, "Leaves, token arrays and displayed text match their commitments");
verifierTable.cells.set(2, 0, "2. Topology + challenge");
verifierTable.cells.set(2, 1, "Graph structure matches verifier policy; openings are unpredictable and meet its minimum");
verifierTable.cells.set(3, 0, "3. Structure");
verifierTable.cells.set(4, 0, "4. Inputs");
verifierTable.cells.set(5, 0, "5. Edges");
verifierTable.cells.set(6, 0, "6. Logits binding");
verifierTable.cells.set(7, 0, "7. Openings");

const leanTable = presentation.resolve("tb/bu903eds");
leanTable.cells.set(2, 0, "Topology, content and 32-opening policy");
leanTable.cells.set(2, 1, "checked");

const proofTable = presentation.resolve("tb/kju9one1");
proofTable.cells.set(0, 1, "Public inputs");
const proofRow = ["Kcur-13, 256 x 1536", "422,400", "2.3 s", "0.19 s", "27.9 MB", "0.20 s", "2.0e-7", "reject"];
const attackRow = ["Invalid ranges", "q4=16 / s1=p", "-", "blocked", "-", "reject", "-", "reject"];
for (let c = 0; c < 8; c += 1) {
  proofTable.cells.set(1, c, proofRow[c]);
  proofTable.cells.set(2, c, attackRow[c]);
}

presentation.resolve("im/m1sbydoj").delete();
const slide15 = presentation.resolve("sl/vaxsvy10");
const terminal = slide15.shapes.add({
  geometry: "roundRect",
  position: { left: 68.78, top: 187.2, width: 1142.4, height: 350.56 },
  fill: "#08131D",
  line: { fill: "#193247", width: 1 },
});
terminal.text = [
  "$ zk_node.py receipt.json --model model.gguf --index 916 --out zk-out",
  "node: Kcur-13 = blk.13.attn_k.weight [1536 x 256]",
  "statement: 422400 public inputs checked against the GGUF",
  "float step relative error: 2.02e-07",
  "compiled in 2.28s; witness solved in 0.03s",
  "proved in 0.19s: proof 27852548 bytes",
  "compile 2.31s, verify 0.200s: ACCEPT",
  "tampered sum: REJECT",
  "RESULT: proof verifies and public weights match the claimed model",
].join("\n");
terminal.text.style = {
  typeface: "Menlo",
  fontSize: 15,
  color: "#D8E6F0",
  autoFit: "shrinkText",
};

const montageBefore = await presentation.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(buildDir, "edited-montage.webp"), new Uint8Array(await montageBefore.arrayBuffer()));
for (const index of [0, 2, 5, 10, 13, 14, 15]) {
  const preview = await presentation.slides.getItem(index).export({ format: "png", scale: 2 });
  await fs.writeFile(path.join(buildDir, `slide-${index + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const candidatePath = path.join(stagingDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const requirements = {
  explicitTotalSlideCount: 17,
  requiredNativeTableOwnerSlides: [6, 7, 8, 11, 14],
  requiredNativeChartOwnerSlides: [],
};
const result = await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12191695,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
    ...[6, 7, 8, 11, 14].flatMap(number => ["--require-native-table-slide", String(number)]),
  ],
  requiredNativeTableOwnerSlides: requirements.requiredNativeTableOwnerSlides,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "secure-deck-v2.validation.json"),
});
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);

const checked = await PresentationFile.importPptx(await FileBlob.load(finalPath));
for (let index = 0; index < 17; index += 1) {
  const preview = await checked.slides.getItem(index).export({ format: "png", scale: 1 });
  await fs.writeFile(path.join(buildDir, `final-slide-${index + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const finalMontage = await checked.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(buildDir, "final-montage.webp"), new Uint8Array(await finalMontage.arrayBuffer()));
