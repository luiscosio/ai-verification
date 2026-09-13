import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "/Users/luiscosio/Projects/ai-verification/docs/llama-receipts-activation-trace.pptx";
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
for (const search of ["zero-knowledge proof", "Private inputs", "private: q4", "private weights", "never sees the weights", "Orion", "7 checks", "What the trace verifier checks", "6.5 MB", "Merkle root over 8,086", "verify_trace.py receipt.json"]) {
  const result = await presentation.inspect({
    kind: "slide,textbox,shape,table,notes,layout",
    search,
    maxChars: 12000,
  });
  process.stdout.write(`SEARCH ${search}\n${result.ndjson}\n`);
}
const slides = await presentation.inspect({ kind: "slide", maxChars: 12000 });
process.stdout.write(`SLIDES\n${slides.ndjson}\n`);
const slide15 = await presentation.inspect({ target: { id: "sl/vaxsvy10", beforeLines: 0, afterLines: 20 }, kind: "slide,textbox,shape,image,notes,layout", maxChars: 10000 });
process.stdout.write(`SLIDE15\n${slide15.ndjson}\n`);
const tables = await presentation.inspect({ kind: "table", maxChars: 12000 });
process.stdout.write(`TABLES\n${tables.ndjson}\n`);
const slide14 = await presentation.inspect({ target: { id: "sl/6lsnupw7", beforeLines: 0, afterLines: 30 }, kind: "slide,textbox,shape,table,notes", maxChars: 12000 });
process.stdout.write(`SLIDE14\n${slide14.ndjson}\n`);
