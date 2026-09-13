#!/usr/bin/env python3
"""Circuit-level boundary and rounding tests against independent integer reference values."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from run import ref,field,commit,write,SNARK,HERE,P

def calculate(build,values,folder):
    write(folder/'input.json',values)
    return subprocess.run(['node',str(SNARK),'wtns','calculate',str(build/'main_js/main.wasm'),str(folder/'input.json'),str(folder/'w.wtns')],capture_output=True,text=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args();a.build=a.build.resolve()
    cases={'zero':[0]*1024,'positive-first-tie':[254,-254,1,3]+[0]*1020,'negative-first-tie':[-254,254,1,3]+[0]*1020,'negative-limit':[-(1<<39)]+[0]*1023}
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        for name,x in cases.items():
            da,q,_=ref.Model.quantize_q8k(SimpleNamespace(F=20),np.array(x,dtype=object))
            inputs={'x':[field(v) for v in x],'context':'7','inputSalt':'11','quantSalt':'13'}
            result=calculate(a.build/'quant_k1024',inputs,folder);assert result.returncode==0,(name,result.stderr)
            subprocess.run(['node',str(SNARK),'wtns','check',str(a.build/'quant_k1024/main.r1cs'),str(folder/'w.wtns')],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['node',str(SNARK),'wtns','export','json',str(folder/'w.wtns'),str(folder/'w.json')],check=True,stdout=subprocess.DEVNULL)
            witness=json.loads((folder/'w.json').read_text())
            expected_x=str(commit({'values':x,'domain':3002,'context':7,'salt':11}))
            expected_q=str(commit({'values':[int(v) for v in list(q)+list(da)],'domain':3004,'context':7,'salt':13}))
            assert witness[1:4]==[expected_x,expected_q,'7'],name
            print(name,'passed',flush=True)
        bad=inputs.copy();bad['x']=list(inputs['x']);bad['x'][0]=field(1<<39)
        assert calculate(a.build/'quant_k1024',bad,folder).returncode!=0
        print('out-of-range input rejected',flush=True)
        # Synthetic row inputs make ties in the final F24 division directly testable.
        base={'q8':['0']*1024,'da':['1']*4,'q4bits':['0']*(16*1024*4),'scbits':['0']*(16*4*8*6),'mnbits':['0']*(16*4*8*6),'D':['0']*64,'Dmin':['0']*64,'s1':['0']*64,'s2':['0']*64,'y':['0']*16,'context':'7','group':'0','quantSalt':'13','outputSalt':'17'}
        base['q8'][0]='1'
        for row in range(16):
            base['q4bits'][row*1024*4]='1';base['scbits'][row*4*8*6]='1';base['s1'][row*4]='1'
        for numerator,expected in [(1<<23,0),(3<<23,2),(-(1<<23),0),(-(3<<23),-2)]:
            candidate={k:list(v) if isinstance(v,list) else v for k,v in base.items()}
            for row in range(16):candidate['D'][row*4]=field(numerator);candidate['y'][row]=field(expected)
            assert calculate(a.build/'rows16_k1024',candidate,folder).returncode==0
            candidate['y'][0]=field(expected+1)
            assert calculate(a.build/'rows16_k1024',candidate,folder).returncode!=0
        for name,index,value in [('q8',0,-128),('D',0,1<<40),('q4bits',0,2),('da',0,1<<33)]:
            candidate={k:list(v) if isinstance(v,list) else v for k,v in base.items()};candidate[name][index]=field(value)
            assert calculate(a.build/'rows16_k1024',candidate,folder).returncode!=0,name
        print('final rounding ties, altered outputs and private ranges passed',flush=True)
if __name__=='__main__':main()
