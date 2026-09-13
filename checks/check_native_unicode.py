"""Native token-to-text checks for complete, split and malformed UTF-8 byte pieces."""
import copy,json,subprocess,unittest
from pathlib import Path
import gguf
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'models/qwen3-0.6b-q4_k_m.gguf'
BINARY=ROOT/'code/llama.cpp/build/bin/llama-receipts'

class NativeUnicode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reader=gguf.GGUFReader(str(MODEL));field=reader.fields['tokenizer.ggml.tokens']
        vocab={bytes(field.parts[i]).decode('utf8'):j for j,i in enumerate(field.data)}
        # GPT-style byte alphabet used by this registered Qwen tokenizer.
        kept=list(range(33,127))+list(range(161,173))+list(range(174,256));chars=dict(zip(kept,kept));extra=0
        for byte in range(256):
            if byte not in chars:chars[byte]=256+extra;extra+=1
        cls.ids={byte:vocab[chr(char)] for byte,char in chars.items()}
        cls.fixture=json.loads((ROOT/'checks/fixtures/receipt.json').read_text())

    def test_byte_sequences_and_tampered_display(self):
        cases=[b'ASCII',b'\x80',b'a\xf0\x9f',b'\xc0\xaf',b'\xed\xa0\x80',b'\xffa']
        for text in ['¢','€','🌍','𐍈']:
            raw=text.encode();cases.extend(raw[:n] for n in range(1,len(raw)+1))
        for raw in cases:
            value=copy.deepcopy(self.fixture);tokens=[self.ids[b] for b in raw]
            value['response']['tokens']=tokens;value['response']['text']=raw.decode('utf8',errors='replace')
            value['response']['per_token']=[dict(value['response']['per_token'][0],token=tok,position=len(value['request']['prompt_tokens'])+i) for i,tok in enumerate(tokens)]
            for changed in [False,True]:
                if changed:value['response']['text']+='wrong'
                result=subprocess.run([str(BINARY),'-m',str(MODEL),'--check-content','-'],input=json.dumps(value),capture_output=True,text=True,timeout=30)
                with self.subTest(bytes=raw.hex(),tampered=changed):self.assertEqual(result.returncode==0,not changed,result.stdout+result.stderr[-200:])

if __name__=='__main__':unittest.main()
